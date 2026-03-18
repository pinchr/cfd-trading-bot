# TEST SCENARIOS - TP/SL, Dynamic Positions, Position Sizing

## Test A: TP/SL Calculation

### Test A1: TP/SL różne dla różnych strategii ✅ PASS

**Cel:** Sprawdzić czy TP/SL są różne dla różnych strategii

**Procedura:**
1. Pobierz sygnał dla XAU ze strategią xau_scalp_trend
2. Zmień strategię na xau_v2_momentum przez API
3. Pobierz nowy sygnał i porównaj TP/SL

**Wyniki:**

| Strategia | TP % | SL % | Dynamic TP | Entry | TP Price | SL Price |
|-----------|------|------|-------------|-------|----------|----------|
| xau_scalp_trend | 2.5% | 1.5% | NIE | 5070.6 | 5197.37 | 4994.54 |
| xau_v2_momentum | 5.0% | 2.0% | TAK (RSI HTF) | 5055.6 | 4802.82 | 5156.71 |

**Wniosek:** TP/SL są różne dla różnych strategii. Strategia xau_scalp_trend ma mniejsze TP/SL (2.5%/1.5%) a xau_v2_momentum ma większe (5%/2%) z dynamicznym TP.

---

### Test A2: TP/SL uwzględniają HTF RSI (Dynamic TP) ⚠️ PARTIAL

**Cel:** Sprawdzić czy TP zmienia się w zależności od HTF RSI

**Konfiguracja strategii xau_v2_momentum:**
```json
{
  "dynamic_tp": {
    "enabled": true,
    "htf_indicator": "RSI",
    "htf_timeframe": "30m",
    "rules": [
      {"condition": {"operator": ">", "value": 65}, "tp_percent": 3.0},
      {"condition": {"operator": "<", "value": 40}, "tp_percent": 7.0}
    ],
    "default_tp_percent": 5.0
  }
}
```

**Wynik:** Dynamic TP jest skonfigurowany, ale:
- Nie widzę w sygnale jakie są wartości HTF RSI
- Nie widzę czy TP jest faktycznie zmieniany w zależności od RSI
- Potrzeba więcej logowania w exit_engine

**Wniosek:** Funkcjonalność istnieje w kodzie (exits.py update_dynamic_tp), ale brak visibility w API/sygnale.

---

### Test A3: ATR w filtrach ✅ PASS

**Cel:** Sprawdzić czy ATR jest używany jako filtr zmienności

**Wynik:** ATR jest używany jako FILTR w strategiach:
- max_atr_percent: 3.0 (maksymalna dopuszczalna zmienność)
- Jeśli ATR % > 3%, strategia nie generuje sygnału

**Lokalizacja kodu:** `backend/strategy/filters.py` - VolatilityFilter

**Wniosek:** ATR NIE wpływa bezpośrednio na TP/SL, ale służy jako filtr - przy wysokiej zmienności nie wchodzi w pozycję.

---

### Test A4: Porównanie z "idealnym" TP/SL ⚠️ MANUAL

**Cel:** Sprawdzić czy TP/SL są blisko wsparcia/oporu

**Procedura:** Wymaga manualnej analizy wykresu:
1. Otworzyć wykres XAU
2. Zidentyfikować najbliższe wsparcie/oporu
3. Porównać z SL/TP z strategii

**Uwaga:** System nie ma automatycznego wyznaczania wsparcia/oporu - TP/SL są oparte na % od ceny wejścia, nie od poziomów technicznych.

---

## Test B: Dynamic Positions

### Test B1: Dynamic Positions On/Off ✅ PASS

**Cel:** Sprawdzyć czy przycisk On/Off działa

**Procedura:**
1. Kliknij "Dynamic Positions" → "On" w UI
2. Sprawdź czy stan się zmienia w UI

**Wynik:** Przycisk działa - UI pokazuje "On"

---

### Test B2: Logika zamykania pozycji ⚠️ CODE REVIEW

**Cel:** Sprawdzić czy system zamyka słabą pozycję gdy pojawi się silniejszy sygnał

**Kod (broker_sim.py:237):**
```python
def check_dynamic_exit(self, current_signals: Dict[str, float]) -> List[str]:
    # Zamyka pozycję gdy:
    # 1. unrealized_pnl > 0 (zysk)
    # 2. Signal decayed > 25% od oryginalnego score
```

**Problem znaleziony:**
- W aktualnej pozycji BTC SELL: `original_signal_score = 0.0`
- Score nie jest zapisywany przy otwieraniu pozycji!
- To uniemożliwia działanie Dynamic Positions

**Wniosek:** BUG - original_signal_score nie jest zapisywany, funkcja Dynamic Positions nie może działać poprawnie.

