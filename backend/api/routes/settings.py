"""Settings API routes - extracted from main.py"""
from fastapi import APIRouter, Body
import database as db
from settings import get_all_settings
from services.state import get_instruments
from app.logging import log_event

router = APIRouter(tags=["settings"])

ALL_INDICATORS = ["RSI", "MACD", "BB", "SMA", "ADX", "STOCH", "MOMENTUM", "WILLIAMS_R", "DIVERGENCE", "HTF_CANDLE"]


@router.get("/api/settings")
async def get_settings():
    """Get all settings including broker-specific refresh rates."""
    db_settings = db.list_settings()
    broker_settings = get_all_settings()
    return {"db": db_settings, "broker": broker_settings}


@router.post("/api/settings")
async def save_setting(key: str = Body(...), value: float = Body(...), note: str = Body("")):
    """Save a setting to DB and update in-memory state if needed."""
    db.set_setting(key, value, note)
    log_event(f"[SETTINGS] Saved {key}={value}", "info")
    
    # Update in-memory state for critical settings
    from services.state import set_auto_trade_enabled, set_auto_trade_interval
    if key == "AUTO_TRADE_ENABLED":
        set_auto_trade_enabled(bool(value))
    elif key == "AUTO_TRADE_INTERVAL_SEC":
        set_auto_trade_interval(int(value))
    
    return {"key": key, "value": value}


@router.delete("/api/settings/{key}")
async def delete_setting(key: str):
    """Delete a setting from DB."""
    db.delete_setting(key)
    return {"key": key, "deleted": True}


@router.get("/api/trading-mode")
async def get_trading_mode():
    """Get current trading mode."""
    mode = db.get_setting("TRADING_MODE", "simulation")
    auto_trade = db.get_setting("AUTO_TRADE_ENABLED", 0)
    return {"mode": mode, "auto_trade": bool(auto_trade)}


@router.post("/api/trading-mode")
async def set_trading_mode(broker: str = "simulation", autoTrade: bool = False):
    """Set trading mode and auto-trade."""
    db.set_setting("TRADING_MODE", broker, "system")
    db.set_setting("AUTO_TRADE_ENABLED", 1 if autoTrade else 0, "system")
    log_event(f"[MODE] {broker.upper()} | Auto-trade: {'ON' if autoTrade else 'OFF'}", "event")
    return {"mode": broker, "auto_trade": autoTrade}


@router.get("/api/settings/indicators/{symbol}")
async def get_indicators_for_symbol(symbol: str):
    """Get indicator settings for a symbol."""
    from services.state import get_symbol_strategy
    
    indicators = db.get_setting(f"INDICATORS_{symbol}", {})
    strategy = get_symbol_strategy(symbol)  # Get active strategy for symbol
    
    return {
        "symbol": symbol, 
        "indicators": indicators,
        "strategy": strategy
    }


@router.post("/api/settings/indicators/{symbol}")
async def set_indicators_for_symbol(symbol: str, data: dict):
    """Save indicator settings for a symbol."""
    indicators = data.get("indicators", [])
    strategy = data.get("strategy", "")
    
    db.set_setting(f"INDICATORS_{symbol}", indicators, "user")
    if strategy:
        from services.state import set_symbol_strategy
        set_symbol_strategy(symbol, strategy)
    
    return {"symbol": symbol, "indicators": indicators, "strategy": strategy}


@router.post("/api/settings/dynamic-positions")
async def set_dynamic_positions(enabled: bool = True):
    """Enable/disable dynamic position sizing."""
    db.set_setting("DYNAMIC_POSITIONS_ENABLED", 1 if enabled else 0, "system")
    log_event(f"[DYNAMIC-POSITIONS] {'Enabled' if enabled else 'Disabled'}", "event")
    return {"status": "ok", "enabled": enabled}
