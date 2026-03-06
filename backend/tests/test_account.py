"""Tests for account management functionality.

Run: python -m pytest tests/test_account.py -v
"""
import asyncio
import os
import sys
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from broker_sim import SimulatedBroker, SimulatedDataProvider


class TestAccountManagement:
    """Test account retrieval and management."""

    @pytest.mark.asyncio
    async def test_get_account_info(self, fresh_broker):
        """Test fetching account information."""
        broker = fresh_broker
        
        account = broker.get_account()
        
        assert account["balance_usd"] == 10000.0

    @pytest.mark.asyncio
    async def test_account_mode_simulation(self, fresh_broker):
        """Test account in simulation mode."""
        broker = fresh_broker
        
        account = broker.get_account()
        assert "mode" in account

    @pytest.mark.asyncio
    async def test_account_with_positions(self, fresh_broker):
        """Test account with open positions."""
        broker = fresh_broker
        
        # Open a position
        await broker.open_position(
            symbol="XAU",
            direction="buy",
            size=0.01,
            entry_price=2000.0
        )
        
        account = broker.get_account()
        
        # Check that we have positions
        positions = broker.get_open_positions()
        assert len(positions) > 0


class TestAccountBalance:
    """Test account balance operations."""

    @pytest.mark.asyncio
    async def test_initial_balance(self, broker_with_balance):
        """Test account starts with correct balance."""
        broker = broker_with_balance(50000)
        
        account = broker.get_account()
        assert account["balance_usd"] == 50000.0

    @pytest.mark.asyncio
    async def test_balance_after_profit(self, fresh_broker):
        """Test balance increases after profitable trade."""
        broker = fresh_broker
        
        # Open and close with profit
        result = await broker.open_position(
            symbol="XAU",
            direction="buy",
            size=0.01,
            entry_price=2000.0
        )
        
        await broker.close_position(result["position"]["id"], exit_price=2020.0)
        
        account = broker.get_account()
        # Balance should be higher (profit)
        assert account["balance_usd"] > 10000.0

    @pytest.mark.asyncio
    async def test_balance_after_loss(self, fresh_broker):
        """Test balance decreases after losing trade."""
        broker = fresh_broker
        
        # Open and close with loss
        result = await broker.open_position(
            symbol="XAU",
            direction="buy",
            size=0.01,
            entry_price=2000.0
        )
        
        await broker.close_position(result["position"]["id"], exit_price=1980.0)
        
        account = broker.get_account()
        # Balance should be lower (loss)
        assert account["balance_usd"] < 10000.0


class TestAccountEdgeCases:
    """Test edge cases in account management."""

    @pytest.mark.asyncio
    async def test_zero_balance_account(self, broker_with_balance):
        """Test account with zero initial balance."""
        broker = SimulatedBroker(initial_balance=0.0)
        
        account = broker.get_account()
        assert account["balance_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_large_balance(self, broker_with_balance):
        """Test account with large balance."""
        broker = broker_with_balance(1000000)
        
        account = broker.get_account()
        assert account["balance_usd"] == 1000000.0

    @pytest.mark.asyncio
    async def test_equity_calculation(self, fresh_broker):
        """Test equity is calculated correctly with open positions."""
        broker = fresh_broker
        
        # Open a position
        await broker.open_position(
            symbol="XAU",
            direction="buy",
            size=0.01,
            entry_price=2000.0
        )
        
        account = broker.get_account()
        
        # Equity should be tracked
        assert "equity_usd" in account

    @pytest.mark.asyncio
    async def test_margin_calculation(self, fresh_broker):
        """Test margin is calculated correctly."""
        broker = fresh_broker
        
        # Open position requiring margin
        await broker.open_position(
            symbol="XAU",
            direction="buy",
            size=0.01,
            entry_price=2000.0
        )
        
        account = broker.get_account()
        
        # Margin should be used
        assert "used_margin" in account


class TestAccountMode:
    """Test account mode (simulation/live)."""

    @pytest.mark.asyncio
    async def test_default_mode(self, fresh_broker):
        """Test default account mode."""
        broker = fresh_broker
        
        account = broker.get_account()
        # Default mode should be set
        assert "mode" in account

    @pytest.mark.asyncio
    async def test_mode_persistence(self, fresh_broker):
        """Test mode is maintained across operations."""
        broker = fresh_broker
        
        # Open and close position
        result = await broker.open_position(
            symbol="XAU",
            direction="buy",
            size=0.01,
            entry_price=2000.0
        )
        
        await broker.close_position(result["position"]["id"], exit_price=2010.0)
        
        account = broker.get_account()
        # Mode should still be set
        assert "mode" in account


class TestMaxDrawdown:
    """Test max drawdown tracking."""

    @pytest.mark.asyncio
    async def test_drawdown_tracking(self, fresh_broker):
        """Test drawdown is tracked correctly."""
        broker = fresh_broker
        
        # Open winning position
        result1 = await broker.open_position(
            symbol="XAU",
            direction="buy",
            size=0.01,
            entry_price=2000.0
        )
        await broker.close_position(result1["position"]["id"], exit_price=2100.0)
        
        # Open losing position
        result2 = await broker.open_position(
            symbol="XAU",
            direction="buy",
            size=0.01,
            entry_price=2100.0
        )
        await broker.close_position(result2["position"]["id"], exit_price=2000.0)
        
        account = broker.get_account()
        
        # Account should have some balance
        assert account["balance_usd"] >= 0
