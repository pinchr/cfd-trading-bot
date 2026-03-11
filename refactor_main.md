# Refactoring Plan: CFD Trading Bot (main.py)
NEVER REVERT TO OLD GIT WORKING VERSION,IT'S NOT REAL FIX!!!

## Executive Summary

**Current State**: `main.py` is a monolithic file with 4,476 lines combining API routes, business logic, data fetching, trading execution, and background tasks.

**Goal**: Decompose into a modular Service-Oriented Architecture (SOA) to improve maintainability, testability, and code clarity.

**Key Principle**: The strategy is now the source of truth for trading decisions. This refactoring aligns the code structure with that principle.

---

## 1. Component Analysis

Based on analysis of `main.py`, the following distinct logical components have been identified:

| Component | Current Location | Lines | Responsibility |
|-----------|-----------------|-------|----------------|
| **FastAPI App** | `main.py` | ~100 | App initialization, middleware, lifespan |
| **API Endpoints** | `main.py` | ~1500 | All `@app.get`, `@app.post` decorators |
| **Signal Generation** | `main.py` | ~500 | `_analyze_single_symbol()`, `calculate_signal_score()` |
| **Auto-Trade Loop** | `main.py` | ~200 | `auto_trade_loop()` |
| **Price Cache** | `main.py` | ~100 | `_live_price_cache`, `_update_live_price_cache()` |
| **Market Hours** | `main.py` | ~50 | `is_market_open()`, `get_market_hours()` |
| **Backtesting** | `main.py` | ~600 | `run_backtest_from_json()` |
| **Timing Utilities** | `main.py` | ~80 | `async_timed()`, `sync_timed()` decorators |
| **Event Logging** | `main.py` | ~30 | `log_event()` |
| **Data Structures** | `main.py` | ~100 | `INSTRUMENTS`, `account`, `open_positions`, etc. |

---

## 2. Proposed Directory Structure

```
backend/
├── main.py                          # Entry point (< 150 lines)
├── app/
│   ├── __init__.py
│   ├── config.py                    # Settings, constants, env vars
│   └── logging.py                   # Logging configuration
│├── api/
│   ├── __init__.py
│   ├── router.py                    # FastAPI router aggregation
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── account.py               # /api/account/* endpoints
│   │   ├── trades.py                # /api/trades/* endpoints
│   │   ├── strategies.py            # /api/strategies/* endpoints
│   │   ├── market.py                # /api/quote/*, /api/chart/* endpoints
│   │   ├── news.py                  # /api/news/* endpoints
│   │   └── control.py               # /api/auto-trade, /api/circuit-breaker
│   └── deps.py                     # Shared dependencies (DB, broker)
│├── services/
│   ├── __init__.py
│   ├── trading_engine.py            # Auto-trade loop, signal orchestration
│   ├── signal_generator.py         # Signal generation (moved from main.py)
│   ├── market_data.py              # Price cache, live price updates
│   ├── market_hours.py             # Market open/close logic
│   ├── backtest_engine.py          # Backtesting logic
│   └── circuit_breaker.py          # Trading circuit breaker
│├── models/
│   ├── __init__.py
│   └── pydantic.py                  # Request/Response schemas
└── utils/
    ├── __init__.py
    ├── decorators.py                # Timing decorators
    └── validators.py                # Input validation helpers
```

---

## 3. Detailed Extraction Plan

### Phase 1: Foundation (Low Risk)

#### 1.1 Extract Configuration

**Target**: `backend/app/config.py`

**Extract from main.py**:
- `INSTRUMENTS` dict
- `INITIAL_BALANCE_USD`
- All settings constants from `settings.py` imports
- Signal handlers setup

**Benefits**: Centralized configuration, easier to modify instrument list.

#### 1.2 Extract Logging

**Target**: `backend/app/logging.py`

**Extract from main.py**:
- `log_event()` function
- `event_log` global list

**Benefits**: Consistent logging across all modules.

---

### Phase 2: Core Business Logic

#### 2.1 Extract Signal Generation

**Target**: `backend/services/signal_generator.py`

**Extract from main.py**:
- `_analyze_single_symbol()` (~200 lines)
- `calculate_signal_score()` (~150 lines)
- Signal caching logic

**Keep in main.py temporarily**:
- Volatility/VIX data fetching (needs to pass to strategy)

**Benefits**: Isolated signal logic, easier to test and modify strategies.

#### 2.2 Extract Market Hours

**Target**: `backend/services/market_hours.py`

**Extract from main.py**:
- `is_market_open()`
- `get_market_hours()`

**Benefits**: Reusable across backtest and live trading.

#### 2.3 Extract Market Data Service

**Target**: `backend/services/market_data.py`

**Extract from main.py**:
- `_live_price_cache` management
- `_update_live_price_cache()` 
- `get_live_price()`
- `_get_cached_candles()`

**Benefits**: Centralized price data management.

---

### Phase 3: Trading Engine

#### 3.1 Extract Auto-Trade Loop

**Target**: `backend/services/trading_engine.py`

**Extract from main.py**:
- `auto_trade_loop()`
- `_execute_trade()`
- Trade execution logic

**Benefits**: Isolated trading execution, easier to modify trade logic.

#### 3.2 Extract Circuit Breaker

