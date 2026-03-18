"""Alerts API routes."""
from typing import Optional

from fastapi import APIRouter, Query
from imessage_alerts import AlertConfig, get_dispatcher

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("/config")
async def get_alert_config():
    """Get alert configuration."""
    dispatcher = get_dispatcher()
    return dispatcher.config.dict()


@router.post("/config")
async def update_alert_config(config: AlertConfig):
    """Update alert configuration."""
    dispatcher = get_dispatcher()
    dispatcher.update_config(config)
    return {"status": "updated", "config": dispatcher.config.dict()}


@router.post("/test")
async def send_test_alert():
    """Send a test alert."""
    dispatcher = get_dispatcher()
    if not dispatcher.config.enabled:
        return {"status": "error", "message": "Alerts are disabled"}
    try:
        result = dispatcher.send_alert(
            symbol="TEST",
            direction="buy",
            score=0.8,
            confidence=0.85,
            current_price=50000.0,
            entry_point=49500.0,
            take_profit=51000.0,
            stop_loss=49000.0,
        )
        if result["status"] == "sent":
            return {"status": "sent", "message_id": result.get("message_id")}
        return {"status": "error", "message": result.get("error", "Failed")}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/history")
async def get_alert_history(symbol: Optional[str] = None, limit: int = Query(20, ge=1, le=100)):
    """Get alert history."""
    dispatcher = get_dispatcher()
    history = dispatcher.get_alert_history(symbol=symbol, limit=limit)
    return {"history": history, "total": len(history), "symbol_filter": symbol}


@router.delete("/history")
async def clear_alert_history():
    """Clear alert history."""
    dispatcher = get_dispatcher()
    dispatcher.clear_history()
    return {"status": "cleared"}
