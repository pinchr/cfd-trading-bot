"""Trading engine - extracted from main.py"""
import asyncio
from typing import Dict, List, Optional
from datetime import datetime
import database as db
from timeframes import TimeFrame
from database import async_save_account
# Import Signal and SignalDirection from models
from app.logging import log_event
from models import Signal, SignalDirection
from services.state import broker, data_provider, open_positions, INSTRUMENTS, AUTO_TRADE_INTERVAL_SEC, AUTO_TRADE_ENABLED, INITIAL_BALANCE_USD
from indicators import TechnicalIndicators
from database import async_save_signal_cache_db, async_sync_account_from_closed_trades
from alpha_vantage_news import get_client as get_news_client
# Import async_timed decorator
from utils.decorators import async_timed
from strategies import get_strategy
# Lazy imports used inside functions to avoid circular dependency
# (imported from main.py at function call time)
from services.market_data import get_cached_candles


async def auto_trade_loop():
    """
    Background loop that runs autonomously:
    1. Updates prices & checks TP/SL on open positions (auto-closes hits)
    2. Generates fresh signals for all instruments
    3. Opens trades automatically when signal is strong enough
    4. Persists account state to DB
    """
    # Lazy imports to avoid circular dependency
    from services.state import broker
    
    from services.circuit_breaker import check_circuit_breaker
    from services.market_hours import is_market_open, get_market_hours
    from services.signal_generator import calculate_position_size
    account = broker.get_account()
    closed_positions = broker.get_closed_positions()
    # Wait a few seconds for startup to finish
    await asyncio.sleep(5)
    log_event("[AUTO-TRADE] Background trading loop started", "event")

    iteration_count = 0
    while True:
        iteration_count += 1
        try:
            print(f"[DEBUG AUTO-TRADE] Loop iteration #{iteration_count} at {datetime.utcnow().isoformat()}")
            if not AUTO_TRADE_ENABLED:
                await asyncio.sleep(AUTO_TRADE_INTERVAL_SEC)
                continue

            # ── Step 1: Update prices & auto-close TP/SL ──
            auto_closed = await broker._async_update_prices()
            if auto_closed:
                for closed in auto_closed:
                    pos = closed.get("position", {})
                    reason = closed.get("exit_reason", "TP/SL")
                    pnl = pos.get("pnl_usd", 0)
                    sym = pos.get("symbol", "?")
                    log_event(
                        f"[AUTO-CLOSE] {sym} {pos.get('direction', '').upper()} hit {reason} "
                        f"| P&L: {'+'if pnl>=0 else ''}{pnl:.2f} USD",
                        "success" if pnl >= 0 else "warning",
                    )
                await async_save_account(account)

            # ── Step 2: Generate fresh signals ──
            signals = await generate_signals()

            # Update signals cache for TP/SL reference
            signals_cache = {s.symbol: s for s in signals}

            # ── Step 3: Auto-execute trades on strong signals ──
            can_trade, reason = check_circuit_breaker()
            # Get risk adjustments from circuit breaker
            size_multiplier = account.get("_risk_multiplier", 1.0)
            min_score_boost = account.get("_min_score_boost", 0.0)

            if can_trade:
                # ── Step 2.5: Dynamic Positions - close weak profitable positions ──
                current_signals = {s.symbol: s.score for s in signals if s.direction not in (SignalDirection.NEUTRAL,)}
                positions_to_close = broker.check_dynamic_exit(current_signals)
                if positions_to_close:
                    log_event(f"[DYNAMIC-EXIT] Checking {len(positions_to_close)} positions for exit...", "info")
                    for pos_id in positions_to_close:
                        pos = next((p for p in open_positions if p["id"] == pos_id), None)
                        if pos:
                            try:
                                quote = await data_provider.get_quote(pos["symbol"])
                                exit_price = quote.get("price") if quote else None
                            except:
                                exit_price = None
                            result = await broker.close_position(pos_id, exit_price=exit_price)
                            if "error" not in result:
                                pnl = result.get("position", {}).get("pnl_usd", 0)
                                log_event(f"[DYNAMIC-CLOSE] {pos['symbol']} | P&L: ${pnl:.2f} | Signal decayed", "info")
                            else:
                                log_event(f"[DYNAMIC-CLOSE] Failed: {result['error']}", "warning")
                    await async_save_account(account)

                for signal in signals:
                    if signal.direction in (SignalDirection.NEUTRAL,):
                        continue

                    sym = signal.symbol
                    info = INSTRUMENTS.get(sym, {})
                    min_score = info.get("min_score", 0.15) + min_score_boost

                    if abs(signal.score) < min_score:
                        continue

                    if signal.direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY):
                        direction = "buy"
                    elif signal.direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL):
                        direction = "sell"
                    else:
                        continue

                    already_open = any(p["symbol"] == sym and p["direction"] == direction for p in open_positions)
                    if already_open:
                        continue

                    trade_enabled = db.get_setting(f"TRADE_ENABLED_{sym}", 1)
                    if not trade_enabled:
                        log_event(f"[AUTO-TRADE] Skipping {sym} - trading disabled", "info")
                        continue

                    if not is_market_open(sym):
                        log_event(f"[AUTO-TRADE] Skipping {sym} - market closed ({get_market_hours(sym)})", "info")
                        continue

                    max_positions = db.get_setting("MAX_OPEN_POSITIONS", 3)
                    if len(open_positions) >= max_positions:
                        log_event(f"[AUTO-TRADE] Skipping {sym} - max {max_positions} positions reached", "info")
                        continue

                    quote = await data_provider.get_quote(sym)
                    if not quote:
                        log_event(f"[AUTO-TRADE] Skipping {sym} - cannot get current price", "warning")
                        continue

                    entry_price = quote["price"]

                    # Recalculate TP/SL from fresh ATR
                    try:
                        
                        fresh_candles = await get_cached_candles(sym, "60", 50, data_provider)
                        if fresh_candles and len(fresh_candles) >= 20:
                            ind = TechnicalIndicators.calculate_all(fresh_candles, period=14)
                            atr = ind.get("atr_14", entry_price * 0.01)
                        else:
                            atr = entry_price * 0.01
                    except Exception:
                        atr = entry_price * 0.01

                    # Get strategy config for TP/SL
                    strategy_id = get_symbol_strategy(sym)
                    strategy_json_id = strategy_id.replace("JSON:", "") if strategy_id else None
                    strategy_config_for_tp = {}
                    if strategy_json_id:
                        from strategy.strategy_manager import get_strategy_manager
                        manager = get_strategy_manager()
                        if strategy_json_id in manager.strategies:
                            strategy_config_for_tp = manager.strategies[strategy_json_id].config
                    
                    take_profit, stop_loss = get_adaptive_tp_sl(
                        strategy_config=strategy_config_for_tp,
                        candles=fresh_candles,
                        entry_price=entry_price,
                        direction=direction
                    )

                    # Calculate dynamic position size based on signal score, confidence, open positions, volatility
                    open_pos_count = len(broker.get_open_positions())
                    
                    # Get volatility from candles
                    volatility = 0.0
                    if fresh_candles and len(fresh_candles) >= 20:
                        try:
                            from strategy.technical import TechnicalIndicators
                            ind = TechnicalIndicators.calculate_all(fresh_candles, period=14)
                            atr = ind.get('atr_14', 0)
                            volatility = (atr / entry_price) * 100 if entry_price > 0 else 0
                        except:
                            pass
                    
                    # Get strategy config for position sizing
                    strategy_id = get_symbol_strategy(sym)
                    strategy_json_id = strategy_id.replace("JSON:", "") if strategy_id else None
                    strategy_config = {}
                    if strategy_json_id:
                        from strategy.strategy_manager import get_strategy_manager
                        manager = get_strategy_manager()
                        if strategy_json_id in manager.strategies:
                            strategy_config = manager.strategies[strategy_json_id].config
                    
                    account = broker.get_account()
                    balance = account.get('balance_usd', 3000)
                    
                    size = calculate_dynamic_position_size(
                        strategy_config=strategy_config,
                        account_balance=balance,
                        entry_price=entry_price,
                        stop_loss_price=stop_loss,
                        signal_score=signal.score,
                        signal_confidence=signal.confidence,
                        open_positions_count=open_pos_count,
                        volatility=volatility
                    ) * size_multiplier

                    result = await broker.open_position(
                        symbol=sym,
                        direction=direction,
                        size=size,
                        take_profit=take_profit,
                        stop_loss=stop_loss,
                        entry_price=entry_price,
                        signal_score=signal.score,
                    )
                    if "error" not in result:
                        log_event(
                            f"[AUTO-TRADE] Opened {direction.upper()} {sym} @ {entry_price:.2f} "
                            f"| Score: {signal.score:.3f} | SL: {stop_loss:.2f} TP: {take_profit:.2f}",
                            "success",
                        )
                    else:
                        log_event(f"[AUTO-TRADE] Failed to open {sym}: {result['error']}", "warning")
            else:
                log_event(f"[AUTO-TRADE] Skipping: {reason}", "info")

            # ── Step 4: Persist state ──
            await async_save_account(account)
            
            # Get signal history cache
            from main import signal_history_cache
            await async_save_signal_cache_db(signal_history_cache)

            log_event(
                f"[AUTO-TRADE] Scan complete | Balance: ${account['balance_usd']:.2f} USD "
                f"| Open: {len(open_positions)} | Closed: {len(closed_positions)}",
                "info",
            )

        except Exception as e:
            import traceback
            log_event(f"[AUTO-TRADE] Error in trading loop: {str(e)}", "error")
            log_event(f"[AUTO-TRADE] Traceback: {traceback.format_exc()}", "error")

        # Sleep in chunks to avoid event loop issues
        sleep_cycles = AUTO_TRADE_INTERVAL_SEC // 60
        remaining = AUTO_TRADE_INTERVAL_SEC % 60
        
        try:
            for i in range(sleep_cycles):
                await asyncio.sleep(60)
            if remaining > 0:
                await asyncio.sleep(remaining)
        except Exception as e:
            log_event(f"[AUTO-TRADE] Error in sleep: {str(e)}", "error")
            await asyncio.sleep(30)


