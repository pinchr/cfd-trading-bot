# TEST SCENARIOS - Advanced Features

## Previous Results (v0.4)

| Test | Status | 
|------|--------|
| A1: TP/SL różne dla różnych strategii | ✅ PASS |
| A2: Dynamic TP (HTF RSI) | ⚠️ PARTIAL |
| A3: ATR filtr | ✅ PASS |
| B1: Dynamic Positions On/Off | ✅ PASS |
| B2: Logika zamykania | ❌ FAIL - BUG: original_signal_score=0 |
| C1: Różne wielkości | ✅ PASS |

---

## 🚀 NEW: Test Scenarios v1.0

### Phase 1: Fix Critical Bugs

#### Test B2-FIX: original_signal_score saving ✅

**Cel:** Naprawić bug gdzie original_signal_score = 0

**Procedura:**
1. Otwórz pozycję przez API z score=0.93
2. Sprawdź w odpowiedzi czy original_signal_score jest zapisany
3. Sprawdź w bazie danych (MongoDB trades collection)

**Oczekiwane:** original_signal_score powinno być 0.93, nie 0.0

---

### Phase 2: Advanced TP/SL

#### Test A5: Adaptive TP/SL Algorithm

**Cel:** Sprawdzić czy nowy algorytm TP/SL łączy wiele czynników

**Procedura:**
1. Konfiguruj strategię z `exits.method: "adaptive"`
2. Otwórz pozycję
3. Sprawdź czy TP/SL uwzględnia:
   - Base percent (30% wagi)
   - ATR multiplier (30% wagi)
   - Support/Resistance (20% wagi)
   - HTF Indicator (20% wagi)

**Weryfikacja:** Porównaj TP/SL z ręcznym obliczeniem według wzoru

---

#### Test A6: Support/Resistance Based SL

**Cel:** SL powinno być umieszczone przy wsparciu/oporze

**Procedura:**
1. Znajdź poziom wsparcia dla LONG (cena poniżej entry)
2. Znajdź poziom oporu dla SHORT (cena powyżej entry)
3. Sprawdź czy SL jest blisko tego poziomu (w tolerancji 0.5%)

**Oczekiwane:** SL < nearest_support (dla LONG) lub SL > nearest_resistance (dla SHORT)

---

#### Test A7: Partial Exits (Trailing TP)

**Cel:** Sprawdzić czy system zamyka część pozycji na różnych poziomach TP

**Procedura:**
1. Ustaw partial_exits w strategii:
   ```json
   "partial_exits": [
     {"tp_percent": 50, "close_percent": 30},
     {"tp_percent": 100, "close_percent": 70}
   ]
   ```
2. Otwórz pozycję i poczekaj na ruch ceny
3. Sprawdź czy pozycja jest częściowo zamknięta

---

### Phase 3: Dynamic Position Sizing

#### Test C3: Size Decreases with More Positions

**Cel:** Sprawdzić czy wielkość pozycji maleje gdy mamy więcej otwartych

**Procedura:**
1. Otwórz pozycję na XAU (size=X)
2. Otwórz pozycję na BTC (size=Y powinno być mniej niż X)
3. Otwórz pozycję na US100 (size=Z powinno być mniej niż Y)

**Oczekiwane:** X > Y > Z (malejąco zgodnie z modifiers)

---

#### Test C4: Size Decreases with Low Equity

**Cel:** Sprawdzić czy system zmniejsza pozycje przy niskim equity

**Procedura:**
1. Ustaw niskie equity (np. przez dużą stratę)
2. Otwórz nową pozycję
3. Porównaj size z poprzednią pozycją przy wyższym equity

**Oczekiwane:** Size powinien być mniejszy przy niższym equity

---

#### Test C5: Volatility-Based Sizing

**Cel:** Pozycje powinny być mniejsze przy wysokiej zmienności

**Procedura:**
1. Znajdź symbol z wysokim ATR (np. > 2%)
2. Znajdź symbol z niskim ATR (np. < 1%)
3. Otwórz pozycje na obu
4. Porównaj wielkości (wolatile = mniejsza pozycja)

**Oczekiwane:** High_volatility_size < Low_volatility_size

---

### Phase 4: Dynamic Positions (Early Exit)

#### Test B4: Signal Decay Exit

**Cel:** Pozycja zamyka się gdy sygnał spadnie o 25%+

**Procedura:**
1. Otwórz pozycję ze score=0.90
2. Poczekaj aż score spadnie do < 0.68
3. Sprawdź czy pozycja została zamknięta

**Oczekiwane:** Pozycja zamknięta z powodem "signal_decayed"

---

#### Test B5: Better Opportunity Exit

**Cel:** Pozycja zamyka się gdy inny symbol ma dużo lepszy sygnał

**Procedura:**
1. Otwórz pozycję na XAU (score=0.50)
2. Poczekaj aż BTC ma score=0.90 (1.5x lepszy)
3. Sprawdź czy XAU został zamknięty

**Oczekiwane:** XAU zamknięty, BTC otwarty

---

#### Test B6: Max Positions Limit

**Cel:** System zamyka najsłabszą pozycję gdy osiągnięto limit

**Procedura:**
1. Ustaw MAX_OPEN_POSITIONS=2
2. Otwórz pozycje na XAU i BTC
3. Otwórz pozycję na US100 (trzecia)
4. Sprawdź czy najsłabsza pozycja została zamknięta

---

### Phase 5: A/B Backtesting

#### Test D1: Compare Exit Strategies

**Cel:** Porównać fixed vs adaptive exit strategy

**Procedura:**
1. Uruchom backtest z fixed_percent TP/SL
2. Uruchom backtest z adaptive TP/SL
3. Porównaj metryki:
   - Total Return
   - Sharpe Ratio
   - Max Drawdown
   - Win Rate

**Oczekiwane:** Adaptive powinno mieć lepszy Sharpe Ratio lub niższy Max Drawdown

---

#### Test D2: Compare Position Sizing

**Cel:** Porównać fixed vs adaptive position sizing

**Procedura:**
1. Uruchom backtest z fixed risk 2%
2. Uruchom backtest z adaptive risk
3. Porównaj metryki

---

#### Test D3: Statistical Significance

**Cel:** Sprawdzić czy różnice są statystycznie istotne

**Procedura:**
1. Uruchom 100 backtestów dla każdej strategii
2. Oblicz p-value dla różnic w returns
3. Oczekiwane: p-value < 0.05 dla istotnych różnic

---

## Test Execution Plan

### Week 1: Bug Fixes
- [x] Test B2-FIX: original_signal_score
- [ ] Test B4: Signal Decay Exit

### Week 2: Advanced Features
- [ ] Test A5: Adaptive TP/SL
- [ ] Test A6: S/R Based SL
- [ ] Test C3-C5: Dynamic Sizing

### Week 3: Integration
- [ ] Test B5: Better Opportunity
- [ ] Test B6: Max Positions

### Week 4: A/B Testing
- [ ] Test D1-D3: Backtesting Framework

---

## Running Tests

```bash
# Run specific test
python -m pytest tests/test_exit_strategy.py::TestA5 -v

# Run all tests
python -m pytest tests/ -v

# Run A/B comparison
python -m pytest tests/backtest/ -v --ab-compare
```

---

## Notes

- Use subagents for long-running tests
- Save test results to `TEST_RESULTS.md`
- Update this file after each test run
