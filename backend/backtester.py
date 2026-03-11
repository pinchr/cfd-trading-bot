"""
Backtesting engine for the CFD trading bot signal strategy.

Replays historical candle data through the same signal engine used in
production, simulates trades with TP/SL, and reports performance metrics.

Usage:
    # From the backend directory:
    python backtester.py --symbol XAU --days 365  # Fetch Yahoo Finance data
    python backtester.py --csv data/gold_2024.csv --symbol XAU
    python backtester.py --all --days 180         # All instruments

Data sources (in priority order):
    1. --csv <file>          CSV file (Yahoo Finance download format)
    2. Yahoo Finance API     Automatic when no --csv given
    3. Alpha Vantage API     Fallback if Yahoo fails
"""

import argparse
import json
import logging

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from indicators import TechnicalIndicators

# Try to import analyze_with_new_strategy for unified signal generation
try:
    from services.strategy_manager import analyze_with_new_strategy as analyze_strategy
    from services.strategy_manager import get_strategy_manager
    HAS_UNIFIED_ANALYSIS = True
except ImportError:
    HAS_UNIFIED_ANALYSIS = False
    analyze_strategy = None
    get_strategy_manager = None

# ── Signal scoring — extracted from main.py to run standalone ──


def calculate_signal_score(indicators: dict) -> Tuple[float, str]:
    """
    Regime-adaptive signal scoring (same logic as production).
    Returns (score, direction) where score is -1..+1.
    """
    scores = []
    weights = []

    # Regime detection
    adx_data = indicators.get("adx")
    adx_value = adx_data["adx"] if adx_data else 20
    is_trending = adx_value > 25

    # RSI
    rsi = indicators.get("rsi_14")
    if rsi is not None:
        if rsi < 30:
            rsi_score = (30 - rsi) / 30
        elif rsi > 70:
            rsi_score = -((rsi - 70) / 30)
        elif rsi < 45:
            rsi_score = (45 - rsi) / 45 * 0.3
        elif rsi > 55:
            rsi_score = -(rsi - 55) / 45 * 0.3
        else:
            rsi_score = 0
        scores.append(max(-1, min(1, rsi_score)))
        weights.append(0.15 if is_trending else 0.25)

    # StochRSI
    stoch = indicators.get("stoch_rsi")
    if stoch:
        k, d = stoch["k"], stoch["d"]
        if k < 20:
            stoch_score = 0.6 + (20 - k) / 50
        elif k > 80:
            stoch_score = -(0.6 + (k - 80) / 50)
        else:
            stoch_score = 0
        if k > d and k < 30:
            stoch_score = max(stoch_score, 0.5)
        elif k < d and k > 70:
            stoch_score = min(stoch_score, -0.5)
        stoch_score = max(-1, min(1, stoch_score))
        if abs(stoch_score) > 0.1:
            scores.append(stoch_score)
            weights.append(0.10)

    # MACD
    macd = indicators.get("macd")
    if macd and macd.get("histogram") is not None and macd.get("macd_line") is not None:
        atr = indicators.get("atr_14", 1) or 1
        norm_hist = macd["histogram"] / atr
        macd_score = max(-1, min(1, norm_hist * 2))
        scores.append(macd_score)
        weights.append(0.25 if is_trending else 0.15)

    # Bollinger Bands
    bb = indicators.get("bollinger_bands")
    closes = indicators.get("_closes", [])
    if bb and closes:
        current_price = closes[-1]
        bb_range = bb["upper"] - bb["lower"] if bb["upper"] != bb["lower"] else 1
        bb_position = ((current_price - bb["lower"]) / bb_range) * 2 - 1
        bb_score = max(-1, min(1, -bb_position * 0.8))
        scores.append(bb_score)
        weights.append(0.15 if is_trending else 0.25)

    # SMA Cross
    sma_20 = indicators.get("sma_20")
    sma_50 = indicators.get("sma_50")
    if sma_20 is not None and sma_50 is not None and sma_50 > 0:
        sma_diff_pct = ((sma_20 - sma_50) / sma_50) * 100
        sma_score = max(-1, min(1, sma_diff_pct / 2))
        scores.append(sma_score)
        weights.append(0.20 if is_trending else 0.10)

    # Volume
    vol = indicators.get("volume_profile")
    if vol and vol["vol_ratio"] > 1.5:
        vol_bias = max(-0.5, min(0.5, (vol["up_down_ratio"] - 1.0) * 0.3))
        scores.append(vol_bias)
        weights.append(0.10)

    # Momentum
    momentum = indicators.get("momentum_10")
    if momentum is not None:
        base = sma_20 or 1
        mom_pct = (momentum / base) * 100 if base else 0
        scores.append(max(-1, min(1, mom_pct / 2)))
        weights.append(0.05)

    # Candlestick Patterns
    cp = indicators.get("candlestick_patterns")
    if cp and cp.get("patterns") and abs(cp["net_bias"]) > 0.1:
        scores.append(max(-1, min(1, cp["net_bias"])))
        weights.append(0.15)

    # RSI Divergence (new indicator)
    divergence = indicators.get("divergence")
    if divergence and isinstance(divergence, dict):
        div_bias = divergence.get("bias", 0.0)
        div_strength = divergence.get("strength", 0.0)
        if div_bias != 0 and div_strength > 0.1:
            scores.append(max(-1, min(1, div_bias * div_strength)))
            weights.append(0.20)  # Higher weight for divergence signals

    # Composite
    if scores:
        total_w = sum(weights)
        composite = sum(s * w for s, w in zip(scores, weights)) / total_w if total_w > 0 else 0
    else:
        composite = 0

    # Agreement bonus/penalty
    if len(scores) >= 3:
        bullish = sum(1 for s in scores if s > 0.1)
        bearish = sum(1 for s in scores if s < -0.1)
        agreement = max(bullish, bearish) / len(scores)
        if agreement > 0.7:
            composite *= 1.15
        elif agreement < 0.4:
            composite *= 0.7

    score = max(-1, min(1, composite))

    # Return score and raw component scores for agreement filtering
    return score, scores


