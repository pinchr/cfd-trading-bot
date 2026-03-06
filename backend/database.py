"""
MongoDB persistence layer for CFD Trading Bot.
Collections: account, trades, signal_cache, candle_cache, quote_cache, candles, event_log
Falls back to in-memory if MONGO_URI is not set.
"""

import os
from collections import OrderedDict
from datetime import datetime
from typing import Any, List, Optional

from timezone import now_warsaw

_db = None
_connected = False


def get_db():
    """Get MongoDB database instance. Returns None if not configured."""
    global _db, _connected
    if _db is not None:
        return _db
    if _connected:
        return _db

    mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
    mongo_db = os.getenv("MONGO_DB", "cfd_trading_bot")

    print(f"[DB] Checking MongoDB config...")
    print(f"[DB] MONGO_URI set: {bool(mongo_uri)} (length: {len(mongo_uri) if mongo_uri else 0})")
    print(f"[DB] MONGO_DB: {mongo_db}")

    if not mongo_uri:
        print(f"[DB] MONGO_URI not set - using in-memory storage")
        _connected = True
        return None

    try:
        import ssl

        from pymongo import MongoClient

        print(f"[DB] Connecting to MongoDB...")

        # Connection with proper SSL handling for Atlas
        client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=10000,
            tlsAllowInvalidCertificates=True,
        )
        client.admin.command("ping")
        print(f"[DB] ✅ MongoDB connected successfully")

        _db = client[mongo_db]
        _connected = True
        print(f"[DB] ✅ MongoDB connected successfully to database: {mongo_db}")

        # Test write access
        try:
            _db.test_connection.insert_one({"test": True, "timestamp": datetime.utcnow()})
            _db.test_connection.delete_one({"test": True})
            print(f"[DB] ✅ Write access confirmed")
        except Exception as write_err:
            print(f"[DB] ⚠️ Connected but write test failed: {write_err}")

        return _db
    except Exception as e:
        print(f"[DB] ❌ MongoDB connection failed: {type(e).__name__}: {e}")
        print(f"[DB] Using in-memory storage - data will be lost on restart!")
        _connected = True
        return None


# ── Account ──────────────────────────────────────────────────────────

DEFAULT_ACCOUNT = {
    "balance_usd": 3000.0,
    "equity_usd": 3000.0,
    "positions": 0,
    "open_trades": 0,
    "closed_trades": 0,
    "total_pnl_usd": 0.0,
    "win_count": 0,
    "loss_count": 0,
    "win_rate": 0.0,
    "used_margin": 0.0,
    "available_usd": 3000.0,
    "dry_run": True,
    "mode": "simulate",
    "currency": "USD",
}


def load_account() -> dict:
    """Load account state from DB, or return defaults."""
    db = get_db()
    if db is None:
        return {**DEFAULT_ACCOUNT, "last_scan": datetime.utcnow().isoformat()}
    doc = db.account.find_one({"_id": "main"})
    if doc:
        doc.pop("_id", None)
        # Migration: ensure USD fields exist
        if "balance_usd" not in doc:
            doc["balance_usd"] = DEFAULT_ACCOUNT["balance_usd"]
        if "equity_usd" not in doc:
            doc["equity_usd"] = doc.get("balance_usd", DEFAULT_ACCOUNT["balance_usd"])
        if "available_usd" not in doc:
            doc["available_usd"] = doc.get("balance_usd", DEFAULT_ACCOUNT["balance_usd"])
        if "used_margin" not in doc:
            doc["used_margin"] = 0.0
        if "total_pnl_usd" not in doc:
            doc["total_pnl_usd"] = 0.0
        return doc
    return {**DEFAULT_ACCOUNT, "last_scan": datetime.utcnow().isoformat()}


def save_account(account: dict):
    """Persist current account state."""
    db = get_db()
    if db is None:
        return
    db.account.replace_one({"_id": "main"}, {**account, "_id": "main"}, upsert=True)


# ── Trades ───────────────────────────────────────────────────────────


