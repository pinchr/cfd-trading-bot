"""trades API routes - extracted from main.py"""
from typing import Optional
from fastapi import APIRouter, Query, Body
from services.state import (
    get_open_positions,
    get_instruments,
    broker, 
    data_provider
)
from services import calculate_position_size, check_circuit_breaker, is_market_open, get_market_hours
from app.logging import log_event
from database import async_save_trade, async_sync_account_from_closed_trades, async_load_closed_positions, async_count_closed_positions

router = APIRouter(prefix="", tags=["trades"])


def get_technical_indicators():
    """Lazy import TechnicalIndicators to avoid circular import"""
    from main import TechnicalIndicators
    return TechnicalIndicators


@router.get("/api/trade/size")
async def get_position_size(symbol: str, entry_price: float, stop_loss: float):
    """Calculate suggested position size for a trade"""
    instruments = get_instruments()
    if symbol not in instruments:
        return {"error": f"Unknown instrument: {symbol}"}

    size = calculate_position_size(symbol, entry_price, stop_loss)
    return {
        "symbol": symbol,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "suggested_size": size,
        "lot_size": instruments[symbol].get("lot_size", 0.01),
    }


@router.get("/api/trade/proposal")
async def get_trade_proposal(symbol: str, direction: str):
    """Get full trade proposal with TP/SL calculated"""
    instruments = get_instruments()
    if symbol not in instruments:
        return {"error": f"Unknown instrument: {symbol}"}
    
    try:
        quote = await data_provider.get_quote(symbol)
        current_price = quote["price"]
    except Exception as e:
        return {"error": f"Failed to get quote: {e}"}
    
    # Calculate position size
    sl_pct = 0.01  # 1% stop loss
    size = calculate_position_size(symbol, current_price, current_price * (1 - sl_pct))
    
    # Calculate TP/SL
    if direction == "buy":
        tp = current_price * 1.02
        sl = current_price * 0.99
    else:
        tp = current_price * 0.98
        sl = current_price * 1.01
    
    return {
        "symbol": symbol,
        "direction": direction,
        "entry_price": current_price,
        "size": size,
        "take_profit": tp,
        "stop_loss": sl,
    }


@router.post("/api/trade/open")
async def open_trade(
    symbol: str = Body(...),
    direction: str = Body(...),
    size: float = Body(...),
    take_profit: float = Body(0),
    stop_loss: float = Body(0),
    entry_price: float = Body(0),
    signal_score: float = Body(0),  # Add signal_score parameter
):
    """Open a new trade"""
    can_trade, reason = check_circuit_breaker()
    if not can_trade:
        return {"error": f"Trading blocked: {reason}"}
    
    # If no signal_score provided, try to get from current signals (simplified)
    # For now, use 0 as default - the auto-trade loop passes signal.score directly
    if signal_score == 0:
        signal_score = 0.0  # Will be set by auto-trade
    
    # Using imported function directly
    result = await broker.open_position(
        symbol=symbol,
        direction=direction,
        size=size,
        take_profit=take_profit if take_profit > 0 else None,
        stop_loss=stop_loss if stop_loss > 0 else None,
        entry_price=entry_price if entry_price > 0 else None,
        signal_score=signal_score,  # Pass signal score
    )
    
    if "error" not in result:
        await async_sync_account_from_closed_trades()
        log_event(f"[TRADE] Opened {direction} {symbol} size={size}", "success")
    
    return result


@router.post("/api/trade/{position_id}/close")
async def close_trade(position_id: str):
    """Close an existing trade"""
    # Using imported function directly
    result = await broker.close_position(position_id)
    
    if "error" not in result:
        await async_sync_account_from_closed_trades()
        log_event(f"[TRADE] Closed position {position_id}", "info")
    
    return result


@router.get("/api/trades")
async def get_open_trades():
    """Get all open trades"""
    positions = get_open_positions()
    return {"positions": positions, "count": len(positions)}


@router.get("/api/trades/open")
async def get_open_trades_alias():
    """Get all open trades (alias for /api/trades)"""
    positions = get_open_positions()
    return {"positions": positions, "count": len(positions)}


@router.get("/api/trades/history")
async def get_trade_history(limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    """Get trade history"""
    closed = await async_load_closed_positions(limit)
    total = await async_count_closed_positions()
    return {"trades": closed, "total": total, "limit": limit, "offset": offset}


@router.post("/api/trades/update/{position_id}")
async def update_trade_position(
    position_id: str, stop_loss: Optional[float] = Query(None), take_profit: Optional[float] = Query(None)
):
    """
    Update SL/TP for position
    """
    positions = broker.get_open_positions()
    position = next((p for p in positions if p["id"] == position_id), None)
    if not position:
        return {"error": "Position not found"}
    updated = False
    if stop_loss is not None:
        position["stop_loss"] = stop_loss
        updated = True
    if take_profit is not None:
        position["take_profit"] = take_profit
        updated = True
    if updated:
        log_event(f"[UPDATE] Position {position_id}: SL/TP updated", "info")
        await async_save_trade(position)
    return {"status": "updated", "position": position}
