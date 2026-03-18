"""Strategy management service - extracted from main.py"""
import os
import math
import database as db

# Global strategy manager - loaded once
_strategy_manager = None


def get_symbol_strategy(symbol: str) -> str:
    """Get strategy for symbol - delegates to state"""
    from services.state import get_symbol_strategy as _get
    result = _get(symbol)
    # Also check DB for per-symbol strategy
    strategy_key = f"STRATEGY_{symbol}"
    db_strategy = db.get_setting(strategy_key)
    if db_strategy:
        return db_strategy
    return result


def set_symbol_strategy(symbol: str, strategy_id: str):
    """Set strategy for symbol - delegates to state"""
    from services.state import set_symbol_strategy as _set
    _set(symbol, strategy_id)
    # Also save to DB
    strategy_key = f"STRATEGY_{symbol}"
    db.set_setting(strategy_key, strategy_id, "user")


def get_strategy_manager(force_reload: bool = False):
    """Get or create the JSON-based strategy manager."""
    global _strategy_manager

    if _strategy_manager is None or force_reload:
        try:
            from strategy import load_strategies_from_file

            # Load from local strategies.json in project root
            json_path = os.path.join(os.path.dirname(__file__), "..", "strategies.json")
            if os.path.exists(json_path):
                _strategy_manager = load_strategies_from_file(json_path)
                print(f"[STRATEGY] Loaded {len(_strategy_manager.strategies)} strategies from JSON")
            else:
                print(f"[STRATEGY] JSON config not found at {json_path}")
                _strategy_manager = None
        except Exception as e:
            print(f"[STRATEGY] Failed to load JSON strategies: {e}")
            _strategy_manager = None

    return _strategy_manager


def analyze_with_new_strategy(symbol: str, candles: list, current_price: float,
                              requested_strategy: str = None, atr_percent: float = None,
                              vix_value: float = None) -> dict:
    """
    Analyze using new JSON-based strategy module.
    Returns dict with direction, score, confidence, etc. or None if not available.

    Score semantics (FIXED):
    - raw_score  = compute_score() result, already in [-1, 1] by weight normalization
    - direction  = from get_signal() which already applies min_score threshold ONCE
    - confidence = how far above min_score the signal is, mapped to [0, 1]
                   formula: (|raw_score| - min_score) / (1 - min_score)
                   A signal that just barely passes -> confidence ~0
                   A max-strength signal (|score|=1) -> confidence ~1
    - score (returned) = direction_sign * |raw_score|  (keeps [-1,1] range, no squashing)
    """
    manager = get_strategy_manager()
    if not manager:
        return None

    # Find strategy - use requested one or find any for symbol
    strategy = None
    if requested_strategy:
        # User specifically requested this JSON strategy
        json_id = requested_strategy.replace("JSON:", "")
        if json_id in manager.strategies:
            strategy = manager.strategies[json_id]
            # Only print on first call (check if already printed this session)
            if not getattr(analyze_with_new_strategy, "_logged", False):
                print(f"[STRATEGY] Using requested JSON strategy: {json_id}")
                analyze_with_new_strategy._logged = True
    else:
        # Default: use enabled strategy for this symbol
        for s in manager.get_enabled_strategies():
            if s.symbol.upper() == symbol.upper():
                strategy = s
                break

        # If no enabled, try any for this symbol
        if not strategy:
            for s in manager.strategies.values():
                if s.symbol.upper() == symbol.upper():
                    strategy = s
                    break

    if not strategy:
        return None

    # Update indicators with latest candles
    for candle in candles[-50:]:  # Last 50 candles for warmup
        candle_data = {
            "open": candle.get("open"),
            "high": candle.get("high"),
            "low": candle.get("low"),
            "close": candle.get("close"),
            "volume": candle.get("volume", 0),
            "timestamp": candle.get("timestamp"),
        }
        for ind in strategy.indicators.values():
            ind.update(candle_data)

    # Get current candle
    if not candles:
        return None
    current_candle = candles[-1]
    candle_data = {
        "open": current_candle.get("open"),
        "high": current_candle.get("high"),
        "low": current_candle.get("low"),
        "close": current_candle.get("close"),
        "volume": current_candle.get("volume", 0),
        "timestamp": current_candle.get("timestamp"),
    }

    # Check if we have enough indicator data
    has_data = all(ind.value() is not None for ind in strategy.indicators.values())
    if not has_data:
        print(f"[DEBUG] {symbol}: Not enough indicator data for {strategy.name}")
        return None

    # Check filters (includes volatility and VIX from strategy config)
    filters_passed, failed_filters = strategy.filters.check_all(
        candle_data, symbol, 'long',
        atr_percent=atr_percent,
        vix_value=vix_value
    )
    if not filters_passed:
        print(f"[FILTERS] {symbol}: Failed filters: {failed_filters}")
        return None

    # Get signal - get_signal() already applies min_score threshold internally (ONCE)
    signal = strategy.score_engine.get_signal()
    if not signal:
        # Signal did not pass min_score - no trade
        return None

    # Get raw score - already in [-1, 1] after weight normalization in compute_score()
    raw_score = strategy.score_engine.compute_score()

    # Clamp to [-1, 1] as a safety guard (should already be in range)
    raw_score = max(-1.0, min(1.0, raw_score))
    abs_score = abs(raw_score)

    # Direction from signal (reliable - uses RSI/Momentum logic or score sign)
    direction = 1 if signal == 'buy' else -1

    # Confidence = how strongly the score exceeds the min_score threshold
    # Maps [min_score, 1.0] -> [0.0, 1.0] so:
    #   - score just at threshold -> confidence ~ 0 (weak signal)
    #   - score at max (1.0)      -> confidence = 1.0 (strong signal)
    min_score = strategy.score_engine.min_score
    score_range = max(1.0 - min_score, 1e-6)  # avoid division by zero
    confidence = max(0.0, min(1.0, (abs_score - min_score) / score_range))

    # Returned score keeps full [-1, 1] range - direction_sign * abs_score
    # This gives meaningful spread in the UI (not squashed to +-1)
    returned_score = direction * abs_score

    print(
        f"[DEBUG] {symbol}: signal={signal}, raw_score={raw_score:.3f}, "
        f"abs_score={abs_score:.3f}, min_score={min_score}, "
        f"confidence={confidence:.3f}, returned_score={returned_score:.3f}"
    )

    # Calculate exits
    exits = strategy.exit_engine.initialize_position(
        position_id=f"live_{symbol}",
        entry_price=current_price,
        direction=direction,
    )

    return {
        'direction': 'long' if direction > 0 else 'short',
        'score': returned_score,          # [-1, 1] with full spread
        'confidence': confidence,          # [0, 1] relative to min_score threshold
        'technical_score': returned_score,
        'components': [{
            'type': 'technical',
            'name': f'JSON Strategy ({strategy.id})',
            'value': returned_score,
            'description': f'Score: {returned_score:.3f}, Signal: {signal}, Conf: {confidence:.2f}',
            'confidence': confidence
        }],
        'exits': exits,
        'strategy_id': strategy.id,
    }
