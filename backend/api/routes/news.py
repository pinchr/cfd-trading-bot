"""News API routes - uses webscraping for real financial news"""
from datetime import datetime
from fastapi import APIRouter
import asyncio
from services.state import get_instruments
from app.logging import log_event
from services.news_scraper import get_scraped_news, get_fallback_news, save_news_to_db, get_cached_news

router = APIRouter(tags=["news"])


@router.get("/api/news/all")
async def get_all_news():
    """Get latest news for all symbols - scrapes real news from financial sites."""
    log_event("Fetching latest news via web scraping...", "info")
    
    try:
        # Try to scrape real news
        news = await get_scraped_news(limit=25)
        
        if news:
            # Save to MongoDB with TTL
            save_news_to_db(news)
            log_event(f"Scraped {len(news)} news items", "success")
            return {"news": news, "timestamp": datetime.now().isoformat(), "source": "scraped"}
        else:
            # Fallback: try cached news from DB
            cached = get_cached_news(limit=10)
            if cached:
                log_event(f"Using {len(cached)} cached news items from DB", "info")
                return {"news": cached, "timestamp": datetime.now().isoformat(), "source": "cached"}
            
            # Fallback to static if scraping fails
            log_event("Scraping returned no results, using fallback", "warning")
            news = get_fallback_news(limit=10)
            return {"news": news, "timestamp": datetime.now().isoformat(), "source": "fallback"}
            
    except Exception as e:
        log_event(f"News fetch error: {e}", "error")
        
        # Try cached news on error
        cached = get_cached_news(limit=10)
        if cached:
            return {"news": cached, "timestamp": datetime.now().isoformat(), "source": "cached"}
        
        news = get_fallback_news(limit=10)
        return {"news": news, "timestamp": datetime.now().isoformat(), "source": "fallback", "error": str(e)}


@router.get("/api/news/{symbol}")
async def get_news(symbol: str):
    """Get news for a specific symbol - scrapes and filters by symbol."""
    log_event(f"Fetching news for {symbol} via web scraping...", "info")
    
    try:
        all_news = await get_scraped_news(limit=30)
        
        # Filter by symbol
        symbol_upper = symbol.upper()
        symbol_news = [n for n in all_news if n.get("symbol", "").upper() == symbol_upper]
        
        if not symbol_news:
            # If no news for this symbol, get from cache or fallback
            cached = get_cached_news(limit=20)
            symbol_news = [n for n in cached if n.get("symbol", "").upper() == symbol_upper]
            
            if not symbol_news:
                fallback = get_fallback_news(limit=10)
                symbol_news = [n for n in fallback if n.get("symbol", "").upper() == symbol_upper]
        
        # Save all news to DB for future use
        if all_news:
            save_news_to_db(all_news)
        
        return {"symbol": symbol, "news": symbol_news, "timestamp": datetime.now().isoformat(), "source": "scraped"}
        
    except Exception as e:
        log_event(f"News fetch error for {symbol}: {e}", "error")
        
        # Try cached on error
        cached = get_cached_news(limit=20)
        symbol_news = [n for n in cached if n.get("symbol", "").upper() == symbol.upper()]
        
        if symbol_news:
            return {"symbol": symbol, "news": symbol_news, "timestamp": datetime.now().isoformat(), "source": "cached"}
        
        fallback = get_fallback_news(limit=5)
        symbol_news = [n for n in fallback if n.get("symbol", "").upper() == symbol.upper()]
        return {"symbol": symbol, "news": symbol_news, "timestamp": datetime.now().isoformat(), "source": "fallback"}