---

### Test B3: Różne scenariusze symboli ⚠️ NOT TESTED

**Cel:** Testuj XAU→BTC, XAG→US100 itp

**Uwaga:** Test wymaga:
1. Otwarcia pozycji na słabym sygnale
2. Poczekania na silniejszy sygnał na innym symbolu
3. Sprawdzenia czy pozycja została zamknięta

**Test nie został przeprowadzony** - wymaga dłuższego czasu (auto-trade co 5 min) lub manualnego wyzwolenia.

---

## Test C: Position Sizing

### Test C1: Różne strategie = różne wielkości pozycji ✅ PASS

**Cel:** Sprawdzić czy różne strategie dają różne wielkości pozycji

**Wyniki obliczeń (balance=$3000, price=66000):**

| Strategia | Risk % | Leverage | Formula | Size (BTC) |
|-----------|--------|----------|---------|------------|
| btc_v2_core | 2.0% | 20 | (3000×0.02×20)/66000 | 0.0182 |
| btc_scalp_trend | 1.5% | 10 | (3000×0.015×10)/66000 | 0.0068 |

**Różnica:** 2.67x (btc_v2_core jest 2.67x większy)

**Wniosek:** Position sizing działa poprawnie - różne strategie dają różne wielkości pozycji.

---

### Test C2: Risk % jest respektowany ✅ PASS

**Cel:** Sprawdzić czy risk_per_trade_pct jest respektowany

**Wzór:**
```
size = (balance × risk_per_trade_pct × leverage) / price
```

**Przykład dla btc_v2_core:**
- Risk amount = $3000 × 2% = $60
- With leverage 20: $60 × 20 = $1200 notional
- At $66000: 1200/66000 = 0.0182 BTC

**Weryfikacja w kodzie:** `backend/strategy/risk.py:34` - calculate_position_size()

**Wniosek:** Risk % jest respektowany w formule.

---

## Raport PASS/FAIL

| Test | Status | Uwagi |
|------|--------|-------|
| A1: TP/SL różne dla różnych strategii | ✅ PASS | Działają |
| A2: Dynamic TP (HTF RSI) | ⚠️ PARTIAL | Funkcja w kodzie, brak widoczności w API |
| A3: ATR filtr | ✅ PASS | Działa jako filtr zmienności |
| A4: Ideal TP/SL | ⚠️ MANUAL | Brak automatycznego wyznaczania |
| B1: Dynamic Positions On/Off | ✅ PASS | UI działa |
| B2: Logika zamykania | ❌ FAIL | original_signal_score = 0 - BUG! |
| B3: Różne symbole | ⚠️ NOT TESTED | Wymaga czasu |
| C1: Różne wielkości | ✅ PASS | Działają |
| C2: Risk % respektowany | ✅ PASS | Działa |

---

## Proponowany format JSON dla strategii

### tp_sl_config

```json
{
  "exits": {
    "stop_loss": {
      "type": "percent_from_entry",  // lub "atr_multiplier", "price_level"
      "value": -2.0
    },
    "take_profit": {
      "type": "percent_from_entry",
      "value": 5.0
    },
    "trailing_stop": {
      "enabled": true,
      "activation_percent": 1.0,
      "trailing_percent": 0.5
    },
    "dynamic_tp": {
      "enabled": true,
      "htf_indicator": "RSI",
      "htf_timeframe": "30m",
      "rules": [
        {"condition": {"operator": ">", "value": 65}, "tp_percent": 3.0},
        {"condition": {"operator": "<", "value": 40}, "tp_percent": 7.0}
      ],
      "default_tp_percent": 5.0
    }
  }
}
```

### position_sizing_config

```json
{
  "risk": {
    "risk_per_trade_pct": 2.0,
    "max_total_risk_pct": 2.0,
    "leverage": 20,
    "max_notional_exposure_multiple": 1.0
  },
  "position_sizing": {
    "formula": "size = (balance * (risk_per_trade_pct/100) * leverage) / price",
    "rounding": {
      "mode": "floor",
      "step": 0.0001
    }
  }
}
```

---

## TODO / Poprawki

1. **BUG FIX:** Zapisywać `original_signal_score` przy otwieraniu pozycji (broker_sim.py:352)
2. **ENHANCEMENT:** Dodać HTF RSI wartość do API sygnalo (dla weryfikacji dynamic TP)
3. **ENHANCEMENT:** Dodać R:R (Risk:Reward) do odpowiedzi API
4. **ENHANCEMENT:** Opcjonalnie: wyznaczanie TP/SL blisko wsparcia/oporu (zaawansowane)

---
*Test wykonany: 2026-03-09 00:55 UTC*
*Tester: QA Engineer subagent*
