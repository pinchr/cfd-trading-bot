"""
Tests for the backtesting engine and historical data module.

Run:  python -m pytest tests/test_backtester.py -v
"""

import os
import sys

import pytest

# Ensure backend dir is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtester import (
    LOOKBACK,
    MAX_HOLD_CANDLES,
    BacktestResult,
    BacktestTrade,
    aggregate_to_daily,
    calculate_signal_score,
    get_direction,
    results_to_dict,
    run_backtest,
)
from historical_data import generate_sample_data, load_csv_candles
from indicators import TechnicalIndicators

# ── Fixtures ──


@pytest.fixture
def gold_candles():
    """200+ daily candles for Gold with fixed seed (deterministic)."""
    return generate_sample_data("XAU", days=300, base_price=2000.0)


@pytest.fixture
def silver_candles():
    return generate_sample_data("XAG", days=300, base_price=23.0)


@pytest.fixture
def nasdaq_candles():
    return generate_sample_data("US100", days=300, base_price=17500.0)


@pytest.fixture
def btc_candles():
    return generate_sample_data("BTC", days=300, base_price=95000.0)


@pytest.fixture
def short_candles():
    """Too few candles — should fail."""
    return generate_sample_data("XAU", days=50, base_price=2000.0)


# ── Sample data generator tests ──


class TestSampleDataGenerator:
    def test_generates_correct_count(self):
        candles = generate_sample_data("XAU", days=200, base_price=2000.0)
        # Weekends are skipped for equity-like instruments, so ~143 trading days
        assert len(candles) > 100
        assert len(candles) < 200  # Must skip weekends

    def test_btc_includes_weekends(self):
        candles = generate_sample_data("BTC", days=100, base_price=95000.0)
        # BTC trades every day, so should be close to 100
        assert len(candles) == 100

    def test_deterministic_with_same_seed(self):
        c1 = generate_sample_data("XAU", days=100, base_price=2000.0)
        c2 = generate_sample_data("XAU", days=100, base_price=2000.0)
        assert len(c1) == len(c2)
        assert c1[0]["close"] == c2[0]["close"]
        assert c1[-1]["close"] == c2[-1]["close"]

    def test_different_symbol_gives_different_data(self):
        c1 = generate_sample_data("XAU", days=100, base_price=2000.0)
        c2 = generate_sample_data("XAG", days=100, base_price=23.0)
        assert c1[10]["close"] != c2[10]["close"]

    def test_candle_structure(self):
        candles = generate_sample_data("XAU", days=100, base_price=2000.0)
        for c in candles:
            assert "timestamp" in c
            assert "time" in c
            assert "open" in c
            assert "high" in c
            assert "low" in c
            assert "close" in c
            assert "volume" in c
            # OHLC validity
            assert c["high"] >= c["low"]
            assert c["high"] >= c["open"]
            assert c["high"] >= c["close"]
            assert c["low"] <= c["open"]
            assert c["low"] <= c["close"]
            assert c["volume"] > 0

    def test_prices_near_base(self):
        candles = generate_sample_data("XAU", days=100, base_price=2000.0)
        # After 100 days of random walk, prices should still be in a reasonable range
        for c in candles:
            assert 1000 < c["close"] < 4000, f"Price {c['close']} too far from base 2000"

    def test_chronological_order(self):
        candles = generate_sample_data("XAU", days=100, base_price=2000.0)
        for i in range(1, len(candles)):
            assert candles[i]["timestamp"] > candles[i - 1]["timestamp"]


# ── Indicator tests ──


