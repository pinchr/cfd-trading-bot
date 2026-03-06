"""
Shared pytest fixtures for CFD Trading Bot tests.
Run: python -m pytest tests/ -v
"""

import os
import sys
from datetime import datetime
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

# Ensure backend dir is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtester import BacktestTrade
from historical_data import generate_sample_data
from models import Component, ComponentType, Signal, SignalDirection
from strategies import BaseStrategy, get_strategy


# ── Mock Database Fixtures ──

@pytest.fixture(autouse=True)
def mock_database():
    """Mock database functions to prevent tests from writing to real database."""
    import database as db_module
    
    # Mock async functions
    db_module.async_save_trade = AsyncMock(return_value=None)
    db_module.async_save_account = AsyncMock(return_value=None)
    db_module.async_save_quote = AsyncMock(return_value=None)
    db_module.save_trade = MagicMock(return_value=None)
    db_module.save_account = MagicMock(return_value=None)
    db_module.save_quote = MagicMock(return_value=None)
    db_module.save_backtest_candles = MagicMock(return_value=None)
    
    # Also patch the module import in broker_sim
    import broker_sim
    broker_sim.async_save_trade = AsyncMock(return_value=None)
    broker_sim.async_save_account = AsyncMock(return_value=None)
    broker_sim.async_save_quote = AsyncMock(return_value=None)
    
    yield
    
    # Cleanup after test
    pass


# ── Sample Data Fixtures ──


@pytest.fixture
def gold_candles():
    """200+ daily candles for Gold with fixed seed (deterministic)."""
    return generate_sample_data("XAU", days=300, base_price=2000.0)


@pytest.fixture
def silver_candles():
    return generate_sample_data("XAG", days=300, base_price=23.0)


@pytest.fixture
def nasdaq_candles():
    return generate_sample_data("US100", days=300, base_price=17500.0)


@pytest.fixture
def btc_candles():
    return generate_sample_data("BTC", days=300, base_price=95000.0)


@pytest.fixture
def short_candles():
    """Too few candles — should fail."""
    return generate_sample_data("XAU", days=50, base_price=2000.0)


@pytest.fixture
def intraday_candles():
    """Intraday (15m) candles for scalping tests."""
    return generate_sample_data("XAU", days=10, base_price=2000.0, resolution="15")


# ── Signal Fixtures ──


@pytest.fixture
def sample_signal():
    """Sample BUY signal for XAU."""
    return Signal(
        symbol="XAU",
        direction=SignalDirection.BUY,
        score=0.75,
        confidence=0.8,
        technical_score=0.7,
        price_action_score=0.1,
        news_score=0.0,
        components=[
            Component(
                type=ComponentType.TECHNICAL,
                name="RSI (14)",
                value=0.5,
                description="RSI 45 (NEUTRAL)",
                confidence=0.5,
                indicators={"value": 45.0, "zone": "NEUTRAL"}
            ),
            Component(
                type=ComponentType.TECHNICAL,
                name="MACD",
                value=0.8,
                description="MACD BULLISH",
                confidence=0.6,
                indicators={"macd_line": 10.0, "signal_line": 5.0, "histogram": 5.0}
            )
        ],
        current_price=2000.0,
        time_horizon="1h",
        entry_point=2000.0,
        take_profit=2100.0,
        stop_loss=1960.0,
        risk_reward_ratio=2.5
    )


@pytest.fixture
def sell_signal():
    """Sample SELL signal for XAG."""
    return Signal(
        symbol="XAG",
        direction=SignalDirection.SELL,
        score=-0.7,
        confidence=0.75,
        technical_score=-0.65,
        price_action_score=-0.1,
        news_score=0.0,
        components=[
            Component(
                type=ComponentType.TECHNICAL,
                name="RSI (14)",
                value=-0.5,
                description="RSI 75 (OVERBOUGHT)",
                confidence=0.8,
                indicators={"value": 75.0, "zone": "OVERBOUGHT"}
            )
        ],
        current_price=23.5,
        time_horizon="1h",
        entry_point=23.5,
        take_profit=22.5,
        stop_loss=24.0,
        risk_reward_ratio=2.5
    )


@pytest.fixture
def neutral_signal():
    """Sample NEUTRAL signal."""
    return Signal(
        symbol="US100",
        direction=SignalDirection.NEUTRAL,
        score=0.05,
        confidence=0.5,
        technical_score=0.05,
        price_action_score=0.0,
        news_score=0.0,
        components=[],
        current_price=17500.0,
        time_horizon="1h",
        entry_point=17500.0,
        take_profit=17675.0,
        stop_loss=17325.0,
        risk_reward_ratio=1.0
    )


# ── Account Fixtures ──


@pytest.fixture
def mock_account():
    """Mock account with known balance."""
    return {
        "balance_usd": 10000.0,
        "equity_usd": 10000.0,
        "available_usd": 10000.0,
        "used_margin": 0.0,
        "peak_equity_usd": 10000.0,
        "total_pnl_usd": 0.0,
        "win_count": 0,
        "loss_count": 0,
        "closed_trades": 0,
        "open_trades": 0,
        "positions": [],
        "mode": "simulation",
        "dry_run": True,
        "currency": "USD",
        "last_scan": datetime.utcnow().isoformat(),
        "initial_balance_usd": 10000.0
    }


