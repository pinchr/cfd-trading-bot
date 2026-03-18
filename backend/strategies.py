"""
⚠️ DEPRECATED STRATEGIES MODULE ⚠️
===================================
This module is deprecated. Please use the new JSON-based strategy system:

  - JSON config: ~/.openclaw/workspace/memory/strategies.json
  - New module: backend/strategy/
  - API: POST /api/strategies/backtest-json

The new system supports:
  - JSON configuration (easy to edit/share)
  - Configurable indicator weights
  - Volume filters
  - Dynamic TP/SL
  - Multiple strategies per symbol

This file will be removed in a future version.

---
OLD DOCUMENTATION (DEPRECATED):
-------------------------------
Trading strategy abstraction layer.

Strategies:
  1. AdaptiveRegime — original multi-factor regime-adaptive scoring
  2. MMS (Mastermind Mean-Reversion) — band-based mean reversion with sequentiality

Each strategy takes candles + indicators and returns (score, direction, components, tp, sl, confidence).
"""

from typing import Any, Dict, List, Optional, Tuple

import database as db
from indicator_classes import ALL_INDICATOR_IDS
from indicators import TechnicalIndicators
from models import Component, ComponentType, Signal, SignalDirection

# ──────────────────────────────────────────────────────────────────────
# Strategy registry
# ──────────────────────────────────────────────────────────────────────

STRATEGIES: Dict[str, "BaseStrategy"] = {}


def get_strategy(name: str) -> "BaseStrategy":
    return STRATEGIES.get(name, STRATEGIES["adaptive_regime"])


def list_strategies() -> List[Dict[str, Any]]:
    """List all available strategies with their metadata"""
    result = []
    for k, v in STRATEGIES.items():
        # Skip JSONStrategyWrapper objects - they don't have the required attributes
        if hasattr(v, 'config') and not hasattr(v, 'default_indicators'):
            continue
        
        # Convert IndicatorConfig objects to dicts
        indicators = []
        for ind in v.default_indicators:
            if isinstance(ind, IndicatorConfig):
                indicators.append(ind.to_dict())
            else:
                indicators.append({"id": ind, "enabled": True, "settings": {}})

        result.append(
            {
                "id": v.id,
                "name": getattr(v, 'display_name', v.id),
                "description": getattr(v, 'description', ''),
                "tooltip": getattr(v, "tooltip", ""),
                "default_indicators": indicators,
            }
        )
    return result


# ──────────────────────────────────────────────────────────────────────
# Indicator config structure
# ──────────────────────────────────────────────────────────────────────


class IndicatorConfig:
    """Configuration for a single indicator in a strategy"""

    def __init__(self, indicator_id: str, enabled: bool = True, settings: dict = None):
        self.id = indicator_id
        self.enabled = enabled
        self.settings = settings or {}

    def to_dict(self) -> dict:
        return {"id": self.id, "enabled": self.enabled, "settings": self.settings}


# ──────────────────────────────────────────────────────────────────────
# Base class
# ──────────────────────────────────────────────────────────────────────