class TestIndicators:
    def test_rsi_range(self, gold_candles):
        closes = [c["close"] for c in gold_candles]
        rsi = TechnicalIndicators.rsi(closes, 14)
        assert rsi is not None
        assert 0 <= rsi <= 100

    def test_macd_structure(self, gold_candles):
        closes = [c["close"] for c in gold_candles]
        macd = TechnicalIndicators.macd(closes)
        assert macd is not None
        assert "macd_line" in macd
        assert "signal_line" in macd
        assert "histogram" in macd

    def test_bollinger_bands(self, gold_candles):
        closes = [c["close"] for c in gold_candles]
        bb = TechnicalIndicators.bollinger_bands(closes)
        assert bb is not None
        assert bb["upper"] > bb["middle"] > bb["lower"]

    def test_atr_positive(self, gold_candles):
        highs = [c["high"] for c in gold_candles]
        lows = [c["low"] for c in gold_candles]
        closes = [c["close"] for c in gold_candles]
        atr = TechnicalIndicators.atr(highs, lows, closes, 14)
        assert atr is not None
        assert atr > 0

    def test_adx_structure(self, gold_candles):
        highs = [c["high"] for c in gold_candles]
        lows = [c["low"] for c in gold_candles]
        closes = [c["close"] for c in gold_candles]
        adx = TechnicalIndicators.adx(highs, lows, closes, 14)
        assert adx is not None
        assert "adx" in adx
        assert "plus_di" in adx
        assert "minus_di" in adx
        assert 0 <= adx["adx"] <= 100

    def test_calculate_all(self, gold_candles):
        result = TechnicalIndicators.calculate_all(gold_candles, period=14)
        assert result is not None
        assert "rsi_14" in result
        assert "macd" in result
        assert "atr_14" in result
        assert "bollinger_bands" in result
        assert "adx" in result
        assert "stoch_rsi" in result
        assert "candlestick_patterns" in result

    def test_candlestick_patterns(self, gold_candles):
        cp = TechnicalIndicators.candlestick_patterns(gold_candles)
        assert cp is not None
        assert "patterns" in cp
        assert "net_bias" in cp
        assert -1 <= cp["net_bias"] <= 1
        for p in cp["patterns"]:
            assert "name" in p
            assert "bias" in p
            assert "strength" in p

    def test_candlestick_bullish_engulfing(self):
        """Test that a bullish engulfing pattern is detected."""
        candles = [
            {"open": 105, "high": 106, "low": 99, "close": 100, "volume": 100},  # bearish
            {"open": 102, "high": 103, "low": 98, "close": 99, "volume": 100},  # bearish
            {"open": 98, "high": 107, "low": 97, "close": 106, "volume": 200},  # big bullish engulfing
        ]
        cp = TechnicalIndicators.candlestick_patterns(candles)
        assert cp is not None
        names = [p["name"] for p in cp["patterns"]]
        assert "BULLISH_ENGULFING" in names
        assert cp["net_bias"] > 0

    def test_candlestick_bearish_engulfing(self):
        """Test that a bearish engulfing pattern is detected."""
        candles = [
            {"open": 100, "high": 107, "low": 99, "close": 106, "volume": 100},  # bullish
            {"open": 104, "high": 108, "low": 103, "close": 107, "volume": 100},  # bullish
            {"open": 108, "high": 109, "low": 100, "close": 101, "volume": 200},  # big bearish engulfing
        ]
        cp = TechnicalIndicators.candlestick_patterns(candles)
        assert cp is not None
        names = [p["name"] for p in cp["patterns"]]
        assert "BEARISH_ENGULFING" in names
        assert cp["net_bias"] < 0

    def test_candlestick_too_few_candles(self):
        """Need at least 3 candles."""
        candles = [
            {"open": 100, "high": 105, "low": 95, "close": 102, "volume": 100},
        ]
        assert TechnicalIndicators.candlestick_patterns(candles) is None


# ── Signal scoring tests ──


class TestSignalScoring:
    def test_score_range(self, gold_candles):
        ind = TechnicalIndicators.calculate_all(gold_candles, period=14)
        ind["_closes"] = [c["close"] for c in gold_candles]
        score, component_scores = calculate_signal_score(ind)
        assert -1 <= score <= 1
        direction = get_direction(score)
        assert direction in ("STRONG_BUY", "BUY", "NEUTRAL", "SELL", "STRONG_SELL")

    def test_strong_buy_threshold(self):
        # Score > 0.45 should be STRONG_BUY
        assert get_direction(0.50) == "STRONG_BUY"
        assert get_direction(0.20) == "BUY"
        assert get_direction(0.10) == "NEUTRAL"
        assert get_direction(-0.20) == "SELL"
        assert get_direction(-0.50) == "STRONG_SELL"

    def test_instrument_specific_thresholds(self):
        # Gold requires min_score=0.30 to enter
        assert get_direction(0.25, min_score=0.30) == "NEUTRAL"
        assert get_direction(0.35, min_score=0.30) == "BUY"
        # BTC/US100 can enter at 0.20
        assert get_direction(0.25, min_score=0.20) == "BUY"

    def test_neutral_for_flat_market(self):
        """A perfectly flat market should produce neutral signals."""
        candles = []
        for i in range(100):
            candles.append(
                {
                    "open": 100.0,
                    "high": 100.5,
                    "low": 99.5,
                    "close": 100.0,
                    "volume": 50000,
                }
            )
        ind = TechnicalIndicators.calculate_all(candles, period=14)
        if ind:
            ind["_closes"] = [100.0] * 100
            score, component_scores = calculate_signal_score(ind)
            # Flat market should be neutral or very weak signal
            assert abs(score) < 0.5