def load_open_positions() -> list:
    """Load open positions from DB."""
    db = get_db()
    if db is None:
        return []
    docs = list(db.trades.find({"status": "open"}).sort("opened_at", 1))
    for doc in docs:
        doc.pop("_id", None)
    return docs


def load_closed_positions(limit: int = 1000) -> list:
    """Load closed positions from DB, most recent first."""
    db = get_db()
    if db is None:
        return []
    docs = list(db.trades.find({"status": "closed"}).sort("closed_at", -1).limit(limit))
    for doc in docs:
        doc.pop("_id", None)
    return docs


def save_trade(trade: dict):
    """Insert or update a trade document (keyed by trade id)."""
    db = get_db()
    if db is None:
        return
    db.trades.replace_one({"id": trade["id"]}, trade, upsert=True)


def count_closed_positions() -> int:
    """Count total closed trades in DB."""
    db = get_db()
    if db is None:
        return 0
    return db.trades.count_documents({"status": "closed"})


def delete_all_trades():
    """Remove all trades (used by account reset)."""
    db = get_db()
    if db is None:
        return
    db.trades.delete_many({})


# ── Signal Cache ─────────────────────────────────────────────────────


def load_signal_cache_db() -> dict:
    """Load signal history cache from DB."""
    db = get_db()
    if db is None:
        return {}
    doc = db.signal_cache.find_one({"_id": "cache"})
    if doc:
        doc.pop("_id", None)
        return doc
    return {}


def save_signal_cache_db(cache: dict):
    """Persist signal history cache."""
    db = get_db()
    if db is None:
        return
    db.signal_cache.replace_one({"_id": "cache"}, {**cache, "_id": "cache"}, upsert=True)


def is_connected() -> bool:
    """Check if MongoDB is available."""
    return get_db() is not None


# ── Candle / Quote Cache ────────────────────────────────────────────
# Persists real market data so the app can show the last-known prices
# even when the API is temporarily unavailable.

_candle_mem_cache: dict = {}
_quote_mem_cache: dict = {}


def save_candles(symbol: str, resolution: str, candles: list, source: str):
    """Cache fetched candle data (DB or in-memory)."""
    doc = {
        "symbol": symbol,
        "resolution": resolution,
        "candles": candles,
        "source": source,
        "fetched_at": datetime.utcnow().isoformat(),
    }
    db = get_db()
    if db is not None:
        # Use update_one with $set instead of replace_one to avoid _id conflict
        db.candle_cache.update_one(
            {"symbol": symbol, "resolution": resolution},
            {"$set": {**doc}},
            upsert=True,
        )
    _candle_mem_cache[f"{symbol}_{resolution}"] = doc


def load_candles(symbol: str, resolution: str) -> Optional[dict]:
    """Load cached candle data. Returns dict with candles, source, fetched_at or None."""
    db = get_db()
    if db is not None:
        doc = db.candle_cache.find_one({"symbol": symbol, "resolution": resolution})
        if doc:
            doc.pop("_id", None)
            return doc
    cached = _candle_mem_cache.get(f"{symbol}_{resolution}")
    return cached


def load_backtest_candles(symbol: str, resolution: str) -> Optional[dict]:
    """Load backtest candle data from backtest_cache collection (separate from live trading)."""
    db = get_db()
    if db is not None:
        doc = db.backtest_cache.find_one({"symbol": symbol, "resolution": resolution})
        if doc:
            doc.pop("_id", None)
            print(f"[Backtest] Loaded {len(doc.get('candles', []))} candles from backtest_cache: {symbol}_{resolution}")
            return doc
    return None


def save_quote(symbol: str, quote: dict):
    """Cache a price quote (DB or in-memory)."""
    doc = {
        "symbol": symbol,
        "quote": quote,
        "fetched_at": datetime.utcnow().isoformat(),
    }
    db = get_db()
    if db is not None:
        # Use update_one with $set instead of replace_one to avoid _id conflict
        db.quote_cache.update_one(
            {"symbol": symbol},
            {"$set": {**doc}},
            upsert=True,
        )
    _quote_mem_cache[symbol] = doc


