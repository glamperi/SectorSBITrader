"""
SectorSBITrader - Main Strategy Module

Strategy Logic:
1. Check parent signal (sector ETF or asset) using PSAR
2. When parent is bullish, scan child stocks for SBI scores
3. Enter stocks with SBI=10 (2x weight) or SBI=9 (1x weight)
4. Lock weights until parent turns bearish
5. Exit ALL sector positions when parent goes bearish

Key Rules:
- Parent signal controls entry/exit timing
- SBI score determines WHICH stocks to buy
- Weights are locked at entry (don't adjust if SBI changes)
- No leverage on individual stocks (1x only)
"""

import pandas as pd
import numpy as np
from datetime import datetime
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from enum import Enum

from config import PARENT_CHILD_MAPPING, DEFAULT_CONFIG, get_parents_by_category
from sbi_calculator import SBICalculator, SBIResult, TechnicalIndicators


class ParentSignal(Enum):
    """Parent signal states."""
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    UNKNOWN = "UNKNOWN"


@dataclass
class Position:
    """Represents a position in a stock."""
    ticker: str
    parent: str  # Parent signal that triggered this position
    entry_date: datetime
    entry_price: float
    entry_sbi: int
    weight_multiplier: float  # 2x for SBI=10, 1x for SBI=9
    shares: float = 0
    current_price: float = 0
    
    def unrealized_pnl(self) -> float:
        """Calculate unrealized P&L."""
        return (self.current_price - self.entry_price) * self.shares
    
    def unrealized_pnl_pct(self) -> float:
        """Calculate unrealized P&L percentage."""
        if self.entry_price == 0:
            return 0
        return ((self.current_price - self.entry_price) / self.entry_price) * 100


@dataclass
class SectorAnalysis:
    """Analysis results for a single sector."""
    parent: str
    description: str
    category: str
    parent_signal: ParentSignal
    parent_reason: str
    stocks: List[SBIResult]
    entry_candidates: List[SBIResult]  # Stocks with SBI >= 9
    
    def has_entry_signals(self) -> bool:
        """Check if sector has any entry signals."""
        return self.parent_signal == ParentSignal.BULLISH and len(self.entry_candidates) > 0


@dataclass
class PortfolioAllocation:
    """Target portfolio allocation."""
    positions: Dict[str, float]  # ticker -> target weight
    reasoning: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    sector_details: Dict[str, SectorAnalysis] = field(default_factory=dict)
    
    def __str__(self):
        if not self.positions:
            return "100% CASH"
        parts = [f"{w*100:.1f}% {t}" for t, w in sorted(self.positions.items(), key=lambda x: -x[1])]
        return " | ".join(parts[:10]) + (f" ... +{len(self.positions)-10} more" if len(self.positions) > 10 else "")


