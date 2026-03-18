"""API router aggregation - extracted from main.py"""
from fastapi import APIRouter

router = APIRouter()

# Routes
from .routes import (
    signals as signals_routes,
    logs,
    control,
    news,
    account as account_routes,
    strategies as strategies_routes,
    trades as trades_routes,
    market as market_routes,
    alerts as alerts_routes,
    status as status_routes,
    backtest as backtest_routes,
    root as root_routes,
    settings as settings_routes,
    rolling_backtest as rolling_backtest_routes,
)
from app.logging import log_event

# Include all routers
router.include_router(root_routes.router)
router.include_router(logs.router)
router.include_router(control.router)
router.include_router(news.router)
router.include_router(account_routes.router)
router.include_router(strategies_routes.router)
router.include_router(trades_routes.router)
router.include_router(market_routes.router)
router.include_router(alerts_routes.router)
router.include_router(status_routes.router)
router.include_router(backtest_routes.router)
router.include_router(rolling_backtest_routes.router)
router.include_router(settings_routes.router)
router.include_router(signals_routes.router)
