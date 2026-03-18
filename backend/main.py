"""
CFD Trading Bot - FastAPI Backend
Real-time signal generation using Finnhub data and technical indicators
Simulated trading engine with USD currency
"""
print("[MAIN.PY] Loaded successfully")

import asyncio
import json
import os
import uuid
import signal
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from services.trading_engine import auto_trade_loop
from services.market_data import price_cache_loop
from services.state import broker, account, open_positions, closed_positions, INSTRUMENTS, INITIAL_BALANCE_USD, get_symbol_strategy
import uvicorn

# =============================================================================
# SIGNAL HANDLERS - Debug why process exits
# =============================================================================
# Load env vars BEFORE importing modules that need them
from dotenv import load_dotenv
load_dotenv()

# Use signal handler from utils
from utils.signal import create_signal_handler
_signal_handler = create_signal_handler()

from database import async_load_open_positions, async_sync_account_from_closed_trades
from fastapi import Body, FastAPI, Query, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from timezone import WARSAW_TZ, now_warsaw

import functools

# =============================================================================
# TIMING PROFILER - Performance monitoring
# =============================================================================
import time
from typing import Any, Callable

import database as db
from alpha_vantage import get_async_client
from alpha_vantage import get_client as get_alpha_vantage_client
from alpha_vantage_news import get_client as get_news_client
from database import (
    async_count_candles,
    async_count_closed_positions,
    async_get_candle_date_range,
    async_load_account,
    async_load_candle_history,
    async_load_candles,
    async_load_closed_positions,
    async_load_event_log,
    async_load_open_positions,
    async_load_signal_cache_db,
    async_save_account,
    async_save_candles,
    async_save_event_log,
    async_save_signal_cache_db,
    async_save_trade,
    async_store_candles,
    get_setting,
)
from imessage_alerts import AlertConfig, get_dispatcher, iMessageAlertDispatcher
from indicators import TechnicalIndicators
from models import Component, ComponentType, Signal, SignalDirection, SignalResponse
from openclaw_integration import format_imessage_for_cfd_alert, set_openclaw_message_function
from settings import (
    ACCOUNT_REFRESH_SEC,
    LOGS_REFRESH_SEC,
    NEWS_REFRESH_INTERVAL_SEC,
    PRICE_CACHE_REFRESH_SEC,
    SIGNAL_SCAN_INTERVAL_SEC,
    get_all_settings,
    get_current_broker_settings,
)

from timeframes import TimeFrame, DEFAULT_TIMEFRAME
from strategy import load_strategies_from_file
from strategies import list_strategies as old_list_strategies, mms_on_trade_result

# Use timing stats from services.state
from services.state import _timing_stats



# Timing decorators - NOW IMPORTED FROM utils.decorators
from utils.decorators import async_timed, sync_timed
from app.logging import log_event


