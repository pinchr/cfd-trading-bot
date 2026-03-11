"""Backtest API routes - extracted from main.py"""
import json
import time
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query, Request, BackgroundTasks

router = APIRouter()


# def create_backtest_endpoints(get_strategy_manager_fn=None):
#     """Factory function to create backtest endpoints with dependencies"""
    
@router.post("/api/strategies/backtest-json")
async def backtest_from_json(
    request: Request,
    symbol: str = Query(..., description="Symbol to backtest"),
    resolution: str = Query("5", description="Resolution: 5, 15, 60"),
    days: int = Query(30, description="Number of days"),
    initial_balance: float = Query(3000.0, description="Initial balance"),
):
    """
    Run backtest using strategy config from JSON body.
    Send JSON with strategy configuration matching memoos.path.join(os.path.dirname(__file__), "..", "strategies.json") format.
    """
    start_time = time.time()
    
    # Get JSON from request body
    body = await request.body()
    config = json.loads(body)
    
    # Get strategy config from JSON
    strategies = config.get('strategies', [])
    if not strategies:
        return {"error": "No strategies found in JSON"}
    
    # Find matching strategy for symbol
    strategy_config = None
    for s in strategies:
        if s.get('symbol', '').upper() == symbol.upper() and s.get('enabled', False):
            strategy_config = s
            break
    
    if not strategy_config:
        # Find any strategy for this symbol
        for s in strategies:
            if s.get('symbol', '').upper() == symbol.upper():
                strategy_config = s
                break
    
    if not strategy_config:
        return {"error": f"No strategy found for symbol: {symbol}"}
    
    # Load strategy module and create strategy
    from strategy import load_strategies_from_json
    
    # Create a manager with the strategy
    json_str = json.dumps({'strategies': [strategy_config]})
    manager = load_strategies_from_json(json_str)
    
    # Get candles
    from database import get_db
    db = get_db()
    
    # Calculate date range
    end_ts = int(time.time() * 1000)
    start_ts = end_ts - (days * 24 * 60 * 60 * 1000)
    
    # Get candles from DB - CRITICAL: For BTC, only use binance source!
    query = {
        'symbol': symbol.upper(),
        'resolution': resolution,
    }
    
    # For BTC, only use binance data to avoid mixed yahoo/binance issues
    if symbol.upper() == "BTC":
        query['source'] = 'binance'
    
    # Try int timestamp first (BTC style), then fall back to string
    candles = list(db.candles.find({
        **query,
        'timestamp': {'$gte': start_ts, '$lte': end_ts}
    }).sort('timestamp', 1))
    
    # If no results with source filter, try without (for compatibility)
    if not candles:
        query_no_source = {
            'symbol': symbol.upper(),
            'resolution': resolution,
        }
        candles = list(db.candles.find({
            **query_no_source,
            'timestamp': {'$gte': start_ts, '$lte': end_ts}
        }).sort('timestamp', 1))
    
    # If still no results, try with string timestamps (XAU/XAG style)
    if not candles:
        start_str = datetime.fromtimestamp(start_ts / 1000).isoformat() + 'Z'
        end_str = datetime.fromtimestamp(end_ts / 1000).isoformat() + 'Z'
        
        # Again, for BTC only binance
        if symbol.upper() == "BTC":
            candles = list(db.candles.find({
                **query,
                'timestamp': {'$gte': start_str, '$lte': end_str}
            }).sort('timestamp', 1))
        else:
            candles = list(db.candles.find({
                'symbol': symbol.upper(),
                'resolution': resolution,
                'timestamp': {'$gte': start_str, '$lte': end_str}
            }).sort('timestamp', 1))
    
    if not candles:
        return {"error": f"No candles found for {symbol} {resolution}"}
    
    # Warmup period - skip first N candles for indicator warmup
    warmup_candles = 30  # Need ~30 candles for RSI(14) + MOM(10) + buffer
    if len(candles) <= warmup_candles:
        return {"error": f"Not enough candles: {len(candles)}, need at least {warmup_candles}"}
    
    # Get strategy config values
    score_config = strategy_config.get('score', {})
    min_score = score_config.get('min_score', 0.01)
    
    risk_config = strategy_config.get('risk', {})
    leverage = risk_config.get('leverage', 20)
    print(f"[BACKTEST DEBUG] strategy={strategy_config.get('id')}, risk_config={risk_config}, leverage={leverage}")
    
    # TP/SL will be calculated per-trade using adaptive algorithm
    # exits_v2 config is loaded above
    
    # Add unified trading functions
    # Use the same logic as live trading!
    from services.trading_engine import (
        calculate_adaptive_tp_sl,
        calculate_dynamic_position_size
    )
    
    # Run backtest
    balance = initial_balance
    trades = []
    position = None
    open_positions_count = 0
    
    # Get strategy's exits_v2 config for adaptive TP/SL
    exits_v2 = strategy_config.get('exits_v2', {})
    sizing_v2 = strategy_config.get('position_sizing_v2', {})
    
    # Get base TP/SL percentages for reporting
    tp_pct = exits_v2.get('base_tp_percent', 2.5) / 100 if exits_v2 else 0.025
    sl_pct = exits_v2.get('base_sl_percent', 1.5) / 100 if exits_v2 else 0.015
    
    # Initialize indicators with warmup data
    for i, candle in enumerate(candles[:warmup_candles]):
        candle_data = {
            'open': candle.get('open'),
            'high': candle.get('high'),
            'low': candle.get('low'),
            'close': candle.get('close'),
            'volume': candle.get('volume', 0),
            'timestamp': candle.get('timestamp')
        }
        for strat in manager.get_enabled_strategies():
            for ind in strat.indicators.values():
                ind.update(candle_data)
    
    # Now start trading after warmup
    for i, candle in enumerate(candles[warmup_candles:], start=warmup_candles):
        # Create indicator dict for this candle
        candle_data = {
            'open': candle.get('open'),
            'high': candle.get('high'),
            'low': candle.get('low'),
            'close': candle.get('close'),
            'volume': candle.get('volume', 0),
            'timestamp': candle.get('timestamp')
        }
        
        # Get enabled strategies from manager and calculate using unified functions
        for strat in manager.get_enabled_strategies():
            # Get signal from strategy
            signal = strat.on_bar(candle_data, balance)
            
            if signal and position is None:
                # Use unified adaptive TP/SL calculation
                direction = 'buy' if signal.get('direction', 0) > 0 else 'sell'
                
                # Get candles for TP/SL calculation (last 50 candles)
                lookback_candles = []
                for j in range(max(warmup_candles, i-50), i):
                    c = candles[j]
                    lookback_candles.append({
                        'open': c.get('open'),
                        'high': c.get('high'),
                        'low': c.get('low'),
                        'close': c.get('close'),
                        'volume': c.get('volume', 0)
                    })
                
                # Calculate adaptive TP/SL
                try:
                    tp_price, sl_price = calculate_adaptive_tp_sl(
                        strategy_config=strategy_config,
                        candles=lookback_candles,
                        entry_price=candle.get('close'),
                        direction=direction
                    )
                except:
                    # Fallback to simple percentage
                    tp_pct = exits_v2.get('base_tp_percent', 2.5) / 100
                    sl_pct = exits_v2.get('base_sl_percent', 1.5) / 100
                    if direction == 'buy':
                        tp_price = candle.get('close') * (1 + tp_pct)
                        sl_price = candle.get('close') * (1 - sl_pct)
                    else:
                        tp_price = candle.get('close') * (1 - tp_pct)
                        sl_price = candle.get('close') * (1 + sl_pct)
                
                # Calculate dynamic position size
                score = abs(signal.get('score', 0.5))
                conf = signal.get('confidence', 0.5)
                
                # Get ATR for volatility
                volatility = 0.0
                if len(lookback_candles) >= 20:
                    try:
                        from strategy.technical import TechnicalIndicators
                        ind = TechnicalIndicators.calculate_all(lookback_candles[-20:], period=14)
                        atr = ind.get('atr_14', 0)
                        volatility = (atr / candle.get('close')) * 100 if candle.get('close') > 0 else 0
                    except:
                        pass
                
                try:
                    size = calculate_dynamic_position_size(
                        strategy_config=strategy_config,
                        account_balance=balance,
                        entry_price=candle.get('close'),
                        stop_loss_price=sl_price,
                        signal_score=score,
                        signal_confidence=conf,
                        open_positions_count=open_positions_count,
                        volatility=volatility
                    )
                except:
                    size = (balance * 0.02 * leverage) / candle.get('close')
                
                # Open position with unified calculations
                position = {
                    'entry_price': candle.get('close'),
                    'size': size,
                    'direction': signal.get('direction', 1),
                    'entry_time': candle.get('timestamp'),
                    'tp_price': tp_price,
                    'sl_price': sl_price,
                    'original_score': score
                }
        
        # Check if we have a position
        if position:
            current_price = candle.get('close')
            direction = position['direction']
            
            # Check TP/SL
            if direction > 0:  # Long
                if current_price >= position['tp_price']:
                    # TP hit
                    pnl = position['size'] * position['entry_price'] * tp_pct * leverage
                    balance += pnl
                    trades.append({
                        'entry': position['entry_price'],
                        'exit': current_price,
                        'pnl_usd': pnl,
                        'result': 'win',
                        'type': 'TP'
                    })
                    position = None
                elif current_price <= position['sl_price']:
                    # SL hit
                    pnl = -position['size'] * position['entry_price'] * sl_pct * leverage
                    balance += pnl
                    trades.append({
                        'entry': position['entry_price'],
                        'exit': current_price,
                        'pnl_usd': pnl,
                        'result': 'loss',
                        'type': 'SL'
                    })
                    position = None
            else:  # Short
                if current_price <= position['tp_price']:
                    pnl = position['size'] * position['entry_price'] * tp_pct * leverage
                    balance += pnl
                    trades.append({
                        'entry': position['entry_price'],
                        'exit': current_price,
                        'pnl_usd': pnl,
                        'result': 'win',
                        'type': 'TP'
                    })
                    position = None
                elif current_price >= position['sl_price']:
                    pnl = -position['size'] * position['entry_price'] * sl_pct * leverage
                    balance += pnl
                    trades.append({
                        'entry': position['entry_price'],
                        'exit': current_price,
                        'pnl_usd': pnl,
                        'result': 'loss',
                        'type': 'SL'
                    })
                    position = None
    
    # Calculate metrics
    wins = len([t for t in trades if t['result'] == 'win'])
    losses = len([t for t in trades if t['result'] == 'loss'])
    win_rate = (wins / len(trades) * 100) if trades else 0
    total_pnl = sum(t['pnl_usd'] for t in trades)
    
    return {
        'strategy_id': strategy_config.get('id'),
        'symbol': symbol,
        'resolution': resolution,
        'days': days,
        'config': {
            'min_score': min_score,
            'leverage': leverage,
            'tp_pct': tp_pct * 100,
            'sl_pct': sl_pct * 100
        },
        'results': {
            'trades': len(trades),
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 1),
            'total_pnl': round(total_pnl, 2),
            'final_balance': round(balance, 2)
        },
        'execution_time_seconds': round(time.time() - start_time, 2)
    }

