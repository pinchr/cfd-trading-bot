"""
Backtest Runner - Batch execution with configuration variants.

Runs backtests with different configurations and saves results to:
- MongoDB: backtest_results collection
- CSV: ~/dev/cfd-trading-bot/backtests/YYYY-MM-DD.csv

Usage:
    python backtest_runner.py --config base                    # Run single config
    python backtest_runner.py --scan min_score                # Scan min_score values
    python backtest_runner.py --scan indicators               # Scan indicator combinations
    python backtest_runner.py --periods 2023,2024,2025        # Multiple years
    python backtest_runner.py --resolutions 15,60             # Multiple timeframes
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Allow passing MONGO_URI via CLI for cron jobs
# Usage: python backtest_runner.py --mongo-uri "mongodb+sr://..."

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from backtester import (
    INSTRUMENT_CONFIG,
    calculate_signal_score,
    get_direction,
    run_backtest,
    results_to_dict,
)
from database import get_db, store_candles
from historical_data import (
    fetch_alpha_vantage_historical,
    fetch_from_db_cache,
    fetch_yahoo_historical,
    load_csv_candles,
)


# ── Configuration Templates ──

CONFIG_PRESETS = {
    "base": {
        "description": "Base configuration - similar to current production",
        "dynamic_positions": False,
        "dynamic_threshold": 0.25,
        "min_score": {"XAU": 0.30, "XAG": 0.28, "US100": 0.20, "BTC": 0.15},
        "min_agreement": {"XAU": 3, "XAG": 3, "US100": 2, "BTC": 2},
        "trailing_stop": True,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "StochRSI", "MACD", "Bollinger", "SMA", "Volume", "Momentum", "Patterns"],
    },
    "dynamic_on": {
        "description": "Base + dynamic positions enabled",
        "dynamic_positions": True,
        "dynamic_threshold": 0.25,
        "min_score": {"XAU": 0.30, "XAG": 0.28, "US100": 0.20, "BTC": 0.15},
        "min_agreement": {"XAU": 3, "XAG": 3, "US100": 2, "BTC": 2},
        "trailing_stop": True,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "StochRSI", "MACD", "Bollinger", "SMA", "Volume", "Momentum", "Patterns"],
    },
    "dynamic_aggressive": {
        "description": "Dynamic positions with lower threshold (close more trades)",
        "dynamic_positions": True,
        "dynamic_threshold": 0.15,
        "min_score": {"XAU": 0.25, "XAG": 0.23, "US100": 0.15, "BTC": 0.10},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": True,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "StochRSI", "MACD", "Bollinger", "SMA", "Volume", "Momentum", "Patterns"],
    },
    "no_rsi": {
        "description": "Without RSI indicator",
        "dynamic_positions": False,
        "dynamic_threshold": 0.25,
        "min_score": {"XAU": 0.30, "XAG": 0.28, "US100": 0.20, "BTC": 0.15},
        "min_agreement": {"XAU": 3, "XAG": 3, "US100": 2, "BTC": 2},
        "trailing_stop": True,
        "risk_per_trade_pct": 2.0,
        "indicators": ["StochRSI", "MACD", "Bollinger", "SMA", "Volume", "Momentum", "Patterns"],
    },
    "momentum_only": {
        "description": "Only momentum-based indicators",
        "dynamic_positions": False,
        "dynamic_threshold": 0.25,
        "min_score": {"XAU": 0.35, "XAG": 0.33, "US100": 0.25, "BTC": 0.20},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": True,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "MACD", "Momentum"],
    },
    "strict": {
        "description": "Strict entry - higher min_score, more agreement required",
        "dynamic_positions": False,
        "dynamic_threshold": 0.25,
        "min_score": {"XAU": 0.40, "XAG": 0.38, "US100": 0.30, "BTC": 0.25},
        "min_agreement": {"XAU": 4, "XAG": 4, "US100": 3, "BTC": 3},
        "trailing_stop": True,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "StochRSI", "MACD", "Bollinger", "SMA", "Volume", "Momentum", "Patterns"],
    },
    # NEW CONFIGS - BTC focused (BTC needs HIGHER min_score due to volatility)
    "btc_focused": {
        "description": "BTC focused - stricter for high volatility",
        "dynamic_positions": True,
        "dynamic_threshold": 0.25,
        "min_score": {"XAU": 0.30, "XAG": 0.28, "US100": 0.20, "BTC": 0.28},
        "min_agreement": {"XAU": 3, "XAG": 3, "US100": 2, "BTC": 3},
        "trailing_stop": True,
        "risk_per_trade_pct": 1.0,  # Lower risk for BTC
        "indicators": ["RSI", "StochRSI", "MACD", "Bollinger", "SMA", "Volume", "Momentum", "Patterns"],
    },
    "scalp": {
        "description": "Scalping config - more trades, shorter holds",
        "dynamic_positions": True,
        "dynamic_threshold": 0.15,
        "min_score": {"XAU": 0.20, "XAG": 0.20, "US100": 0.15, "BTC": 0.15},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": False,
        "risk_per_trade_pct": 1.0,
        "indicators": ["RSI", "MACD", "Bollinger"],
    },
    "scalp_aggressive": {
        "description": "Aggressive scalping - more trades",
        "dynamic_positions": True,
        "dynamic_threshold": 0.10,
        "min_score": {"XAU": 0.15, "XAG": 0.15, "US100": 0.12, "BTC": 0.12},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": False,
        "risk_per_trade_pct": 0.5,
        "indicators": ["RSI", "MACD", "Bollinger"],
    },
    "btc_conservative": {
        "description": "BTC conservative - higher min_score, less trades",
        "dynamic_positions": False,
        "dynamic_threshold": 0.25,
        "min_score": {"XAU": 0.30, "XAG": 0.28, "US100": 0.20, "BTC": 0.25},
        "min_agreement": {"XAU": 3, "XAG": 3, "US100": 2, "BTC": 3},
        "trailing_stop": True,
        "risk_per_trade_pct": 1.0,
        "indicators": ["RSI", "StochRSI", "MACD", "Bollinger", "SMA", "Volume", "Momentum", "Patterns"],
    },
    "us100_focused": {
        "description": "US100/Nasdaq focused - balanced for indices",
        "dynamic_positions": True,
        "dynamic_threshold": 0.25,
        "min_score": {"XAU": 0.30, "XAG": 0.28, "US100": 0.22, "BTC": 0.28},
        "min_agreement": {"XAU": 3, "XAG": 3, "US100": 2, "BTC": 3},
        "trailing_stop": True,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "StochRSI", "MACD", "Bollinger", "SMA", "Volume", "Momentum", "Patterns"],
    },
    "xag_focused": {
        "description": "Silver focused - different params for commodities",
        "dynamic_positions": True,
        "dynamic_threshold": 0.20,
        "min_score": {"XAU": 0.30, "XAG": 0.20, "US100": 0.20, "BTC": 0.15},
        "min_agreement": {"XAU": 3, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": True,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "StochRSI", "MACD", "Bollinger", "SMA", "Volume", "Momentum", "Patterns"],
    },
    # JSON STRATEGIES from strategies.json - FIXED min_score to reasonable values
    "btc_v2_core": {
        "description": "JSON: BTC v2 Core 5m - RSI/MACD/Momentum/ADX",
        "dynamic_positions": True,
        "dynamic_threshold": 0.20,
        "min_score": {"XAU": 0.25, "XAG": 0.25, "US100": 0.20, "BTC": 0.15},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": False,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "MACD", "Momentum", "ADX"],
    },
    "btc_v2_safe": {
        "description": "JSON: BTC v2 Safe 5m - conservative version",
        "dynamic_positions": True,
        "dynamic_threshold": 0.25,
        "min_score": {"XAU": 0.30, "XAG": 0.30, "US100": 0.25, "BTC": 0.20},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": True,
        "risk_per_trade_pct": 1.5,
        "indicators": ["RSI", "MACD", "Momentum", "ADX"],
    },
    "xau_v2_momentum": {
        "description": "JSON: XAU v2 Momentum 5m - gold momentum strategy",
        "dynamic_positions": True,
        "dynamic_threshold": 0.20,
        "min_score": {"XAU": 0.15, "XAG": 0.25, "US100": 0.20, "BTC": 0.20},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": False,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "MACD", "Momentum", "ADX"],
    },
    "btc_v3_exp": {
        "description": "JSON: BTC v3 Experimental - RSI/Momentum only",
        "dynamic_positions": True,
        "dynamic_threshold": 0.20,
        "min_score": {"XAU": 0.25, "XAG": 0.25, "US100": 0.20, "BTC": 0.15},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": False,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "Momentum"],
    },
    "xau_v3_exp": {
        "description": "JSON: XAU v3 Experimental - RSI/Momentum only",
        "dynamic_positions": True,
        "dynamic_threshold": 0.20,
        "min_score": {"XAU": 0.15, "XAG": 0.25, "US100": 0.20, "BTC": 0.20},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": False,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "Momentum"],
    },
    "xag_v3_exp": {
        "description": "JSON: XAG v3 Experimental - RSI/Momentum only",
        "dynamic_positions": True,
        "dynamic_threshold": 0.20,
        "min_score": {"XAU": 0.25, "XAG": 0.15, "US100": 0.20, "BTC": 0.20},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": False,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "Momentum"],
    },
    "xau_scalp_trend": {
        "description": "JSON: XAU Scalp Trend 5m - RSI/MAC/Momentum",
        "dynamic_positions": True,
        "dynamic_threshold": 0.15,
        "min_score": {"XAU": 0.15, "XAG": 0.25, "US100": 0.20, "BTC": 0.20},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": False,
        "risk_per_trade_pct": 1.0,
        "indicators": ["RSI", "MACD", "Momentum"],
    },
    "btc_scalp_trend": {
        "description": "JSON: BTC Scalp Trend 5m - RSI/MAC/Momentum",
        "dynamic_positions": True,
        "dynamic_threshold": 0.15,
        "min_score": {"XAU": 0.25, "XAG": 0.25, "US100": 0.20, "BTC": 0.15},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": False,
        "risk_per_trade_pct": 1.0,
        "indicators": ["RSI", "MACD", "Momentum"],
    },
    # HTF Divergence Test Strategy - with DIVERGENCE and HTF_CANDLE indicators
    "htf_divergence_test": {
        "description": "TEST: HTF Candle Patterns + RSI Divergence strategy",
        "dynamic_positions": True,
        "dynamic_threshold": 0.15,
        "min_score": {"XAU": 0.10, "XAG": 0.10, "US100": 0.10, "BTC": 0.10},
        "min_agreement": {"XAU": 2, "XAG": 2, "US100": 2, "BTC": 2},
        "trailing_stop": False,
        "risk_per_trade_pct": 2.0,
        "indicators": ["RSI", "MACD", "Momentum", "DIVERGENCE", "HTF_CANDLE"],
    },
}


# ── Period Definitions ──

PERIODS = {
    "2023": {"start": "2023-01-01", "end": "2023-12-31"},
    "2024": {"start": "2024-01-01", "end": "2024-12-31"},
    "2025": {"start": "2025-01-01", "end": "2025-12-31"},
    "2025_H1": {"start": "2025-01-01", "end": "2025-06-30"},
    "2025_H2": {"start": "2025-07-01", "end": "2025-12-31"},
    "2024_H2": {"start": "2024-07-01", "end": "2024-12-31"},
    "2023_H1": {"start": "2023-01-01", "end": "2023-06-30"},
    "all": {"start": "2025-01-01", "end": "2026-12-31"},  # All available data
    "recent": {"start": "2026-01-01", "end": "2026-12-31"},  # Recent data only
}


# ── Backtest Result Storage ──


def save_to_db(result: Dict, config: Dict, period: str, resolution: str) -> str:
    """Save backtest result to MongoDB."""
    db = get_db()
    if db is None:
        print("  [DB] Not connected - skipping MongoDB save")
        return ""
    
    doc = {
        "_id": f"bt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{config.get('name', 'unknown')}",
        "run_at": datetime.now().isoformat(),
        "config": config,
        "period": period,
        "resolution": resolution,
        "results": result,
    }
    
    try:
        db.backtest_results.insert_one(doc)
        print(f"  [DB] Saved to backtest_results: {doc['_id']}")
        return doc["_id"]
    except Exception as e:
        print(f"  [DB] Error saving: {e}")
        return ""


def save_to_csv(results: List[Dict], output_dir: Path):
    """Save aggregated results to CSV for easy sorting/analysis."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d")
    csv_path = output_dir / f"backtests_{timestamp}.csv"
    
    # Also save all-time results
    all_time_path = output_dir / "backtests_all.csv"
    
    # Data quality info per symbol (for CSV)
    DATA_QUALITY = {
        ("XAU", "60"): {"status": "GOOD", "candles": 85008, "period": "1 year"},
        ("XAU", "15"): {"status": "GOOD", "candles": 3736, "period": "1 month"},
        ("XAU", "5"): {"status": "GOOD", "candles": 11057, "period": "1 month"},
        ("XAG", "60"): {"status": "GOOD", "candles": 4113, "period": "5 months"},
        ("XAG", "15"): {"status": "GOOD", "candles": 3750, "period": "1 month"},
        ("XAG", "5"): {"status": "GOOD", "candles": 6015, "period": "1 month"},
        ("BTC", "60"): {"status": "LIMITED", "candles": 7063, "period": "~1 month"},
        ("BTC", "15"): {"status": "LIMITED", "candles": 6195, "period": "~1 month"},
        ("BTC", "5"): {"status": "LIMITED", "candles": 8319, "period": "~1 month"},
        ("US100", "60"): {"status": "BAD", "candles": 102220, "period": "~10 days"},
        ("US100", "15"): {"status": "BAD", "candles": 2118, "period": "~1 month"},
        ("US100", "5"): {"status": "BAD", "candles": 6253, "period": "~1 month"},
    }
    
    # Flatten results for CSV
    rows = []
    for r in results:
        config = r.get("config", {})
        for symbol, symbol_result in r.get("results", {}).items():
            initial_balance = 10000.0
            total_return = symbol_result.get("total_return_pct", 0)
            final_balance = initial_balance * (1 + total_return / 100)
            
            # Calculate profit after N days from equity curve
            profit_30d = None
            profit_60d = None
            profit_90d = None
            
            # Try to get equity curve from individual backtest result
            equity_curve = r.get("equity_curve", [])
            if equity_curve and len(equity_curve) > 30:
                candles_per_day = 24 if r.get("resolution") == "60" else (4 if r.get("resolution") == "D" else 24)
                idx_30 = min(30 * candles_per_day, len(equity_curve) - 1)
                idx_60 = min(60 * candles_per_day, len(equity_curve) - 1)
                idx_90 = min(90 * candles_per_day, len(equity_curve) - 1)
                profit_30d = round(equity_curve[idx_30] - initial_balance, 2) if idx_30 > 0 else None
                profit_60d = round(equity_curve[idx_60] - initial_balance, 2) if idx_60 > 0 else None
                profit_90d = round(equity_curve[idx_90] - initial_balance, 2) if idx_90 > 0 else None
            
            row = {
                "run_id": r.get("run_id", ""),
                "run_at": r.get("run_at", ""),
                "config_name": config.get("name", ""),
                "config_description": config.get("description", ""),
                "period": r.get("period", ""),
                "timeframe": f"{r.get('resolution', '')}m",
                "dynamic_positions": config.get("dynamic_positions", False),
                "dynamic_threshold": config.get("dynamic_threshold", 0.25),
                "min_score": config.get("min_score", {}).get(symbol, ""),
                "indicators": ",".join(config.get("indicators", [])),
                "symbol": symbol,
                "initial_balance": initial_balance,
                "final_balance": round(final_balance, 2),
                "profit_30d": profit_30d,
                "profit_60d": profit_60d,
                "profit_90d": profit_90d,
                "total_trades": symbol_result.get("total_trades", 0),
                "winning_trades": symbol_result.get("winning_trades", 0),
                "losing_trades": symbol_result.get("losing_trades", 0),
                "neutral_skipped": symbol_result.get("neutral_skipped", 0),
                "total_signals": symbol_result.get("total_signals", 0),
                "win_rate": symbol_result.get("win_rate", 0),
                "avg_win_pct": symbol_result.get("avg_win_pct", 0),
                "avg_loss_pct": symbol_result.get("avg_loss_pct", 0),
                "total_return_pct": symbol_result.get("total_return_pct", 0),
                "max_drawdown_pct": symbol_result.get("max_drawdown_pct", 0),
                "profit_factor": symbol_result.get("profit_factor", 0),
                "sharpe_approx": symbol_result.get("sharpe_approx", 0),
            }
            
            # Add data quality info
            timeframe_key = r.get("resolution", "")
            quality = DATA_QUALITY.get((symbol, timeframe_key), {"status": "UNKNOWN", "candles": 0, "period": "unknown"})
            row["data_status"] = quality["status"]
            row["data_candles"] = quality["candles"]
            row["data_period"] = quality["period"]
            
            rows.append(row)
    
    if not rows:
        print("  [CSV] No results to save")
        return None
    
    # Write CSV - define fieldnames explicitly
    import csv
    
    fieldnames = [
        "run_id", "run_at", "config_name", "config_description", "period", "timeframe",
        "data_status", "data_candles", "data_period",
        "dynamic_positions", "dynamic_threshold", "min_score", "indicators", "symbol",
        "initial_balance", "final_balance", "profit_30d", "profit_60d", "profit_90d",
        "total_trades", "winning_trades", "losing_trades", "neutral_skipped", "total_signals",
        "win_rate", "avg_win_pct", "avg_loss_pct", "total_return_pct", "max_drawdown_pct",
        "profit_factor", "sharpe_approx"
    ]
    
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    
    print(f"  [CSV] Saved {len(rows)} rows to {csv_path}")
    
    # Append to all-time CSV
    existing_rows = []
    if all_time_path.exists() and all_time_path.stat().st_size > 0:
        with open(all_time_path, "r") as f:
            reader = csv.DictReader(f)
            existing_rows = list(reader)
    
    # Deduplicate by run_id
    existing_ids = {r.get("run_id", "") for r in existing_rows}
    new_rows = [r for r in rows if r.get("run_id", "") not in existing_ids]
    
    if new_rows:
        with open(all_time_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            # Write header if file is empty
            if all_time_path.stat().st_size == 0:
                writer.writeheader()
            writer.writerows(new_rows)
        print(f"  [CSV] Appended {len(new_rows)} new rows to {all_time_path}")
    
    return csv_path, all_time_path


# Valid symbols/resolutions for ranking (clean data only)
VALID_FOR_RANKING = {
    ("XAU", "60"): "Full year clean data",
    ("XAG", "60"): "Full year clean data", 
    ("BTC", "60"): "~1 month clean data (limited)",
    ("XAU", "15"): "Recent clean data",
    ("XAG", "15"): "Recent clean data",
    ("BTC", "15"): "Recent clean data",
    ("XAU", "5"): "Recent clean data",
    ("XAG", "5"): "Recent clean data",
    ("BTC", "5"): "Recent clean data",
}


def get_summary_stats(csv_path: Path) -> Dict:
    """Get summary statistics from CSV results - ONLY clean data."""
    import csv
    
    if not csv_path or not csv_path.exists():
        return {}
    
    rows = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    if not rows:
        return {}
    
    # Filter to valid symbols only (exclude bad data)
    # Convert string values to proper types
    valid_rows = []
    excluded = 0
    for r in rows:
        # Convert numeric fields from string to proper type
        r["total_trades"] = int(float(r.get("total_trades", 0))) if r.get("total_trades") else 0
        r["win_rate"] = float(r.get("win_rate", 0)) if r.get("win_rate") else 0.0
        r["total_return_pct"] = float(r.get("total_return_pct", 0)) if r.get("total_return_pct") else 0.0
        
        symbol = r.get("symbol", "")
        timeframe = r.get("timeframe", "").replace("m", "")
        trades = r.get("total_trades", 0)
        
        # Check if this is valid clean data
        if (symbol, timeframe) in VALID_FOR_RANKING:
            # Also exclude unrealistic trade counts (>500 = too many)
            if trades > 500:
                excluded += 1
                continue
            valid_rows.append(r)
        else:
            excluded += 1
    
    if excluded > 0:
        print(f"  [INFO] Excluded {excluded} rows with bad/incomplete data from ranking")
    
    rows = valid_rows
    
    # Group by config_name
    configs = {}
    for r in rows:
        name = r.get("config_name", "unknown")
        if name not in configs:
            configs[name] = []
        configs[name].append(r)
    
    # Calculate stats per config
    config_stats = []
    for name, results in configs.items():
        returns = [float(r.get("total_return_pct", 0)) for r in results]
        profits_30d = [float(r["profit_30d"]) for r in results if r.get("profit_30d") and r["profit_30d"] != ""]
        profits_60d = [float(r["profit_60d"]) for r in results if r.get("profit_60d") and r["profit_60d"] != ""]
        trades = [int(r.get("total_trades", 0)) for r in results]
        
        avg_return = sum(returns) / len(returns) if returns else 0
        avg_profit_30d = sum(profits_30d) / len(profits_30d) if profits_30d else None
        avg_profit_60d = sum(profits_60d) / len(profits_60d) if profits_60d else None
        total_trades = sum(trades)
        
        config_stats.append({
            "name": name,
            "runs": len(results),
            "avg_return_pct": round(avg_return, 2),
            "avg_profit_30d": round(avg_profit_30d, 2) if avg_profit_30d else None,
            "avg_profit_60d": round(avg_profit_60d, 2) if avg_profit_60d else None,
            "total_trades": total_trades,
        })
    
    # Sort by avg return
    config_stats.sort(key=lambda x: x["avg_return_pct"], reverse=True)
    
    return {
        "total_configs_tested": len(configs),
        "total_runs": len(rows),
        "top_configs": config_stats[:3],
        "all_configs": config_stats,
    }


# ── Data Fetching with Validation ──


def fetch_candles_for_period(
    symbol: str,
    resolution: str,
    start_date: str,
    end_date: str,
) -> Optional[List[Dict]]:
    """Fetch candles for a specific period, with validation."""
    db = get_db()
    
    # Try backtest_cache first (fresh sync from Binance/Yahoo)
    if db is not None:
        backtest_doc = db.backtest_cache.find_one({"symbol": symbol, "resolution": resolution})
        if backtest_doc and backtest_doc.get("candles"):
            candles = backtest_doc["candles"]
            # Filter by date range
            candles = [c for c in candles if start_date <= c.get("timestamp", "") <= end_date]
            if len(candles) >= 50:
                print(f"    {symbol} {resolution}: {len(candles)} candles from backtest_cache ({backtest_doc.get('source', '?')})")
                return candles
    
    # Fall back to original logic
    if db is not None:
        # First try exact resolution
        candles = list(db.candles.find({
            "symbol": symbol,
            "resolution": resolution,
            "timestamp": {"$gte": start_date, "$lte": end_date}
        }).sort("timestamp", 1))
        
        if candles and len(candles) >= 50:
            if validate_candle_data(candles):
                print(f"    {symbol} {resolution}: {len(candles)} candles from DB")
                return candles
        
        # Try to aggregate from smaller resolutions
        source_resolutions = {
            "60": ["15", "5", "1"],
            "15": ["5", "1"],
            "5": ["1"],
        }
        
        for src_res in source_resolutions.get(resolution, []):
            candles = list(db.candles.find({
                "symbol": symbol,
                "resolution": src_res,
                "timestamp": {"$gte": start_date, "$lte": end_date}
            }).sort("timestamp", 1))
            
            if candles and len(candles) >= 50:
                # Aggregate to target resolution
                from database import aggregate_candles
                aggregated = aggregate_candles(candles, resolution)
                if aggregated and len(aggregated) >= 50:
                    if validate_candle_data(aggregated):
                        print(f"    {symbol} {resolution}: {len(aggregated)} candles (aggregated from {src_res}m)")
                        return aggregated
        
        # Try D resolution for any period
        if resolution != "D":
            candles = list(db.candles.find({
                "symbol": symbol,
                "resolution": "D",
                "timestamp": {"$gte": start_date, "$lte": end_date}
            }).sort("timestamp", 1))
            
            if candles and len(candles) >= 30:
                if validate_candle_data(candles):
                    print(f"    {symbol} {resolution}: Using {len(candles)} daily candles from DB")
                    return candles
    
    # Fallback: try Yahoo for recent data only (last 60 days)
    print(f"    {symbol} {resolution}: DB has limited data, trying Yahoo (recent only)...")
    candles = fetch_yahoo_historical(symbol, period_days=60, interval="1d" if resolution == "D" else f"{resolution}m")
    
    if candles:
        candles = [c for c in candles if start_date <= c.get("timestamp", "").split("T")[0] <= end_date]
        if candles and len(candles) >= 30:
            if validate_candle_data(candles):
                print(f"    {symbol} {resolution}: {len(candles)} candles from Yahoo (recent)")
                return candles
    
    print(f"    {symbol} {resolution}: No valid data for period {start_date} - {end_date}")
    return None


def validate_candle_data(candles: List[Dict]) -> bool:
    """Validate candle data for anomalies/gaps."""
    if not candles or len(candles) < 10:
        return False
    
    prices = [c.get("close", 0) for c in candles if c.get("close", 0) > 0]
    if not prices:
        return False
    
    # Check for unrealistic gaps (>50% between consecutive candles - allow for weekends/holidays)
    for i in range(1, len(candles)):
        prev_ts = candles[i-1].get("timestamp", "")
        curr_ts = candles[i].get("timestamp", "")
        
        # Skip if gap is more than 24h (weekend/holiday)
        if "T" in prev_ts and "T" in curr_ts:
            from datetime import datetime
            try:
                prev_dt = datetime.fromisoformat(prev_ts.replace("Z", "+00:00"))
                curr_dt = datetime.fromisoformat(curr_ts.replace("Z", "+00:00"))
                hours_diff = (curr_dt - prev_dt).total_seconds() / 3600
                if hours_diff > 36:  # Weekend/holiday
                    continue
            except:
                pass
        
        prev = candles[i-1].get("close", 0)
        curr = candles[i].get("close", 0)
        if prev > 0:
            change = abs((curr - prev) / prev) * 100
            if change > 50:  # 50% intraday gap is unrealistic
                print(f"      ⚠️  Gap detected: {change:.1f}% at {curr_ts}")
                return False
    
    # Check for zero/invalid prices
    if any(c.get("close", 0) <= 0 or c.get("open", 0) <= 0 for c in candles):
        print(f"      ⚠️  Invalid prices (zero or negative)")
        return False
    
    return True


# ── Backtest Execution ──


def run_single_backtest(
    symbol: str,
    config: Dict,
    period: str,
    resolution: str = "60",
    verbose: bool = False,
) -> Optional[Dict]:
    """Run a single backtest for one symbol with given config."""
    
    # Get period dates
    period_info = PERIODS.get(period, PERIODS.get(period.split("_")[0], {"start": "2025-01-01", "end": "2025-12-31"}))
    if isinstance(period_info, str):  # Handle "2025_H1" format
        period_info = PERIODS.get(period, {"start": "2025-01-01", "end": "2025-12-31"})
    
    start_date = period_info.get("start", "2025-01-01")
    end_date = period_info.get("end", "2025-12-31")
    
    # Fetch data
    candles = fetch_candles_for_period(symbol, resolution, start_date, end_date)
    if not candles:
        return None
    
    # Prepare config for this symbol
    symbol_config = INSTRUMENT_CONFIG.get(symbol, {}).copy()
    symbol_config["min_score"] = config.get("min_score", {}).get(symbol, 0.15)
    symbol_config["min_agreement"] = config.get("min_agreement", {}).get(symbol, 2)
    symbol_config["trailing_stop"] = config.get("trailing_stop", True)
    
    # Override global INSTRUMENT_CONFIG temporarily
    original = INSTRUMENT_CONFIG.get(symbol, {}).copy()
    INSTRUMENT_CONFIG[symbol] = symbol_config
    
    # Always use analyze_with_new_strategy() - it will fallback to traditional scoring 
    # only if no strategy is found for the symbol
    config_name = config.get('name', '')
    json_strategy_prefixes = ('btc_v2_', 'btc_v3_', 'xau_v2_', 'xau_v3_', 'xag_v3_', 'xau_scalp_', 'btc_scalp_', 'htf_divergence_')
    use_unified = True  # Always try unified strategy first
    
    # Extract base strategy ID from config name (e.g., "btc_v3_exp_base" -> "btc_v3_exp")
    if use_unified:
        for prefix in json_strategy_prefixes:
            if config_name.startswith(prefix):
                # Find where suffix starts (_base, _dynamic_on, etc.)
                strategy_id = config_name
                for suffix in ('_base', '_dynamic_on', '_scalp', '_btc_focused', '_no_rsi'):
                    if config_name.endswith(suffix):
                        strategy_id = config_name[:-len(suffix)]
                        break
                break
        else:
            strategy_id = config_name
    else:
        strategy_id = None
    
    try:
        # Run backtest (without HTF for speed, can add later)
        # Use analyze_with_new_strategy() for JSON strategy configs
        result = run_backtest(
            candles,
            symbol=symbol,
            initial_balance=10000.0,
            risk_per_trade_pct=config.get("risk_per_trade_pct", 2.0),
            max_concurrent=1,
            verbose=verbose,
            htf_candles=None,  # Skip HTF for speed
            use_unified_strategy=use_unified,
            strategy_id=strategy_id,
        )
        
        # Add config info to result
        result_dict = results_to_dict(result)
        result_dict["config_applied"] = {
            "min_score": symbol_config["min_score"],
            "min_agreement": symbol_config["min_agreement"],
            "trailing_stop": symbol_config["trailing_stop"],
        }
        # Add equity curve for profit calculations
        result_dict["equity_curve"] = result.equity_curve
        
        return result_dict
        
    finally:
        # Restore original config
        INSTRUMENT_CONFIG[symbol] = original


def run_full_backtest(
    config: Dict,
    symbols: List[str],
    period: str,
    resolution: str = "60",
    verbose: bool = False,
) -> Dict:
    """Run backtest for multiple symbols with same config."""
    
    results = {}
    all_trades = []
    equity_curve = []
    
    print(f"\n  Running backtest: {config.get('name', 'unknown')} | {period} | {resolution}m")
    
    for symbol in symbols:
        result = run_single_backtest(symbol, config, period, resolution, verbose)
        if result:
            results[symbol] = {
                "total_trades": result["total_trades"],
                "winning_trades": result["winning_trades"],
                "losing_trades": result["losing_trades"],
                "win_rate": result["win_rate"],
                "avg_win_pct": result["avg_win_pct"],
                "avg_loss_pct": result["avg_loss_pct"],
                "total_return_pct": result["total_return_pct"],
                "max_drawdown_pct": result["max_drawdown_pct"],
                "profit_factor": result["profit_factor"],
                "sharpe_approx": result["sharpe_approx"],
                "neutral_skipped": result["neutral_skipped"],
                "total_signals": result["total_signals"],
            }
            all_trades.extend(result.get("trades", []))
            # Use first symbol's equity curve for profit calculations
            if not equity_curve and result.get("equity_curve"):
                equity_curve = result["equity_curve"]
        else:
            results[symbol] = {"error": "No data or validation failed"}
    
    return {
        "config": config,
        "period": period,
        "resolution": resolution,
        "results": results,
        "total_trades": sum(r.get("total_trades", 0) for r in results.values() if "error" not in r),
        "trades": all_trades,
        "equity_curve": equity_curve,
    }


# ── Scanner Functions ──


def scan_min_score_values(
    symbols: List[str],
    base_config: Dict,
    period: str,
    resolution: str,
) -> List[Dict]:
    """Scan different min_score values."""
    results = []
    
    # Test base config first
    base_config["name"] = "base"
    results.append(run_full_backtest(base_config, symbols, period, resolution))
    
    # Scan different min_score levels
    for multiplier in [0.75, 1.25, 1.5]:
        config = base_config.copy()
        config["name"] = f"min_score_{multiplier}x"
        config["min_score"] = {
            symbol: round(base_config["min_score"][symbol] * multiplier, 2)
            for symbol in symbols
        }
        results.append(run_full_backtest(config, symbols, period, resolution))
    
    return results


def scan_indicator_combinations(
    symbols: List[str],
    base_config: Dict,
    period: str,
    resolution: str,
) -> List[Dict]:
    """Scan different indicator combinations."""
    results = []
    
    indicator_sets = {
        "all": ["RSI", "StochRSI", "MACD", "Bollinger", "SMA", "Volume", "Momentum", "Patterns"],
        "no_rsi": ["StochRSI", "MACD", "Bollinger", "SMA", "Volume", "Momentum", "Patterns"],
        "no_stoch": ["RSI", "MACD", "Bollinger", "SMA", "Volume", "Momentum", "Patterns"],
        "momentum_only": ["RSI", "MACD", "Momentum"],
        "simple": ["RSI", "MACD", "SMA"],
    }
    
    for name, indicators in indicator_sets.items():
        config = base_config.copy()
        config["name"] = name
        config["indicators"] = indicators
        results.append(run_full_backtest(config, symbols, period, resolution))
    
    return results


# ── Main ──


def main():
    parser = argparse.ArgumentParser(description="Backtest Runner - Batch execution with config variants")
    parser.add_argument("--config", default="base", help="Config preset to use")
    parser.add_argument("--symbols", default="XAU,XAG,US100", help="Comma-separated symbols")
    parser.add_argument("--period", default="2025", help="Period: 2023, 2024, 2025, 2025_H1, etc.")
    parser.add_argument("--periods", default="", help="Comma-separated periods for multi-period run")
    parser.add_argument("--resolution", default="60", help="Resolution in minutes: 15, 60, etc.")
    parser.add_argument("--resolutions", default="", help="Comma-separated resolutions for multi-resolution run")
    parser.add_argument("--scan", choices=["min_score", "indicators", "all"], help="Scan mode")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show individual trades")
    parser.add_argument("--mongo-uri", default=None, help="MongoDB URI (optional, for backtest data)")
    parser.add_argument("--output-dir", default="~/dev/cfd-trading-bot/backtests", help="Output directory for CSVs")
    
    args = parser.parse_args()
    
    # Set MONGO_URI from CLI if provided (for cron jobs)
    if args.mongo_uri:
        os.environ["MONGO_URI"] = args.mongo_uri
        print(f"[INFO] MONGO_URI set from CLI")
    
    # Enable backtest mode - relaxes some filters for historical data
    os.environ["BACKTEST_MODE"] = "1"
    
    symbols = args.symbols.split(",")
    base_config = CONFIG_PRESETS.get(args.config, CONFIG_PRESETS["base"]).copy()
    base_config["name"] = args.config
    
    output_dir = Path(args.output_dir).expanduser()
    all_results = []
    
    # Determine periods to run
    periods = args.periods.split(",") if args.periods else [args.period]
    periods = [p for p in periods if p]
    
    # Determine resolutions to run
    resolutions = args.resolutions.split(",") if args.resolutions else [args.resolution]
    resolutions = [r for r in resolutions if r]
    
    print(f"\n{'='*60}")
    print(f"  BACKTEST RUNNER")
    print(f"  Config: {args.config}")
    print(f"  Symbols: {symbols}")
    print(f"  Periods: {periods}")
    print(f"  Resolutions: {resolutions}")
    print(f"{'='*60}")
    
    for period in periods:
        for resolution in resolutions:
            if args.scan == "min_score":
                results = scan_min_score_values(symbols, base_config, period, resolution)
            elif args.scan == "indicators":
                results = scan_indicator_combinations(symbols, base_config, period, resolution)
            elif args.scan == "all":
                # Run all presets
                results = []
                for preset_name, preset_config in CONFIG_PRESETS.items():
                    config = preset_config.copy()
                    config["name"] = preset_name
                    results.append(run_full_backtest(config, symbols, period, resolution))
            else:
                # Single config run
                results = [run_full_backtest(base_config, symbols, period, resolution)]
            
            # Add run metadata
            for r in results:
                r["run_id"] = save_to_db(r.get("results", {}), r.get("config", {}), period, resolution)
                r["run_at"] = datetime.now().isoformat()
                all_results.append(r)
    
    # Save aggregated CSV
    if all_results:
        csv_path, all_time_path = save_to_csv(all_results, output_dir)
        
        # Get summary stats from all-time CSV
        summary = get_summary_stats(all_time_path)
        
        print(f"\n{'='*60}")
        print(f"  SUMMARY")
        print(f"{'='*60}")
        
        # Print overall stats
        if summary:
            print(f"\n  Total configs tested: {summary.get('total_configs_tested', 0)}")
            print(f"  Total runs: {summary.get('total_runs', 0)}")
            
            # Top 3 configs
            top_configs = summary.get("top_configs", [])
            if top_configs:
                print(f"\n  🏆 Top 3 Configs (by avg return):")
                for i, c in enumerate(top_configs, 1):
                    p30 = f"${c.get('avg_profit_30d', 'N/A')}" if c.get("avg_profit_30d") else "N/A"
                    p60 = f"${c.get('avg_profit_60d', 'N/A')}" if c.get("avg_profit_60d") else "N/A"
                    print(f"    {i}. {c['name']}: {c['avg_return_pct']:+.2f}% avg | 30d: {p30} | 60d: {p60} | {c['total_trades']} trades")
        
        # Print this run's table
        print(f"\n  This run:")
        print(f"\n  {'Config':<20} {'Period':<10} {'Res':<5} {'Trades':<7} {'Win%':<7} {'Return':<10} {'DD%':<7} {'PF':<6}")
        print(f"  {'-'*75}")
        
        for r in all_results:
            config_name = r.get("config", {}).get("name", "unknown")[:18]
            period = r.get("period", "")[:8]
            res = str(r.get("resolution", ""))
            
            total_trades = 0
            total_return = 0
            
            for symbol, sr in r.get("results", {}).items():
                if "error" not in sr:
                    total_trades += sr.get("total_trades", 0)
                    total_return += sr.get("total_return_pct", 0)
            
            win_rate = sum(sr.get("win_rate", 0) for sr in r.get("results", {}).values() if "error" not in sr)
            win_rate = win_rate / max(1, len([s for s in r.get("results", {}).values() if "error" not in s]))
            
            return_pct = total_return / max(1, len(symbols))
            
            print(f"  {config_name:<20} {period:<10} {res:<5} {total_trades:<7} {win_rate:>5.1f}% {return_pct:>+9.1f}%")
        
        print(f"\n  Results saved to: {csv_path}")
        print(f"  All-time results: {all_time_path}")
    else:
        print("\n  No results to display")


if __name__ == "__main__":
    main()