# =============================================================================
# LIFESPAN HANDLER - Startup/Shutdown events (replaces deprecated @app.on_event)
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle startup and shutdown events."""
    global _trading_task, alpha_client

    # STARTUP
    log_event("[CFD TRADING BOT v0.2.0 - USD SIMULATION]", "event")
    log_event("Instruments: XAU (Gold), XAG (Silver), US100 (Nasdaq), BTC (Bitcoin)", "info")

    # Database status
    if db.is_connected():
        log_event("MongoDB connected - trades & account persisted", "success")
        log_event(f"Restored {len(open_positions)} open positions, {len(closed_positions)} closed trades", "info")
        
        # Load settings from MongoDB on startup
        from services.state import set_auto_trade_enabled, set_auto_trade_interval, load_strategy_selections_from_db
        
        db_settings = db.list_settings()
        auto_trade_val = db_settings.get("AUTO_TRADE_ENABLED", 0)
        set_auto_trade_enabled(bool(auto_trade_val))
        log_event(f"Loaded AUTO_TRADE_ENABLED={auto_trade_val} from MongoDB", "info")
        
        interval = db_settings.get("AUTO_TRADE_INTERVAL_SEC", 30)
        set_auto_trade_interval(int(interval))
        log_event(f"Loaded AUTO_TRADE_INTERVAL_SEC={interval} from MongoDB", "info")
        
        # Load strategy selections from MongoDB
        load_strategy_selections_from_db()
        log_event("Loaded strategy selections from MongoDB", "info")
        
        db.ensure_candle_indexes()
        log_event("Candle history indexes ensured", "info")
        db.ensure_settings_indexes()
        log_event("Settings indexes ensured & defaults migrated", "info")
        db.ensure_trades_indexes()
        log_event("Trades indexes ensured", "info")
        db.ensure_news_indexes()
        log_event("News indexes ensured (TTL: 60 days)", "info")
        db.ensure_strategy_indexes()
        log_event("Strategy indexes ensured", "info")
        
        # Sync strategies from JSON to DB on startup
        db.sync_strategies_from_json()
        log_event("Strategies synced from JSON to DB", "info")
        
        db.list_settings()  # triggers migration of defaults
        await async_sync_account_from_closed_trades()
    else:
        log_event("MongoDB not configured - using in-memory storage (set MONGO_URI)", "warning")

    alpha_client = get_alpha_vantage_client()
    if alpha_client:
        log_event("Connected to Alpha Vantage API", "success")
    await async_load_signal_cache_db()
    try:
        # Don't block startup with news client - it's not critical
        # get_news_client()  # Disabled to prevent blocking on rate limits
        log_event("News client skipped (using mock data)", "info")
    except Exception as e:
        log_event(f"Failed to initialize news client: {e}", "error")
    # Update global account in services.state
    from services.state import account as state_account
    state_account.update(account)
    account["last_scan"] = datetime.utcnow().isoformat()
    log_event(f"Account loaded: ${account['balance_usd']:.2f} USD", "success")

    # Start autonomous trading loop with watchdog
    _trading_task = None
    
    async def start_auto_trade_with_watchdog():
        """Start auto-trade loop with automatic restart if it crashes or exits."""
        from services.trading_engine import auto_trade_loop
        while True:
            try:
                log_event("[AUTO-TRADE-WATCHDOG] Starting auto-trade loop...", "info")
                await auto_trade_loop()
                # If we get here, loop exited unexpectedly - log it!
                log_event("[AUTO-TRADE-WATCHDOG] Loop exited unexpectedly! Restarting...", "error")
            except Exception as e:
                import traceback
                log_event(f"[AUTO-TRADE-WATCHDOG] Loop crashed: {e}", "error")
                log_event(f"[AUTO-TRADE-WATCHDOG] Traceback: {traceback.format_exc()}", "error")
            finally:
                # Always wait before restart
                log_event("[AUTO-TRADE-WATCHDOG] Waiting 5s before restart...", "info")
                await asyncio.sleep(5)
    
    _trading_task = asyncio.create_task(start_auto_trade_with_watchdog())
    _price_cache_task = asyncio.create_task(price_cache_loop())
    log_event("[AUTO-TRADE] Background task launched (5 min interval)", "success")
    log_event("[PRICE-CACHE] Live price cache started (3 sec refresh)", "success")

    # Start strategy sync background task (every 5 minutes)
    async def strategy_sync_loop():
        """Periodically sync strategies from JSON to DB."""
        while True:
            await asyncio.sleep(300)  # 5 minutes
            try:
                db.sync_strategies_from_json()
                # Reload strategies in memory
                from strategies import reload_strategies
                reload_strategies()
                log_event("[STRATEGY-SYNC] Synced from JSON to DB", "info")
            except Exception as e:
                log_event(f"[STRATEGY-SYNC] Error: {e}", "error")
    
    _strategy_sync_task = asyncio.create_task(strategy_sync_loop())
    log_event("[STRATEGY-SYNC] Background sync started (5 min interval)", "success")

    yield  # App runs here

    # SHUTDOWN
    if _trading_task:
        _trading_task.cancel()
        try:
            await _trading_task
        except asyncio.CancelledError:
            pass
    if _price_cache_task:
        _price_cache_task.cancel()
        try:
            await _price_cache_task
        except asyncio.CancelledError:
            pass
    await async_save_account(account)
    await async_save_event_log(event_log)
    # Skip news client cleanup - it's not critical
    # try:
    #     news_client = get_news_client()
    #     if hasattr(news_client, "close"):
    #         await news_client.close()
    # except Exception:
    #     pass
    log_event("[CFD TRADING BOT] Shutdown complete - state saved", "event")


# =============================================================================

app = FastAPI(
    title="CFD Trading Bot API",
    description="Real-time trading signals for CFD instruments with simulated trading",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app import PLN_USD_RATE, event_log
from services import is_market_open, get_market_hours, update_live_price_cache, get_live_price
from services.state import _live_price_cache, _live_price_cache_last_update, get_signal_history_cache as _get_signal_history_cache, set_signal_history_cache as _set_signal_history_cache
from services.market_data import get_cached_quote, get_cached_candles
from services.strategy_manager import get_strategy_manager, analyze_with_new_strategy
from api.router import router as api_router

# Global state

# Include API routes from router (includes backtest optimization routes)
app.include_router(api_router)

# Enable Dynamic Positions feature
try:
    broker.enable_dynamic_exit(True, decay_threshold=0.25)  # Close if signal drops 25%
    try:
        log_event("[DYNAMIC-POSITIONS] Enabled with 25% decay threshold", "info")
    except:
        print("[DYNAMIC-POSITIONS] Enabled with 25% decay threshold")
except Exception as e:
    try:
        log_event(f"[DYNAMIC-POSITIONS] Not available: {e}", "warning")
    except:
        print(f"[DYNAMIC-POSITIONS] Not available: {e}")

# Convenience references (broker owns this state)
account = broker.get_account()
open_positions = broker.get_open_positions() if hasattr(broker, "open_positions") else []
closed_positions = broker.get_closed_positions() if hasattr(broker, "closed_positions") else []

# For SimulatedBroker, keep direct references to the same lists
if hasattr(broker, "open_positions"):
    open_positions = broker.open_positions
if hasattr(broker, "closed_positions"):
    closed_positions = broker.closed_positions
if hasattr(broker, "account"):
    account = broker.account

# Ensure all USD fields exist (migration for old accounts)
if "balance_usd" not in account:
    account["balance_usd"] = INITIAL_BALANCE_USD
if "equity_usd" not in account:
    account["equity_usd"] = account["balance_usd"]
if "available_usd" not in account:
    account["available_usd"] = account["balance_usd"]
if "used_margin" not in account:
    account["used_margin"] = 0.0
if "peak_balance_usd" not in account:
    account["peak_balance_usd"] = account["balance_usd"]
if "peak_equity_usd" not in account:
    account["peak_equity_usd"] = account["balance_usd"]

# Signal history cache for trend analysis - NOW DELEGATED TO services.state
# signal_history_cache = {}  # Removed - now uses get_signal_history_cache()

# Strategy selection per symbol (default: adaptive_regime)
# NOW DELEGATED TO services.state








# run_backtest imported from backtester
from backtester import run_backtest as _run_backtest

# ============================================================
# Strategy Management Endpoints
# ============================================================

@app.get("/api/strategies/list")
async def list_strategies_api():
    """List all strategies from database."""
    from database import list_strategies_db
    strategies = list_strategies_db()
    return {"strategies": strategies, "count": len(strategies)}


@app.get("/api/strategies/{strategy_id}")
async def get_strategy_api(strategy_id: str):
    """Get a specific strategy from database."""
    from database import get_strategy_from_db
    strategy = get_strategy_from_db(strategy_id)
    if strategy:
        return strategy
    return {"error": f"Strategy {strategy_id} not found"}, 404


@app.post("/api/strategies/sync")
async def sync_strategies_api():
    """Sync strategies from JSON file to database."""
    from database import sync_strategies_from_json
    result = sync_strategies_from_json()
    # Reload strategies in memory
    from strategies import reload_strategies
    reload_strategies()
    return result


@app.post("/api/strategies/reload")
async def reload_strategies_api():
    """Reload strategies into memory from database."""
    from strategies import reload_strategies
    reload_strategies()
    return {"status": "success", "count": len(STRATEGIES)}


@app.put("/api/strategies/{strategy_id}")
async def update_strategy_api(strategy_id: str, config: dict):
    """Update a strategy in database."""
    from database import save_strategy
    config["id"] = strategy_id
    save_strategy(config, updated_by="api")
    # Reload strategies in memory
    from strategies import reload_strategies
    reload_strategies()
    return {"status": "success"}


@app.delete("/api/strategies/{strategy_id}")
async def delete_strategy_api(strategy_id: str):
    """Delete a strategy from database."""
    from database import delete_strategy_from_db
    result = delete_strategy_from_db(strategy_id)
    # Reload strategies in memory
    from strategies import reload_strategies
    reload_strategies()
    return {"status": "success" if result else "not_found"}


# API endpoint for backtest
print("[TEST] backtest endpoint called")
@app.get("/api/backtest")
async def backtest(
    symbol: str = Query(..., description="Symbol to backtest"),
    resolution: str = Query("5", description="Resolution: 1, 5, 15, 30, 60, D"),
    days: int = Query(14, description="Number of days to backtest"),
    date_from: Optional[str] = Query(None, description="Start date"),
    date_to: Optional[str] = Query(None, description="End date"),
    min_score: float = Query(0.3, description="Minimum score threshold"),
    initial_balance: float = Query(3000.0, description="Initial balance"),
    strategy: Optional[str] = Query(None, description="Strategy ID"),
    indicators: Optional[str] = Query(None, description="Indicators"),
    settings: Optional[str] = Query(None, description="Settings"),
    leverage: int = Query(20, description="Leverage"),
    tp_pct: float = Query(0.02, description="Take profit %"),
    sl_pct: float = Query(0.01, description="Stop loss %"),
    risk_pct: float = Query(0.02, description="Risk per trade %"),
    trailing_sl_pct: float = Query(0.0, description="Trailing SL"),
    volume_filter: float = Query(0.0, description="Volume filter"),
    multi_tf: Optional[str] = Query(None, description="Multi-timeframe"),
    htf_rsi_filter: Optional[str] = Query(None, description="HTF RSI"),
    htf_adx_filter: Optional[str] = Query(None, description="HTF ADX"),
    htf_resistance_filter: Optional[str] = Query(None, description="HTF resistance"),
    htf_vwap_filter: Optional[str] = Query(None, description="HTF VWAP"),
    htf_trend_filter: Optional[str] = Query(None, description="HTF trend"),
    adx_filter_mode: Optional[str] = Query(None, description="ADX mode"),
    divergence_filter: Optional[str] = Query(None, description="Divergence"),
    order_block_filter: Optional[str] = Query(None, description="Order block"),
    rsi_weight: Optional[float] = Query(None, description="RSI weight"),
    macd_weight: Optional[float] = Query(None, description="MACD weight"),
    stoch_weight: Optional[float] = Query(None, description="Stoch weight"),
    momentum_weight: Optional[float] = Query(None, description="Momentum weight"),
    adx_weight: Optional[float] = Query(None, description="ADX weight"),
    bb_weight: Optional[float] = Query(None, description="BB weight"),
):
    """Run backtest on historical data"""
    # Call the main run_backtest function (defined later in this file)
    return await run_backtest(
        symbol=symbol, resolution=resolution, days=days,
        date_from=date_from, date_to=date_to,
        min_score=min_score, initial_balance=initial_balance,
        strategy_name=strategy, indicators=indicators, settings=settings,
        leverage=leverage, tp_pct=tp_pct, sl_pct=sl_pct,
        risk_pct=risk_pct, trailing_sl_pct=trailing_sl_pct,
        volume_filter=volume_filter, multi_tf=multi_tf,
        htf_rsi_filter=htf_rsi_filter, htf_adx_filter=htf_adx_filter,
        htf_resistance_filter=htf_resistance_filter,
        htf_vwap_filter=htf_vwap_filter, htf_trend_filter=htf_trend_filter,
        adx_filter_mode=adx_filter_mode, divergence_filter=divergence_filter,
        order_block_filter=order_block_filter,
        rsi_weight=rsi_weight, macd_weight=macd_weight,
        stoch_weight=stoch_weight, momentum_weight=momentum_weight,
        adx_weight=adx_weight, bb_weight=bb_weight,
    )

async def run_backtest(
    symbol: str,
    resolution: str = "5",
    days: int = 14,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    min_score: float = 0.15,
    initial_balance: float = 3000.0,
    strategy_name: Optional[str] = None,
    indicators: Optional[str] = None,
    settings: Optional[str] = None,
    leverage: int = 10,
    tp_pct: float = 0.05,
    sl_pct: float = 0.02,
    risk_pct: float = 0.02,
    trailing_sl_pct: float = 0.0,
    volume_filter: float = 0.0,
    multi_tf: Optional[str] = None,
    htf_rsi_filter: Optional[str] = None,
    htf_adx_filter: Optional[str] = None,
    htf_resistance_filter: Optional[str] = None,
    htf_vwap_filter: Optional[str] = None,
    htf_trend_filter: Optional[str] = None,
    adx_filter_mode: Optional[str] = None,
    divergence_filter: Optional[str] = None,
    order_block_filter: Optional[str] = None,
    rsi_weight: Optional[float] = None,
    macd_weight: Optional[float] = None,
    stoch_weight: Optional[float] = None,
    momentum_weight: Optional[float] = None,
    adx_weight: Optional[float] = None,
    bb_weight: Optional[float] = None,
):
    """
    Run backtest on historical data.
    Returns all trades and performance metrics.

    If strategy/indicators not provided, uses per-symbol defaults from DB.
    """
    import time
    start_time = time.time()

    from database import get_db

    # Build strategy weights dict if any provided
    custom_weights = {}
    if rsi_weight is not None:
        custom_weights['rsi'] = rsi_weight
    if macd_weight is not None:
        custom_weights['macd'] = macd_weight
    if stoch_weight is not None:
        custom_weights['stoch'] = stoch_weight
    if momentum_weight is not None:
        custom_weights['momentum'] = momentum_weight
    if adx_weight is not None:
        custom_weights['adx'] = adx_weight
    if bb_weight is not None:
        custom_weights['bb'] = bb_weight

    # Get candles from DB
    symbol_key = symbol.upper()
    if symbol_key not in INSTRUMENTS:
        return {"error": f"Unknown symbol: {symbol}"}

    # Validate strategy if provided
    if strategy_name:
        from strategies import STRATEGIES

        if strategy_name not in STRATEGIES:
            return {"error": f"Unknown strategy: {strategy_name}. Available: {list(STRATEGIES.keys())}"}
        strategy_id = strategy_name
    else:
        strategy_id = get_symbol_strategy(symbol_key)

    from strategies import get_strategy
    strategy = get_strategy(strategy_id)
    instrument_info = INSTRUMENTS.get(symbol_key, {})

    # Override TP/SL, leverage, risk from JSON strategy config
    print(f"[DEBUG] strategy_id={strategy_id}, checking if not in ['adaptive_regime', 'mms']: {strategy_id and strategy_id not in ['adaptive_regime', 'mms']}")
    if strategy_id and strategy_id not in ['adaptive_regime', 'mms']:
        try:
            print(f"[DEBUG] Has strategy.config: {hasattr(strategy, 'config')}")
            if hasattr(strategy, 'config') and strategy.config:
                print(f"[DEBUG] Config keys: {list(strategy.config.keys())}")
                # Get exits config
                exits = strategy.config.get('exits', {})
                if exits:
                    tp_val = exits.get('take_profit', {}).get('value', 0)
                    sl_val = exits.get('stop_loss', {}).get('value', 0)
                    if tp_val:
                        tp_pct = abs(tp_val) / 100
                    if sl_val:
                        sl_pct = abs(sl_val) / 100
                
                # Get risk config (leverage, risk_per_trade)
                risk = strategy.config.get('risk', {})
                if risk:
                    if 'leverage' in risk:
                        leverage = risk.get('leverage', 20)
                    if 'risk_per_trade_pct' in risk:
                        risk_pct = risk.get('risk_per_trade_pct', 2.0) / 100  # Convert % to decimal
                
                # Get min_score from strategy score config
                score_cfg = strategy.config.get('score', {})
                if score_cfg and 'min_score' in score_cfg:
                    min_score = score_cfg.get('min_score', 0.3)
                    
                print(f"[BACKTEST] Using strategy config: leverage={leverage}, risk_pct={risk_pct}, min_score={min_score}, tp_pct={tp_pct}, sl_pct={sl_pct}")
        except Exception as e:
            print(f"[BACKTEST] Error loading strategy config: {e}")
            pass  # Use defaults if anything fails

    # Parse custom settings if provided (e.g., "rsi_period=14,macd_fast=12")
    custom_settings = {}
    if settings:
        try:
            for pair in settings.split(","):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    custom_settings[k.strip()] = v.strip()
        except Exception:
            pass  # Ignore invalid settings

    # Apply custom settings to strategy
    if custom_settings:
        for ind in strategy.default_indicators:
            if hasattr(ind, "settings") and ind.settings:
                for key in list(ind.settings.keys()):
                    # Map frontend keys to settings keys
                    mapping = {
                        "rsi_period": "period",
                        "rsi_overbought": "overbought",
                        "rsi_oversold": "oversold",
                        "macd_fast": "fast",
                        "macd_slow": "slow",
                        "macd_signal": "signal",
                        "bb_period": "period",
                        "bb_std": "std",
                    }
                    frontend_key = f"{ind.id.lower()}_{key}"
                    if frontend_key in custom_settings:
                        try:
                            val = custom_settings[frontend_key]
                            # Try to convert to int/float
                            if "." in val:
                                ind.settings[key] = float(val)
                            else:
                                ind.settings[key] = int(val)
                        except Exception:
                            pass

    # Parse indicators if provided
    if indicators:
        enabled_indicators = [ind.strip().upper() for ind in indicators.split(",")]
    else:
        # Try to get from DB, otherwise use strategy defaults
        enabled_key = f"INDICATORS_{symbol_key}"
        db_indicators = get_setting(enabled_key)
        if db_indicators:
            enabled_indicators = db_indicators
        else:
            # Use all indicators from strategy
            enabled_indicators = strategy.get_enabled_indicators()

    # Get candles from DB
    end_dt = datetime.utcnow()
    start_dt = end_dt - timedelta(days=days)
    
    # Override with specific dates if provided
    if date_from:
        try:
            start_dt = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        except:
            pass
    if date_to:
        try:
            end_dt = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
        except:
            pass
    
    db = get_db()
    cursor = db.candles.find(
        {"symbol": symbol_key, "resolution": resolution, "timestamp": {"$gte": start_dt.isoformat()}}
    ).sort("timestamp", 1)

    candles = list(cursor)
    if not candles:
        return {"error": f"No candles found for {symbol_key} {resolution}"}

    if len(candles) < 50:
        return {"error": f"Not enough candles: {len(candles)}"}

    print(f"[BACKTEST] Processing {len(candles)} candles for {symbol_key} {resolution}")

    candles = [
        {
            "timestamp": c.get("timestamp"),
            "open": c.get("open"),
            "high": c.get("high"),
            "low": c.get("low"),
            "close": c.get("close"),
            "volume": c.get("volume"),
        }
        for c in candles
    ]

    # Run backtest
    balance = initial_balance
    peak_balance = initial_balance
    trades = []
    open_trade = None
    
    # Parse HTF RSI filter parameter
    htf_rsi_res = None
    htf_rsi_candles = []
    if htf_rsi_filter:
        htf_rsi_res = htf_rsi_filter.strip()
        tf_cursor = db.candles.find(
            {"symbol": symbol_key, "resolution": htf_rsi_res, "timestamp": {"$gte": start_dt.isoformat()}}
        ).sort("timestamp", 1)
        htf_rsi_candles = list(tf_cursor)
        if htf_rsi_candles:
            print(f"[BACKTEST] HTF RSI filter: {htf_rsi_res}, {len(htf_rsi_candles)} candles")
    
    # Parse HTF ADX filter parameter
    htf_adx_res = None
    htf_adx_candles = []
    if htf_adx_filter:
        htf_adx_res = htf_adx_filter.strip()
        tf_cursor = db.candles.find(
            {"symbol": symbol_key, "resolution": htf_adx_res, "timestamp": {"$gte": start_dt.isoformat()}}
        ).sort("timestamp", 1)
        htf_adx_candles = list(tf_cursor)
        if htf_adx_candles:
            print(f"[BACKTEST] HTF ADX filter: {htf_adx_res}, {len(htf_adx_candles)} candles")
    
    # Parse HTF resistance filter parameter
    htf_res_res = None
    htf_res_candles = []
    if htf_resistance_filter:
        htf_res_res = htf_resistance_filter.strip()
        tf_cursor = db.candles.find(
            {"symbol": symbol_key, "resolution": htf_res_res, "timestamp": {"$gte": start_dt.isoformat()}}
        ).sort("timestamp", 1)
        htf_res_candles = list(tf_cursor)
        if htf_res_candles:
            print(f"[BACKTEST] HTF Resistance filter: {htf_res_res}, {len(htf_res_candles)} candles")
    
    # Parse HTF VWAP filter parameter
    htf_vwap_res = None
    htf_vwap_candles = []
    if htf_vwap_filter:
        htf_vwap_res = htf_vwap_filter.strip()
        tf_cursor = db.candles.find(
            {"symbol": symbol_key, "resolution": htf_vwap_res, "timestamp": {"$gte": start_dt.isoformat()}}
        ).sort("timestamp", 1)
        htf_vwap_candles = list(tf_cursor)
        if htf_vwap_candles:
            print(f"[BACKTEST] HTF VWAP filter: {htf_vwap_res}, {len(htf_vwap_candles)} candles")
    
    # Parse HTF trend filter parameter (SIMPLE: RSI > 50 = long, RSI < 50 = short)
    htf_trend_res = None
    htf_trend_candles = []
    if htf_trend_filter:
        htf_trend_res = htf_trend_filter.strip()
        tf_cursor = db.candles.find(
            {"symbol": symbol_key, "resolution": htf_trend_res, "timestamp": {"$gte": start_dt.isoformat()}}
        ).sort("timestamp", 1)
        htf_trend_candles = list(tf_cursor)
        if htf_trend_candles:
            print(f"[BACKTEST] HTF Trend filter: {htf_trend_res}, {len(htf_trend_candles)} candles")
    
    # Parse multi-timeframe parameter
    multi_tf_resolutions = []
    multi_tf_candles = {}
    if multi_tf:
        multi_tf_resolutions = [r.strip() for r in multi_tf.split(',') if r.strip()]
        print(f"[BACKTEST] Multi-TF enabled: {multi_tf_resolutions}")
        
        # Get candles for additional timeframes from DB
        if multi_tf_resolutions:
            for tf_res in multi_tf_resolutions:
                tf_cursor = db.candles.find(
                    {"symbol": symbol_key, "resolution": tf_res, "timestamp": {"$gte": start_dt.isoformat()}}
                ).sort("timestamp", 1)
                tf_candles = list(tf_cursor)
                if tf_candles:
                    multi_tf_candles[tf_res] = [
                        {"timestamp": c.get("timestamp"), "close": c.get("close"), "volume": c.get("volume")}
                        for c in tf_candles
                    ]
                    print(f"[BACKTEST] Loaded {len(multi_tf_candles[tf_res])} candles for {tf_res}")

    # Calculate indicators and signals for each candle
    for i in range(50, len(candles)):  # Need 50 candles for warmup
        candle_window = candles[max(0, i - 50) : i]
        current_candle = candles[i]

        if len(candle_window) < 50:
            continue

        # Calculate indicators
        try:
            indicators = TechnicalIndicators.calculate_all(candle_window, period=14)
            current_price = current_candle.get("close", 0)
            if current_price <= 0:
                continue
        except Exception:
            continue

        # Use actual strategy to generate signal
        try:
            result = strategy.score(candle_window, indicators, symbol_key, instrument_info, current_price, custom_weights=custom_weights if custom_weights else None)
            score = result.get("score", 0)
            direction = result.get("direction")
            tp = result.get("take_profit")
            sl = result.get("stop_loss")
        except Exception as e:
            print(f"[BACKTEST] Error at candle {i}: {e}")
            continue

        # Debug: log score and direction every 50 candles
        if i % 50 == 0:
            print(f"[BACKTEST] candle {i}: score={score}, direction={direction}")

        # Use score to determine direction (more flexible than strategy's direction)
        direction_str = None
        if score >= min_score:
            direction_str = "buy"
        elif score <= -min_score:
            direction_str = "sell"

        # Check if score meets threshold and we don't have open trade
        if direction_str and open_trade is None:
            # Check volume filter if enabled
            if volume_filter > 0:
                try:
                    # Safety check: ensure candles is defined and has data
                    if 'candles' not in dir() or not candles or len(candles) < i:
                        raise ValueError(f"Candles not available or insufficient: len={len(candles) if 'candles' in dir() else 'N/A'}, i={i}")
                    
                    current_volume = current_candle.get("volume", 0)
                    if current_volume is None:
                        current_volume = 0
                    # Calculate average volume from last 20 candles
                    start_idx = max(0, i - 20)
                    volumes = []
                    for c in candles[start_idx:i]:
                        v = c.get("volume", 0)
                        if v is not None and v > 0:
                            volumes.append(v)
                    avg_volume = sum(volumes) / len(volumes) if volumes else 0
                    if avg_volume > 0 and current_volume < avg_volume * volume_filter:
                        direction_str = None  # Skip this signal due to low volume
                except Exception as e:
                    print(f"[BACKTEST] Volume filter error at i={i}: {e}")
                    # Don't fail the whole backtest - just skip filtering
            
            # Check multi-timeframe alignment if enabled
            if multi_tf_candles and direction_str:
                try:
                    # Get current timestamp
                    current_ts = current_candle.get("timestamp", "")
                    
                    # Check each additional timeframe
                    tf_agrees = True
                    for tf_res, tf_candles_list in multi_tf_candles.items():
                        if not tf_candles_list:
                            continue
                        
                        # Find closest candle in this timeframe
                        tf_direction = None
                        for j, tc in enumerate(tf_candles_list):
                            if tc.get("timestamp", "") >= current_ts:
                                if j > 0:
                                    prev = tf_candles_list[j-1]
                                    curr = tc
                                    # Simple direction check: compare close prices
                                    if curr.get("close", 0) > prev.get("close", 0):
                                        tf_direction = "buy"
                                    elif curr.get("close", 0) < prev.get("close", 0):
                                        tf_direction = "sell"
                                break
                        
                        # Check if this timeframe agrees
                        if tf_direction and tf_direction != direction_str:
                            tf_agrees = False
                            break
                    
                    if not tf_agrees:
                        direction_str = None  # Skip - timeframes don't agree
                        print(f"[BACKTEST] Multi-TF: Skipping {symbol_key} at i={i} - timeframes don't align")
                except Exception as e:
                    print(f"[BACKTEST] Multi-TF error: {e}")
            
            # HTF RSI Filter - skip trade if higher timeframe RSI is extreme
            if htf_rsi_candles and direction_str:
                try:
                    current_ts = current_candle.get("timestamp", "")
                    for j, tc in enumerate(htf_rsi_candles):
                        if tc.get("timestamp", "") >= current_ts:
                            if j > 0:
                                window = htf_rsi_candles[max(0, j-14):j]
                                if len(window) >= 14:
                                    closes = [c.get("close", 0) for c in window]
                                    if closes and all(c > 0 for c in closes):
                                        gains = []
                                        losses = []
                                        for k in range(1, len(closes)):
                                            diff = closes[k] - closes[k-1]
                                            if diff > 0:
                                                gains.append(diff)
                                            else:
                                                losses.append(abs(diff))
                                        avg_gain = sum(gains) / 14 if gains else 0
                                        avg_loss = sum(losses) / 14 if losses else 0
                                        rs = avg_gain / avg_loss if avg_loss > 0 else 100
                                        rsi = 100 - (100 / (1 + rs))
                                        
                                        # Skip if HTF RSI is extreme
                                        if (direction_str == "buy" and rsi > 70) or (direction_str == "sell" and rsi < 30):
                                            print(f"[BACKTEST] HTF RSI {rsi:.0f} extreme - SKIPPING trade")
                                            direction_str = None
                            break
                except Exception as e:
                    pass  # Continue on error
            
            # HTF ADX Filter - skip if no trend
            if htf_adx_candles and direction_str:
                try:
                    current_ts = current_candle.get("timestamp", "")
                    for j, tc in enumerate(htf_adx_candles):
                        if tc.get("timestamp", "") >= current_ts:
                            if j > 14:
                                window = htf_adx_candles[j-14:j]
                                highs = [c.get("high", 0) for c in window]
                                lows = [c.get("low", 0) for c in window]
                                closes = [c.get("close", 0) for c in window]
                                
                                if highs and lows and closes and all(h > 0 and l > 0 and c > 0 for h,l,c in zip(highs, lows, closes)):
                                    plus_dm = []
                                    minus_dm = []
                                    for k in range(1, len(window)):
                                        high_diff = highs[k] - highs[k-1]
                                        low_diff = lows[k-1] - lows[k]
                                        if high_diff > low_diff and high_diff > 0:
                                            plus_dm.append(high_diff)
                                            minus_dm.append(0)
                                        elif low_diff > high_diff and low_diff > 0:
                                            plus_dm.append(0)
                                            minus_dm.append(low_diff)
                                        else:
                                            plus_dm.append(0)
                                            minus_dm.append(0)
                                    
                                    tr = []
                                    for k in range(1, len(window)):
                                        h, l, pc = highs[k], lows[k], closes[k-1]
                                        tr.append(max(h-l, abs(h-pc), abs(l-pc)))
                                    
                                    atr = sum(tr) / 14 if tr else 1
                                    plus_di = (sum(plus_dm) / 14 / atr * 100) if atr > 0 else 0
                                    minus_di = (sum(minus_dm) / 14 / atr * 100) if atr > 0 else 0
                                    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0
                                    
                                    if dx < 20:
                                        print(f"[BACKTEST] HTF ADX {dx:.0f} < 20 - SKIP (no trend)")
                                        direction_str = None
                            break
                except Exception as e:
                    pass
            
            # HTF Resistance Filter - reduce TP if price near HTF extremes
            if htf_res_candles and direction_str and tp_pct > 0:
                try:
                    current_ts = current_candle.get("timestamp", "")
                    for j, tc in enumerate(htf_res_candles):
                        if tc.get("timestamp", "") >= current_ts:
                            if j > 0:
                                window = htf_res_candles[max(0, j-20):j]
                                htf_high = max(c.get("high", 0) for c in window)
                                htf_low = min(c.get("low", 0) for c in window)
                                htf_range = htf_high - htf_low
                                
                                if htf_range > 0 and current_price > 0:
                                    dist_to_high = (htf_high - current_price) / htf_range
                                    dist_to_low = (current_price - htf_low) / htf_range
                                    
                                    if direction_str == "buy" and dist_to_high < 0.1:
                                        tp_pct = tp_pct * 0.7
                                        print(f"[BACKTEST] Near HTF high - TP to {tp_pct*100:.1f}%")
                                    elif direction_str == "sell" and dist_to_low < 0.1:
                                        tp_pct = tp_pct * 0.7
                                        print(f"[BACKTEST] Near HTF low - TP to {tp_pct*100:.1f}%")
                            break
                except Exception as e:
                    pass
            
            # HTF VWAP Filter - only trade when price is moving toward VWAP
            if htf_vwap_candles and direction_str:
                try:
                    current_ts = current_candle.get("timestamp", "")
                    for j, tc in enumerate(htf_vwap_candles):
                        if tc.get("timestamp", "") >= current_ts:
                            if j > 14:
                                # Calculate VWAP for last 20 candles
                                window = htf_vwap_candles[j-20:j]
                                cum_vol = 0
                                cum_pv = 0
                                for c in window:
                                    h = c.get("high", 0)
                                    l = c.get("low", 0)
                                    c_ = c.get("close", 0)
                                    v = c.get("volume", 0)
                                    if h > 0 and l > 0 and c_ > 0 and v > 0:
                                        typical_price = (h + l + c_) / 3
                                        cum_pv += typical_price * v
                                        cum_vol += v
                                
                                vwap = cum_pv / cum_vol if cum_vol > 0 else 0
                                
                                if vwap > 0 and current_price > 0:
                                    # Check if price is on the "right side" of VWAP
                                    # Buy only if price > VWAP (bullish) or just crossed above
                                    # Sell only if price < VWAP (bearish) or just crossed below
                                    
                                    # Get previous candle
                                    prev_candle = htf_vwap_candles[j-1] if j > 0 else None
                                    prev_vwap = None
                                    if prev_candle and j > 15:
                                        prev_window = htf_vwap_candles[j-21:j-1]
                                        prev_cum_vol = 0
                                        prev_cum_pv = 0
                                        for c in prev_window:
                                            h = c.get("high", 0)
                                            l = c.get("low", 0)
                                            c_ = c.get("close", 0)
                                            v = c.get("volume", 0)
                                            if h > 0 and l > 0 and c_ > 0 and v > 0:
                                                typical_price = (h + l + c_) / 3
                                                prev_cum_pv += typical_price * v
                                                prev_cum_vol += v
                                        prev_vwap = prev_cum_pv / prev_cum_vol if prev_cum_vol > 0 else 0
                                    
                                    # VWAP direction
                                    vwap_up = current_price > vwap
                                    prev_vwap_up = prev_vwap is not None and prev_vwap > 0 and prev_candle.get("close", 0) > prev_vwap if prev_vwap else False
                                    
                                    # Trade with VWAP trend
                                    if direction_str == "buy":
                                        # For buy: price should be above VWAP or crossing above
                                        if current_price < vwap and not (prev_vwap and prev_candle.get("close", 0) < prev_vwap):
                                            print(f"[BACKTEST] HTF VWAP: price below VWAP ({current_price} < {vwap:.0f}) - SKIP")
                                            direction_str = None
                                    elif direction_str == "sell":
                                        # For sell: price should be below VWAP or crossing below
                                        if current_price > vwap and not (prev_vwap and prev_candle.get("close", 0) > prev_vwap):
                                            print(f"[BACKTEST] HTF VWAP: price above VWAP ({current_price} > {vwap:.0f}) - SKIP")
                                            direction_str = None
                            break
                except Exception as e:
                    pass
            
            # Simple HTF Trend Filter - SOFT filter (adjust min_score, not block)
            # Long: HTF RSI > 50, Short: HTF RSI < 50
            # This uses CLOSED HTF candle to avoid look-ahead bias
            if htf_trend_candles and direction_str:
                try:
                    # Find the LAST CLOSED HTF candle (not current one - avoid look-ahead)
                    current_ts = current_candle.get("timestamp", "")
                    htf_index = None
                    for j, tc in enumerate(htf_trend_candles):
                        if tc.get("timestamp", "") >= current_ts:
                            htf_index = max(0, j - 1)  # Use PREVIOUS closed candle
                            break
                    
                    if htf_index is not None and htf_index > 14:
                        window = htf_trend_candles[max(0, htf_index-14):htf_index]
                        closes = [c.get("close", 0) for c in window]
                        if closes and all(c > 0 for c in closes):
                            gains = []
                            losses = []
                            for k in range(1, len(closes)):
                                diff = closes[k] - closes[k-1]
                                if diff > 0:
                                    gains.append(diff)
                                else:
                                    losses.append(abs(diff))
                            avg_gain = sum(gains) / 14 if gains else 0
                            avg_loss = sum(losses) / 14 if losses else 0
                            rs = avg_gain / avg_loss if avg_loss > 0 else 100
                            htf_rsi = 100 - (100 / (1 + rs))
                            
                            # Soft filter: if trading against HTF trend, require HIGHER score
                            if direction_str == "buy" and htf_rsi < 45:
                                # HTF bearish, but we want to buy - require stronger signal
                                min_score_adjusted = min_score * 2  # Double the threshold
                                if abs(score) < min_score_adjusted:
                                    print(f"[BACKTEST] HTF Trend: RSI={htf_rsi:.0f} < 45, need stronger signal - SKIP")
                                    direction_str = None
                            elif direction_str == "sell" and htf_rsi > 55:
                                # HTF bullish, but we want to sell - require stronger signal
                                min_score_adjusted = min_score * 2
                                if abs(score) < min_score_adjusted:
                                    print(f"[BACKTEST] HTF Trend: RSI={htf_rsi:.0f} > 55, need stronger signal - SKIP")
                                    direction_str = None
                except Exception as e:
                    pass
            
            # Divergence Filter - check for price/indicator divergence
            if divergence_filter and direction_str:
                try:
                    div_indicator = divergence_filter.upper().strip()
                    if div_indicator in ["RSI", "MACD", "STOCH"]:
                        # Get indicator values
                        if div_indicator == "RSI":
                            rsi_val = indicators.get("RSI", {}).get("value", 50)
                            # Need previous RSI from earlier in window
                            if i > 60:
                                prev_indicators = TechnicalIndicators.calculate_all(candle_window[:-1], period=14)
                                prev_rsi = prev_indicators.get("RSI", {}).get("value", 50)
                                
                                # Check divergence
                                prev_price = candle_window[-2].get("close", 0) if len(candle_window) > 1 else current_price
                                
                                # Bearish divergence: price higher, RSI lower
                                if direction_str == "buy" and current_price > prev_price and rsi_val < prev_rsi:
                                    print(f"[BACKTEST] Divergence: bearish - SKIP")
                                    direction_str = None
                                # Bullish divergence: price lower, RSI higher
                                elif direction_str == "sell" and current_price < prev_price and rsi_val > prev_rsi:
                                    print(f"[BACKTEST] Divergence: bullish - SKIP")
                                    direction_str = None
                except Exception as e:
                    pass
            
            # Order Block Filter - only trade from order blocks
            if order_block_filter and direction_str:
                try:
                    # Look for recent order block (last 5 candles)
                    for ob_idx in range(max(1, i-5), i):
                        if ob_idx < len(candles):
                            ob_candle = candles[ob_idx]
                            ob_close = ob_candle.get("close", 0)
                            ob_open = ob_candle.get("open", 0)
                            ob_is_green = ob_close > ob_open
                            
                            # Check if price is returning to OB zone
                            if direction_str == "buy" and ob_is_green:
                                # Green OB = buy order block, look for price return to it
                                ob_high = ob_candle.get("high", 0)
                                if current_price >= ob_high * 0.99 and current_price <= ob_high * 1.02:
                                    # Price at or near OB high - good entry
                                    pass
                            elif direction_str == "sell" and not ob_is_green:
                                ob_low = ob_candle.get("low", 0)
                                if current_price <= ob_low * 1.01 and current_price >= ob_low * 0.98:
                                    # Price at or near OB low - good entry
                                    pass
                            else:
                                # Price not at OB - skip
                                if direction_str == "buy":
                                    print(f"[BACKTEST] Order Block: price not at buy OB - SKIP")
                                    direction_str = None
                                else:
                                    print(f"[BACKTEST] Order Block: price not at sell OB - SKIP")
                                    direction_str = None
                            break
                except Exception as e:
                    pass
            
            # Open trade with leverage
            if direction_str:
                price = current_price
                risk_amount = balance * risk_pct
                # With leverage: size = (balance * risk_pct * leverage) / price
                size = (risk_amount * leverage) / price

                open_trade = {
                    "id": str(uuid.uuid4())[:8],
                    "symbol": symbol_key,
                    "direction": direction_str,
                    "entry_price": price,
                    "size": size,
                    "leverage": leverage,
                    "risk_pct": risk_pct,
                    "tp_pct": tp_pct,
                    "sl_pct": sl_pct,
                    "trailing_sl_pct": trailing_sl_pct,
                    "trailing_sl_activated": False,
                    "opened_at": current_candle.get("timestamp", ""),
                    "opened_at_candle": i,  # Track which candle we opened at
                    "balance_at_entry": balance,
                    "tp": tp,
                    "sl": sl,
                }

        # Check close conditions
        if open_trade:
            price = current_candle.get("close", 0)
            entry = open_trade["entry_price"]
            direction = open_trade["direction"]
            tp_pct = open_trade.get("tp_pct", 0.02)
            sl_pct = open_trade.get("sl_pct", 0.01)
            trailing_sl_pct = open_trade.get("trailing_sl_pct", 0)
            trailing_sl_activated = open_trade.get("trailing_sl_activated", False)
            
            # Dynamic TP adjustment based on HTF (only adjust, never increase TP)
            original_tp_pct = tp_pct
            if htf_rsi_candles:
                try:
                    current_ts = current_candle.get("timestamp", "")
                    for j, tc in enumerate(htf_rsi_candles):
                        if tc.get("timestamp", "") >= current_ts:
                            if j > 14:
                                window = htf_rsi_candles[j-14:j]
                                closes = [c.get("close", 0) for c in window]
                                if closes and all(c > 0 for c in closes):
                                    gains = []
                                    losses = []
                                    for k in range(1, len(closes)):
                                        diff = closes[k] - closes[k-1]
                                        if diff > 0:
                                            gains.append(diff)
                                        else:
                                            losses.append(abs(diff))
                                    avg_gain = sum(gains) / 14 if gains else 0
                                    avg_loss = sum(losses) / 14 if losses else 0
                                    rs = avg_gain / avg_loss if avg_loss > 0 else 100
                                    rsi = 100 - (100 / (1 + rs))
                                    
                                    # Adjust TP based on HTF RSI (only reduce, never increase)
                                    if direction == "buy" and rsi > 65:
                                        tp_pct = min(tp_pct, 0.03)  # Reduce TP if overbought
                                    elif direction == "buy" and rsi < 40:
                                        tp_pct = max(tp_pct, 0.06)  # Increase TP if oversold (more room)
                                    elif direction == "sell" and rsi < 35:
                                        tp_pct = min(tp_pct, 0.03)
                                    elif direction == "sell" and rsi > 60:
                                        tp_pct = max(tp_pct, 0.06)
                except Exception as e:
                    pass
            
            # Update trade with adjusted TP
            open_trade["tp_pct"] = tp_pct

            # Use percentage-based TP/SL
            tp_price = entry * (1 + tp_pct) if direction == "buy" else entry * (1 - tp_pct)
            sl_price = entry * (1 - sl_pct) if direction == "buy" else entry * (1 + sl_pct)

            closed = False
            pnl = 0

            # Calculate current profit/loss %
            if direction == "buy":
                profit_pct = (price - entry) / entry
            else:
                profit_pct = (entry - price) / entry

            # Trailing SL: if profit > trailing_sl_pct, move SL to breakeven
            if trailing_sl_pct > 0 and not trailing_sl_activated and profit_pct >= trailing_sl_pct:
                # Activate trailing SL - move SL to breakeven
                trailing_sl_activated = True
                if direction == "buy":
                    sl_price = entry  # Move SL to entry price
                else:
                    sl_price = entry  # Move SL to entry price
                open_trade["trailing_sl_activated"] = True
                open_trade["trailing_sl_price"] = sl_price
            elif trailing_sl_activated:
                # Update trailing SL - move it up as price moves
                if direction == "buy":
                    new_sl = entry + (price - entry) * 0.5  # Keep 50% of profits
                    if new_sl > sl_price:
                        sl_price = new_sl
                        open_trade["trailing_sl_price"] = sl_price
                else:
                    new_sl = entry - (entry - price) * 0.5
                    if new_sl < sl_price:
                        sl_price = new_sl
                        open_trade["trailing_sl_price"] = sl_price

            if direction == "buy":
                if price >= tp_price:  # TP
                    pnl = (price - entry) * open_trade["size"]
                    closed = True
                elif price <= sl_price:  # SL (or trailing SL)
                    pnl = (price - entry) * open_trade["size"]
                    closed = True
            else:  # sell
                if price <= tp_price:  # TP
                    pnl = (entry - price) * open_trade["size"]
                    closed = True
                elif price >= sl_price:  # SL (or trailing SL)
                    pnl = (entry - price) * open_trade["size"]
                    closed = True

            if closed:
                balance += pnl
                peak_balance = max(peak_balance, balance)

                trade_result = {
                    **open_trade,
                    "exit_price": price,
                    "closed_at": current_candle.get("timestamp", ""),
                    "pnl_usd": pnl,
                    "result": "win" if pnl > 0 else "loss",
                }
                trades.append(trade_result)
                open_trade = None
            else:
                # Close position if open for too long (max 4 hours / 240 minutes of candles)
                candles_open = i - open_trade.get("opened_at_candle", i)
                if candles_open > 240:  # 240 candles = 4 hours for 1min resolution
                    # Close at market price
                    pnl = 0
                    if direction == "buy":
                        pnl = (price - entry) * open_trade["size"]
                    else:
                        pnl = (entry - price) * open_trade["size"]
                    balance += pnl
                    trade_result = {
                        **open_trade,
                        "exit_price": price,
                        "closed_at": current_candle.get("timestamp", ""),
                        "pnl_usd": pnl,
                        "result": "win" if pnl > 0 else ("loss" if pnl < 0 else "breakeven"),
                    }
                    trades.append(trade_result)
                    open_trade = None

    # Close any remaining open positions at last candle price
    if open_trade:
        last_price = candles[-1].get("close", 0)
        entry = open_trade["entry_price"]
        direction = open_trade["direction"]
        if direction == "buy":
            pnl = (last_price - entry) * open_trade["size"]
        else:
            pnl = (entry - last_price) * open_trade["size"]
        balance += pnl
        trade_result = {
            **open_trade,
            "exit_price": last_price,
            "closed_at": candles[-1].get("timestamp", ""),
            "pnl_usd": pnl,
            "result": "win" if pnl > 0 else ("loss" if pnl < 0 else "breakeven"),
        }
        trades.append(trade_result)

    # Calculate metrics
    winning_trades = [t for t in trades if t["pnl_usd"] > 0]
    losing_trades = [t for t in trades if t["pnl_usd"] <= 0]
    win_rate = len(winning_trades) / len(trades) if trades else 0

    # Max drawdown
    max_dd = 0
    running_balance = initial_balance
    for t in trades:
        running_balance += t["pnl_usd"]
        dd = (peak_balance - running_balance) / peak_balance
        max_dd = max(max_dd, dd)

    duration = time.time() - start_time

    return {
        "symbol": symbol_key,
        "resolution": resolution,
        "config": strategy.to_config(enabled_indicators),
        "period": {
            "from": candles[0].get("timestamp", "")[:10],
            "to": candles[-1].get("timestamp", "")[:10],
        },
        "trades_count": len(trades),
        "trades": trades[:200],  # Return up to 200 trades
        "metrics": {
            "initial_balance": initial_balance,
            "final_balance": balance,
            "total_pnl": balance - initial_balance,
            "win_rate": round(win_rate * 100, 1),
            "max_drawdown_pct": round(max_dd * 100, 1),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "duration_seconds": round(duration, 2),
        },
    }


# EXTRACTED TO api/routes/backtest.py - using router below
# @app.get("/api/backtest/optimize")
# async def start_optimize(
#     symbol: str = Query(..., description="Symbol to backtest"),
#     resolution: str = Query("60", description="Resolution: 1, 5, 15, 30, 60, D"),
#     days: int = Query(7, description="Number of days to backtest (keep small)"),
#     min_score: float = Query(0.05, description="Minimum score threshold"),
#     initial_balance: float = Query(3000.0, description="Initial balance"),
#     background_tasks: BackgroundTasks = None,
# ):
#     """
#     Start optimization in background. Returns job_id immediately.
#     Use /api/backtest/optimize/{job_id} to get results.
#     """
#     import uuid
#     from database import get_db
#     
#     job_id = str(uuid.uuid4())[:8]
#     
#     # Store initial status in DB
#     db = get_db()
#     db.optimize_jobs.insert_one({
#         "_id": job_id,
#         "status": "running",
#         "symbol": symbol,
#         "started_at": datetime.utcnow().isoformat(),
#     })
#     
#     # Run in background
#     background_tasks.add_task(
#         run_optimization, job_id, symbol, resolution, days, min_score, initial_balance
#     )
#     
#     return {
#         "job_id": job_id,
#         "status": "started",
#         "symbol": symbol,
#         "message": "Optimization started in background. Poll /api/backtest/optimize/{job_id} for results."
#     }


