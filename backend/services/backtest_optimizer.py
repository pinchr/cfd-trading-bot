"""
Backtest Optimizer Service
Continuously evaluates strategy performance and finds optimal parameters.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import asyncio

# Path helpers
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
RESULTS_FILE = os.path.join(DATA_DIR, "backtest_results.json")
BEST_STRATEGIES_FILE = os.path.join(DATA_DIR, "best_strategies.json")
OPTIMIZATION_LOG = os.path.join(BASE_DIR, "OPTIMIZATION_LOG.md")

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.join(DATA_DIR, "optimization_history"), exist_ok=True)


@dataclass
class BacktestResult:
    """Single backtest result entry."""
    strategy_id: str
    symbol: str
    timeframe: str
    lookback_period: str
    candle_count: int
    parameters: Dict[str, Any]
    metrics: Dict[str, float]
    insights: Dict[str, str]
    timestamp: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class BacktestOptimizer:
    """Main optimizer class that runs backtests and finds best parameters."""
    
    # Parameter search space
    PARAM_SPACE = {
        "min_score": [0.01, 0.03, 0.05, 0.08, 0.10, 0.15, 0.20],
        "min_agreement": [2, 3],
        "htf_timeframe": ["30m", "1h"],
        "htf_filter_enabled": [True, False],
    }
    
    # Symbol + TF combinations to test
    TEST_COMBINATIONS = [
        {"symbol": "XAU", "timeframe": "5m"},
        {"symbol": "XAG", "timeframe": "5m"},
        {"symbol": "BTC", "timeframe": "5m"},
        {"symbol": "US100", "timeframe": "5m"},
    ]
    
    def __init__(self):
        self.results: List[BacktestResult] = []
        self.best_strategies: Dict[str, Dict] = {}
        self.load_results()
        self.load_best_strategies()
    
    def load_results(self):
        """Load previous results from disk."""
        if os.path.exists(RESULTS_FILE):
            try:
                with open(RESULTS_FILE) as f:
                    data = json.load(f)
                    self.results = [BacktestResult(**r) for r in data]
            except Exception as e:
                print(f"[OPTIMIZER] Failed to load results: {e}")
                self.results = []
    
    def save_results(self):
        """Persist results to disk."""
        with open(RESULTS_FILE, 'w') as f:
            json.dump([asdict(r) for r in self.results], f, indent=2)
    
    def load_best_strategies(self):
        """Load current best strategies."""
        if os.path.exists(BEST_STRATEGIES_FILE):
            try:
                with open(BEST_STRATEGIES_FILE) as f:
                    self.best_strategies = json.load(f)
            except Exception:
                self.best_strategies = {}
    
    def save_best_strategies(self):
        """Save best strategies."""
        with open(BEST_STRATEGIES_FILE, 'w') as f:
            json.dump(self.best_strategies, f, indent=2)
    
    def get_lookback_period(self, timeframe: str) -> str:
        """Return lookback period based on timeframe."""
        lookbacks = {
            "5m": "1 week",
            "15m": "2 weeks",
            "30m": "2 weeks",
            "1h": "1 month",
            "4h": "3 months",
            "1d": "1 year",
        }
        return lookbacks.get(timeframe, "1 week")
    
    def get_candle_count_estimate(self, timeframe: str) -> int:
        """Estimate candle count for lookback period."""
        # Rough estimates per timeframe
        counts = {
            "5m": 2016,    # 7 days * 12h * 28 candles/hr
            "15m": 672,    # 7 days * 12h * 8 candles/hr
            "30m": 336,    # 7 days * 12h * 4 candles/hr
            "1h": 168,     # 7 days * 24h
            "4h": 126,     # 21 days * 6 candles/day
            "1d": 365,     # 1 year
        }
        return counts.get(timeframe, 1000)
    
    def get_next_combinations(self, count: int = 5) -> List[Dict]:
        """Get next parameter combinations to test."""
        tested = set()
        for r in self.results:
            key = f"{r.symbol}_{r.timeframe}_{json.dumps(r.parameters, sort_keys=True)}"
            tested.add(key)
        
        # Get untested combinations
        candidates = []
        for combo in self.TEST_COMBINATIONS:
            symbol = combo["symbol"]
            tf = combo["timeframe"]
            
            # Try different min_score values
            for min_score in self.PARAM_SPACE["min_score"]:
                params = {"min_score": min_score}
                key = f"{symbol}_{tf}_{json.dumps(params, sort_keys=True)}"
                
                if key not in tested:
                    candidates.append({
                        "symbol": symbol,
                        "timeframe": tf,
                        "parameters": params,
                    })
                    
                    if len(candidates) >= count:
                        return candidates
        
        # If we've tested everything, return random combinations for exploration
        if not candidates:
            import random
            for _ in range(count):
                combo = random.choice(self.TEST_COMBINATIONS)
                params = {
                    "min_score": random.choice(self.PARAM_SPACE["min_score"]),
                }
                candidates.append({
                    "symbol": combo["symbol"],
                    "timeframe": combo["timeframe"],
                    "parameters": params,
                })
        
        return candidates[:count]
    
    async def run_single_backtest(self, symbol: str, timeframe: str, 
                                   params: Dict) -> Optional[BacktestResult]:
        """Run a single backtest with given parameters."""
        try:
            # Import here to avoid circular dependencies
            from backtester import run_backtest, INSTRUMENT_CONFIG
            import database as db
            
            # Map timeframe to resolution
            resolution_map = {
                "5m": "5",
                "15m": "15", 
                "30m": "30",
                "1h": "60",
                "4h": "240",
                "1d": "D",
            }
            resolution = resolution_map.get(timeframe, "5")
            
            # Get candles from DB (try backtest_cache first, then regular)
            candles_data = await db.async_load_candles(symbol, resolution)
            
            # Fallback to backtest cache
            if not candles_data:
                candles_data = await asyncio.to_thread(
                    db.load_backtest_candles, symbol, resolution
                )
            
            if not candles_data or not candles_data.get("candles"):
                print(f"[OPTIMIZER] No candles for {symbol} {timeframe}")
                return None
            
            candles = candles_data["candles"]
            if len(candles) < 100:
                print(f"[OPTIMIZER] Not enough candles for {symbol} {timeframe}: {len(candles)}")
                return None
            
            # Override min_score in instrument config
            from backtester import INSTRUMENT_CONFIG
            original_config = INSTRUMENT_CONFIG.get(symbol, {}).copy()
            INSTRUMENT_CONFIG[symbol] = {
                **original_config,
                "min_score": params.get("min_score", 0.05),
            }
            
            try:
                # Run backtest
                result = run_backtest(
                    candles=candles,
                    symbol=symbol,
                    initial_balance=3000.0,
                    verbose=False,
                )
                
                # Extract metrics from BacktestResult
                metrics = {
                    "trade_count": result.total_trades,
                    "pnl_pct": result.total_return_pct,
                    "win_rate": result.win_rate,
                    "max_drawdown": result.max_drawdown_pct,
                    "profit_factor": result.profit_factor,
                }
                
                # Add loss rate
                if result.total_trades > 0:
                    metrics["loss_rate"] = (result.losing_trades / result.total_trades) * 100
                    metrics["avg_trade_pct"] = result.total_return_pct / result.total_trades
                else:
                    metrics["loss_rate"] = 0
                    metrics["avg_trade_pct"] = 0
                
                backtest_result = BacktestResult(
                    strategy_id=f"{symbol}_{timeframe}_optimized",
                    symbol=symbol,
                    timeframe=timeframe,
                    lookback_period=self.get_lookback_period(timeframe),
                    candle_count=len(candles),
                    parameters=params,
                    metrics=metrics,
                    insights={},
                )
                
                print(f"[OPTIMIZER] {symbol} {timeframe}: {metrics['trade_count']} trades, "
                      f"WR {metrics['win_rate']:.1f}%, PnL {metrics['pnl_pct']:.2f}%")
                
                return backtest_result
                
            finally:
                # Restore original config
                if symbol in INSTRUMENT_CONFIG:
                    INSTRUMENT_CONFIG[symbol] = original_config
                    
        except Exception as e:
            print(f"[OPTIMIZER] Backtest failed for {symbol} {timeframe}: {e}")
            return None
    
    async def run_optimization_cycle(self, combinations: int = 5) -> List[BacktestResult]:
        """Run optimization cycle - test N combinations."""
        print(f"[OPTIMIZER] Starting optimization cycle with {combinations} combinations...")
        
        new_results = []
        to_test = self.get_next_combinations(combinations)
        
        for combo in to_test:
            result = await self.run_single_backtest(
                combo["symbol"],
                combo["timeframe"],
                combo["parameters"],
            )
            
            if result:
                new_results.append(result)
                self.results.append(result)
        
        self.save_results()
        
        # Analyze and generate insights
        self.analyze_results(new_results)
        
        return new_results
    
    def analyze_results(self, new_results: List[BacktestResult]):
        """Analyze new results and generate insights."""
        if not new_results:
            return
        
        # Analyze min_score impact
        min_score_impact = {}
        for r in self.results:
            ms = r.parameters.get("min_score")
            if ms not in min_score_impact:
                min_score_impact[ms] = {"trades": [], "wr": [], "pnl": []}
            
            min_score_impact[ms]["trades"].append(r.metrics["trade_count"])
            min_score_impact[ms]["wr"].append(r.metrics["win_rate"])
            min_score_impact[ms]["pnl"].append(r.metrics["pnl_pct"])
        
        # Generate insights
        insights = []
        for ms, data in min_score_impact.items():
            avg_wr = sum(data["wr"]) / len(data["wr"]) if data["wr"] else 0
            avg_pnl = sum(data["pnl"]) / len(data["pnl"]) if data["pnl"] else 0
            total_trades = sum(data["trades"])
            
            if total_trades > 10:  # Only for significant samples
                insights.append(
                    f"min_score={ms}: avg WR={avg_wr:.1f}%, avg PnL={avg_pnl:.2f}%, "
                    f"total trades={total_trades}"
                )
        
        # Log to file
        with open(OPTIMIZATION_LOG, "a") as f:
            f.write(f"\n### {datetime.now().isoformat()}\n")
            f.write(f"Tested: {len(new_results)} combinations\n")
            f.write("Insights:\n")
            for insight in insights:
                f.write(f"- {insight}\n")
    
    def find_winner(self, symbol: str, timeframe: str) -> Optional[BacktestResult]:
        """Find best strategy for a symbol/timeframe."""
        symbol_results = [
            r for r in self.results 
            if r.symbol == symbol and r.timeframe == timeframe
        ]
        
        if not symbol_results:
            return None
        
        # Score: prioritize PnL, then win rate, then trade count (for significance)
        def score(r: BacktestResult) -> float:
            m = r.metrics
            # Must have minimum trades for significance
            if m["trade_count"] < 10:
                return -999
            # Must have reasonable win rate
            if m["win_rate"] < 35:
                return -999
            # Score formula
            return m["pnl_pct"] * 2 + m["win_rate"] * 0.1
        
        return max(symbol_results, key=score)
    
    async def run_summary_cycle(self) -> Dict:
        """Run hourly summary cycle - compare and promote winners."""
        print("[OPTIMIZER] Running summary cycle...")
        
        # Count results from last hour
        one_hour_ago = datetime.now() - timedelta(hours=1)
        recent_results = [r for r in self.results 
                        if datetime.fromisoformat(r.timestamp) > one_hour_ago]
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "tested_this_hour": len(recent_results),
            "new_winners": [],
            "observations": [],
        }
        
        for combo in self.TEST_COMBINATIONS:
            winner = self.find_winner(combo["symbol"], combo["timeframe"])
            
            if winner:
                key = f"{winner.symbol}_{winner.timeframe}"
                current_best = self.best_strategies.get(key)
                
                if current_best:
                    # Compare with current best
                    old_score = (
                        current_best.get("pnl_pct", 0) * 2 + 
                        current_best.get("win_rate", 0) * 0.1
                    )
                    new_score = (
                        winner.metrics["pnl_pct"] * 2 + 
                        winner.metrics["win_rate"] * 0.1
                    )
                    
                    if new_score > old_score:
                        self.best_strategies[key] = {
                            "strategy_id": winner.strategy_id,
                            "parameters": winner.parameters,
                            "metrics": winner.metrics,
                            "updated": datetime.now().isoformat(),
                        }
                        summary["new_winners"].append({
                            "symbol": winner.symbol,
                            "timeframe": winner.timeframe,
                            "improvement": new_score - old_score,
                        })
                else:
                    # First winner for this combo
                    self.best_strategies[key] = {
                        "strategy_id": winner.strategy_id,
                        "parameters": winner.parameters,
                        "metrics": winner.metrics,
                        "updated": datetime.now().isoformat(),
                    }
                    summary["new_winners"].append({
                        "symbol": winner.symbol,
                        "timeframe": winner.timeframe,
                        "improvement": 0,
                    })
        
        self.save_best_strategies()
        
        # Generate summary report
        await self.generate_summary_report(summary)
        
        return summary
    
    async def generate_summary_report(self, summary: Dict):
        """Generate hourly summary report."""
        report = f"""
