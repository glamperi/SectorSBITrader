"""
SectorSBITrader - Signal Bullish Index (SBI) Calculator

SBI is a 10-point scoring system that measures how bullish a stock is.
Entry requires SBI >= 9 (all or nearly all indicators bullish).

SBI Components (10 points total):
  1. Price > 20 SMA (short-term trend)
  2. Price > 50 SMA (intermediate trend)
  3. Price > 200 SMA (long-term trend)
  4. RSI(14) > 50 (momentum positive)
  5. RSI(14) < 70 (not overbought)
  6. MACD > Signal Line (momentum confirmation)
  7. MACD Histogram > 0 (momentum accelerating)
  8. Price > PSAR (trend confirmation)
  9. 20-day momentum > 0 (positive returns)
  10. Volume > 20-day average (accumulation)

Entry Logic:
  - SBI = 10 → 2x weight
  - SBI = 9 → 1x weight
  - SBI < 9 → No entry
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional


@dataclass
class SBIResult:
    """Result of SBI calculation for a single stock."""
    ticker: str
    sbi_score: int  # 0-10
    components: Dict[str, bool]  # Individual indicator results
    price: float
    weight_multiplier: float  # 2x for SBI=10, 1x for SBI=9, 0 otherwise
    details: Dict[str, float]  # Detailed indicator values
    
    def is_entry_signal(self) -> bool:
        """Check if stock qualifies for entry (SBI >= 9)."""
        return self.sbi_score >= 9
    
    def __str__(self) -> str:
        status = "✅ ENTRY" if self.is_entry_signal() else "❌ SKIP"
        return f"{self.ticker}: SBI={self.sbi_score}/10 ({self.weight_multiplier}x) {status}"


class TechnicalIndicators:
    """Technical indicator calculations for SBI scoring."""
    
    @staticmethod
    def sma(prices: pd.Series, period: int) -> pd.Series:
        """Simple Moving Average."""
        return prices.rolling(window=period).mean()
    
    @staticmethod
    def ema(prices: pd.Series, period: int) -> pd.Series:
        """Exponential Moving Average."""
        return prices.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """Relative Strength Index."""
        delta = prices.diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """MACD indicator.
        
        Returns:
            (macd_line, signal_line, histogram)
        """
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram
    
    @staticmethod
    def psar(prices: pd.Series, af: float = 0.02, max_af: float = 0.2) -> pd.Series:
        """Parabolic SAR.
        
        Note: This is a simplified version using close prices only.
        For more accuracy, use OHLC data.
        """
        length = len(prices)
        psar = prices.copy()
        af_current = af
        ep = prices.iloc[0]
        is_uptrend = True
        
        for i in range(2, length):
            if is_uptrend:
                psar.iloc[i] = psar.iloc[i-1] + af_current * (ep - psar.iloc[i-1])
                psar.iloc[i] = min(psar.iloc[i], prices.iloc[i-1], prices.iloc[i-2])
                
                if prices.iloc[i] > ep:
                    ep = prices.iloc[i]
                    af_current = min(af_current + af, max_af)
                
                if prices.iloc[i] < psar.iloc[i]:
                    is_uptrend = False
                    psar.iloc[i] = ep
                    ep = prices.iloc[i]
                    af_current = af
            else:
                psar.iloc[i] = psar.iloc[i-1] - af_current * (psar.iloc[i-1] - ep)
                psar.iloc[i] = max(psar.iloc[i], prices.iloc[i-1], prices.iloc[i-2])
                
                if prices.iloc[i] < ep:
                    ep = prices.iloc[i]
                    af_current = min(af_current + af, max_af)
                
                if prices.iloc[i] > psar.iloc[i]:
                    is_uptrend = True
                    psar.iloc[i] = ep
                    ep = prices.iloc[i]
                    af_current = af
        
        return psar
    
    @staticmethod
    def momentum(prices: pd.Series, period: int = 20) -> float:
        """Calculate percentage return over period."""
        if len(prices) < period + 1:
            return 0.0
        return ((prices.iloc[-1] - prices.iloc[-period-1]) / prices.iloc[-period-1]) * 100


class SBICalculator:
    """
    Signal Bullish Index Calculator.
    
    Calculates a 10-point score for each stock based on technical indicators.
    """
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
    
    def calculate(self, ticker: str, prices: pd.Series, volume: pd.Series = None) -> SBIResult:
        """
        Calculate SBI score for a stock.
        
        Args:
            ticker: Stock symbol
            prices: Price series (at least 201 days for SMA200)
            volume: Volume series (optional, for volume indicator)
        
        Returns:
            SBIResult with score and details
        """
        # Check minimum data requirement
        if len(prices) < 201:
            return SBIResult(
                ticker=ticker,
                sbi_score=0,
                components={},
                price=0,
                weight_multiplier=0,
                details={'error': 'Insufficient data (need 201+ days)'}
            )
        
        current_price = float(prices.iloc[-1])
        components = {}
        details = {}
        
        # =========================================
        # SBI Component 1: Price > SMA(20)
        # =========================================
        sma_20 = self.indicators.sma(prices, 20).iloc[-1]
        components['price_above_sma20'] = current_price > sma_20
        details['sma_20'] = sma_20
        
        # =========================================
        # SBI Component 2: Price > SMA(50)
        # =========================================
        sma_50 = self.indicators.sma(prices, 50).iloc[-1]
        components['price_above_sma50'] = current_price > sma_50
        details['sma_50'] = sma_50
        
        # =========================================
        # SBI Component 3: Price > SMA(200)
        # =========================================
        sma_200 = self.indicators.sma(prices, 200).iloc[-1]
        components['price_above_sma200'] = current_price > sma_200
        details['sma_200'] = sma_200
        
        # =========================================
        # SBI Component 4: RSI(14) > 50
        # =========================================
        rsi = self.indicators.rsi(prices, 14).iloc[-1]
        components['rsi_above_50'] = rsi > 50
        details['rsi_14'] = rsi
        
        # =========================================
        # SBI Component 5: RSI(14) < 70 (not overbought)
        # =========================================
        components['rsi_below_70'] = rsi < 70
        
        # =========================================
        # SBI Component 6: MACD > Signal Line
        # =========================================
        macd_line, signal_line, histogram = self.indicators.macd(prices)
        components['macd_above_signal'] = macd_line.iloc[-1] > signal_line.iloc[-1]
        details['macd'] = macd_line.iloc[-1]
        details['macd_signal'] = signal_line.iloc[-1]
        
        # =========================================
        # SBI Component 7: MACD Histogram > 0
        # =========================================
        components['macd_histogram_positive'] = histogram.iloc[-1] > 0
        details['macd_histogram'] = histogram.iloc[-1]
        
        # =========================================
        # SBI Component 8: Price > PSAR
        # =========================================
        psar = self.indicators.psar(prices)
        components['price_above_psar'] = current_price > psar.iloc[-1]
        details['psar'] = psar.iloc[-1]
        
        # =========================================
        # SBI Component 9: 20-day Momentum > 0
        # =========================================
        momentum = self.indicators.momentum(prices, 20)
        components['momentum_positive'] = momentum > 0
        details['momentum_20d'] = momentum
        
        # =========================================
        # SBI Component 10: Volume > 20-day Average
        # =========================================
        if volume is not None and len(volume) >= 20:
            avg_volume = volume.rolling(20).mean().iloc[-1]
            current_volume = volume.iloc[-1]
            components['volume_above_avg'] = current_volume > avg_volume
            details['volume'] = current_volume
            details['volume_avg_20d'] = avg_volume
        else:
            # Default to True if no volume data (don't penalize)
            components['volume_above_avg'] = True
            details['volume'] = None
        
        # =========================================
        # Calculate SBI Score
        # =========================================
        sbi_score = sum(1 for v in components.values() if v)
        
        # Determine weight multiplier
        if sbi_score == 10:
            weight_multiplier = 2.0
        elif sbi_score == 9:
            weight_multiplier = 1.0
        else:
            weight_multiplier = 0.0
        
        return SBIResult(
            ticker=ticker,
            sbi_score=sbi_score,
            components=components,
            price=current_price,
            weight_multiplier=weight_multiplier,
            details=details
        )
    
    def calculate_batch(self, price_data: Dict[str, pd.Series], 
                        volume_data: Dict[str, pd.Series] = None) -> Dict[str, SBIResult]:
        """
        Calculate SBI for multiple stocks.
        
        Args:
            price_data: Dict mapping ticker to price series
            volume_data: Dict mapping ticker to volume series (optional)
        
        Returns:
            Dict mapping ticker to SBIResult
        """
        results = {}
        volume_data = volume_data or {}
        
        for ticker, prices in price_data.items():
            volume = volume_data.get(ticker)
            results[ticker] = self.calculate(ticker, prices, volume)
        
        return results
    
    def get_entry_candidates(self, results: Dict[str, SBIResult]) -> List[SBIResult]:
        """
        Get stocks that qualify for entry (SBI >= 9).
        
        Returns list sorted by SBI score (10s first, then 9s).
        """
        candidates = [r for r in results.values() if r.is_entry_signal()]
        # Sort by SBI score descending
        candidates.sort(key=lambda x: x.sbi_score, reverse=True)
        return candidates


def print_sbi_breakdown(result: SBIResult):
    """Print detailed SBI breakdown for a stock."""
    print(f"\n{'='*50}")
    print(f"SBI Analysis: {result.ticker}")
    print(f"{'='*50}")
    print(f"Price: ${result.price:.2f}")
    print(f"SBI Score: {result.sbi_score}/10")
    print(f"Weight Multiplier: {result.weight_multiplier}x")
    print(f"Entry Signal: {'YES ✅' if result.is_entry_signal() else 'NO ❌'}")
    print()
    print("Component Breakdown:")
    print("-" * 50)
    
    component_names = {
        'price_above_sma20': 'Price > SMA(20)',
        'price_above_sma50': 'Price > SMA(50)',
        'price_above_sma200': 'Price > SMA(200)',
        'rsi_above_50': 'RSI(14) > 50',
        'rsi_below_70': 'RSI(14) < 70',
        'macd_above_signal': 'MACD > Signal',
        'macd_histogram_positive': 'MACD Histogram > 0',
        'price_above_psar': 'Price > PSAR',
        'momentum_positive': '20d Momentum > 0%',
        'volume_above_avg': 'Volume > 20d Avg',
    }
    
    for key, name in component_names.items():
        if key in result.components:
            status = "✅" if result.components[key] else "❌"
            print(f"  {status} {name}")
    
    print()
    print("Indicator Values:")
    print("-" * 50)
    if 'sma_20' in result.details:
        print(f"  SMA(20):  ${result.details['sma_20']:.2f}")
    if 'sma_50' in result.details:
        print(f"  SMA(50):  ${result.details['sma_50']:.2f}")
    if 'sma_200' in result.details:
        print(f"  SMA(200): ${result.details['sma_200']:.2f}")
    if 'rsi_14' in result.details:
        print(f"  RSI(14):  {result.details['rsi_14']:.1f}")
    if 'macd' in result.details:
        print(f"  MACD:     {result.details['macd']:.4f}")
    if 'macd_signal' in result.details:
        print(f"  Signal:   {result.details['macd_signal']:.4f}")
    if 'psar' in result.details:
        print(f"  PSAR:     ${result.details['psar']:.2f}")
    if 'momentum_20d' in result.details:
        print(f"  Momentum: {result.details['momentum_20d']:.1f}%")


if __name__ == "__main__":
    # Demo with sample data
    print("SBI Calculator Demo")
    print("=" * 50)
    print("\nSBI = Signal Bullish Index (0-10 points)")
    print("  SBI = 10 → 2x weight (all indicators bullish)")
    print("  SBI = 9  → 1x weight (9/10 indicators bullish)")
    print("  SBI < 9  → No entry")
    print("\nComponents:")
    print("  1. Price > SMA(20)")
    print("  2. Price > SMA(50)")
    print("  3. Price > SMA(200)")
    print("  4. RSI(14) > 50")
    print("  5. RSI(14) < 70")
    print("  6. MACD > Signal")
    print("  7. MACD Histogram > 0")
    print("  8. Price > PSAR")
    print("  9. 20d Momentum > 0%")
    print(" 10. Volume > 20d Avg")
