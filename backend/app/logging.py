"""Logging module - centralized event logging"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List

# Global event log storage
event_log: List[Dict[str, Any]] = []
_log_counter = 0


def log_event(message: str, log_type: str = "info"):
    """
    Log events for the console. Persists to DB every 10 entries.
    
    Args:
        message: The log message
        log_type: Type of log (info, warning, error, success, event)
    """
    global _log_counter
    
    event_log.append(
        {
            "id": str(len(event_log)),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "message": message,
            "type": log_type,
        }
    )
    
    # Keep only last 200 events in memory
    if len(event_log) > 200:
        event_log.pop(0)
    
    print(f"[{log_type.upper()}] {message}")
    
    # Persist periodically (every 10 log entries) to avoid excessive DB writes
    _log_counter += 1
    if _log_counter % 10 == 0:
        # Run DB save in background - don't block
        # Import here to avoid circular imports
        try:
            from database import async_save_event_log
            asyncio.create_task(async_save_event_log(event_log))
        except Exception:
            pass  # DB not available


def get_event_log() -> List[Dict[str, Any]]:
    """Get the current event log."""
    return event_log.copy()


def clear_event_log():
    """Clear the in-memory event log."""
    event_log.clear()


def get_log_count() -> int:
    """Get the current log counter value."""
    return _log_counter
