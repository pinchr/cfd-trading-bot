"""Market data service - extracted from main.py"""
import time
from typing import Dict, List, Optional
import asyncio

# Price cache
_live_price_cache: Dict[str, dict] = {}
_live_price_cache_last_update: float = 0.0
_candles_cache: Dict[str, List] = {}


async def update_live_price_cache(data_provider, instruments: Dict) -> None:
    """Background task: keep live prices fresh for all instruments."""
    global _live_price_cache, _live_price_cache_last_update

    symbols = list(instruments.keys())

    for symbol in symbols:
        try:
            candles = await data_provider.get_candles(symbol, "60", 1)
            if candles and len(candles) > 0:
                _live_price_cache[symbol] = {
                    "price": candles[-1]["close"],
                    "timestamp": time.time(),
                    "candle": candles[-1],
                }
        except Exception:
            try:
                quote = await data_provider.get_quote(symbol)
                if quote:
                    _live_price_cache[symbol] = {
                        "price": quote.get("price", 0),
                        "timestamp": time.time(),
                        "quote": quote,
                    }
            except:
                pass

    _live_price_cache_last_update = time.time()


def get_live_price(symbol: str) -> Optional[float]:
    """Get cached live price for a symbol."""
    cached = _live_price_cache.get(symbol)
    if cached:
        return cached.get("price")
    return None


def get_cached_quote(symbol: str) -> Optional[dict]:
    """Get cached quote data."""
    return _live_price_cache.get(symbol)


async def get_cached_candles(symbol: str, resolution: str, count: int, data_provider) -> Optional[List]:
    """Get cached candles or fetch fresh."""
    key = f"{symbol}_{resolution}"
    
    # Return cached if fresh (< 1 min for 5m, < 5 min for 60m)
    cache_ttl = 60 if resolution == "5" else 300
    cached = _candles_cache.get(key, {})
    cached_time = cached.get("_cached_at", 0)
    
    if time.time() - cached_time < cache_ttl:
        return cached.get("candles", [])[-count:]
    
    # Fetch fresh
    try:
        candles = await data_provider.get_candles(symbol, resolution, count + 10)
        if candles:
            candles = candles[-count:]
            _candles_cache[key] = {"candles": candles, "_cached_at": time.time()}
            return candles
    except Exception:
        pass
    
    # Return stale cache
    return cached.get("candles", [])[-count:]


def set_cached_candles(symbol: str, resolution: str, candles: List) -> None:
    """Set candles in cache."""
    key = f"{symbol}_{resolution}"
    _candles_cache[key] = {"candles": candles, "_cached_at": time.time()}


def get_cache_stats() -> dict:
    """Get cache statistics."""
    return {
        "price_cache_size": len(_live_price_cache),
        "candles_cache_size": len(_candles_cache),
        "last_price_update": _live_price_cache_last_update,
    }
