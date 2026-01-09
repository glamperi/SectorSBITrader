"""
SBI (Smart Buy Indicator) Calculator
====================================
Exact implementation from market-psar-scanner main.py

SBI measures entry quality on a 0-10 scale:
- 10 = Perfect entry (fresh signal, low volatility, strong trend)
- 9 = Excellent entry
- 8 = Good entry (threshold for Strong Buy)
- 0 = Broken (stock crashed through PSAR - NOT a buy)

Formula varies by days since PSAR cross:
- Day 1: 100% ATR score (no slope data yet)
- Day 2: 80% ATR + 20% Slope
- Day 3: 60% ATR + 40% Slope
- Days 4-5: 40% ATR + 40% Slope + 20% ADX
- Days 6+: 40% Slope + 30% ADX + 30% ATR

PRSI(4) bearish applies -2 penalty for Days 3+ (momentum warning)
"""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class SBIResult:
    """Result of SBI calculation."""
    sbi: int  # 0-10 score
    days_in_trend: int
    atr_percent: float
    gap_slope: float
    adx_value: float
    prsi_fast_bearish: bool
    is_broken: bool
    components: Dict[str, int]  # Individual component scores


# =============================================================================
# PSAR CALCULATION
# =============================================================================

def calculate_psar(df: pd.DataFrame, af: float = 0.02, max_af: float = 0.2) -> pd.Series:
    """
    Calculate Parabolic SAR for a price series.
    """
    high = df['High'].values
    low = df['Low'].values
    close = df['Close'].values
    
    psar_arr = calculate_psar_arrays(high, low, close, af, max_af)
    return pd.Series(psar_arr, index=df.index)


def calculate_psar_arrays(high: np.ndarray, low: np.ndarray, close: np.ndarray, 
                          af: float = 0.02, max_af: float = 0.2) -> np.ndarray:
    """
    Calculate Parabolic SAR using numpy arrays.
    This is the core implementation that works with raw arrays.
    """
    length = len(high)
    psar = np.zeros(length)
    trend = np.zeros(length)  # 1 = uptrend, -1 = downtrend
    ep = np.zeros(length)  # Extreme point
    af_arr = np.zeros(length)
    
    # Initialize
    trend[0] = 1  # Start assuming uptrend
    psar[0] = low[0]
    ep[0] = high[0]
    af_arr[0] = af
    
    for i in range(1, length):
        prev_psar = psar[i-1]
        prev_af = af_arr[i-1]
        prev_ep = ep[i-1]
        prev_trend = trend[i-1]
        
        if prev_trend == 1:  # Was in uptrend
            new_psar = prev_psar + prev_af * (prev_ep - prev_psar)
            new_psar = min(new_psar, low[i-1])
            if i >= 2:
                new_psar = min(new_psar, low[i-2])
            
            if low[i] < new_psar:
                # Reversal to downtrend
                trend[i] = -1
                psar[i] = prev_ep
                ep[i] = low[i]
                af_arr[i] = af
            else:
                # Continue uptrend
                trend[i] = 1
                psar[i] = new_psar
                if high[i] > prev_ep:
                    ep[i] = high[i]
                    af_arr[i] = min(prev_af + af, max_af)
                else:
                    ep[i] = prev_ep
                    af_arr[i] = prev_af
        else:  # Was in downtrend
            new_psar = prev_psar + prev_af * (prev_ep - prev_psar)
            new_psar = max(new_psar, high[i-1])
            if i >= 2:
                new_psar = max(new_psar, high[i-2])
            
            if high[i] > new_psar:
                # Reversal to uptrend
                trend[i] = 1
                psar[i] = prev_ep
                ep[i] = high[i]
                af_arr[i] = af
            else:
                # Continue downtrend
                trend[i] = -1
                psar[i] = new_psar
                if low[i] < prev_ep:
                    ep[i] = low[i]
                    af_arr[i] = min(prev_af + af, max_af)
                else:
                    ep[i] = prev_ep
                    af_arr[i] = prev_af
    
    return psar


def get_psar_trend(price: float, psar: float) -> str:
    """Determine if price is above or below PSAR."""
    return 'bullish' if price > psar else 'bearish'


def calculate_psar_gap(price: float, psar: float) -> float:
    """Calculate percentage gap between price and PSAR."""
    if psar == 0:
        return 0.0
    return ((price - psar) / psar) * 100


# =============================================================================
# ADX / DMI CALCULATION
# =============================================================================

