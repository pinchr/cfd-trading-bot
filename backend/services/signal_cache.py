"""Signal cache service - extracted from main.py"""
import json
import os
from typing import Dict, Any


def create_signal_cache_service(db):
    """Factory function to create signal cache functions with DB dependency."""
    
    _signal_history_cache: Dict[str, Any] = {}
    
    def load_signal_cache():
        """Load signal history cache from DB, fallback to JSON file"""
        nonlocal _signal_history_cache
        # Try MongoDB first
        cached = db.load_signal_cache_db()
        if cached:
            _signal_history_cache = cached
            return _signal_history_cache
        # Fallback to JSON file
        try:
            cache_file = "signal_cache.json"
            if os.path.exists(cache_file):
                with open(cache_file, "r") as f:
                    _signal_history_cache = json.load(f)
        except Exception:
            _signal_history_cache = {}
        return _signal_history_cache
    
    def save_signal_cache():
        """Save signal history cache to DB + JSON file"""
        db.save_signal_cache_db(_signal_history_cache)
        try:
            cache_file = "signal_cache.json"
            with open(cache_file, "w") as f:
                json.dump(_signal_history_cache, f)
        except Exception:
            pass  # File write is best-effort fallback
    
    def get_cache():
        return _signal_history_cache
    
    def set_cache(cache: Dict[str, Any]):
        nonlocal _signal_history_cache
        _signal_history_cache = cache
    
    return {
        'load': load_signal_cache,
        'save': save_signal_cache,
        'get': get_cache,
        'set': set_cache
    }
