"""account API routes - extracted from main.py"""
from fastapi import APIRouter
from services.state import get_account as _get_account, set_account as _set_account, get_instruments, get_open_positions
from database import async_load_open_positions, async_sync_account_from_closed_trades
from app.logging import log_event

router = APIRouter(tags=["account"])


@router.get("/api/account")
async def get_account():
    """Get account info with USD balance."""
    await async_sync_account_from_closed_trades()
    account = _get_account()
    open_positions = get_open_positions()
    
    unrealized_pnl = 0.0
    for pos in open_positions:
        unrealized_pnl += pos.get("unrealized_pnl_usd", 0)
    
    equity = account.get("balance_usd", 0) + unrealized_pnl
    
    return {
        "account": account,
        "balance_usd": account.get("balance_usd", 0),
        "equity_usd": equity,
        "available_usd": account.get("available_usd", equity),
        "unrealized_pnl": unrealized_pnl,
        "open_positions": len(open_positions),
    }


@router.post("/api/account/mode")
async def set_account_mode(mode: str):
    """Set account mode (simulation/live)."""
    account = _get_account()
    account["mode"] = mode
    _set_account(account)
    log_event(f"[ACCOUNT] Mode set to {mode}", "info")
    return {"mode": mode}


@router.post("/api/account/reset")
async def reset_account():
    """Reset account to initial state."""
    from services.state import get_initial_balance
    from database import async_clear_positions
    
    await async_clear_positions()
    balance = get_initial_balance()
    
    account = {
        "balance_usd": balance,
        "equity_usd": balance,
        "peak_balance_usd": balance,
        "peak_equity_usd": balance,
        "mode": "simulation",
        "broker": "sim",
    }
    _set_account(account)
    log_event(f"[ACCOUNT] Reset to ${balance}", "info")
    return account


@router.get("/api/account/peak")
async def get_peak_balance():
    """Get peak balance and equity."""
    account = _get_account()
    return {
        "peak_balance_usd": account.get("peak_balance_usd", 0),
        "peak_equity_usd": account.get("peak_equity_usd", 0),
    }


@router.post("/api/account/broker")
async def set_account_broker(broker: str):
    """Set broker type."""
    account = _get_account()
    account["broker"] = broker
    _set_account(account)
    return {"broker": broker}


@router.get("/api/account/config")
async def get_account_config():
    """Get account configuration."""
    account = _get_account()
    return {
        "mode": account.get("mode", "simulation"),
        "broker": account.get("broker", "sim"),
    }