def load_quote(symbol: str) -> Optional[dict]:
    """Load cached quote. Returns dict with quote, fetched_at or None."""
    db = get_db()
    if db is not None:
        doc = db.quote_cache.find_one({"symbol": symbol})
        if doc:
            doc.pop("_id", None)
            return doc
    return _quote_mem_cache.get(symbol)


# ── Candle History (accumulating time-series) ──────────────────────
# Stores individual candles as documents, never overwrites.
# Key: (symbol, resolution, timestamp) — upserts to avoid duplicates.
# This builds a growing historical dataset for backtesting.

_candle_history_mem: dict = {}  # In-memory fallback: {symbol_resolution: [candles]}


def store_candles(symbol: str, resolution: str, candles: list, source: str = ""):
    """
    Accumulate candles into persistent history.
    Each candle is stored as its own document keyed by (symbol, resolution, timestamp).
    Existing candles are updated (upsert), new ones are inserted — no data lost.
    """
    if not candles:
        return

    db = get_db()
    if db is not None:
        from pymongo import UpdateOne

        ops = []
        for c in candles:
            ts = c.get("timestamp", "")
            if not ts:
                continue
            doc = {
                "symbol": symbol,
                "resolution": resolution,
                "timestamp": ts,
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c.get("volume", 0),
                "source": source,
            }
            ops.append(
                UpdateOne(
                    {"symbol": symbol, "resolution": resolution, "timestamp": ts},
                    {"$set": doc},
                    upsert=True,
                )
            )
        if ops:
            db.candles.bulk_write(ops, ordered=False)
    else:
        # In-memory fallback
        key = f"{symbol}_{resolution}"
        existing = {c.get("timestamp"): c for c in _candle_history_mem.get(key, [])}
        for c in candles:
            ts = c.get("timestamp", "")
            if ts:
                existing[ts] = c
        _candle_history_mem[key] = sorted(existing.values(), key=lambda x: x.get("timestamp", ""))


def load_candle_history(
    symbol: str,
    resolution: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 0,
) -> list:
    """
    Load accumulated candle history from DB.
    Optional time range filter (ISO timestamps).
    Returns candles sorted oldest-first (chronological).
    """
    db = get_db()
    if db is not None:
        query: dict = {"symbol": symbol, "resolution": resolution}
        if start or end:
            ts_filter: dict = {}
            if start:
                ts_filter["$gte"] = start
            if end:
                ts_filter["$lte"] = end
            query["timestamp"] = ts_filter

        cursor = db.candles.find(query).sort("timestamp", 1)
        if limit > 0:
            cursor = cursor.limit(limit)
        docs = list(cursor)
        for doc in docs:
            doc.pop("_id", None)
        return docs

    # In-memory fallback
    key = f"{symbol}_{resolution}"
    all_candles = _candle_history_mem.get(key, [])
    if start:
        all_candles = [c for c in all_candles if c.get("timestamp", "") >= start]
    if end:
        all_candles = [c for c in all_candles if c.get("timestamp", "") <= end]
    if limit > 0:
        all_candles = all_candles[-limit:]
    return all_candles


def count_candles(symbol: str, resolution: str) -> int:
    """Count stored candles for a symbol/resolution pair."""
    db = get_db()
    if db is not None:
        return db.candles.count_documents({"symbol": symbol, "resolution": resolution})
    key = f"{symbol}_{resolution}"
    return len(_candle_history_mem.get(key, []))


def get_candle_date_range(symbol: str, resolution: str) -> Optional[dict]:
    """Get the earliest and latest timestamp for stored candles."""
    db = get_db()
    if db is not None:
        query = {"symbol": symbol, "resolution": resolution}
        first = db.candles.find_one(query, sort=[("timestamp", 1)])
        last = db.candles.find_one(query, sort=[("timestamp", -1)])
        if first and last:
            return {"first": first["timestamp"], "last": last["timestamp"]}
        return None
    key = f"{symbol}_{resolution}"
    candles = _candle_history_mem.get(key, [])
    if candles:
        return {"first": candles[0].get("timestamp", ""), "last": candles[-1].get("timestamp", "")}
    return None


