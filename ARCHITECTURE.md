# CFD Trading Bot - Architecture Documentation

## Overview
Real-time CFD trading bot with signal generation, position management, and React frontend.

---

## Backend Structure (`/backend`)

### Entry Point
**`main.py`** - FastAPI application entry
- Initializes: broker, database, trading engine, market data
- Starts: `auto_trade_loop` + `price_cache_loop` as background tasks
- Handles: graceful shutdown

---

### Services Layer (`/services`)

| File | Purpose | Key Functions |
|------|---------|---------------|
| `state.py` | **Central state management** | `get_account()`, `get_open_positions()`, `set_account()`, `get_instruments()` |
| `trading_engine.py` | Main trading logic + signal generation | `auto_trade_loop()`, `_analyze_single_symbol()` |
| `market_data.py` | Price data fetching + caching | `update_live_price_cache()` |
| `signal_generator.py` | Technical indicator calculation | `generate_signals()` |
| `strategy_manager.py` | Strategy loading + analysis | `get_strategy()`, `analyze_with_new_strategy()` |
| `circuit_breaker.py` | API failure protection | Circuit breaker for external APIs |
| `backtest_engine.py` | Historical backtesting | `run_backtest()` |

---

## 🚀 NEW: Advanced Exit Strategy (TP/SL)

### Current Implementation (v0.4)
- Fixed percentage TP/SL per strategy
- Basic ATR filtering for volatility
- Basic Dynamic TP based on HTF RSI

### Required Enhancements

#### 1. Smart TP/SL Algorithm
```json
{
  "exits": {
    "stop_loss": {
      "method": "atr_multiplier",  // or: "fixed_percent", "support_resistance", "adaptive"
      "atr_multiplier": 2.0,
      "min_sl_percent": 1.0,
      "max_sl_percent": 3.0
    },
    "take_profit": {
      "method": "adaptive",  // combines multiple factors
      "components": [
        {"type": "percent", "weight": 0.3, "base": 2.5},
        {"type": "atr_multiplier", "weight": 0.3, "value": 3.0},
        {"type": "support_resistance", "weight": 0.2},
        {"type": "htf_indicator", "weight": 0.2, "indicator": "RSI", "thresholds": {"overbought": 70, "oversold": 30}}
      ],
      "min_rr_ratio": 1.5
    },
    "partial_exits": [
      {"tp_percent": 50, "close_percent": 30},
      {"tp_percent": 75, "close_percent": 50},
      {"tp_percent": 100, "close_percent": 20}
    ]
  }
}
```

#### 2. Support/Resistance Detection
- Calculate pivot points (PP, R1-R3, S1-S3)
- Find nearest support below entry (for LONG)
- Find nearest resistance above entry (for SHORT)
- Use for SL placement (below support / above resistance)

#### 3. HTF Confirmation
- Use HTF (1H, 4H, D1) indicators for TP confirmation
- If HTF RSI > 70 (overbought) → reduce TP target
- If HTF RSI < 30 (oversold) → extend TP target
- HTF trend alignment (price above/below SMA)

---

## 🚀 NEW: Dynamic Position Sizing

### Current Implementation (v0.4)
- Fixed risk % per strategy
- Simple formula: `(balance × risk × leverage) / price`

### Required Enhancements

```json
{
  "position_sizing": {
    "method": "adaptive",  // or: "fixed", "kelly", "volatility"
    "base_risk_percent": 2.0,
    
    // Dynamic modifiers
    "modifiers": {
      "open_positions": {
        "0": 1.0,    // 100% of base risk
        "1": 0.8,    // 80% of base risk
        "2": 0.6,    // 60% of base risk  
        "3+": 0.4    // 40% of base risk
      },
      "equity": {
        "high": 1.0,      // > $5000
        "medium": 0.75,  // $3000-$5000
        "low": 0.5       // < $3000
      },
      "volatility": {
        "low": 1.0,      // ATR < 1%
        "medium": 0.75,  // ATR 1-2%
        "high": 0.5      // ATR > 2%
      },
      "momentum": {
        "strong": 1.0,
        "weak": 0.5
      }
    },
    
    // Leverage scaling
    "max_leverage": 20,
    "min_leverage": 5,
    "leverage_by_volatility": true
  }
}
```

---

## 🚀 NEW: Dynamic Positions (Early Exit)

### Current Issues
- BUG: `original_signal_score = 0` - not saved when opening position
- Logic exists in `broker_sim.py:check_dynamic_exit()` but can't work

### Required Fixes
1. Save `signal_score` when opening position
2. Track signal decay: `current_score / original_score < 0.75` → close
3. Compare cross-symbol: if other symbol has higher score × confidence → close current

### Enhanced Logic
```python
def should_close_early(position, current_signals, all_positions):
    # 1. Signal decay check
    if position.original_signal_score > 0:
        decay_ratio = current_signals[position.symbol] / position.original_signal_score
        if decay_ratio < 0.75 and position.unrealized_pnl > 0:
            return True, "signal_decayed"
    
    # 2. Better opportunity check
    current_score = current_signals.get(position.symbol, 0)
    for sym, score in current_signals.items():
        if sym != position.symbol:
            # Check if other symbol has significantly better opportunity
            if score > current_score * 1.5 and position.unrealized_pnl > 0:
                return True, "better_opportunity"
    
    # 3. Too many positions - close weakest
    if len(all_positions) >= MAX_POSITIONS:
        # Find weakest position and close it
        pass
    
    return False, None
```

---

## 🚀 NEW: A/B Backtesting Framework

### Purpose
Compare different exit strategies, position sizing methods, and parameter combinations

### Required Components

```python
class BacktestConfig:
    # Strategy parameters to test
    variations = {
        "exit_method": ["fixed_percent", "atr_multiplier", "adaptive"],
        "risk_percent": [1.0, 1.5, 2.0, 2.5],
        "dynamic_positions": [True, False],
        "position_sizing": ["fixed", "adaptive"]
    }
    
    # Historical period
    start_date: datetime
    end_date: datetime
    symbols: List[str]
    
    # Metrics to track
    metrics = ["total_return", "sharpe_ratio", "max_drawdown", "win_rate", "avg_trade"]
```

### Output
- Comparison table: Strategy A vs Strategy B
- Statistical significance testing
- Best parameters recommendation

---

## Test Coverage Requirements

### Must Have Tests
1. **TP/SL Tests**
   - [ ] Different strategies produce different TP/SL
   - [ ] Dynamic TP adjusts based on HTF RSI
   - [ ] SL respects support/resistance levels
   - [ ] RR ratio >= min_rr_ratio

2. **Position Sizing Tests**
   - [ ] Size decreases with more open positions
   - [ ] Size decreases with lower equity
   - [ ] Size decreases with higher volatility

3. **Dynamic Positions Tests**
   - [ ] Position closes when signal decays > 25%
   - [ ] Position closes when better opportunity appears
   - [ ] Multiple positions managed correctly

4. **A/B Backtest Tests**
   - [ ] Can compare two strategy configurations
   - [ ] Results are statistically meaningful
   - [ ] Can identify best parameters

---

## File Changes Required

### New Files
- `strategy/exits_v2.py` - Advanced exit strategy engine
- `strategy/position_sizing_v2.py` - Dynamic position sizing
- `strategy/support_resistance.py` - S/R level detection
- `backtest/ab_testing.py` - A/B testing framework

### Modified Files
- `broker_sim.py` - Fix original_signal_score saving
- `services/trading_engine.py` - Use new exit/position sizing
- `strategy/strategies.json` - Add new config fields
- `api/routes/signals.py` - Return enhanced signal data