class BaseStrategy:
    id: str = ""
    display_name: str = ""
    description: str = ""
    # List of IndicatorConfig objects - which indicators this strategy uses
    default_indicators: List[IndicatorConfig] = []

    def get_enabled_indicators(self) -> List[str]:
        """Return list of enabled indicator IDs"""
        return [ind.id for ind in self.default_indicators if ind.enabled]

    def get_indicator_settings(self, indicator_id: str) -> dict:
        """Get settings for a specific indicator"""
        for ind in self.default_indicators:
            if ind.id == indicator_id:
                return ind.settings
        return {}

    def to_config(self, used_indicators: List[str] = None) -> dict:
        """Convert to config dict for API response"""
        indicators = []
        used = used_indicators if used_indicators else [ind.id for ind in self.default_indicators]
        for ind in self.default_indicators:
            enabled = used_indicators is None or ind.id in used_indicators
            indicators.append(
                {
                    "id": ind.id,
                    "enabled": enabled,
                    "settings": ind.settings,
                }
            )
        return {
            "id": self.id,
            "display_name": self.display_name,
            "used_indicators": used,
            "default_indicators": indicators,
        }

    def save_strategy(self, name_suffix: str = "") -> str:
        """
        Save this strategy configuration to database with custom name.
        Returns the saved strategy ID.

        Args:
            name_suffix: Custom suffix to add to strategy name (e.g., "_v1", "_custom")

        Returns:
            Strategy ID (e.g., "adaptive_regime_custom1")
        """
        import database as db

        # Build strategy ID
        strategy_id = f"{self.id}{name_suffix}" if name_suffix else self.id

        # Convert indicators to dict format
        indicators_data = []
        for ind in self.default_indicators:
            if isinstance(ind, IndicatorConfig):
                indicators_data.append(ind.to_dict())
            else:
                indicators_data.append({"id": ind, "enabled": True, "settings": {}})

        # Save to database
        setting_key = f"STRATEGY_{strategy_id.upper()}"
        setting_value = {
            "id": strategy_id,
            "base_strategy": self.id,
            "display_name": f"{self.display_name}{name_suffix}",
            "default_indicators": indicators_data,
        }

        db.set_setting(setting_key, setting_value)

        # Also add to STRATEGIES registry
        STRATEGIES[strategy_id] = self

        return strategy_id

    @staticmethod
    def load_strategy(strategy_id: str) -> Optional["BaseStrategy"]:
        """Load a saved strategy from database"""
        import database as db

        setting_key = f"STRATEGY_{strategy_id.upper()}"
        saved = db.get_setting(setting_key)

        if not saved:
            return None

        # Load base strategy and apply saved config
        base_id = saved.get("base_strategy", strategy_id)
        base_strategy = STRATEGIES.get(base_id)

        if not base_strategy:
            return None

        # Create new instance with saved indicators
        new_strategy = type(
            f"Custom{strategy_id.title().replace('_', '')}",
            (BaseStrategy,),
            {
                "id": strategy_id,
                "display_name": saved.get("display_name", strategy_id),
                "description": base_strategy.description,
                "default_indicators": [
                    IndicatorConfig(ind["id"], enabled=ind.get("enabled", True), settings=ind.get("settings", {}))
                    for ind in saved.get("default_indicators", [])
                ],
            },
        )

        # Register it
        STRATEGIES[strategy_id] = new_strategy

        return new_strategy()

    def score(
        self,
        candles: List[Dict],
        indicators: Dict,
        symbol: str,
        instrument_info: Dict,
        current_price: float,
        htf_bias: float = 0.0,
        news_score: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Returns dict with keys:
          score, direction, components, confidence, take_profit, stop_loss,
          risk_reward_ratio, technical_score
        """
        raise NotImplementedError


# ──────────────────────────────────────────────────────────────────────
# Strategy 1: Adaptive Regime (original)
# ──────────────────────────────────────────────────────────────────────


class AdaptiveRegimeStrategy(BaseStrategy):
    id = "adaptive_regime"
    display_name = "Adaptive Regime"
    description = "Multi-factor regime-adaptive scoring with ADX-based trending/ranging detection"
    tooltip = """**Best for:** Trending markets (forex, indices, crypto with clear direction)
        
**How it works:**
• Detects market regime using ADX (ADX > 25 = trending)
• Adjusts indicator weights dynamically:
- Trending: higher weight on MACD, SMA cross, momentum
- Ranging: higher weight on RSI, Bollinger Bands mean-reversion
• Filters trades with multi-timeframe alignment
• Uses ATR-based dynamic SL/TP (R:R ~1:2 to 1:3)

**When to use:**
✓ Markets showing clear directional movement
✓ You're comfortable with trend-following
✓ Higher volatility periods"""

    # Which indicators this strategy uses by default - with settings
    default_indicators = [
        IndicatorConfig("RSI", enabled=True, settings={"period": 14, "overbought": 70, "oversold": 30}),
        IndicatorConfig("MACD", enabled=True, settings={"fast": 12, "slow": 26, "signal": 9}),
        IndicatorConfig("BB", enabled=True, settings={"period": 20, "std": 2}),
        IndicatorConfig("SMA", enabled=True, settings={"period": 20, "period2": 50}),
        IndicatorConfig("ADX", enabled=True, settings={"period": 14}),
        IndicatorConfig("STOCH", enabled=True, settings={"rsi_period": 14, "stoch_period": 14}),
        IndicatorConfig("MOMENTUM", enabled=True, settings={"period": 10}),
    ]

    def score(self, candles, indicators, symbol, instrument_info, current_price, htf_bias=0.0, news_score=0.0, custom_weights=None):
        components = []
        scores = []
        weights = []
        
        # Default weights
        default_weights = {
            'rsi': 0.15,
            'macd': 0.25,
            'stoch': 0.10,
            'momentum': 0.20,
            'adx': 0.15,
            'bb': 0.15,
        }
        w = {**default_weights, **(custom_weights or {})}

        # --- Detect market regime via ADX ---
        adx_data = indicators.get("adx")
        adx_value = adx_data["adx"] if adx_data else 20
        is_trending = adx_value > 25
        regime = "TRENDING" if is_trending else "RANGING"

        if adx_data:
            trend_dir = "UP" if adx_data["plus_di"] > adx_data["minus_di"] else "DOWN"
            components.append(
                Component(
                    type=ComponentType.TECHNICAL,
                    name="ADX (Trend)",
                    value=(
                        max(-1, min(1, (adx_value - 25) / 25))
                        if trend_dir == "UP"
                        else max(-1, min(1, -(adx_value - 25) / 25))
                    ),
                    description=f"ADX {adx_value:.0f} ({regime}, {trend_dir}) +DI:{adx_data['plus_di']:.0f} -DI:{adx_data['minus_di']:.0f}",
                    confidence=0.8 if adx_value > 30 else 0.5,
                    indicators=adx_data,
                )
            )

        # --- RSI ---
        if indicators.get("rsi_14") is not None:
            rsi = indicators["rsi_14"]
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
            rsi_score = max(-1, min(1, rsi_score))
            zone = "OVERSOLD" if rsi < 30 else "OVERBOUGHT" if rsi > 70 else "NEUTRAL"
            rsi_weight = w.get('rsi', 0.15) if is_trending else w.get('rsi', 0.25)
            components.append(
                Component(
                    type=ComponentType.TECHNICAL,
                    name="RSI (14)",
                    value=rsi_score,
                    description=f"RSI {rsi:.1f} ({zone})",
                    confidence=0.85 if abs(rsi - 50) > 20 else 0.5,
                    indicators={"value": rsi, "zone": zone},
                )
            )
            scores.append(rsi_score)
            weights.append(rsi_weight)

        # --- StochRSI ---
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
                components.append(
                    Component(
                        type=ComponentType.TECHNICAL,
                        name="StochRSI",
                        value=stoch_score,
                        description=f"StochRSI K:{k:.0f} D:{d:.0f}",
                        confidence=0.7 if abs(k - 50) > 30 else 0.4,
                        indicators=stoch,
                    )
                )
                scores.append(stoch_score)
                weights.append(w.get('stoch', 0.10))

        # --- MACD ---
        if indicators.get("macd"):
            macd = indicators["macd"]
            if macd.get("histogram") is not None and macd.get("macd_line") is not None:
                histogram = macd["histogram"]
                macd_line = macd["macd_line"]
                signal_line = macd.get("signal_line", 0) or 0
                atr = indicators.get("atr_14", 1) or 1
                norm_hist = histogram / atr
                macd_score = max(-1, min(1, norm_hist * 2))
                cross = "BULLISH" if macd_line > signal_line else "BEARISH"
                macd_weight = w.get('macd', 0.25) if is_trending else w.get('macd', 0.15)
                components.append(
                    Component(
                        type=ComponentType.TECHNICAL,
                        name="MACD",
                        value=macd_score,
                        description=f"MACD {cross} | hist/ATR: {norm_hist:.2f}",
                        confidence=0.8 if abs(norm_hist) > 0.5 else 0.5,
                        indicators=macd,
                    )
                )
                scores.append(macd_score)
                weights.append(macd_weight)

        # --- Bollinger Bands ---
        if indicators.get("bollinger_bands"):
            bb = indicators["bollinger_bands"]
            closes = indicators.get("_closes", [])
            if closes:
                cp = closes[-1]
                bb_range = bb["upper"] - bb["lower"] if bb["upper"] != bb["lower"] else 1
                bb_position = ((cp - bb["lower"]) / bb_range) * 2 - 1
                bb_score = -bb_position * 0.8
                zone = "UPPER" if cp > bb["upper"] else "LOWER" if cp < bb["lower"] else "MIDDLE"
                bb_weight = w.get('bb', 0.15) if is_trending else w.get('bb', 0.25)
                components.append(
                    Component(
                        type=ComponentType.TECHNICAL,
                        name="Bollinger Bands",
                        value=max(-1, min(1, bb_score)),
                        description=f"BB {zone} (pos: {bb_position:.2f})",
                        confidence=0.75 if abs(bb_position) > 0.8 else 0.4,
                        indicators={"position": bb_position, "zone": zone},
                    )
                )
                scores.append(max(-1, min(1, bb_score)))
                weights.append(bb_weight)

        # --- SMA Trend ---
        if indicators.get("sma_20") is not None and indicators.get("sma_50") is not None:
            sma_20 = indicators["sma_20"]
            sma_50 = indicators["sma_50"]
            if sma_50 > 0:
                sma_diff_pct = ((sma_20 - sma_50) / sma_50) * 100
                sma_score = max(-1, min(1, sma_diff_pct / 2))
                trend = "BULLISH" if sma_20 > sma_50 else "BEARISH"
                sma_weight = w.get('sma', 0.20) if is_trending else w.get('sma', 0.10)
                components.append(
                    Component(
                        type=ComponentType.TECHNICAL,
                        name="SMA Cross (20/50)",
                        value=sma_score,
                        description=f"SMA20/50: {sma_diff_pct:.2f}% ({trend})",
                        confidence=0.7,
                        indicators={"sma_20": sma_20, "sma_50": sma_50, "trend": trend},
                    )
                )
                scores.append(sma_score)
                weights.append(sma_weight)

        # --- Volume ---
        vol = indicators.get("volume_profile")
        if vol and vol["vol_ratio"] > 1.5:
            vol_bias = max(-0.5, min(0.5, (vol["up_down_ratio"] - 1.0) * 0.3))
            components.append(
                Component(
                    type=ComponentType.TECHNICAL,
                    name="Volume",
                    value=vol_bias,
                    description=f"Vol {vol['vol_ratio']:.1f}x avg | Up/Down: {vol['up_down_ratio']:.1f}",
                    confidence=0.6,
                    indicators=vol,
                )
            )
            scores.append(vol_bias)
            weights.append(0.10)

        # --- Momentum ---
        if indicators.get("momentum_10") is not None:
            momentum = indicators["momentum_10"]
            base_price = indicators.get("sma_20", 1) or 1
            mom_pct = (momentum / base_price) * 100 if base_price else 0
            momentum_score = max(-1, min(1, mom_pct / 2))
            components.append(
                Component(
                    type=ComponentType.TECHNICAL,
                    name="Momentum (10)",
                    value=momentum_score,
                    description=f"Momentum: {mom_pct:.2f}%",
                    confidence=0.6,
                    indicators={"value": momentum, "pct": mom_pct},
                )
            )
            scores.append(momentum_score)
            weights.append(w.get('momentum', 0.05))

        # --- Candlestick Patterns ---
        cp_data = indicators.get("candlestick_patterns")
        if cp_data and cp_data.get("patterns") and abs(cp_data["net_bias"]) > 0.1:
            pattern_names = ", ".join(p["name"] for p in cp_data["patterns"])
            cp_score = max(-1, min(1, cp_data["net_bias"]))
            components.append(
                Component(
                    type=ComponentType.TECHNICAL,
                    name="Candlestick Patterns",
                    value=cp_score,
                    description=f"Patterns: {pattern_names} (bias: {cp_data['net_bias']:.2f})",
                    confidence=0.7,
                    indicators={"patterns": [p["name"] for p in cp_data["patterns"]], "net_bias": cp_data["net_bias"]},
                )
            )
            scores.append(cp_score)
            weights.append(w.get('adx', 0.15))

        # --- Composite ---
        if scores:
            total_weight = sum(weights)
            # Always normalize to sum = 1.0
            if total_weight > 0:
                weights = [w / total_weight for w in weights]
            technical_score = sum(s * w for s, w in zip(scores, weights)) if weights else 0
        else:
            technical_score = 0

        # Agreement bonus/penalty
        if len(scores) >= 3:
            bullish = sum(1 for s in scores if s > 0.1)
            bearish = sum(1 for s in scores if s < -0.1)
            agreement = max(bullish, bearish) / len(scores)
            if agreement > 0.7:
                technical_score *= 1.15
            elif agreement < 0.4:
                technical_score *= 0.7

        technical_score = max(-1, min(1, technical_score))

        # === V2 FILTERS ===

        # ── VIX Filter (v2) ──
        # Skip trading if VIX too high (extreme volatility)
        vix = indicators.get("vix") or indicators.get("_vix")
        vix_filter_active = False
        vix_component = None
        # VIX filter disabled - high volatility doesn't mean bad trading opportunity
        # TODO: Re-enable when per-symbol VIX is properly implemented
        if vix and isinstance(vix, dict):
            vix_value = vix.get("value", vix.get("VIX", 0))
            # if vix_value > 30:
            #     # High volatility - reduce confidence, may skip
            #     technical_score *= 0.3  # Strong dampening
            #     vix_filter_active = True
            #     vix_component = Component(
            #         type=ComponentType.TECHNICAL, name="VIX Filter",
            #         value=0.0,
            #         description=f"VIX {vix_value:.1f} > 30: HIGH VOLATILITY - signal dampened",
            #         confidence=0.9, indicators={"vix": vix_value, "action": "dampened"}
            #     )
            # elif vix_value > 22:
            #     technical_score *= 0.7
            #     vix_filter_active = True
            #     vix_component = Component(
            #         type=ComponentType.TECHNICAL, name="VIX Filter",
            #         value=0.0,
            #         description=f"VIX {vix_value:.1f} > 22: elevated volatility - mild dampening",
            #         confidence=0.7, indicators={"vix": vix_value, "action": "mild_dampen"}
            #     )
        if vix_component:
            components.append(vix_component)

        # ── Seasonality Filter (v2) ──
        # Turn-of-month effect: days 1-3 of month have positive bias
        from datetime import datetime

        now = datetime.now()
        is_turn_of_month = now.day <= 3
        seasonality_bias = 0.0
        if is_turn_of_month:
            # Add +0.1 bias for turn-of-month (Sharpe ~1.8 in research)
            seasonality_bias = 0.10
            components.append(
                Component(
                    type=ComponentType.TECHNICAL,
                    name="Seasonality",
                    value=seasonality_bias,
                    description=f"Turn-of-month (day {now.day}): +{seasonality_bias:.2f} bias",
                    confidence=0.6,
                    indicators={"day": now.day, "effect": "turn_of_month"},
                )
            )

        # Apply seasonality bias (with clamping)
        if seasonality_bias > 0:
            technical_score = max(-1, min(1, technical_score * 0.9 + seasonality_bias))

        # === END V2 FILTERS ===

        # Blend with news + HTF
        effective_news = news_score if abs(news_score) > 0.1 else 0.0
        if effective_news != 0:
            final_score = technical_score * 0.80 + effective_news * 0.10 + htf_bias * 0.10
        elif abs(htf_bias) > 0.1:
            final_score = technical_score * 0.85 + htf_bias * 0.15
        else:
            final_score = technical_score
        final_score = max(-1, min(1, final_score))

        # MTF alignment filter
        if abs(htf_bias) > 0.3:
            if (final_score > 0) != (htf_bias > 0):
                final_score *= 0.5

        # Direction
        min_score = instrument_info.get("min_score", 0.15)
        strong_threshold = max(0.45, min_score + 0.20)
        if final_score > strong_threshold:
            direction = SignalDirection.STRONG_BUY
        elif final_score > min_score:
            direction = SignalDirection.BUY
        elif final_score < -strong_threshold:
            direction = SignalDirection.STRONG_SELL
        elif final_score < -min_score:
            direction = SignalDirection.SELL
        else:
            direction = SignalDirection.NEUTRAL

        # Minimum indicator agreement filter
        component_vals = [c.value for c in components]
        bullish_c = sum(1 for v in component_vals if v > 0.1)
        bearish_c = sum(1 for v in component_vals if v < -0.1)
        min_agreement = 3 if instrument_info.get("asset_class") == "commodity" else 2
        if direction != SignalDirection.NEUTRAL and max(bullish_c, bearish_c) < min_agreement:
            direction = SignalDirection.NEUTRAL

        # Trend alignment for commodities
        sma_50 = indicators.get("sma_50")
        if instrument_info.get("asset_class") == "commodity" and sma_50 and direction != SignalDirection.NEUTRAL:
            price_above = current_price > sma_50
            is_buy = direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY)
            if is_buy and not price_above:
                direction = SignalDirection.NEUTRAL
            elif not is_buy and price_above:
                direction = SignalDirection.NEUTRAL

        # Confidence
        if component_vals:
            bullish_count = sum(1 for v in component_vals if v > 0.1)
            bearish_count = sum(1 for v in component_vals if v < -0.1)
            total_opinionated = bullish_count + bearish_count
            agreement = max(bullish_count, bearish_count) / max(total_opinionated, 1)
            confidence = min(0.95, abs(final_score) * agreement + 0.1)
        else:
            confidence = 0.1

        # TP/SL
        atr = indicators.get("atr_14", current_price * 0.01)
        adx_trending = adx_data and adx_data["adx"] > 25 if adx_data else False
        use_trailing = instrument_info.get("trailing_stop", False)
        if use_trailing:
            sl_mult, tp_mult = 3.0, (4.0 if adx_trending else 3.5)
        elif adx_trending:
            sl_mult, tp_mult = 1.5, 3.5
        else:
            sl_mult, tp_mult = 1.5, 3.0

        if direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY):
            stop_loss = current_price - (atr * sl_mult)
            take_profit = current_price + (atr * tp_mult)
        else:
            stop_loss = current_price + (atr * sl_mult)
            take_profit = current_price - (atr * tp_mult)

        risk = abs(current_price - stop_loss)
        reward = abs(take_profit - current_price)
        rr = reward / risk if risk > 0 else 0

        return {
            "score": final_score,
            "direction": direction,
            "components": components,
            "confidence": confidence,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "risk_reward_ratio": rr,
            "technical_score": technical_score,
        }


# ──────────────────────────────────────────────────────────────────────
# Strategy 2: MMS (Mastermind Mean-Reversion Strategy)
# Based on mastermindzx.pl methodology
# ──────────────────────────────────────────────────────────────────────

# Sequentiality state: per-symbol leverage scaling after losses
# Now persisted to database - survives restarts
_mms_seq_state: Dict[str, Dict] = {}


def _get_seq_state(symbol: str) -> Dict:
    """Get sequentiality state for symbol. Loads from DB if not in memory."""
    global _mms_seq_state
    if symbol not in _mms_seq_state:
        # Try to load from database first
        db_state = db.load_mms_state(symbol)
        if db_state:
            _mms_seq_state[symbol] = db_state
        else:
            # Default state for new symbol
            _mms_seq_state[symbol] = {
                "leverage_level": 3,  # index into LEVERAGE_LADDER
                "consecutive_losses": 0,
                "in_recovery": False,
            }
            # Save default to DB
            db.save_mms_state(symbol, _mms_seq_state[symbol])
    return _mms_seq_state[symbol]


def _save_seq_state(symbol: str, state: Dict):
    """Save sequentiality state to database."""
    db.save_mms_state(symbol, state)


# Leverage ladder: index 0 = minimum, index 5 = maximum
LEVERAGE_LADDER = [0.01, 0.1, 0.25, 0.5, 1.0, 2.0]
LEVERAGE_LABELS = ["x0.01", "x0.1", "x0.25", "x0.5", "x1", "x2"]


def mms_on_trade_result(symbol: str, is_win: bool):
    """Call after a trade closes to update sequentiality state. Persists to DB."""
    state = _get_seq_state(symbol)
    if is_win:
        if state["in_recovery"]:
            # First win after loss series: jump to x0.5
            state["leverage_level"] = 3  # x0.5
            state["in_recovery"] = False
        else:
            # Normal win: step up one level (max x2)
            state["leverage_level"] = min(5, state["leverage_level"] + 1)
        state["consecutive_losses"] = 0
    else:
        state["consecutive_losses"] += 1
        state["in_recovery"] = True
        # Step down: more losses = lower leverage
        if state["consecutive_losses"] >= 4:
            state["leverage_level"] = 0  # x0.01 "scout" mode
        elif state["consecutive_losses"] >= 3:
            state["leverage_level"] = 1  # x0.1
        elif state["consecutive_losses"] >= 2:
            state["leverage_level"] = 2  # x0.25
        else:
            state["leverage_level"] = max(0, state["leverage_level"] - 2)

    # Persist to database
    _save_seq_state(symbol, state)


def init_mms_states_from_db():
    """Load all MMS states from database on startup."""
    global _mms_seq_state
    db_states = db.load_all_mms_states()
    for symbol, state in db_states.items():
        _mms_seq_state[symbol] = state


# Initialize on module load
init_mms_states_from_db()


class MMSStrategy(BaseStrategy):
    """
    MMS (Mastermind Mean-Reversion Strategy)

    Core idea: price tends to revert to mean after hitting statistical extremes
    measured by ATR-derivative bands (Bollinger Bands).

    Entry: Price touches upper band → SHORT (wait for reactionary candle).
           Price touches lower band → LONG (wait for reactionary candle).
    Exit:  TP at opposite band (position flip). SL at 2% price move.
    Risk:  Sequentiality system scales leverage after losses.
           Max x2 leverage, max 3% capital risk.
           NO trailing stops (empirically worse for mean reversion).

    Confirmation: Stochastic RSI for entry timing.
    """

    id = "mms"
    display_name = "MMS Mean-Reversion"
    description = "Band-based mean reversion with sequentiality risk management (mastermindzx.pl)"
    tooltip = """**Best for:** Range-bound markets (Gold, Silver, sideways crypto)

**How it works:**
• Trades price extremes at Bollinger Bands (top/bottom 5%)
• Waits for reactionary candle confirmation
• Uses StochRSI for timing entries
• **Sequentiality:** Scales position size after losses
  - x2 max after wins, x0.01 "scout mode" after 4+ losses
• TP at opposite band | SL fixed at 2%

**When to use:**
✓ Markets stuck in a range/channel
✓ You're patient (fewer signals, higher quality)
✓ Lower volatility, mean-reverting assets (GC=XAG=XAU)"""

    # MMS uses fewer indicators - mainly BB, RSI, STOCH
    default_indicators = [
        IndicatorConfig("RSI", enabled=True, settings={"period": 14, "overbought": 70, "oversold": 30}),
        IndicatorConfig("BB", enabled=True, settings={"period": 20, "std": 2}),
        IndicatorConfig("STOCH", enabled=True, settings={"rsi_period": 14, "stoch_period": 14}),
        IndicatorConfig("SMA", enabled=True, settings={"period": 20, "period2": 50}),
    ]

    def score(self, candles, indicators, symbol, instrument_info, current_price, htf_bias=0.0, news_score=0.0):

        components = []
        closes = indicators.get("_closes", [c["close"] for c in candles])

        # ── 1. Bollinger Bands position (primary signal) ──
        bb = indicators.get("bollinger_bands")
        if not bb:
            return self._neutral(symbol, current_price, components)

        bb_upper = bb["upper"]
        bb_lower = bb["lower"]
        bb_middle = bb["middle"]
        bb_range = bb_upper - bb_lower if bb_upper != bb_lower else 1
        bb_position = (current_price - bb_lower) / bb_range  # 0..1

        # How far outside the bands (>1 = above upper, <0 = below lower)
        band_score = 0.0
        if bb_position > 0.95:
            # At or above upper band → SELL signal (mean revert down)
            band_score = -min(1.0, (bb_position - 0.5) * 2)
        elif bb_position < 0.05:
            # At or below lower band → BUY signal (mean revert up)
            band_score = min(1.0, (0.5 - bb_position) * 2)
        elif bb_position > 0.75:
            # Approaching upper → mild sell bias
            band_score = -((bb_position - 0.5) * 1.2)
        elif bb_position < 0.25:
            # Approaching lower → mild buy bias
            band_score = (0.5 - bb_position) * 1.2
        else:
            # Middle zone → no signal (wait for extremes)
            band_score = 0.0

        band_score = max(-1, min(1, band_score))
        band_zone = "UPPER" if bb_position > 0.8 else "LOWER" if bb_position < 0.2 else "MIDDLE"

        components.append(
            Component(
                type=ComponentType.TECHNICAL,
                name="BB Position (MMS)",
                value=band_score,
                description=f"BB pos: {bb_position:.2f} ({band_zone}) — {'SELL zone' if band_score < -0.3 else 'BUY zone' if band_score > 0.3 else 'WAIT zone'}",
                confidence=0.9 if abs(band_score) > 0.5 else 0.4,
                indicators={"bb_position": bb_position, "zone": band_zone},
            )
        )

        # ── 2. Reactionary candle confirmation ──
        # After touching band, we need a candle in the opposite direction
        react_score = 0.0
        if len(candles) >= 2:
            last = candles[-1]
            prev = candles[-2]
            last_body = last["close"] - last["open"]
            prev_body = prev["close"] - prev["open"]

            if band_score < -0.3 and last_body < 0:
                # Upper band hit + bearish candle = confirmed SHORT
                react_score = -0.6
            elif band_score > 0.3 and last_body > 0:
                # Lower band hit + bullish candle = confirmed LONG
                react_score = 0.6
            elif band_score < -0.3 and last_body > 0:
                # Upper band but candle still bullish = wait
                react_score = -0.1
            elif band_score > 0.3 and last_body < 0:
                # Lower band but candle still bearish = wait
                react_score = 0.1

        react_score = max(-1, min(1, react_score))
        if abs(react_score) > 0.05:
            components.append(
                Component(
                    type=ComponentType.TECHNICAL,
                    name="Reactionary Candle",
                    value=react_score,
                    description=f"{'Confirmed' if abs(react_score) > 0.3 else 'Waiting'} — candle {'bearish' if react_score < 0 else 'bullish'}",
                    confidence=0.8 if abs(react_score) > 0.3 else 0.3,
                    indicators={},
                )
            )

        # ── 3. Stochastic RSI confirmation ──
        stoch = indicators.get("stoch_rsi")
        stoch_score = 0.0
        if stoch:
            k, d = stoch["k"], stoch["d"]
            if k > 80 and band_score < -0.2:
                stoch_score = -0.5  # Overbought confirms sell
            elif k < 20 and band_score > 0.2:
                stoch_score = 0.5  # Oversold confirms buy
            elif k > 70:
                stoch_score = -0.2
            elif k < 30:
                stoch_score = 0.2

            stoch_score = max(-1, min(1, stoch_score))
            if abs(stoch_score) > 0.1:
                components.append(
                    Component(
                        type=ComponentType.TECHNICAL,
                        name="StochRSI (MMS)",
                        value=stoch_score,
                        description=f"StochRSI K:{k:.0f} D:{d:.0f} — {'overbought' if k > 70 else 'oversold' if k < 30 else 'neutral'}",
                        confidence=0.7 if abs(k - 50) > 25 else 0.4,
                        indicators=stoch,
                    )
                )

        # ── 4. Distance from middle band (mean) ──
        # Stronger signal when further from mean
        dist_from_mean = (current_price - bb_middle) / bb_range if bb_range > 0 else 0
        mean_rev_score = -dist_from_mean * 0.8  # Further from mean = stronger reversion signal
        mean_rev_score = max(-1, min(1, mean_rev_score))

        if abs(mean_rev_score) > 0.15:
            components.append(
                Component(
                    type=ComponentType.TECHNICAL,
                    name="Mean Distance",
                    value=mean_rev_score,
                    description=f"Distance from mean: {dist_from_mean:.2f} BB widths",
                    confidence=0.6,
                    indicators={"distance": dist_from_mean},
                )
            )

        # ── 5. ATR relative to price (volatility check) ──
        atr = indicators.get("atr_14", current_price * 0.01) or current_price * 0.01
        atr_pct = (atr / current_price) * 100 if current_price > 0 else 0

        # MMS works best in volatile markets — weak signal if ATR too low
        vol_factor = min(1.5, max(0.3, atr_pct / 1.0))  # normalize around 1% ATR

        # ── Composite score ──
        # Weights: BB position (40%), reaction (25%), stoch (15%), mean distance (20%)
        raw_score = band_score * 0.40 + react_score * 0.25 + stoch_score * 0.15 + mean_rev_score * 0.20

        # Apply volatility factor (more volatile = stronger signal)
        raw_score *= vol_factor
        technical_score = max(-1, min(1, raw_score))

        # === V2 FILTERS FOR MMS ===

        # ── VIX Filter (v2) ──
        # MMS is more sensitive to volatility - lower threshold
        vix = indicators.get("vix") or indicators.get("_vix")
        vix_component = None
        if vix and isinstance(vix, dict):
            vix_value = vix.get("value", vix.get("VIX", 0))
            if vix_value > 25:
                # MMS: skip if VIX > 25 (mean reversion fails in extreme volatility)
                technical_score = 0.0  # Neutralize signal
                vix_component = Component(
                    type=ComponentType.TECHNICAL,
                    name="VIX Filter (MMS)",
                    value=0.0,
                    description=f"VIX {vix_value:.1f} > 25: MMS disabled in extreme volatility",
                    confidence=0.95,
                    indicators={"vix": vix_value, "action": "disabled"},
                )
            elif vix_value > 20:
                technical_score *= 0.5
                vix_component = Component(
                    type=ComponentType.TECHNICAL,
                    name="VIX Filter (MMS)",
                    value=0.0,
                    description=f"VIX {vix_value:.1f} > 20: reduced MMS confidence",
                    confidence=0.7,
                    indicators={"vix": vix_value, "action": "reduced"},
                )
        if vix_component:
            components.append(vix_component)

        # ── Seasonality Filter (v2) ──
        # MMS benefits more from turn-of-month (mean reversion stronger)
        from datetime import datetime

        now = datetime.now()
        is_turn_of_month = now.day <= 3
        if is_turn_of_month:
            # MMS gets stronger bias: +0.15 (mean reversion effect stronger)
            technical_score = max(-1, min(1, technical_score * 0.85 + 0.15))
            components.append(
                Component(
                    type=ComponentType.TECHNICAL,
                    name="Seasonality (MMS)",
                    value=0.15,
                    description=f"Turn-of-month (day {now.day}): +0.15 bias for MMS",
                    confidence=0.65,
                    indicators={"day": now.day, "effect": "turn_of_month"},
                )
            )

        # ── No-Trade Zone (v2) ──
        # Add buffer zone around band edges (MMS already waits for extremes, add 2% buffer)
        if 0.03 < bb_position < 0.07 or 0.93 < bb_position < 0.97:
            # Near buffer zone - reduce signal
            technical_score *= 0.5
            components.append(
                Component(
                    type=ComponentType.TECHNICAL,
                    name="No-Trade Zone",
                    value=0.0,
                    description=f"BB position {bb_position:.2f} in buffer zone - reduced",
                    confidence=0.6,
                    indicators={"bb_position": bb_position, "action": "buffer"},
                )
            )

        # === END V2 FILTERS ===

        # ── Sequentiality leverage adjustment ──
        seq_state = _get_seq_state(symbol)
        lev_level = seq_state["leverage_level"]
        lev_mult = LEVERAGE_LADDER[lev_level]
        lev_label = LEVERAGE_LABELS[lev_level]

        components.append(
            Component(
                type=ComponentType.TECHNICAL,
                name="Sequentiality",
                value=0.0,
                description=f"Leverage: {lev_label} | Losses: {seq_state['consecutive_losses']} | {'Recovery' if seq_state['in_recovery'] else 'Normal'}",
                confidence=1.0,
                indicators={"leverage": lev_mult, "level": lev_level},
            )
        )

        # ── Direction thresholds ──
        # MMS uses tighter thresholds — band proximity is the trigger
        min_score = 0.20
        if abs(technical_score) > 0.50:
            direction = SignalDirection.STRONG_BUY if technical_score > 0 else SignalDirection.STRONG_SELL
        elif abs(technical_score) > min_score:
            direction = SignalDirection.BUY if technical_score > 0 else SignalDirection.SELL
        else:
            direction = SignalDirection.NEUTRAL

        # ── Confidence ──
        component_vals = [c.value for c in components if c.name != "Sequentiality"]
        if component_vals:
            same_dir = sum(1 for v in component_vals if (v > 0.1) == (technical_score > 0) and abs(v) > 0.1)
            confidence = min(0.95, abs(technical_score) * (same_dir / max(len(component_vals), 1)) + 0.1)
        else:
            confidence = 0.1

        # ── TP / SL (MMS-specific) ──
        # TP: opposite band (position flip point)
        # SL: 2% of price (fixed, no trailing)
        sl_pct = 0.02  # 2% stop loss (MMS rule)

        if direction in (SignalDirection.BUY, SignalDirection.STRONG_BUY):
            take_profit = bb_upper  # TP at upper band
            stop_loss = current_price * (1 - sl_pct)
        elif direction in (SignalDirection.SELL, SignalDirection.STRONG_SELL):
            take_profit = bb_lower  # TP at lower band
            stop_loss = current_price * (1 + sl_pct)
        else:
            take_profit = bb_upper
            stop_loss = current_price * (1 - sl_pct)

        risk = abs(current_price - stop_loss)
        reward = abs(take_profit - current_price)
        rr = reward / risk if risk > 0 else 0

        return {
            "score": technical_score,
            "direction": direction,
            "components": components,
            "confidence": confidence,
            "take_profit": take_profit,
            "stop_loss": stop_loss,
            "risk_reward_ratio": rr,
            "technical_score": technical_score,
            "mms_leverage": lev_mult,
            "mms_leverage_label": lev_label,
        }

    def _neutral(self, symbol, current_price, components):
        return {
            "score": 0.0,
            "direction": SignalDirection.NEUTRAL,
            "components": components,
            "confidence": 0.0,
            "take_profit": 0.0,
            "stop_loss": 0.0,
            "risk_reward_ratio": 0.0,
            "technical_score": 0.0,
        }


# ──────────────────────────────────────────────────────────────────────
# Register strategies
# ──────────────────────────────────────────────────────────────────────

_adaptive = AdaptiveRegimeStrategy()
_mms = MMSStrategy()
STRATEGIES[_adaptive.id] = _adaptive
STRATEGIES[_mms.id] = _mms


class JSONStrategyWrapper:
    """Wrapper for JSON strategy config to work with old backtest API"""
    
    def __init__(self, config: dict, strat_id: str):
        self.config = config
        self.id = strat_id
        self.name = config.get('name', strat_id)
        
        # Parse exits config
        exits = config.get('exits', {})
        self.sl_type = exits.get('stop_loss', {}).get('type', 'percent_from_entry')
        self.sl_value = exits.get('stop_loss', {}).get('value', -2.0)
        self.tp_type = exits.get('take_profit', {}).get('type', 'percent_from_entry')
        self.tp_value = exits.get('take_profit', {}).get('value', 5.0)
        
        # Parse risk config
        risk = config.get('risk', {})
        self.leverage = risk.get('leverage', 20)
        self.risk_per_trade = risk.get('risk_per_trade_pct', 2.0)
        
        # Direction
        self.trade_direction = config.get('trade_direction', 'long_only')
        
        # Score config
        self.score_config = config.get('score', {})
        self.min_score = self.score_config.get('min_score', 0.01)
        self.indicator_weights = {}
        for ind in self.score_config.get('indicators', []):
            self.indicator_weights[ind['name']] = ind.get('weight', 0)
        
        # Filters config
        self.filters_config = config.get('filters', {})
    
    def _normalize_indicator_name(self, name: str) -> str:
        """Normalize indicator name to match what's passed from TechnicalIndicators"""
        # Map uppercase to lowercase versions
        mapping = {
            'RSI': 'rsi_14',
            'MACD': 'macd',
            'MOMENTUM': 'momentum_10',
            'ADX': 'adx',
            'BB': 'bollinger_bands',
            'STOCH': 'stoch_rsi',
            'SMA': 'sma_20',
            'VOLUME': 'volume_profile',
        }
        return mapping.get(name.upper(), name.lower())
    
    def score(self, candles, indicators, symbol, instrument_info, current_price, htf_bias=0.0, news_score=0.0, custom_weights=None):
        """Calculate strategy score based on JSON config"""
        try:
            # Calculate weighted score from indicators
            total_weight = 0
            weighted_score = 0
            components = {}
            
            weights = custom_weights or self.indicator_weights
            
            for ind_name, weight in weights.items():
                if weight == 0:
                    continue
                
                # Normalize indicator name to match what's passed from TechnicalIndicators
                normalized_name = self._normalize_indicator_name(ind_name)
                
                # Get indicator value from indicators dict
                ind_value = None
                ind_data = indicators.get(normalized_name)
                
                if ind_data:
                    # Handle different indicator formats
                    if isinstance(ind_data, dict):
                        # MACD: {"macd_line": X, "signal_line": Y, "histogram": Z}
                        if 'macd_line' in ind_data:
                            ind_value = ind_data.get('histogram', 0)
                        # ADX: {"adx": X, "plus_di": Y, "minus_di": Z}
                        elif 'adx' in ind_data:
                            # ADX value
                            adx_val = ind_data.get('adx', 0)
                            # DI crossover as signal
                            plus_di = ind_data.get('plus_di', 0)
                            minus_di = ind_data.get('minus_di', 0)
                            if plus_di > minus_di:
                                ind_value = min(1, adx_val / 100)
                            elif minus_di > plus_di:
                                ind_value = max(-1, -adx_val / 100)
                            else:
                                ind_value = 0
                        # Bollinger Bands: {"upper": X, "middle": Y, "lower": Z, "position": P}
                        elif 'position' in ind_data:
                            ind_value = ind_data.get('position', 0) * 2 - 1  # Normalize 0-1 to -1 to 1
                        # Stoch RSI: {"k": X, "d": Y}
                        elif 'k' in ind_data:
                            ind_value = (ind_data.get('k', 50) - 50) / 50  # Normalize 0-100 to -1 to 1
                        else:
                            # Generic: try to find first numeric value
                            for k, v in ind_data.items():
                                if isinstance(v, (int, float)):
                                    ind_value = v
                                    break
                    elif isinstance(ind_data, (int, float)):
                        ind_value = ind_data
                    
                    # Normalize values to -1 to 1 range
                    if ind_value is not None:
                        # For RSI-like (0-100), normalize
                        if 0 <= ind_value <= 100:
                            if ind_value > 70:
                                ind_value = -((ind_value - 70) / 30)
                            elif ind_value < 30:
                                ind_value = ((30 - ind_value) / 30)
                            else:
                                ind_value = 0
                        
                        weighted_score += ind_value * weight
                        total_weight += weight
                        components[ind_name] = ind_value
            
            # Normalize by total weight
            if total_weight > 0:
                final_score = weighted_score / total_weight
            else:
                final_score = 0
            
            # Apply min_score threshold
            if abs(final_score) < self.min_score:
                return {
                    "score": 0,
                    "direction": "neutral",
                    "components": components,
                    "confidence": 0,
                    "take_profit": 0,
                    "stop_loss": 0,
                    "risk_reward_ratio": 0,
                    "technical_score": 0,
                }
            
            # Determine direction based on score
            if final_score > 0:
                direction = "buy"
            elif final_score < 0:
                direction = "sell"
            else:
                direction = "neutral"
            
            # Check trade direction filter
            if self.trade_direction == "long_only" and direction == "sell":
                return {
                    "score": 0,
                    "direction": "neutral",
                    "components": components,
                    "confidence": 0,
                    "take_profit": 0,
                    "stop_loss": 0,
                    "risk_reward_ratio": 0,
                    "technical_score": 0,
                }
            elif self.trade_direction == "short_only" and direction == "buy":
                return {
                    "score": 0,
                    "direction": "neutral",
                    "components": components,
                    "confidence": 0,
                    "take_profit": 0,
                    "stop_loss": 0,
                    "risk_reward_ratio": 0,
                    "technical_score": 0,
                }
            
            # Calculate TP/SL prices
            if direction != "neutral":
                tp_value = abs(self.tp_value) / 100
                sl_value = abs(self.sl_value) / 100
                
                if direction == "buy":
                    take_profit = current_price * (1 + tp_value)
                    stop_loss = current_price * (1 - sl_value)
                else:
                    take_profit = current_price * (1 - tp_value)
                    stop_loss = current_price * (1 + sl_value)
                
                risk_reward = tp_value / sl_value if sl_value > 0 else 0
            else:
                take_profit = 0
                stop_loss = 0
                risk_reward = 0
            
            return {
                "score": final_score,
                "direction": direction,
                "components": components,
                "confidence": abs(final_score),
                "take_profit": take_profit,
                "stop_loss": stop_loss,
                "risk_reward_ratio": risk_reward,
                "technical_score": abs(final_score),
            }
            
        except Exception as e:
            # Return neutral on any error
            return {
                "score": 0,
                "direction": "neutral",
                "components": {},
                "confidence": 0,
                "take_profit": 0,
                "stop_loss": 0,
                "risk_reward_ratio": 0,
                "technical_score": 0,
            }
    
    def to_config(self, used_indicators=None):
        """Convert to config dict for API response"""
        # Build indicators list from score config
        indicators = []
        score_config = self.config.get('score', {})
        for ind in score_config.get('indicators', []):
            ind_name = ind.get('name', '')
            indicators.append({
                "id": ind_name,
                "enabled": ind_name.upper() in [k.upper() for k in (used_indicators or [])],
                "settings": {}
            })
        
        return {
            "id": self.id,
            "display_name": self.name,
            "used_indicators": list(self.indicator_weights.keys()),
            "default_indicators": indicators,
        }


# Load strategies: try DB first, then fall back to JSON
def load_strategies_from_db_or_json():
    """Load strategies from database first, then fall back to JSON file."""
    loaded_count = 0
    
    # Try to load from database first
    try:
        from database import list_strategies_db, get_strategy_from_db
        
        db_strategies = list_strategies_db()
        if db_strategies:
            for config in db_strategies:
                strat_id = config.get("id")
                if strat_id:
                    wrapper = JSONStrategyWrapper(config, strat_id)
                    STRATEGIES[strat_id] = wrapper
                    loaded_count += 1
            print(f"Loaded {loaded_count} strategies from database")
            return loaded_count
    except Exception as e:
        print(f"Could not load strategies from DB: {e}")
    
    # Fall back to JSON file
    try:
        from strategy.config_loader import load_strategies_from_file
        from pathlib import Path
        
        # Try to load from multiple possible locations
        json_path = Path("strategy/strategies.json")
        if not json_path.exists():
            json_path = Path("../strategy/strategies.json")
        if not json_path.exists():
            json_path = Path(__file__).parent / "strategy" / "strategies.json"
        
        if json_path.exists():
            manager = load_strategies_from_file(str(json_path))
            for strat_id, strat in manager.strategies.items():
                # Create wrapper for backtest compatibility
                wrapper = JSONStrategyWrapper(strat.config, strat_id)
                STRATEGIES[strat_id] = wrapper
                loaded_count += 1
            print(f"Loaded {loaded_count} strategies from JSON file")
    except Exception as e:
        print(f"Warning: Could not load JSON strategies: {e}")
    
    return loaded_count


# Initial load
load_strategies_from_db_or_json()


def reload_strategies():
    """Reload strategies from DB (for cron job or manual refresh)."""
    global STRATEGIES
    STRATEGIES = {}  # Clear existing
    STRATEGIES["adaptive_regime"] = AdaptiveRegimeStrategy()
    STRATEGIES["mms"] = MMSStrategy()
    load_strategies_from_db_or_json()
    print(f"Reloaded strategies. Total: {len(STRATEGIES)}")