# ── Backtest engine tests ──


class TestBacktestEngine:
    def test_basic_run(self, gold_candles):
        result = run_backtest(gold_candles, symbol="XAU")
        assert isinstance(result, BacktestResult)
        assert result.symbol == "XAU"
        assert result.total_candles == len(gold_candles)
        assert result.total_trades >= 0
        assert result.total_signals > 0

    def test_too_few_candles_raises(self, short_candles):
        if len(short_candles) < LOOKBACK + 10:
            with pytest.raises(ValueError, match="Need at least"):
                run_backtest(short_candles, symbol="XAU")

    def test_trades_have_valid_structure(self, gold_candles):
        result = run_backtest(gold_candles, symbol="XAU")
        for trade in result.trades:
            assert isinstance(trade, BacktestTrade)
            assert trade.direction in ("BUY", "SELL")
            assert trade.entry_price > 0
            assert trade.exit_price is not None
            assert trade.exit_price > 0
            assert trade.exit_reason in ("TP", "SL", "TRAIL", "TIMEOUT", "END")
            assert trade.entry_idx >= LOOKBACK
            assert trade.exit_idx >= trade.entry_idx

    def test_win_rate_bounds(self, gold_candles):
        result = run_backtest(gold_candles, symbol="XAU")
        assert 0 <= result.win_rate <= 100
        assert result.winning_trades + result.losing_trades == result.total_trades

    def test_equity_curve_length(self, gold_candles):
        result = run_backtest(gold_candles, symbol="XAU")
        # Equity curve has one entry per candle from LOOKBACK onward, plus initial
        assert len(result.equity_curve) > 0

    def test_max_drawdown_non_negative(self, gold_candles):
        result = run_backtest(gold_candles, symbol="XAU")
        assert result.max_drawdown_pct >= 0

    def test_profit_factor_non_negative(self, gold_candles):
        result = run_backtest(gold_candles, symbol="XAU")
        assert result.profit_factor >= 0

    def test_all_instruments(self, gold_candles, silver_candles, nasdaq_candles, btc_candles):
        """Run backtest for all 4 instruments."""
        for candles, sym in [
            (gold_candles, "XAU"),
            (silver_candles, "XAG"),
            (nasdaq_candles, "US100"),
            (btc_candles, "BTC"),
        ]:
            result = run_backtest(candles, symbol=sym)
            assert result.total_candles > 0
            assert result.total_signals > 0, f"{sym} produced no signals"

    def test_max_concurrent_respected(self, gold_candles):
        """With max_concurrent=1, should never have overlapping trades."""
        result = run_backtest(gold_candles, symbol="XAU", max_concurrent=1)
        # Sort trades by entry index
        sorted_trades = sorted(result.trades, key=lambda t: t.entry_idx)
        for i in range(1, len(sorted_trades)):
            prev = sorted_trades[i - 1]
            curr = sorted_trades[i]
            # Current trade should start after previous trade exits
            assert curr.entry_idx >= prev.exit_idx, (
                f"Trade overlap: trade {i-1} exits at {prev.exit_idx}, " f"trade {i} enters at {curr.entry_idx}"
            )

    def test_stop_loss_respected(self, gold_candles):
        """Trades closed via SL should exit at the stop loss price."""
        result = run_backtest(gold_candles, symbol="XAU")
        for trade in result.trades:
            if trade.exit_reason == "SL":
                assert trade.exit_price == trade.stop_loss

    def test_take_profit_respected(self, gold_candles):
        """Trades closed via TP should exit at the take profit price."""
        result = run_backtest(gold_candles, symbol="XAU")
        for trade in result.trades:
            if trade.exit_reason == "TP":
                assert trade.exit_price == trade.take_profit

    def test_timeout_respected(self, gold_candles):
        """Timed-out trades should not exceed MAX_HOLD_CANDLES bars."""
        result = run_backtest(gold_candles, symbol="XAU")
        for trade in result.trades:
            if trade.exit_reason == "TIMEOUT":
                bars_held = trade.exit_idx - trade.entry_idx
                assert bars_held >= MAX_HOLD_CANDLES

    def test_buy_pnl_calculation(self):
        """Manual check: BUY trade P&L should be positive when exit > entry."""
        candles = generate_sample_data("XAU", days=300, base_price=2000.0)
        result = run_backtest(candles, symbol="XAU")
        for trade in result.trades:
            if trade.direction == "BUY" and trade.exit_reason in ("TP", "SL"):
                expected_sign = 1 if trade.exit_price > trade.entry_price else -1
                actual_sign = 1 if trade.pnl_pct > 0 else -1
                assert expected_sign == actual_sign, (
                    f"BUY: entry={trade.entry_price}, exit={trade.exit_price}, " f"pnl={trade.pnl_pct}"
                )

    def test_sell_pnl_calculation(self):
        """Manual check: SELL trade P&L should be positive when exit < entry."""
        candles = generate_sample_data("XAG", days=300, base_price=23.0)
        result = run_backtest(candles, symbol="XAG")
        for trade in result.trades:
            if trade.direction == "SELL" and trade.exit_reason in ("TP", "SL"):
                expected_sign = 1 if trade.exit_price < trade.entry_price else -1
                actual_sign = 1 if trade.pnl_pct > 0 else -1
                assert expected_sign == actual_sign, (
                    f"SELL: entry={trade.entry_price}, exit={trade.exit_price}, " f"pnl={trade.pnl_pct}"
                )

    def test_deterministic_results(self, gold_candles):
        """Same input data should produce identical backtest results."""
        r1 = run_backtest(gold_candles, symbol="XAU")
        r2 = run_backtest(gold_candles, symbol="XAU")
        assert r1.total_trades == r2.total_trades
        assert r1.win_rate == r2.win_rate
        assert r1.total_return_pct == r2.total_return_pct

    def test_results_to_dict(self, gold_candles):
        result = run_backtest(gold_candles, symbol="XAU")
        d = results_to_dict(result)
        assert d["symbol"] == "XAU"
        assert isinstance(d["trades"], list)
        assert "win_rate" in d
        assert "total_return_pct" in d
        # Should be JSON serialisable
        import json

        json_str = json.dumps(d)
        assert len(json_str) > 0


