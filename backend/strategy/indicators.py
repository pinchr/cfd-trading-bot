"""Indicators module - Technical indicators with normalized values"""

from collections import deque
from typing import Optional, Deque
import math
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from indicators import TechnicalIndicators


class Indicator:
    """Base class for all indicators"""
    
    def __init__(self, period: int = 14, source: str = "close"):
        self.period = period
        self.source = source
        self.values: Deque = deque(maxlen=period * 2)
    
    def update(self, candle: dict) -> None:
        """Update indicator with new candle"""
        raise NotImplementedError
    
    def value(self) -> Optional[float]:
        """Get current indicator value"""
        raise NotImplementedError
    
    def normalized_value(self, range_min: float = -1.0, range_max: float = 1.0) -> float:
        """Normalize indicator value to specified range"""
        val = self.value()
        if val is None:
            return 0.0
        
        min_val, max_val = self._get_range()
        
        # Normalize: map from [min_val, max_val] to [range_min, range_max]
        # Use midpoint as zero point
        mid = (min_val + max_val) / 2
        half_range = (max_val - min_val) / 2
        
        # Normalize to -1 to 1 first
        if half_range > 0:
            normalized = (val - mid) / half_range
        else:
            normalized = 0.0
        
        # Scale to desired range
        return normalized * ((range_max - range_min) / 2)
    
    def _get_range(self) -> tuple:
        """Get min/max range for normalization"""
        raise NotImplementedError


class RsiIndicator(Indicator):
    """Relative Strength Index"""
    
    def __init__(self, period: int = 14, source: str = "close"):
        super().__init__(period, source)
        self.gains = deque(maxlen=period)
        self.losses = deque(maxlen=period)
        self.avg_gain = None
        self.avg_loss = None
    
    def update(self, candle: dict) -> None:
        close = candle.get(self.source, candle.get('close'))
        if len(self.values) > 0:
            prev_close = self.values[-1]
            change = close - prev_close
            gain = max(0, change)
            loss = max(0, -change)
            
            self.gains.append(gain)
            self.losses.append(loss)
            
            if len(self.gains) >= self.period:
                if self.avg_gain is None:
                    self.avg_gain = sum(self.gains) / self.period
                    self.avg_loss = sum(self.losses) / self.period
                else:
                    self.avg_gain = (self.avg_gain * (self.period - 1) + gain) / self.period
                    self.avg_loss = (self.avg_loss * (self.period - 1) + loss) / self.period
        
        self.values.append(close)
    
    def value(self) -> Optional[float]:
        if self.avg_gain is None or self.avg_loss is None:
            return None
        if self.avg_loss == 0:
            return 100.0
        rs = self.avg_gain / self.avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
    
    def _get_range(self) -> tuple:
        return (0.0, 100.0)


class MacdIndicator(Indicator):
    """MACD - Moving Average Convergence Divergence"""
    
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9, source: str = "close"):
        super().__init__(slow, source)  # Use slow period for buffer size (needs slow * 2 values)
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.ema_fast: Optional[float] = None
        self.ema_slow: Optional[float] = None
        self.macd_line: Deque = deque(maxlen=signal * 2)
        self.signal_line: Optional[float] = None
    
    def _ema(self, values: list, period: int, prev_ema: Optional[float] = None) -> float:
        if len(values) < period:
            return prev_ema or sum(values) / len(values) if values else 0
        multiplier = 2 / (period + 1)
        if prev_ema is None:
            return sum(values[:period]) / period
        return (values[-1] - prev_ema) * multiplier + prev_ema
    
    def update(self, candle: dict) -> None:
        close = candle.get(self.source, candle.get('close'))
        self.values.append(close)
        
        if len(self.values) >= self.slow:
            closes = list(self.values)
            self.ema_fast = self._ema(closes, self.fast, self.ema_fast)
            self.ema_slow = self._ema(closes, self.slow, self.ema_slow)
            
            if self.ema_fast and self.ema_slow:
                macd = self.ema_fast - self.ema_slow
                self.macd_line.append(macd)
                
                if len(self.macd_line) >= self.signal:
                    self.signal_line = self._ema(list(self.macd_line), self.signal, self.signal_line)
    
    def value(self) -> Optional[float]:
        if self.ema_fast and self.ema_slow and self.signal_line:
            return self.ema_fast - self.ema_slow - self.signal_line
        return None
    
    def _get_range(self) -> tuple:
        return (-2.0, 2.0)


class MomentumIndicator(Indicator):
    """Momentum - rate of change"""
    
    def __init__(self, lookback: int = 10, source: str = "close"):
        super().__init__(lookback, source)
        self.lookback = lookback
    
    def update(self, candle: dict) -> None:
        close = candle.get(self.source, candle.get('close'))
        self.values.append(close)
    
    def value(self) -> Optional[float]:
        if len(self.values) < self.lookback + 1:
            return None
        current = self.values[-1]
        past = self.values[-(self.lookback + 1)]
        if past == 0:
            return 0
        return ((current - past) / past) * 100
    
    def _get_range(self) -> tuple:
        return (-5.0, 5.0)