async def execute_trade(symbol: str, direction: str, volume: float, signal_score: float = 0.0, take_profit: float = None, stop_loss: float = None) -> Dict:
    """Execute a trade - wrapper around broker.open_position"""
    from main import broker
    result = await broker.open_position(
        symbol=symbol,
        direction=direction,
        size=volume,
        signal_score=signal_score,
        take_profit=take_profit,
        stop_loss=stop_loss,
    )
    return result


def check_circuit_breaker() -> bool:
    """Check if trading should be allowed - wrapper"""
    from services.circuit_breaker import check_circuit_breaker as _cb
    allowed, _ = _cb()
    return allowed


async def _analyze_single_symbol(symbol: str, info: dict, news_client_instance) -> Signal:
    """Analyze a single symbol - runs in parallel for all symbols."""
    # Lazy imports to avoid circular dependency
    from services.state import get_live_price_cache as _price_cache, get_symbol_strategy, broker
    from services.strategy_manager import get_strategy_manager, analyze_with_new_strategy
    import asyncio
    _api_semaphore = asyncio.Semaphore(3)
    from services.market_data import get_cached_quote as _get_cached_quote, get_cached_candles as _get_cached_candles
    
    timeframe = "5"
    account = broker.get_account()
    
    try:
        quote = _get_cached_quote(symbol)

        last_known_price = 0.0
        price_cache = _price_cache()
        if symbol in price_cache:
            last_known_price = price_cache[symbol].get('price', 0)

        if not quote:
            # Return neutral signal with last known price if available
            return Signal(
                symbol=symbol,
                direction=SignalDirection.NEUTRAL,
                score=0.0,
                confidence=0.0,
                technical_score=0.0,
                price_action_score=0.0,
                news_score=0.0,
                components=[],
                current_price=last_known_price,
                time_horizon=timeframe,
                entry_point=last_known_price,
                take_profit=0.0,
                stop_loss=0.0,
                risk_reward_ratio=0.0,
            )

        current_price = quote["price"]

        # Get timeframe from selected strategy (convert to db_resolution for compatibility)
        selected_strategy = get_symbol_strategy(symbol)
        
        # Use StrategyManager from JSON (supports timeframe)
        manager = get_strategy_manager()
        strategy_obj = manager.strategies.get(selected_strategy)
        if not strategy_obj:
            strategy_obj = manager.strategies.get('xau_v3_exp')
        
        # Handle both string and TimeFrame enum
        tf_value = strategy_obj.timeframe if strategy_obj and hasattr(strategy_obj, 'timeframe') else "5m"
        if hasattr(tf_value, 'value'):
            tf_value = tf_value.value
        
        # Convert to db_resolution (e.g., "5m" -> "5")
        try:
            tf_enum = TimeFrame(tf_value)
            timeframe = tf_enum.db_resolution
        except ValueError:
            timeframe = "5"  # fallback
        
        # Use cached candles with strategy's timeframe
        async with _api_semaphore:
            candles = await asyncio.wait_for(_get_cached_candles(symbol, timeframe, 100, data_provider), timeout=10.0)
        if not candles or len(candles) < 20:
            return Signal(
                symbol=symbol,
                direction=SignalDirection.NEUTRAL,
                score=0.0,
                confidence=0.0,
                technical_score=0.0,
                price_action_score=0.0,
                news_score=0.0,
                components=[],
                current_price=current_price,
                time_horizon=timeframe,
                entry_point=current_price,
                take_profit=0.0,
                stop_loss=0.0,
                risk_reward_ratio=0.0,
            )

        indicators = TechnicalIndicators.calculate_all(candles, period=14)
        if not indicators:
            return Signal(
                symbol=symbol,
                direction=SignalDirection.NEUTRAL,
                score=0.0,
                confidence=0.0,
                technical_score=0.0,
                price_action_score=0.0,
                news_score=0.0,
                components=[],
                current_price=current_price,
                time_horizon=timeframe,
                entry_point=current_price,
                take_profit=0.0,
                stop_loss=0.0,
                risk_reward_ratio=0.0,
            )

        # Filter indicators based on per-symbol settings
        enabled_key = f"INDICATORS_{symbol}"
        enabled_indicators = db.get_setting(enabled_key)
        if enabled_indicators:
            # Map indicator names to their keys in the indicators dict
            indicator_map = {
                "RSI": ["rsi_14"],
                "MACD": ["macd", "macd_signal", "macd_hist"],
                "BB": ["bb_upper", "bb_lower", "bb_middle"],
                "SMA": ["sma_20", "sma_50", "sma_200"],
                "ADX": ["adx"],
                "STOCH": ["stoch_k", "stoch_d"],
                "MOMENTUM": ["momentum"],
                "WILLIAMS_R": ["williams_r"],
            }
            # Filter indicators dict to only include enabled ones
            filtered = {"_closes": indicators.get("_closes", [])}
            for ind_name in enabled_indicators:
                keys = indicator_map.get(ind_name, [])
                for key in keys:
                    if key in indicators:
                        filtered[key] = indicators[key]
            indicators = filtered

        indicators["_closes"] = [c["close"] for c in candles]

        # ── Multi-timeframe: fetch daily candles for higher-TF trend ──
        htf_bias = 0.0
        try:
            async with _api_semaphore:
                htf_candles = await asyncio.wait_for(_get_cached_candles(symbol, "D", 60, data_provider), timeout=10.0)
            if htf_candles and len(htf_candles) >= 20:
                htf_ind = TechnicalIndicators.calculate_all(htf_candles, period=14)
                if htf_ind:
                    htf_sma20 = htf_ind.get("sma_20")
                    htf_sma50 = htf_ind.get("sma_50")
                    htf_adx = htf_ind.get("adx")
                    htf_price = htf_candles[-1]["close"]
                    if htf_sma20 and htf_sma50 and htf_sma50 > 0:
                        sma_diff = ((htf_sma20 - htf_sma50) / htf_sma50) * 100
                        htf_bias = max(-1, min(1, sma_diff / 3))
                    if htf_adx and htf_adx["adx"] > 30 and abs(htf_bias) > 0.1:
                        htf_bias *= 1.3
                        htf_bias = max(-1, min(1, htf_bias))
        except Exception:
            pass  # MTF is optional

        # ── VIX Filter (v2) ──
        # Get instrument-specific volatility index
        vix_data = None
        try:
            from historical_data import get_volatility_index

            vix_data = get_volatility_index(symbol)
            if vix_data:
                indicators["vix"] = vix_data
                print(
                    f"[VIX] {symbol}: {vix_data['value']} ({vix_data['name']}, change: {vix_data['change_pct']:+.1f}%)"
                )
            else:
                # Fallback to standard VIX
                vix_data = get_volatility_index("SPX")
                if vix_data:
                    indicators["vix"] = vix_data
        except Exception as e:
            print(f"[VIX] Could not fetch VIX for {symbol}: {e}")

        # ── Volatility filter ──
        # NOTE: Volatility check now handled by Strategy's filter config
        # The strategy.json defines volatility filter per-strategy
        atr = indicators.get("atr_14", current_price * 0.01)
        atr_pct = (atr / current_price) * 100 if current_price > 0 else 0

        # ── News sentiment (disabled to speed up - optional feature) ──
        news_score = 0.0
        # try:
        #     async with _api_semaphore:
        #         news = await asyncio.wait_for(
        #             news_client_instance.get_news(symbol, 5),
        #             timeout=1.0  # Quick timeout - don't wait for news
        #         )
        #     if news and len(news) > 0:
        #         sentiments = [article.get('sentiment', 0) for article in news]
        #         news_score = sum(sentiments) / len(sentiments) if sentiments else 0
        # except Exception:
        #     pass  # News is optional

        # ── Get selected strategy from DB ──
        selected_strategy = get_symbol_strategy(symbol)
        
        # ── Try JSON-based strategy (if selected or default) ──
        # If user selected a JSON strategy, use that one. Otherwise use any available JSON strategy for this symbol
        new_result = analyze_with_new_strategy(
            symbol, 
            candles, 
            current_price, 
            requested_strategy=selected_strategy if selected_strategy.startswith("JSON:") else None,
            atr_percent=atr_pct,
            vix_value=vix_data.get('value') if vix_data else None
        )
        
        if new_result:
            print(f"[STRATEGY] Using NEW JSON strategy for {symbol}: {new_result.get('strategy_id')}")
            # Clamp scores to valid range [-1, 1]
            json_score = max(-1.0, min(1.0, new_result["score"]))
            json_technical = max(-1.0, min(1.0, new_result["technical_score"]))
            
            # Filter out weak signals - require minimum score threshold from strategy config
            min_signal_score = new_result.get("confidence", 0.5)  # Use confidence as min threshold
            if abs(json_score) < min_signal_score:
                print(f"[SIGNAL] {symbol}: Score {json_score:.3f} below threshold {min_signal_score}, skipping")
                return Signal(
                    symbol=symbol,
                    direction=SignalDirection.NEUTRAL,
                    score=0.0,
                    confidence=0.0,
                    technical_score=0.0,
                    price_action_score=0.0,
                    news_score=0.0,
                    components=[],
                    current_price=current_price,
                    time_horizon=timeframe,
                    entry_point=current_price,
                    take_profit=0.0,
                    stop_loss=0.0,
                    risk_reward_ratio=0.0,
                )
            
            return Signal(
                symbol=symbol,
                direction=SignalDirection.BUY if new_result["direction"] == "long" else SignalDirection.SELL,
                score=json_score,
                confidence=new_result["confidence"],
                technical_score=json_technical,
                price_action_score=0.0,
                news_score=0.0,
                components=new_result["components"],
                current_price=current_price,
                time_horizon=timeframe,
                entry_point=current_price,
                take_profit=new_result.get("exits", {}).get("tp_price", 0) or 0,
                stop_loss=new_result.get("exits", {}).get("sl_price", 0) or 0,
                risk_reward_ratio=new_result.get("risk_reward_ratio") or 0,
            )

        # ── Fallback: OLD strategy (DEPRECATED - see strategies.py) ──
        # ⚠️ DEPRECATED: Old strategy code - migrate to JSON-based strategies
        strategy_id = get_symbol_strategy(symbol)
        strategy = get_strategy(strategy_id)
        indicators["_closes"] = [c["close"] for c in candles]

        result = strategy.score(
            candles=candles,
            indicators=indicators,
            symbol=symbol,
            instrument_info=info,
            current_price=current_price,
            htf_bias=htf_bias,
            news_score=news_score,
        )

        # Clamp scores to valid range [-1, 1] - safety guard
        safe_score = max(-1.0, min(1.0, result["score"]))
        safe_technical = max(-1.0, min(1.0, result["technical_score"]))
        
        signal = Signal(
            symbol=symbol,
            direction=result["direction"],
            score=safe_score,
            confidence=result["confidence"],
            technical_score=safe_technical,
            price_action_score=0.0,
            news_score=news_score,
            components=result["components"],
            current_price=current_price,
            time_horizon=timeframe,
            entry_point=current_price,
            take_profit=result["take_profit"],
            stop_loss=result["stop_loss"],
            risk_reward_ratio=result["risk_reward_ratio"],
        )

        return signal

    except Exception as e:
        raise e
        log_event(f"Error analyzing {symbol}: {e}", "error")
        return Signal(
            symbol=symbol,
            direction=SignalDirection.NEUTRAL,
            score=0.0,
            confidence=0.0,
            technical_score=0.0,
            price_action_score=0.0,
            news_score=0.0,
            components=[],
            current_price=0.0,
            time_horizon=timeframe,
            entry_point=0.0,
            take_profit=0.0,
            stop_loss=0.0,
            risk_reward_ratio=0.0,
        )

