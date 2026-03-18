# Global Variables w main.py.backup

## Cel dokumentu
Analiza wszystkich zmiennych globalnych w oryginalnym main.py.backup - gdzie są inicjowane i używane. To pomoże odbudować zależności w nowym systemie.

---

## Zmienne Globalne

### 1. broker
- **Typ:** `SimulatedBroker` (z broker_factory)
- **Inicjowany:** `main.py.backup:48` (import), `main.py.backup:209` (create_broker)
- **Używany przez:** lines 79, 209, 221-243, 1105, 1136, 1148, 1230, 1566-1569, 2146, 2296, ...
- **Funkcje:** `broker.get_account()`, `broker.get_open_positions()`, `broker.get_closed_positions()`, `broker.open_position()`, `broker.close_position()`

### 2. data_provider
- **Typ:** Data provider (z broker_factory)
- **Inicjowany:** `main.py.backup:48` (import), `main.py.backup:205` (create_data_provider)
- **Używany przez:** lines 205, 324, 796, 864, 1144, 1200, 1210, 2076, 2109, 2197, ...
- **Funkcje:** pobieranie danych rynkowych, cen, świec

### 3. account
- **Typ:** `Dict[str, Any]`
- **Inicjowany:** `main.py.backup:27` (import z database), `main.py.backup:230` (pobieranie z broker.get_account())
- **Pola:**
  - `balance_usd` - INITIAL_BALANCE_USD lub z DB
  - `equity_usd` - balance + unrealized PnL
  - `available_usd` - equity - margin
  - `used_margin` - margin używany
  - `peak_equity_usd`, `peak_balance_usd`
  - `total_pnl_usd`
  - `win_count`, `loss_count`, `win_rate`
  - `closed_trades`, `open_trades`
  - `last_scan`
- **Używany przez:** lines 53, 60, 116, 138-245, 611-670, ...

### 4. INSTRUMENTS
- **Typ:** `Dict[str, Dict]`
- **Inicjowany:** `main.py.backup:312` (import z app.config)
- **Struktura:**
  ```python
  {
    "XAU": {"name": "Gold", "leverage": 20, "lot_size": 0.003, "pip_size": 0.01, ...},
    "XAG": {"name": "Silver", "leverage": 20, ...},
    "US100": {"name": "Nasdaq-100", ...},
    "BTC": {"name": "Bitcoin", "leverage": 5, ...}
  }
  ```
- **Używany przez:** lines 324, 686, 1037, 1161, 2179-2180, 2951

### 5. INITIAL_BALANCE_USD
- **Typ:** `float`
- **Inicjowany:** `main.py.backup:95` - `db.get_setting("INITIAL_BALANCE_USD", 3000.0)`
- **Używany przez:** lines 235, 620, 630, 643, 1028, 1031, 1470, 2481

### 6. open_positions
- **Typ:** `List[Dict]`
- **Inicjowany:** `main.py.backup:222` - `broker.get_open_positions()`
- **Struktura:**
  ```python
  {
    "symbol": "XAU",
    "direction": "buy",
    "size": 0.01,
    "entry_price": 2950.0,
    "current_price": 2960.0,
    "pnl_usd": 10.0,
    "pnl_percent": 0.34,
    ...
  }
  ```
- **Używany przez:** lines 58, 117, 226, 650, 697, 1141, 1177, 1195, 1258, 2255, 2297-2309, ...

### 7. closed_positions
- **Typ:** `List[Dict]`
- **Inicjowany:** `main.py.backup:223` - `broker.get_closed_positions()`
- **Używany przez:** lines 51, 56, 117, 228, 1258, 2403, 2406

### 8. _live_price_cache / _price_cache
- **Typ:** `Dict[str, Dict]`
- **Inicjowany:** `main.py.backup:143` (task), `main.py.backup:321` (update function)
- **Struktura:**
  ```python
  {
    "XAU": {"price": 2950.0, "bid": 2949.5, "ask": 2950.5, "timestamp": ...},
    "XAG": {...}
  }
  ```
- **Używany przez:** lines 321, 324, 329, 750, 1060-1070

### 9. signals_cache
- **Typ:** `Dict[str, Signal]`
- **Inicjowany:** `main.py.backup:1124` (w generate_signals)
- **Używany przez:** lines 1123, 1421, 2089

### 10. _api_semaphore
- **Typ:** `asyncio.Semaphore`
- **Inicjowany:** `main.py.backup:729` - `asyncio.Semaphore(4)`
- **Używany przez:** ograniczanie równoczesnych wywołań API

### 11. signal_history_cache
- **Typ:** `Dict[str, Any]`
- **Inicjowany:** `main.py.backup:193` (import z services.state)
- **Używany przez:** lines 277, 284, 293, 1253-1254

### 12. AUTO_TRADE_ENABLED
- **Typ:** `bool`
- **Inicjowany:** `main.py.backup:1077` - `False`
- **Używany przez:** lines 1089, 1100, 1293-1567

### 13. AUTO_TRADE_INTERVAL_SEC
- **Typ:** `int`
- **Inicjowany:** `main.py.backup:1076` - `300` (5 min)
- **Używany przez:** lines 1101, 1268-1317

### 14. ALL_INDICATORS
- **Typ:** `List[str]`
- **Inicjowany:** `main.py.backup:1588`
- **Wartość:** `["RSI", "MACD", "BB", "SMA", "ADX", "STOCH", "MOMENTUM", "WILLIAMS_R", "DIVERGENCE"]`
- **Używany przez:** lines 1602, 3783-3911

---

## Kluczowe Funkcje

