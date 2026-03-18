# CFD Trading Bot - Issues & Fixes Log

## Date: 2026-03-04

---

## Issue 1: Critical Logic Error - RSI Momentum Signal Inversion

**Severity:** CRITICAL (Trading Logic Bug)
**Component:** `backend/strategy/strategy.py` - Method: `_get_signal_rsi_momentum()`
**Branch:** `march_2`

### The Problem

The momentum calculation logic was mathematically inverted, causing the bot to generate opposite trade signals. This directly led to losing trades.

**Incorrect Logic (Before):**
```python
elif mom_val is not None and mom_val < momentum_threshold:
    direction = 'buy'  # Price DOWN = BUY (WRONG!)

elif mom_val is not None and mom_val > momentum_threshold:
    direction = 'sell'  # Price UP = SELL (WRONG!)
```

### Root Cause

The developer confused "momentum" direction with "price" direction. Momentum is the rate of price change:
- Positive momentum = price is rising = BULLISH = BUY signal
- Negative momentum = price is falling = BEARISH = SELL signal

### The Fix

```python
elif mom_val is not None and mom_val > momentum_threshold:
    # Momentum > 0 means price is rising (bullish)
    direction = 'buy'

elif mom_val is not None and mom_val < momentum_threshold:
    # Momentum < 0 means price is falling (bearish)
    direction = 'sell'
```

### Impact

Strategies affected (using `direction_mode: "rsi_momentum"`):
- `btc_v3_exp`
- `xau_v3_exp`
- `xag_v3_exp`

These strategies were generating REVERSED signals - buying when they should sell and vice versa.

---

## Issue 2: Hardcoded Filters in Orchestrator (Architectural Issue)

**Severity:** MEDIUM (Architecture / Maintainability)
**Component:** `backend/main.py` - `_analyze_single_symbol()`
**Branch:** `march_2`

### The Problem

Global market filters (Volatility and VIX) were hardcoded directly in the main execution loop, violating separation of concerns:

```python
# Hardcoded in main.py - line ~1143
if atr_pct > 3.0:
    return Signal(...)  # Returns NEUTRAL, blocking ALL trades
```

Problems with this approach:
1. **No flexibility** - All strategies used the same 3% ATR threshold
2. **Violates SRP** - main.py should only orchestrate, not contain trading rules
3. **Hard to test** - Cannot test different filter configurations independently
4. **Strategy not source of truth** - The strategy should decide, not the orchestrator

### The Solution

Refactored to make Strategy the single source of truth:

1. **Added filter definitions to strategies.json:**
   ```json
   {
     "id": "btc_v3_exp",
     "filters": {
       "volatility": {
         "enabled": true,
         "max_atr_percent": 3.0
       },
       "vix": {
         "enabled": false,
         "max_vix": 30
       }
     }
   }
   ```

2. **Created new filter classes in `backend/strategy/filters.py`:**
   - `VolatilityFilter` - Checks if ATR% is within configured threshold
   - `VixFilter` - Checks if VIX is below configured threshold

3. **Updated FilterChain to include new filters:**
   ```python
   def check_all(self, candle, symbol, direction, atr_percent=None, vix_value=None):
       # Now checks: volume, position_already_open, symbol_enabled, htf_trend, volatility, vix
   ```

4. **Updated `analyze_with_new_strategy()` to pass market data to filters:**
   ```python
   new_result = analyze_with_new_strategy(
       symbol, candles, current_price, balance,
       atr_percent=atr_pct,
       vix_value=vix_data.get('value') if vix_data else None
   )
   ```

5. **Removed hardcoded filter from main.py:**
   - Deleted the early-return logic when ATR% > 3%
   - Now filters are checked inside the strategy

### Benefits of New Architecture

| Before | After |
|--------|-------|
| main.py decides if market is too volatile | Strategy decides based on its config |
| One threshold for all strategies | Each strategy has own thresholds |
| Hard to change filter params | Change via JSON, no code changes |
| Violates separation of concerns | Strategy is source of truth |

---

## Issue 3: Signal Generation Flow Complexity

**Severity:** LOW (Code Clarity)
**Component:** Multiple files

### The Problem

Signal generation has multiple paths that behave differently:
- **New path:** `analyze_with_new_strategy()` → uses `strategy/strategy.py` ScoreEngine
- **Legacy path:** `calculate_signal_score()` → uses `strategies.py` AdaptiveRegimeStrategy

Both use different normalization and weighting, making it hard to predict behavior.

### Recommendation

Standardize on the JSON-based strategy path. Legacy strategies should be migrated to JSON format.

---

## Summary of Changes

### Files Modified

| File | Change |
|------|--------|
| `backend/strategy/strategy.py` | Fixed inverted momentum logic, updated on_bar() to accept atr_percent and vix_value |
| `backend/strategy/filters.py` | Added VolatilityFilter and VixFilter classes, updated FilterChain |
| `backend/strategy/strategies.json` | Added volatility and vix filter configs to all strategies |
| `backend/main.py` | Removed hardcoded volatility filter, updated analyze_with_new_strategy() call |

### Testing Recommendations

1. **Logic Verification:**
   - [ ] Test with rising prices → should get BUY signal
   - [ ] Test with falling prices → should get SELL signal

2. **Filter Verification:**
   - [ ] Set strategy max_atr_percent: 1.0, verify trades blocked when ATR% > 1%
   - [ ] Set vix.enabled: true, max_vix: 20, verify trades blocked when VIX > 20

3. **Regression:**
   - [ ] Verify main.py runs without errors
   - [ ] Verify existing strategies still work

---

*Log created: 2026-03-04*