@async_timed("generate_signals")
async def generate_signals() -> List[Signal]:
    """Generate trading signals for all instruments using regime-adaptive scoring - PARALLEL"""
    account = broker.get_account()
    now = datetime.utcnow().isoformat()
    account["last_scan"] = now
    print(f"[DEBUG] generate_signals set last_scan to {now}")

    # Track peak equity (balance + unrealized P&L) for drawdown calculation
    current_equity = account.get("equity_usd", account.get("balance_usd", INITIAL_BALANCE_USD))
    if current_equity > account.get("peak_equity_usd", INITIAL_BALANCE_USD):
        account["peak_equity_usd"] = current_equity
    # Keep peak_balance_usd for backward compatibility
    if account["balance_usd"] > account.get("peak_balance_usd", INITIAL_BALANCE_USD):
        account["peak_balance_usd"] = account["balance_usd"]

    news_client_instance = get_news_client()

    # Run all symbol analysis in PARALLEL
    tasks = [_analyze_single_symbol(symbol, info, news_client_instance) for symbol, info in INSTRUMENTS.items()]
    signals = await asyncio.gather(*tasks)

    # Log results
    # Log results
    for signal in signals:
        if signal.direction != SignalDirection.NEUTRAL:
            log_event(
                f"[SIGNAL] {signal.symbol}: {signal.direction.value} | Score: {signal.score:.2f} | Conf: {signal.confidence:.0%} | ${signal.current_price:.2f}",
                "event",
            )

    # Update equity after signals
    await async_sync_account_from_closed_trades()

    return signals

