"""
Binance Historical Data Sync
- Fetches candles from Binance for all resolutions
- Normalizes to match our candle format
- Stores in separate collection for comparison
"""
import os
import requests
from datetime import datetime
import time
from pymongo import MongoClient

BINANCE_BASE = "https://api.binance.com/api/v3"

# Map our resolutions to Binance intervals
RESOLUTION_MAP = {
    "1": "1m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "1h",
    "240": "4h",
    "D": "1d",
}

SYMBOL_MAP = {
    "XAU": "PAXGUSDT",  # PAX Gold (tokenized gold)
    "XAG": "PAXGUSDT",  # Silver - use PAXG for now or skip
    "BTC": "BTCUSDT",
    "ETH": "ETHUSDT",
}

# Use same DB but separate collection
BINANCE_DB = "cfd_trading_bot"
BINANCE_COLLECTION = "binance_candles"


def get_mongo_client():
    """Get MongoDB client"""
    mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/cfd_trading_bot")
    return MongoClient(
        mongo_uri,
        serverSelectionTimeoutMS=10000,
        tlsAllowInvalidCertificates=True,
    )


def get_binance_symbol(symbol: str) -> str:
    return SYMBOL_MAP.get(symbol, f"{symbol}USDT")


def fetch_binance_candles(symbol: str, interval: str, start_time: int = None, end_time: int = None, limit: int = 1000):
    """Fetch candles from Binance API"""
    binance_symbol = get_binance_symbol(symbol)
    
    url = f"{BINANCE_BASE}/klines"
    params = {
        "symbol": binance_symbol,
        "interval": interval,
        "limit": limit,
    }
    
    if start_time:
        params["startTime"] = start_time
    if end_time:
        params["endTime"] = end_time
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        candles = []
        for c in data:
            # Binance: [openTime, open, high, low, close, volume, closeTime, ...]
            ts = int(c[0])
            dt = datetime.utcfromtimestamp(ts / 1000)
            
            candles.append({
                "timestamp": dt.isoformat() + "Z",
                "time": int(ts / 1000),  # Unix seconds
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
                "source": "binance",
                "symbol": symbol,
                "interval": interval,
            })
        
        return candles
    except Exception as e:
        print(f"[Binance] Error fetching {symbol} {interval}: {e}")
        return []


def fetch_all_resolutions(symbol: str, days: int = 30):
    """Fetch all resolutions for a symbol"""
    end_time = int(time.time() * 1000)
    start_time = end_time - (days * 24 * 60 * 60 * 1000)
    
    all_data = {}
    
    for resolution, interval in RESOLUTION_MAP.items():
        print(f"  Fetching {symbol} {resolution} ({interval})...")
        
        # Binance max 1000 candles per call
        candles = fetch_binance_candles(
            symbol, 
            interval, 
            start_time=start_time, 
            end_time=end_time,
            limit=1000
        )
        
        if candles:
            all_data[resolution] = candles
            print(f"    Got {len(candles)} candles")
        else:
            print(f"    No data")
        
        time.sleep(0.2)  # Rate limiting
    
    return all_data


def store_to_mongodb(symbol: str, data: dict):
    """Store Binance data to separate MongoDB collection"""
    client = get_mongo_client()
    db = client[BINANCE_DB]
    
    collection = db[BINANCE_COLLECTION]
    
    # Prepare bulk operations
    from pymongo import InsertOne, UpdateOne
    
    operations = []
    for resolution, candles in data.items():
        for c in candles:
            c["resolution"] = resolution
            c["binance_symbol"] = SYMBOL_MAP.get(symbol, f"{symbol}USDT")
            operations.append(UpdateOne(
                {"timestamp": c["timestamp"], "resolution": resolution, "binance_symbol": c["binance_symbol"]},
                {"$set": c},
                upsert=True
            ))
    
    if operations:
        result = collection.bulk_write(operations, ordered=False)
        print(f"[MongoDB] Stored {len(operations)} candles for {symbol}")
    client.close()


def compare_candles(symbol: str, resolution: str):
    """Compare Binance data with our existing data"""
    client = get_mongo_client()
    
    # Our data
    our_collection = client[BINANCE_DB]["candles"]
    
    # Binance data  
    binance_collection = client[BINANCE_DB][BINANCE_COLLECTION]
    
    # Get sample from both
    our_sample = list(our_collection.find({"symbol": symbol, "resolution": resolution}).limit(5))
    binance_sample = list(binance_collection.find({"resolution": resolution, "binance_symbol": SYMBOL_MAP.get(symbol, f"{symbol}USDT")}).limit(5))
    
    print(f"\n=== Comparison: {symbol} {resolution} ===")
    print(f"Our candles ({len(our_sample)} sample):")
    for c in our_sample[:3]:
        print(f"  {c.get('timestamp')}: O={c.get('open')} H={c.get('high')} L={c.get('low')} C={c.get('close')}")
    
    print(f"\nBinance candles ({len(binance_sample)} sample):")
    for c in binance_sample[:3]:
        print(f"  {c.get('timestamp')}: O={c.get('open')} H={c.get('high')} L={c.get('low')} C={c.get('close')}")
    
    client.close()


if __name__ == "__main__":
    import sys
    
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XAU"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    
    print(f"Fetching {symbol} for {days} days from Binance...")
    
    data = fetch_all_resolutions(symbol, days)
    
    print(f"\nStoring to MongoDB...")
    store_to_mongodb(symbol, data)
    
    print(f"\nComparing with existing data...")
    for resolution in RESOLUTION_MAP.keys():
        compare_candles(symbol, resolution)
