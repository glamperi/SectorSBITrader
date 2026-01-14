#!/usr/bin/env python3
"""
Synthetic ETF Price Generator
=============================
Generates synthetic prices for ETFs that didn't exist historically.
Used for backtesting crypto ETFs (IBIT, BITU, FETH, ETHU, etc.)

Key Features:
1. Detects missing ETF data
2. Generates 1x ETF prices from underlying (BTC-USD, ETH-USD, SOL-USD)
3. Simulates 2x leveraged ETF with daily rebalancing (includes decay)
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime


# ETF to underlying mapping
ETF_UNDERLYING_MAP = {
    # Bitcoin ETFs
    'IBIT': {'underlying': 'BTC-USD', 'leverage': 1, 'launch': '2024-01-11'},
    'BITU': {'underlying': 'BTC-USD', 'leverage': 2, 'launch': '2024-04-01'},
    'GBTC': {'underlying': 'BTC-USD', 'leverage': 1, 'launch': '2013-09-25'},
    
    # Ethereum ETFs
    'FETH': {'underlying': 'ETH-USD', 'leverage': 1, 'launch': '2024-07-23'},
    'ETHU': {'underlying': 'ETH-USD', 'leverage': 2, 'launch': '2024-04-01'},
    'ETHE': {'underlying': 'ETH-USD', 'leverage': 1, 'launch': '2017-12-14'},
    
    # Solana ETFs (if they exist)
    'SOLQ': {'underlying': 'SOL-USD', 'leverage': 1, 'launch': '2024-01-01'},
    'SOLT': {'underlying': 'SOL-USD', 'leverage': 2, 'launch': '2024-01-01'},
}

# Expense ratios (annual) - affects long-term returns
ETF_EXPENSE_RATIOS = {
    'IBIT': 0.0025,  # 0.25%
    'BITU': 0.0095,  # 0.95%
    'FETH': 0.0025,
    'ETHU': 0.0095,
    'GBTC': 0.015,   # 1.5%
    'ETHE': 0.025,   # 2.5%
}


def calculate_daily_returns(prices: pd.Series) -> pd.Series:
    """Calculate daily returns from price series."""
    return prices.pct_change()


def simulate_1x_etf(underlying_df: pd.DataFrame, 
                    expense_ratio: float = 0.0025) -> pd.DataFrame:
    """
    Simulate a 1x ETF tracking an underlying asset.
    
    Args:
        underlying_df: DataFrame with OHLC data for underlying
        expense_ratio: Annual expense ratio (e.g., 0.0025 = 0.25%)
    
    Returns:
        DataFrame with synthetic ETF OHLC data
    """
    # Helper to extract column safely
    def get_column(df, col):
        if col in df.columns:
            data = df[col]
            if hasattr(data, 'values'):
                return pd.Series(data.values.flatten(), index=df.index)
            return data
        return None
    
    # Daily expense drag
    daily_expense = expense_ratio / 252
    
    close = get_column(underlying_df, 'Close')
    high = get_column(underlying_df, 'High')
    low = get_column(underlying_df, 'Low')
    open_col = get_column(underlying_df, 'Open')
    
    if close is None:
        return None
    
    # Start with normalized prices (first close = 100)
    first_close = float(close.iloc[0])
    scale = 100 / first_close
    
    # Create synthetic DataFrame
    synthetic = pd.DataFrame(index=underlying_df.index)
    
    # Scale close prices and apply expense drag
    daily_returns = close.pct_change()
    adjusted_returns = daily_returns - daily_expense
    adjusted_returns.iloc[0] = 0
    
    synthetic['Close'] = (1 + adjusted_returns).cumprod() * 100
    
    # Scale other columns proportionally
    ratio = synthetic['Close'] / (close * scale)
    
    if high is not None:
        synthetic['High'] = high * scale * ratio
    else:
        synthetic['High'] = synthetic['Close'] * 1.01
        
    if low is not None:
        synthetic['Low'] = low * scale * ratio
    else:
        synthetic['Low'] = synthetic['Close'] * 0.99
        
    if open_col is not None:
        synthetic['Open'] = open_col * scale * ratio
    else:
        synthetic['Open'] = synthetic['Close'].shift(1)
        synthetic.loc[synthetic.index[0], 'Open'] = 100
    
    # Add volume
    vol = get_column(underlying_df, 'Volume')
    if vol is not None:
        synthetic['Volume'] = vol.values
    
    return synthetic


def simulate_2x_leveraged_etf(underlying_df: pd.DataFrame,
                              expense_ratio: float = 0.0095) -> pd.DataFrame:
    """
    Simulate a 2x leveraged ETF with daily rebalancing.
    
    IMPORTANT: 2x leveraged ETFs have "volatility decay" - they lose value
    over time in choppy markets even if the underlying is flat.
    
    Args:
        underlying_df: DataFrame with OHLC data for underlying
        expense_ratio: Annual expense ratio (e.g., 0.0095 = 0.95%)
    
    Returns:
        DataFrame with synthetic 2x ETF OHLC data
    """
    leverage = 2.0
    daily_expense = expense_ratio / 252
    
    # Extract columns safely (handle multi-level columns from yfinance)
    def get_column(df, col):
        if col in df.columns:
            data = df[col]
            if hasattr(data, 'values'):
                return pd.Series(data.values.flatten(), index=df.index)
            return data
        return None
    
    close = get_column(underlying_df, 'Close')
    high = get_column(underlying_df, 'High')
    low = get_column(underlying_df, 'Low')
    
    if close is None:
        return None
    
    # Calculate daily returns of underlying
    underlying_returns = close.pct_change()
    
    # Apply 2x leverage to daily returns, minus expenses
    leveraged_returns = (underlying_returns * leverage) - daily_expense
    
    # Handle first day
    leveraged_returns.iloc[0] = 0
    
    # Compound to get price series (start at 100)
    synthetic_close = (1 + leveraged_returns).cumprod() * 100
    
    # Build full OHLC DataFrame
    synthetic = pd.DataFrame(index=underlying_df.index)
    synthetic['Close'] = synthetic_close.values
    
    # Estimate Open, High, Low based on underlying's intraday range
    if high is not None and low is not None:
        underlying_range = (high - low) / close
        underlying_range = underlying_range.fillna(0.02)  # Default 2% range
    else:
        underlying_range = pd.Series(0.02, index=underlying_df.index)
    
    # For leveraged ETF, intraday range is approximately 2x
    synthetic_range = underlying_range * leverage
    
    # Estimate OHLC - simple approach
    synthetic['Open'] = synthetic['Close'].shift(1)
    synthetic.loc[synthetic.index[0], 'Open'] = 100
    
    # High/Low based on range
    synthetic['High'] = synthetic['Close'] * (1 + synthetic_range.values * 0.3)
    synthetic['Low'] = synthetic['Close'] * (1 - synthetic_range.values * 0.3)
    
    # Ensure High >= Close and Low <= Close
    synthetic['High'] = synthetic[['High', 'Close', 'Open']].max(axis=1)
    synthetic['Low'] = synthetic[['Low', 'Close', 'Open']].min(axis=1)
    
    # Add volume (use underlying volume as proxy)
    vol = get_column(underlying_df, 'Volume')
    if vol is not None:
        synthetic['Volume'] = vol.values
    
    return synthetic
    
    return synthetic


def generate_synthetic_etf(etf_ticker: str, 
                           underlying_df: pd.DataFrame,
                           start_date: str = None,
                           end_date: str = None) -> Optional[pd.DataFrame]:
    """
    Generate synthetic ETF prices from underlying asset.
    
    Args:
        etf_ticker: ETF ticker (e.g., 'IBIT', 'BITU')
        underlying_df: DataFrame with underlying asset OHLC
        start_date: Optional start date filter
        end_date: Optional end date filter
    
    Returns:
        DataFrame with synthetic ETF prices, or None if not supported
    """
    if etf_ticker not in ETF_UNDERLYING_MAP:
        return None
    
    config = ETF_UNDERLYING_MAP[etf_ticker]
    leverage = config['leverage']
    expense_ratio = ETF_EXPENSE_RATIOS.get(etf_ticker, 0.005)
    
    # Filter date range if specified
    df = underlying_df.copy()
    if start_date:
        df = df[df.index >= pd.Timestamp(start_date)]
    if end_date:
        df = df[df.index <= pd.Timestamp(end_date)]
    
    if len(df) < 10:
        return None
    
    # Generate synthetic prices
    if leverage == 1:
        synthetic = simulate_1x_etf(df, expense_ratio)
    elif leverage == 2:
        synthetic = simulate_2x_leveraged_etf(df, expense_ratio)
    else:
        # For other leverage ratios, adapt the 2x function
        synthetic = simulate_2x_leveraged_etf(df, expense_ratio)
    
    return synthetic


def fill_missing_etf_data(price_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    """
    Fill in missing ETF data with synthetic prices.
    
    Args:
        price_data: Dict of ticker -> DataFrame with price data
    
    Returns:
        Updated price_data with synthetic ETFs added
    """
    print("\n🔧 Checking for missing ETF data...")
    
    for etf_ticker, config in ETF_UNDERLYING_MAP.items():
        underlying = config['underlying']
        launch_date = config['launch']
        
        # Check if we have underlying data
        if underlying not in price_data:
            continue
        
        underlying_df = price_data[underlying]
        
        # Check if ETF data is missing or incomplete
        need_synthetic = False
        
        if etf_ticker not in price_data:
            need_synthetic = True
            print(f"   📈 {etf_ticker}: No data found, generating synthetic from {underlying}")
        elif len(price_data[etf_ticker]) < len(underlying_df) * 0.5:
            # ETF has less than 50% of underlying's history
            need_synthetic = True
            print(f"   📈 {etf_ticker}: Limited history, extending with synthetic from {underlying}")
        
        if need_synthetic:
            synthetic = generate_synthetic_etf(etf_ticker, underlying_df)
            
            if synthetic is not None and len(synthetic) > 0:
                # If we have some real data, merge it
                if etf_ticker in price_data and len(price_data[etf_ticker]) > 0:
                    real_data = price_data[etf_ticker]
                    real_start = real_data.index[0]
                    
                    # Use synthetic before real data starts
                    synthetic_before = synthetic[synthetic.index < real_start]
                    
                    if len(synthetic_before) > 0:
                        # Scale synthetic to match real data at junction
                        scale_factor = real_data['Close'].iloc[0] / synthetic_before['Close'].iloc[-1]
                        for col in ['Open', 'High', 'Low', 'Close']:
                            if col in synthetic_before.columns:
                                synthetic_before[col] = synthetic_before[col] * scale_factor
                        
                        # Combine
                        combined = pd.concat([synthetic_before, real_data])
                        price_data[etf_ticker] = combined
                        print(f"   ✅ {etf_ticker}: Added {len(synthetic_before)} synthetic days before {real_start.strftime('%Y-%m-%d')}")
                else:
                    price_data[etf_ticker] = synthetic
                    print(f"   ✅ {etf_ticker}: Generated {len(synthetic)} days of synthetic data")
    
    return price_data


def generate_synthetic_from_holdings(etf_ticker: str, holdings: list, 
                                     price_data: dict, 
                                     expense_ratio: float = 0.005) -> Optional[pd.DataFrame]:
    """
    Generate synthetic ETF from equal-weighted holdings.
    Used for MEME, TCAI and other ETFs without long history.
    
    Args:
        etf_ticker: ETF ticker (e.g., 'MEME', 'TCAI')
        holdings: List of stock tickers in the ETF
        price_data: Dict of ticker -> DataFrame with price data
        expense_ratio: Annual expense ratio
    
    Returns:
        DataFrame with synthetic ETF OHLC data
    """
    # Find holdings with data
    available = []
    for ticker in holdings:
        if ticker in price_data and len(price_data[ticker]) > 50:
            available.append(ticker)
    
    if len(available) < 3:
        return None
    
    # Find common date range
    common_dates = None
    for ticker in available:
        df = price_data[ticker]
        if common_dates is None:
            common_dates = set(df.index)
        else:
            common_dates = common_dates.intersection(set(df.index))
    
    if len(common_dates) < 50:
        return None
    
    common_dates = sorted(list(common_dates))
    
    # Calculate equal-weighted returns
    daily_returns = []
    for date in common_dates:
        rets = []
        for ticker in available:
            df = price_data[ticker]
            if date in df.index:
                idx = df.index.get_loc(date)
                if idx > 0:
                    prev_date = df.index[idx - 1]
                    try:
                        close_now = df['Close'].iloc[idx]
                        close_prev = df['Close'].iloc[idx - 1]
                        if hasattr(close_now, 'iloc'):
                            close_now = close_now.iloc[0]
                        if hasattr(close_prev, 'iloc'):
                            close_prev = close_prev.iloc[0]
                        if close_prev > 0:
                            ret = (float(close_now) / float(close_prev)) - 1
                            if abs(ret) < 0.5:  # Filter outliers
                                rets.append(ret)
                    except:
                        pass
        
        if rets:
            avg_ret = np.mean(rets) - (expense_ratio / 252)  # Daily expense
            daily_returns.append(avg_ret)
        else:
            daily_returns.append(0)
    
    # Build price series
    prices = [100]
    for ret in daily_returns[1:]:
        prices.append(prices[-1] * (1 + ret))
    
    # Create DataFrame
    synthetic = pd.DataFrame(index=common_dates)
    synthetic['Close'] = prices
    synthetic['Open'] = synthetic['Close'].shift(1)
    synthetic.loc[synthetic.index[0], 'Open'] = 100
    
    # Estimate High/Low
    synthetic['High'] = synthetic['Close'] * 1.01
    synthetic['Low'] = synthetic['Close'] * 0.99
    
    return synthetic


def fill_synthetic_etfs_from_holdings(price_data: dict) -> dict:
    """
    Generate synthetic data for ETFs like MEME and TCAI from their holdings.
    """
    # ETFs to generate from holdings
    etf_holdings = {
        'MEME': {
            'holdings': ['GME', 'MSTR', 'HOOD', 'COIN', 'PLTR', 'SOFI', 'AMC', 
                        'AFRM', 'UPST', 'CVNA', 'LCID', 'RIVN', 'PLUG', 'MARA'],
            'launch': '2021-12-08',
            'expense': 0.0069,
        },
        'TCAI': {
            'holdings': ['CIEN', 'STX', 'VRT', 'PWR', 'WDC', 'NRG', 'DELL', 'MU',
                        'CEG', 'WULF', 'PSTG', 'ANET', 'VST', 'NVDA', 'SMCI', 'EQIX'],
            'launch': '2025-08-04',
            'expense': 0.0065,
        },
    }
    
    print("\n🔧 Generating synthetic ETF data from holdings...")
    
    for etf_ticker, config in etf_holdings.items():
        holdings = config['holdings']
        launch_date = config['launch']
        expense = config['expense']
        
        # Check if we need synthetic data
        need_synthetic = False
        
        if etf_ticker not in price_data:
            need_synthetic = True
        elif len(price_data[etf_ticker]) < 200:  # Less than ~1 year of data
            need_synthetic = True
        
        if need_synthetic:
            print(f"   📈 {etf_ticker}: Generating synthetic from {len(holdings)} holdings")
            
            synthetic = generate_synthetic_from_holdings(
                etf_ticker, holdings, price_data, expense
            )
            
            if synthetic is not None and len(synthetic) > 0:
                # If we have real data, merge
                if etf_ticker in price_data and len(price_data[etf_ticker]) > 0:
                    real_data = price_data[etf_ticker]
                    real_start = real_data.index[0]
                    
                    # Use synthetic before real data starts
                    synthetic_before = synthetic[synthetic.index < real_start]
                    
                    if len(synthetic_before) > 0:
                        # Scale synthetic to match real data
                        scale = real_data['Close'].iloc[0] / synthetic_before['Close'].iloc[-1]
                        for col in ['Open', 'High', 'Low', 'Close']:
                            if col in synthetic_before.columns:
                                synthetic_before[col] = synthetic_before[col] * scale
                        
                        combined = pd.concat([synthetic_before, real_data])
                        price_data[etf_ticker] = combined
                        print(f"   ✅ {etf_ticker}: Added {len(synthetic_before)} synthetic days")
                else:
                    price_data[etf_ticker] = synthetic
                    print(f"   ✅ {etf_ticker}: Generated {len(synthetic)} days of data")
    
    return price_data


def demonstrate_leverage_decay():
    """
    Demonstrate how 2x leverage decays in volatile markets.
    """
    print("\n📊 Leverage Decay Demonstration")
    print("=" * 50)
    
    # Simulate 100 days of +5%/-5% alternating returns
    days = 100
    underlying_prices = [100]
    
    for i in range(days):
        if i % 2 == 0:
            underlying_prices.append(underlying_prices[-1] * 1.05)  # +5%
        else:
            underlying_prices.append(underlying_prices[-1] * 0.95)  # -5%
    
    underlying = pd.DataFrame({
        'Open': underlying_prices[:-1],
        'High': [p * 1.02 for p in underlying_prices[:-1]],
        'Low': [p * 0.98 for p in underlying_prices[:-1]],
        'Close': underlying_prices[1:]
    })
    underlying.index = pd.date_range('2020-01-01', periods=days, freq='D')
    
    # Generate 2x leveraged
    leveraged = simulate_2x_leveraged_etf(underlying)
    
    print(f"After {days} days of +5%/-5% alternating:")
    print(f"  Underlying: ${underlying['Close'].iloc[0]:.2f} → ${underlying['Close'].iloc[-1]:.2f} ({(underlying['Close'].iloc[-1]/underlying['Close'].iloc[0]-1)*100:+.1f}%)")
    print(f"  2x Levered: ${leveraged['Close'].iloc[0]:.2f} → ${leveraged['Close'].iloc[-1]:.2f} ({(leveraged['Close'].iloc[-1]/leveraged['Close'].iloc[0]-1)*100:+.1f}%)")
    print(f"\n  ⚠️ This is 'volatility decay' - the 2x ETF loses money even though underlying is ~flat!")


if __name__ == "__main__":
    print("🔧 Synthetic ETF Generator")
    print("=" * 50)
    
    print("\nSupported ETFs:")
    for etf, config in ETF_UNDERLYING_MAP.items():
        print(f"  {etf}: {config['leverage']}x {config['underlying']} (launched {config['launch']})")
    
    # Show leverage decay demo
    demonstrate_leverage_decay()
