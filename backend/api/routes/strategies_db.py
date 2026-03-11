"""Strategy DB API routes - extracted from main.py
Database CRUD operations for strategies (separate from in-memory strategy management in strategies.py)
"""
from fastapi import APIRouter, Body, Query
from typing import Optional
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/api/strategies/{strategy_id}")
async def get_strategy_api(strategy_id: str):
    """Get a specific strategy from database."""
    from database import get_strategy_from_db
    strategy = get_strategy_from_db(strategy_id)
    if strategy:
        return strategy
    return {"error": f"Strategy {strategy_id} not found"}, 404


@router.post("/api/strategies/sync")
async def sync_strategies_api():
    """Sync strategies from JSON file to database."""
    from database import sync_strategies_from_json
    result = sync_strategies_from_json()
    # Reload strategies in memory
    from strategies import reload_strategies
    reload_strategies()
    return result


@router.post("/api/strategies/reload")
async def reload_strategies_api():
    """Reload strategies into memory from database."""
    from strategies import reload_strategies, STRATEGIES
    reload_strategies()
    return {"status": "success", "count": len(STRATEGIES)}


@router.put("/api/strategies/{strategy_id}")
async def update_strategy_api(strategy_id: str, config: dict):
    """Update a strategy in database."""
    from database import save_strategy
    config["id"] = strategy_id
    save_strategy(config, updated_by="api")
    # Reload strategies in memory
    from strategies import reload_strategies
    reload_strategies()
    return {"status": "success"}


@router.delete("/api/strategies/{strategy_id}")
async def delete_strategy_api(strategy_id: str):
    """Delete a strategy from database."""
    from database import delete_strategy_from_db
    result = delete_strategy_from_db(strategy_id)
    # Reload strategies in memory
    from strategies import reload_strategies
    reload_strategies()
    return {"status": "success" if result else "not_found"}


@router.get("/api/strategies-db/list")
async def list_strategies_db_api():
    """List all strategies from database."""
    from database import list_strategies_db
    strategies = list_strategies_db()
    return {"strategies": strategies, "count": len(strategies)}