### Hourly Optimization Summary [{datetime.now().strftime('%Y-%m-%d %H:%M')}]
- **Tested:** {summary['tested_this_hour']} combinations across {len(self.TEST_COMBINATIONS)} symbols.
"""
        
        if summary["new_winners"]:
            for w in summary["new_winners"]:
                report += f"- **New Winner:** {w['symbol']} {w['timeframe']} - Beat baseline by {w['improvement']:.2f} points.\n"
        else:
            report += "- **No new winners found.**\n"
        
        # Add observations from insights
        if len(self.results) > 10:
            recent = self.results[-20:]
            
            # Group by min_score
            ms_groups = {}
            for r in recent:
                ms = r.parameters.get("min_score")
                if ms not in ms_groups:
                    ms_groups[ms] = []
                ms_groups[ms].append(r.metrics["win_rate"])
            
            if len(ms_groups) > 1:
                report += "- **Observations:**\n"
                for ms, wrs in sorted(ms_groups.items()):
                    avg_wr = sum(wrs) / len(wrs)
                    report += f" - min_score {ms}: avg WR {avg_wr:.1f}%\n"
        
        print(report)
        
        # Save to log
        with open(OPTIMIZATION_LOG, "a") as f:
            f.write(report)


# Global optimizer instance
_optimizer: Optional[BacktestOptimizer] = None


def get_optimizer() -> BacktestOptimizer:
    """Get or create global optimizer."""
    global _optimizer
    if _optimizer is None:
        _optimizer = BacktestOptimizer()
    return _optimizer


async def run_cycle():
    """Run a single optimization cycle."""
    optimizer = get_optimizer()
    await optimizer.run_optimization_cycle(5)


async def run_summary():
    """Run hourly summary."""
    optimizer = get_optimizer()
    return await optimizer.run_summary_cycle()
