"""
Simulated broker for paper trading - ASYNC version.
Implements Broker + DataProvider interfaces using async Alpha Vantage + Yahoo Finance.
"""

import asyncio
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import database as db
from alpha_vantage import get_async_client
from binance_data import fetch_binance_candles
from broker import Broker, DataProvider
from database import async_save_account, async_save_quote, async_save_trade
from historical_data import fetch_yahoo_historical
from timezone import now_warsaw

INITIAL_BALANCE_USD = 3000.0

INSTRUMENTS = {
    "XAU": {"name": "Gold", "multiplier": 1, "pip_size": 0.01, "lot_size": 0.003, "leverage": 20},
    "XAG": {"name": "Silver", "multiplier": 1, "pip_size": 0.001, "lot_size": 0.003, "leverage": 10},
    "US100": {"name": "Nasdaq-100", "multiplier": 1, "pip_size": 0.01, "lot_size": 0.003, "leverage": 20},
    "BTC": {"name": "Bitcoin", "multiplier": 1, "pip_size": 1.0, "lot_size": 0.001, "leverage": 2},
}


class AsyncSimulatedDataProvider:
    """Async data provider with multiple sources."""

    _YAHOO_INTERVAL = {
        "1": "1m",
        "5": "5m",
        "15": "15m",
        "30": "30m",
        "60": "1h",
        "D": "1d",
    }

    def __init__(self):
        self._alpha = get_async_client()

    async def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get quote - tries Alpha Vantage async (except BTC), then Yahoo, then DB."""
        # Skip Alpha Vantage for BTC - it returns ETF ticker "BTC" not Bitcoin
        if symbol != "BTC":
            # 1. Alpha Vantage (async)
            try:
                q = await asyncio.wait_for(self._alpha.get_quote(symbol), timeout=5.0)
                if q and q.get("price"):
                    await async_save_quote(symbol, q)
                    return q
            except Exception:
                pass

        # 2. Yahoo Finance (sync - runs in thread)
        try:
            yahoo_interval = self._YAHOO_INTERVAL.get("60", "1h")
            candles = await asyncio.to_thread(fetch_yahoo_historical, symbol, period_days=2, interval=yahoo_interval)
            if candles and len(candles) > 0:
                last = candles[-1]
                q = {
                    "symbol": symbol,
                    "price": last["close"],
                    "high": last["high"],
                    "low": last["low"],
                    "open": last["open"],
                    "volume": last.get("volume", 0),
                    "timestamp": last.get("timestamp", datetime.utcnow().isoformat()),
                    "source": "yahoo",
                }
                await async_save_quote(symbol, q)
                return q
        except Exception:
            pass

        # 3. DB cache
        cached = db.load_quote(symbol)
        if cached and cached.get("quote"):
            return cached["quote"]
        return None

    async def get_candles(
        self, symbol: str, resolution: str = "60", count: int = 100
    ) -> Optional[List[Dict[str, Any]]]:
        """Get candles - async with fallbacks."""
        candles = None
        source = ""

        # 0. Binance for BTC (fastest, free)
        if symbol == "BTC":
            try:
                import time
                interval = {"1": "1m", "5": "5m", "15": "15m", "30": "30m", "60": "1h", "240": "4h", "D": "1d"}.get(resolution, "1h")
                binance_symbol = "BTCUSDT"
                # Fetch last N*2 candles to account for possible gaps, then take last N
                fetched = await asyncio.to_thread(
                    fetch_binance_candles, binance_symbol, interval, limit=count * 2
                )
                if fetched and len(fetched) > 0:
                    # Binance returns newest first, reverse for chronological
                    fetched = list(reversed(fetched))
                    candles = fetched[-count:]
                    source = "binance"
            except Exception:
                candles = None

        # Skip Alpha Vantage for BTC - it returns ETF ticker "BTC" not Bitcoin
        if symbol != "BTC":
            # 1. Alpha Vantage (async)
            try:
                candles = await asyncio.wait_for(self._alpha.get_candles(symbol, resolution, count), timeout=10.0)
                if candles and len(candles) > 0:
                    source = "alpha_vantage"
            except Exception:
                candles = None

        # 2. Yahoo Finance (in thread)
        if not candles:
            try:
                yahoo_interval = self._YAHOO_INTERVAL.get(resolution, "1h")
                period = 30 if resolution in ("1", "5", "15", "30", "60") else 365
                candles = await asyncio.to_thread(
                    fetch_yahoo_historical, symbol, period_days=period, interval=yahoo_interval
                )
                if candles and len(candles) > 0:
                    candles = candles[-count:]
                    source = "yahoo"
            except Exception:
                candles = None

        # 3. DB history
        if not candles:
            history = await asyncio.to_thread(db.load_candle_history, symbol, resolution, limit=count)
            if history:
                candles = history
                source = "db_history"

        # 4. Aggregation
        if not candles:
            candles = await self._try_aggregate(symbol, resolution, count)
            if candles:
                source = "aggregated"

        # 5. Cache fallback
        if not candles:
            cached = await asyncio.to_thread(db.load_candles, symbol, resolution)
            if cached and cached.get("candles"):
                candles = cached["candles"]
                source = "cache"

        # Add live candle with current price if we have data
        if candles and len(candles) > 0:
            try:
                quote = await self.get_quote(symbol)
                if quote and quote.get("price"):
                    current_price = quote["price"]
                    now = datetime.utcnow()
                    # Create timestamp for current period
                    resolution_minutes = int(resolution) if resolution != "D" else 1440
                    minute_quant = (now.minute // resolution_minutes) * resolution_minutes
                    period_start = now.replace(minute=minute_quant, second=0, microsecond=0)
                    last_ts = candles[-1].get("timestamp", "")
                    if last_ts:
                        last_dt = datetime.strptime(last_ts.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
                        if period_start > last_dt:
                            # Add live candle
                            live_candle = {
                                "timestamp": period_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                "open": current_price,
                                "high": current_price,
                                "low": current_price,
                                "close": current_price,
                                "volume": 0
                            }
                            candles.append(live_candle)
                            source = source + "_live" if source else "live"
            except Exception as e:
                print(f"[get_candles] Failed to add live candle: {e}")

        # Save to DB
        if candles and source not in ("db_history", "aggregated", "cache"):
            await asyncio.to_thread(db.store_candles, symbol, resolution, candles, source)
            await asyncio.to_thread(db.save_candles, symbol, resolution, candles, source)

        return candles

    async def _try_aggregate(self, symbol: str, target_resolution: str, count: int) -> Optional[List[Dict[str, Any]]]:
        """Try to build candles from smaller intervals."""
        source_candidates = {
            "5": ["1"],
            "15": ["5", "1"],
            "30": ["15", "5", "1"],
            "60": ["30", "15", "5", "1"],
            "240": ["60", "30", "15"],
            "D": ["60", "30", "15", "5", "1"],
        }
        candidates = source_candidates.get(target_resolution, [])
        for src_res in candidates:
            stored = await asyncio.to_thread(db.load_candle_history, symbol, src_res)
            if stored and len(stored) >= 2:
                aggregated = db.aggregate_candles(stored, target_resolution)
                if aggregated and len(aggregated) >= min(10, count):
                    return aggregated[-count:]
        return None


class AsyncSimulatedBroker(Broker):
    """Async paper-trading broker."""

    def __init__(self, initial_balance: Optional[float] = None, data_provider=None):
        self.account: Dict[str, Any] = db.load_account()
        # Allow overriding initial balance for testing
        if initial_balance is not None:
            self.account["balance_usd"] = initial_balance
            self.account["equity_usd"] = initial_balance
            self.account["available_usd"] = initial_balance
            self.account["peak_equity_usd"] = initial_balance
        self.open_positions: List[Dict[str, Any]] = db.load_open_positions()
        self.closed_positions: List[Dict[str, Any]] = db.load_closed_positions()
        # Use external data_provider if provided, otherwise create mock
        self._data_provider = data_provider if data_provider else AsyncSimulatedDataProvider()
        self._max_positions = 3  # Default max positions
        self._dynamic_exit_enabled = False
        self._signal_decay_threshold = 0.3  # Close if signal drops by 30%

    def set_max_positions(self, max_pos: int):
        """Set maximum open positions."""
        self._max_positions = max_pos

    def enable_dynamic_exit(self, enabled: bool = True, decay_threshold: float = 0.3):
        """Enable dynamic position management - close positions with weak signals to make room for new ones."""
        self._dynamic_exit_enabled = enabled
        self._signal_decay_threshold = decay_threshold

    def check_dynamic_exit(self, current_signals: Dict[str, float]) -> List[str]:
        """
        Check if any positions should be closed for Dynamic Positions.
        Returns list of position IDs to close.
        
        Logic:
        - Position has profit (unrealized_pnl > 0)
        - Current signal for that symbol is weaker than original by more than threshold
        - OR current signal is too weak (|signal| < 0.05 = neutral zone)
        """
        if not self._dynamic_exit_enabled:
            return []
        
        NEUTRAL_THRESHOLD = 0.05  # Signals between -0.05 and 0.05 are neutral
        
        positions_to_close = []
        for pos in self.open_positions:
            symbol = pos.get("symbol")
            direction = pos.get("direction", "buy")
            original_score = pos.get("original_signal_score", 0)
            
            # If no original score stored (old position), use current score as baseline
            if original_score == 0 and symbol in current_signals:
                original_score = current_signals[symbol]
            current_pnl = pos.get("unrealized_pnl_usd", 0)
            
            if current_pnl <= 0:
                continue  # Only close profitable positions
            
            if symbol not in current_signals:
                continue
                
            current_score = current_signals[symbol]
            
            # CLOSE if signal is in neutral zone (|signal| < 0.05)
            if abs(current_score) < NEUTRAL_THRESHOLD:
                positions_to_close.append(pos["id"])
                print(f"[DYNAMIC-EXIT] {symbol} ({direction}) closing: signal now {current_score:.3f} (neutral zone)")
                continue
            
            # For BUY positions: close if signal drops significantly
            if direction == "buy" and original_score > 0:
                if current_score < original_score * (1 - self._signal_decay_threshold):
                    positions_to_close.append(pos["id"])
                    print(f"[DYNAMIC-EXIT] {symbol} closing: decay {(1 - current_score/original_score)*100:.1f}%")
            
            # For SELL positions: close if signal becomes less negative (weaker sell)
            elif direction == "sell" and original_score < 0:
                if current_score > original_score * (1 - self._signal_decay_threshold):  # less negative
                    positions_to_close.append(pos["id"])
                    print(f"[DYNAMIC-EXIT] {symbol} closing: sell signal weakened from {original_score:.3f} to {current_score:.3f}")
                    
        return positions_to_close

    def get_account(self) -> Dict[str, Any]:
        return self.account

    def get_open_positions(self) -> List[Dict[str, Any]]:
        return self.open_positions

    def get_closed_positions(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.closed_positions[:limit]

    async def open_position(
        self,
        symbol: str,
        direction: str,
        size: float,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        entry_price: Optional[float] = None,
        signal_score: float = 0.0,
    ) -> Dict[str, Any]:
        """Async open position."""
        return await self._async_open_position(symbol, direction, size, take_profit, stop_loss, entry_price, signal_score)

    async def _async_open_position(
        self,
        symbol: str,
        direction: str,
        size: float,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        entry_price: Optional[float] = None,
        signal_score: float = 0.0,
    ) -> Dict[str, Any]:
        """Async position opening."""
        if symbol not in INSTRUMENTS:
            return {"error": f"Unknown instrument: {symbol}"}
        if direction not in ("buy", "sell"):
            return {"error": "Direction must be 'buy' or 'sell'"}
        if entry_price is None:
            return {"error": "entry_price is required"}
        if size <= 0:
            return {"error": "Invalid size: must be greater than 0"}

        # Check max positions limit
        max_positions = getattr(self, '_max_positions', 3)
        if len(self.open_positions) >= max_positions:
            return {"error": f"Max {max_positions} positions reached"}

        leverage = INSTRUMENTS[symbol].get("leverage", 20)
        margin_usd = entry_price * size / leverage

        available = self.account.get("available_usd", 0)
        if margin_usd > available:
            return {
                "error": "Insufficient margin",
                "required_usd": margin_usd,
                "available_usd": available,
            }

        # Default TP/SL - fallback (should never happen when called from main.py)
        # TODO: Remove this fallback - main.py should always calculate ATR-based SL/TP
        # This is a safety net that should be removed once ATR calculation is proven stable
        atr = entry_price * 0.01
        if take_profit is None:
            take_profit = entry_price + atr * 3 if direction == "buy" else entry_price - atr * 3
        if stop_loss is None:
            stop_loss = entry_price - atr * 2 if direction == "buy" else entry_price + atr * 2

        position = {
            "id": str(uuid.uuid4())[:8],
            "symbol": symbol,
            "name": INSTRUMENTS[symbol]["name"],
            "direction": direction,
            "size": size,
            "leverage": leverage,
            "entry_price": entry_price,
            "current_price": entry_price,
            "take_profit": round(take_profit, 2),
            "stop_loss": round(stop_loss, 2),
            "trailing_enabled": False,
            "margin_usd": round(margin_usd, 2),
            "unrealized_pnl_usd": 0.0,
            "original_signal_score": signal_score,
            "opened_at": datetime.utcnow().isoformat(),
            "status": "open",
        }

        self.open_positions.append(position)
        self.account["used_margin"] = self.account.get("used_margin", 0) + margin_usd
        self.account["available_usd"] = self.account["balance_usd"] - self.account["used_margin"]
        self.account["open_trades"] = len(self.open_positions)
        self.account["positions"] = len(self.open_positions)

        await async_save_trade(position)
        await async_save_account(self.account)

        return {"status": "opened", "position": position}

    async def close_position(self, position_id: str, exit_price: Optional[float] = None) -> Dict[str, Any]:
        """Async close position."""
        return await self._async_close_position(position_id, exit_price)

    async def _async_close_position(self, position_id: str, exit_price: Optional[float] = None) -> Dict[str, Any]:
        """Async position closing."""
        position = None
        pos_index = None
        for i, pos in enumerate(self.open_positions):
            if pos["id"] == position_id:
                position = pos
                pos_index = i
                break

        if not position:
            return {"error": f"Position {position_id} not found"}

        if exit_price is None:
            # Always get fresh price for accurate P&L calculation
            try:
                candles = await self._data_provider.get_candles(position["symbol"], "60", 1)
                if candles and len(candles) > 0:
                    exit_price = candles[-1]["close"]
                else:
                    # Fallback to quote
                    quote = await self._data_provider.get_quote(position["symbol"])
                    exit_price = quote.get("price") if quote else position.get("current_price", position["entry_price"])
            except Exception:
                # Last resort fallback
                exit_price = position.get("current_price", position["entry_price"])

        pos_leverage = position.get("leverage", 1)
        if position["direction"] == "buy":
            pnl_usd = (exit_price - position["entry_price"]) * position["size"] * pos_leverage
        else:
            pnl_usd = (position["entry_price"] - exit_price) * position["size"] * pos_leverage

        self.account["balance_usd"] = round(self.account["balance_usd"] + pnl_usd, 2)
        self.account["used_margin"] = max(0, self.account["used_margin"] - position["margin_usd"])
        self.account["available_usd"] = self.account["balance_usd"] - self.account["used_margin"]
        self.account["total_pnl_usd"] = round(self.account.get("total_pnl_usd", 0) + pnl_usd, 2)
        self.account["closed_trades"] = self.account.get("closed_trades", 0) + 1

        if pnl_usd >= 0:
            self.account["win_count"] = self.account.get("win_count", 0) + 1
        else:
            self.account["loss_count"] = self.account.get("loss_count", 0) + 1

        total = self.account["win_count"] + self.account["loss_count"]
        self.account["win_rate"] = round(self.account["win_count"] / total * 100, 1) if total > 0 else 0

        closed_pos = {
            **position,
            "exit_price": exit_price,
            "pnl_usd": round(pnl_usd, 2),
            "closed_at": datetime.utcnow().isoformat(),
            "status": "closed",
            "result": "win" if pnl_usd >= 0 else "loss",
        }
        self.closed_positions.insert(0, closed_pos)
        self.open_positions.pop(pos_index)

        self.account["open_trades"] = len(self.open_positions)
        self.account["positions"] = len(self.open_positions)

        # Save to DB - ensure status is updated
        try:
            await async_save_trade(closed_pos)
        except Exception as e:
            print(f"[ERROR] Failed to save closed trade: {e}")
        
        await async_save_account(self.account)

        return {"status": "closed", "position": closed_pos}

    def update_prices(self, data_provider) -> List[Dict[str, Any]]:
        """Sync wrapper for price update."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(self._async_update_prices(), loop)
                return future.result(timeout=30)
            else:
                return loop.run_until_complete(self._async_update_prices())
        except Exception as e:
            print(f"Error updating prices: {e}")
            return []

    async def _async_update_prices(self) -> List[Dict[str, Any]]:
        """Async price update with auto-close - uses quotes for real-time prices."""
        print(f"[PRICE-UPDATE] Updating prices for {len(self.open_positions)} positions")
        auto_closed = []
        to_close = []

        for pos in self.open_positions:
            symbol = pos["symbol"]

            # Use quote API for real-time prices (not candles which may be stale)
            price = None
            try:
                quote = await self._data_provider.get_quote(symbol)
                if quote and "price" in quote:
                    price = quote["price"]
                    print(f"[PRICE-UPDATE] {symbol}: got quote price = {price}")
            except Exception as e:
                print(f"[PRICE-UPDATE] Error getting quote for {symbol}: {e}")

            # Fallback to candles if quote unavailable
            if price is None:
                try:
                    candles = await self._data_provider.get_candles(symbol, "60", 1)
                    if candles and len(candles) > 0:
                        price = candles[-1]["close"]
                except Exception as e:
                    print(f"[PRICE-UPDATE] Error getting candles for {symbol}: {e}")

            if price is None:
                print(f"[PRICE-UPDATE] Could not get price for {symbol}")
                continue

            pos_leverage = pos.get("leverage", 1)
            if pos["direction"] == "buy":
                pnl = (price - pos["entry_price"]) * pos["size"] * pos_leverage
            else:
                pnl = (pos["entry_price"] - price) * pos["size"] * pos_leverage

            pos["current_price"] = price
            pos["unrealized_pnl_usd"] = round(pnl, 2)

            # Dynamic TP adjustment based on HTF RSI
            try:
                from database import get_db
                db = get_db()
                htf_rsi_enabled = db.get_setting("HTF_RSI_DYNAMIC_TP", 0)
                if htf_rsi_enabled and htf_rsi_enabled > 0:
                    # Get HTF candles (e.g., 30 min)
                    htf_res = str(int(htf_rsi_enabled))
                    htf_candles = list(db.candles.find(
                        {"symbol": symbol, "resolution": htf_res}
                    ).sort("timestamp", -1).limit(20))
                    
                    if htf_candles and len(htf_candles) >= 14:
                        closes = [c.get("close", 0) for c in htf_candles[:14]]
                        if closes and all(c > 0 for c in closes):
                            gains = []
                            losses = []
                            for k in range(1, len(closes)):
                                diff = closes[k] - closes[k-1]
                                if diff > 0:
                                    gains.append(diff)
                                else:
                                    losses.append(abs(diff))
                            avg_gain = sum(gains) / 14 if gains else 0
                            avg_loss = sum(losses) / 14 if losses else 0
                            rs = avg_gain / avg_loss if avg_loss > 0 else 100
                            rsi = 100 - (100 / (1 + rs))
                            
                            original_tp = pos.get("take_profit")
                            entry = pos["entry_price"]
                            direction = pos["direction"]
                            
                            # Adjust TP based on HTF RSI
                            new_tp = None
                            if direction == "buy" and rsi > 65:
                                # Overbought - reduce TP to protect profits
                                new_tp = entry * 1.03  # 3% instead of original
                            elif direction == "buy" and rsi < 40:
                                # Oversold - give more room
                                new_tp = entry * 1.07  # 7% instead of original
                            elif direction == "sell" and rsi < 35:
                                new_tp = entry * 0.97
                            elif direction == "sell" and rsi > 60:
                                new_tp = entry * 0.93
                            
                            if new_tp and new_tp != original_tp:
                                pos["take_profit"] = new_tp
                                print(f"[DYNAMIC TP] {symbol} {direction} RSI={rsi:.0f} TP: {original_tp} -> {new_tp}")
            except Exception as e:
                pass  # Continue on error

            # Trailing stop logic
            if pos.get("trailing_enabled", False) and pos["unrealized_pnl_usd"] > 0:
                entry = pos["entry_price"]
                dir_ = pos["direction"]
                curr_sl = pos["stop_loss"]
                be_sl = entry
                if (dir_ == "buy" and be_sl > curr_sl) or (dir_ == "sell" and be_sl < curr_sl):
                    pos["stop_loss"] = be_sl

            # === TREND REVERSAL EARLY EXIT ===
            # Check if trend has reversed - close position if RSI/MACD shows opposite signal
            try:
                trend_exit_enabled = db.get_setting("TREND_REVERSAL_EXIT", 0)
                if trend_exit_enabled and pos.get("unrealized_pnl_usd", 0) > 0:  # Only close if in profit
                    # Get short-term candles for trend detection
                    st_candles = await self._data_provider.get_candles(symbol, "15", 30)
                    if st_candles and len(st_candles) >= 20:
                        closes = [c["close"] for c in st_candles[-20:]]
                        
                        # Calculate RSI
                        gains, losses = [], []
                        for i in range(1, len(closes)):
                            diff = closes[i] - closes[i-1]
                            if diff > 0: gains.append(diff)
                            else: losses.append(abs(diff))
                        avg_gain = sum(gains) / 14 if gains else 0
                        avg_loss = sum(losses) / 14 if losses else 0
                        rsi = 100 - (100 / (1 + avg_gain/avg_loss)) if avg_loss > 0 else 50
                        
                        # Check for reversal
                        entry = pos["entry_price"]
                        direction = pos["direction"]
                        reversal = False
                        
                        if direction == "buy" and rsi > 70:  # Overbought - trend may reverse down
                            reversal = True
                            reason = f"RSI={rsi:.0f} overbought"
                        elif direction == "sell" and rsi < 30:  # Oversold - trend may reverse up
                            reversal = True
                            reason = f"RSI={rsi:.0f} oversold"
                        
                        if reversal:
                            # Only close if we have some profit (>0.5%)
                            profit_pct = (price - entry) / entry * 100 if direction == "buy" else (entry - price) / entry * 100
                            if profit_pct > 0.5:
                                print(f"[TREND EXIT] {symbol} {direction} {reason} profit={profit_pct:.1f}% - closing early")
                                to_close.append((pos["id"], price, "TREND"))
            except Exception as e:
                pass  # Continue on error

            tp = pos.get("take_profit")
            sl = pos.get("stop_loss")

            # Validate SL/TP are set correctly for direction (sanity check)
            entry = pos["entry_price"]
            if pos["direction"] == "buy":
                # For BUY: TP should be > entry, SL should be < entry
                if tp and tp <= entry:
                    print(f"[WARN] BUY position {pos['id']} has TP ({tp}) <= entry ({entry}), fixing...")
                    tp = entry + abs(tp - entry)  # Mirror above entry
                if sl and sl >= entry:
                    print(f"[WARN] BUY position {pos['id']} has SL ({sl}) >= entry ({entry}), fixing...")
                    sl = entry - abs(sl - entry)  # Mirror below entry

                if tp and price >= tp:
                    to_close.append((pos["id"], price, "TP"))  # Use actual market price
                elif sl and price <= sl:
                    to_close.append((pos["id"], price, "SL"))  # Use actual market price
            else:
                # For SELL: TP should be < entry, SL should be > entry
                if tp and tp >= entry:
                    print(f"[WARN] SELL position {pos['id']} has TP ({tp}) >= entry ({entry}), fixing...")
                    tp = entry - abs(tp - entry)  # Mirror below entry
                if sl and sl <= entry:
                    print(f"[WARN] SELL position {pos['id']} has SL ({sl}) <= entry ({entry}), fixing...")
                    sl = entry + abs(sl - entry)  # Mirror above entry

                if tp and price <= tp:
                    to_close.append((pos["id"], price, "TP"))  # Use actual market price
                elif sl and price >= sl:
                    to_close.append((pos["id"], price, "SL"))  # Use actual market price

        for pos_id, exit_price, reason in to_close:
            # Use actual market price at trigger time, not TP/SL level
            result = await self._async_close_position(pos_id, exit_price=exit_price)
            if "error" not in result:
                result["exit_reason"] = reason
                auto_closed.append(result)

        # Recalculate unrealized
        for pos in self.open_positions:
            symbol = pos["symbol"]
            # Try candles first for price consistency
            price = None
            try:
                candles = await self._data_provider.get_candles(symbol, "60", 3)
                if candles and len(candles) > 0:
                    price = candles[-1]["close"]
            except Exception:
                pass

            # Fallback to quote
            if price is None:
                quote = await self._data_provider.get_quote(symbol)
                if quote:
                    price = quote["price"]
                else:
                    continue
                pos_leverage = pos.get("leverage", 1)
                if pos["direction"] == "buy":
                    pnl = (price - pos["entry_price"]) * pos["size"] * pos_leverage
                else:
                    pnl = (pos["entry_price"] - price) * pos["size"] * pos_leverage
                pos["current_price"] = price
                pos["unrealized_pnl_usd"] = round(pnl, 2)

        unrealized_usd = sum(p.get("unrealized_pnl_usd", 0) for p in self.open_positions)
        self.account["equity_usd"] = round(self.account["balance_usd"] + unrealized_usd, 2)
        self.account["open_trades"] = len(self.open_positions)
        self.account["positions"] = len(self.open_positions)

        return auto_closed

    def reload_from_db(self):
        """Reload positions from DB - call after external DB changes."""
        self.open_positions = db.load_open_positions()
        self.closed_positions = db.load_closed_positions()
        self.account = db.load_account()

    def reset(self) -> Dict[str, Any]:
        """Reset account."""
        self.open_positions.clear()
        self.closed_positions.clear()
        self.account.update(
            {
                "balance_usd": INITIAL_BALANCE_USD,
                "equity_usd": INITIAL_BALANCE_USD,
                "positions": 0,
                "open_trades": 0,
                "closed_trades": 0,
                "total_pnl_usd": 0.0,
                "win_count": 0,
                "loss_count": 0,
                "win_rate": 0.0,
                "used_margin": 0.0,
                "available_usd": INITIAL_BALANCE_USD,
            }
        )
        db.delete_all_trades()
        db.save_account(self.account)
        return {"status": "reset", "account": self.account}


# Legacy SimulatedDataProvider for compatibility
class SimulatedDataProvider(AsyncSimulatedDataProvider):
    """Legacy sync wrapper."""

    pass


# Legacy SimulatedBroker for compatibility
class SimulatedBroker(AsyncSimulatedBroker):
    """Legacy sync wrapper."""

    pass
