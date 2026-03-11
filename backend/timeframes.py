"""
Standardized timeframe constants.
Use these instead of hardcoded strings like "5", "60", "1h".
"""

from enum import Enum

class TimeFrame(str, Enum):
    """Standard timeframe values used across the system."""
    
    # Minutes - readable format like frontend
    M1 = "1m"     # 1 minute
    M5 = "5m"     # 5 minutes
    M15 = "15m"   # 15 minutes
    M30 = "30m"   # 30 minutes
    M60 = "1h"    # 1 hour (60 minutes)
    
    # Higher timeframes
    H4 = "4h"     # 4 hours
    D1 = "1d"     # Daily
    W1 = "1w"     # Weekly
    
    @property
    def minutes(self) -> int:
        """Convert to minutes for internal use."""
        mapping = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}
        return mapping.get(self.value, 60)
    
    @property
    def yahoo_interval(self) -> str:
        """Yahoo Finance interval format."""
        mapping = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1wk"}
        return mapping.get(self.value, "1h")
    
    @property
    def db_resolution(self) -> str:
        """Database resolution format (numbers for compatibility)."""
        mapping = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "1h": "60", "4h": "240", "1d": "D", "1w": "W"}
        return mapping.get(self.value, "60")


# Default timeframes for trading
DEFAULT_TIMEFRAME = TimeFrame.M5   # 5 minutes for scalping
DEFAULT_HTF = TimeFrame.M60       # 1 hour for higher timeframe analysis
