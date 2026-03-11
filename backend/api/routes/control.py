"""Control API routes - auto-trade, circuit-breaker control"""
from fastapi import APIRouter
from services.state import (
    get_auto_trade_enabled,
    set_auto_trade_enabled,
    get_auto_trade_interval,
    set_auto_trade_interval,
    get_account,
    get_open_positions,
)
from app.logging import log_event

router = APIRouter(tags=["control"])


@router.get("/api/auto-trade")
async def get_auto_trade_status():
    """Get auto-trading status."""
    return {
        "enabled": get_auto_trade_enabled(),
        "interval_sec": get_auto_trade_interval(),
        "last_scan": get_account().get("last_scan"),
        "open_positions": len(get_open_positions()),
    }


@router.post("/api/auto-trade")
async def set_auto_trade(enabled: bool):
    """Enable/disable auto-trading."""
    set_auto_trade_enabled(enabled)
    log_event(f"[AUTO-TRADE] {'ENABLED' if enabled else 'DISABLED'}", "event")
    return {"enabled": get_auto_trade_enabled()}


@router.post("/api/auto-trade/interval")
async def set_auto_trade_interval(seconds: int):
    """Set auto-trade scan interval (min 60s, max 3600s)."""
    if seconds < 60 or seconds > 3600:
        return {"error": "Interval must be between 60 and 3600 seconds"}
    set_auto_trade_interval(seconds)
    log_event(f"[AUTO-TRADE] Interval set to {seconds}s", "event")
    return {"interval_sec": get_auto_trade_interval()}