def get_direction(score: float, min_score: float = 0.15) -> str:
    """Convert score to direction string using per-instrument threshold."""
    strong_threshold = max(0.45, min_score + 0.20)
    if score > strong_threshold:
        return "STRONG_BUY"
    elif score > min_score:
        return "BUY"
    elif score < -strong_threshold:
        return "STRONG_SELL"
    elif score < -min_score:
        return "SELL"
    else:
        return "NEUTRAL"


# ── Trade simulation ──


@dataclass
class BacktestTrade:
    entry_idx: int
    entry_price: float
    entry_time: str
    direction: str  # "BUY" or "SELL"
    stop_loss: float
    take_profit: float
    score: float
    initial_sl: float = 0.0  # Original SL before trailing
    atr_at_entry: float = 0.0  # ATR at entry for trailing distance
    best_price: float = 0.0  # Best price seen (for trailing)
    trailing_active: bool = False  # Whether trailing stop is active
    exit_idx: Optional[int] = None
    exit_price: Optional[float] = None
    exit_time: Optional[str] = None
    exit_reason: Optional[str] = None  # "TP", "SL", "TRAIL", "TIMEOUT", "END"
    pnl_pct: float = 0.0


@dataclass
class BacktestResult:
    symbol: str
    period: str
    total_candles: int
    total_signals: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    neutral_skipped: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    total_return_pct: float
    max_drawdown_pct: float
    profit_factor: float
    sharpe_approx: float
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)


# Minimum candles to have before generating first signal
LOOKBACK = 60
# Max candles to hold a position before force-closing
MAX_HOLD_CANDLES = 20
# Per-instrument tuning
# min_score: higher = fewer but better trades
# min_agreement: how many indicators must agree to enter
# asset_class: "commodity" gets trend-alignment filter
INSTRUMENT_CONFIG = {
    "XAU": {"min_score": 0.30, "min_agreement": 3, "asset_class": "commodity", "leverage": 20, "trailing_stop": True},
    "XAG": {"min_score": 0.28, "min_agreement": 3, "asset_class": "commodity", "leverage": 20, "trailing_stop": True},
    "US100": {"min_score": 0.20, "min_agreement": 2, "asset_class": "equity", "leverage": 20, "trailing_stop": True},
    "BTC": {"min_score": 0.20, "min_agreement": 2, "asset_class": "crypto", "leverage": 5, "trailing_stop": True},
}


