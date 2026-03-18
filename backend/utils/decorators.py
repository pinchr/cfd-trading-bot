"""Timing decorators - extracted from main.py"""
import functools
import time
from typing import Any, Callable, Dict
from services.state import _timing_stats


def async_timed(label: str | None = None):
    """Decorator to measure async function execution time."""

    def decorator(func: Callable) -> Callable:
        func_name = label or func.__name__

        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                if func_name not in _timing_stats:
                    _timing_stats[func_name] = {"calls": 0, "total": 0.0, "min": float("inf"), "max": 0.0}
                _timing_stats[func_name]["calls"] += 1
                _timing_stats[func_name]["total"] += elapsed
                _timing_stats[func_name]["min"] = min(_timing_stats[func_name]["min"], elapsed)
                _timing_stats[func_name]["max"] = max(_timing_stats[func_name]["max"], elapsed)
                print(f"[TIMING] {func_name}: {elapsed:.3f}s", flush=True)
                try:
                    from app.logging import log_event
                    log_event(f"[TIMING] {func_name}: {elapsed:.3f}s", "info")
                except Exception:
                    pass

        return wrapper

    return decorator


def sync_timed(label: str | None = None):
    """Decorator to measure sync function execution time."""

    def decorator(func: Callable) -> Callable:
        func_name = label or func.__name__

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                if func_name not in _timing_stats:
                    _timing_stats[func_name] = {"calls": 0, "total": 0.0, "min": float("inf"), "max": 0.0}
                _timing_stats[func_name]["calls"] += 1
                _timing_stats[func_name]["total"] += elapsed
                _timing_stats[func_name]["min"] = min(_timing_stats[func_name]["min"], elapsed)
                _timing_stats[func_name]["max"] = max(_timing_stats[func_name]["max"], elapsed)
                print(f"[TIMING] {func_name}: {elapsed:.3f}s", flush=True)
                try:
                    from app.logging import log_event
                    log_event(f"[TIMING] {func_name}: {elapsed:.3f}s", "info")
                except Exception:
                    pass

        return wrapper

    return decorator
