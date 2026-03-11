"""Risk management module"""

import math
from typing import Optional


class RiskManager:
    """Manages position sizing and risk limits"""
    
    def __init__(self, config: dict):
        self.risk_per_trade_pct = config.get('risk_per_trade_pct', 2.0)
        self.max_total_risk_pct = config.get('max_total_risk_pct', 2.0)
        self.leverage = config.get('leverage', 20)
        self.max_notional_exposure_multiple = config.get('max_notional_exposure_multiple', 1.0)
        self.sl_percent = abs(config.get('stop_loss', {}).get('value', 2.0))
        
        # Position sizing config
        sizing = config.get('position_sizing', {})
        self.rounding_mode = sizing.get('rounding', {}).get('mode', 'floor')
        self.rounding_step = sizing.get('rounding', {}).get('step', 0.0001)
    
    def calculate_position_size(
        self, 
        balance: float, 
        price: float, 
        current_exposure: float = 0,
        open_risk_amount: float = 0
    ) -> float:
        """
        Calculate position size based on risk parameters
        
        Args:
            balance: Account balance
            price: Current asset price
            current_exposure: Current position notional value
            open_risk_amount: Sum of risk amounts for open positions
        
        Returns:
            Position size (number of units)
        """
        # Calculate risk amount for this trade
        risk_amount = balance * (self.risk_per_trade_pct / 100.0)
        
        # Check total risk limit
        if open_risk_amount + risk_amount > balance * (self.max_total_risk_pct / 100.0):
            # Reduce risk amount to stay within limit
            risk_amount = max(0, balance * (self.max_total_risk_pct / 100.0) - open_risk_amount)
        
        # Calculate initial size: (risk_amount * leverage) / price
        if price <= 0:
            return 0
        
        size = (risk_amount * self.leverage) / price
        
        # Calculate notional value
        notional = size * price
        
        # Apply notional exposure limit
        max_notional = balance * self.max_notional_exposure_multiple
        if notional > max_notional:
            size = max_notional / price
        
        # Apply rounding
        size = self._round_size(size)
        
        return size
    
    def _round_size(self, size: float) -> float:
        """Apply rounding to position size"""
        if self.rounding_mode == 'floor':
            return math.floor(size / self.rounding_step) * self.rounding_step
        elif self.rounding_mode == 'round':
            return round(size / self.rounding_step) * self.rounding_step
        else:
            return size
    
    def calculate_risk_amount(self, balance: float) -> float:
        """Calculate risk amount for a single trade"""
        return balance * (self.risk_per_trade_pct / 100.0)
