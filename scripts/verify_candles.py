#!/usr/bin/env python3
"""
Verify candle data consistency:
1. No gaps > 20% between consecutive candles
2. 5m candles aggregate correctly to 1h candles
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

sys.path.insert(0, 'backend')
from binance_data import fetch_binance_candles

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/cfd_trading_bot")


def check_price_gaps(candles: List[Dict], max_gap_pct: float = 20.0) -> List[Tuple]:
    """Check for large price gaps between consecutive candles."""
    gaps = []
    for i in range(1, len(candles)):
        prev_close = candles[i-1]['close']
        curr_close = candles[i]['close']
        
        gap_pct = abs(curr_close - prev_close) / prev_close * 100
        
        if gap_pct > max_gap_pct:
            gaps.append((
                i,
                candles[i-1]['timestamp'],
                candles[i]['timestamp'],
                prev_close,
                curr_close,
                gap_pct
            ))
    
    return gaps


def aggregate_5m_to_1h(candles_5m: List[Dict]) -> List[Dict]:
    """Aggregate 5m candles to 1h candles."""
    hourly_bars = {}
    
    for c in candles_5m:
        # Parse timestamp
        ts = c['timestamp']
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        else:
            dt = ts
        
        # Round to hour
        hour_key = dt.replace(minute=0, second=0, microsecond=0)
        
        if hour_key not in hourly_bars:
            hourly_bars[hour_key] = {
                'open': c['open'],
                'high': c['high'],
                'low': c['low'],
                'close': c['close'],
                'volume': c.get('volume', 0),
                'timestamp': hour_key.isoformat(),
                'count': 1
            }
        else:
            bar = hourly_bars[hour_key]
            bar['high'] = max(bar['high'], c['high'])
            bar['low'] = min(bar['low'], c['low'])
            bar['close'] = c['close']
            bar['volume'] += c.get('volume', 0)
            bar['count'] += 1
    
    return list(hourly_bars.values())


def compare_5h_aggregated_with_1h(candles_5m: List[Dict], candles_1h: List[Dict]) -> List[Dict]:
    """Compare 5m-aggregated candles with actual 1h candles."""
    # Aggregate 5m to 1h
    aggregated = aggregate_5m_to_1h(candles_5m)
    
    # Create lookup for 1h candles
    candles_1h_dict = {}
    for c in candles_1h:
        ts = c['timestamp']
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        else:
            dt = ts
        hour_key = dt.replace(minute=0, second=0, microsecond=0)
        candles_1h_dict[hour_key] = c
    
    # Compare
    mismatches = []
    for agg in aggregated:
        agg_ts = datetime.fromisoformat(agg['timestamp'].replace('Z', '+00:00'))
        
        if agg_ts in candles_1h_dict:
            actual = candles_1h_dict[agg_ts]
            
            # Check if prices match within tolerance
            price_tolerance = 0.5  # 0.5% tolerance
            close_diff = abs(agg['close'] - actual['close']) / actual['close'] * 100
            
            if close_diff > price_tolerance:
                mismatches.append({
                    'timestamp': agg['timestamp'],
                    'aggregated_close': agg['close'],
                    'actual_close': actual['close'],
                    'diff_pct': close_diff,
                    'aggregated_count': agg['count']
                })
    
    return mismatches


def verify_symbol(symbol: str, timeframe: str = '5m', days_back: int = 30):
    """Verify candles for a symbol."""
    print(f"\n{'='*60}")
    print(f"Verifying {symbol} {timeframe} - last {days_back} days")
    print(f"{'='*60}")
    
    # Fetch candles from Binance
    end = int(datetime.now().timestamp() * 1000)
    start = end - (days_back * 24 * 60 * 60 * 1000)
    
    print(f"Fetching {symbol} from Binance...")
    candles = fetch_binance_candles(symbol, interval=timeframe, start_time=start, end_time=end, limit=5000)
    
    if not candles:
        print(f"❌ No data fetched")
        return
    
    print(f"Fetched {len(candles)} candles")
    print(f"Period: {candles[0]['timestamp']} -> {candles[-1]['timestamp']}")
    print(f"Price: {candles[0]['close']:.2f} -> {candles[-1]['close']:.2f}")
    
    # Check price gaps
    print(f"\n🔍 Checking for gaps > 20%...")
    gaps = check_price_gaps(candles, max_gap_pct=20.0)
    
    if gaps:
        print(f"❌ Found {len(gaps)} gaps > 20%:")
        for g in gaps[:10]:
            print(f"  [{g[0]}] {g[1]} -> {g[2]}: {g[3]:.2f} -> {g[4]:.2f} ({g[5]:.1f}%)")
    else:
        print(f"✅ No gaps > 20% found")
    
    # Check for 5m vs 1h consistency
    if timeframe == '5m':
        print(f"\n🔍 Fetching 1h candles for comparison...")
        candles_1h = fetch_binance_candles(symbol, interval='1h', start_time=start, end_time=end, limit=2000)
        
        if candles_1h:
            print(f"Fetched {len(candles_1h)} 1h candles")
            
            print(f"\n🔍 Comparing 5m-aggregated vs actual 1h...")
            mismatches = compare_5h_aggregated_with_1h(candles, candles_1h)
            
            if mismatches:
                print(f"❌ Found {len(mismatches)} mismatches:")
                for m in mismatches[:10]:
                    print(f"  {m['timestamp']}: agg={m['aggregated_close']:.2f} vs actual={m['actual_close']:.2f} (diff: {m['diff_pct']:.2f}%)")
            else:
                print(f"✅ 5m aggregates match 1h candles")
        else:
            print(f"⚠️ No 1h data to compare")
    
    return candles


def main():
    symbols = ['BTC', 'XAU', 'XAG']
    
    for symbol in symbols:
        verify_symbol(symbol, timeframe='5m', days_back=30)
    
    print(f"\n{'='*60}")
    print("Verification complete!")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
