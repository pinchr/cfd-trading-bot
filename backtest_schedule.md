# Backtest Schedule & Periods

## Test Periods (4 weeks - same for all symbols)
- **Week 1**: 2026-02-09 to 2026-02-16 (7 days)
- **Week 2**: 2026-02-16 to 2026-02-23 (7 days)
- **Week 3**: 2026-02-23 to 2026-03-02 (7 days)
- **Week 4**: 2026-03-02 to 2026-03-09 (7 days)

## Timeframes to Test
- **5m**: 1 week (Week 4 latest)
- **15m**: 1 week (Week 4)
- **30m**: 1 week (Week 4)
- **1h**: 2 weeks (Week 3-4 combined)

## Symbols
- XAG (PRIORITY!)
- BTC
- XAU (skip - losing)

## Strategy Parameters to Test
1. risk_per_trade: 2.0% (baseline) → 3.0%, 4.0%
2. leverage: 20x (baseline) → 30x
3. min_score: 0.05 (baseline) → 0.03, 0.10, 0.15
4. Different TP/SL combinations
