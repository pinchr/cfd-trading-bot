#!/usr/bin/env python3
"""
Sync candles from Binance to MongoDB backtest_cache collection.
This collection is separate from candle_cache (used by live trading).
"""

import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict

sys.path.insert(0, 'backend')
from binance_data import fetch_binance_candles

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/cfd_trading_bot")


def sync_symbol(symbol: str, resolution: str = '60', days_back: int = 90):
    """Sync candles for a symbol from Binance."""
    from pymongo import MongoClient
    
    client = MongoClient(MONGO_URI)
    db = client.cfd_trading_bot
    
    # Map resolution to interval
    interval_map = {
        '5': '5m',
        '15': '15m', 
        '30': '30m',
        '60': '1h',
        'D': '1d'
    }
    interval = interval_map.get(resolution, '1h')
    
    # Calculate time range
    end = int(datetime.now().timestamp() * 1000)
    start = end - (days_back * 24 * 60 * 60 * 1000)
    
    limit_map = {'5m': 5000, '15m': 3000, '30m': 2000, '1h': 2000, '1d': 365}
    limit = limit_map.get(interval, 2000)
    
    print(f"Fetching {symbol} {resolution} from Binance...")
    
    try:
        candles = fetch_binance_candles(symbol, interval=interval, start_time=start, end_time=end, limit=limit)
    except Exception as e:
        print(f"  Error: {e}")
        return False
    
    if not candles:
        print(f"  No data returned")
        return False
    
    print(f"  Got {len(candles)} candles")
    
    # Store in backtest_cache collection
    doc = {
        'symbol': symbol,
        'resolution': resolution,
        'source': 'binance',
        'fetched_at': datetime.utcnow().isoformat(),
        'start_date': candles[0]['timestamp'],
        'end_date': candles[-1]['timestamp'],
        'candles': candles
    }
    
    db.backtest_cache.delete_many({'symbol': symbol, 'resolution': resolution})
    db.backtest_cache.insert_one(doc)
    
    print(f"  Saved to backtest_cache: {symbol}_{resolution}")
    return True


def main():
    # Sync BTC and ETH from Binance
    symbols = [
        ('BTC', '60', 90),
        ('BTC', '15', 30),
        ('BTC', '5', 7),
        ('ETH', '60', 90),
        ('ETH', '15', 30),
    ]
    
    print("Syncing candles to backtest_cache...")
    print("="*50)
    
    for sym, res, days in symbols:
        sync_symbol(sym, res, days)
    
    print("="*50)
    print("Done!")
    
    # Verify
    from pymongo import MongoClient
    client = MongoClient(MONGO_URI)
    db = client.cfd_trading_bot
    
    print("\nBacktest cache status:")
    for doc in db.backtest_cache.find():
        print(f"  {doc['symbol']}_{doc['resolution']}: {len(doc['candles'])} candles")


if __name__ == '__main__':
    main()