# return router


# def create_optimize_endpoints():
# """Factory function to create optimization endpoints"""

@router.get("/api/backtest/optimize")
async def start_optimize(
    symbol: str = Query(..., description="Symbol to backtest"),
    resolution: str = Query("60", description="Resolution: 1, 5, 15, 30, 60, D"),
    days: int = Query(7, description="Number of days to backtest (keep small)"),
    min_score: float = Query(0.05, description="Minimum score threshold"),
    initial_balance: float = Query(3000.0, description="Initial balance"),
    background_tasks: BackgroundTasks = None,
):
    """
    Start optimization in background. Returns job_id immediately.
    Use /api/backtest/optimize/{job_id} to get results.
    """
    from database import get_db
    
    job_id = str(uuid.uuid4())[:8]
    
    # Store initial status in DB
    db = get_db()
    db.optimize_jobs.insert_one({
        "_id": job_id,
        "status": "running",
        "symbol": symbol,
        "started_at": datetime.utcnow().isoformat(),
    })
    
    # Run in background
    background_tasks.add_task(
        _run_optimization, job_id, symbol, resolution, days, min_score, initial_balance
    )
    
    return {
        "job_id": job_id,
        "status": "started",
        "symbol": symbol,
        "message": "Optimization started in background. Poll /api/backtest/optimize/{job_id} for results."
    }