class SectorSBIStrategy:
    """
    Sector SBI Trading Strategy.
    
    Uses sector/asset signals to determine timing, then drills into
    individual stocks using the Signal Bullish Index (SBI).
    """
    
    def __init__(self, price_data: Dict[str, pd.Series] = None,
                 volume_data: Dict[str, pd.Series] = None,
                 config=None):
        """
        Args:
            price_data: Dict mapping ticker to price series
            volume_data: Dict mapping ticker to volume series
            config: Strategy configuration (uses DEFAULT_CONFIG if None)
        """
        self.price_data = price_data or {}
        self.volume_data = volume_data or {}
        self.config = config or DEFAULT_CONFIG
        self.sbi_calc = SBICalculator()
        self.indicators = TechnicalIndicators()
        
        # Track current positions by parent
        self.positions_by_parent: Dict[str, List[Position]] = {}
        
        # Cache for parent signals
        self._parent_signal_cache: Dict[str, Tuple[ParentSignal, str]] = {}
    
    def _get_prices(self, ticker: str) -> pd.Series:
        """Get price series for a ticker."""
        return self.price_data.get(ticker, pd.Series())
    
    def _get_volume(self, ticker: str) -> pd.Series:
        """Get volume series for a ticker."""
        return self.volume_data.get(ticker, pd.Series())
    
    def check_parent_signal(self, parent_ticker: str) -> Tuple[ParentSignal, str]:
        """
        Check if parent signal is bullish using PSAR on price.
        
        This mirrors AdaptiveX2 logic - simple PSAR check.
        
        Args:
            parent_ticker: Parent ETF/asset ticker (e.g., 'BTC-USD', 'XLK')
        
        Returns:
            (ParentSignal, reason_string)
        """
        # Check cache first
        if parent_ticker in self._parent_signal_cache:
            return self._parent_signal_cache[parent_ticker]
        
        prices = self._get_prices(parent_ticker)
        
        if len(prices) < 50:
            result = (ParentSignal.UNKNOWN, f"Insufficient data for {parent_ticker}")
            self._parent_signal_cache[parent_ticker] = result
            return result
        
        # Calculate PSAR
        psar = self.indicators.psar(prices)
        
        current_price = float(prices.iloc[-1])
        current_psar = float(psar.iloc[-1])
        
        if current_price > current_psar:
            signal = ParentSignal.BULLISH
            reason = f"{parent_ticker}: ${current_price:.2f} > PSAR ${current_psar:.2f} → BULLISH"
        else:
            signal = ParentSignal.BEARISH
            reason = f"{parent_ticker}: ${current_price:.2f} < PSAR ${current_psar:.2f} → BEARISH"
        
        result = (signal, reason)
        self._parent_signal_cache[parent_ticker] = result
        return result
    
    def analyze_sector(self, parent_ticker: str) -> SectorAnalysis:
        """
        Analyze a single sector.
        
        1. Check parent signal
        2. If bullish, calculate SBI for all child stocks
        3. Identify entry candidates (SBI >= 9)
        
        Args:
            parent_ticker: Parent ETF/asset ticker
        
        Returns:
            SectorAnalysis with full breakdown
        """
        if parent_ticker not in PARENT_CHILD_MAPPING:
            return SectorAnalysis(
                parent=parent_ticker,
                description="Unknown",
                category="unknown",
                parent_signal=ParentSignal.UNKNOWN,
                parent_reason=f"Unknown parent: {parent_ticker}",
                stocks=[],
                entry_candidates=[]
            )
        
        sector_info = PARENT_CHILD_MAPPING[parent_ticker]
        
        # Check parent signal
        parent_signal, parent_reason = self.check_parent_signal(parent_ticker)
        
        # Calculate SBI for all child stocks
        stocks = []
        entry_candidates = []
        
        for stock_ticker in sector_info['stocks']:
            prices = self._get_prices(stock_ticker)
            volume = self._get_volume(stock_ticker)
            
            if len(prices) < 201:
                # Not enough data - create placeholder
                sbi_result = SBIResult(
                    ticker=stock_ticker,
                    sbi_score=0,
                    components={},
                    price=0,
                    weight_multiplier=0,
                    details={'error': 'Insufficient data'}
                )
            else:
                sbi_result = self.sbi_calc.calculate(stock_ticker, prices, volume)
            
            stocks.append(sbi_result)
            
            # Only consider entry if parent is bullish AND SBI >= 9
            if parent_signal == ParentSignal.BULLISH and sbi_result.is_entry_signal():
                entry_candidates.append(sbi_result)
        
        # Sort stocks by SBI score
        stocks.sort(key=lambda x: x.sbi_score, reverse=True)
        entry_candidates.sort(key=lambda x: x.sbi_score, reverse=True)
        
        return SectorAnalysis(
            parent=parent_ticker,
            description=sector_info['description'],
            category=sector_info['category'],
            parent_signal=parent_signal,
            parent_reason=parent_reason,
            stocks=stocks,
            entry_candidates=entry_candidates
        )
    
    def analyze_all_sectors(self) -> Dict[str, SectorAnalysis]:
        """
        Analyze all sectors.
        
        Returns:
            Dict mapping parent ticker to SectorAnalysis
        """
        results = {}
        
        for parent_ticker in PARENT_CHILD_MAPPING:
            results[parent_ticker] = self.analyze_sector(parent_ticker)
        
        return results
    
    def generate_allocation(self) -> PortfolioAllocation:
        """
        Generate target portfolio allocation.
        
        Logic:
        1. Analyze all sectors
        2. For bullish sectors, collect entry candidates (SBI >= 9)
        3. Allocate based on:
           - Category allocation (from config)
           - SBI weight multiplier (2x for SBI=10, 1x for SBI=9)
        4. Normalize to 100%
        
        Returns:
            PortfolioAllocation with target weights
        """
        reasoning = []
        reasoning.append("=" * 60)
        reasoning.append("SectorSBITrader Signal Generation")
        reasoning.append(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        reasoning.append("=" * 60)
        
        # Analyze all sectors
        sector_details = self.analyze_all_sectors()
        
        # Collect all entry candidates with their weights
        entry_signals = []  # (ticker, parent, category, weight)
        
        bullish_sectors = []
        bearish_sectors = []
        
        for parent, analysis in sector_details.items():
            if analysis.parent_signal == ParentSignal.BULLISH:
                bullish_sectors.append(parent)
                
                for candidate in analysis.entry_candidates:
                    entry_signals.append((
                        candidate.ticker,
                        parent,
                        analysis.category,
                        candidate.weight_multiplier,
                        candidate.sbi_score
                    ))
            else:
                bearish_sectors.append(parent)
        
        # Report bullish sectors
        reasoning.append("")
        reasoning.append(f"🟢 BULLISH SECTORS ({len(bullish_sectors)}):")
        for parent in bullish_sectors:
            analysis = sector_details[parent]
            n_candidates = len(analysis.entry_candidates)
            reasoning.append(f"   {parent} ({analysis.description}): {n_candidates} entry signals")
        
        # Report bearish sectors (abbreviated)
        reasoning.append("")
        reasoning.append(f"🔴 BEARISH SECTORS ({len(bearish_sectors)}): {', '.join(bearish_sectors[:5])}...")
        
        # If no entry signals, return cash
        if not entry_signals:
            reasoning.append("")
            reasoning.append("⚠️ NO ENTRY SIGNALS - Staying in cash")
            reasoning.append("   (No sectors are bullish with SBI >= 9 stocks)")
            return PortfolioAllocation(
                positions={},
                reasoning=reasoning,
                sector_details=sector_details
            )
        
        # Calculate allocations
        reasoning.append("")
        reasoning.append("📊 ALLOCATION CALCULATION:")
        
        # Group by category
        by_category = {}
        for ticker, parent, category, weight, sbi in entry_signals:
            if category not in by_category:
                by_category[category] = []
            by_category[category].append((ticker, parent, weight, sbi))
        
        # Calculate positions
        positions = {}
        
        for category, signals in by_category.items():
            category_allocation = self.config.sector_allocations.get(category, 0.10)
            
            # Calculate total weight in category
            total_weight = sum(w for _, _, w, _ in signals)
            
            if total_weight == 0:
                continue
            
            reasoning.append(f"")
            reasoning.append(f"   {category.upper()} ({category_allocation*100:.0f}% allocation):")
            
            for ticker, parent, weight, sbi in signals:
                # Position weight = (category allocation) * (stock weight / total weight)
                position_weight = category_allocation * (weight / total_weight)
                
                # Apply max position limit
                position_weight = min(position_weight, self.config.max_position_pct)
                
                positions[ticker] = positions.get(ticker, 0) + position_weight
                
                weight_str = "2x" if weight == 2.0 else "1x"
                reasoning.append(f"      {ticker}: SBI={sbi} ({weight_str}) → {position_weight*100:.1f}%")
        
        # Normalize if total > 100%
        total = sum(positions.values())
        if total > 1.0:
            positions = {k: v/total for k, v in positions.items()}
            reasoning.append(f"")
            reasoning.append(f"   Normalized from {total*100:.1f}% to 100%")
        
        # Summary
        reasoning.append("")
        reasoning.append("=" * 60)
        reasoning.append(f"SUMMARY: {len(positions)} positions across {len(by_category)} categories")
        reasoning.append(f"Total allocation: {sum(positions.values())*100:.1f}%")
        
        # Top 5 positions
        top_positions = sorted(positions.items(), key=lambda x: -x[1])[:5]
        reasoning.append("")
        reasoning.append("Top 5 positions:")
        for ticker, weight in top_positions:
            reasoning.append(f"   {ticker}: {weight*100:.1f}%")
        
        return PortfolioAllocation(
            positions=positions,
            reasoning=reasoning,
            sector_details=sector_details
        )
    
    def get_exit_signals(self, current_positions: Dict[str, Position]) -> List[str]:
        """
        Check which positions should be exited.
        
        Exit rule: When parent signal turns bearish, exit ALL positions
        from that sector.
        
        Args:
            current_positions: Dict mapping ticker to Position
        
        Returns:
            List of tickers to exit
        """
        exit_tickers = []
        
        # Group positions by parent
        by_parent = {}
        for ticker, position in current_positions.items():
            parent = position.parent
            if parent not in by_parent:
                by_parent[parent] = []
            by_parent[parent].append(ticker)
        
        # Check each parent
        for parent, tickers in by_parent.items():
            signal, reason = self.check_parent_signal(parent)
            
            if signal == ParentSignal.BEARISH:
                # Exit all positions from this sector
                exit_tickers.extend(tickers)
        
        return exit_tickers
    
    def print_analysis_report(self):
        """Print comprehensive analysis report."""
        allocation = self.generate_allocation()
        
        for line in allocation.reasoning:
            print(line)
        
        return allocation


def demo():
    """Demo the strategy with sample output."""
    print("\n" + "=" * 60)
    print("SectorSBITrader - Demo")
    print("=" * 60)
    
    print("""
Strategy Overview:
    
1. PARENT SIGNAL CHECK
   - Check PSAR on sector ETF (XLK, XLF, GLD, BTC-USD, etc.)
   - If price > PSAR → Sector is BULLISH
   
2. CHILD STOCK SBI CALCULATION  
   - For bullish sectors, calculate SBI for each stock
   - SBI = 10 → 2x weight (perfect score)
   - SBI = 9  → 1x weight (near-perfect)
   - SBI < 9  → No entry
   
3. WEIGHT LOCKING
   - Initial weight is LOCKED until parent turns bearish
   - If MSTR enters at SBI=10 (2x), keep 2x even if SBI drops to 8
   
4. EXIT RULE
   - Exit ALL positions in sector when parent turns bearish
   - Do NOT exit on individual stock signals
   
Example Flow:
    
Day 1: BTC-USD > PSAR (BULLISH)
   └── Scan: MSTR(SBI=10), COIN(SBI=9), MARA(SBI=7)
   └── Enter: MSTR (2x weight), COIN (1x weight)
   └── Skip: MARA (SBI < 9)
   
Day 15: BTC-USD still > PSAR
   └── HOLD all positions (ignore individual SBI changes)
   
Day 30: BTC-USD < PSAR (BEARISH)
   └── EXIT: MSTR, COIN (all BTC-related positions)
""")


if __name__ == "__main__":
    demo()
