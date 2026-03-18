"""
A/B Backtesting Framework
Uses the same functions as live trading for signal generation and position management.
"""
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import uuid


@dataclass
class BacktestTrade:
    """Single trade result from backtest"""
    entry_price: float
    exit_price: float
    size: float
    direction: int
    entry_time: Any
    exit_time: Any
    pnl_usd: float
    result: str  # 'win', 'loss', 'breakeven'
    exit_type: str  # 'TP', 'SL', 'trailing', 'time'
    score: float
    confidence: float
    tp_price: float
    sl_price: float


@dataclass
class BacktestResult:
    """Complete backtest result"""
    run_id: str
    strategy_id: str
    strategy_config: dict
    symbol: str
    resolution: str
    days: int
    initial_balance: float
    final_balance: float
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    total_pnl_percent: float
    avg_trade_pnl: float
    max_drawdown: float
    avg_score: float
    avg_confidence: float
    trades: List[Dict]
    candles_used: int
    execution_time_seconds: float
    created_at: str


class BacktestEngine:
    """
    Core backtest engine using the same functions as live trading.
    """
    
    def __init__(self, db=None):
        self.db = db
        self._load_functions()
    
    def _load_functions(self):
        """Load trading functions from live trading modules"""
        from services.trading_engine import (
            calculate_adaptive_tp_sl,
            calculate_dynamic_position_size
        )
        self.calculate_adaptive_tp_sl = calculate_adaptive_tp_sl
        self.calculate_dynamic_position_size = calculate_dynamic_position_size
    
    def run(
        self,
        symbol: str,
        strategy_config: dict,
        days: int = 3,
        resolution: str = "5",
        initial_balance: float = 3000.0,
        warmup_candles: int = 50
    ) -> BacktestResult:
        """Run a backtest for given symbol and strategy"""
        start_time = time.time()
        
        # Get candles from database
        candles = self._get_candles(symbol, resolution, days)
        
        if not candles:
            raise ValueError(f"No candles found for {symbol} {resolution}")
        
        if len(candles) <= warmup_candles:
            raise ValueError(f"Not enough candles: {len(candles)}, need at least {warmup_candles}")
        
        # Initialize strategy manager
        from strategy import load_strategies_from_json
        
        json_str = json.dumps({'strategies': [strategy_config]})
        manager = load_strategies_from_json(json_str)
        
        # Get strategy exits and sizing config
        exits_v2 = strategy_config.get('exits_v2', {})
        sizing_v2 = strategy_config.get('position_sizing_v2', {})
        
        # Base TP/SL percentages
        tp_pct = exits_v2.get('base_tp_percent', 2.5) / 100 if exits_v2 else 0.025
        sl_pct = exits_v2.get('base_sl_percent', 1.5) / 100 if exits_v2 else 0.015
        
        # Initialize indicators with warmup data
        for i, candle in enumerate(candles[:warmup_candles]):
            candle_data = self._candle_to_dict(candle)
            for strat in manager.get_enabled_strategies():
                for ind in strat.indicators.values():
                    ind.update(candle_data)
        
        # Run backtest
        balance = initial_balance
        trades = []
        position = None
        open_positions_count = 0
        max_balance = initial_balance
        max_drawdown = 0.0
        total_score = 0.0
        total_confidence = 0.0
        
        # Start trading after warmup
        for i, candle in enumerate(candles[warmup_candles:], start=warmup_candles):
            candle_data = self._candle_to_dict(candle)
            current_price = candle.get('close')
            current_time = candle.get('timestamp')
            
            # Get signal from strategy
            for strat in manager.get_enabled_strategies():
                if position is None:
                    signal = strat.on_bar(candle_data, balance)
                    
                    if signal:
                        # Use unified adaptive TP/SL calculation
                        direction = 'buy' if signal.get('direction', 0) > 0 else 'sell'
                        
                        # Get lookback candles for TP/SL calculation
                        lookback_start = max(warmup_candles, i - 50)
                        lookback_candles = [self._candle_to_dict(candles[j]) 
                                           for j in range(lookback_start, i)]
                        
                        # Calculate adaptive TP/SL
                        try:
                            tp_price, sl_price = self.calculate_adaptive_tp_sl(
                                strategy_config=strategy_config,
                                candles=lookback_candles,
                                entry_price=current_price,
                                direction=direction
                            )
                        except Exception as e:
                            # Fallback to simple percentage
                            if direction == 'buy':
                                tp_price = current_price * (1 + tp_pct)
                                sl_price = current_price * (1 - sl_pct)
                            else:
                                tp_price = current_price * (1 - tp_pct)
                                sl_price = current_price * (1 + sl_pct)
                        
                        # Calculate dynamic position size
                        score = abs(signal.get('score', 0.5))
                        conf = signal.get('confidence', 0.5)
                        
                        # Get volatility (ATR-based)
                        volatility = 0.0
                        if len(lookback_candles) >= 20:
                            try:
                                from strategy.technical import TechnicalIndicators
                                ind = TechnicalIndicators.calculate_all(lookback_candles[-20:], period=14)
                                atr = ind.get('atr_14', 0)
                                volatility = (atr / current_price) * 100 if current_price > 0 else 0
                            except:
                                pass
                        
                        try:
                            size = self.calculate_dynamic_position_size(
                                strategy_config=strategy_config,
                                account_balance=balance,
                                entry_price=current_price,
                                stop_loss_price=sl_price,
                                signal_score=score,
                                signal_confidence=conf,
                                open_positions_count=open_positions_count,
                                volatility=volatility
                            )
                        except:
                            # Fallback calculation
                            leverage = strategy_config.get('risk', {}).get('leverage', 20)
                            size = (balance * 0.02 * leverage) / current_price
                        
                        # Track for metrics
                        total_score += score
                        total_confidence += conf
                        open_positions_count += 1
                        
                        # Open position
                        position = {
                            'entry_price': current_price,
                            'size': size,
                            'direction': 1 if direction == 'buy' else -1,
                            'entry_time': current_time,
                            'tp_price': tp_price,
                            'sl_price': sl_price,
                            'score': score,
                            'confidence': conf
                        }
            
            # Check if we have a position
            if position:
                direction = position['direction']
                
                # Check TP/SL
                if direction > 0:  # Long
                    if current_price >= position['tp_price']:
                        # TP hit
                        pnl = position['size'] * position['entry_price'] * tp_pct * strategy_config.get('risk', {}).get('leverage', 20)
                        balance += pnl
                        trades.append(BacktestTrade(
                            entry_price=position['entry_price'],
                            exit_price=current_price,
                            size=position['size'],
                            direction=position['direction'],
                            entry_time=position['entry_time'],
                            exit_time=current_time,
                            pnl_usd=pnl,
                            result='win',
                            exit_type='TP',
                            score=position['score'],
                            confidence=position['confidence'],
                            tp_price=position['tp_price'],
                            sl_price=position['sl_price']
                        ))
                        position = None
                    elif current_price <= position['sl_price']:
                        # SL hit
                        pnl = -position['size'] * position['entry_price'] * sl_pct * strategy_config.get('risk', {}).get('leverage', 20)
                        balance += pnl
                        trades.append(BacktestTrade(
                            entry_price=position['entry_price'],
                            exit_price=current_price,
                            size=position['size'],
                            direction=position['direction'],
                            entry_time=position['entry_time'],
                            exit_time=current_time,
                            pnl_usd=pnl,
                            result='loss',
                            exit_type='SL',
                            score=position['score'],
                            confidence=position['confidence'],
                            tp_price=position['tp_price'],
                            sl_price=position['sl_price']
                        ))
                        position = None
                else:  # Short
                    if current_price <= position['tp_price']:
                        pnl = position['size'] * position['entry_price'] * tp_pct * strategy_config.get('risk', {}).get('leverage', 20)
                        balance += pnl
                        trades.append(BacktestTrade(
                            entry_price=position['entry_price'],
                            exit_price=current_price,
                            size=position['size'],
                            direction=position['direction'],
                            entry_time=position['entry_time'],
                            exit_time=current_time,
                            pnl_usd=pnl,
                            result='win',
                            exit_type='TP',
                            score=position['score'],
                            confidence=position['confidence'],
                            tp_price=position['tp_price'],
                            sl_price=position['sl_price']
                        ))
                        position = None
                    elif current_price >= position['sl_price']:
                        pnl = -position['size'] * position['entry_price'] * sl_pct * strategy_config.get('risk', {}).get('leverage', 20)
                        balance += pnl
                        trades.append(BacktestTrade(
                            entry_price=position['entry_price'],
                            exit_price=current_price,
                            size=position['size'],
                            direction=position['direction'],
                            entry_time=position['entry_time'],
                            exit_time=current_time,
                            pnl_usd=pnl,
                            result='loss',
                            exit_type='SL',
                            score=position['score'],
                            confidence=position['confidence'],
                            tp_price=position['tp_price'],
                            sl_price=position['sl_price']
                        ))
                        position = None
                
                # Track max balance and drawdown
                if balance > max_balance:
                    max_balance = balance
                drawdown = (max_balance - balance) / max_balance * 100 if max_balance > 0 else 0
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
        
        # Close any open position at the end
        if position:
            final_price = candles[-1].get('close')
            direction = position['direction']
            if direction > 0:
                pnl = position['size'] * position['entry_price'] * ((final_price - position['entry_price']) / position['entry_price'])
            else:
                pnl = position['size'] * position['entry_price'] * ((position['entry_price'] - final_price) / position['entry_price'])
            balance += pnl
        
        # Calculate metrics
        wins = len([t for t in trades if t.result == 'win'])
        losses = len([t for t in trades if t.result == 'loss'])
        total_trades = len(trades)
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        total_pnl = balance - initial_balance
        total_pnl_percent = (total_pnl / initial_balance) * 100
        avg_trade_pnl = total_pnl / total_trades if total_trades > 0 else 0
        avg_score = total_score / total_trades if total_trades > 0 else 0
        avg_confidence = total_confidence / total_trades if total_trades > 0 else 0
        
        # Create result
        result = BacktestResult(
            run_id=str(uuid.uuid4())[:8],
            strategy_id=strategy_config.get('id', 'unknown'),
            strategy_config=strategy_config,
            symbol=symbol,
            resolution=resolution,
            days=days,
            initial_balance=initial_balance,
            final_balance=round(balance, 2),
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            win_rate=round(win_rate, 1),
            total_pnl=round(total_pnl, 2),
            total_pnl_percent=round(total_pnl_percent, 2),
            avg_trade_pnl=round(avg_trade_pnl, 2),
            max_drawdown=round(max_drawdown, 2),
            avg_score=round(avg_score, 3),
            avg_confidence=round(avg_confidence, 3),
            trades=[asdict(t) for t in trades],
            candles_used=len(candles) - warmup_candles,
            execution_time_seconds=round(time.time() - start_time, 2),
            created_at=datetime.utcnow().isoformat()
        )
        
        return result
    
    def _get_candles(self, symbol: str, resolution: str, days: int):
        """Get candles from database"""
        if self.db is None:
            from database import get_db
            self.db = get_db()
        
        end_ts = int(time.time() * 1000)
        start_ts = end_ts - (days * 24 * 60 * 60 * 1000)
        
        # Query - for BTC, only use binance source
        query = {'symbol': symbol.upper(), 'resolution': resolution}
        if symbol.upper() == "BTC":
            query['source'] = 'binance'
        
        candles = list(self.db.candles.find({
            **query,
            'timestamp': {'$gte': start_ts, '$lte': end_ts}
        }).sort('timestamp', 1))
        
        # Fallback without source filter
        if not candles:
            candles = list(self.db.candles.find({
                'symbol': symbol.upper(),
                'resolution': resolution,
                'timestamp': {'$gte': start_ts, '$lte': end_ts}
            }).sort('timestamp', 1))
        
        # Fallback with string timestamps (XAU/XAG style)
        if not candles:
            start_str = datetime.fromtimestamp(start_ts / 1000).isoformat() + 'Z'
            end_str = datetime.fromtimestamp(end_ts / 1000).isoformat() + 'Z'
            
            if symbol.upper() == "BTC":
                candles = list(self.db.candles.find({
                    **query,
                    'timestamp': {'$gte': start_str, '$lte': end_str}
                }).sort('timestamp', 1))
            else:
                candles = list(self.db.candles.find({
                    'symbol': symbol.upper(),
                    'resolution': resolution,
                    'timestamp': {'$gte': start_str, '$lte': end_str}
                }).sort('timestamp', 1))
        
        return candles
    
    def _candle_to_dict(self, candle) -> dict:
        """Convert candle to dict format"""
        return {
            'open': candle.get('open'),
            'high': candle.get('high'),
            'low': candle.get('low'),
            'close': candle.get('close'),
            'volume': candle.get('volume', 0),
            'timestamp': candle.get('timestamp')
        }
    
    def save_result(self, result: BacktestResult) -> str:
        """Save result to backtest_results collection"""
        if self.db is None:
            from database import get_db
            self.db = get_db()
        
        doc = asdict(result)
        self.db.backtest_results.insert_one(doc)
        return result.run_id


