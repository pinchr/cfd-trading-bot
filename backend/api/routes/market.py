"""market API routes - extracted from main.py"""
from fastapi import APIRouter, Query

from services.state import get_instruments, data_provider
from services import is_market_open, get_market_hours

router = APIRouter(prefix="/api")


def get_async_load_candle_history():
    """Lazy import async_load_candle_history to avoid circular import"""
    from main import async_load_candle_history
    return async_load_candle_history


def get_async_count_candles():
    """Lazy import async_count_candles to avoid circular import"""
    from main import async_count_candles
    return async_count_candles


def get_async_get_candle_date_range():
    """Lazy import async_get_candle_date_range to avoid circular import"""
    from main import async_get_candle_date_range
    return async_get_candle_date_range


@router.get("/instruments")
async def _get_instruments():
    """Get all instruments with their settings."""
    instruments = get_instruments()
    return {
        symbol: {
            "name": info.get("name", symbol),
            "leverage": info.get("leverage", 1),
            "lot_size": info.get("lot_size", 1),
            "pip_size": info.get("pip_size", 0.01),
            "asset_class": info.get("asset_class", ""),
            "trailing_stop": info.get("trailing_stop", False),
            "market_open": is_market_open(symbol),
            "market_hours": get_market_hours(symbol),
        }
        for symbol, info in instruments.items()
    }


@router.post("/instruments/{symbol}/leverage")
async def set_leverage(symbol: str, leverage: int):
    """Update leverage for an instrument."""
    instruments = _get_instruments()
    if symbol not in instruments:
        return {"error": f"Unknown instrument: {symbol}"}
    if leverage < 1 or leverage > 100:
        return {"error": "Leverage must be between 1 and 100"}
    instruments[symbol]["leverage"] = leverage
    return {"symbol": symbol, "leverage": leverage}


@router.get("/quote/{symbol}")
async def get_quote(symbol: str):
    """Get current quote for a symbol."""
    try:
        quote = await data_provider.get_quote(symbol)
        return quote
    except Exception as e:
        return {"error": str(e)}


@router.get("/chart/{symbol}")
async def get_chart_data(symbol: str, resolution: str = "60", count: int = 100):
    """Get OHLCV chart data for a symbol."""
    try:
        candles = await data_provider.get_candles(symbol, resolution, count)
        return {"symbol": symbol, "candles": candles, "count": len(candles)}
    except Exception as e:
        return {"error": str(e)}


@router.get("/candles/{symbol}")
async def get_candle_history(
    symbol: str,
    resolution: str = Query("60", description="Resolution: 1, 5, 15, 30, 60, D"),
    count: int = Query(100, ge=1, le=5000),
    from_time: str = Query(None, description="ISO timestamp or YYYY-MM-DD"),
    to_time: str = Query(None, description="ISO timestamp or YYYY-MM-DD"),
):
    """Get historical candle data with aggregation from smaller intervals."""
    try:
        from database import get_db
        async_load_candle_history = get_async_load_candle_history()
        
        # Direct fetch from accumulated history
        candles = await async_load_candle_history(symbol, resolution, count, from_time, to_time)

        # Try aggregation from smaller intervals if not enough data
        if len(candles) < min(10, count):
            source_candidates = {
                "5": ["1"],
                "15": ["5", "1"],
                "30": ["15", "5", "1"],
                "60": ["30", "15", "5", "1"],
                "240": ["60", "30", "15"],
                "D": ["60", "30", "15", "5", "1"],
            }
            db = get_db()
            for src_res in source_candidates.get(resolution, []):
                stored = await async_load_candle_history(symbol, src_res, count, from_time, to_time)
                if stored and len(stored) >= 2:
                    aggregated = db.aggregate_candles(stored, resolution)
                    if len(aggregated) > len(candles):
                        candles = aggregated[-count:]
                        break

        return {"symbol": symbol, "resolution": resolution, "candles": candles, "count": len(candles)}
    except Exception as e:
        return {"error": str(e)}


@router.get("/candles/stats")
async def get_candle_stats():
    """Get stored candle history statistics for all instruments."""
    async_count_candles = get_async_count_candles()
    async_get_candle_date_range = get_async_get_candle_date_range()
    instruments = _get_instruments()
    
    stats = {}
    resolutions = ["1", "5", "15", "30", "60", "D"]
    for symbol in instruments:
        symbol_stats = {}
        for res in resolutions:
            cnt = await async_count_candles(symbol, res)
            if cnt > 0:
                date_range = await async_get_candle_date_range(symbol, res)
                symbol_stats[res] = {"count": cnt, "range": date_range}
        if symbol_stats:
            stats[symbol] = symbol_stats
    return {"stats": stats}


@router.delete("/candles/{symbol}")
async def delete_candles(
    symbol: str,
    resolution: str = "60",
):
    """Delete cached candles for a symbol (to force fresh fetch)"""
    from database import get_db
    db = get_db()
    
    result = db.candles.delete_many({
        "symbol": symbol.upper(),
        "resolution": resolution,
    })
    
    return {"deleted": result.deleted_count, "symbol": symbol.upper(), "resolution": resolution}