# DEAD CODE - was used by start_optimize above (extracted to backtest.py)
# def run_optimization(job_id: str, symbol: str, resolution: str, days: int, min_score: float, initial_balance: float):
    """Run optimization in background and save results to DB"""
    import subprocess
    import json
    from database import get_db
    from strategies import STRATEGIES
    
    print(f"[OPTIMIZE] Starting job {job_id} for {symbol}")
    db = get_db()
    
    try:
        # Get available indicators - limit to first 3
        ALL_INDICATORS = ["RSI", "MACD", "BB", "SMA", "ADX", "STOCH", "MOMENTUM"]
        
        # Get all strategies
        all_strategies = list(STRATEGIES.keys())
        
        # Generate combinations - more indicators for better results
        combinations = []
        for strat in all_strategies:
            # Single indicators
            for ind in ALL_INDICATORS:
                combinations.append({"strategy": strat, "indicators": [ind]})
            # Pairs of indicators
            for i, ind1 in enumerate(ALL_INDICATORS):
                for ind2 in ALL_INDICATORS[i+1:]:
                    if len(combinations) < 30:  # Limit to 30
                        combinations.append({"strategy": strat, "indicators": [ind1, ind2]})
        
        # Save total combinations count
        db.optimize_jobs.update_one(
            {"_id": job_id},
            {"$set": {"total_combinations": len(combinations)}}
        )
        
        results = []
        for combo in combinations:
            # Check if cancelled
            job = db.optimize_jobs.find_one({"_id": job_id})
            if job and job.get("status") == "cancelled":
                break
            
            strat = combo["strategy"]
            inds = combo["indicators"]
            ind_str = ",".join(inds)
            
            try:
                # Call backtest endpoint using subprocess
                url = f"http://localhost:9000/api/backtest?symbol={symbol}&resolution={resolution}&days={days}&min_score={min_score}&initial_balance={initial_balance}&strategy={strat}&indicators={ind_str}"
                result = subprocess.run(["curl", "-s", url], capture_output=True, timeout=60)
                if result.returncode == 0:
                    try:
                        data = json.loads(result.stdout)
                        if "error" not in data and data.get("trades_count", 0) > 0:
                            result = {
                                "strategy": strat,
                                "indicators": inds,
                                "trades_count": data["trades_count"],
                                "total_pnl": data["metrics"]["total_pnl"],
                                "win_rate": data["metrics"]["win_rate"],
                                "max_drawdown_pct": data["metrics"]["max_drawdown_pct"],
                                "score": data["metrics"]["total_pnl"] - (data["metrics"]["max_drawdown_pct"] * 10),
                            }
                            results.append(result)
                        
                        # Save partial results to DB for live updates
                        sorted_partial = sorted(results, key=lambda x: x["score"], reverse=True)
                        db.optimize_jobs.update_one(
                            {"_id": job_id},
                            {"$set": {
                                "results": sorted_partial[:10],
                                "best": sorted_partial[0] if sorted_partial else None,
                            }}
                        )
                    except Exception:
                        pass
            except Exception as e:
                print(f"[OPTIMIZE] Error: {e}")
                pass
        
        # Sort results
        results.sort(key=lambda x: x["score"], reverse=True)
        
        # Save to DB
        db.optimize_jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "completed",
                "results": results[:10],
                "best": results[0] if results else None,
                "completed_at": datetime.utcnow().isoformat(),
            }}
        )
    except Exception as e:
        db.optimize_jobs.update_one(
            {"_id": job_id},
            {"$set": {"status": "failed", "error": str(e)}}
        )