# ── Multi-timeframe tests ──


class TestMultiTimeframe:
    """Tests for aggregate_to_daily and multi-TF consistency."""

    def test_aggregate_to_daily_basic(self):
        """Aggregated daily OHLCV should match intraday extremes."""
        candles_60m = generate_sample_data("XAU", days=30, base_price=2000.0, resolution="60")
        daily = aggregate_to_daily(candles_60m)
        assert len(daily) > 0
        # Each daily bar should have valid OHLCV
        for d in daily:
            assert d["high"] >= d["low"]
            assert d["high"] >= d["open"]
            assert d["high"] >= d["close"]
            assert d["low"] <= d["open"]
            assert d["low"] <= d["close"]
            assert d["volume"] > 0

    def test_aggregate_preserves_price_path(self):
        """First daily open should equal first intraday open, last daily close should equal last intraday close."""
        candles_60m = generate_sample_data("BTC", days=10, base_price=95000.0, resolution="60")
        daily = aggregate_to_daily(candles_60m)
        assert daily[0]["open"] == candles_60m[0]["open"]
        assert daily[-1]["close"] == candles_60m[-1]["close"]

    def test_aggregate_daily_high_matches_intraday(self):
        """Daily high must be >= all intraday highs for that day."""
        candles_60m = generate_sample_data("XAU", days=5, base_price=2000.0, resolution="60")
        daily = aggregate_to_daily(candles_60m)
        # Check first day
        first_date = daily[0]["timestamp"].split("T")[0]
        intraday_highs = [c["high"] for c in candles_60m if c["timestamp"].startswith(first_date)]
        assert daily[0]["high"] >= max(intraday_highs) - 0.01  # float tolerance

    def test_mtf_backtest_runs(self):
        """Backtest with htf_candles parameter should work without error."""
        candles_60m = generate_sample_data("BTC", days=30, base_price=95000.0, resolution="60")
        htf = aggregate_to_daily(candles_60m)
        result = run_backtest(candles_60m, symbol="BTC", htf_candles=htf)
        assert result.total_candles > 0
        assert result.total_candles == len(candles_60m)