@pytest.fixture
def account_with_positions():
    """Mock account with open positions."""
    return {
        "balance_usd": 9500.0,
        "equity_usd": 9800.0,
        "available_usd": 7000.0,
        "used_margin": 2500.0,
        "peak_equity_usd": 10500.0,
        "total_pnl_usd": 300.0,
        "win_count": 5,
        "loss_count": 2,
        "closed_trades": 7,
        "open_trades": 2,
        "positions": [
            {
                "id": "pos001",
                "symbol": "XAU",
                "direction": "buy",
                "size": 0.01,
                "entry_price": 2000.0,
                "current_price": 2050.0,
                "unrealized_pnl_usd": 50.0,
                "status": "open"
            },
            {
                "id": "pos002",
                "symbol": "BTC",
                "direction": "sell",
                "size": 0.001,
                "entry_price": 50000.0,
                "current_price": 49000.0,
                "unrealized_pnl_usd": 10.0,
                "status": "open"
            }
        ],
        "mode": "simulation",
        "dry_run": True,
        "currency": "USD"
    }


# ── Position Fixtures ──


@pytest.fixture
def open_position():
    """Sample open position."""
    return {
        "id": "test_pos_001",
        "symbol": "XAU",
        "direction": "buy",
        "size": 0.01,
        "leverage": 10,
        "entry_price": 2000.0,
        "current_price": 2025.0,
        "take_profit": 2100.0,
        "stop_loss": 1950.0,
        "trailing_enabled": False,
        "margin_usd": 2.0,
        "unrealized_pnl_usd": 25.0,
        "opened_at": datetime.utcnow().isoformat(),
        "status": "open"
    }


@pytest.fixture
def closed_position():
    """Sample closed position."""
    return {
        "id": "test_pos_002",
        "symbol": "XAG",
        "direction": "sell",
        "size": 0.1,
        "leverage": 5,
        "entry_price": 23.0,
        "exit_price": 22.5,
        "pnl_usd": 50.0,
        "pnl_percent": 10.0,
        "opened_at": "2026-01-15T10:00:00",
        "closed_at": "2026-01-15T14:30:00",
        "status": "closed",
        "close_reason": "take_profit"
    }


# ── Strategy Fixtures ──


@pytest.fixture
def adaptive_strategy():
    """Get the AdaptiveRegimeStrategy."""
    return get_strategy("adaptive_regime")


@pytest.fixture
def mms_strategy():
    """Get the MMS strategy."""
    return get_strategy("mms")


# ── Indicator Fixtures ──


@pytest.fixture
def sample_indicators():
    """Sample technical indicators."""
    return {
        "rsi": 45.0,
        "rsi_zone": "NEUTRAL",
        "macd_line": 10.0,
        "signal_line": 5.0,
        "histogram": 5.0,
        "macd_bullish": True,
        "bb_upper": 2050.0,
        "bb_middle": 2000.0,
        "bb_lower": 1950.0,
        "bb_position": 0.5,
        "bb_zone": "MIDDLE",
        "adx": 30.0,
        "plus_di": 25.0,
        "minus_di": 20.0,
        "trend": "BULLISH",
        "sma_20": 1995.0,
        "sma_50": 1980.0,
        "atr": 25.0,
        "volume": 1000.0,
        "avg_volume": 800.0
    }


# ── Broker Fixtures ──


@pytest.fixture
def fresh_broker():
    """Create a fresh broker with 10000 balance for each test.
    
    IMPORTANT: This clears any existing positions from the database
    to ensure test isolation.
    """
    from broker_sim import SimulatedBroker
    broker = SimulatedBroker(initial_balance=10000.0)
    # Clear any existing positions loaded from DB
    broker.open_positions.clear()
    broker.closed_positions.clear()
    # Reset account to known state
    broker.account["balance_usd"] = 10000.0
    broker.account["equity_usd"] = 10000.0
    broker.account["available_usd"] = 10000.0
    broker.account["positions"] = 0
    broker.account["open_trades"] = 0
    return broker


@pytest.fixture
def broker_with_balance():
    """Create a broker with custom initial balance. Usage: broker_with_balance(50000)"""
    def _create_broker(balance=10000.0):
        from broker_sim import SimulatedBroker
        broker = SimulatedBroker(initial_balance=balance)
        # Clear any existing positions loaded from DB
        broker.open_positions.clear()
        broker.closed_positions.clear()
        # Reset account to known state
        broker.account["balance_usd"] = balance
        broker.account["equity_usd"] = balance
        broker.account["available_usd"] = balance
        broker.account["positions"] = 0
        broker.account["open_trades"] = 0
        return broker
    return _create_broker


# ── Price Fixtures ──


@pytest.fixture
def sample_quotes():
    """Sample quotes for multiple symbols."""
    return {
        "XAU": {"price": 2025.0, "bid": 2024.5, "ask": 2025.5, "timestamp": datetime.utcnow().isoformat()},
        "XAG": {"price": 23.5, "bid": 23.49, "ask": 23.51, "timestamp": datetime.utcnow().isoformat()},
        "BTC": {"price": 50000.0, "bid": 49990.0, "ask": 50010.0, "timestamp": datetime.utcnow().isoformat()},
        "US100": {"price": 17500.0, "bid": 17495.0, "ask": 17505.0, "timestamp": datetime.utcnow().isoformat()}
    }
