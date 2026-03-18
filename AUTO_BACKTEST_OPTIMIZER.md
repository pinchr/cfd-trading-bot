# Auto Backtest Optimizer - Cronjob Specification

## Overview
A background service (cronjob) that continuously evaluates strategy performance, runs backtests for unexplored parameter combinations, and identifies optimal settings based on historical data.

## Execution Schedule

### 1. Optimization Cycle (Every 10 Minutes)
- **Target:** Process 5 strategy/parameter combinations per run.
- **Action:** 
 - Pick 5 least recently tested or unexplored combinations.
 - Run backtests using dynamic lookback windows.
 - Record results and insights.

### 2. Summary & Comparison Cycle (Every 1 Hour)
- **Action:**
 - Aggregate results from the last hour.
 - Compare against the daily "Best Strategy" baseline.
 - If a new winner is found, promote it to the daily baseline.
 - Generate a summary report with insights and observations.
 - Update decision logic for the next optimization cycle.
 - Persist the best strategy configuration for future comparison.

## Dynamic Lookback Windows
Lookback is scaled to ensure roughly the same candle count (~1,000 - 2,000 candles) for statistical relevance:
- **5m Timeframe:** 1 week lookback
- **15m Timeframe:** 2 weeks lookback
- **30m Timeframe:** 2 weeks lookback
- **1H Timeframe:** 1 month lookback
- **4H Timeframe:** 3 months lookback
- **1D Timeframe:** 1 year lookback

## Data Structure for Results (`backtest_results.json`)

Each result entry must include:
- `strategy_id`: Unique identifier
- `symbol`: Trading symbol (XAU, BTC, etc.)
- `timeframe`: Strategy TF (5m, 1h, etc.)
- `lookback_period`: Duration tested
- `candle_count`: Total candles processed
- `parameters`: JSON object of settings tested (min_score, weights, etc.)
- `metrics`:
 - `trade_count`: Total trades executed
 - `pnl_pct`: Total profit/loss percentage
 - `win_rate`: Percentage of winning trades
 - `loss_rate`: Percentage of losing trades
 - `max_drawdown`: Peak-to-trough decline
 - `profit_factor`: Gross profit / gross loss
 - `avg_trade_pct`: Average profit per trade
- `insights`:
 - `parameter_impact`: How specific changes affected results (e.g., "Increasing MACD weight improved win rate by 5% but reduced trade count by 10%")

## Logic & Analysis Requirements

### 1. Parameter Impact Tracking
The cronjob must analyze how individual parameters affect performance:
- **Trend Detection:** "Does higher min_score always lead to higher win rate?"
- **Filter Evaluation:** "Does the HTF filter prevent more losses than it cuts potential gains?"
- **Comparison:** Always compare results against the current "Best Strategy" for that specific symbol/timeframe.

### 2. Intelligent Search (Learning Mechanism)
- Use results from previous runs to decide what to test next.
- If increasing a parameter value improved results, continue in that direction.
- Avoid re-testing combinations that are logically similar to known poor performers.

### 3. Insights Persistence
- Save observations in a dedicated `optimization_log.md`.
- These insights should be read by the cronjob at startup to inform its search strategy.

## File Structure

- `backend/services/backtest_optimizer.py` - Core logic for running and analyzing tests.
- `backend/cron/optimizer_cron.py` - Scheduler (running every 10m and 1h).
- `backend/data/best_strategies.json` - Persistent storage for the current winners.
- `backend/data/optimization_history/` - Directory for detailed JSON result files.

## Summary Report Format (Hourly)

```markdown
### Hourly Optimization Summary [2026-03-12 14:00]
- **Tested:** 30 combinations across 5 symbols.
- **New Winner:** BTC_v2_aggressive (PnL +5.2%, WR 68%) - Beat baseline by 1.2%.
- **Observations:** 
 - min_score > 0.3 on US100 significantly reduces drawdown.
 - 1H HTF filter is 20% more effective than 30m for Gold.
- **Actionable Insight:** Increasing MOMENTUM weight on XAU 5m shows positive correlation with Profit Factor.
```

## Cronjob Setup

```bash
# Run as daemon (continuous 10min + 1hr cycles)
cd /Users/pinchr/dev/cfd-trading-bot/backend
python3 -m cron.optimizer_cron

# Or run once (quick test)
python3 -m cron.optimizer_cron --quick

# Add to crontab for auto-start on boot:
@reboot cd /Users/pinchr/dev/cfd-trading-bot/backend && python3 -m cron.optimizer_cron >> /Users/pinchr/logs/optimizer.log 2>&1

# Logs location
/Users/pinchr/logs/optimizer.log
```

## Commit Message Suggestion
`docs: add Auto Backtest Optimizer specification (AUTO_BACKTEST_OPTIMIZER.md)`
