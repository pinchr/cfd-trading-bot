"""Signal generation service - extracted from main.py"""
import asyncio
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum

# Import from main.py or other modules
from models import Signal, SignalDirection
from indicators import TechnicalIndicators
from timeframes import TimeFrame
from services.market_data import get_cached_quote, get_cached_candles
from services.strategy_manager import get_strategy_manager, analyze_with_new_strategy
from services.state import get_symbol_strategy as _get_symbol_strategy
import database as db

# Settings
from settings import get_all_settings

class SignalDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"
    NEUTRAL = "neutral"


@dataclass
class Component:
    name: str
    value: float
    weight: float
    direction: SignalDirection


def calculate_signal_score(indicators: dict, symbol: str = "") -> Tuple[float, List[Component]]:
    """
    Multi-factor signal scoring with regime-adaptive weighting.
    Uses: RSI (corrected), MACD, Bollinger Bands, SMA trend, ADX trend strength,
    StochRSI for timing, and volume confirmation.

    In TRENDING markets (ADX > 25): momentum/trend components get higher weight.
    In RANGING markets (ADX < 20): mean-reversion components (BB, RSI) get higher weight.
    """
    components = []
    score = 0.0
    
    if not indicators:
        return 0.0, []
    
    # Determine market regime
    adx = indicators.get("adx", 0)
    is_trending = adx > 25
    is_ranging = adx < 20
    
    # Weights based on regime
    if is_trending:
        trend_weight = 0.5
        mean_rev_weight = 0.2
    elif is_ranging:
        trend_weight = 0.2
        mean_rev_weight = 0.5
    else:
        trend_weight = 0.35
        mean_rev_weight = 0.35
    
    # RSI (mean-reversion in ranging, reduced in trending)
    rsi = indicators.get("rsi")
    if rsi:
        rsi_val = rsi.get("value", 50)
        if rsi_val < 30:
            rsi_score = 0.3 * mean_rev_weight
            direction = SignalDirection.BUY
        elif rsi_val > 70:
            rsi_score = -0.3 * mean_rev_weight
            direction = SignalDirection.SELL
        else:
            rsi_score = 0
            direction = SignalDirection.NEUTRAL
        score += rsi_score
        components.append(Component("RSI", rsi_val, rsi_score * 3.33, direction))
    
    # MACD (momentum - stronger in trending)
    macd = indicators.get("macd")
    if macd:
        macd_val = macd.get("value", 0)
        signal_val = macd.get("signal", 0)
        if macd_val > signal_val:
            macd_score = 0.25 * trend_weight
            direction = SignalDirection.BUY
        elif macd_val < signal_val:
            macd_score = -0.25 * trend_weight
            direction = SignalDirection.SELL
        else:
            macd_score = 0
            direction = SignalDirection.NEUTRAL
        score += macd_score
        components.append(Component("MACD", macd_val - signal_val, macd_score * 4, direction))
    
    # Bollinger Bands (mean-reversion)
    bb = indicators.get("bb_position")
    if bb is not None:
        if bb < 20:
            bb_score = 0.2 * mean_rev_weight
            direction = SignalDirection.BUY
        elif bb > 80:
            bb_score = -0.2 * mean_rev_weight
            direction = SignalDirection.SELL
        else:
            bb_score = 0
            direction = SignalDirection.NEUTRAL
        score += bb_score
        components.append(Component("BB", bb, bb_score * 5, direction))
    
    # SMA Trend
    sma = indicators.get("sma_trend")
    if sma:
        if sma > 0:
            sma_score = 0.15 * trend_weight
            direction = SignalDirection.BUY
        elif sma < 0:
            sma_score = -0.15 * trend_weight
            direction = SignalDirection.SELL
        else:
            sma_score = 0
            direction = SignalDirection.NEUTRAL
        score += sma_score
        components.append(Component("SMA", sma, sma_score * 6.67, direction))
    
    # ADX (trend strength - filter signals in ranging)
    if adx:
        if adx < 20:
            # Weak trend - reduce confidence
            score *= 0.5
        components.append(Component("ADX", adx, 0.1, SignalDirection.NEUTRAL))
    
    # StochRSI (timing)
    stoch = indicators.get("stoch_rsi")
    if stoch:
        stoch_val = stoch.get("value", 50)
        if stoch_val < 20:
            stoch_score = 0.15
            direction = SignalDirection.BUY
        elif stoch_val > 80:
            stoch_score = -0.15
            direction = SignalDirection.SELL
        else:
            stoch_score = 0
            direction = SignalDirection.NEUTRAL
        score += stoch_score
        components.append(Component("StochRSI", stoch_val, stoch_score * 6.67, direction))
    
    # Clamp score
    score = max(-1.0, min(1.0, score))
    
    return score, components


def get_signal_direction(score: float, min_score: float = 0.15) -> SignalDirection:
    """Convert score to signal direction."""
    if score >= min_score:
        return SignalDirection.BUY
    elif score <= -min_score:
        return SignalDirection.SELL
    return SignalDirection.NEUTRAL


def calculate_confidence(score: float, components: List[Component]) -> float:
    """Calculate signal confidence based on score and component agreement."""
    if not components:
        return 0.0
    
    # Base confidence from absolute score
    base_confidence = abs(score) * 100
    
    # Bonus for component agreement
    directions = [c.direction for c in components if c.direction != SignalDirection.NEUTRAL]
    if len(directions) > 0:
        buy_count = sum(1 for d in directions if d == SignalDirection.BUY)
        sell_count = sum(1 for d in directions if d == SignalDirection.SELL)
        if score > 0:
            agreement = buy_count / len(directions)
        else:
            agreement = sell_count / len(directions)
        agreement_bonus = agreement * 20
    else:
        agreement_bonus = 0
    
    return min(100, base_confidence + agreement_bonus)


def calculate_position_size(symbol: str, entry_price: float, stop_loss: float, account_balance: float = 3000.0) -> float:
    """Calculate position size based on risk management."""
    if not entry_price or not stop_loss or entry_price == stop_loss:
        return 0.01
    
    risk_percent = 0.02  # 2% risk per trade
    risk_amount = account_balance * risk_percent
    
    price_risk = abs(entry_price - stop_loss)
    if price_risk == 0:
        return 0.01
    
    # For commodities (XAU, XAG), lot size is different
    if symbol in ("XAU", "XAG"):
        # Gold: $100 per 1.0 lot per $1 move
        # Silver: $5 per 1.0 lot per $1 move
        multiplier = 100 if symbol == "XAG" else 100
        position_size = risk_amount / (price_risk * multiplier)
    else:
        # Indices/crypto: simpler calculation
        position_size = risk_amount / price_risk
    
    return max(0.01, min(position_size, 10.0))  # Clamp between 0.01 and 10 lots
