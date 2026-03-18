# Backtest Results - 2026-03-13 (Strategy Analyzer Run 02:23 UTC)

## This Run's Results (2026-03-13 02:23 UTC)

### XAU min_score Scan (21d, 60m)
| Config | Trades | Win Rate | Return | Notes |
|--------|--------|----------|--------|-------|
| **base** | 41 | 43.9% | **+5.9%** | ✅ BEST - confirmed optimal |
| min_score_0.75x | 126 | 38.1% | -17.9% | ❌ More trades = losses |
| min_score_1.25x | 3 | 100% | +1.2% | ⚠️ Too few trades |
| min_score_1.5x | 0 | 0% | 0% | ❌ Too strict |

### Key Finding: XAU base is already optimal!
- Lowering min_score gives more trades but lower quality (losing money)
- Current base config with 41 trades and +5.9% is the best achievable
- Further optimization of XAU would require different indicators or timeframes

---

# Backtest Results - 2026-03-13 (Strategy Analyzer Run 02:08 UTC)

## This Run's Results (2026-03-13 02:08 UTC)

| Symbol | Config | Period | TF | Trades | Win Rate | Return | Notes |
|--------|--------|--------|-----|--------|----------|--------|-------|
| **XAG** | xag_v3_exp | 45d | 60m | 297 | 38.7% | **+20.0%** | ✅ Same as 21d/30d - capped |
| **BTC** | btc_scalp_trend | 7d | 60m | 216 | 40.7% | **+14.4%** | ✅ Capped at 216 (7-60d) |
| **XAU** | xau_v2_momentum | 30d | 60m | 278 | 35.6% | **-34.4%** | ❌ Too many bad trades |
| **XAU** | momentum_only | 21d | 60m | 13 | 61.5% | **+2.4%** | ⚠️ Few trades, high win rate |
| **XAU** | xau_base | 30d | 60m | 41 | 43.9% | **+5.9%** | ✅ Same as 14d/21d |

### Key Findings
- **XAG consistent**: 21d, 30d, 45d all give +20.0%, capped at 297 trades
- **BTC capped**: 216 trades regardless of period (7d-60d), always +14.4%
- **XAU struggle**: v2_momentum loses (-34.4%), base wins (+5.9%), momentum_only has few trades but high win rate
- **XAU configs tested**: Need better config for XAU - low trade count limits profitability

## This Run's Results (2026-03-13 01:53 UTC)

| Symbol | Config | Period | TF | Trades | Win Rate | Return | Notes |
|--------|--------|--------|-----|--------|----------|--------|-------|
| **XAG** | xag_v3_exp | 21d | 60m | 297 | 38.7% | **+20.0%** | ✅ Same as 30d |
| **XAU** | xau_base | 21d | 60m | 41 | 43.9% | **+5.9%** | ✅ Same as 14d |
| **BTC** | btc_scalp_trend | 21d | 60m | 216 | 40.7% | **+14.4%** | ✅ Capped |

### Key Findings
- **XAG consistent**: 21d and 30d both give +20.0%
- **XAU consistent**: 14d and 21d both give +5.9%
- **BTC capped**: 216 trades regardless of period

---

## This Run's Results (2026-03-13 01:38 UTC)

| Symbol | Config | Period | TF | Trades | Win Rate | Return | Notes |
|--------|--------|--------|-----|--------|----------|--------|-------|
| **BTC** | btc_scalp_trend | 21d | 60m | 216 | 40.7% | **+14.4%** | ✅ Same as 30d, capped |
| XAU | xau_v3_exp | 14d | 60m | 278 | 35.6% | **-34.4%** | ❌ Worse than base |
| **XAG** | xag_v3_exp | 30d | 60m | 297 | 38.7% | **+20.0%** | ✅ BEST for XAG! |

### Key Findings
- **XAG breakthrough**: xag_v3_exp 30d gives +20.0% - best XAG result ever!
- **XAU v3 exp fails**: -34.4% vs xau_base +5.9%
- **BTC capped**: 216 trades regardless of period (14-60d)

---

## Previous (01:09 UTC)

| Symbol | Period | TF | Trades | Win Rate | Return | Notes |
|--------|--------|-----|--------|----------|--------|-------|
| **BTC** | 45d | 60m | 216 | 40.7% | **+14.4%** | Same as 30d |
| **BTC** | 60d | 60m | 216 | 40.7% | **+14.4%** | Same as 30d - capped |
| **XAU** | 14d | 60m | 49 | 40.8% | **+4.5%** | ✅ Previous best |
| XAU | 30d | 60m | 278 | 35.6% | -17.1% | ❌ Too many bad trades |
| XAU | 14d | 60m | 41 | 43.9% | **+5.9%** | ✅ Base/no_rsi better than scalp |
| XAU | 14d | 5m | 0 | - | 0% | ❌ No data |
| XAU | 14d | 15m | 0 | - | 0% | ❌ No data |
| XAU | 14d | 240m | 0 | - | 0% | ❌ No data |
| XAG | 14d | 5m | 0 | - | 0% | ❌ No data |