def ensure_candle_indexes():
    """Create indexes on the candles collection for fast queries."""
    db = get_db()
    if db is None:
        return


def ensure_trades_indexes():
    db = get_db()
    if db:
        db.trades.create_index([("status", 1), ("closed_at", -1)], background=True)
        db.trades.create_index("status", background=True)
        db.trades.create_index("opened_at", -1)
        db.trades.create_index("symbol", background=True)


async def async_calc_closed_stats():
    pipeline = [
        {"$match": {"status": "closed"}},
        {
            "$group": {
                "_id": None,
                "total_count": {"$sum": 1},
                "total_pnl": {"$sum": "$pnl_usd"},
                "win_count": {"$sum": {"$cond": [{"$gte": ["$pnl_usd", 0]}, 1, 0]}},
            }
        },
    ]
    db_conn = get_db()
    if db_conn:
        result = await asyncio.to_thread(list, db_conn.trades.aggregate(pipeline))
        stats = result[0] if result else {"total_count": 0, "total_pnl": 0, "win_count": 0}
    else:
        stats = {"total_count": 0, "total_pnl": 0, "win_count": 0}
    loss_count = stats["total_count"] - stats["win_count"]
    win_rate = round(stats["win_count"] / stats["total_count"] * 100, 1) if stats["total_count"] else 0
    return {
        "total_pnl": round(stats["total_pnl"], 2),
        "win_count": stats["win_count"],
        "loss_count": loss_count,
        "win_rate": win_rate,
        "closed_trades": stats["total_count"],
    }

    db.candles.create_index(
        [("symbol", 1), ("resolution", 1), ("timestamp", 1)],
        unique=True,
        background=True,
    )
    db.candles.create_index(
        [("symbol", 1), ("resolution", 1)],
        background=True,
    )


def ensure_trades_indexes():
    """Create indexes on the trades collection for fast queries."""
    db = get_db()
    if db is None:
        return
    # Index for open/closed status queries
    db.trades.create_index([("status", 1), ("opened_at", 1)], background=True)
    db.trades.create_index([("status", 1), ("closed_at", -1)], background=True)
    # Index for symbol-based queries
    db.trades.create_index([("symbol", 1), ("status", 1)], background=True)
    # Unique index for trade id
    db.trades.create_index([("id", 1)], unique=True, background=True)


# ── Candle Aggregation ────────────────────────────────────────────
# Build larger interval candles from smaller stored ones.

AGGREGATION_MAP = {
    "5": ("1", 5),
    "15": ("5", 3),  # or ("1", 15)
    "30": ("15", 2),  # or ("5", 6)
    "60": ("30", 2),  # or ("15", 4)
    "240": ("60", 4),  # 4H from 1H
    "D": ("60", None),  # daily from hourly — group by date
}


