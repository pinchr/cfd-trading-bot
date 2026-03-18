"""Status API routes - extracted from main.py"""
from fastapi import APIRouter
import os
from datetime import datetime

router = APIRouter(tags=["status"])


@router.get("/api/timing-report")
async def get_timing_report():
    """Get performance timing report."""
    from services.state import get_timing_stats
    stats = get_timing_stats()
    formatted = {}
    for name, s in stats.items():
        if s["calls"] > 0:
            formatted[name] = {
                "calls": s["calls"],
                "total_sec": round(s["total"], 3),
                "avg_sec": round(s["total"] / s["calls"], 3),
                "min_sec": round(s["min"], 3),
                "max_sec": round(s["max"], 3),
            }
    formatted = dict(sorted(formatted.items(), key=lambda x: -x[1]["total_sec"]))
    return {"timestamp": datetime.utcnow().isoformat(), "functions": formatted, "count": len(formatted)}


@router.delete("/api/timing-report")
async def clear_timing_report():
    """Clear timing statistics."""
    from services.state import reset_timing_stats
    reset_timing_stats()
    return {"status": "cleared"}


@router.get("/api/status")
async def get_status():
    """Detailed status endpoint."""
    import database as db
    from services.state import get_account, get_open_positions, get_instruments
    
    mongo_uri_set = bool(os.getenv("MONGO_URI") or os.getenv("MONGODB_URI"))
    mongo_connected = hasattr(db, 'is_connected') and db.is_connected()

    account = get_account()
    open_positions = get_open_positions()
    instruments = get_instruments()

    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "0.2.0",
        "environment": {
            "mongo_uri_set": mongo_uri_set,
            "mongo_db": os.getenv("MONGO_DB", "cfd_trading_bot"),
            "mongo_connected": mongo_connected,
            "broker_type": os.getenv("BROKER_TYPE", "sim"),
        },
        "account": {
            "balance_usd": account.get("balance_usd", 0),
            "equity_usd": account.get("equity_usd", 0),
            "open_trades": len(open_positions),
            "mode": account.get("mode", "simulation"),
        },
        "instruments": list(instruments.keys()),
    }
