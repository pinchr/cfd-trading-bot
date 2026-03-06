# CFD Trading Bot - Project Documentation

## Overview

AI-powered CFD trading bot for XAU (Gold), XAG (Silver), BTC (Bitcoin), and US100 (Nasdaq). Uses technical indicators, multi-timeframe analysis, and JSON-defined strategies.

---

## Current Architecture

### Tech Stack
- **Backend:** FastAPI (Python) — Port 8001
- **Frontend:** React + Vite — Port 5173
- **Database:** MongoDB Atlas (cloud)
- **Data Sources:** Yahoo Finance, Alpha Vantage, Binance

### Symbols Supported
- **XAU** (Gold) — Primary
- **XAG** (Silver)
- **BTC** (Bitcoin)
- **US100** (Nasdaq-100)

---

## Project Structure

```
cfd-trading-bot/
├── backend/
│   ├── main.py              # FastAPI app, trading logic, API endpoints
│   ├── database.py         # MongoDB operations
│   ├── broker_sim.py       # Simulated broker (paper trading)
│   ├── broker_factory.py   # Broker instantiation
│   ├── backtester.py      # Backtesting engine
│   ├── strategies.py       # Legacy strategy logic
│   ├── indicators.py       # Technical indicators
│   ├── indicator_classes.py # Indicator classes
│   ├── historical_data.py # Data fetching (Yahoo, Alpha Vantage)
│   ├── realistic_prices.py # Real-time price feeder
│   ├── news_client.py     # News/scraping for sentiment
│   ├── settings.py        # Configuration
│   ├── strategies.json    # JSON strategy definitions
│   └── strategy/          # Strategy modules
│
├── frontend/              # React dashboard
├── strategies.json       # Active trading strategies
└── scripts/              # Automation scripts
```

---

## How Trading Works

### 1. Data Flow

```
Data Sources (Yahoo/Alpha/Binance)
         ↓
  broker_sim.py (get_quote, get_candles)
         ↓
  database.py (cache quotes/candles)
         ↓
  main.py (signal generation)
         ↓
  Trading decision (buy/sell/hold)
         ↓
  broker_sim.py (open_position)
         ↓
  database.py (save trades)
```

### 2. Signal Generation

```
1. Fetch current quote → get_quote()
2. Fetch candles (60m, 100 bars) → get_candles()
3. Calculate indicators → TechnicalIndicators.calculate_all()
4. Generate signal → analyze_with_new_strategy() OR legacy calculate_signal_score()
5. Check risk rules (max positions, drawdown)
6. Open position if signal passes all checks
```

### 3. Position Management

- **Dynamic Positions:** Close winning trades early if momentum fades
- **Take Profit / Stop Loss:** Calculated from ATR
- **Risk Management:** Max 2% risk per trade, max 3 open positions

---

## Database Collections

| Collection | Purpose |
|------------|---------|
| `account` | Balance, equity, stats |
| `trades` | Open and closed positions |
| `candles` | OHLCV data for live trading |
| `backtest_cache` | Backtest-specific candle data |
| `quote_cache` | Latest prices |
| `signal_cache` | Cached signals |
| `settings` | Bot configuration |

---

## Key Files Explained

### main.py (4500+ lines)
- FastAPI endpoints (`/api/*`)
- Signal generation (`analyze_with_new_strategy()`)
- Auto-trade loop
- Price cache management
- Account management

### broker_sim.py
- `get_quote()` — Fetches current price (tries Alpha Vantage → Yahoo → DB cache)
- `get_candles()` — Fetches OHLCV data
- `open_position()` / `close_position()` — Trade execution

### backtester.py
- Runs historical simulations
- Uses same signal logic as live trading
- Should use `backtest_cache` collection (separate from live)

### database.py
- All MongoDB operations
- `store_candles()` / `load_candles()`
- `save_quote()` / `load_quote()`
- `save_backtest_candles()` / `load_backtest_candles()` — **Separated for backtests**

---

## Current Issues & Bugs

### 1. ❌ DATA MIXING (CRITICAL - FIXED TODAY)
**Problem:** Backtester was writing sample/fake data to `candles` collection (used by live trading), causing entry prices like 2000 for XAU instead of real ~5200.

**Root Cause:** 
- Backtester used `generate_sample_data()` with base_price=2000 when no real data
- Wrote to same `candles` collection as live trading
- Live trading read old/stale prices

**Fix Applied:**
- Added `backtest_cache` collection for backtest data
- Backtester now checks `backtest_cache` → `candles` → external APIs
- Removed sample data fallback (backtest fails if no real data)

