"""App configuration module - constants and instrument definitions"""

from typing import Dict, Any

# Exchange rate
PLN_USD_RATE = 4.05

# Instruments to monitor - with per-instrument signal tuning
# leverage: position multiplier (x20 = 5% margin requirement)
# min_score: minimum |score| to enter (higher = fewer but better trades)
# asset_class: "commodity" (mean-reverting) or "equity"/"crypto" (trending)
# trailing_stop: enable trailing SL that locks in profits once in the green
INSTRUMENTS: Dict[str, Dict[str, Any]] = {
    "XAU": {
        "name": "Gold",
        "multiplier": 1,
        "pip_size": 0.01,
        "lot_size": 0.003,
        "leverage": 20,
        "min_score": 0.30,
        "asset_class": "commodity",
        "trailing_stop": True,
    },
    "XAG": {
        "name": "Silver",
        "multiplier": 1,
        "pip_size": 0.001,
        "lot_size": 0.003,
        "leverage": 20,
        "min_score": 0.28,
        "asset_class": "commodity",
        "trailing_stop": True,
    },
    "US100": {
        "name": "Nasdaq-100",
        "multiplier": 1,
        "pip_size": 0.01,
        "lot_size": 0.003,
        "leverage": 20,
        "min_score": 0.20,
        "asset_class": "equity",
        "trailing_stop": True,
    },
    "BTC": {
        "name": "Bitcoin",
        "multiplier": 1,
        "pip_size": 1.0,
        "lot_size": 0.001,
        "leverage": 5,
        "min_score": 0.20,
        "asset_class": "crypto",
        "trailing_stop": True,
    },
}


def get_instrument_config(symbol: str) -> Dict[str, Any]:
    """Get configuration for a specific instrument."""
    return INSTRUMENTS.get(symbol, {})


def get_all_instruments() -> Dict[str, Dict[str, Any]]:
    """Get all instrument configurations."""
    return INSTRUMENTS.copy()
