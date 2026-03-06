"""Strategy module - Score engine and main strategy class"""

from typing import Dict, List, Optional, Callable
from .indicators import create_indicator, Indicator
from .filters import FilterChain
from .risk import RiskManager
from .exits import ExitEngine


class ScoreEngine:
    """Computes trading signals from indicators"""
    
    def __init__(self, config: dict, indicators: Dict[str, Indicator]):
        self.config = config
        self.indicators = indicators
        self.min_score = config.get('min_score', 0.01)
        
        # Score indicators definition
        self.score_indicators = config.get('indicators', [])
    
    def compute_score(self) -> float:
        """
        Compute overall score from weighted indicators
        
        Returns:
            Score value (positive = buy, negative = sell)
        """
        total_score = 0.0
        total_weight = 0.0
        
        for ind_config in self.score_indicators:
            name = ind_config.get('name', '').upper()
            weight = ind_config.get('weight', 0.0)
            normalized_range = ind_config.get('normalized_range', [-1, 1])
            
            if name not in self.indicators or weight == 0:
                continue
            
            indicator = self.indicators[name]
            range_min, range_max = normalized_range[0], normalized_range[1]
            
            normalized = indicator.normalized_value(range_min, range_max)
            total_score += normalized * weight
            total_weight += weight
        
        # Normalize by actual weight used
        if total_weight > 0:
            total_score = total_score / total_weight
        
        return total_score
    
    def get_signal(self) -> Optional[str]:
        """
        Get trading signal based on score and direction mode.
        
        Returns:
            'buy', 'sell', or None
        """
        # Get direction mode from config
        direction_mode = self.config.get('direction_mode', 'score_only')
        
        if direction_mode == 'rsi_momentum':
            # v3: Direction based on RSI/Momentum, score as quality filter
            return self._get_signal_rsi_momentum()
        
        # Default v2: Score-based direction (score > 0 = buy, score < 0 = sell)
        score = self.compute_score()
        
        if score >= self.min_score:
            return 'buy'
        elif score <= -self.min_score:
            return 'sell'
        
        return None
    
    def _get_signal_rsi_momentum(self) -> Optional[str]:
        """
        v3 logic: Direction based on RSI/Momentum, score as quality filter.

        BUY signals (price expected to go UP):
        - RSI < rsi_oversold (e.g., < 40) = oversold, potential bounce
        - Momentum > 0 = price trending upward (momentum is positive % change)

        SELL signals (price expected to go DOWN):
        - RSI > rsi_overbought (e.g., > 60) = overbought, potential drop
        - Momentum < 0 = price trending downward (momentum is negative % change)

        Score is used as quality filter - must exceed min_score.
        """
        # Get direction config
        dir_config = self.config.get('direction_config', {})
        rsi_oversold = dir_config.get('rsi_oversold', 40)
        rsi_overbought = dir_config.get('rsi_overbought', 60)
        momentum_threshold = dir_config.get('momentum_threshold', 0)

        # Get indicator values
        rsi = self.indicators.get('RSI')
        momentum = self.indicators.get('MOMENTUM')

        rsi_val = rsi.value() if rsi else None
        mom_val = momentum.value() if momentum else None

        # Determine direction
        # Priority: RSI signal first, then momentum
        direction = None

        # BUY signals: RSI oversold (potential bounce) OR momentum positive (uptrend)
        if rsi_val is not None and rsi_val < rsi_oversold:
            direction = 'buy'
        elif mom_val is not None and mom_val > momentum_threshold:
            # Momentum > 0 means price is rising (bullish)
            direction = 'buy'

        # SELL signals: RSI overbought OR momentum negative - ONLY if not already buy
        if direction is None:  # Only check sell if not already buy
            if rsi_val is not None and rsi_val > rsi_overbought:
                direction = 'sell'
            elif mom_val is not None and mom_val < momentum_threshold:
                # Momentum < 0 means price is falling (bearish)
                direction = 'sell'

        if direction is None:
            return None

        # Apply score as quality filter
        score = abs(self.compute_score())
        if score >= self.min_score:
            return direction
        
        return None


