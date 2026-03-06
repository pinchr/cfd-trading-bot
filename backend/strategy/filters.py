"""Filters module - Entry filters for trading strategies"""

from collections import deque
from typing import Optional, Dict, Callable


class VolumeFilter:
    """Filter trades based on volume"""
    
    def __init__(self, config: dict):
        self.enabled = config.get('enabled', True)
        self.lookback_bars = config.get('lookback_bars', 20)
        self.min_ratio_to_average = config.get('min_ratio_to_average', 0.75)
        
        self.volume_history: deque = deque(maxlen=self.lookback_bars)
    
    def check(self, candle: dict) -> bool:
        """
        Check if volume filter passes
        
        Args:
            candle: Current candle with volume
        
        Returns:
            True if filter passes or disabled
        """
        if not self.enabled:
            return True
        
        volume = candle.get('volume', 0)
        if volume is None or volume == 0:
            return False
        
        self.volume_history.append(volume)
        
        if len(self.volume_history) < self.lookback_bars:
            # Not enough data yet - pass filter
            return True
        
        avg_volume = sum(self.volume_history) / len(self.volume_history)
        ratio = volume / avg_volume if avg_volume > 0 else 0
        
        return ratio >= self.min_ratio_to_average
    
    def reset(self) -> None:
        """Reset volume history"""
        self.volume_history.clear()


class PositionAlreadyOpenFilter:
    """Filter if position already open on symbol"""
    
    def __init__(self, config: dict, position_service: Callable = None):
        self.enabled = config.get('enabled', True)
        self.position_service = position_service
    
    def check(self, symbol: str) -> bool:
        """
        Check if position already open
        
        Args:
            symbol: Trading symbol
        
        Returns:
            True if no position or filter disabled
        """
        if not self.enabled:
            return True
        
        if self.position_service is None:
            return True  # Can't check, allow
        
        # Check if position exists
        open_positions = self.position_service.get_open_positions(symbol)
        return len(open_positions) == 0


class SymbolEnabledFilter:
    """Filter based on symbol trade enable flag"""
    
    def __init__(self, config: dict, settings_service: Callable = None):
        self.enabled = config.get('enabled', True)
        self.key_pattern = config.get('key_pattern', 'TRADE_ENABLED_{SYMBOL}')
        self.settings_service = settings_service
    
    def check(self, symbol: str) -> bool:
        """
        Check if symbol trading is enabled
        
        Args:
            symbol: Trading symbol
        
        Returns:
            True if enabled or filter disabled
        """
        if not self.enabled:
            return True
        
        if self.settings_service is None:
            return True  # Can't check, allow
        
        key = self.key_pattern.replace('{SYMBOL}', symbol.upper())
        enabled = self.settings_service.get(key, True)
        
        return enabled


class HtfTrendFilter:
    """Filter based on higher timeframe trend"""
    
    def __init__(self, config: dict, htf_indicator=None):
        self.enabled = config.get('enabled', True)
        self.indicator_name = config.get('indicator', 'RSI')
        self.htf_timeframe = config.get('htf_timeframe', '30m')
        self.source = config.get('source', 'close')
        self.use_closed_candles_only = config.get('use_closed_candles_only', True)
        
        # Long condition
        long_cond = config.get('long_condition', {})
        self.long_operator = long_cond.get('operator', '>')
        self.long_value = long_cond.get('value', 50)
        
        # Short condition (not used for long_only)
        short_cond = config.get('short_condition')
        self.short_operator = short_cond.get('operator') if short_cond else None
        self.short_value = short_cond.get('value') if short_cond else None
        
        self.htf_indicator = htf_indicator
    
    def check(self, direction: str = 'long') -> bool:
        """
        Check if HTF trend aligns with direction
        
        Args:
            direction: 'long' or 'short'
        
        Returns:
            True if trend aligns or filter disabled
        """
        if not self.enabled:
            return True
        
        if self.htf_indicator is None:
            return True  # Can't check, allow
        
        value = self.htf_indicator.value()
        if value is None:
            return True  # No data, allow
        
        if direction == 'long':
            return self._check_condition(value, self.long_operator, self.long_value)
        else:  # short
            if self.short_operator is None:
                return True
            return self._check_condition(value, self.short_operator, self.short_value)
    
    def _check_condition(self, value: float, operator: str, threshold: float) -> bool:
        """Check if value meets condition"""
        if operator == '>':
            return value > threshold
        elif operator == '<':
            return value < threshold
        elif operator == '>=':
            return value >= threshold
        elif operator == '<=':
            return value <= threshold
        elif operator == '==':
            return value == threshold
        return True