class AdxIndicator(Indicator):
    """Average Directional Index - trend strength"""
    
    def __init__(self, period: int = 14):
        super().__init__(period)
        self.period = period
        self.plus_dm: Deque = deque(maxlen=period * 2)
        self.minus_dm: Deque = deque(maxlen=period * 2)
        self.tr: Deque = deque(maxlen=period * 2)
        self.plus_di: Optional[float] = None
        self.minus_di: Optional[float] = None
        self.adx: Optional[float] = None
    
    def update(self, candle: dict) -> None:
        high = candle.get('high')
        low = candle.get('low')
        close = candle.get('close')
        
        if len(self.values) > 0:
            prev_close = self.values[-1]
            
            # True Range
            tr1 = high - low
            tr2 = abs(high - prev_close)
            tr3 = abs(low - prev_close)
            tr = max(tr1, tr2, tr3)
            self.tr.append(tr)
            
            # Directional Movement
            plus_dm = max(0, high - prev_close)
            minus_dm = max(0, prev_close - low)
            
            self.plus_dm.append(plus_dm)
            self.minus_dm.append(minus_dm)
            
            if len(self.tr) >= self.period:
                avg_tr = sum(list(self.tr)[-self.period:]) / self.period
                avg_plus_dm = sum(list(self.plus_dm)[-self.period:]) / self.period
                avg_minus_dm = sum(list(self.minus_dm)[-self.period:]) / self.period
                
                if avg_tr > 0:
                    self.plus_di = (avg_plus_dm / avg_tr) * 100
                    self.minus_di = (avg_minus_dm / avg_tr) * 100
                    
                    di_sum = self.plus_di + self.minus_di
                    if di_sum > 0:
                        dx = abs(self.plus_di - self.minus_di) / di_sum * 100
                        self.adx = dx
        
        self.values.append(close)
    
    def value(self) -> Optional[float]:
        return self.adx
    
    def _get_range(self) -> tuple:
        return (0.0, 100.0)


class DivergenceIndicator(Indicator):
    """RSI Divergence indicator - detects bullish/bearish divergence between price and RSI"""
    
    def __init__(self, lookback: int = 20, source: str = "close"):
        super().__init__(lookback, source)
        self.lookback = lookback
        self.candles_history = []
    
    def update(self, candle: dict) -> None:
        self.candles_history.append(candle)
        if len(self.candles_history) > self.lookback * 2:
            self.candles_history.pop(0)
        self.values.append(candle.get('close'))
    
    def value(self) -> Optional[float]:
        if len(self.candles_history) < self.lookback:
            return None
        try:
            result = TechnicalIndicators.divergence(self.candles_history, self.lookback)
            if result and isinstance(result, dict):
                return result.get('bias', 0.0)
        except Exception:
            pass
        return 0.0
    
    def _get_range(self) -> tuple:
        return (-1.0, 1.0)


class HTFCandleIndicator(Indicator):
    """HTF Candle Pattern indicator - detects candlestick patterns for trend reversals"""
    
    def __init__(self, min_strength: float = 0.3, source: str = "close"):
        super().__init__(1, source)
        self.min_strength = min_strength
        self.candles_history = []
    
    def update(self, candle: dict) -> None:
        self.candles_history.append(candle)
        if len(self.candles_history) > 50:
            self.candles_history.pop(0)
        self.values.append(candle.get('close'))
    
    def value(self) -> Optional[float]:
        if len(self.candles_history) < 10:
            return None
        try:
            result = TechnicalIndicators.candlestick_patterns(self.candles_history)
            if result and isinstance(result, dict):
                patterns = result.get('patterns', [])
                # Filter by min_strength
                strong_patterns = [p for p in patterns if p.get('strength', 0) >= self.min_strength]
                if strong_patterns:
                    # Return bias of strongest pattern
                    return strong_patterns[0].get('bias', 0.0)
        except Exception:
            pass
        return 0.0
    
    def _get_range(self) -> tuple:
        return (-1.0, 1.0)


# Factory function to create indicators
def create_indicator(name: str, **kwargs) -> Indicator:
    """Create indicator by name"""
    indicators = {
        'RSI': RsiIndicator,
        'MACD': MacdIndicator,
        'MOMENTUM': MomentumIndicator,
        'ADX': AdxIndicator,
        'DIVERGENCE': DivergenceIndicator,
        'HTF_CANDLE': HTFCandleIndicator,
    }
    
    if name.upper() not in indicators:
        raise ValueError(f"Unknown indicator: {name}")
    
    return indicators[name.upper()](**kwargs)
