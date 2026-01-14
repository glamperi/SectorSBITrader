#!/usr/bin/env python3
"""
Meme Stock Holdings Fetcher
===========================
Fetches top holdings from MEME ETF via stockanalysis.com
Updates monthly since ETF holdings don't change that often.
"""

import requests
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import json
import os
import re

# Cache file to avoid too many scrapes
CACHE_FILE = os.path.expanduser('~/.meme_holdings_cache.json')
CACHE_DAYS = 30  # Refresh monthly


def get_cached_holdings() -> Optional[List[str]]:
    """Get cached holdings if still valid."""
    if not os.path.exists(CACHE_FILE):
        return None
    
    try:
        with open(CACHE_FILE, 'r') as f:
            data = json.load(f)
        
        cached_time = datetime.fromisoformat(data['timestamp'])
        if datetime.now() - cached_time < timedelta(days=CACHE_DAYS):
            print(f"   📦 Using cached meme holdings from {cached_time.strftime('%Y-%m-%d')}")
            return data['holdings']
    except:
        pass
    
    return None


def save_holdings_cache(holdings: List[str], source: str):
    """Save holdings to cache."""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'holdings': holdings,
                'source': source
            }, f)
    except:
        pass


def scrape_stockanalysis_holdings() -> List[str]:
    """
    Scrape MEME ETF holdings from stockanalysis.com
    Returns list of ticker symbols.
    """
    url = 'https://stockanalysis.com/etf/meme/holdings/'
    holdings = []
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        html = response.text
        
        # Parse holdings from the table
        # Look for ticker symbols in the holdings table
        # Pattern: links like /stocks/gme/ or ticker symbols in table cells
        
        # Method 1: Find stock links
        stock_pattern = r'/stocks/([a-z]+)/"'
        matches = re.findall(stock_pattern, html.lower())
        
        if matches:
            # Convert to uppercase and deduplicate while preserving order
            seen = set()
            for ticker in matches:
                ticker_upper = ticker.upper()
                if ticker_upper not in seen and len(ticker_upper) <= 5:
                    seen.add(ticker_upper)
                    holdings.append(ticker_upper)
        
        # Method 2: If method 1 didn't work well, try finding ticker patterns
        if len(holdings) < 10:
            # Look for standalone tickers (2-5 uppercase letters)
            ticker_pattern = r'>([A-Z]{2,5})<'
            matches = re.findall(ticker_pattern, html)
            
            # Filter to likely tickers (exclude common HTML words)
            exclude = {'ETF', 'USD', 'NYSE', 'NASDAQ', 'CEO', 'CFO', 'USA', 'INC', 'LLC', 'THE'}
            for ticker in matches:
                if ticker not in exclude and ticker not in holdings:
                    holdings.append(ticker)
        
        if holdings:
            print(f"   🎮 Scraped {len(holdings)} holdings from stockanalysis.com")
            return holdings[:25]  # Top 25
            
    except requests.exceptions.RequestException as e:
        print(f"   ⚠️ Could not scrape stockanalysis.com: {e}")
    except Exception as e:
        print(f"   ⚠️ Error parsing holdings: {e}")
    
    return []


def get_default_meme_holdings() -> List[str]:
    """
    Default MEME ETF holdings as of Jan 2026.
    Used as fallback if scraping fails.
    Source: https://stockanalysis.com/etf/meme/holdings/
    """
    return [
        'GME',    # GameStop - 6.52%
        'MSTR',   # MicroStrategy - 5.89%
        'HOOD',   # Robinhood - 5.54%
        'RDDT',   # Reddit - 5.46%
        'IONQ',   # IonQ - 5.44%
        'COIN',   # Coinbase - 5.37%
        'RKLB',   # Rocket Lab - 5.35%
        'SOFI',   # SoFi - 5.30%
        'PLTR',   # Palantir - 5.26%
        'AMC',    # AMC - 4.54%
        'AFRM',   # Affirm - 4.49%
        'UPST',   # Upstart - 4.44%
        'CVNA',   # Carvana - 4.43%
        'LCID',   # Lucid - 4.15%
        'RIVN',   # Rivian - 4.09%
        'DNA',    # Ginkgo Bioworks - 3.83%
        'JOBY',   # Joby Aviation - 3.73%
        'OPEN',   # Opendoor - 3.48%
        'PLUG',   # Plug Power - 3.37%
        'MARA',   # Marathon Digital - 2.99%
        'SMCI',   # Super Micro - 2.60%
        'RIOT',   # Riot Platforms - 2.34%
        'VLD',    # Velo3D - 0.80%
    ]


def get_meme_holdings(use_cache: bool = True, force_refresh: bool = False) -> Dict:
    """
    Get meme stock holdings with metadata.
    
    Args:
        use_cache: Whether to use cached data if available
        force_refresh: Force a fresh scrape even if cache is valid
    
    Returns:
        Dict with 'stocks' list and 'source' info
    """
    # Check cache first (unless forcing refresh)
    if use_cache and not force_refresh:
        cached = get_cached_holdings()
        if cached:
            return {
                'stocks': cached,
                'source': 'cache',
                'updated': 'cached'
            }
    
    print("   🔄 Fetching fresh MEME ETF holdings...")
    
    # Try scraping stockanalysis.com
    holdings = scrape_stockanalysis_holdings()
    source = 'stockanalysis.com'
    
    # Fall back to default list if scraping failed
    if not holdings or len(holdings) < 10:
        print("   📋 Using default MEME holdings list")
        holdings = get_default_meme_holdings()
        source = 'default'
    
    # Save to cache
    save_holdings_cache(holdings, source)
    
    return {
        'stocks': holdings,
        'source': source,
        'updated': datetime.now().isoformat()
    }


def get_meme_stock_list() -> List[str]:
    """Simple function to get meme stock list for config."""
    result = get_meme_holdings()
    return result['stocks']


if __name__ == "__main__":
    print("\n🎮 MEME ETF Holdings Fetcher")
    print("=" * 50)
    print("Source: https://stockanalysis.com/etf/meme/holdings/")
    
    # Force fresh fetch
    result = get_meme_holdings(use_cache=False, force_refresh=True)
    
    print(f"\n📊 Source: {result['source']}")
    print(f"📅 Updated: {result['updated']}")
    print(f"\n🚀 Top {len(result['stocks'])} MEME ETF Holdings:")
    
    for i, ticker in enumerate(result['stocks'], 1):
        print(f"   {i:2}. {ticker}")
    
    print(f"\n💾 Cached to: {CACHE_FILE}")
    print(f"   Cache valid for {CACHE_DAYS} days")