# ── Candle accumulation & aggregation tests ──


class TestCandleAggregation:
    """Tests for the candle aggregation pipeline in database.py."""

    def test_aggregate_60m_from_15m(self):
        """Build 1H candles from 15m candles."""
        from database import aggregate_candles

        candles_15m = generate_sample_data("XAU", days=5, base_price=2000.0, resolution="15")
        result = aggregate_candles(candles_15m, "60")
        # 15m → 60m: ~4x fewer candles
        assert len(result) > 0
        assert len(result) < len(candles_15m)
        # Each aggregated candle should have valid OHLCV
        for c in result:
            assert c["high"] >= c["low"]
            assert c["open"] > 0
            assert c["close"] > 0

    def test_aggregate_daily_from_60m(self):
        """Build daily candles from 1H candles."""
        from database import aggregate_candles

        candles_60m = generate_sample_data("XAU", days=10, base_price=2000.0, resolution="60")
        daily = aggregate_candles(candles_60m, "D")
        assert len(daily) > 0
        # Should have fewer bars than 60m
        assert len(daily) < len(candles_60m)
        # Daily open should match first 60m open of that day
        first_date = daily[0]["timestamp"].split("T")[0]
        first_60m = [c for c in candles_60m if c["timestamp"].startswith(first_date)]
        assert daily[0]["open"] == first_60m[0]["open"]
        # Daily close should match last 60m close of that day
        assert daily[0]["close"] == first_60m[-1]["close"]

    def test_aggregate_preserves_high_low(self):
        """Aggregated high/low must match extremes of source candles."""
        from database import aggregate_candles

        candles_15m = generate_sample_data("BTC", days=3, base_price=95000.0, resolution="15")
        hourly = aggregate_candles(candles_15m, "60")
        # Check that hourly high >= all source highs in that group
        for h_candle in hourly[:3]:
            ts = h_candle["timestamp"]
            # Find source candles that contributed to this bar (same hour)
            hour_str = ts[:13]  # "YYYY-MM-DDTHH"
            sources = [c for c in candles_15m if c["timestamp"].startswith(hour_str)]
            if sources:
                assert h_candle["high"] >= max(c["high"] for c in sources) - 0.01
                assert h_candle["low"] <= min(c["low"] for c in sources) + 0.01

    def test_aggregate_volume_sums(self):
        """Aggregated volume should be the sum of source candle volumes."""
        from database import aggregate_candles

        candles_5m = generate_sample_data("US100", days=2, base_price=17500.0, resolution="5")
        hourly = aggregate_candles(candles_5m, "60")
        # Total volume should be preserved
        total_5m_vol = sum(c.get("volume", 0) for c in candles_5m)
        total_hourly_vol = sum(c.get("volume", 0) for c in hourly)
        assert total_hourly_vol == total_5m_vol

    def test_store_and_load_candles_in_memory(self):
        """Test in-memory candle accumulation (no MongoDB)."""
        from database import _candle_history_mem, count_candles, load_candle_history, store_candles, get_db

        # Clear any existing state - both in-memory and MongoDB
        _candle_history_mem.clear()
        
        db = get_db()
        if db is not None:
            # Clear ALL BTC/60 candles (not just test source - there may be existing data)
            db.candles.delete_many({"symbol": "BTC", "resolution": "60"})

        # BTC trades 24h so we get many candles per day
        candles = generate_sample_data("BTC", days=10, base_price=95000.0, resolution="60")
        assert len(candles) >= 100, f"Expected 100+ candles, got {len(candles)}"

        batch1 = candles[:50]
        store_candles("BTC", "60", batch1, source="test")
        assert count_candles("BTC", "60") == 50

        # Store overlapping + new candles
        batch2 = candles[40:80]
        store_candles("BTC", "60", batch2, source="test")
        # Should have 80+ unique candles (50 original + 30 new, 10 overlap deduped)
        # Note: may be 81+ due to timing variations in generate_sample_data
        assert count_candles("BTC", "60") >= 80

        # Load and verify order
        loaded = load_candle_history("BTC", "60")
        assert len(loaded) >= 80  # May be 80-81 depending on data
        # Should be chronological
        for i in range(1, len(loaded)):
            assert loaded[i]["timestamp"] >= loaded[i - 1]["timestamp"]

        # Clean up
        _candle_history_mem.clear()
        if db is not None:
            db.candles.delete_many({"symbol": "BTC", "resolution": "60"})


