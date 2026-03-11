"""Strategies API routes - extracted from main.py"""
from fastapi import APIRouter, Body, Query, Request
from typing import Optional
from pydantic import BaseModel
from services.state import get_symbol_strategy, set_symbol_strategy, get_all_strategy_selections, get_instruments
from app.logging import log_event

router = APIRouter()


def get_strategy_manager():
    """Lazy import get_strategy_manager to avoid circular import"""
    from main import get_strategy_manager
    return get_strategy_manager()


@router.get("/api/strategies")
async def get_strategies():
    """List all available trading strategies (OLD + JSON)."""
    from strategies import list_strategies as old_list_strategies
    
    # Get OLD strategies
    old_strategies = old_list_strategies()
    for s in old_strategies:
        s['source'] = 'OLD'
        s['id'] = f"OLD:{s['id']}"
    
    # Get JSON strategies
    json_strategies = []
    manager = get_strategy_manager()
    if manager:
        for s in manager.strategies.values():
            json_strategies.append({
                'id': f"JSON:{s.id}",
                'name': s.name,
                'description': f"JSON-based strategy for {s.symbol}",
                'source': 'JSON',
                'symbol': s.symbol,
                'timeframe': s.timeframe,
                'enabled': s.enabled
            })
    
    # Combine and return
    all_strategies = old_strategies + json_strategies
    return {"strategies": all_strategies}


@router.get("/api/strategy/{symbol}")
async def get_strategy_for_symbol(symbol: str):
    """Get the active strategy for a symbol."""
    return {"symbol": symbol, "strategy": get_symbol_strategy(symbol)}


@router.post("/api/strategy/{symbol}")
async def set_strategy_for_symbol(
    symbol: str, 
    strategy_id: str = Query(None),
    body_strategy_id: str = Body(None, embed=True)
):
    """Set the strategy for a symbol via query param or body."""
    # Accept either query param or body
    strategy_id = strategy_id or body_strategy_id
    if not strategy_id:
        return {"error": "strategy_id is required (query param or body)"}
    
    from strategies import STRATEGIES
    
    # Handle JSON strategies
    if strategy_id.startswith("JSON:"):
        json_id = strategy_id.replace("JSON:", "")
        manager = get_strategy_manager()
        if manager and json_id in manager.strategies:
            set_symbol_strategy(symbol, strategy_id)
            log_event(f"[STRATEGY] {symbol} → JSON:{json_id} (JSON strategy)", "event")
            return {"symbol": symbol, "strategy": strategy_id, "note": "JSON strategy will be used automatically"}
    
    # Handle OLD strategies
    old_id = strategy_id.replace("OLD:", "")
    if old_id not in STRATEGIES:
        return {"error": f"Unknown strategy: {strategy_id}. Available OLD: {list(STRATEGIES.keys())}"}
    set_symbol_strategy(symbol, old_id)
    log_event(f"[STRATEGY] {symbol} → {STRATEGIES[old_id].display_name} (OLD)", "event")
    return {"symbol": symbol, "strategy": strategy_id}


@router.get("/api/strategy-selections")
async def get_all_strategy_selections():
    """Get strategy selection for all symbols."""
    instruments = get_instruments()
    return {sym: get_symbol_strategy(sym) for sym in instruments}


@router.post("/api/strategies/save")
async def save_strategy_config(
    strategy_id: str = Body(..., description="Strategy ID to save"),
    name_suffix: str = Body("", description="Suffix to add"),
):
    """Save a strategy configuration with custom name"""
    from strategies import STRATEGIES, get_strategy

    if strategy_id in STRATEGIES:
        base_id = strategy_id
    else:
        base_id = None
        for sid in STRATEGIES.keys():
            if strategy_id.startswith(sid):
                base_id = sid
                break
        if not base_id:
            parts = strategy_id.rsplit("_", 1)
            if parts[0] in STRATEGIES:
                base_id = parts[0]
            else:
                return {"error": f"Base strategy not found for: {strategy_id}"}

    strategy = get_strategy(base_id)
    saved_id = strategy.save_strategy(name_suffix)
    return {"status": "saved", "strategy_id": saved_id}


@router.get("/strategies/load/{strategy_id}")
async def load_strategy_config(strategy_id: str):
    """Load a saved strategy from database"""
    from strategies import BaseStrategy
    strategy = BaseStrategy.load_strategy(strategy_id)
    if not strategy:
        return {"error": f"Strategy not found: {strategy_id}"}
    return {"status": "loaded", "strategy_id": strategy_id}


@router.post("/api/strategies/backtest-json")
async def backtest_from_json(
    symbol: str = Query(...),
    resolution: str = Query("5"),
    days: int = Query(30),
    initial_balance: float = Query(3000.0),
    request: Request = None,
):
    """Run backtest using strategy config from JSON body."""
    # Import the actual implementation from backtest.py
    from api.routes.backtest import backtest_from_json as _run_backtest
    return await _run_backtest(symbol=symbol, resolution=resolution, days=days, initial_balance=initial_balance, request=request)