def run_backtest(
    candles: List[Dict],
    symbol: str = "XAU",
    initial_balance: float = 10000.0,
    risk_per_trade_pct: float = 2.0,
    max_concurrent: int = 1,
    verbose: bool = False,
    htf_candles: Optional[List[Dict]] = None,
    use_unified_strategy: bool = True,
    strategy_id: Optional[str] = None,
) -> BacktestResult:
    """
    Run backtest over historical candle data.

    Walks forward through candles, computing indicators on the trailing window,
    generating signals, and simulating trades with TP/SL exits.

    htf_candles: optional higher-timeframe (e.g. daily) candles for multi-TF filter.
    use_unified_strategy: if True, use analyze_with_new_strategy() for signal generation
    strategy_id: specific JSON strategy to use (e.g., "btc_v3_exp")
    """
    # Track if we're using unified strategy
    using_unified = use_unified_strategy and HAS_UNIFIED_ANALYSIS and analyze_strategy is not None
    
    # Force reload strategy manager to ensure clean state (indicators reset)
    # This ensures deterministic results between backtest runs
    if using_unified and get_strategy_manager:
        try:
            get_strategy_manager(force_reload=True)
        except Exception:
            pass  # Ignore errors - may not have the function
    
    if using_unified:
        print(f"[BACKTEST] Using unified strategy: {strategy_id or 'default'}")
    
    if len(candles) < LOOKBACK + 10:
        raise ValueError(f"Need at least {LOOKBACK + 10} candles, got {len(candles)}")

    # Pre-compute higher-timeframe (daily) trend bias if HTF candles provided
    htf_bias = 0.0
    if htf_candles and len(htf_candles) >= 50:
        htf_ind = TechnicalIndicators.calculate_all(htf_candles, period=14)
        if htf_ind:
            htf_sma20 = htf_ind.get("sma_20")
            htf_sma50 = htf_ind.get("sma_50")
            htf_adx = htf_ind.get("adx")
            if htf_sma20 and htf_sma50 and htf_sma50 > 0:
                sma_diff = ((htf_sma20 - htf_sma50) / htf_sma50) * 100
                htf_bias = max(-1, min(1, sma_diff / 3))
            if htf_adx and htf_adx["adx"] > 30 and abs(htf_bias) > 0.1:
                htf_bias *= 1.3
                htf_bias = max(-1, min(1, htf_bias))

    trades: List[BacktestTrade] = []
    open_trades: List[BacktestTrade] = []
    balance = initial_balance
    peak_balance = initial_balance
    max_drawdown = 0.0
    equity_curve = [balance]
    total_signals = 0
    neutral_skipped = 0

    for i in range(LOOKBACK, len(candles)):
        # Trailing window for indicator computation
        window = candles[i - LOOKBACK : i + 1]
        current = candles[i]
        current_price = current["close"]
        current_high = current["high"]
        current_low = current["low"]

        # Check TP/SL and trailing stop on open trades
        closed_this_bar = []
        for trade in open_trades:
            hit_tp = False
            hit_sl = False

            # Update best price for trailing stop
            if trade.direction == "BUY":
                trade.best_price = max(trade.best_price, current_high)
            else:
                trade.best_price = min(trade.best_price, current_low)

            # Trailing stop logic:
            # Phase 1: price moves 1×ATR in favor → move SL to breakeven
            # Phase 2: trail SL at 1.5×ATR behind best price
            if trade.atr_at_entry > 0:
                atr = trade.atr_at_entry
                if trade.direction == "BUY":
                    profit_distance = trade.best_price - trade.entry_price
                    if profit_distance >= atr:
                        # At least breakeven
                        new_sl = max(trade.entry_price, trade.best_price - atr * 1.5)
                        if new_sl > trade.stop_loss:
                            trade.stop_loss = round(new_sl, 2)
                            trade.trailing_active = True
                else:  # SELL
                    profit_distance = trade.entry_price - trade.best_price
                    if profit_distance >= atr:
                        new_sl = min(trade.entry_price, trade.best_price + atr * 1.5)
                        if new_sl < trade.stop_loss:
                            trade.stop_loss = round(new_sl, 2)
                            trade.trailing_active = True

            if trade.direction == "BUY":
                hit_tp = current_high >= trade.take_profit
                hit_sl = current_low <= trade.stop_loss
            else:  # SELL
                hit_tp = current_low <= trade.take_profit
                hit_sl = current_high >= trade.stop_loss

            # Timeout
            bars_held = i - trade.entry_idx
            hit_timeout = bars_held >= MAX_HOLD_CANDLES

            if hit_sl:
                trade.exit_price = trade.stop_loss
                trade.exit_reason = "TRAIL" if trade.trailing_active else "SL"
            elif hit_tp:
                trade.exit_price = trade.take_profit
                trade.exit_reason = "TP"
            elif hit_timeout:
                trade.exit_price = current_price
                trade.exit_reason = "TIMEOUT"
            else:
                continue

            trade.exit_idx = i
            trade.exit_time = current.get("timestamp", current.get("time", ""))

            # P&L % includes leverage effect
            leverage = INSTRUMENT_CONFIG.get(symbol, {}).get("leverage", 1)
            if trade.direction == "BUY":
                raw_pct = ((trade.exit_price - trade.entry_price) / trade.entry_price) * 100
            else:
                raw_pct = ((trade.entry_price - trade.exit_price) / trade.entry_price) * 100
            trade.pnl_pct = raw_pct * leverage

            # Update balance using initial SL for position sizing
            risk_amount = balance * (risk_per_trade_pct / 100)
            initial_sl = trade.initial_sl if trade.initial_sl else trade.stop_loss
            risk_per_unit = abs(trade.entry_price - initial_sl)
            if risk_per_unit > 0:
                position_value = risk_amount / (risk_per_unit * leverage) * trade.entry_price
                dollar_pnl = position_value * (raw_pct / 100) * leverage
            else:
                dollar_pnl = 0
            balance += dollar_pnl

            closed_this_bar.append(trade)

        for t in closed_this_bar:
            open_trades.remove(t)
            trades.append(t)

        equity_curve.append(balance)
        peak_balance = max(peak_balance, balance)
        drawdown = ((peak_balance - balance) / peak_balance) * 100 if peak_balance > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)

        # Generate signal if no open trades (or below max concurrent)
        if len(open_trades) >= max_concurrent:
            continue

        # Use unified strategy if requested
        using_unified_result = False  # Track if we actually got a unified result
        strategy_exists_for_symbol = False  # Track if any strategy exists for this symbol
        if using_unified:
            # Try to get signal from unified strategy
            try:
                # First, check if any strategy exists for this symbol (before calling analyze)
                # This helps us distinguish between "no strategy" vs "filters failed"
                if analyze_strategy and get_strategy_manager:
                    try:
                        mgr = get_strategy_manager()
                        if mgr:
                            # Check both enabled and disabled strategies
                            for s in mgr.strategies.values():
                                if s.symbol.upper() == symbol.upper():
                                    strategy_exists_for_symbol = True
                                    break
                            # Also check enabled strategies
                            if not strategy_exists_for_symbol:
                                for s in mgr.get_enabled_strategies():
                                    if s.symbol.upper() == symbol.upper():
                                        strategy_exists_for_symbol = True
                                        break
                    except Exception:
                        pass
                
                # Also compute indicators for filters
                ind = TechnicalIndicators.calculate_all(window, period=14)
                if not ind:
                    continue
                ind["_closes"] = [c["close"] for c in window]
                
                # Volatility filter (same as production)
                atr = ind.get("atr_14", current_price * 0.01)
                atr_pct = (atr / current_price) * 100 if current_price > 0 else 0
                if atr_pct > 3.0:
                    continue
                
                # Get signal from unified strategy
                result = analyze_strategy(
                    symbol=symbol,
                    candles=window,  # trailing window
                    current_price=current_price,
                    balance=initial_balance,
                    requested_strategy=strategy_id
                )
                
                if result and result.get('direction'):
                    # Convert to format expected by backtester
                    direction = result['direction']
                    score = result.get('score', 0)
                    direction_str = 'BUY' if direction == 'long' else 'SELL'
                    component_scores = [score]  # Simplified
                    total_signals += 1
                    using_unified_result = True  # Mark that unified strategy gave us a valid signal
                elif result is None:
                    # Strategy returned None - could be no strategy OR filters failed
                    # Only fall back if NO strategy exists for this symbol
                    # If strategy exists but returned None, it means filters failed - SKIP, don't fall back
                    if not strategy_exists_for_symbol:
                        # No strategy at all for this symbol - fall back to traditional scoring
                        if verbose:
                            print(f"[BACKTEST] No strategy found for {symbol}, falling back to traditional scoring")
                        ind = TechnicalIndicators.calculate_all(window, period=14)
                        if not ind:
                            continue
                        ind["_closes"] = [c["close"] for c in window]
                        score, component_scores = calculate_signal_score(ind)
                        total_signals += 1
                        using_unified_result = False  # Fell back to traditional
                    else:
                        # Strategy exists but filters failed or no signal - skip this bar
                        # Do NOT fall back - use the strategy's filtering
                        if verbose:
                            print(f"[BACKTEST] Strategy exists for {symbol} but no signal (filters/data), skipping bar")
                        neutral_skipped += 1
                        continue
                else:
                    # Result returned but filters failed (no direction) - skip this bar
                    # Do NOT fall back - use the strategy's filtering
                    if verbose:
                        print(f"[BACKTEST] Filters failed for {symbol}, skipping bar")
                    neutral_skipped += 1
                    continue
            except Exception as e:
                # Fall back to traditional scoring but keep unified enabled
                # (exception may be transient)
                if verbose:
                    print(f"[BACKTEST] Unified strategy error: {e}, falling back")
                # Don't disable unified - it may work on next bar
                ind = TechnicalIndicators.calculate_all(window, period=14)
                if not ind:
                    continue
                ind["_closes"] = [c["close"] for c in window]
                score, component_scores = calculate_signal_score(ind)
                total_signals += 1
                using_unified_result = False  # Fell back to traditional
        else:
            # Original logic: compute indicators and calculate score
            # Compute indicators on trailing window
            ind = TechnicalIndicators.calculate_all(window, period=14)
            if not ind:
                continue
            ind["_closes"] = [c["close"] for c in window]

            # Volatility filter (same as production)
            atr = ind.get("atr_14", current_price * 0.01)
            atr_pct = (atr / current_price) * 100 if current_price > 0 else 0
            if atr_pct > 3.0:
                continue

            score, component_scores = calculate_signal_score(ind)
            total_signals += 1

        # Blend in higher-TF bias (if available)
        if not using_unified and abs(htf_bias) > 0.1:
            score = score * 0.85 + htf_bias * 0.15
            score = max(-1, min(1, score))

        # Multi-TF alignment filter: halve score if opposing daily trend (not for unified - it has its own filters)
        if not using_unified and abs(htf_bias) > 0.3:
            if (score > 0) != (htf_bias > 0):
                score *= 0.5

        # Per-instrument threshold - use from unified result or config
        # Only use min_score=0.0 if we actually got a unified strategy result
        # If we fell back to traditional scoring, use the config threshold
        if using_unified and using_unified_result:
            # Unified strategy already applies its own thresholds
            min_score = 0.0
        else:
            # Fell back to traditional scoring - use config thresholds
            inst_config = INSTRUMENT_CONFIG.get(symbol, {})
            min_score = inst_config.get("min_score", 0.15)

        inst_config = INSTRUMENT_CONFIG.get(symbol, {})  # Always need this for filters
        direction = get_direction(score, min_score=min_score)

        if direction == "NEUTRAL":
            neutral_skipped += 1
            continue

        # Minimum indicator agreement filter (per-instrument) - skip for unified
        if not using_unified:
            bullish_c = sum(1 for s in component_scores if s > 0.1)
            bearish_c = sum(1 for s in component_scores if s < -0.1)
            min_agreement = inst_config.get("min_agreement", 2)
            if max(bullish_c, bearish_c) < min_agreement:
                neutral_skipped += 1
                continue

        # Trend-alignment filter for commodities (skip for unified - has its own filters)
        if not using_unified:
            sma_50 = ind.get("sma_50")
            asset_class = inst_config.get("asset_class", "crypto")
            if asset_class == "commodity" and sma_50:
                price_above_sma50 = current_price > sma_50
                is_buy = direction in ("BUY", "STRONG_BUY")
                if is_buy and not price_above_sma50:
                    neutral_skipped += 1
                    continue
                if not is_buy and price_above_sma50:
                    neutral_skipped += 1
                    continue

        # Determine TP/SL using ATR
        # With trailing stop: wider initial SL (3×ATR emergency) since trailing will tighten
        # Without trailing: standard 1.5×ATR SL
        adx_data = ind.get("adx")
        is_trending = adx_data and adx_data["adx"] > 25
        use_trailing = inst_config.get("trailing_stop", True)

        if use_trailing:
            # Wide emergency SL — trailing stop will manage the real exit
            sl_mult = 3.0
            tp_mult = 4.0 if is_trending else 3.5
        else:
            if is_trending:
                sl_mult, tp_mult = 1.5, 3.5
            else:
                sl_mult, tp_mult = 1.5, 3.0

        if direction in ("BUY", "STRONG_BUY"):
            stop_loss = current_price - (atr * sl_mult)
            take_profit = current_price + (atr * tp_mult)
            trade_dir = "BUY"
        else:
            stop_loss = current_price + (atr * sl_mult)
            take_profit = current_price - (atr * tp_mult)
            trade_dir = "SELL"

        trade = BacktestTrade(
            entry_idx=i,
            entry_price=current_price,
            entry_time=current.get("timestamp", current.get("time", "")),
            direction=trade_dir,
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            score=round(score, 4),
            initial_sl=round(stop_loss, 2),
            atr_at_entry=atr if use_trailing else 0.0,
            best_price=current_price,
        )
        open_trades.append(trade)

        if verbose:
            print(
                f"  [{current.get('time', i)}] {trade_dir} @ {current_price:.2f} "
                f"(score={score:.3f}, SL={stop_loss:.2f}, TP={take_profit:.2f})"
            )

    # Force-close any remaining open trades at last candle price
    last_price = candles[-1]["close"]
    leverage = INSTRUMENT_CONFIG.get(symbol, {}).get("leverage", 1)
    for trade in open_trades:
        trade.exit_idx = len(candles) - 1
        trade.exit_price = last_price
        trade.exit_time = candles[-1].get("timestamp", "")
        trade.exit_reason = "END"
        if trade.direction == "BUY":
            raw_pct = ((last_price - trade.entry_price) / trade.entry_price) * 100
        else:
            raw_pct = ((trade.entry_price - last_price) / trade.entry_price) * 100
        trade.pnl_pct = raw_pct * leverage
        trades.append(trade)

    # Compute stats
    winning = [t for t in trades if t.pnl_pct > 0]
    losing = [t for t in trades if t.pnl_pct <= 0]
    total_trades = len(trades)
    win_count = len(winning)
    loss_count = len(losing)
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

    avg_win = sum(t.pnl_pct for t in winning) / win_count if win_count > 0 else 0
    avg_loss = sum(t.pnl_pct for t in losing) / loss_count if loss_count > 0 else 0

    gross_profit = sum(t.pnl_pct for t in winning)
    gross_loss = abs(sum(t.pnl_pct for t in losing))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0

    total_return = ((balance - initial_balance) / initial_balance) * 100

    # Approximate Sharpe (annualised, assuming daily candles)
    if len(trades) > 1:
        returns = [t.pnl_pct for t in trades]
        mean_r = sum(returns) / len(returns)
        var_r = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = var_r**0.5
        sharpe = (mean_r / std_r) * (252**0.5) if std_r > 0 else 0
    else:
        sharpe = 0

    first_time = candles[0].get("timestamp", candles[0].get("time", ""))
    last_time = candles[-1].get("timestamp", candles[-1].get("time", ""))
    period = f"{first_time} -> {last_time}"

    return BacktestResult(
        symbol=symbol,
        period=period,
        total_candles=len(candles),
        total_signals=total_signals,
        total_trades=total_trades,
        winning_trades=win_count,
        losing_trades=loss_count,
        neutral_skipped=neutral_skipped,
        win_rate=round(win_rate, 1),
        avg_win_pct=round(avg_win, 2),
        avg_loss_pct=round(avg_loss, 2),
        total_return_pct=round(total_return, 2),
        max_drawdown_pct=round(max_drawdown, 2),
        profit_factor=round(profit_factor, 2),
        sharpe_approx=round(sharpe, 2),
        trades=trades,
        equity_curve=equity_curve,
    )