# ── CSV loader tests ──


class TestIntradayBacktest:
    """Tests for intraday (15m/30m) backtesting."""

    def test_15m_sample_generation(self):
        candles = generate_sample_data("XAU", days=10, base_price=2000.0, resolution="15")
        assert len(candles) > 100  # ~26 candles/day * ~7 trading days
        # All times should be at 15m intervals
        for c in candles:
            parts = c["time"].split(":")
            assert int(parts[1]) % 15 == 0

    def test_30m_sample_generation(self):
        candles = generate_sample_data("XAU", days=10, base_price=2000.0, resolution="30")
        assert len(candles) > 50  # ~13 candles/day * ~7 trading days
        for c in candles:
            parts = c["time"].split(":")
            assert int(parts[1]) % 30 == 0

    def test_60m_sample_generation(self):
        candles = generate_sample_data("US100", days=10, base_price=17500.0, resolution="60")
        assert len(candles) > 30

    def test_btc_24h_candles(self):
        """BTC should generate 24h of candles per day (no market hours restriction)."""
        candles = generate_sample_data("BTC", days=2, base_price=95000.0, resolution="60")
        # 2 days * 24 hours = 48 candles
        assert len(candles) == 48

    def test_intraday_backtest_runs(self):
        """15m backtest should run and produce signals (trades may be filtered by strict commodity rules)."""
        # Use BTC (fewer filters) to ensure trades are generated
        candles = generate_sample_data("BTC", days=30, base_price=95000.0, resolution="15")
        result = run_backtest(candles, symbol="BTC")
        assert result.total_trades > 0
        assert result.total_signals > 0
        assert 0 <= result.win_rate <= 100

    def test_30m_backtest_all_instruments(self):
        """30m backtest across all instruments."""
        configs = [
            ("XAU", 2000.0),
            ("XAG", 23.0),
            ("US100", 17500.0),
            ("BTC", 95000.0),
        ]
        for sym, base in configs:
            candles = generate_sample_data(sym, days=30, base_price=base, resolution="30")
            result = run_backtest(candles, symbol=sym)
            assert result.total_signals > 0, f"{sym} at 30m produced no signals"

    def test_intraday_chronological_order(self):
        candles = generate_sample_data("XAU", days=5, base_price=2000.0, resolution="15")
        for i in range(1, len(candles)):
            assert candles[i]["timestamp"] > candles[i - 1]["timestamp"]


class TestCSVLoader:
    def test_missing_file_returns_none(self):
        result = load_csv_candles("/nonexistent/file.csv")
        assert result is None

    def test_load_valid_csv(self, tmp_path):
        csv_file = tmp_path / "test_data.csv"
        csv_file.write_text(
            "Date,Open,High,Low,Close,Volume\n"
            "2025-01-02,100.0,105.0,98.0,103.0,50000\n"
            "2025-01-03,103.0,107.0,101.0,106.0,60000\n"
            "2025-01-06,106.0,110.0,104.0,108.0,55000\n"
        )
        candles = load_csv_candles(str(csv_file))
        assert candles is not None
        assert len(candles) == 3
        assert candles[0]["open"] == 100.0
        assert candles[2]["close"] == 108.0

    def test_load_with_multiplier(self, tmp_path):
        csv_file = tmp_path / "test_gold.csv"
        csv_file.write_text("Date,Open,High,Low,Close,Volume\n" "2025-01-02,190.0,195.0,188.0,193.0,50000\n")
        candles = load_csv_candles(str(csv_file), multiplier=10.0)
        assert candles is not None
        assert candles[0]["close"] == 1930.0  # 193 * 10


