# BUGS.md - CFD Trading Bot

## 2026-03-13

### Błąd #4: XAG position sizing multiplier
- **Status:** ✅ NAPRAWIONO
- **Data:** 2026-03-13 00:30
- **Opis:** W funkcji calculate_position_size (signal_generator.py) był błąd: `multiplier = 100 if symbol == "XAG" else 100` - zawsze 100 zamiast 5 dla XAG
- **Rozwiązanie:** Zmieniono na `multiplier = 5 if symbol == "XAG" else 100`
- **Plik:** services/signal_generator.py linia 206

### Błąd #5: Leverage niezgodny z IBKR
- **Status:** ✅ NAPRAWIONO
- **Data:** 2026-03-13 00:35
- **Opis:** Leverage: XAG=20 (powinno 10), BTC=5 (powinno 2)
- **Rozwiązanie:** Zmieniono w broker_sim.py i backtester.py: XAG=10, BTC=2
- **Plik:** broker_sim.py, backtester.py

### Błąd #6: API /candles błędne argumenty
- **Status:** ✅ NAPRAWIONO
- **Data:** 2026-03-13 00:50
- **Opis:** Błąd `'>' not supported between instances of 'NoneType' and 'int'` - błędna kolejność argumentów
- **Rozwiązanie:** Zmieniono `async_load_candle_history(symbol, resolution, count, from_time, to_time)` na `async_load_candle_history(symbol, resolution, start=from_time, end=to_time, limit=count)`
- **Plik:** api/routes/market.py

### Błąd #7: Dynamic position sizing nie używał mnożnika dla XAG
- **Status:** ✅ NAPRAWIONO
- **Data:** 2026-03-13 00:55
- **Opis:** Funkcja calculate_dynamic_position_size nie używała mnożnika 5 dla XAG
- **Rozwiązanie:** Dodano commodity_multiplier = 5 dla XAG w trading_engine.py
- **Plik:** services/trading_engine.py

### Błąd #8: Leverage w dynamic position sizing
- **Status:** ✅ NAPRAWIONO
- **Data:** 2026-03-13 00:55
- **Opis:** Leverage nie był ograniczony przez max instrument leverage
- **Rozwiązanie:** Dodano instrument_leverage lookup dla XAU=20, XAG=10, US100=20, BTC=2
- **Plik:** services/trading_engine.py

## 2026-03-12

### Błąd #1: ModuleNotFoundError: strategy.strategy_manager
- **Status:** ✅ NAPRAWIONO
- **Data:** 2026-03-12 23:00
- **Opis:** Kod próbował zaimportować `from strategy.strategy_manager import get_strategy_manager` ale ten moduł nie istniał
- **Rozwiązanie:** Zmieniono import na `from services.strategy_manager import get_strategy_manager`
- **Plik:** `services/trading_engine.py` linie 191, 222

### Błąd #2: ImportError: signal_history_cache
- **Status:** ✅ NAPRAWIONO  
- **Data:** 2026-03-12 23:02
- **Opis:** Kod próbował zaimportować `signal_history_cache` z `main.py` ale zmienna nie istniała
- **Rozwiązanie:** Zmieniono na `from services.state import get_signal_history_cache`
- **Plik:** `services/trading_engine.py` linia 265

### Błąd #3: Dynamic Positions nie zamykało pozycji z słabym sygnałem
- **Status:** ✅ NAPRAWIONO
- **Data:** 2026-03-13 00:15
- **Opis:** 
  1. Pozycje US100 miały sygnał -0.097 (negatywny) ale nie były zamykane
  2. Problem: neutralne sygnały były filtrowane z current_signals
  3. Problem: open_positions był pusty (nie synchronizowany z brokerem)
- **Rozwiązanie:**
  1. Zmieniono `current_signals` żeby zawierał też neutralne/negatywne sygnały
  2. Dodano `open_positions = broker.get_open_positions()` na początku pętli
  3. Dodano logikę zamykania pozycji gdy sygnał spada poniżej 0
- **Plik:** `services/trading_engine.py` linia 111, 113, broker_sim.py linia 237+

### Wynik testu HEARTBEAT:
- ✅ Dashboard - działa
- ✅ Wykresy - działają
- ✅ Trading - strategie działają
- ✅ Pozycje otwarte - wyświetlanie OK
- ✅ Historia transakcji - OK
- ✅ Logi - OK (wcześniej były błędy, teraz czyste)
- ✅ Auto-trade - działa!
- ✅ Dynamic Positions - DZIAŁA! (US100 zamknięty z +$20.90)