# EXTRACTED TO api/routes/backtest.py - using router below
# @app.get("/api/backtest/optimize/{job_id}")
# async def get_optimize_results(job_id: str):
#     """Get optimization results by job_id"""
#     from database import get_db
#     db = get_db()
#     job = db.optimize_jobs.find_one({"_id": job_id})
#     
#     if not job:
#         return {"error": "Job not found"}
#     
#     return {
#         "job_id": job_id,
#         "status": job.get("status"),
#         "symbol": job.get("symbol"),
#         "best": job.get("best"),
#         "results": job.get("results", []),
#         "total": job.get("total_combinations", 0),
#     }


# EXTRACTED TO api/routes/backtest.py - using router below
# @app.post("/api/backtest/optimize/{job_id}/cancel")
# async def cancel_optimize(job_id: str):
#     """Cancel a running optimization job"""
#     from database import get_db
#     db = get_db()
#     db.optimize_jobs.update_one(
#         {"_id": job_id},
#         {"$set": {"status": "cancelled"}}
#     )
#     return {"status": "cancelled"}

    # Get available strategies
    from strategies import STRATEGIES

    all_strategies = [s.strip() for s in strategies.split(",")] if strategies else list(STRATEGIES.keys())

    # Get available indicators - limit to first 3 for speed
    ALL_INDICATORS = ["RSI", "MACD", "BB", "SMA", "ADX", "STOCH", "MOMENTUM"]
    all_indicators = [ind.strip().upper() for ind in indicators.split(",")] if indicators else ALL_INDICATORS[:3]  # Limit to 3 for speed

    # Generate combinations - limit count
    combinations = []
    for strat in all_strategies:
        # Single indicators only (for speed)
        for ind in all_indicators:
            combinations.append({"strategy": strat, "indicators": [ind]})

    print(f"[OPTIMIZE] Testing {len(combinations)} combinations (parallel)...")

    # Run backtests in parallel
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def run_single_combo(combo):
        strat = combo["strategy"]
        inds = combo["indicators"]
        ind_str = ",".join(inds)
        # Build URL inside function
        combo_url = f"http://127.0.0.1:8002/api/backtest?symbol={symbol}&resolution={resolution}&days={days}&min_score={min_score}&initial_balance={initial_balance}&strategy={strat}&indicators={ind_str}"
        try:
            resp = requests.get(combo_url, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if "error" not in data and data.get("trades_count", 0) > 0:
                    return {
                        "strategy": strat,
                        "indicators": inds,
                        "trades_count": data["trades_count"],
                        "total_pnl": data["metrics"]["total_pnl"],
                        "win_rate": data["metrics"]["win_rate"],
                        "max_drawdown_pct": data["metrics"]["max_drawdown_pct"],
                        "score": data["metrics"]["total_pnl"] - (data["metrics"]["max_drawdown_pct"] * 10),
                    }
        except Exception as e:
            pass
        return None

    # Run in parallel
    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(run_single_combo, combo): combo for combo in combinations}
        for future in as_completed(futures):
            result = future.result()
            if result:
                results.append(result)

    print(f"[OPTIMIZE] Completed {len(results)} tests")

    # Sort by score (PnL - drawdown penalty)
    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "symbol": symbol,
        "period_days": days,
        "total_combinations": len(combinations),
        "tested": len(results),
        "best": results[0] if results else None,
        "results": results[:20],  # Top 20
    }