### 2. ❌ MULTIPLE BOTS ON DIFFERENT PORTS
**Problem:** Sometimes 2+ bot processes running (port 8000 + 8001), each with different state.

**Root Cause:** 
- Cron jobs restarting bot
- VSCode auto-reload
- launchctl service

**Current Fix:** Only port 8001 should be used. All other processes should be killed.

### 3. ❌ AUTO_TRADE DEFAULT
**Problem:** `AUTO_TRADE_ENABLED = True` in code, so bot starts trading immediately on launch.

**Current Fix:** Changed default to `False`. Must enable manually via API.

### 4. ❌ STALE DATA IN CACHE
**Problem:** Old candles (from 2025) in database causing wrong prices.

**Fix Applied:** Deleted candles with timestamp < 2026-03-01.

### 5. ⚠️ BACKTEST vs LIVE SEPARATION (INCOMPLETE)
**Status:** 
- ✅ backtest_cache added
- ✅ Sample data removed
- ⚠️ Need to verify backtester reads from backtest_cache first

### 6. ✅ STRATEGY-DRIVEN FILTER ARCHITECTURE (FIXED 2026-03-04)
**Problem:** Volatility and VIX filters were hardcoded in main.py, violating separation of concerns.

**Changes Made:**

1. **New filter classes added to `backend/strategy/filters.py`:**
   - `VolatilityFilter` - Checks ATR% against strategy config
   - `VixFilter` - Checks VIX level against strategy config

2. **Filter configuration added to all strategies in `strategies.json`:**
   ```json
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
   ```

3. **Updated signal flow:**
   - `analyze_with_new_strategy()` now passes `atr_percent` and `vix_value` to strategy filters
   - Filters checked INSIDE strategy, not in main.py
   - Strategy is now the single source of truth

4. **Benefits:**
   - Each strategy can have different filter thresholds
   - No code changes needed to adjust filters
   - Better testability and maintainability
**Problem:** In `rsi_momentum` direction mode, momentum logic was inverted:
- **Before (WRONG):** momentum < 0 → BUY, momentum > 0 → SELL
- **After (FIXED):** momentum > 0 → BUY (price rising), momentum < 0 → SELL (price falling)

**Location:** `backend/strategy/strategy.py` - `_get_signal_rsi_momentum()`

**Impact:** BTC, XAU, XAG strategies using `direction_mode: "rsi_momentum"` (btc_v3_exp, xau_v3_exp, xag_v3_exp) were generating opposite signals.

### 7. ⚠️ US100 STRATEGY FALLBACK ISSUE
**Problem:** When strategy for US100 (`htf_divergence_test`) not found, falls back to `xau_v3_exp` instead of proper default.

**Location:** `main.py` line ~1015 - fallback logic

### 8. ⚠️ REMOVED DEFAULT VALUES
**Problem:** Removed default values for `timeframe` and `trade_direction` in Strategy class, could cause None errors.

**Location:** `backend/strategy/strategy.py` lines 143-144

### 9. ⚠️ SIGNAL GENERATION FLOW COMPLEXITY
**Problem:** Signal generation has multiple paths that could behave differently:
- New JSON strategy: `analyze_with_new_strategy()` 
- Legacy strategy: `calculate_signal_score()` in backtester.py
- Both use different normalization/weighting

**Recommendation:** Ensure both paths produce consistent results

---

## Signal Generation Flow (Detailed)

```
_analyze_single_symbol(symbol, info, news_client)
    │
    ├─→ 1. Get quote from cache
    │
    ├─→ 2. Get strategy from DB (get_symbol_strategy)
    │       └─→ Falls back to 'xau_v3_exp' if not found (BUG!)
    │
    ├─→ 3. Get timeframe from strategy config
    │       └─→ Convert "5m" → "5" for db_resolution
    │
    ├─→ 4. Fetch candles (100 bars)
    │       └─→ Return NEUTRAL if < 20 candles
    │
    ├─→ 5. Calculate indicators (TechnicalIndicators.calculate_all)
    │       └─→ Return NEUTRAL if indicators fail
    │
    ├─→ 6. Filter indicators by per-symbol settings
    │
    ├─→ 7. Fetch HTF (daily) candles for trend bias
    │
    ├─→ 8. VIX filter
    │       └─→ Return NEUTRAL if ATR% > 3%
    │
    ├─→ 9. Try JSON strategy (analyze_with_new_strategy)
    │       └─→ NEW PATH: Uses strategy/strategy.py ScoreEngine
    │
    ├─→ 10. Fallback to legacy strategy
    │       └─→ OLD PATH: Uses strategies.py AdaptiveRegimeStrategy
    │
    └─→ Return Signal with direction, score, confidence
```

