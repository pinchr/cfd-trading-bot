"""FastAPI dependencies for dependency injection."""
from typing import Any
from services.state import broker, data_provider, account, INSTRUMENTS, INITIAL_BALANCE_USD

def get_broker() -> Any:
    """Get broker instance."""
    return broker

def get_data_provider() -> Any:
    """Get data provider instance."""
    return data_provider

def get_account() -> dict:
    """Get account dict."""
    return account

def get_instruments() -> dict:
    """Get instruments dict."""
    return INSTRUMENTS

def get_initial_balance() -> float:
    """Get initial balance."""
    return INITIAL_BALANCE_USD