# === Adaptive TP/SL Helper Functions ===

def calculate_adaptive_tp_sl(strategy_config: dict, candles: list, entry_price: float, direction: str) -> tuple:
    """
    Calculate TP/SL using adaptive algorithm combining:
    - Base percentage from strategy
    - ATR-based levels
    - Support/Resistance levels
    """
    from strategy.support_resistance import calculate_optimal_tp_sl as sr_calc
    
    exits_v2 = strategy_config.get('exits_v2', {})
    
    if not exits_v2 or exits_v2.get('tp_method') != 'adaptive':
        # Fallback to simple percentage
        base_tp = exits_v2.get('base_tp_percent', 2.5) if exits_v2 else 2.5
        base_sl = exits_v2.get('base_sl_percent', 1.5) if exits_v2 else 1.5
        
        if direction == 'buy':
            return (
                entry_price * (1 + base_tp / 100),
                entry_price * (1 - base_sl / 100)
            )
        else:
            return (
                entry_price * (1 - base_tp / 100),
                entry_price * (1 + base_sl / 100)
            )
    
    # Use adaptive algorithm
    result = sr_calc(
        candles=candles,
        entry_price=entry_price,
        direction=direction,
        base_tp_percent=exits_v2.get('base_tp_percent', 2.5),
        base_sl_percent=exits_v2.get('base_sl_percent', 1.5),
        atr_multiplier=exits_v2.get('atr_multiplier', 2.0),
        min_rr_ratio=exits_v2.get('min_rr_ratio', 1.5)
    )
    
    return result['take_profit'], result['stop_loss']


