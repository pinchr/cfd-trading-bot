"""Circuit breaker service - extracted from main.py"""
from typing import Tuple
from datetime import datetime, timedelta

# Circuit breaker state
_circuit_breaker_triggered = False
_circuit_breaker_reason = ""
_circuit_breaker_since = None

# Configuration
MAX_CONSECUTIVE_LOSSES = 5
MAX_DAILY_TRADES = 20
MAX_DRAWDOWN_PERCENT = 10.0


def check_circuit_breaker() -> Tuple[bool, str]:
    """
    Check if trading should be paused due to risk limits.
    Returns (can_trade, reason).
    - can_trade=True: trading is allowed
    - can_trade=False: trading is blocked
    """
    global _circuit_breaker_triggered, _circuit_breaker_reason, _circuit_breaker_since
    
    from main import db, account
    
    # Check if manually triggered
    if _circuit_breaker_triggered:
        # Auto-reset after 1 hour
        if _circuit_breaker_since and datetime.now() - _circuit_breaker_since > timedelta(hours=1):
            reset_circuit_breaker()
            return True, ""  # FIXED: was False
        return False, _circuit_breaker_reason  # FIXED: was True
    
    # Check consecutive losses
    try:
        recent_trades = list(db.trades.find({
            "closed_at": {"$gte": datetime.now() - timedelta(hours=24)}
        }).sort("closed_at", -1).limit(10))
        
        if len(recent_trades) >= MAX_CONSECUTIVE_LOSSES:
            losses = sum(1 for t in recent_trades[:MAX_CONSECUTIVE_LOSSES] if t.get("pnl", 0) < 0)
            if losses >= MAX_CONSECUTIVE_LOSSES:
                trigger_circuit_breaker("Too many consecutive losses")
                return False, _circuit_breaker_reason  # FIXED: trading blocked
    except Exception:
        pass
    
    # Check drawdown
    try:
        peak = account.get("peak_equity_usd", account.get("balance_usd", 3000))
        current = account.get("balance_usd", 3000)
        if peak > 0:
            drawdown = ((peak - current) / peak) * 100
            if drawdown > MAX_DRAWDOWN_PERCENT:
                trigger_circuit_breaker(f"Max drawdown exceeded: {drawdown:.1f}%")
                return False, _circuit_breaker_reason  # FIXED: trading blocked
    except Exception:
        pass
    
    return True, ""  # FIXED: was False - trading allowed!


def trigger_circuit_breaker(reason: str) -> None:
    """Manually trigger circuit breaker."""
    global _circuit_breaker_triggered, _circuit_breaker_reason, _circuit_breaker_since
    _circuit_breaker_triggered = True
    _circuit_breaker_reason = reason
    _circuit_breaker_since = datetime.now()


def reset_circuit_breaker() -> None:
    """Reset circuit breaker."""
    global _circuit_breaker_triggered, _circuit_breaker_reason, _circuit_breaker_since
    _circuit_breaker_triggered = False
    _circuit_breaker_reason = ""
    _circuit_breaker_since = None


def get_circuit_breaker_status() -> dict:
    """Get current circuit breaker status."""
    return {
        "triggered": _circuit_breaker_triggered,
        "reason": _circuit_breaker_reason,
        "since": _circuit_breaker_since.isoformat() if _circuit_breaker_since else None,
    }