# @app.get("/api/dashboard")
# @async_timed("dashboard")
# async def get_dashboard(resolution: str = Query("60"), count: int = Query(50)):
#     symbols = list(INSTRUMENTS.keys())
#     account_task = async_load_account()
#     signals_task = generate_signals()
#     open_task = async_load_open_positions()
#     closed_task = async_load_closed_positions(20)
#     chart_tasks = [get_chart_data(s, resolution=resolution, count=count) for s in symbols]
#     news_tasks = [get_news(s) for s in symbols]
#     account, signals, open_pos, closed_pos = await asyncio.gather(account_task, signals_task, open_task, closed_task)
#     charts_results = await asyncio.gather(*chart_tasks, return_exceptions=True)
#     news_results = await asyncio.gather(*news_tasks, return_exceptions=True)
#     charts = {}
#     news_dict = {}
#     for i, sym in enumerate(symbols):
#         res_chart = charts_results[i]
#         if isinstance(res_chart, dict) and "data" in res_chart:
#             charts[sym] = res_chart
#         res_news = news_results[i]
#         if isinstance(res_news, dict) and "news" in res_news:
#             news_dict[sym] = res_news["news"]
#     return {
#         "account": account,
#         "signals": signals,
#         "open_positions": open_pos[:20],
#         "closed_positions": closed_pos[:20],
#         "charts": charts,
#         "news": news_dict,
#     }


# =====================
# SERVE FRONTEND (production)
# =====================
# In production, the backend serves the built frontend as static files.
# Build with: cd frontend && npm run build
# The dist/ folder is served at / and all non-API routes fall back to index.html (SPA)

import pathlib

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_frontend_dist = pathlib.Path(__file__).parent.parent / "frontend" / "dist"

if _frontend_dist.is_dir():

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve frontend SPA - all non-API routes get index.html"""
        # Skip API routes - let them 404
        if full_path.startswith("api/"):
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "Not found"}, status_code=404)
        file_path = _frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8001")))
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)