def calculate_adx(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculate ADX (Average Directional Index) and +DI/-DI."""
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    
    tr = pd.concat([
        high - low,
        abs(high - close.shift(1)),
        abs(low - close.shift(1))
    ], axis=1).max(axis=1)
    
    atr = tr.ewm(span=period, adjust=False).mean()
    plus_di = 100 * (plus_dm.ewm(span=period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(span=period, adjust=False).mean() / atr)
    
    dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
    adx = dx.ewm(span=period, adjust=False).mean()
    
    return adx, plus_di, minus_di


def calculate_adx_arrays(high: np.ndarray, low: np.ndarray, close: np.ndarray, 
                         period: int = 14) -> Dict[str, np.ndarray]:
    """
    Calculate ADX using numpy arrays.
    Returns dict with 'adx', 'plus_di', 'minus_di' arrays.
    """
    length = len(high)
    
    # Calculate +DM and -DM
    plus_dm = np.zeros(length)
    minus_dm = np.zeros(length)
    tr = np.zeros(length)
    
    for i in range(1, length):
        up_move = high[i] - high[i-1]
        down_move = low[i-1] - low[i]
        
        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        else:
            plus_dm[i] = 0
            
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move
        else:
            minus_dm[i] = 0
        
        # True Range
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i-1]),
            abs(low[i] - close[i-1])
        )
    
    # EMA smoothing
    alpha = 2.0 / (period + 1)
    
    atr = np.zeros(length)
    smoothed_plus_dm = np.zeros(length)
    smoothed_minus_dm = np.zeros(length)
    
    # Initialize
    atr[period-1] = np.mean(tr[1:period])
    smoothed_plus_dm[period-1] = np.mean(plus_dm[1:period])
    smoothed_minus_dm[period-1] = np.mean(minus_dm[1:period])
    
    for i in range(period, length):
        atr[i] = alpha * tr[i] + (1 - alpha) * atr[i-1]
        smoothed_plus_dm[i] = alpha * plus_dm[i] + (1 - alpha) * smoothed_plus_dm[i-1]
        smoothed_minus_dm[i] = alpha * minus_dm[i] + (1 - alpha) * smoothed_minus_dm[i-1]
    
    # Calculate +DI and -DI
    plus_di = np.zeros(length)
    minus_di = np.zeros(length)
    dx = np.zeros(length)
    
    for i in range(period, length):
        if atr[i] > 0:
            plus_di[i] = 100 * smoothed_plus_dm[i] / atr[i]
            minus_di[i] = 100 * smoothed_minus_dm[i] / atr[i]
        
        if plus_di[i] + minus_di[i] > 0:
            dx[i] = 100 * abs(plus_di[i] - minus_di[i]) / (plus_di[i] + minus_di[i])
    
    # Smooth DX to get ADX
    adx = np.zeros(length)
    adx[2*period-1] = np.mean(dx[period:2*period])
    
    for i in range(2*period, length):
        adx[i] = alpha * dx[i] + (1 - alpha) * adx[i-1]
    
    return {
        'adx': adx,
        'plus_di': plus_di,
        'minus_di': minus_di
    }


# =============================================================================
# ATR CALCULATION
# =============================================================================

def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Calculate Average True Range."""
    high = df['High']
    low = df['Low']
    close = df['Close']
    
    tr = pd.concat([
        high - low,
        abs(high - close.shift(1)),
        abs(low - close.shift(1))
    ], axis=1).max(axis=1)
    
    return tr.ewm(span=period, adjust=False).mean()


def get_atr_volatility(df: pd.DataFrame, period: int = 14) -> float:
    """Get ATR as percentage of current price (volatility measure)."""
    atr = calculate_atr(df, period)
    current_price = df['Close'].iloc[-1]
    return (atr.iloc[-1] / current_price) * 100


# =============================================================================
# PRSI CALCULATION (PSAR on RSI)
# =============================================================================

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI from pandas Series."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_rsi_array(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Calculate RSI from numpy array."""
    length = len(close)
    rsi = np.zeros(length)
    
    if length < period + 1:
        return rsi
    
    # Calculate price changes
    delta = np.diff(close)
    
    # Separate gains and losses
    gains = np.where(delta > 0, delta, 0)
    losses = np.where(delta < 0, -delta, 0)
    
    # First average (simple)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    # First RSI value
    if avg_loss > 0:
        rs = avg_gain / avg_loss
        rsi[period] = 100 - (100 / (1 + rs))
    else:
        rsi[period] = 100
    
    # Subsequent values using EMA
    for i in range(period, length - 1):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        if avg_loss > 0:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100 - (100 / (1 + rs))
        else:
            rsi[i + 1] = 100
    
    return rsi


def calculate_psar_on_series(series: pd.Series, af: float = 0.02, max_af: float = 0.2) -> Tuple[pd.Series, pd.Series]:
    """Calculate PSAR on any series (used for PRSI)."""
    values = series.values
    length = len(series)
    
    psar = np.zeros(length)
    trend = np.zeros(length)
    ep = np.zeros(length)
    af_arr = np.zeros(length)
    
    # Find first valid value
    start_idx = 0
    for i in range(length):
        if not np.isnan(values[i]):
            start_idx = i
            break
    
    if start_idx >= length - 1:
        return pd.Series(index=series.index, dtype=float), pd.Series(index=series.index, dtype=float)
    
    trend[start_idx] = 1
    psar[start_idx] = values[start_idx] * 0.98
    ep[start_idx] = values[start_idx]
    af_arr[start_idx] = af
    
    for i in range(start_idx + 1, length):
        if np.isnan(values[i]):
            psar[i] = psar[i-1]
            trend[i] = trend[i-1]
            ep[i] = ep[i-1]
            af_arr[i] = af_arr[i-1]
            continue
        
        prev_psar = psar[i-1]
        prev_af = af_arr[i-1]
        prev_ep = ep[i-1]
        prev_trend = trend[i-1]
        
        if prev_trend == 1:  # Uptrend
            new_psar = prev_psar + prev_af * (prev_ep - prev_psar)
            
            if values[i] < new_psar:
                trend[i] = -1
                psar[i] = prev_ep
                ep[i] = values[i]
                af_arr[i] = af
            else:
                trend[i] = 1
                psar[i] = new_psar
                if values[i] > prev_ep:
                    ep[i] = values[i]
                    af_arr[i] = min(prev_af + af, max_af)
                else:
                    ep[i] = prev_ep
                    af_arr[i] = prev_af
        else:  # Downtrend
            new_psar = prev_psar + prev_af * (prev_ep - prev_psar)
            
            if values[i] > new_psar:
                trend[i] = 1
                psar[i] = prev_ep
                ep[i] = values[i]
                af_arr[i] = af
            else:
                trend[i] = -1
                psar[i] = new_psar
                if values[i] < prev_ep:
                    ep[i] = values[i]
                    af_arr[i] = min(prev_af + af, max_af)
                else:
                    ep[i] = prev_ep
                    af_arr[i] = prev_af
    
    return pd.Series(psar, index=series.index), pd.Series(trend, index=series.index)


def get_prsi_fast_bearish(df: pd.DataFrame) -> bool:
    """Check if PRSI(4) is bearish (fast momentum warning)."""
    try:
        rsi_fast = calculate_rsi(df['Close'], period=4)
        prsi_psar, prsi_trend = calculate_psar_on_series(rsi_fast)
        
        current_rsi = rsi_fast.iloc[-1]
        current_prsi = prsi_psar.iloc[-1]
        
        # PRSI(4) is bearish if RSI is below its PSAR
        return current_rsi < current_prsi
    except:
        return False


# =============================================================================
# SBI CALCULATION (Main Function)
# =============================================================================

def calculate_sbi(
    days_in_trend: int,
    atr_percent: float,
    gap_slope: float,
    adx_value: float = 20,
    prsi_fast_bearish: bool = False,
    is_broken: bool = False
) -> int:
    """
    Calculate Smart Buy Indicator (SBI) 0-10.
    
    Exact implementation from market-psar-scanner main.py
    
    Args:
        days_in_trend: Days since PSAR crossed
        atr_percent: ATR as % of price (volatility)
        gap_slope: Change in PSAR gap since cross (positive = widening = good)
        adx_value: ADX trend strength (higher = stronger trend)
        prsi_fast_bearish: True if PRSI(4) is bearish (momentum warning)
        is_broken: True if stock recently broke DOWN through PSAR
    
    Returns:
        SBI score 0-10 (10 = best)
    """
    # If broken (crashed through PSAR), SBI = 0 - this is NOT a buy
    if is_broken:
        return 0
    
    # ATR score - day-specific thresholds
    if days_in_trend == 1:
        atr_score = 10 if atr_percent < 7 else 4
    elif days_in_trend == 2:
        atr_score = 10 if atr_percent < 6 else 4
    elif days_in_trend in [3, 4]:
        atr_score = 10 if atr_percent < 5 else 4
    elif days_in_trend == 5:
        if atr_percent < 4:
            atr_score = 10
        elif atr_percent < 5:
            atr_score = 8
        elif atr_percent < 6:
            atr_score = 6
        else:
            atr_score = 4
    else:
        # Days 6+ use gradual ATR scoring
        if atr_percent < 2:
            atr_score = 10
        elif atr_percent < 2.5:
            atr_score = 9
        elif atr_percent < 3:
            atr_score = 8
        elif atr_percent < 4:
            atr_score = 7
        elif atr_percent < 5:
            atr_score = 6
        else:
            atr_score = 4
    
    # Slope score: gap widening = good, narrowing = bad
    if gap_slope >= 2:
        slope_score = 10  # Strongly widening
    elif gap_slope >= 1:
        slope_score = 9   # Widening
    elif gap_slope >= 0.5:
        slope_score = 8   # Slightly widening
    elif gap_slope >= -0.5:
        slope_score = 7   # Stable
    elif gap_slope >= -1:
        slope_score = 5   # Slightly narrowing
    elif gap_slope >= -2:
        slope_score = 3   # Narrowing
    else:
        slope_score = 1   # Strongly narrowing (trend exhausting)
    
    # ADX score: higher ADX = stronger trend = better
    if adx_value >= 40:
        adx_score = 10  # Very strong trend
    elif adx_value >= 30:
        adx_score = 8   # Strong trend
    elif adx_value >= 25:
        adx_score = 6   # Moderate trend
    elif adx_value >= 20:
        adx_score = 4   # Weak trend
    else:
        adx_score = 2   # Choppy/no trend
    
    # Calculate SBI based on days in trend
    if days_in_trend == 1:
        # Day 1: ATR only (no slope data yet)
        sbi = atr_score
    elif days_in_trend == 2:
        # Day 2: 80% ATR + 20% Slope
        sbi = int(0.8 * atr_score + 0.2 * slope_score)
    elif days_in_trend == 3:
        # Day 3: 60% ATR + 40% Slope
        sbi = int(0.6 * atr_score + 0.4 * slope_score)
    elif days_in_trend in [4, 5]:
        # Days 4-5: 40% ATR + 40% Slope + 20% ADX
        sbi = int(0.4 * atr_score + 0.4 * slope_score + 0.2 * adx_score)
    else:
        # Days 6+: 40% Slope + 30% ADX + 30% ATR
        sbi = int(0.4 * slope_score + 0.3 * adx_score + 0.3 * atr_score)
    
    # Apply PRSI(4) penalty for Days 3+ (momentum warning)
    if prsi_fast_bearish and days_in_trend >= 3:
        sbi = sbi - 2
    
    return max(0, min(10, sbi))


def get_full_sbi_data(df: pd.DataFrame) -> Optional[SBIResult]:
    """
    Calculate full SBI data for a stock.
    
    Args:
        df: DataFrame with OHLC + Volume data
    
    Returns:
        SBIResult with all components, or None if insufficient data
    """
    if len(df) < 20:
        return None
    
    try:
        # Calculate PSAR
        psar_series = calculate_psar(df)
        current_psar = psar_series.iloc[-1]
        current_price = df['Close'].iloc[-1]
        
        gap_percent = calculate_psar_gap(current_price, current_psar)
        trend = get_psar_trend(current_price, current_psar)
        
        # Count days in current trend
        days_in_trend = 1
        for i in range(len(df) - 2, -1, -1):
            price = df['Close'].iloc[i]
            psar = psar_series.iloc[i]
            if get_psar_trend(price, psar) == trend:
                days_in_trend += 1
            else:
                break
        
        # Detect if broken (recently crossed DOWN through PSAR)
        is_broken = False
        if days_in_trend <= 5 and trend == 'bearish':
            # Look at the day before the cross
            cross_idx = len(df) - days_in_trend - 1
            if cross_idx >= 0:
                prev_price = df['Close'].iloc[cross_idx]
                prev_psar = psar_series.iloc[cross_idx]
                prev_trend = get_psar_trend(prev_price, prev_psar)
                if prev_trend == 'bullish':
                    is_broken = True  # This is a BREAKDOWN
        
        # Calculate gap slope (change since cross)
        gap_slope = 0.0
        if days_in_trend >= 2:
            lookback = min(3, days_in_trend - 1)
            if lookback >= 1:
                price_lookback = df['Close'].iloc[-(lookback + 1)]
                psar_lookback = psar_series.iloc[-(lookback + 1)]
                gap_lookback = calculate_psar_gap(price_lookback, psar_lookback)
                gap_slope = gap_percent - gap_lookback
        
        # Get ATR volatility
        atr_percent = get_atr_volatility(df)
        
        # Get ADX value
        adx_series, plus_di, minus_di = calculate_adx(df)
        adx_value = adx_series.iloc[-1] if not pd.isna(adx_series.iloc[-1]) else 20
        
        # Get PRSI(4) status
        prsi_fast_bearish = get_prsi_fast_bearish(df)
        
        # Calculate SBI
        sbi = calculate_sbi(
            days_in_trend=days_in_trend,
            atr_percent=atr_percent,
            gap_slope=gap_slope,
            adx_value=adx_value,
            prsi_fast_bearish=prsi_fast_bearish,
            is_broken=is_broken
        )
        
        # Calculate component scores for debugging
        if days_in_trend == 1:
            atr_score = 10 if atr_percent < 7 else 4
        elif days_in_trend == 2:
            atr_score = 10 if atr_percent < 6 else 4
        elif days_in_trend in [3, 4]:
            atr_score = 10 if atr_percent < 5 else 4
        elif days_in_trend == 5:
            atr_score = 10 if atr_percent < 4 else (8 if atr_percent < 5 else (6 if atr_percent < 6 else 4))
        else:
            atr_score = 10 if atr_percent < 2 else (9 if atr_percent < 2.5 else (8 if atr_percent < 3 else (7 if atr_percent < 4 else (6 if atr_percent < 5 else 4))))
        
        if gap_slope >= 2: slope_score = 10
        elif gap_slope >= 1: slope_score = 9
        elif gap_slope >= 0.5: slope_score = 8
        elif gap_slope >= -0.5: slope_score = 7
        elif gap_slope >= -1: slope_score = 5
        elif gap_slope >= -2: slope_score = 3
        else: slope_score = 1
        
        if adx_value >= 40: adx_score = 10
        elif adx_value >= 30: adx_score = 8
        elif adx_value >= 25: adx_score = 6
        elif adx_value >= 20: adx_score = 4
        else: adx_score = 2
        
        return SBIResult(
            sbi=sbi,
            days_in_trend=days_in_trend,
            atr_percent=atr_percent,
            gap_slope=gap_slope,
            adx_value=adx_value,
            prsi_fast_bearish=prsi_fast_bearish,
            is_broken=is_broken,
            components={
                'atr_score': atr_score,
                'slope_score': slope_score,
                'adx_score': adx_score,
                'trend': trend,
                'psar_gap': gap_percent,
            }
        )
    
    except Exception as e:
        print(f"Error calculating SBI: {e}")
        return None


def is_parent_bullish(df: pd.DataFrame) -> bool:
    """
    Check if a parent ticker (ETF/crypto) is in bullish PSAR trend.
    Used to determine if sector is active.
    """
    if len(df) < 10:
        return False
    
    try:
        psar_series = calculate_psar(df)
        current_psar = psar_series.iloc[-1]
        current_price = df['Close'].iloc[-1]
        return current_price > current_psar
    except:
        return False


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    import yfinance as yf
    
    print("SBI Calculator Test")
    print("=" * 60)
    
    test_tickers = ['MSTR', 'NVDA', 'AAPL', 'GDX', 'COIN']
    
    for ticker in test_tickers:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="6mo")
            
            if len(df) > 20:
                result = get_full_sbi_data(df)
                if result:
                    print(f"\n{ticker}:")
                    print(f"  SBI: {result.sbi}/10")
                    print(f"  Days in trend: {result.days_in_trend}")
                    print(f"  ATR%: {result.atr_percent:.2f}%")
                    print(f"  Gap slope: {result.gap_slope:+.2f}")
                    print(f"  ADX: {result.adx_value:.1f}")
                    print(f"  PRSI(4) bearish: {result.prsi_fast_bearish}")
                    print(f"  Is broken: {result.is_broken}")
                    print(f"  Trend: {result.components['trend']}")
        except Exception as e:
            print(f"\n{ticker}: Error - {e}")