def print_report(result: BacktestResult):
    """Print a formatted backtest report to stdout."""
    print("\n" + "=" * 65)
    print(f"  BACKTEST REPORT — {result.symbol}")
    print("=" * 65)
    print(f"  Period:           {result.period}")
    print(f"  Total candles:    {result.total_candles}")
    print(f"  Signals generated:{result.total_signals}")
    print(f"  Neutral skipped:  {result.neutral_skipped}")
    print("-" * 65)
    print(f"  Total trades:     {result.total_trades}")
    print(f"  Winning:          {result.winning_trades}")
    print(f"  Losing:           {result.losing_trades}")
    print(f"  Win rate:         {result.win_rate:.1f}%")
    print(f"  Avg win:         +{result.avg_win_pct:.2f}%")
    print(f"  Avg loss:         {result.avg_loss_pct:.2f}%")
    print("-" * 65)
    print(f"  Total return:     {result.total_return_pct:+.2f}%")
    print(f"  Max drawdown:     {result.max_drawdown_pct:.2f}%")
    print(f"  Profit factor:    {result.profit_factor:.2f}")
    print(f"  Sharpe (approx):  {result.sharpe_approx:.2f}")
    print("=" * 65)

    if result.trades:
        print("\n  Last 10 trades:")
        print(f"  {'Dir':<5} {'Entry':>10} {'Exit':>10} {'P&L%':>8} {'Reason':<8} {'Time'}")
        print("  " + "-" * 63)
        for t in result.trades[-10:]:
            ep = f"{t.entry_price:.2f}"
            xp = f"{t.exit_price:.2f}" if t.exit_price else "open"
            pnl = f"{t.pnl_pct:+.2f}%"
            reason = t.exit_reason or ""
            print(f"  {t.direction:<5} {ep:>10} {xp:>10} {pnl:>8} {reason:<8} {t.entry_time[:10]}")
    print()


