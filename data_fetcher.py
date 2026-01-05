"""
SectorSBITrader - Data Fetcher

Fetches historical price and volume data for all tickers needed by the strategy.
Uses yfinance for data retrieval.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import time

try:
    import yfinance as yf
except ImportError:
    print("Warning: yfinance not installed. Run: pip install yfinance")
    yf = None

from config import PARENT_CHILD_MAPPING, get_all_tickers


class DataFetcher:
    """
    Fetches and caches price/volume data for all strategy tickers.
    """
    
    def __init__(self, cache_file: str = None):
        """
        Args:
            cache_file: Optional path to cache data (pickle format)
        """
        self.cache_file = cache_file
        self.price_data: Dict[str, pd.Series] = {}
        self.volume_data: Dict[str, pd.Series] = {}
        self.last_fetch: Optional[datetime] = None
        self.failed_tickers: List[str] = []
    
    def fetch_ticker(self, ticker: str, period: str = "2y") -> Tuple[pd.Series, pd.Series]:
        """
        Fetch price and volume data for a single ticker.
        
        Args:
            ticker: Stock/ETF symbol
            period: Data period (e.g., "1y", "2y", "5y")
        
        Returns:
            (price_series, volume_series)
        """
        if yf is None:
            raise ImportError("yfinance not installed")
        
        try:
            data = yf.download(ticker, period=period, progress=False)
            
            if len(data) == 0:
                return pd.Series(), pd.Series()
            
            prices = data['Close']
            volume = data['Volume']
            
            return prices, volume
            
        except Exception as e:
            print(f"  Error fetching {ticker}: {e}")
            return pd.Series(), pd.Series()
    
    def fetch_all(self, period: str = "2y", delay: float = 0.1) -> Tuple[Dict[str, pd.Series], Dict[str, pd.Series]]:
        """
        Fetch data for all tickers in the strategy.
        
        Args:
            period: Data period
            delay: Delay between requests to avoid rate limiting
        
        Returns:
            (price_data_dict, volume_data_dict)
        """
        all_tickers = get_all_tickers()
        print(f"Fetching data for {len(all_tickers)} tickers...")
        
        self.price_data = {}
        self.volume_data = {}
        self.failed_tickers = []
        
        for i, ticker in enumerate(all_tickers):
            print(f"  [{i+1}/{len(all_tickers)}] {ticker}...", end=" ")
            
            prices, volume = self.fetch_ticker(ticker, period)
            
            if len(prices) > 0:
                self.price_data[ticker] = prices
                self.volume_data[ticker] = volume
                print(f"✓ ({len(prices)} days)")
            else:
                self.failed_tickers.append(ticker)
                print("✗ (no data)")
            
            if delay > 0:
                time.sleep(delay)
        
        self.last_fetch = datetime.now()
        
        print(f"\nFetch complete:")
        print(f"  Success: {len(self.price_data)}")
        print(f"  Failed: {len(self.failed_tickers)}")
        
        if self.failed_tickers:
            print(f"  Failed tickers: {', '.join(self.failed_tickers[:10])}" + 
                  ("..." if len(self.failed_tickers) > 10 else ""))
        
        return self.price_data, self.volume_data
    
    def fetch_batch(self, tickers: List[str], period: str = "2y") -> Tuple[Dict[str, pd.Series], Dict[str, pd.Series]]:
        """
        Fetch data for a batch of tickers using yfinance batch download.
        
        This is faster than fetching one-by-one but may miss some tickers.
        
        Args:
            tickers: List of ticker symbols
            period: Data period
        
        Returns:
            (price_data_dict, volume_data_dict)
        """
        if yf is None:
            raise ImportError("yfinance not installed")
        
        print(f"Batch fetching {len(tickers)} tickers...")
        
        try:
            # Download all at once
            data = yf.download(tickers, period=period, progress=True, group_by='ticker')
            
            price_data = {}
            volume_data = {}
            
            for ticker in tickers:
                try:
                    if len(tickers) == 1:
                        # Single ticker - data is not grouped
                        prices = data['Close']
                        volume = data['Volume']
                    else:
                        # Multiple tickers - data is grouped by ticker
                        prices = data[ticker]['Close']
                        volume = data[ticker]['Volume']
                    
                    if len(prices.dropna()) > 0:
                        price_data[ticker] = prices.dropna()
                        volume_data[ticker] = volume.dropna()
                except Exception as e:
                    print(f"  Warning: Could not extract {ticker}: {e}")
            
            print(f"Fetched {len(price_data)} tickers successfully")
            return price_data, volume_data
            
        except Exception as e:
            print(f"Batch fetch failed: {e}")
            return {}, {}
    
    def fetch_parents_only(self, period: str = "2y") -> Dict[str, pd.Series]:
        """
        Fetch data for parent tickers only (for quick parent signal check).
        
        Returns:
            price_data_dict for parent tickers
        """
        parents = list(PARENT_CHILD_MAPPING.keys())
        # Add VIX for safety checks
        parents.extend(['^VIX', 'VIXM'])
        
        price_data, _ = self.fetch_batch(parents, period)
        return price_data
    
    def save_cache(self, filename: str = None):
        """Save data to cache file."""
        filename = filename or self.cache_file
        if not filename:
            return
        
        import pickle
        cache = {
            'price_data': self.price_data,
            'volume_data': self.volume_data,
            'last_fetch': self.last_fetch,
            'failed_tickers': self.failed_tickers,
        }
        
        with open(filename, 'wb') as f:
            pickle.dump(cache, f)
        
        print(f"Cache saved to {filename}")
    
    def load_cache(self, filename: str = None) -> bool:
        """
        Load data from cache file.
        
        Returns:
            True if cache loaded successfully
        """
        import os
        import pickle
        
        filename = filename or self.cache_file
        if not filename or not os.path.exists(filename):
            return False
        
        try:
            with open(filename, 'rb') as f:
                cache = pickle.load(f)
            
            self.price_data = cache.get('price_data', {})
            self.volume_data = cache.get('volume_data', {})
            self.last_fetch = cache.get('last_fetch')
            self.failed_tickers = cache.get('failed_tickers', [])
            
            print(f"Cache loaded: {len(self.price_data)} tickers")
            if self.last_fetch:
                print(f"Last fetch: {self.last_fetch}")
            
            return True
            
        except Exception as e:
            print(f"Error loading cache: {e}")
            return False
    
    def is_cache_fresh(self, max_age_hours: float = 24) -> bool:
        """Check if cache is fresh enough."""
        if self.last_fetch is None:
            return False
        
        age = datetime.now() - self.last_fetch
        return age.total_seconds() < max_age_hours * 3600
    
    def get_data(self) -> Tuple[Dict[str, pd.Series], Dict[str, pd.Series]]:
        """
        Get price and volume data (from cache or fetch).
        
        Returns:
            (price_data_dict, volume_data_dict)
        """
        # Try to load cache first
        if self.cache_file and self.load_cache():
            if self.is_cache_fresh():
                return self.price_data, self.volume_data
            else:
                print("Cache is stale, refetching...")
        
        # Fetch fresh data
        self.fetch_all()
        
        # Save to cache
        if self.cache_file:
            self.save_cache()
        
        return self.price_data, self.volume_data


def fetch_live_quote(ticker: str) -> Dict:
    """
    Fetch live quote for a single ticker.
    
    Returns:
        Dict with price, volume, change info
    """
    if yf is None:
        return {'error': 'yfinance not installed'}
    
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        return {
            'ticker': ticker,
            'price': info.get('regularMarketPrice', info.get('currentPrice', 0)),
            'change': info.get('regularMarketChange', 0),
            'change_pct': info.get('regularMarketChangePercent', 0),
            'volume': info.get('regularMarketVolume', 0),
            'market_cap': info.get('marketCap', 0),
        }
    except Exception as e:
        return {'ticker': ticker, 'error': str(e)}


def fetch_live_quotes(tickers: List[str]) -> Dict[str, Dict]:
    """
    Fetch live quotes for multiple tickers.
    
    Returns:
        Dict mapping ticker to quote dict
    """
    results = {}
    for ticker in tickers:
        results[ticker] = fetch_live_quote(ticker)
    return results


if __name__ == "__main__":
    # Demo
    print("SectorSBITrader Data Fetcher")
    print("=" * 50)
    
    fetcher = DataFetcher()
    
    # Just show what would be fetched
    all_tickers = get_all_tickers()
    print(f"\nTotal tickers to fetch: {len(all_tickers)}")
    
    # Group by category
    print("\nTickers by parent:")
    for parent, info in list(PARENT_CHILD_MAPPING.items())[:5]:
        print(f"  {parent} ({info['description']}): {len(info['stocks'])} stocks")
    print("  ...")