**Target**: `backend/services/circuit_breaker.py`

**Extract from main.py**:
- `check_circuit_breaker()`
- Circuit breaker state management

**Benefits**: Reusable safety mechanism.

---

### Phase 4: API Routes

#### 4.1 Restructure API Endpoints

**Target**: `backend/api/routes/`

**Extract from main.py**:
Move each endpoint group to separate files:

| Original | New Location |
|----------|--------------|
| `/api/account/*` | `api/routes/account.py` |
| `/api/trades/*` | `api/routes/trades.py` |
| `/api/strategies/*` | `api/routes/strategies.py` |
| `/api/quote/*`, `/api/chart/*` | `api/routes/market.py` |
| `/api/news/*` | `api/routes/news.py` |
|`/api/auto-trade`, `/api/circuit-breaker/*` | `api/routes/control.py` |

**Benefits**: Each route file is focused, easier to maintain.

#### 4.2 Create Router

**Target**: `backend/api/router.py`

**Purpose**: Aggregate all route modules into single router for main.py.

---

### Phase 5: Backtesting

#### 5.1 Extract Backtest Engine

**Target**: `backend/services/backtest_engine.py`

**Extract from main.py**:
- `run_backtest_from_json()`
- `run_backtest()`
- Backtest-specific logic (~600 lines)

**Benefits**: Separated from live trading logic, easier to improve backtesting.

---

## 4. Dependency Graph

```
main.py (Entry)
    │
    ├── app/config.py
    ├── app/logging.py
    │
    ├── api/router.py
    │   ├── api/routes/account.py
    │   ├── api/routes/trades.py
    │   ├── api/routes/strategies.py
    │   ├── api/routes/market.py
    │   ├── api/routes/news.py
    │   └── api/routes/control.py
    │
    └── services/
        ├── trading_engine.py
        │   ├── signal_generator.py
        │   │   └── strategy/ (existing)
        │   ├── market_data.py
        │   ├── market_hours.py
        │   └── circuit_breaker.py
        ├── backtest_engine.py
        └── market_data.py
```

**Key Dependency Rules**:
- Services should NOT import each other's execution logic (avoid circular imports)
- API routes call services, not vice versa
- `trading_engine.py` orchestrates, individual services implement

---

## 5. Migration Steps

### Step 1: Create Directory Structure
```bash
mkdir -p backend/app
mkdir -p backend/api/routes
mkdir -p backend/services
mkdir -p backend/models
mkdir -p backend/utils
```

### Step 2: Extract Config and Logging (Day 1)
1. Create `app/config.py` with INSTRUMENTS and constants
2. Create `app/logging.py` with log_event
3. Update main.py to import from new modules
4. Test: Bot should start normally

### Step 3: Extract Market Hours and Data (Day 2)
1. Create `services/market_hours.py`
2. Create `services/market_data.py`
3. Update imports in main.py
4. Test: Price fetching works

### Step 4: Extract Signal Generation (Day 3-4)
1. Create `services/signal_generator.py`
2. Move `_analyze_single_symbol()` and related functions
3. Keep volatility/VIX fetching in main.py initially
4. Test: Signals still generate correctly

### Step 5: Extract Trading Engine (Day 5)
1. Create `services/trading_engine.py`
2. Move `auto_trade_loop()`
3. Test: Auto-trading still works

### Step 6: Extract Circuit Breaker (Day 6)
1. Create `services/circuit_breaker.py`
2. Move circuit breaker logic

### Step 7: Move API Routes (Day 7-8)
1. Create `api/routes/` files
2. Create `api/router.py`
3. Update main.py to use router
4. Test: All endpoints work

### Step 8: Extract Backtesting (Day 9)
1. Create `services/backtest_engine.py`
2. Move backtest functions

### Step 9: Final Cleanup (Day 10)
1. Remove unused imports from main.py
2. Verify main.py is under 200 lines
3. Run full test suite

---

## 6. Risk Mitigation

### Risk 1: Breaking Existing Functionality
**Mitigation**: Create integration tests before starting. Test each extraction before moving to next.

### Risk 2: Circular Imports
**Mitigation**: Follow dependency hierarchy strictly. Use late imports if needed.

### Risk 3: Losing Global State
**Mitigation**: Some global state (account, positions) will need to remain accessible. Create a state manager service.

### Risk 4: Performance Impact
**Mitigation**: Keep imports lazy. Don't import all services at startup unless needed.

---

## 7. Acceptance Criteria

| Metric | Target | Verification |
|--------|--------|--------------|
| `main.py` lines | < 200 | `wc -l main.py` |
| API routes in separate files | 6+ files | `ls api/routes/` |
| Services in separate files | 6+ files | `ls services/` |
| Bot starts successfully | 100% | Manual test |
| Auto-trade works | 100% | Manual test |
| Backtest works | 100% | Manual test |
| All endpoints respond | 100% | API test |

---

## 8. Implementation Priority

1. **Immediate**: Extract config and logging (foundation)
2. **High**: Extract signal generation (core business logic)
3. **High**: Extract trading engine (critical path)
4. **Medium**: Extract API routes (code organization)
5. **Low**: Extract backtesting (can be done later)

---

*Plan created: 2026-03-04*
*Based on main.py analysis (4,476 lines)*