class Strategy:
    """
    Main strategy class that combines all components
    """
    
    def __init__(
        self,
        config: dict,
        indicators: Dict[str, Indicator],
        broker_service: Callable = None,
        position_service: Callable = None,
        settings_service: Callable = None,
        market_data_service: Callable = None
    ):
        self.config = config
        self.id = config.get('id')
        self.name = config.get('name')
        self.symbol = config.get('symbol')
        self.timeframe = config.get('timeframe')
        self.enabled = config.get('enabled', True)
        self.trade_direction = config.get('trade_direction')
        
        # Components
        self.indicators = indicators
        self.score_engine = ScoreEngine(config.get('score', {}), indicators)
        
        # Services
        self.broker_service = broker_service
        self.position_service = position_service
        self.settings_service = settings_service
        self.market_data_service = market_data_service
        
        # Risk & Exits
        self.risk_manager = RiskManager(config.get('risk', {}))
        
        # HTF indicator for exits (placeholder - would be injected)
        htf_indicator = None
        self.exit_engine = ExitEngine(config.get('exits', {}), htf_indicator)
        
        # Filters - require services
        services = {
            'position_service': position_service,
            'settings_service': settings_service,
            'htf_indicator': htf_indicator
        }
        self.filters = FilterChain(config.get('filters', {}), services)
        
        # State
        self.is_initialized = False
    
    def on_bar(self, candle: dict, balance: float, current_exposure: float = 0, open_risk: float = 0, 
               atr_percent: float = None, vix_value: float = None) -> Optional[dict]:
        """
        Process new bar and generate signals
        
        Args:
            candle: New candle data
            balance: Current account balance
            current_exposure: Current position notional
            open_risk: Sum of risk for open positions
            atr_percent: ATR percent for volatility filter
            vix_value: Current VIX value for VIX filter
        
        Returns:
            Trade order dict or None
        """
        # Update all indicators
        for indicator in self.indicators.values():
            indicator.update(candle)
        
        # Check if enough data
        if not self._has_sufficient_data():
            return None
        
        # Check filters first (now includes volatility and VIX from strategy config)
        filters_passed, failed = self.filters.check_all(
            candle, self.symbol, 'long', 
            atr_percent=atr_percent, 
            vix_value=vix_value
        )
        if not filters_passed:
            return None
        
        # Get signal
        signal = self.score_engine.get_signal()
        
        if signal is None:
            return None
        
        # Determine direction
        if self.trade_direction == 'long_only' and signal == 'sell':
            return None
        
        # Calculate position size
        price = candle.get('close', candle.get('price'))
        if price is None or price <= 0:
            return None
        
        size = self.risk_manager.calculate_position_size(
            balance, price, current_exposure, open_risk
        )
        
        if size <= 0:
            return None
        
        # Generate order
        direction = 1 if signal == 'buy' else -1
        
        # Initialize exits
        exits = self.exit_engine.initialize_position(
            position_id=f"{self.id}_{self.symbol}_{int(candle.get('time', 0))}",
            entry_price=price,
            direction=direction
        )
        
        order = {
            'strategy_id': self.id,
            'symbol': self.symbol,
            'direction': direction,
            'size': size,
            'entry_price': price,
            'tp_price': exits['tp_price'],
            'sl_price': exits['sl_price'],
            'tp_percent': exits['tp_percent'],
            'sl_percent': self.risk_manager.sl_percent,
            'leverage': self.risk_manager.leverage,
            'timestamp': candle.get('timestamp', candle.get('time'))
        }
        
        return order
    
    def _has_sufficient_data(self) -> bool:
        """Check if indicators used in score have enough data"""
        # Only check indicators with non-zero weight
        for ind_config in self.score_engine.score_indicators:
            name = ind_config.get('name', '').upper()
            weight = ind_config.get('weight', 0)
            if weight > 0 and name in self.indicators:
                if self.indicators[name].value() is None:
                    return False
        return True
    
    def update_exits(self, position_id: str, current_price: float) -> Optional[float]:
        """Update dynamic TP for position"""
        return self.exit_engine.update_dynamic_tp(position_id, current_price)
    
    def check_exit(self, position_id: str, current_price: float) -> Optional[str]:
        """Check if position should exit"""
        return self.exit_engine.check_exit(position_id, current_price)


class StrategyManager:
    """Manages multiple strategies"""
    
    def __init__(self):
        self.strategies: Dict[str, Strategy] = {}
    
    def add_strategy(self, strategy: Strategy) -> None:
        """Add strategy to manager"""
        self.strategies[strategy.id] = strategy
    
    def get_strategy(self, strategy_id: str) -> Optional[Strategy]:
        """Get strategy by ID"""
        return self.strategies.get(strategy_id)
    
    def get_enabled_strategies(self) -> List[Strategy]:
        """Get all enabled strategies"""
        return [s for s in self.strategies.values() if s.enabled]
    
    def on_bar(self, candle: dict, balance: float, **kwargs) -> List[dict]:
        """Process bar for all enabled strategies"""
        orders = []
        
        for strategy in self.get_enabled_strategies():
            if strategy.symbol == candle.get('symbol'):
                order = strategy.on_bar(candle, balance, **kwargs)
                if order:
                    orders.append(order)
        
        return orders
    
    def remove_strategy(self, strategy_id: str) -> None:
        """Remove strategy"""
        if strategy_id in self.strategies:
            del self.strategies[strategy_id]
