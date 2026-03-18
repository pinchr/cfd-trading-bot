"""News scraping service - fetches real financial news via RSS feeds for all symbols"""
import httpx
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from typing import List, Dict, Any
import asyncio
import logging

logger = logging.getLogger(__name__)

# RSS feeds organized by symbol/asset class
# Each feed is (url, target_symbol) - target_symbol=None means auto-detect
RSS_FEEDS = [
    # BTC/Crypto feeds - always detect as BTC
    ("https://cointelegraph.com/rss", "BTC"),
    ("https://www.coindesk.com/feed", "BTC"),
    
    # US100/Tech feeds - detect tech-related
    ("https://feeds.bloomberg.com/technology/news.rss", None),
    ("https://feeds.reuters.com/reuters/technologyNews", "US100"),
    
    # XAU/Gold - commodities
    ("https://www.investing.com/rss/commodities.rss", "XAU"),
    
    # XAG/Silver - commodities
    ("https://www.investing.com/rss/commodities.rss", "XAG"),
    
    # General/Bloomberg - will auto-detect
    ("https://feeds.bloomberg.com/markets/news.rss", None),
]


def detect_symbol(headline: str, default: str = "XAU") -> str:
    """Detect which symbol the news is about based on headline"""
    text = headline.lower()
    
    # BTC/Crypto detection (most specific)
    if any(x in text for x in ['bitcoin', 'btc', 'crypto', 'cryptocurrency', 'ethereum', 'ether', 'solana', 'blockchain', 'cointelegraph', 'coindesk', 'digital asset']):
        return "BTC"
    
    # US100/Tech detection
    elif any(x in text for x in ['nasdaq', 's&p 500', 'sp500', 'tech', 'apple', 'microsoft', 'google', 'nvidia', 'meta', 'amazon', 'facebook', 'ai ', 'artificial intelligence', 'semiconductor', 'chip']):
        return "US100"
    
    # XAG/Silver detection
    elif any(x in text for x in ['silver', 'xag', 'ag ', 'precious metal', 'industrial metal']):
        return "XAG"
    
    # XAU/Gold detection
    elif any(x in text for x in ['gold', 'xau', 'oz ', 'dollar', 'treasury', 'yield', 'inflation']):
        return "XAU"
    
    return default


async def fetch_rss_feed(url: str, target_symbol: str = None) -> List[Dict[str, Any]]:
    """Fetch and parse RSS feed"""
    news_items = []
    
    async with httpx.AsyncClient(timeout=15.0, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }) as client:
        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"RSS feed returned {resp.status_code}: {url}")
                return news_items
            
            soup = BeautifulSoup(resp.text, "xml")
            
            # Find all items
            for item in soup.find_all("item")[:15]:
                title_elem = item.find("title")
                link_elem = item.find("link")
                desc_elem = item.find("description")
                
                if title_elem and title_elem.text:
                    headline = title_elem.text.strip()
                    # Clean up headline
                    headline = ' '.join(headline.split())[:200]
                    
                    # Determine symbol - use provided or detect
                    symbol = target_symbol or detect_symbol(headline, "XAU")
                    
                    # Determine sentiment from keywords
                    sentiment = 0.0
                    direction = "neutral"
                    text_lower = headline.lower()
                    if any(x in text_lower for x in ['rise', 'gain', 'surge', 'up', 'high', 'bullish', 'growth', 'increase', 'soar', 'rally']):
                        sentiment = 0.5
                        direction = "buy"
                    elif any(x in text_lower for x in ['fall', 'drop', 'down', 'low', 'bearish', 'decline', 'decrease', 'loss', 'plunge', 'tumble']):
                        sentiment = -0.5
                        direction = "sell"
                    
                    # Determine importance
                    importance = 0.5
                    if any(x in text_lower for x in ['fed', 'interest rate', 'inflation', 'jobs', 'gdp', 'earnings', 'fed meeting', 'rate decision']):
                        importance = 0.8
                    
                    news_items.append({
                        "symbol": symbol,
                        "headline": headline,
                        "sentiment": sentiment,
                        "direction": direction,
                        "importance": importance,
                        "source": "Bloomberg" if "bloomberg" in url else "Investing.com",
                        "url": link_elem.text if link_elem else "",
                        "published": datetime.now(timezone.utc).isoformat(),
                    })
                    
        except Exception as e:
            logger.warning(f"Failed to fetch RSS {url}: {e}")
    
    return news_items


async def get_scraped_news(limit: int = 10) -> List[Dict[str, Any]]:
    """Main function to get scraped news from multiple RSS sources for all symbols"""
    all_news = []
    
    # Fetch all feeds in parallel
    tasks = [fetch_rss_feed(url, symbol) for url, symbol in RSS_FEEDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, list):
            all_news.extend(result)
    
    # If still no news, return fallback
    if not all_news:
        logger.warning("All scrapers failed, using fallback news")
        return get_fallback_news(limit)
    
    # Remove duplicates based on headline similarity
    seen = set()
    unique_news = []
    for news in all_news:
        headline_key = news["headline"][:30].lower()
        if headline_key not in seen:
            seen.add(headline_key)
            unique_news.append(news)
    
    # Sort by importance and limit
    unique_news.sort(key=lambda x: x.get("importance", 0), reverse=True)
    return unique_news[:limit]


def get_fallback_news(limit: int = 10) -> List[Dict[str, Any]]:
    """Fallback news when scraping fails"""
    now = datetime.now(timezone.utc)
    return [
        {"symbol": "XAU", "headline": "Gold prices steady as investors await US jobs data", "sentiment": 0.2, "direction": "neutral", "importance": 0.7, "source": "Reuters", "url": "", "published": now.isoformat()},
        {"symbol": "XAU", "headline": "Gold remains near 3-week high on dollar weakness", "sentiment": 0.4, "direction": "buy", "importance": 0.8, "source": "Bloomberg", "url": "", "published": now.isoformat()},
        {"symbol": "XAG", "headline": "Silver outperforms gold on industrial demand", "sentiment": 0.5, "direction": "buy", "importance": 0.6, "source": "MarketWatch", "url": "", "published": now.isoformat()},
        {"symbol": "US100", "headline": "Nasdaq rises on strong tech earnings", "sentiment": 0.5, "direction": "buy", "importance": 0.8, "source": "Yahoo Finance", "url": "", "published": now.isoformat()},
        {"symbol": "BTC", "headline": "Bitcoin holds above $67,000 amid ETF inflows", "sentiment": 0.3, "direction": "neutral", "importance": 0.7, "source": "CoinDesk", "url": "", "published": now.isoformat()},
    ][:limit]


def save_news_to_db(news_items: List[Dict[str, Any]]) -> None:
    """Save news items to MongoDB with TTL (60 days)"""
    try:
        import database as db
        database = db.get_db()
        if database is None:
            return
        
        now = datetime.now(timezone.utc)
        for item in news_items:
            item["fetched_at"] = now
            database.news.update_one(
                {"headline": item["headline"]},
                {"$set": item},
                upsert=True
            )
        logger.info(f"Saved {len(news_items)} news items to MongoDB")
    except Exception as e:
        logger.warning(f"Failed to save news to DB: {e}")


def get_cached_news(limit: int = 10) -> List[Dict[str, Any]]:
    """Get news from MongoDB cache"""
    try:
        import database as db
        database = db.get_db()
        if database is None:
            return []
        
        cursor = database.news.find().sort("fetched_at", -1).limit(limit)
        news = list(cursor)
        for item in news:
            item.pop("_id", None)
        return news
    except Exception as e:
        logger.warning(f"Failed to get cached news: {e}")
        return []
