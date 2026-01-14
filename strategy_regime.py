"""
AdaptiveX2 SectorBot - Regime-Aware Strategy
=============================================

AUTO-SWITCHES between strategies based on market regime:

1. BEAR MARKET (SPY below 200 SMA):
   → Use Weighted-Rotation (best bear protection: +19.5% vs SPY -19% in 2022)
   
2. HIGH VOLATILITY (VIX > 25):
   → Use Rotation (captures quick moves: +38.9% in 2020)
   
3. BULL MARKET (default):
   → Use Parent-Based (ride winners: +29.1% in 2025)

Backtest Results:
- 2020 (volatile): Rotation +38.9%
- 2022 (bear): Weighted-Rotation +19.5% 
- 2025 (bull): Parent-Based +29.1%
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import yfinance as yf

from strategy import (
    AdaptiveX2SectorBot,
    Position,
    SectorStatus,
    StockHealth,
    StockSignal,
)
from sbi_calculator import (
    calculate_psar_arrays,
    calculate_rsi_array,
)


class MarketRegime(Enum):
    """Market regime classification."""
    BULL = "bull"           # SPY > 200 SMA, VIX < 20
    BEAR = "bear"           # SPY < 200 SMA
    VOLATILE = "volatile"   # VIX > 25
    NEUTRAL = "neutral"     # Everything else


class StrategyMode(Enum):
    """Strategy mode to use."""
    PARENT_BASED = "parent_based"           # Exit only on parent PSAR bearish
    ROTATION = "rotation"                   # Rotate on stock weakness
    WEIGHTED_ROTATION = "weighted_rotation" # Weighted allocation + rotation


@dataclass
class RegimeInfo:
    """Current market regime information."""
    regime: MarketRegime
    strategy_mode: StrategyMode
    spy_price: float
    spy_sma200: float
    spy_above_sma: bool
    vix_level: float
    reason: str


class RegimeAwareSectorBot(AdaptiveX2SectorBot):
    """
    Regime-aware strategy that auto-switches based on market conditions.
    
    Inherits from AdaptiveX2SectorBot and overrides key methods to
    implement regime-based strategy selection.
    """
    
    def __init__(self, config=None, small_account: bool = False, 
                 force_mode: StrategyMode = None):
        """
        Initialize regime-aware bot.
        
        Args:
            config: Strategy configuration
            small_account: Use small account limits (10 positions, 2/sector)
            force_mode: Force a specific strategy mode (bypasses regime detection)
        """
        super().__init__(config, small_account)
        
        self.force_mode = force_mode
        self.current_regime: RegimeInfo = None
        self._spy_data: pd.DataFrame = None
        self._vix_data: pd.DataFrame = None
        
        # Regime thresholds
        self.vix_high_threshold = 25  # Above this = volatile
        self.vix_low_threshold = 20   # Below this in bull = calm bull
        
        # Strategy-specific parameters
        self.rotation_rsi_threshold = 40  # RSI below this triggers rotation
        self.parent_based_hold_days = 5   # Min days to hold in parent-based mode
        
    def detect_regime(self, as_of_date: datetime = None) -> RegimeInfo:
        """
        Detect current market regime based on SPY and VIX.
        
        Returns:
            RegimeInfo with current regime and recommended strategy
        """
        if self.force_mode:
            return RegimeInfo(
                regime=MarketRegime.NEUTRAL,
                strategy_mode=self.force_mode,
                spy_price=0, spy_sma200=0, spy_above_sma=True,
                vix_level=0, reason=f"Forced mode: {self.force_mode.value}"
            )
        
        try:
            # Get SPY data
            if self._spy_data is None or len(self._spy_data) == 0:
                self._spy_data = yf.download('SPY', period='1y', progress=False)
            
            # Get VIX data
            if self._vix_data is None or len(self._vix_data) == 0:
                self._vix_data = yf.download('^VIX', period='3mo', progress=False)
            
            # Use as_of_date if provided, otherwise latest
            if as_of_date:
                spy_df = self._spy_data[self._spy_data.index <= as_of_date]
                vix_df = self._vix_data[self._vix_data.index <= as_of_date]
            else:
                spy_df = self._spy_data
                vix_df = self._vix_data
            
            if len(spy_df) < 200:
                # Not enough data, default to bull
                return RegimeInfo(
                    regime=MarketRegime.BULL,
                    strategy_mode=StrategyMode.PARENT_BASED,
                    spy_price=0, spy_sma200=0, spy_above_sma=True,
                    vix_level=20, reason="Insufficient SPY data, defaulting to bull"
                )
            
            # Calculate indicators
            spy_price = float(spy_df['Close'].iloc[-1])
            spy_sma200 = float(spy_df['Close'].rolling(200).mean().iloc[-1])
            spy_above_sma = spy_price > spy_sma200
            
            vix_level = float(vix_df['Close'].iloc[-1]) if len(vix_df) > 0 else 20
            
            # Determine regime
            if not spy_above_sma:
                # BEAR MARKET
                regime = MarketRegime.BEAR
                strategy = StrategyMode.WEIGHTED_ROTATION
                reason = f"SPY {spy_price:.0f} < 200 SMA {spy_sma200:.0f} → Bear market → Weighted-Rotation"
                
            elif vix_level > self.vix_high_threshold:
                # HIGH VOLATILITY
                regime = MarketRegime.VOLATILE
                strategy = StrategyMode.ROTATION
                reason = f"VIX {vix_level:.1f} > {self.vix_high_threshold} → Volatile → Rotation"
                
            else:
                # BULL MARKET
                regime = MarketRegime.BULL
                strategy = StrategyMode.PARENT_BASED
                reason = f"SPY {spy_price:.0f} > 200 SMA {spy_sma200:.0f}, VIX {vix_level:.1f} → Bull → Parent-Based"
            
            return RegimeInfo(
                regime=regime,
                strategy_mode=strategy,
                spy_price=spy_price,
                spy_sma200=spy_sma200,
                spy_above_sma=spy_above_sma,
                vix_level=vix_level,
                reason=reason
            )
            
        except Exception as e:
            print(f"⚠️ Regime detection failed: {e}, defaulting to Weighted-Rotation")
            return RegimeInfo(
                regime=MarketRegime.NEUTRAL,
                strategy_mode=StrategyMode.WEIGHTED_ROTATION,
                spy_price=0, spy_sma200=0, spy_above_sma=True,
                vix_level=20, reason=f"Error: {e}, defaulting to Weighted-Rotation"
            )
    
    def should_rotate_stock(self, health: StockHealth, position: Position) -> bool:
        """
        Determine if a stock should be rotated based on current strategy mode.
        
        Args:
            health: Current stock health indicators
            position: Current position info
            
        Returns:
            True if stock should be rotated/exited
        """
        if self.current_regime is None:
            self.current_regime = self.detect_regime()
        
        mode = self.current_regime.strategy_mode
        
        if mode == StrategyMode.PARENT_BASED:
            # Only exit on parent bearish (handled elsewhere)
            # Don't rotate on stock weakness
            return False
            
        elif mode == StrategyMode.ROTATION:
            # Rotate on stock weakness: PSAR bearish OR RSI < 40
            return not health.psar_bullish or health.rsi < self.rotation_rsi_threshold
            
        elif mode == StrategyMode.WEIGHTED_ROTATION:
            # Same as rotation but with weighted allocation
            return not health.psar_bullish or health.rsi < self.rotation_rsi_threshold
        
        return False
    
    def get_parent_weight(self, parent: str) -> float:
        """
        Get allocation weight for a parent based on rank and strategy mode.
        
        In Parent-Based mode: Equal weights
        In Rotation mode: Equal weights
        In Weighted-Rotation mode: Top sectors get more weight
        """
        if self.current_regime is None:
            self.current_regime = self.detect_regime()
        
        mode = self.current_regime.strategy_mode
        
        if mode == StrategyMode.WEIGHTED_ROTATION:
            # Weighted allocation - top sectors get more
            rankings = self.rank_parents_by_strength()
            for rank, (p, score) in enumerate(rankings):
                if p == parent:
                    if rank < 3:
                        return 2.0  # Top 3 get 2x
                    elif rank < 8:
                        return 1.0  # Next 5 get 1x
                    else:
                        return 0.5  # Rest get 0.5x
            return 0.5
        else:
            # Equal weights for Parent-Based and Rotation
            return 1.0
    
    def check_positions(self) -> Tuple[List, List, List]:
        """
        Check existing positions for rotation/exit based on current regime.
        
        Returns:
            (rotations, exits, holds) - lists of signals
        """
        if self.current_regime is None:
            self.current_regime = self.detect_regime()
        
        mode = self.current_regime.strategy_mode
        rotations = []
        exits = []
        holds = []
        
        for ticker, position in list(self.positions.items()):
            parent = position.parent
            
            # Check if parent is still bullish
            sector = self.sector_status.get(parent)
            if not sector or not sector.is_bullish:
                # Parent bearish - EXIT regardless of mode
                exits.append(StockSignal(
                    ticker=ticker,
                    parent=parent,
                    category=position.category,
                    sbi=0, rsi=0, psar_bullish=False,
                    signal_type='exit',
                    reason="Parent PSAR bearish"
                ))
                continue
            
            # Check stock health
            health = self.get_stock_health(ticker)
            if not health:
                holds.append(ticker)
                continue
            
            # Decision based on strategy mode
            if mode == StrategyMode.PARENT_BASED:
                # Only exit on parent bearish (handled above)
                # Hold through stock weakness
                holds.append(ticker)
                
            elif mode in [StrategyMode.ROTATION, StrategyMode.WEIGHTED_ROTATION]:
                # Check for stock weakness
                if self.should_rotate_stock(health, position):
                    # Try to find rotation candidate
                    exclude = [ticker] + [p.ticker for p in self.positions.values() if p.parent == parent]
                    replacement = self.find_rotation_candidate(parent, exclude)
                    
                    if replacement:
                        rotations.append((
                            StockSignal(
                                ticker=ticker,
                                parent=parent,
                                category=position.category,
                                sbi=health.sbi, rsi=health.rsi,
                                psar_bullish=health.psar_bullish,
                                signal_type='rotation_out',
                                reason=f"Rotating: PSAR={'bull' if health.psar_bullish else 'bear'}, RSI={health.rsi:.0f}"
                            ),
                            replacement
                        ))
                    else:
                        # No replacement - exit or hold depending on how weak
                        if not health.psar_bullish and health.rsi < 35:
                            exits.append(StockSignal(
                                ticker=ticker,
                                parent=parent,
                                category=position.category,
                                sbi=health.sbi, rsi=health.rsi,
                                psar_bullish=health.psar_bullish,
                                signal_type='exit',
                                reason=f"No rotation available, very weak: RSI={health.rsi:.0f}"
                            ))
                        else:
                            holds.append(ticker)
                else:
                    holds.append(ticker)
        
        return rotations, exits, holds
    
    def generate_signals(self) -> Dict:
        """
        Main entry point - generate all trading signals with regime awareness.
        """
        # Detect current regime
        self.current_regime = self.detect_regime()
        
        # Call parent implementation
        signals = super().generate_signals()
        
        # Add regime info to signals
        signals['regime'] = {
            'regime': self.current_regime.regime.value,
            'strategy_mode': self.current_regime.strategy_mode.value,
            'spy_price': self.current_regime.spy_price,
            'spy_sma200': self.current_regime.spy_sma200,
            'spy_above_sma': self.current_regime.spy_above_sma,
            'vix_level': self.current_regime.vix_level,
            'reason': self.current_regime.reason,
        }
        
        return signals
    
    def print_report(self, signals: Dict):
        """Print formatted report with regime info."""
        print("\n" + "=" * 70)
        print("AdaptiveX2 SectorBot - REGIME-AWARE")
        print(f"Generated: {signals['timestamp']}")
        print("=" * 70)
        
        # Regime info
        regime = signals.get('regime', {})
        print(f"\n🎯 MARKET REGIME: {regime.get('regime', 'unknown').upper()}")
        print(f"   Strategy Mode: {regime.get('strategy_mode', 'unknown')}")
        print(f"   SPY: ${regime.get('spy_price', 0):.2f} (200 SMA: ${regime.get('spy_sma200', 0):.2f})")
        print(f"   VIX: {regime.get('vix_level', 0):.1f}")
        print(f"   Reason: {regime.get('reason', '')}")
        
        # Call parent report
        super().print_report(signals)


def run_regime_aware_signal(small_account: bool = True, 
                            force_mode: StrategyMode = None) -> Dict:
    """
    Run the regime-aware signal generation.
    
    Args:
        small_account: Use small account limits
        force_mode: Force a specific strategy mode
        
    Returns:
        Signal dictionary with regime info
    """
    import yfinance as yf
    from config import PARENT_CHILD_MAPPING
    
    print("📊 Loading price data...")
    
    # Collect all tickers
    all_tickers = set()
    for parent, info in PARENT_CHILD_MAPPING.items():
        all_tickers.add(parent)
        all_tickers.update(info.get('stocks', []))
    
    # Download data
    price_data = {}
    try:
        data = yf.download(list(all_tickers), period='6mo', progress=True, threads=True)
        
        # Handle multi-level columns
        if isinstance(data.columns, pd.MultiIndex):
            for ticker in all_tickers:
                try:
                    df = data.xs(ticker, level=1, axis=1).copy()
                    if len(df) > 30:
                        price_data[ticker] = df
                except:
                    pass
        else:
            # Single ticker
            price_data[list(all_tickers)[0]] = data
            
    except Exception as e:
        print(f"⚠️ Bulk download failed: {e}, trying individual...")
        for ticker in all_tickers:
            try:
                df = yf.download(ticker, period='6mo', progress=False)
                if len(df) > 30:
                    price_data[ticker] = df
            except:
                pass
    
    print(f"✅ Loaded {len(price_data)} tickers")
    
    # Create bot and set price data
    bot = RegimeAwareSectorBot(small_account=small_account, force_mode=force_mode)
    bot.set_price_data(price_data)
    
    # Generate signals
    signals = bot.generate_signals()
    bot.print_report(signals)
    return signals


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Regime-Aware SectorBot')
    parser.add_argument('--small-account', action='store_true', default=True,
                       help='Small account mode (10 positions)')
    parser.add_argument('--large-account', action='store_true',
                       help='Large account mode (20 positions)')
    parser.add_argument('--force-mode', type=str, choices=['parent_based', 'rotation', 'weighted_rotation'],
                       help='Force a specific strategy mode')
    
    args = parser.parse_args()
    
    small = not args.large_account
    
    force_mode = None
    if args.force_mode:
        force_mode = StrategyMode(args.force_mode)
    
    signals = run_regime_aware_signal(small_account=small, force_mode=force_mode)