@router.get("/api/backtest/optimize/{job_id}")
async def get_optimize_results(job_id: str):
    """Get optimization results by job_id"""
    from database import get_db
    db = get_db()
    job = db.optimize_jobs.find_one({"_id": job_id})
    
    if not job:
        return {"error": "Job not found"}
    
    return {
        "job_id": job_id,
        "status": job.get("status"),
        "symbol": job.get("symbol"),
        "best": job.get("best"),
        "results": job.get("results", []),
        "total": job.get("total_combinations", 0),
    }

@router.post("/api/backtest/optimize/{job_id}/cancel")
async def cancel_optimize(job_id: str):
    """Cancel a running optimization job"""
    from database import get_db
    db = get_db()
    db.optimize_jobs.update_one(
        {"_id": job_id},
        {"$set": {"status": "cancelled"}}
    )
    return {"job_id": job_id, "status": "cancelled"}

# return router


async def _run_optimization(job_id: str, symbol: str, resolution: str, days: int, min_score: float, initial_balance: float):
    """Run optimization in background and save results to DB"""
    import subprocess
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
        best = None
        
        for idx, combo in enumerate(combinations):
            # Check if cancelled
            job = db.optimize_jobs.find_one({"_id": job_id})
            if job and job.get("status") == "cancelled":
                print(f"[OPTIMIZE] Job {job_id} cancelled")
                break
            
            strat = combo["strategy"]
            indicators = ",".join(combo["indicators"])
            
            try:
                # Run backtest as subprocess to get fresh results
                cmd = [
                    "python", "-c",
                    f"""
import sys
sys.path.insert(0, '.')
from main import run_backtest
import asyncio
result = asyncio.run(run_backtest(
    symbol="{symbol}",
    resolution="{resolution}",
    days={days},
    min_score={min_score},
    initial_balance={initial_balance},
    strategy="{strat}",
    indicators="{indicators}"
))
print(result)
"""
                ]
                
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if proc.returncode == 0 and proc.stdout:
                    import re
                    # Extract metrics from output
                    win_rate_match = re.search(r"'win_rate':\s*([0-9.]+)", proc.stdout)
                    pnl_match = re.search(r"'total_pnl':\s*([-0-9.]+)", proc.stdout)
                    
                    if win_rate_match and pnl_match:
                        win_rate = float(win_rate_match.group(1))
                        total_pnl = float(pnl_match.group(1))
                        
                        results.append({
                            "strategy": strat,
                            "indicators": combo["indicators"],
                            "win_rate": win_rate,
                            "total_pnl": total_pnl
                        })
                        
                        if best is None or total_pnl > best["total_pnl"]:
                            best = {
                                "strategy": strat,
                                "indicators": combo["indicators"],
                                "win_rate": win_rate,
                                "total_pnl": total_pnl
                            }
            except Exception as e:
                print(f"[OPTIMIZE] Error for {strat} {indicators}: {e}")
            
            # Update progress every 5 iterations
            if idx % 5 == 0:
                db.optimize_jobs.update_one(
                    {"_id": job_id},
                    {"$set": {
                        "results": results[:10],  # Keep top 10
                        "best": best,
                        "progress": f"{idx+1}/{len(combinations)}"
                    }}
                )
        
        # Final update
        db.optimize_jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "completed",
                "results": results,
                "best": best,
                "completed_at": datetime.utcnow().isoformat()
            }}
        )
        print(f"[OPTIMIZE] Job {job_id} completed with {len(results)} results")
        
    except Exception as e:
        print(f"[OPTIMIZE] Job {job_id} failed: {e}")
        db.optimize_jobs.update_one(
            {"_id": job_id},
            {"$set": {
                "status": "failed",
                "error": str(e)
            }}
        )