def aggregate_candles(candles: list, target_resolution: str) -> list:
    """
    Aggregate smaller-interval candles into larger ones.
    For "D" (daily): groups by date.
    For numeric resolutions: groups every N candles.
    """
    if not candles:
        return []

    if target_resolution == "D":
        # Group by date
        days: OrderedDict = OrderedDict()
        for c in candles:
            ts = c.get("timestamp", "")
            date_key = ts.split("T")[0] if "T" in ts else ""
            if not date_key:
                continue
            if date_key not in days:
                days[date_key] = {
                    "timestamp": date_key + "T00:00:00",
                    "time": datetime.fromisoformat(date_key).strftime("%m/%d") if len(date_key) == 10 else date_key,
                    "open": c["open"],
                    "high": c["high"],
                    "low": c["low"],
                    "close": c["close"],
                    "volume": c.get("volume", 0),
                }
            else:
                day = days[date_key]
                day["high"] = max(day["high"], c["high"])
                day["low"] = min(day["low"], c["low"])
                day["close"] = c["close"]
                day["volume"] += c.get("volume", 0)
        return list(days.values())

    # Numeric grouping
    try:
        n = int(target_resolution)
    except ValueError:
        return candles

    # Determine source interval from first two timestamps
    if len(candles) >= 2:
        t0 = candles[0].get("timestamp", "")
        t1 = candles[1].get("timestamp", "")
        try:
            dt0 = datetime.fromisoformat(t0)
            dt1 = datetime.fromisoformat(t1)
            src_minutes = max(1, int((dt1 - dt0).total_seconds() / 60))
        except (ValueError, TypeError):
            src_minutes = 1
    else:
        src_minutes = 1

    group_size = max(1, n // src_minutes)
    result = []
    for i in range(0, len(candles), group_size):
        group = candles[i : i + group_size]
        if not group:
            continue
        result.append(
            {
                "timestamp": group[0].get("timestamp", ""),
                "time": group[0].get("time", ""),
                "open": group[0]["open"],
                "high": max(c["high"] for c in group),
                "low": min(c["low"] for c in group),
                "close": group[-1]["close"],
                "volume": sum(c.get("volume", 0) for c in group),
            }
        )
    return result


# ── Event Log ──────────────────────────────────────────────────────
# Persists the last N log entries so they survive restarts.


def save_event_log(events: list, max_entries: int = 200):
    """Persist recent event log entries to DB."""
    db = get_db()
    if db is None:
        return
    # Keep only the most recent entries
    trimmed = events[-max_entries:] if len(events) > max_entries else events
    db.event_log.replace_one(
        {"_id": "log"},
        {"_id": "log", "entries": trimmed, "updated_at": datetime.utcnow().isoformat()},
        upsert=True,
    )


def load_event_log() -> list:
    """Load persisted event log entries from DB."""
    db = get_db()
    if db is None:
        return []
    doc = db.event_log.find_one({"_id": "log"})
    if doc and "entries" in doc:
        return doc["entries"]
    return []


# =============================================================================
# ASYNC WRAPPERS - Non-blocking database operations
# =============================================================================
import asyncio


async def async_load_account() -> dict:
    """Async: Load account state from DB."""
    return await asyncio.to_thread(load_account)


async def async_save_account(account: dict):
    """Async: Persist account state."""
    return await asyncio.to_thread(save_account, account)


async def async_load_open_positions() -> list:
    """Async: Load open positions."""
    return await asyncio.to_thread(load_open_positions)


async def async_load_closed_positions(limit: int = 1000) -> list:
    """Async: Load closed positions."""
    return await asyncio.to_thread(load_closed_positions, limit)


async def async_save_trade(trade: dict):
    """Async: Save trade to DB."""
    return await asyncio.to_thread(save_trade, trade)


async def async_load_candle_history(
    symbol: str,
    resolution: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 0,
) -> list:
    """Async: Load candle history."""
    return await asyncio.to_thread(load_candle_history, symbol, resolution, start, end, limit)


async def async_store_candles(symbol: str, resolution: str, candles: list, source: str = ""):
    """Async: Store candles to history."""
    return await asyncio.to_thread(store_candles, symbol, resolution, candles, source)


async def async_load_candles(symbol: str, resolution: str) -> Optional[dict]:
    """Async: Load cached candles."""
    return await asyncio.to_thread(load_candles, symbol, resolution)


async def async_save_candles(symbol: str, resolution: str, candles: list, source: str):
    """Async: Save candles to cache."""
    return await asyncio.to_thread(save_candles, symbol, resolution, candles, source)


async def async_load_signal_cache_db() -> dict:
    """Async: Load signal cache."""
    return await asyncio.to_thread(load_signal_cache_db)


async def async_save_signal_cache_db(cache: dict):
    """Async: Save signal cache."""
    return await asyncio.to_thread(save_signal_cache_db, cache)


async def async_save_event_log(events: list, max_entries: int = 200):
    """Async: Persist event log."""
    return await asyncio.to_thread(save_event_log, events, max_entries)


async def async_load_event_log() -> list:
    """Async: Load event log."""
    return await asyncio.to_thread(load_event_log)


async def async_count_closed_positions() -> int:
    """Async: Count closed positions."""
    return await asyncio.to_thread(count_closed_positions)


async def async_delete_all_trades():
    """Async: Delete all trades."""
    return await asyncio.to_thread(delete_all_trades)


async def async_count_candles(symbol: str, resolution: str) -> int:
    """Async: Count candles."""
    return await asyncio.to_thread(count_candles, symbol, resolution)


async def async_ensure_trades_indexes():
    """Async: Ensure trades indexes."""
    return await asyncio.to_thread(ensure_trades_indexes)


def sync_account_from_closed_trades_sync() -> dict:
    """Fast sync of account stats from closed trades using MongoDB aggregation.
    Returns stats dict with total_pnl_usd, win_count, loss_count, closed_trades, win_rate.
    """
    db = get_db()
    if db is None:
        return {"total_pnl_usd": 0.0, "win_count": 0, "loss_count": 0, "closed_trades": 0, "win_rate": 0.0}

    pipeline = [
        {"$match": {"status": "closed"}},
        {
            "$group": {
                "_id": None,
                "total_pnl_usd": {"$sum": "$pnl_usd"},
                "win_count": {"$sum": {"$cond": [{"$gte": ["$pnl_usd", 0]}, 1, 0]}},
                "loss_count": {"$sum": {"$cond": [{"$lt": ["$pnl_usd", 0]}, 1, 0]}},
                "closed_trades": {"$sum": 1},
            }
        },
    ]

    result = list(db.trades.aggregate(pipeline))
    if result:
        doc = result[0]
        total = doc.get("closed_trades", 0)
        win_count = doc.get("win_count", 0)
        win_rate = round(win_count / total * 100, 1) if total > 0 else 0.0
        return {
            "total_pnl_usd": round(doc.get("total_pnl_usd", 0.0), 2),
            "win_count": win_count,
            "loss_count": doc.get("loss_count", 0),
            "closed_trades": total,
            "win_rate": win_rate,
        }
    return {"total_pnl_usd": 0.0, "win_count": 0, "loss_count": 0, "closed_trades": 0, "win_rate": 0.0}


async def async_sync_account_from_closed_trades() -> dict:
    """Async: Fast sync of account stats from closed trades using aggregation."""
    return await asyncio.to_thread(sync_account_from_closed_trades_sync)


async def async_get_candle_date_range(symbol: str, resolution: str) -> Optional[dict]:
    """Async: Get candle date range."""
    return await asyncio.to_thread(get_candle_date_range, symbol, resolution)


async def async_save_quote(symbol: str, quote: dict):
    """Async: Save quote to cache."""
    return await asyncio.to_thread(save_quote, symbol, quote)


async def async_load_quote(symbol: str) -> Optional[dict]:
    """Async: Load cached quote."""
    return await asyncio.to_thread(load_quote, symbol)


# =============================================================================
# MMS SEQUENTIALITY STATE
# =============================================================================


def save_mms_state(symbol: str, state: dict):
    """Save MMS sequentiality state for a symbol."""
    try:
        db = get_db()
        if db is None:
            return False
        db.mms_state.update_one(
            {"symbol": symbol}, {"$set": {"state": state, "updated_at": datetime.utcnow()}}, upsert=True
        )
        return True
    except Exception as e:
        print(f"[DB] Error saving MMS state for {symbol}: {e}")
        return False


def load_mms_state(symbol: str) -> Optional[dict]:
    """Load MMS sequentiality state for a symbol."""
    try:
        db = get_db()
        if db is None:
            return None
        doc = db.mms_state.find_one({"symbol": symbol})
        return doc["state"] if doc else None
    except Exception as e:
        print(f"[DB] Error loading MMS state for {symbol}: {e}")
        return None


def load_all_mms_states() -> dict:
    """Load all MMS sequentiality states."""
    try:
        db = get_db()
        if db is None:
            return {}
        states = {}
        for doc in db.mms_state.find():
            states[doc["symbol"]] = doc["state"]
        return states
    except Exception as e:
        print(f"[DB] Error loading all MMS states: {e}")
        return {}


async def async_save_mms_state(symbol: str, state: dict):
    """Async: Save MMS sequentiality state."""
    return await asyncio.to_thread(save_mms_state, symbol, state)


async def async_load_mms_state(symbol: str) -> Optional[dict]:
    """Async: Load MMS sequentiality state."""
    return await asyncio.to_thread(load_mms_state, symbol)


async def async_load_all_mms_states() -> dict:
    """Async: Load all MMS sequentiality states."""
    return await asyncio.to_thread(load_all_mms_states)


# ── Settings ──────────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "MAX_RISK_PER_TRADE_PCT": 2.0,
    "MAX_DRAWDOWN_PCT": 20.0,
    "MAX_OPEN_POSITIONS": 3,
    "INITIAL_BALANCE_USD": 3000.0,
}


