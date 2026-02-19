"""
Alpha Vantage News Sentiment Client for CFD Trading Bot.
Uses the NEWS_SENTIMENT endpoint with proper symbol mapping.
Provides an async get_news() interface that main.py expects.
"""
import os
import time
import httpx
from datetime import datetime
from typing import Optional, Dict, List, Any
from dotenv import load_dotenv

load_dotenv()

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "demo")
ALPHA_BASE_URL = "https://www.alphavantage.co/query"

# Map our internal symbols to Alpha Vantage NEWS_SENTIMENT tickers
# Alpha Vantage uses specific ticker formats for commodities and crypto
NEWS_TICKER_MAP = {
    "XAU": "FOREX:XAU",       # Gold
    "XAG": "FOREX:XAG",       # Silver
    "US100": "QQQ",           # Nasdaq-100 via QQQ ETF
    "BTC": "CRYPTO:BTC",      # Bitcoin
}

# Broader search topics when ticker-specific news is empty
NEWS_TOPICS_MAP = {
    "XAU": "financial_markets",
    "XAG": "financial_markets",
    "US100": "technology",
    "BTC": "blockchain",
}


class AlphaVantageNewsClient:
    def __init__(self, api_key: str = ALPHA_VANTAGE_API_KEY):
        self.api_key = api_key
        self.base_url = ALPHA_BASE_URL
        self.client = httpx.Client(timeout=10)
        self.cache: Dict[str, List] = {}
        self.cache_time: Dict[str, float] = {}
        self.cache_ttl = 3*3600  # Cache for 10 minutes (news doesn't change fast)
        self.last_api_call = 0.0
        self.min_interval = 13.0  # Alpha Vantage free: 5 calls/min

    def _rate_limit(self):
        """Rate limiter - blocking (only for sync usage)."""
        elapsed = time.time() - self.last_api_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_api_call = time.time()

    def _fetch_news(self, symbol: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch news sentiment from Alpha Vantage API."""
        cache_key = f"news_{symbol}"
        if cache_key in self.cache:
            if time.time() - self.cache_time.get(cache_key, 0) < self.cache_ttl:
                return self.cache[cache_key]

        if self.api_key == "demo":
            print(f"[NEWS] ALPHA_VANTAGE_API_KEY not set – skipping news for {symbol}")
            return []

        try:
            self._rate_limit()

            av_ticker = NEWS_TICKER_MAP.get(symbol, symbol)
            topics = NEWS_TOPICS_MAP.get(symbol)

            params = {
                "function": "NEWS_SENTIMENT",
                "tickers": av_ticker,
                "limit": min(limit, 50),
                "sort": "RELEVANCE",
                "apikey": self.api_key,
            }
            if topics:
                params["topics"] = topics

            response = self.client.get(self.base_url, params=params)

            if response.status_code != 200:
                print(f"[NEWS] API error for {symbol}: HTTP {response.status_code}")
                return []

            data = response.json()

            # Check for API error messages (rate limit, invalid key, etc.)
            if "Information" in data:
                print(f"[NEWS] API limit: {data['Information'][:180]}")
                return []
            if "Error Message" in data:
                print(f"[NEWS] API error: {data['Error Message'][:180]}")
                return []

            if "feed" not in data:
                print(f"[NEWS] No feed in response for {symbol}")
                return []

            news = []
            for article in data["feed"][:limit]:
                # Try to find ticker-specific sentiment first
                sentiment_score = 0.0
                relevance = 0.0

                if "ticker_sentiment" in article:
                    for ts in article["ticker_sentiment"]:
                        ticker = ts.get("ticker", "")
                        # Match our mapped ticker or the raw symbol
                        if ticker == av_ticker or ticker == symbol:
                            relevance = float(ts.get("relevance_score", 0))
                            raw_sentiment = float(ts.get("ticker_sentiment_score", 0))
                            sentiment_score = raw_sentiment * relevance
                            break

                # Fallback to overall article sentiment if no ticker match
                if sentiment_score == 0.0:
                    sentiment_score = float(article.get("overall_sentiment_score", 0))

                if sentiment_score > 0.15:
                    direction = "buy"
                elif sentiment_score < -0.15:
                    direction = "sell"
                else:
                    direction = "neutral"

                importance = min(1.0, abs(sentiment_score) + 0.3)

                news.append({
                    "headline": article.get("title", "")[:120],
                    "sentiment": round(sentiment_score, 3),
                    "direction": direction,
                    "importance": round(importance, 2),
                    "source": article.get("source", "Unknown"),
                    "url": article.get("url", ""),
                    "published": article.get("time_published", ""),
                })

            self.cache[cache_key] = news
            self.cache_time[cache_key] = time.time()

            return news

        except Exception as e:
            print(f"[NEWS] Error fetching for {symbol}: {e}")
            return []

    async def get_news(self, symbol: str, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Async interface expected by main.py.
        Wraps the sync HTTP call (Alpha Vantage doesn't need async).
        """
        return self._fetch_news(symbol, limit)

    def close(self):
        self.client.close()


# Singleton
_client = None


def get_client() -> AlphaVantageNewsClient:
    global _client
    if _client is None:
        _client = AlphaVantageNewsClient()
    return _client
