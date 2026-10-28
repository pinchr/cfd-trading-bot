#!/usr/bin/env python3
"""
Sync XAU/XAG from Yahoo Finance to backtest_cache.
"""

import os
import sys
from datetime import datetime
from typing import List, Dict

sys.path.insert(0, 'backend')
from historical_data import fetch_yahoo_historical

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/cfd_trading_bot")


def sync_yahoo(symbol: str, resolution: str = '60', days_back: int = 365):
    """Sync candles for a symbol from Yahoo Finance."""
    from pymongo import MongoClient
    
    client = MongoClient(MONGO_URI)
    db = client.cfd_trading_bot
    
    print(f"Fetching {symbol} {resolution} from Yahoo...")
    
    try:
        # Map resolution to interval
        interval_map = {'60': '1h', '15': '15m', 'D': '1d'}
        interval = interval_map.get(resolution, '1h')
        
        candles = fetch_yahoo_historical(symbol, period_days=days_back, interval=interval)
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
        'source': 'yahoo',
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
    # Sync XAU and XAG from Yahoo
    symbols = [
        ('XAU', '60', 365),
        ('XAU', 'D', 365),
        ('XAG', '60', 365),
        ('XAG', 'D', 365),
        ('US100', '60', 365),
    ]
    
    print("Syncing XAU/XAG/US100 to backtest_cache...")
    print("="*50)
    
    for sym, res, days in symbols:
        sync_yahoo(sym, res, days)
    
    print("="*50)
    print("Done!")
    
    # Verify
    from pymongo import MongoClient
    client = MongoClient(MONGO_URI)
    db = client.cfd_trading_bot
    
    print("\nBacktest cache status:")
    for doc in db.backtest_cache.find():
        print(f"  {doc['symbol']}_{doc['resolution']}: {len(doc['candles'])} candles ({doc.get('source', '?')})")


if __name__ == '__main__':
    main()
