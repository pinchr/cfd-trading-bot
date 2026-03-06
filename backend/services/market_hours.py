"""Market hours service - check if markets are open for trading"""

from typing import Optional
from timezone import now_warsaw


def is_market_open(symbol: str) -> bool:
    """
    Check if market is currently open for trading.
    Uses Europe/Warsaw time.

    XAU/XAG/US100: Mon-Fri 01:00-22:59 Warsaw (CET/CEST)
    BTC: Always open (24/7)
    
    Args:
        symbol: Trading symbol (XAU, XAG, US100, BTC)
    
    Returns:
        True if market is open, False otherwise
    """
    now = now_warsaw()
    weekday = now.weekday()  # 0=Monday, 6=Sunday
    hour = now.hour

    if symbol == "BTC":
        # Crypto never closes
        return True

    if symbol in ("XAU", "XAG", "US100"):
        # Forex commodities: Mon 00:00 - Fri 22:00 UTC
        # Weekend closed (Fri 22:00 - Sun 23:00)
        if weekday == 5:  # Saturday
            return False
        if weekday == 6:  # Sunday - opens at 23:00
            return hour >= 23
        if weekday == 4 and hour >= 22:  # Friday after 22:00
            return False
        return True

    # Default: allow trading
    return True


def get_market_hours(symbol: str) -> str:
    """
    Get human-readable market hours for a symbol.
    
    Args:
        symbol: Trading symbol
    
    Returns:
        String describing market hours
    """
    if symbol == "BTC":
        return "24/7"
    if symbol in ("XAU", "XAG"):
        return "Mon-Fri 00:00-22:00 UTC"
    if symbol == "US100":
        return "Mon-Fri 14:30-21:00 UTC"
    return "Unknown"


def is_trading_day(symbol: str) -> bool:
    """Check if today is a trading day for the symbol."""
    return is_market_open(symbol)


def get_next_open_time(symbol: str) -> Optional[str]:
    """
    Get the next market open time as a string.
    
    Args:
        symbol: Trading symbol
    
    Returns:
        Human-readable time until next open, or None if always open
    """
    if symbol == "BTC":
        return None  # Always open
    
    now = now_warsaw()
    weekday = now.weekday()
    hour = now.hour
    
    if symbol in ("XAU", "XAG", "US100"):
        if weekday == 5:  # Saturday
            return "Sunday 23:00 UTC"
        if weekday == 6:  # Sunday
            if hour < 23:
                hours_left = 23 - hour
                return f"{hours_left} hours"
        if weekday == 4 and hour >= 22:  # Friday after close
            return "Monday 00:00 UTC"
    
    return None  # Currently open