class VolatilityFilter:
    """Filter trades based on volatility (ATR percent)"""
    
    def __init__(self, config: dict):
        self.enabled = config.get('enabled', True)
        self.max_atr_percent = config.get('max_atr_percent', 3.0)
    
    def check(self, candle: dict, atr_percent: float = None) -> bool:
        """
        Check if volatility filter passes
        
        Args:
            candle: Current candle (for close price)
            atr_percent: ATR percent value (calculated externally)
        
        Returns:
            True if filter passes or disabled
        """
        if not self.enabled:
            return True
        
        if atr_percent is None:
            return True  # Can't check, allow
        
        return atr_percent <= self.max_atr_percent


class VixFilter:
    """Filter trades based on VIX level"""
    
    def __init__(self, config: dict):
        self.enabled = config.get('enabled', True)
        self.max_vix = config.get('max_vix', 30)
    
    def check(self, vix_value: float = None) -> bool:
        """
        Check if VIX filter passes
        
        Args:
            vix_value: Current VIX value
        
        Returns:
            True if filter passes or disabled
        """
        if not self.enabled:
            return True
        
        if vix_value is None:
            return True  # Can't check, allow
        
        return vix_value <= self.max_vix


class FilterChain:
    """Chain multiple filters together"""
    
    def __init__(self, config: dict, services: dict = None):
        self.config = config
        self.services = services or {}
        
        # Initialize filters
        self.volume_filter = VolumeFilter(config.get('volume', {}))
        self.position_filter = PositionAlreadyOpenFilter(
            config.get('position_already_open', {}),
            services.get('position_service')
        )
        self.symbol_filter = SymbolEnabledFilter(
            config.get('symbol_enabled_flag', {}),
            services.get('settings_service')
        )
        self.htf_filter = HtfTrendFilter(
            config.get('htf_trend', {}),
            services.get('htf_indicator')
        )
        # New filters
        self.volatility_filter = VolatilityFilter(config.get('volatility', {}))
        self.vix_filter = VixFilter(config.get('vix', {}))
    
    def check_all(
        self, 
        candle: dict = None, 
        symbol: str = None, 
        direction: str = 'long',
        atr_percent: float = None,
        vix_value: float = None
    ) -> tuple[bool, list]:
        """
        Check all filters
        
        Args:
            candle: Current candle
            symbol: Trading symbol
            direction: 'long' or 'short'
            atr_percent: ATR percent for volatility check
            vix_value: Current VIX value
        
        Returns:
            (all_passed, list_of_failed_filters)
        """
        failed = []
        
        # Volume filter
        if candle and not self.volume_filter.check(candle):
            failed.append('volume')
        
        # Position already open
        if symbol and not self.position_filter.check(symbol):
            failed.append('position_already_open')
        
        # Symbol enabled
        if symbol and not self.symbol_filter.check(symbol):
            failed.append('symbol_enabled_flag')
        
        # HTF trend
        if not self.htf_filter.check(direction):
            failed.append('htf_trend')
        
        # Volatility filter
        if not self.volatility_filter.check(candle, atr_percent):
            failed.append('volatility')
        
        # VIX filter
        if not self.vix_filter.check(vix_value):
            failed.append('vix')
        
        return len(failed) == 0, failed
    
    def reset(self) -> None:
        """Reset all filters"""
        self.volume_filter.reset()
