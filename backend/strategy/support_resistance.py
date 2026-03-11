"""
Support/Resistance Detection Module
Finds pivot points and key price levels for TP/SL placement
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class PivotPoint:
    level: float
    type: str  # 'R3', 'R2', 'R1', 'PP', 'S1', 'S2', 'S3'
    strength: float  # 0-1, based on how many times price touched


def calculate_pivot_points(high: float, low: float, close: float) -> Dict[str, float]:
    """
    Calculate classic pivot points (Woodie)
    
    PP = (High + Low + Close) / 3
    R1 = 2*PP - Low
    S1 = 2*PP - High
    R2 = PP + (High - Low)
    S2 = PP - (High - Low)
    R3 = High + 2*(PP - Low)
    S3 = Low - 2*(High - PP)
    """
    pp = (high + low + close) / 3
    
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    r3 = high + 2 * (pp - low)
    s3 = low - 2 * (high - pp)
    
    return {
        'R3': r3,
        'R2': r2,
        'R1': r1,
        'PP': pp,
        'S1': s1,
        'S2': s2,
        'S3': s3
    }


def find_nearest_support(candles: List[dict], entry_price: float, lookback: int = 50) -> Optional[float]:
    """
    Find nearest support level below entry price
    
    Support = local minimum where price previously bounced up
    """
    if not candles:
        return None
    
    supports = []
    for i in range(lookback, len(candles) - 1):
        # Support: candle is local minimum
        if (candles[i]['low'] < candles[i-1]['low'] and 
            candles[i]['low'] < candles[i+1]['low'] and
            candles[i]['low'] < entry_price):  # Must be below entry
            
            # Strength = how many times price tested this level
            strength = sum(1 for c in candles[max(0, i-5):i+5] 
                         if abs(c['low'] - candles[i]['low']) / candles[i]['low'] < 0.01)
            
            supports.append((candles[i]['low'], strength))
    
    if not supports:
        # Fallback: use recent low
        recent_low = min(c['low'] for c in candles[-lookback:])
        if recent_low < entry_price:
            return recent_low
        return None
    
    # Return strongest support (most touches)
    supports.sort(key=lambda x: x[1], reverse=True)
    return supports[0][0]


def find_nearest_resistance(candles: List[dict], entry_price: float, lookback: int = 50) -> Optional[float]:
    """
    Find nearest resistance level above entry price
    
    Resistance = local maximum where price previously bounced down
    """
    if not candles:
        return None
    
    resistances = []
    for i in range(lookback, len(candles) - 1):
        # Resistance: candle is local maximum
        if (candles[i]['high'] > candles[i-1]['high'] and 
            candles[i]['high'] > candles[i+1]['high'] and
            candles[i]['high'] > entry_price):  # Must be above entry
            
            strength = sum(1 for c in candles[max(0, i-5):i+5] 
                         if abs(c['high'] - candles[i]['high']) / candles[i]['high'] < 0.01)
            
            resistances.append((candles[i]['high'], strength))
    
    if not resistances:
        recent_high = max(c['high'] for c in candles[-lookback:])
        if recent_high > entry_price:
            return recent_high
        return None
    
    resistances.sort(key=lambda x: x[1], reverse=True)
    return resistances[0][0]


def calculate_atr(candles: List[dict], period: int = 14) -> float:
    """Calculate Average True Range"""
    if len(candles) < period + 1:
        return 0
    
    trs = []
    for i in range(1, min(period + 1, len(candles))):
        high = candles[-i]['high']
        low = candles[-i]['low']
        prev_close = candles[-i-1]['close']
        
        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)
    
    return sum(trs) / len(trs) if trs else 0


def calculate_optimal_tp_sl(
    candles: List[dict],
    entry_price: float,
    direction: str,
    base_tp_percent: float = 2.5,
    base_sl_percent: float = 1.5,
    atr_multiplier: float = 2.0,
    min_rr_ratio: float = 1.5
) -> Dict[str, float]:
    """
    Calculate optimal TP/SL combining multiple factors:
    1. Base percentage from strategy
    2. ATR-based (volatility)
    3. Support/Resistance levels
    
    Returns:
        {
            'take_profit': float,
            'stop_loss': float,
            'tp_method': str,
            'sl_method': str,
            'rr_ratio': float,
            'levels': {...}  # debug info
        }
    """
    if not candles:
        # Fallback to simple percentage
        return {
            'take_profit': entry_price * (1 + base_tp_percent/100) if direction == 'buy' 
                         else entry_price * (1 - base_tp_percent/100),
            'stop_loss': entry_price * (1 - base_sl_percent/100) if direction == 'buy'
                        else entry_price * (1 + base_sl_percent/100),
            'tp_method': 'fallback_percent',
            'sl_method': 'fallback_percent',
            'rr_ratio': base_tp_percent / base_sl_percent,
            'levels': {}
        }
    
    atr = calculate_atr(candles)
    atr_percent = (atr / entry_price) * 100 if entry_price > 0 else 0
    
    # Method 1: Percentage-based
    if direction == 'buy':
        tp_percent = base_tp_percent
        sl_percent = base_sl_percent
        
        # Method 2: ATR-based
        atr_tp = atr_percent * 2  # TP at 2x ATR
        atr_sl = atr_percent * atr_multiplier
        
        # Method 3: S/R levels
        resistance = find_nearest_resistance(candles, entry_price)
        support = find_nearest_support(candles, entry_price)
        
        # Calculate TPs
        tp_percentages = [
            ('base', base_tp_percent),
            ('atr', atr_tp)
        ]
        
        if resistance and resistance > entry_price:
            resistance_tp_percent = ((resistance - entry_price) / entry_price) * 100
            tp_percentages.append(('resistance', resistance_tp_percent))
        
        # Use weighted average: base 40%, ATR 30%, S/R 30%
        tp_final = (base_tp_percent * 0.4 + atr_tp * 0.3 + 
                   (resistance_tp_percent * 0.3 if resistance else base_tp_percent * 0.3))
        
        # SL: use support level or ATR
        if support and support < entry_price:
            sl_percent_from_support = ((entry_price - support) / entry_price) * 100
            sl_percent = min(sl_percent, sl_percent_from_support * 1.1)  # 10% margin above support
        else:
            sl_percent = min(sl_percent, atr_sl)
        
    else:  # sell/short
        tp_percent = base_tp_percent
        sl_percent = base_sl_percent
        
        atr_tp = atr_percent * 2
        atr_sl = atr_percent * atr_multiplier
        
        support = find_nearest_support(candles, entry_price)
        resistance = find_nearest_resistance(candles, entry_price)
        
        tp_percentages = [
            ('base', base_tp_percent),
            ('atr', atr_tp)
        ]
        
        if support and support < entry_price:
            support_tp_percent = ((entry_price - support) / entry_price) * 100
            tp_percentages.append(('support', support_tp_percent))
        
        tp_final = (base_tp_percent * 0.4 + atr_tp * 0.3 +
                   (support_tp_percent * 0.3 if support else base_tp_percent * 0.3))
        
        if resistance and resistance > entry_price:
            sl_percent_from_resistance = ((resistance - entry_price) / entry_price) * 100
            sl_percent = min(sl_percent, sl_percent_from_resistance * 1.1)
        else:
            sl_percent = min(sl_percent, atr_sl)
    
    # Ensure minimum R:R ratio
    if sl_percent > 0:
        actual_rr = tp_percent / sl_percent
        if actual_rr < min_rr_ratio:
            sl_percent = tp_percent / min_rr_ratio
    
    # Calculate final prices
    if direction == 'buy':
        tp_price = entry_price * (1 + tp_final / 100)
        sl_price = entry_price * (1 - sl_percent / 100)
    else:
        tp_price = entry_price * (1 - tp_final / 100)
        sl_price = entry_price * (1 + sl_percent / 100)
    
    return {
        'take_profit': tp_price,
        'stop_loss': sl_price,
        'tp_method': 'adaptive',
        'sl_method': 'adaptive',
        'rr_ratio': tp_final / sl_percent if sl_percent > 0 else 0,
        'levels': {
            'atr_percent': atr_percent,
            'nearest_support': support,
            'nearest_resistance': resistance,
            'base_tp': base_tp_percent,
            'atr_tp': atr_tp,
            'final_tp_percent': tp_final,
            'final_sl_percent': sl_percent
        }
    }


# Test
if __name__ == "__main__":
    # Sample candles
    candles = [
        {'high': 5100, 'low': 5050, 'close': 5080},
        {'high': 5120, 'low': 5070, 'close': 5100},
        {'high': 5150, 'low': 5090, 'close': 5120},
        {'high': 5140, 'low': 5080, 'close': 5100},
        {'high': 5180, 'low': 5100, 'close': 5150},
    ] * 20  # Repeat for more data
    
    result = calculate_optimal_tp_sl(candles, 5100, 'buy', 2.5, 1.5)
    print("TP:", result['take_profit'])
    print("SL:", result['stop_loss'])
    print("Method:", result['tp_method'])
    print("RR:", result['rr_ratio'])
    print("Levels:", result['levels'])