# === Adaptive TP/SL Helper ===
def get_adaptive_tp_sl(strategy_config: dict, candles: list, entry_price: float, direction: str) -> tuple:
    """
    Calculate TP/SL using adaptive algorithm combining base %, ATR, and S/R levels
    """
    try:
        from strategy.support_resistance import calculate_optimal_tp_sl
        
        exits_v2 = strategy_config.get('exits_v2', {}) if strategy_config else {}
        
        if not exits_v2 or exits_v2.get('tp_method') != 'adaptive':
            # Fallback: simple ATR
            atr = entry_price * 0.015
            if direction == 'buy':
                return (entry_price + atr*2, entry_price - atr*1.5)
            else:
                return (entry_price - atr*2, entry_price + atr*1.5)
        
        result = calculate_optimal_tp_sl(
            candles=candles,
            entry_price=entry_price,
            direction=direction,
            base_tp_percent=exits_v2.get('base_tp_percent', 2.5),
            base_sl_percent=exits_v2.get('base_sl_percent', 1.5),
            atr_multiplier=exits_v2.get('atr_multiplier', 2.0),
            min_rr_ratio=exits_v2.get('min_rr_ratio', 1.5)
        )
        return result['take_profit'], result['stop_loss']
    except Exception as e:
        # Fallback
        atr = entry_price * 0.015
        if direction == 'buy':
            return (entry_price + atr*2, entry_price - atr*1.5)
        else:
            return (entry_price - atr*2, entry_price + atr*1.5)