def get_setting(key: str, default: Optional[Any] = None) -> Any:
    db = get_db()
    if db is None:
        return DEFAULT_SETTINGS.get(key, default)
    doc = db.settings_current.find_one({"key": key})
    if doc:
        return doc.get("value")
    return DEFAULT_SETTINGS.get(key, default)


def set_setting(key: str, value: Any, updated_by: str = "system") -> bool:
    db = get_db()
    if db is None:
        return False
    now = datetime.utcnow().isoformat()
    old_doc = db.settings_current.find_one({"key": key})
    old_value = old_doc.get("value") if old_doc else None
    db.settings_current.replace_one(
        {"key": key}, {"key": key, "value": value, "updated_at": now, "updated_by": updated_by}, upsert=True
    )
    event_doc = {
        "timestamp": now,
        "key": key,
        "old_value": old_value,
        "new_value": value,
        "updated_by": updated_by,
    }
    db.settings_events.insert_one(event_doc)
    materialize_settings()
    return True


def list_settings() -> dict:
    db = get_db()
    if db is None:
        return DEFAULT_SETTINGS.copy()
    settings = {}
    for doc in db.settings_current.find({}).sort("key", 1):
        settings[doc["key"]] = doc["value"]
    # Migrate missing defaults
    for k, v in DEFAULT_SETTINGS.items():
        if k not in settings:
            set_setting(k, v)
            settings[k] = v
    return settings