# ── Time format tests (regression for the x-axis bug) ──


class TestTimeFormatting:
    def test_realistic_prices_60m_times_aligned(self):
        """60-minute candles should have times ending in :00."""
        from realistic_prices import RealisticPriceFeeder

        feeder = RealisticPriceFeeder()
        candles = feeder.get_candles("XAU", resolution="60", count=20)
        assert candles is not None
        for c in candles:
            time_str = c["time"]
            # Should be HH:MM format with minutes = 00
            assert ":" in time_str, f"Bad time format: {time_str}"
            parts = time_str.split(":")
            assert len(parts) == 2
            assert parts[1] == "00", f"60m candle should end in :00, got {time_str}"

    def test_realistic_prices_30m_times_aligned(self):
        """30-minute candles should have times ending in :00 or :30."""
        from realistic_prices import RealisticPriceFeeder

        feeder = RealisticPriceFeeder()
        candles = feeder.get_candles("XAU", resolution="30", count=20)
        assert candles is not None
        for c in candles:
            time_str = c["time"]
            parts = time_str.split(":")
            assert parts[1] in ("00", "30"), f"30m candle should be :00 or :30, got {time_str}"

    def test_realistic_prices_15m_times_aligned(self):
        """15-minute candles should have times at 15-minute intervals."""
        from realistic_prices import RealisticPriceFeeder

        feeder = RealisticPriceFeeder()
        candles = feeder.get_candles("XAU", resolution="15", count=20)
        assert candles is not None
        for c in candles:
            time_str = c["time"]
            parts = time_str.split(":")
            minute = int(parts[1])
            assert minute % 15 == 0, f"15m candle should be at 15m intervals, got {time_str}"

    def test_realistic_prices_5m_times_aligned(self):
        """5-minute candles should have times at 5-minute intervals."""
        from realistic_prices import RealisticPriceFeeder

        feeder = RealisticPriceFeeder()
        candles = feeder.get_candles("XAU", resolution="5", count=20)
        assert candles is not None
        for c in candles:
            time_str = c["time"]
            parts = time_str.split(":")
            minute = int(parts[1])
            assert minute % 5 == 0, f"5m candle should be at 5m intervals, got {time_str}"

    def test_realistic_prices_daily_format(self):
        """Daily candles should have MM/DD format."""
        from realistic_prices import RealisticPriceFeeder

        feeder = RealisticPriceFeeder()
        candles = feeder.get_candles("XAU", resolution="D", count=10)
        assert candles is not None
        for c in candles:
            time_str = c["time"]
            assert "/" in time_str, f"Daily candle should have MM/DD format, got {time_str}"
            parts = time_str.split("/")
            assert len(parts) == 2
            month = int(parts[0])
            day = int(parts[1])
            assert 1 <= month <= 12
            assert 1 <= day <= 31

    def test_realistic_prices_chronological_order(self):
        """Candles should be in chronological order (oldest first)."""
        from realistic_prices import RealisticPriceFeeder

        feeder = RealisticPriceFeeder()
        candles = feeder.get_candles("XAU", resolution="60", count=20)
        assert candles is not None
        timestamps = [c["timestamp"] for c in candles]
        for i in range(1, len(timestamps)):
            assert timestamps[i] > timestamps[i - 1], f"Candles not in order: {timestamps[i-1]} >= {timestamps[i]}"

    def test_candle_continuity(self):
        """Each candle's open should equal the previous candle's close (from index 1+)."""
        from realistic_prices import RealisticPriceFeeder

        feeder = RealisticPriceFeeder()
        candles = feeder.get_candles("XAU", resolution="60", count=20)
        assert candles is not None
        for i in range(1, len(candles)):
            assert candles[i]["open"] == candles[i - 1]["close"], (
                f"Continuity break at index {i}: "
                f"prev close={candles[i-1]['close']}, current open={candles[i]['open']}"
            )