def calculate_dynamic_position_size(
    strategy_config: dict,
    account_balance: float,
    entry_price: float,
    stop_loss_price: float,
    signal_score: float,
    signal_confidence: float,
    open_positions_count: int,
    volatility: float = 0.0
) -> float:
    """
    Calculate position size dynamically based on multiple factors:
    - Signal score (higher score = bigger position)
    - Signal confidence (higher confidence = bigger position)
    - Number of open positions (more positions = smaller size)
    - Volatility (higher volatility = smaller size)
    """
    from services.signal_generator import calculate_position_size
    
    sizing_v2 = strategy_config.get('position_sizing_v2', {})
    
    if not sizing_v2 or sizing_v2.get('method') != 'adaptive':
        # Fallback to simple calculation
        return calculate_position_size("XAU", entry_price, stop_loss_price)
    
    # Get base risk
    base_risk_percent = sizing_v2.get('base_risk_percent', 1.5)
    max_leverage = sizing_v2.get('max_leverage', 10)
    min_leverage = sizing_v2.get('min_leverage', 5)
    modifiers = sizing_v2.get('modifiers', {})
    
    # Modifier 1: Signal Score (0-1 scale)
    # Higher score = larger position
    score_modifier = abs(signal_score)  # Use absolute value (both buy/sell)
    
    # Modifier 2: Confidence (0-1 scale)
    confidence_modifier = signal_confidence
    
    # Modifier 3: Open positions
    pos_modifiers = modifiers.get('by_open_positions', {})
    if open_positions_count == 0:
        pos_mod = pos_modifiers.get('0', 1.0)
    elif open_positions_count == 1:
        pos_mod = pos_modifiers.get('1', 0.8)
    elif open_positions_count == 2:
        pos_mod = pos_modifiers.get('2', 0.6)
    else:
        pos_mod = pos_modifiers.get('3+', 0.4)
    
    # Modifier 4: Volatility (ATR %)
    # Higher volatility = smaller position
    if volatility > 2.0:
        vol_mod = modifiers.get('by_volatility', {}).get('high', 0.5)
    elif volatility > 1.0:
        vol_mod = modifiers.get('by_volatility', {}).get('medium', 0.75)
    else:
        vol_mod = modifiers.get('by_volatility', {}).get('low', 1.0)
    
    # Combine all modifiers
    combined_modifier = score_modifier * confidence_modifier * pos_mod * vol_mod
    
    # Apply modifier to base risk
    adjusted_risk = base_risk_percent * combined_modifier
    
    # Ensure minimum risk (0.5%)
    adjusted_risk = max(adjusted_risk, 0.5)
    
    # Calculate position size with adjusted risk
    risk_amount = account_balance * (adjusted_risk / 100)
    risk_per_lot = abs(entry_price - stop_loss_price)
    
    if risk_per_lot > 0:
        size = risk_amount / risk_per_lot
    else:
        size = risk_amount / entry_price
    
    # Apply leverage
    leverage = max_leverage * combined_modifier
    leverage = max(min_leverage, min(max_leverage, leverage))
    
    size = size * leverage
    
    # Round to reasonable precision
    size = round(size, 4)
    
    return max(0.01, size)  # Minimum 0.01 lot
