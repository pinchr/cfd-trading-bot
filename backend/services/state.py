"""Central state management for CFD Trading Bot
Replaces global variables in main.py - provides clean API for all services
"""
from typing import Dict, Any
from broker_factory import create_broker, create_data_provider
from broker_sim import INSTRUMENTS as _BROKER_INSTRUMENTS

data_provider = create_data_provider()
broker = create_broker(data_provider)

# Core state
account: Dict[str, Any] = {}
open_positions: list = []
closed_positions: list = []
signals_cache: Dict[str, Any] = {}
signal_history_cache: Dict[str, Any] = {}

# Strategy selection (per-symbol)
_strategy_selection: Dict[str, str] = {}

# Signals cache
signals_cache: Dict[str, Any] = {}

# Timing stats
_timing_stats: Dict[str, Dict] = {}


def get_timing_stats() -> Dict[str, Dict]:
    """Get timing stats"""
    return _timing_stats


def reset_timing_stats() -> None:
    """Reset timing stats"""
    global _timing_stats
    _timing_stats = {}


# Signals cache
_signals_cache: Dict[str, Any] = {}


def get_signals_cache() -> Dict[str, Any]:
    """Get signals cache"""
    return _signals_cache


def set_signals_cache(cache: Dict[str, Any]) -> None:
    """Set signals cache"""
    global _signals_cache
    _signals_cache = cache

# Price cache
_live_price_cache: Dict[str, Dict[str, Any]] = {}
_live_price_cache_last_update: float = 0

# Settings
INSTRUMENTS: Dict[str, Dict[str, Any]] = _BROKER_INSTRUMENTS

INITIAL_BALANCE_USD: float = 3000.0

# Trading state
AUTO_TRADE_ENABLED: bool = False
AUTO_TRADE_INTERVAL_SEC: int = 30


def get_account() -> Dict[str, Any]:
    """Get current account state from broker with unrealized P&L"""
    acct = broker.account if hasattr(broker, 'account') else account
    
    # Calculate unrealized P&L from open positions - use broker's current prices
    positions = broker.get_open_positions() if hasattr(broker, 'get_open_positions') else []
    unrealized_pnl = 0
    
    # Use current_price from position (updated by broker's _async_update_prices)
    for pos in positions:
        entry = pos.get("entry_price", 0)
        current_price = pos.get("current_price", entry)
        size = pos.get("size", 0)
        leverage = pos.get("leverage", 1)
        direction = pos.get("direction", "buy")
        
        if current_price and entry:
            if direction == "buy":
                pnl = (current_price - entry) * size * leverage
            else:  # sell
                pnl = (entry - current_price) * size * leverage
            unrealized_pnl += pnl
    
    # Update equity to include unrealized P&L
    if "equity_usd" in acct:
        acct["equity_usd"] = round(acct.get("balance_usd", 0) + unrealized_pnl, 2)
    if "unrealized_pnl_usd" in acct:
        acct["unrealized_pnl_usd"] = round(unrealized_pnl, 2)
    
    return acct


def set_account(new_account: Dict[str, Any]) -> None:
    """Update account state"""
    global account
    account = new_account


def get_open_positions() -> list:
    """Get open positions from broker - trigger price update synchronously"""
    positions = broker.get_open_positions() if hasattr(broker, 'get_open_positions') else open_positions
    
    # Always trigger price update when positions are requested
    # This ensures P&L is current
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            # Sync context - run async update
            async def update_and_get():
                await broker._async_update_prices()
                return broker.get_open_positions()
            positions = loop.run_until_complete(update_and_get())
        else:
            # Async context - just return positions, they'll be updated by background task
            pass
    except Exception as e:
        print(f"[get_open_positions] Error: {e}")
    
    return positions


def set_open_positions(positions: list) -> None:
    """Update open positions"""
    global open_positions
    open_positions = positions


def get_closed_positions() -> list:
    """Get closed positions from broker"""
    return broker.get_closed_positions() if hasattr(broker, 'get_closed_positions') else closed_positions


def set_closed_positions(positions: list) -> None:
    """Update closed positions"""
    global closed_positions
    closed_positions = positions


def get_signals_cache() -> Dict[str, Any]:
    """Get signals cache"""
    return signals_cache


def set_signals_cache(cache: Dict[str, Any]) -> None:
    """Update signals cache"""
    global signals_cache
    signals_cache = cache


def get_signal_history_cache() -> Dict[str, Any]:
    """Get signal history cache"""
    return signal_history_cache


def set_signal_history_cache(cache: Dict[str, Any]) -> None:
    """Update signal history cache"""
    global signal_history_cache
    signal_history_cache = cache


def get_live_price_cache() -> Dict[str, Dict[str, Any]]:
    """Get live price cache"""
    return _live_price_cache


def update_live_price_cache(symbol: str, price_data: Dict[str, Any]) -> None:
    """Update price for a symbol"""
    global _live_price_cache, _live_price_cache_last_update
    import time
    _live_price_cache[symbol] = price_data
    _live_price_cache_last_update = time.time()


def get_price_cache_last_update() -> float:
    """Get last price cache update time"""
    return _live_price_cache_last_update


def get_auto_trade_enabled() -> bool:
    """Get auto trade enabled state"""
    return AUTO_TRADE_ENABLED


def set_auto_trade_enabled(enabled: bool) -> None:
    """Set auto trade enabled state"""
    global AUTO_TRADE_ENABLED
    AUTO_TRADE_ENABLED = enabled


def get_auto_trade_interval() -> int:
    """Get auto trade interval in seconds"""
    return AUTO_TRADE_INTERVAL_SEC


def set_auto_trade_interval(seconds: int) -> None:
    """Set auto trade interval"""
    global AUTO_TRADE_INTERVAL_SEC
    AUTO_TRADE_INTERVAL_SEC = seconds


def get_instruments() -> Dict[str, Dict[str, Any]]:
    """Get instruments config"""
    return INSTRUMENTS


def set_instruments(instruments: Dict[str, Dict[str, Any]]) -> None:
    """Set instruments config"""
    global INSTRUMENTS
    INSTRUMENTS = instruments


def get_initial_balance() -> float:
    """Get initial balance"""
    return INITIAL_BALANCE_USD


def set_initial_balance(balance: float) -> None:
    """Set initial balance"""
    global INITIAL_BALANCE_USD
    INITIAL_BALANCE_USD = balance


# Strategy selection
def get_symbol_strategy(symbol: str) -> str:
    """Get strategy for symbol"""
    return _strategy_selection.get(symbol, "adaptive_regime")


def set_symbol_strategy(symbol: str, strategy_id: str) -> None:
    """Set strategy for symbol - saves to both memory and MongoDB"""
    global _strategy_selection
    _strategy_selection[symbol] = strategy_id
    # Persist to MongoDB
    import database as db
    db.set_setting(f"STRATEGY_{symbol}", strategy_id, "system")
    
    # Trigger immediate signal recalculation for this symbol
    try:
        from services.signal_cache import invalidate_signal_cache
        invalidate_signal_cache(symbol)
    except Exception:
        pass


def load_strategy_selections_from_db() -> None:
    """Load strategy selections from MongoDB on startup"""
    global _strategy_selection
    import database as db
    instruments = ["XAU", "XAG", "US100", "BTC"]
    for sym in instruments:
        val = db.get_setting(f"STRATEGY_{sym}")
        if val:
            _strategy_selection[sym] = val


def get_all_strategy_selections() -> Dict[str, str]:
    """Get all symbol strategy selections"""
    return _strategy_selection.copy()