def results_to_dict(result: BacktestResult) -> dict:
    """Convert BacktestResult to a JSON-serialisable dict."""
    return {
        "symbol": result.symbol,
        "period": result.period,
        "total_candles": result.total_candles,
        "total_signals": result.total_signals,
        "total_trades": result.total_trades,
        "winning_trades": result.winning_trades,
        "losing_trades": result.losing_trades,
        "neutral_skipped": result.neutral_skipped,
        "win_rate": result.win_rate,
        "avg_win_pct": result.avg_win_pct,
        "avg_loss_pct": result.avg_loss_pct,
        "total_return_pct": result.total_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "profit_factor": result.profit_factor,
        "sharpe_approx": result.sharpe_approx,
        "trades": [
            {
                "direction": t.direction,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "pnl_pct": round(t.pnl_pct, 4),
                "exit_reason": t.exit_reason,
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "score": t.score,
            }
            for t in result.trades
        ],
    }


def aggregate_to_daily(candles: List[Dict]) -> List[Dict]:
    """
    Aggregate intraday candles into daily OHLCV bars.
    Groups by date (from timestamp or time field) so that HTF candles
    are consistent with the intraday price path.
    """
    from collections import OrderedDict

    days: OrderedDict = OrderedDict()

    for c in candles:
        ts = c.get("timestamp", "")
        if "T" in ts:
            date_key = ts.split("T")[0]
        else:
            # time field is HH:MM — no date info, use index-based grouping
            date_key = ts[:10] if len(ts) >= 10 else ""

        if not date_key:
            continue

        if date_key not in days:
            days[date_key] = {
                "timestamp": date_key + "T00:00:00",
                "time": date_key[5:7] + "/" + date_key[8:10] if len(date_key) >= 10 else date_key,
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c.get("volume", 0),
            }
        else:
            day = days[date_key]
            day["high"] = max(day["high"], c["high"])
            day["low"] = min(day["low"], c["low"])
            day["close"] = c["close"]
            day["volume"] += c.get("volume", 0)

    return list(days.values())


