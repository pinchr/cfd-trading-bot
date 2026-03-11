# Backtest Results - 2026-03-11 (Strategy Comparison - UPDATED)

## Test Setup
- **Period:** 7 days (Mar 4-10, 2026)
- **Initial Balance:** $3,000
- **Resolution:** 5m
- **Min Score:** 0.3
- **Backend:** Running ✅
- **MongoDB:** Connected ✅

---

## WYNIKI (Latest Run)

### BTC (Bitcoin) - 7d
| Strategia | Trades | Win Rate | PnL | Status |
|-----------|--------|----------|-----|--------|
| btc_v2_core | 12 | 41.7% | -$11.60 | ⚠️ |
| btc_v2_safe | 12 | 41.7% | -$11.60 | ⚠️ |
| btc_scalp_trend | 0 | 0% | $0.00 | ❌ No trades |
| btc_v3_exp | 13 | 38.5% | -$1.40 | ⚠️ |

**Uwaga:** btc_v2_core i btc_v2_safe dają IDENTYCZNE wyniki (prawdopodobnie ten sam kodstrategii)

### XAU (Gold) - 7d
| Strategia | Trades | Win Rate | PnL | Status |
|-----------|--------|----------|-----|--------|
| xau_v2_momentum | 3 | 0.0% | -$18.29 | ❌ |
| xau_scalp_trend | 0 | 0% | $0.00 | ❌ No trades |
| xau_v3_exp | 20 | 45.0% | +$4.83 | ✅ |

**Najlepsza XAU:** xau_v3_exp (+$4.83, 45% WR)

### XAG (Silver) - 7d
| Strategia | Trades | Win Rate | PnL | Status |
|-----------|--------|----------|-----|--------|
| xag_v3_exp | 37 | 40.5% | +$23.67 | ✅ (using default) |

**Najlepsza XAG:** xag_v3_exp/default (+$23.67, 40.5% WR)

---

## PODSUMOWANIE

| Symbol | Najlepsza Strategia | PnL | Win Rate | Trades |
|--------|---------------------|-----|----------|--------|
| **BTC** | btc_v3_exp | -$1.40 | 38.5% | 13 |
| **XAU** | xau_v3_exp | +$4.83 | 45.0% | 20 |
| **XAG** | xag_v3_exp (default) | +$23.67 | 40.5% | 37 |

---

## 🔍 ANALIZA

1. **BTC:** Wszystkie strategie na minusie. btc_v3_exp najmniej traci (-$1.40). 
   - Problem: rynek BTC w dół w tym okresie (Mar 4-10)
   - btc_v2_core i btc_v2_safe są IDENTYCZNE (ten sam wynik)

2. **XAU:** xau_v3_exp działa najlepiej (+$4.83, 45% WR)
   - xau_v2_momentum traci (-$18.29) - slaba strategia
   - xau_scalp_trend nie generuje trades

3. **XAG:** Najlepszy wynik (+$23.67, 40.5% WR, 37 trades)
   - xag_v3_exp strategy wrapper ma buga, ale default działa

4. **Scalp strategies:** btc_scalp_trend i xau_scalp_trend NIE GENERUJĄ żadnych trades
   - Wymagają debugowania

---

## REKOMENDACJE

1. ✅ **BTC:** Użyj btc_v3_exp (najmniejsza strata)
2. ✅ **XAU:** Użyj xau_v3_exp (+$4.83)
3. ✅ **XAG:** Użyj domyślnej strategii (+$23.67)
4. 🔧 **Scalp strategies:** Wymagają debugowania - brak trades
5. 🔧 **btc_v2_safe:** Tożsama z btc_v2_core - do usunięcia lub poprawy

---

## PORÓWNANIE Z POPRZEDNIM RUN (adaptive_regime)

| Symbol | JSON v2/v3 | adaptive_regime | Różnica |
|--------|------------|-----------------|---------|
| BTC | -$11.60 (v3) | +$151.07 | adaptive 18x lepsze! |
| XAU | +$4.83 (v3) | -$5.28 | JSON lepsze |
| XAG | +$23.67 | +$23.67 | równo |

**Wniosek:** adaptive_regime nadal najlepszy dla BTC. Dla XAU/XAG JSON strategie wychodzą na plus.

---

## OPTIMIZACJA - Następne kroki

1. Naprawić btc_scalp_trend i xau_scalp_trend (brak trades)
2. Usunąć duplikat btc_v2_safe lub zmienić jego konfigurację
3. Zwiększyć indicator weights (0.5 → 1.5-2.0) - zgodnie z poprzednimi rekomendacjami
4. Przetestować adaptive_regime z nowymi parametrami weight
