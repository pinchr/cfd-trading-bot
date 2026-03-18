"""Logs API routes - extracted from main.py"""

from fastapi import APIRouter
from app.logging import event_log

router = APIRouter(tags=["logs"])


@router.get("/api/logs")
async def get_logs():
    return {"logs": event_log}
