"""Signals API routes"""
from fastapi import APIRouter
from models import SignalResponse
from services.trading_engine import generate_signals
from app.logging import log_event

router = APIRouter(tags=["signals"])


@router.get("/api/signals", response_model=SignalResponse)
async def get_signals():
    """Fetch real trading signals."""
    log_event("Generating signals via API...", "info")
    signals = await generate_signals()
    return SignalResponse(signals=signals)
