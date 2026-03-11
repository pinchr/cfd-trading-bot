"""Dashboard API route - extracted from main.py
Endpoint: /api/dashboard
"""

from fastapi import APIRouter, Query
import asyncio
from app.config import INSTRUMENTS
from backend.database import (
    async_load_account,
    async_load_open_positions, 
    async_load_closed_positions,
    )
from services.trading_engine import generate_signals
from api.routes.market import get_chart_data
from api.routes.news import get_news
router = APIRouter(tags=["dashboard"])


    
@router.get("/api/dashboard")
@async_timed_decorator("dashboard")
async def get_dashboard(resolution: str = Query("60"), count: int = Query(50)):
    """Get dashboard data with account, signals, positions, charts, and news."""
    
    symbols = list(INSTRUMENTS.keys())
    
    # Run all fetches in parallel
    account_task = async_load_account()
    signals_task = generate_signals()
    open_task = async_load_open_positions()
    closed_task = async_load_closed_positions(20)
    
    chart_tasks = [get_chart_data(s, resolution=resolution, count=count) for s in symbols]
    news_tasks = [get_news(s) for s in symbols]
    
    account, signals, open_pos, closed_pos = await asyncio.gather(
        account_task, signals_task, open_task, closed_task
    )
    charts_results = await asyncio.gather(*chart_tasks, return_exceptions=True)
    news_results = await asyncio.gather(*news_tasks, return_exceptions=True)
    
    # Process charts
    charts = {}
    for i, sym in enumerate(symbols):
        res_chart = charts_results[i]
        if isinstance(res_chart, dict) and "data" in res_chart:
            charts[sym] = res_chart
    
    # Process news
    news_dict = {}
    for i, sym in enumerate(symbols):
        res_news = news_results[i]
        if isinstance(res_news, dict) and "news" in res_news:
            news_dict[sym] = res_news["news"]
    
    return {
        "account": account,
        "signals": signals,
        "open_positions": open_pos[:20],
        "closed_positions": closed_pos[:20],
        "charts": charts,
        "news": news_dict,
    }

