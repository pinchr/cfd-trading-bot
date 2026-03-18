"""
Rolling Window Backtest System
Uruchamia backtesty na wielu okresach dla danej strategii i symbolu.
"""
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import asyncio

from fastapi import APIRouter, Query, BackgroundTasks
from pymongo import MongoClient
import os

router = APIRouter(tags=["rolling-backtest"])


async def _run_single_backtest(
    symbol: str,
    resolution: str,
    days: int,
    date_from: str,
    date_to: str,
    min_score: float,
    use_unified_strategy: bool,
    strategy: str,
) -> dict:
    """Helper to run single backtest - directly imports and runs backtest logic."""
    import httpx
    
    # Call the backtest API endpoint
    async with httpx.AsyncClient() as client:
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "days": days,
            "date_from": date_from,
            "date_to": date_to,
            "min_score": min_score,
            "use_unified_strategy": use_unified_strategy,
            "strategy": strategy,
        }
        response = await client.get("http://localhost:8001/api/backtest", params=params, timeout=60.0)
        return response.json()


def get_mongo_client():
    """Get MongoDB client."""
    mongo_uri = os.environ.get('MONGO_URI', '')
    if not mongo_uri:
        from services.state import get_settings
        settings = get_settings()
        mongo_uri = settings.get('MONGO_URI', '')
    return MongoClient(mongo_uri)


def generate_periods(days: int = 7, num_periods: int = 5) -> List[Dict]:
    """Generate rolling window periods."""
    periods = []
    end_dt = datetime.utcnow()
    
    for i in range(num_periods):
        period_end = end_dt - timedelta(days=i*days)
        period_start = period_end - timedelta(days=days)
        periods.append({
            "from": period_start.strftime("%Y-%m-%d"),
            "to": period_end.strftime("%Y-%m-%d")
        })
    return periods


@router.get("/api/backtest/rolling")
async def rolling_backtest(
    symbol: str = Query("XAU", description="Symbol"),
    strategy: str = Query("adaptive_regime", description="Strategy ID"),
    days: int = Query(7, description="Days per period"),
    num_periods: int = Query(5, description="Number of periods"),
    use_unified_strategy: bool = Query(True, description="Use unified strategy"),
    min_score: float = Query(0.15, description="Min score threshold"),
):
    """
    Run rolling window backtests across multiple time periods.
    Returns results for each period + aggregated stats.
    """
    periods = generate_periods(days, num_periods)
    results = []
    
    for i, period in enumerate(periods):
        result = await _run_single_backtest(
            symbol=symbol,
            resolution="5",
            days=days,
            date_from=period["from"],
            date_to=period["to"],
            min_score=min_score,
            use_unified_strategy=use_unified_strategy,
            strategy=strategy,
        )
        
        if "error" not in result:
            results.append({
                "period": i + 1,
                "from": period["from"],
                "to": period["to"],
                "trades": result.get("trades_count", 0),
                "win_rate": result.get("metrics", {}).get("win_rate", 0),
                "pnl": result.get("metrics", {}).get("total_pnl", 0),
                "final_balance": result.get("metrics", {}).get("final_balance", 0),
                "max_dd": result.get("metrics", {}).get("max_drawdown_pct", 0),
            })
    
    # Calculate aggregated stats
    if results:
        total_trades = sum(r["trades"] for r in results)
        avg_win_rate = sum(r["win_rate"] for r in results) / len(results)
        total_pnl = sum(r["pnl"] for r in results)
        avg_dd = sum(r["max_dd"] for r in results) / len(results)
    else:
        total_trades = 0
        avg_win_rate = 0
        total_pnl = 0
        avg_dd = 0
    
    return {
        "symbol": symbol,
        "strategy": strategy,
        "days_per_period": days,
        "num_periods": num_periods,
        "use_unified_strategy": use_unified_strategy,
        "periods": results,
        "aggregated": {
            "total_trades": total_trades,
            "avg_win_rate": round(avg_win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_max_dd": round(avg_dd, 1),
        }
    }


@router.get("/api/backtest/compare")
async def compare_strategies(
    symbol: str = Query("XAU", description="Symbol"),
    strategies: str = Query("adaptive_regime,mms", description="Comma-separated strategies"),
    days: int = Query(7, description="Days per period"),
    num_periods: int = Query(5, description="Number of periods"),
):
    """
    Compare multiple strategies across rolling windows.
    Returns results for each strategy + comparison.
    """
    strategy_list = [s.strip() for s in strategies.split(",")]
    periods = generate_periods(days, num_periods)
    
    all_results = {}
    
    for strategy in strategy_list:
        results = []
        for period in periods:
            result = await _run_single_backtest(
                symbol=symbol,
                resolution="5",
                days=days,
                date_from=period["from"],
                date_to=period["to"],
                min_score=0.15,
                use_unified_strategy=True,
                strategy=strategy,
            )
            
            if "error" not in result:
                results.append({
                    "trades": result.get("trades_count", 0),
                    "win_rate": result.get("metrics", {}).get("win_rate", 0),
                    "pnl": result.get("metrics", {}).get("total_pnl", 0),
                })
        
        if results:
            all_results[strategy] = {
                "total_trades": sum(r["trades"] for r in results),
                "avg_win_rate": sum(r["win_rate"] for r in results) / len(results),
                "total_pnl": sum(r["pnl"] for r in results),
            }
    
    # Find best strategy
    best = max(all_results.items(), key=lambda x: x[1]["total_pnl"]) if all_results else (None, {})
    
    return {
        "symbol": symbol,
        "periods": [{"from": p["from"], "to": p["to"]} for p in periods],
        "results": all_results,
        "best_strategy": best[0] if best[0] else "none",
        "best_pnl": best[1].get("total_pnl", 0) if best[1] else 0,
    }