class ABTestFramework:
    """
    A/B Testing framework for comparing multiple strategies.
    """
    
    def __init__(self, db=None):
        self.db = db
        self.engine = BacktestEngine(db)
    
    def run_ab_test(
        self,
        symbol: str,
        strategy_a: dict,
        strategy_b: dict,
        days: int = 3,
        resolution: str = "5",
        initial_balance: float = 3000.0
    ) -> Dict:
        """Run A/B test comparing two strategies"""
        
        # Run backtest for strategy A
        result_a = self.engine.run(
            symbol=symbol,
            strategy_config=strategy_a,
            days=days,
            resolution=resolution,
            initial_balance=initial_balance
        )
        
        # Run backtest for strategy B
        result_b = self.engine.run(
            symbol=symbol,
            strategy_config=strategy_b,
            days=days,
            resolution=resolution,
            initial_balance=initial_balance
        )
        
        # Calculate comparison metrics
        comparison = {
            'symbol': symbol,
            'days': days,
            'resolution': resolution,
            'strategy_a': {
                'id': result_a.strategy_id,
                'total_pnl': result_a.total_pnl,
                'total_pnl_percent': result_a.total_pnl_percent,
                'win_rate': result_a.win_rate,
                'total_trades': result_a.total_trades,
                'max_drawdown': result_a.max_drawdown,
                'avg_score': result_a.avg_score
            },
            'strategy_b': {
                'id': result_b.strategy_id,
                'total_pnl': result_b.total_pnl,
                'total_pnl_percent': result_b.total_pnl_percent,
                'win_rate': result_b.win_rate,
                'total_trades': result_b.total_trades,
                'max_drawdown': result_b.max_drawdown,
                'avg_score': result_b.avg_score
            },
            'winner': None,
            'pnl_difference': 0,
            'win_rate_difference': 0
        }
        
        # Determine winner
        if result_a.total_pnl > result_b.total_pnl:
            comparison['winner'] = result_a.strategy_id
            comparison['pnl_difference'] = result_a.total_pnl - result_b.total_pnl
        elif result_b.total_pnl > result_a.total_pnl:
            comparison['winner'] = result_b.strategy_id
            comparison['pnl_difference'] = result_b.total_pnl - result_a.total_pnl
        
        comparison['win_rate_difference'] = result_a.win_rate - result_b.win_rate
        
        # Save results
        run_id = str(uuid.uuid4())[:8]
        
        # Create combined result document
        ab_result = {
            '_id': run_id,
            'type': 'ab_test',
            'symbol': symbol,
            'days': days,
            'resolution': resolution,
            'result_a': asdict(result_a),
            'result_b': asdict(result_b),
            'comparison': comparison,
            'created_at': datetime.utcnow().isoformat()
        }
        
        if self.db is None:
            from database import get_db
            self.db = get_db()
        
        self.db.backtest_results.insert_one(ab_result)
        
        return ab_result
    
    def get_results(self, symbol: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Get backtest results"""
        if self.db is None:
            from database import get_db
            self.db = get_db()
        
        query = {}
        if symbol:
            query['symbol'] = symbol.upper()
        
        results = list(self.db.backtest_results.find(query).sort('created_at', -1).limit(limit))
        
        # Convert ObjectId to string for JSON serialization
        for r in results:
            if '_id' in r:
                r['_id'] = str(r['_id'])
        
        return results
    
    def get_comparisons(self, symbol: Optional[str] = None, limit: int = 20) -> List[Dict]:
        """Get A/B test comparisons"""
        if self.db is None:
            from database import get_db
            self.db = get_db()
        
        query = {'type': 'ab_test'}
        if symbol:
            query['symbol'] = symbol.upper()
        
        results = list(self.db.backtest_results.find(query).sort('created_at', -1).limit(limit))
        
        for r in results:
            if '_id' in r:
                r['_id'] = str(r['_id'])
        
        return results