# ── CLI entrypoint ──


def main():
    parser = argparse.ArgumentParser(description="Backtest the CFD trading bot signal strategy")
    parser.add_argument("--symbol", default="XAU", help="Instrument symbol (XAU, XAG, US100, BTC)")
    parser.add_argument("--all", action="store_true", help="Run backtest for all instruments")
    parser.add_argument("--days", type=int, default=365, help="Days of history (default: 365)")
    parser.add_argument("--resolution", default="D", help="Candle interval: D, 60, 30, 15, 5 (default: D)")
    parser.add_argument("--csv", type=str, help="Path to CSV file with OHLCV data")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show individual trade entries")
    parser.add_argument("--sample", action="store_true", help="Use synthetic/sample data if no real data available")
    args = parser.parse_args()

    from historical_data import (
        fetch_alpha_vantage_historical,
        fetch_from_db_cache,
        fetch_yahoo_historical,
        load_csv_candles,
    )

    symbols = ["XAU", "XAG", "US100", "BTC"] if args.all else [args.symbol]
    all_results = []

    for symbol in symbols:
        print(f"\n{'=' * 40}")
        print(f"  Loading data for {symbol}...")
        print(f"{'=' * 40}")

        candles = None

        # Priority: CSV > Yahoo > Alpha Vantage (real data only)
        if args.csv:
            from historical_data import PRICE_MULTIPLIERS

            mult = PRICE_MULTIPLIERS.get(symbol, 1.0)
            candles = load_csv_candles(args.csv, multiplier=mult)
            if candles:
                print(f"  Loaded {len(candles)} candles from CSV")

        # Map resolution for Yahoo Finance intervals
        yahoo_interval_map = {
            "D": "1d",
            "60": "60m",
            "30": "30m",
            "15": "15m",
            "5": "5m",
            "1": "2m",  # TODO: we can have such thing how is it suppose to help 
        }
        yahoo_interval = yahoo_interval_map.get(args.resolution, "1d")

        if candles is None and not args.sample:
            # Try DB candle history first (accumulated from previous fetches)
            import database as _db

            history = _db.load_candle_history(symbol, args.resolution)
            if history and len(history) >= 50:
                candles = history
                print(f"  Loaded {len(candles)} candles from DB history")
            else:
                # Try aggregation from smaller stored intervals
                source_candidates = {
                    "5": ["1"],
                    "15": ["5", "1"],
                    "30": ["15", "5", "1"],
                    "60": ["30", "15", "5", "1"],
                    "240": ["60", "30"],
                    "D": ["60", "30", "15"],
                }
                for src_res in source_candidates.get(args.resolution, []):
                    stored = _db.load_candle_history(symbol, src_res)
                    if stored and len(stored) >= 10:
                        candles = _db.aggregate_candles(stored, args.resolution)
                        if candles and len(candles) >= 50:
                            print(
                                f"  Aggregated {len(candles)} {args.resolution} candles from {len(stored)} stored {src_res}m candles"
                            )
                            break
                        candles = None

            if candles is None:
                logging.error(f"No cached data for {symbol} at {args.resolution} resolution")
                print(f"  Fetching {args.days} days ({args.resolution} candles) from Yahoo Finance...")
                candles = fetch_yahoo_historical(symbol, period_days=args.days, interval=yahoo_interval)
                if candles:
                    print(f"  Fetched {len(candles)} candles from Yahoo Finance")
                else:
                    print(f"  Yahoo fetch failed, trying Alpha Vantage...")
                    candles = fetch_alpha_vantage_historical(symbol, count=min(args.days, 200))
                    if candles:
                        print(f"  Fetched {len(candles)} candles from Alpha Vantage")
                    else:
                        print(f"  Alpha Vantage failed, trying DB cache...")
                        candles = fetch_from_db_cache(symbol, args.resolution)
                        if not candles:
                            print(f"  ERROR: No real data available for {symbol}.")
                            print(f"  Use --csv <file> to provide data, or --sample for synthetic test data.")
                            continue

        # Try sample data ONLY if explicitly requested AND no real data available
        if candles is None and args.sample:
            print(f"  ERROR: No real data available for {symbol}. Use --csv <file> to provide data.")
            continue

        # Generate/fetch daily candles for multi-timeframe filter
        htf_candles = None
        if args.resolution != "D":
            print(f"  Loading daily candles for multi-timeframe filter...")
            if args.sample:
                # Aggregate intraday candles into daily bars so HTF is
                # consistent with the same price path (not independent RNG)
                htf_candles = aggregate_to_daily(candles)
                print(f"  HTF: {len(htf_candles)} daily candles (aggregated from {args.resolution}m)")
            else:
                # Try real sources for daily data
                htf_candles = fetch_yahoo_historical(symbol, period_days=365, interval="1d")
                if not htf_candles:
                    htf_candles = fetch_alpha_vantage_historical(symbol, count=200)
                if not htf_candles:
                    htf_candles = fetch_from_db_cache(symbol, "D")
                if htf_candles:
                    print(f"  HTF: {len(htf_candles)} daily candles loaded")
                else:
                    print(f"  HTF: No daily data — running without multi-timeframe filter")

        try:
            result = run_backtest(candles, symbol=symbol, verbose=args.verbose, htf_candles=htf_candles)
            all_results.append(result)

            if args.json:
                print(json.dumps(results_to_dict(result), indent=2))
            else:
                print_report(result)
        except ValueError as e:
            print(f"  ERROR: {e}")

    if args.all and not args.json:
        print("\n" + "=" * 65)
        print("  SUMMARY — ALL INSTRUMENTS")
        print("=" * 65)
        print(f"  {'Symbol':<8} {'Trades':>7} {'WinRate':>8} {'Return':>9} {'MaxDD':>8} {'PF':>6} {'Sharpe':>7}")
        print("  " + "-" * 56)
        for r in all_results:
            print(
                f"  {r.symbol:<8} {r.total_trades:>7} {r.win_rate:>7.1f}% {r.total_return_pct:>+8.2f}% "
                f"{r.max_drawdown_pct:>7.2f}% {r.profit_factor:>5.2f} {r.sharpe_approx:>6.2f}"
            )
        print()


if __name__ == "__main__":
    main()
