#!/usr/bin/env python3
"""Quick check a stock's signals"""
import sys
import yfinance as yf
import pandas as pd
import numpy as np

# Add parent dir for imports
from sbi_calculator import get_full_sbi_data, calculate_psar_arrays, calculate_rsi_array

def check_stock(ticker):
    print(f"\nChecking {ticker}...")
    df = yf.download(ticker, period='6mo', progress=False)
    
    if len(df) < 30:
        print(f"  Not enough data: {len(df)} days")
        return
    
    close = np.array(df['Close'].values, dtype=float)
    high = np.array(df['High'].values, dtype=float)
    low = np.array(df['Low'].values, dtype=float)
    
    # Remove NaN
    valid = ~(np.isnan(close) | np.isnan(high) | np.isnan(low))
    close, high, low = close[valid], high[valid], low[valid]
    
    # Create DataFrame for SBI
    temp_df = pd.DataFrame({'High': high, 'Low': low, 'Close': close})
    sbi_result = get_full_sbi_data(temp_df)
    
    # PSAR
    psar = calculate_psar_arrays(high, low, close)
    psar_bullish = close[-1] > psar[-1]
    
    # RSI
    rsi_arr = calculate_rsi_array(close, 14)
    rsi = rsi_arr[-1]
    
    print(f"  Price: ${close[-1]:.2f}")
    print(f"  PSAR: ${psar[-1]:.2f} ({'BULLISH' if psar_bullish else 'BEARISH'})")
    print(f"  RSI: {rsi:.1f}")
    print(f"  SBI: {sbi_result.sbi if sbi_result else 'None'}")
    
    # Entry check
    qualifies = sbi_result and sbi_result.sbi >= 9 and psar_bullish and rsi > 50
    print(f"\n  QUALIFIES: {'YES ✓' if qualifies else 'NO ✗'}")
    if not qualifies and sbi_result:
        if sbi_result.sbi < 9:
            print(f"    - SBI {sbi_result.sbi} < 9")
        if not psar_bullish:
            print(f"    - PSAR bearish")
        if rsi <= 50:
            print(f"    - RSI {rsi:.1f} <= 50")

if __name__ == "__main__":
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ['MSTR', 'COIN', 'RIOT']
    for t in tickers:
        check_stock(t)
