"""Root API routes - extracted from main.py
Endpoints: /, /health, /api/debug/positions
"""

from fastapi import APIRouter
from fastapi.responses import FileResponse
from datetime import datetime
import pathlib

router = APIRouter(tags=["root"])


@router.get("/")
async def root():
    """Serve frontend or return API info"""
    # Try to find frontend dist
    frontend_paths = [
        pathlib.Path("../frontend/dist"),
        pathlib.Path("../../frontend/dist"),
        pathlib.Path("frontend/dist"),
    ]
    for path in frontend_paths:
        if path.is_dir():
            return FileResponse(path / "index.html")
    return {"message": "CFD Trading Bot API", "status": "running", "version": "0.2.0"}


@router.get("/health")
async def health():
    """Health check with MongoDB status"""
    from database import get_db
    db = get_db()
    mongo_status = "connected" if db is not None else "disconnected"
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat(), "mongodb": mongo_status, "version": "0.2.0"}


@router.get("/api/debug/positions")
async def debug_positions():
    """Debug endpoint to check all positions in memory vs DB."""
    from database import load_closed_positions, load_open_positions
    from services.state import get_open_positions
    
    open_pos = get_open_positions()
    
    db_open = load_open_positions()
    db_closed = load_closed_positions(20)
    
    return {
        "memory": {
            "open_count": len(open_pos),
            "open_ids": [p["id"] for p in open_pos],
        },
        "database": {
            "open_count": len(db_open),
            "open_ids": [p["id"] for p in db_open],
            "closed_count": len(db_closed),
            "recent_closed": [
                (p["id"], p["symbol"], p["entry_price"], str(p.get("closed_at", "unknown"))[:16]) for p in db_closed[:5]
            ],
        },
    }