def ensure_settings_indexes():
    """Create indexes on settings collections."""
    db = get_db()
    if db is None:
        return
    db.settings_current.create_index([("key", 1)], unique=True, background=True)
    db.settings_events.create_index([("timestamp", -1)], background=True)
    db.settings_events.create_index([("key", 1), ("timestamp", -1)], background=True)


def materialize_settings():
    """Aggregate latest per param from events."""
    db = get_db()
    if db is None:
        return
    pipeline = [{"$sort": {"timestamp": -1}}, {"$group": {"_id": "$key", "doc": {"$first": "$$ROOT"}}}]
    latest_events = list(db.settings_events.aggregate(pipeline))
    for item in latest_events:
        event = item["doc"]
        db.settings_current.replace_one(
            {"key": event["key"]},
            {
                "key": event["key"],
                "value": event["new_value"],
                "updated_at": event["timestamp"],
                "updated_by": event["updated_by"],
            },
            upsert=True,
        )


# Async wrappers
async def async_get_setting(key: str, default: Optional[Any] = None) -> Any:
    return await asyncio.to_thread(get_setting, key, default)


async def async_set_setting(key: str, value: Any, updated_by: str = "system") -> bool:
    return await asyncio.to_thread(set_setting, key, value, updated_by)


async def async_list_settings() -> dict:
    return await asyncio.to_thread(list_settings)