### When Signal Returns None (No Trade)

| Check | Location | Reason |
|-------|----------|--------|
| Insufficient candles | `_analyze_single_symbol` | < 20 candles |
| Indicator calculation failed | `_analyze_single_symbol` | TechnicalIndicators returned None |
| High volatility | `_analyze_single_symbol` | ATR% > 3% |
| No signal from strategy | `analyze_with_new_strategy` | Score below min_score |
| Filters failed | `Strategy.on_bar()` | Volume low, position exists, etc. |
| Wrong direction | `Strategy.on_bar()` | long_only mode but sell signal |

---

## What's Working

### ✅ Live Trading
- Signal generation on 60m timeframe
- Position opening/closing
- P&L tracking
- Dynamic positions (close early if momentum fades)

### ✅ Backtesting
- Uses same signal logic as live (unified strategy)
- Stores results in MongoDB + CSV

### ✅ Data Sources
- Yahoo Finance (primary)
- Alpha Vantage (fallback)
- Binance (for BTC)

### ✅ Frontend
- Charts with indicators
- Trade history
- Account balance
- Settings panel

---

## What's Missing / Needs Work

### 1. Real-time 1m/5m Data
- Currently only 60m candles stored
- Need to fetch and store lower timeframes for scalping
- Plan: Fetch 1m/5m live → aggregate to higher timeframes → store in DB

### 2. Research Mode
- Web scraping for market sentiment
- Strategy ideas from news
- Not fully integrated with trading

### 3. Strategy Editor
- UI to create/edit JSON strategies
- Currently manual editing of strategies.json

### 4. Proper Backtest/Live Separation
- Backtest should ONLY read from backtest_cache
- Live should ONLY read from candles
- Currently partly fixed but needs verification

### 5. Test Coverage
- 194 tests passing
- Some skipped (trailing_stop, broker TP/SL)

---

## Configuration

### Environment Variables
```
MONGO_URI=mongodb+srv://...
BROKER_TYPE=sim  # or ibkr
ALPHA_VANTAGE_API_KEY=...
```

### Key Settings (in DB settings collection)
- `AUTO_TRADE_ENABLED` — Must be FALSE by default
- `DYNAMIC_POSITIONS_ENABLED` — Close winning trades early
- `MAX_OPEN_POSITIONS` — Max 3
- `MAX_RISK_PER_TRADE_PCT` — 2%
- `STRATEGY_XAU` — Which strategy to use for XAU
- `STRATEGY_BTC` — Which strategy to use for BTC

---

## Running the Bot

### Start Backend
```bash
cd backend
source venv/bin/activate
python -c "import uvicorn; from main import app; uvicorn.run(app, host='0.0.0.0', port=8001)"
```

### Start Frontend
```bash
cd frontend
npm run dev
```

### Enable Auto-Trading
```bash
curl -X POST "http://localhost:8001/api/auto-trade?enabled=true"
```

### Reset Account
```bash
curl -X POST "http://localhost:8001/api/account/reset"
```

---

## Goals & Roadmap

### Phase 1: Fix Critical Issues ✅
- [x] Separate backtest cache from live data
- [x] Fix stale data
- [x] Fix auto-trade default
- [x] Single port (8001)

### Phase 2: Data Infrastructure
- [ ] Store 1m/5m candles for scalping
- [ ] Proper candle aggregation
- [ ] Data quality monitoring

### Phase 3: Strategy Development
- [ ] Strategy editor UI
- [ ] Parameter optimization
- [ ] Research mode integration

### Phase 4: Advanced Features
- [ ] Multi-timeframe signals (H1 + H4 + D1)
- [ ] News sentiment integration
- [ ] Portfolio optimization

---

## Known Technical Debt

1. **main.py is 4500+ lines** — Should be split into modules
2. **Duplicate logic** — Some functions exist in both main.py and backtester.py
3. **No proper logging** — Using print() and log_event()
4. **Test coverage gaps** — Some broker functionality not tested

---

## Questions for Refactor

1. Should we keep unified signal logic (backtest = live) or separate?
2. What's the data retention policy for candles?
3. How often should we fetch new data?
4. What's the max history we need to keep?

---

*Last updated: 2026-03-03*