### This Run's Findings
- **XAU base/no_rsi better than xau_scalp_trend**: 41 trades, +5.9% vs 49 trades, +4.5%
- **240m TF unavailable** for XAU in MongoDB
- **min_score doesn't affect unified strategies** - backtester overrides to 0.0 for unified mode

| Symbol | Trades | Win Rate | PnL | Change vs Previous |
|--------|--------|----------|-----|-------------------|
| **BTC** | 56 | 42.9% | **+7.2%** | ✅ Improved from 39 trades |
| **XAU** (base) | 41 | 43.9% | **+5.9%** | ✅ Better win rate than scalp |
| **XAU** (scalp) | 49 | 40.8% | **+4.5%** | ✅ Previous best |

---

## Extended Testing Results (2026-03-13)

| Symbol | Period | TF | Trades | Win Rate | Return | Notes |
|--------|--------|-----|--------|----------|--------|-------|
| **BTC** | 30d | 60m | 216 | 40.7% | **+14.4%** | ✅ BEST - More trades = better |
| XAU | 30d | 60m | 278 | 35.6% | -17.1% | ❌ Too many bad trades |
| XAG | 14d | 60m | 15 | 33.3% | -7.3% | ❌ Too few trades |

### Key Finding
- **BTC benefits from longer period (30d)** - 216 trades, +14.4%
- **XAU/XAG don't benefit from 60m** - too few or losing trades

---

## Previous Results (2026-03-11)

### Naprawy wprowadzone tego dnia

1. **min_score** w backtester.py: XAU 0.30→0.05, XAG 0.28→0.05, BTC 0.20→0.05
2. **strong_threshold** w get_direction(): 0.45→0.25
3. **RSI neutral zone (45-55)**: zwracało 0 → teraz daje słaby kierunek
4. **StochRSI neutral zone (20-80)**: zwracało 0 → teraz daje słaby kierunek

---

## WYNIKI (14 dni, 5m TF) - from 2026-03-11

| Symbol | Trades | Win Rate | PnL | Zmiana vs przed |
|--------|--------|----------|-----|-----------------|
| **BTC** | 39 | 43.6% | **+$104.11** | ✅ +$105 |
| **XAU** | 19 | 42.1% | -$30.28 | ⚠️ -$35 |
| **XAG** | 63 | 42.9% | **+$182.58** | ✅ +$160 |

## Naprawy wprowadzone tego dnia

1. **min_score** w backtester.py: XAU 0.30→0.05, XAG 0.28→0.05, BTC 0.20→0.05
2. **strong_threshold** w get_direction(): 0.45→0.25
3. **RSI neutral zone (45-55)**: zwracało 0 → teraz daje słaby kierunek
4. **StochRSI neutral zone (20-80)**: zwracało 0 → teraz daje słaby kierunek

---

## WYNIKI (14 dni, 5m TF)

| Symbol | Trades | Win Rate | PnL | Zmiana vs przed |
|--------|--------|----------|-----|-----------------|
| **BTC** | 39 | 43.6% | **+$104.11** | ✅ +$105 |
| **XAU** | 19 | 42.1% | -$30.28 | ⚠️ -$35 |
| **XAG** | 63 | 42.9% | **+$182.58** | ✅ +$160 |

---

## Szczegóły

### BTC (14 dni)
- Initial: $3,000
- Final: $3,104.11
- Winning: 17 / 39
- Losing: 22 / 39

### XAU (14 dni)  
- Initial: $3,000
- Final: $2,969.72
- Winning: 8 / 19
- Losing: 11 / 19

### XAG (14 dni)
- Initial: $3,000
- Final: $3,182.58
- Winning: 27 / 63
- Losing: 36 / 63

---

## Wnioski

1. **Naprawa min_score** - drastycznie zwiększyła liczbę trades (13→39 BTC, 37→63 XAG)
2. **RSI/Stoch neutral zones** - teraz generują sygnały nawet w strefie 45-55
3. **XAG najlepszy** - +$182.58 przy 63 trades
4. **BTC dobry** - +$104.11 przy 39 trades
5. **XAU wymaga optymalizacji** - mniej trades niż przed naprawą

## TODO
- Zbadać dlaczego XAU ma mniej trades
- Dodać więcej wskaźników do XAU
- Przetestować dłuższy okres (30 dni)