| Funkcja | Linia | Zależności |
|---------|-------|------------|
| `lifespan` | 106 | Inicjalizacja brokera, data_provider, account, MongoDB |
| `generate_signals` | 1018 | broker, data_provider, INSTRUMENTS, signals_cache |
| `auto_trade_loop` | 1081 | AUTO_TRADE_ENABLED, broker, generate_signals |
| `price_cache_loop` | 1063 | _live_price_cache, data_provider |
| `_analyze_single_symbol` | 737 | broker, data_provider, INSTRUMENTS, _api_semaphore |
| `get_signals` | 1415 | signals_cache |
| `open_trade` | 2047 | broker, account |
| `close_trade` | 2295 | broker, account |
| `get_open_trades` | 2367 | broker, open_positions |
| `sync_account_from_closed_trades` | 608 | broker, account, database |

---

## Zależności między modułami

```
main.py.backup
├── broker_factory.py
│   ├── broker_sim.py (SimulatedBroker)
│   │   └── INSTRUMENTS = {...}
│   └── twelvedata.py / alpha_vantage.py (data_provider)
├── database.py
│   └── account, trades (MongoDB)
├── services.state (nowe)
│   ├── account
│   ├── broker
│   ├── INSTRUMENTS
│   └── _live_price_cache
└── app.config
    └── INSTRUMENTS
```

---

## Problem do naprawienia

Obecnie zmienne są zdefiniowane w wielu miejscach:
1. `services/state.py` - account, broker, INSTRUMENTS
2. `broker_sim.py` - INSTRUMENTS, broker.account
3. `main.py` - account, open_positions
4. `app/config.py` - INSTRUMENTS

**Rozwiązanie:** JEDNO źródło prawdy w `services/state.py`:
- Wszystkie zmienne globalne inicjowane TYLKO w services/state.py
- Wszystkie moduły importują z services/state.py
- Broker i data_provider tworzone w services/state.py

---

## TODO: Lista zmian do wykonania

1. [ ] Upewnić się że `services/state.py` inicjuje wszystkie zmienne
2. [ ] Usunąć duplikaty INSTRUMENTS z broker_sim.py
3. [ ] Upewnić się że account jest synchronizowany z MongoDB
4. [ ] Przemapować wszystkie importy w innych plikach

---

## NOWE PROBLEMY ZNALEZIONE I NAPRAWIONE [2026-03-07 11:05]

### 1. api/routes/trades.py - sync_account import
- **Problem:** Funkcja `get_sync_account()` importowała `sync_account_from_closed_trades` z main.py, która nie istnieje
- **Rozwiązanie:** Zmieniono na import z `database.async_sync_account_from_closed_trades`
- **Status:** ✅ NAPRAWIONE

### 2. Frontend proxy - brak /api
- **Problem:** Frontend wywoływał `/api/chart/{symbol}` bezpośrednio, ale proxy obsługiwało tylko `/cfd/api`
- **Rozwiązanie:** Dodano `/api` do proxy w vite.config.ts
- **Status:** ✅ NAPRAWIONE

### 3. services/state.py - get_account()
- **Problem:** Funkcja zwracała pusty `account` zamiast `broker.account`
- **Rozwiązanie:** Zmieniono na `return broker.account if hasattr(broker, 'account') else account`
- **Status:** ✅ NAPRAWIONE

---

## MAPOWANIE: stara funkcja -> nowa lokalizacja

| Funkcja (main.py.backup) | Nowa lokalizacja |
|--------------------------|-------------------|
| `generate_signals` | services/trading_engine.py |
| `_analyze_single_symbol` | services/trading_engine.py |
| `auto_trade_loop` | services/trading_engine.py |
| `price_cache_loop` | services/market_data.py |
| `open_trade` | api/routes/trades.py |
| `close_trade` | api/routes/trades.py |
| `sync_account_from_closed_trades` | database.py (async_sync_account_from_closed_trades) |
| `get_chart_data` | api/routes/market.py |
| `get_instruments` | services/state.py |

---

## ZMIENNE W services.state vs broker_sim

| Zmienna | services/state.py | broker_sim.py |
|---------|-------------------|---------------|
| `account` | `{}` (pusty init) | `broker.account` (właściwe dane) |
| `INSTRUMENTS` | import z broker_sim | `INSTRUMENTS = {...}` |
| `broker` | `create_broker(data_provider)` | klasa SimulatedBroker |
| `data_provider` | `create_data_provider()` | data provider |

### WNIOSEK
**Rozwiązanie:** `get_account()` w services/state.py musi zwracać `broker.account`, nie lokalny `account`.

---

## KOLEJNE NAPRAWY [2026-03-07 11:45-11:52]

### 1. get_cached_quote - nie był async
- **Problem:** Funkcja była wywoływana z `await`, ale nie była async
- **Rozwiązanie:** Usunięto await przy wywołaniu
- **Status:** ✅ NAPRAWIONE

### 2. get_cached_candles - brakowało data_provider
- **Problem:** Funkcja wymaga data_provider jako argument, ale nie był przekazywany
- **Rozwiązanie:** Dodano data_provider do wszystkich wywołań
- **Status:** ✅ NAPRAWIONE

### 3. analyze_with_new_strategy - brak importu
- **Problem:** Funkcja nie była importowana w trading_engine.py
- **Rozwiązanie:** Dodano import z services.strategy_manager
- **Status:** ✅ NAPRAWIONE

### 4. Frontend proxy - brakowało /api
- **Problem:** Frontend wywoływał /api/chart bezpośrednio, ale proxy miało tylko /cfd/api
- **Rozwiązanie:** Dodano /api do proxy w vite.config.ts
- **Status:** ✅ NAPRAWIONE

### 5. Frontend open_trade - złe parametry
- **Problem:** Wysyłało dane jako query params zamiast JSON body
- **Rozwiązanie:** Zmieniono na wysyłanie JSON body z Content-Type: application/json
- **Status:** ✅ NAPRAWIONE
