"""
AdaptiveX2 SectorBot Strategy - Enhanced Version
=================================================

NEW LOGIC:
1. PARENT DETERMINES SECTOR EXPOSURE
   - Parent PSAR bullish → Sector is ACTIVE, can hold stocks
   - Parent PSAR bearish → EXIT ALL stocks in that sector

2. STOCK'S OWN TECHNICALS DETERMINE INDIVIDUAL POSITIONS
   - Entry: Stock PSAR bullish + RSI > 50 + SBI >= 9
   - Exit/Rotate: Stock PSAR bearish OR RSI < 40
     - If parent still bullish → ROTATE to stronger stock
     - If no replacement → Exit position (but watch sector)
   - Exit All: Parent bearish → Dump all stocks in sector

3. WEIGHTED PARENT ALLOCATION
   - Rank parents by strength (PSAR gap, ADX, momentum)
   - Top 3 parents get 2x allocation
   - Next 5 get 1x allocation
   - Rest get 0.5x allocation

4. SMALL ACCOUNT MODE (<$10K)
   - Max 10 positions total
   - Max 2 per sector
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import json
import os

from sbi_calculator import (
    get_full_sbi_data, 
    calculate_psar,
    calculate_psar_arrays,
    calculate_adx,
    calculate_adx_arrays,
    calculate_rsi,
    calculate_rsi_array,
    SBIResult
)
from config import (
    PARENT_CHILD_MAPPING,
    DEFAULT_CONFIG,
    get_parents_by_category,
    get_all_categories,
    get_category_allocation,
)


@dataclass
class Position:
    """Tracks a single stock position."""
    ticker: str
    parent: str
    category: str
    entry_date: str
    entry_price: float
    entry_sbi: int
    shares: float = 0
    weight: float = 0  # Portfolio weight


@dataclass
class SectorStatus:
    """Status of a parent sector."""
    parent: str
    category: str
    description: str
    is_bullish: bool
    days_bullish: int = 0
    psar_gap: float = 0.0
    adx: float = 0.0
    strength_score: float = 0.0  # For ranking


@dataclass
class StockHealth:
    """Health indicators for a stock."""
    ticker: str
    parent: str
    sbi: int
    psar_bullish: bool
    rsi: float
    is_healthy: bool  # PSAR bullish AND RSI > 50
    is_weak: bool     # PSAR bearish OR RSI < 40


@dataclass
class StockSignal:
    """A stock that qualifies for entry or rotation."""
    ticker: str
    parent: str
    category: str
    sbi: int
    rsi: float
    psar_bullish: bool
    signal_type: str  # 'entry', 'rotation', 'exit'
    reason: str = ""


class StrategyMode:
    """Strategy mode determines rotation and allocation behavior."""
    PARENT_BASED = "parent_based"       # Exit only on parent bearish, equal weights
    ROTATION = "rotation"               # Rotate on stock weakness, equal weights  
    WEIGHTED_ROTATION = "weighted_rotation"  # Rotate + weighted allocation


class AdaptiveX2SectorBot:
    """
    Enhanced Strategy:
    - Parent PSAR controls sector exposure
    - Stock PSAR + RSI controls individual positions
    - Rotation within sector when stock weakens
    - Weighted allocation to strongest parents
    
    REGIME-AWARE MODE:
    - Bull market (SPY > 200 SMA, VIX < 25): Parent-Based (hold through stock weakness)
    - Volatile (VIX > 25): Rotation (rotate weak stocks quickly)
    - Bear market (SPY < 200 SMA): Weighted-Rotation (rotate + concentrate in top sectors)
    """
    
    def __init__(self, config=None, small_account: bool = False, 
                 strategy_mode: str = None, regime_aware: bool = True):
        """
        Initialize SectorBot.
        
        Args:
            config: Strategy configuration
            small_account: Use small account limits (10 positions, 2/sector)
            strategy_mode: Force a specific mode (parent_based, rotation, weighted_rotation)
            regime_aware: If True and strategy_mode is None, auto-detect regime
        """
        self.config = config or DEFAULT_CONFIG
        self.positions: Dict[str, Position] = {}
        self.sector_status: Dict[str, SectorStatus] = {}
        self.price_data: Dict[str, pd.DataFrame] = {}
        
        # Strategy mode
        self.forced_mode = strategy_mode
        self.regime_aware = regime_aware
        self.current_mode = strategy_mode or StrategyMode.WEIGHTED_ROTATION
        self.regime_info = {}
        
        # Small account mode
        if small_account:
            self.max_positions = 10
            self.max_per_sector = 2
        else:
            self.max_positions = self.config.max_positions if hasattr(self.config, 'max_positions') else 20
            self.max_per_sector = self.config.max_stocks_per_sector if hasattr(self.config, 'max_stocks_per_sector') else 5
        
        # Thresholds
        self.min_sbi_entry = 9
        self.min_rsi_entry = 50
        self.weak_rsi_threshold = 40  # Below this = weak
        self.min_sbi_rotation = 7     # Lower bar for rotation replacements
        
        # State persistence
        self.state_file = 'sectorbot_state.json'
        self.load_state()
    
    def load_state(self):
        """
        Position tracking disabled for 3-day rotation.
        Each run generates fresh signals based on current technicals.
        """
        # Don't load positions - we're stateless now
        # User tracks their own positions
        pass
    
    def detect_regime(self) -> str:
        """
        Detect market regime and set strategy mode.
        
        Returns:
            Current strategy mode string
        """
        if self.forced_mode:
            self.current_mode = self.forced_mode
            self.regime_info = {'forced': True, 'mode': self.forced_mode}
            return self.current_mode
        
        if not self.regime_aware:
            self.regime_info = {'regime_aware': False, 'mode': self.current_mode}
            return self.current_mode
        
        try:
            # Get SPY data for regime detection
            spy_df = self.price_data.get('SPY')
            vix_df = self.price_data.get('^VIX')
            
            if spy_df is None or len(spy_df) < 200:
                # Not enough data, default to weighted rotation (safest)
                self.current_mode = StrategyMode.WEIGHTED_ROTATION
                self.regime_info = {
                    'regime': 'unknown',
                    'reason': 'Insufficient SPY data',
                    'mode': self.current_mode
                }
                return self.current_mode
            
            # Get SPY price and 200 SMA
            spy_close = spy_df['Close'].iloc[-1]
            if hasattr(spy_close, 'item'):
                spy_close = spy_close.item()
            
            spy_sma200 = spy_df['Close'].rolling(200).mean().iloc[-1]
            if hasattr(spy_sma200, 'item'):
                spy_sma200 = spy_sma200.item()
            
            spy_above_sma = spy_close > spy_sma200
            
            # Get VIX level
            vix_level = 20  # Default
            if vix_df is not None and len(vix_df) > 0:
                vix_level = vix_df['Close'].iloc[-1]
                if hasattr(vix_level, 'item'):
                    vix_level = vix_level.item()
            
            # Determine regime
            if not spy_above_sma:
                regime = 'bear'
                self.current_mode = StrategyMode.WEIGHTED_ROTATION
                reason = f"SPY {spy_close:.0f} < 200 SMA {spy_sma200:.0f}"
            elif vix_level > 25:
                regime = 'volatile'
                self.current_mode = StrategyMode.ROTATION
                reason = f"VIX {vix_level:.1f} > 25"
            else:
                regime = 'bull'
                self.current_mode = StrategyMode.PARENT_BASED
                reason = f"SPY {spy_close:.0f} > 200 SMA {spy_sma200:.0f}, VIX {vix_level:.1f}"
            
            self.regime_info = {
                'regime': regime,
                'spy_price': spy_close,
                'spy_sma200': spy_sma200,
                'spy_above_sma': spy_above_sma,
                'vix_level': vix_level,
                'reason': reason,
                'mode': self.current_mode
            }
            
            return self.current_mode
            
        except Exception as e:
            print(f"⚠️ Regime detection error: {e}")
            self.current_mode = StrategyMode.WEIGHTED_ROTATION
            self.regime_info = {'error': str(e), 'mode': self.current_mode}
            return self.current_mode
    
    def save_state(self):
        """Save positions to file."""
        state = {
            'positions': {ticker: vars(pos) for ticker, pos in self.positions.items()},
            'last_updated': datetime.now().isoformat(),
        }
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)
        print(f"💾 Saved {len(self.positions)} positions to {self.state_file}")
    
    def add_position(self, ticker: str, parent: str, category: str, 
                     entry_price: float, weight: float = 0.1, entry_sbi: int = 10):
        """Add a new position and save state."""
        self.positions[ticker] = Position(
            ticker=ticker,
            parent=parent,
            category=category,
            entry_date=datetime.now().strftime('%Y-%m-%d'),
            entry_price=entry_price,
            entry_sbi=entry_sbi,
            weight=weight
        )
        self.save_state()
        print(f"✅ Added position: {ticker} @ ${entry_price:.2f}")
    
    def remove_position(self, ticker: str):
        """Remove a position and save state."""
        if ticker in self.positions:
            del self.positions[ticker]
            self.save_state()
            print(f"🔴 Removed position: {ticker}")
        else:
            print(f"⚠️ Position {ticker} not found")
    
    def execute_signals(self, signals: Dict, confirm: bool = True):
        """
        Execute trading signals - update positions based on signals.
        
        This should be called AFTER you actually trade!
        
        Args:
            signals: Output from generate_signals()
            confirm: If True, ask for confirmation before each action
        """
        actions_taken = []
        
        # Process EXIT signals
        for exit_sig in signals.get('exit_signals', []):
            ticker = exit_sig['ticker']
            if ticker in self.positions:
                if confirm:
                    response = input(f"❓ Confirm SELL {ticker}? (y/n): ")
                    if response.lower() != 'y':
                        print(f"   Skipped {ticker}")
                        continue
                self.remove_position(ticker)
                actions_taken.append(f"SOLD {ticker}")
        
        # Process ROTATION signals
        for rotation in signals.get('rotation_signals', []):
            exit_ticker = rotation['exit']['ticker']
            enter_ticker = rotation['enter']['ticker']
            
            if confirm:
                response = input(f"❓ Confirm ROTATE {exit_ticker} → {enter_ticker}? (y/n): ")
                if response.lower() != 'y':
                    print(f"   Skipped rotation")
                    continue
            
            # Get entry price for new position
            entry_price = self.get_price(enter_ticker) or 0
            
            # Find parent info
            parent = None
            category = ''
            for p, info in PARENT_CHILD_MAPPING.items():
                if enter_ticker in info.get('stocks', []):
                    parent = p
                    category = info.get('category', '')
                    break
            
            if parent and exit_ticker in self.positions:
                old_weight = self.positions[exit_ticker].weight
                self.remove_position(exit_ticker)
                self.add_position(enter_ticker, parent, category, entry_price, old_weight)
                actions_taken.append(f"ROTATED {exit_ticker} → {enter_ticker}")
        
        # Process NEW ENTRY signals (only if we have slots)
        available_slots = self.max_positions - len(self.positions)
        if available_slots > 0:
            for entry_sig in signals.get('entry_signals', [])[:available_slots]:
                ticker = entry_sig['ticker']
                if ticker in self.positions:
                    continue  # Already own it
                
                if confirm:
                    response = input(f"❓ Confirm BUY {ticker}? (y/n): ")
                    if response.lower() != 'y':
                        print(f"   Skipped {ticker}")
                        continue
                
                entry_price = self.get_price(ticker) or 0
                parent = entry_sig['parent']
                category = entry_sig['category']
                
                self.add_position(ticker, parent, category, entry_price)
                actions_taken.append(f"BOUGHT {ticker}")
        
        print(f"\n📊 Actions taken: {len(actions_taken)}")
        for action in actions_taken:
            print(f"   • {action}")
        
        return actions_taken
    
    def set_price_data(self, data: Dict[str, pd.DataFrame]):
        """Set price data for all tickers."""
        self.price_data = data
    
    def get_price(self, ticker: str) -> Optional[float]:
        """Get current price for a ticker."""
        if ticker in self.price_data and len(self.price_data[ticker]) > 0:
            return self.price_data[ticker]['Close'].iloc[-1]
        return None
    
    # =========================================================================
    # PARENT SECTOR ANALYSIS
    # =========================================================================
    
    def get_parent_strength(self, parent: str) -> SectorStatus:
        """
        Calculate parent sector strength.
        Returns SectorStatus with strength_score for ranking.
        """
        info = PARENT_CHILD_MAPPING.get(parent, {})
        
        if parent not in self.price_data:
            return SectorStatus(
                parent=parent, category=info.get('category', ''),
                description=info.get('description', ''),
                is_bullish=False
            )
        
        df = self.price_data[parent]
        if len(df) < 30:
            return SectorStatus(
                parent=parent, category=info.get('category', ''),
                description=info.get('description', ''),
                is_bullish=False
            )
        
        try:
            # Convert to numpy arrays properly
            close = np.array(df['Close'].values, dtype=float)
            high = np.array(df['High'].values, dtype=float)
            low = np.array(df['Low'].values, dtype=float)
            
            # Remove any NaN values
            valid_mask = ~(np.isnan(close) | np.isnan(high) | np.isnan(low))
            close = close[valid_mask]
            high = high[valid_mask]
            low = low[valid_mask]
            
            if len(close) < 30:
                return SectorStatus(
                    parent=parent, category=info.get('category', ''),
                    description=info.get('description', ''),
                    is_bullish=False
                )
            
            # PSAR
            psar = calculate_psar_arrays(high, low, close)
            is_bullish = close[-1] > psar[-1]
            psar_gap = ((close[-1] - psar[-1]) / close[-1]) * 100 if is_bullish else 0
            
            # Count bullish days
            days_bullish = 0
            if is_bullish:
                for i in range(len(close) - 1, -1, -1):
                    if close[i] > psar[i]:
                        days_bullish += 1
                    else:
                        break
            
            # ADX for trend strength
            adx_data = calculate_adx_arrays(high, low, close)
            adx = adx_data['adx'][-1] if len(adx_data['adx']) > 0 else 0
            
            # RSI
            rsi_arr = calculate_rsi_array(close, 14)
            rsi = rsi_arr[-1] if len(rsi_arr) > 14 else 50
            
            # Strength score (0-100)
            if is_bullish:
                strength = (psar_gap * 2) + (adx * 0.5) + ((rsi - 50) * 0.3)
                strength = max(0, min(100, strength))
            else:
                strength = 0
            
            return SectorStatus(
                parent=parent,
                category=info.get('category', ''),
                description=info.get('description', ''),
                is_bullish=is_bullish,
                days_bullish=days_bullish,
                psar_gap=psar_gap,
                adx=adx,
                strength_score=strength,
            )
            
        except Exception as e:
            print(f"Error analyzing {parent}: {e}")
            import traceback
            traceback.print_exc()
            return SectorStatus(
                parent=parent, category=info.get('category', ''),
                description=info.get('description', ''),
                is_bullish=False
            )
    
    def update_sector_status(self) -> Dict[str, SectorStatus]:
        """Update status for all parent sectors."""
        self.sector_status = {}
        
        for parent in PARENT_CHILD_MAPPING.keys():
            self.sector_status[parent] = self.get_parent_strength(parent)
        
        return self.sector_status
    
    def rank_parents_by_strength(self) -> List[Tuple[str, float]]:
        """
        Rank parents by strength score.
        Returns [(parent, strength), ...] sorted descending.
        """
        rankings = [
            (parent, status.strength_score)
            for parent, status in self.sector_status.items()
            if status.is_bullish
        ]
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings
    
    def get_parent_weight(self, parent: str) -> float:
        """
        Get allocation weight for a parent based on rank and strategy mode.
        
        - PARENT_BASED mode: Equal weights (1.0)
        - ROTATION mode: Equal weights (1.0)
        - WEIGHTED_ROTATION mode: Top 3 = 2x, Next 5 = 1x, Rest = 0.5x
        """
        # In non-weighted modes, return equal weight
        if self.current_mode != StrategyMode.WEIGHTED_ROTATION:
            return 1.0
        
        # Weighted allocation for WEIGHTED_ROTATION mode
        rankings = self.rank_parents_by_strength()
        for rank, (p, score) in enumerate(rankings):
            if p == parent:
                if rank < 3:
                    return 2.0
                elif rank < 8:
                    return 1.0
                else:
                    return 0.5
        return 0.0  # Not bullish
    
    # =========================================================================
    # STOCK HEALTH ANALYSIS
    # =========================================================================
    
    def get_stock_health(self, ticker: str) -> Optional[StockHealth]:
        """
        Get health indicators for a stock.
        Returns StockHealth with is_healthy/is_weak flags.
        """
        if ticker not in self.price_data:
            return None
        
        df = self.price_data[ticker]
        if len(df) < 30:
            return None
        
        # Find parent
        parent = None
        for p, info in PARENT_CHILD_MAPPING.items():
            if ticker in info.get('stocks', []):
                parent = p
                break
        
        if not parent:
            return None
        
        try:
            # Convert to numpy arrays properly
            close = np.array(df['Close'].values, dtype=float)
            high = np.array(df['High'].values, dtype=float)
            low = np.array(df['Low'].values, dtype=float)
            
            # Remove any NaN values
            valid_mask = ~(np.isnan(close) | np.isnan(high) | np.isnan(low))
            close = close[valid_mask]
            high = high[valid_mask]
            low = low[valid_mask]
            
            if len(close) < 30:
                return None
            
            # Create a DataFrame for SBI calculation (it expects DataFrame)
            temp_df = pd.DataFrame({
                'High': high,
                'Low': low,
                'Close': close
            })
            
            # SBI
            sbi_result = get_full_sbi_data(temp_df)
            sbi = sbi_result.sbi if sbi_result else 0
            
            # PSAR
            psar = calculate_psar_arrays(high, low, close)
            psar_bullish = close[-1] > psar[-1]
            
            # RSI
            rsi_arr = calculate_rsi_array(close, 14)
            rsi = rsi_arr[-1] if len(rsi_arr) > 14 else 50
            
            # Health flags
            is_healthy = psar_bullish and rsi > self.min_rsi_entry
            is_weak = (not psar_bullish) or (rsi < self.weak_rsi_threshold)
            
            return StockHealth(
                ticker=ticker,
                parent=parent,
                sbi=sbi,
                psar_bullish=psar_bullish,
                rsi=rsi,
                is_healthy=is_healthy,
                is_weak=is_weak,
            )
            
        except Exception as e:
            print(f"Error analyzing {ticker}: {e}")
            return None
    
    # =========================================================================
    # ENTRY SIGNALS
    # =========================================================================
    
    def scan_for_entries(self) -> List[StockSignal]:
        """
        Scan for new entry signals.
        Entry requires:
        - Parent PSAR bullish
        - Stock PSAR bullish
        - Stock RSI > 50
        - Stock SBI >= 9
        """
        signals = []
        
        # Get bullish parents ranked by strength
        rankings = self.rank_parents_by_strength()
        
        for parent, strength in rankings:
            info = PARENT_CHILD_MAPPING.get(parent, {})
            stocks = info.get('stocks', [])
            
            # Count current positions in this sector
            positions_in_sector = sum(
                1 for p in self.positions.values() if p.parent == parent
            )
            
            # Check parent weight for max positions
            parent_weight = self.get_parent_weight(parent)
            max_for_parent = min(self.max_per_sector, int(self.max_per_sector * parent_weight) + 1)
            
            if positions_in_sector >= max_for_parent:
                continue
            
            # SCAN ALL STOCKS AND RANK BY MOMENTUM
            candidates = []
            for ticker in stocks:
                if ticker in self.positions:
                    continue
                
                health = self.get_stock_health(ticker)
                if not health:
                    continue
                
                # ENTRY CRITERIA
                if (health.sbi >= self.min_sbi_entry and 
                    health.psar_bullish and 
                    health.rsi > self.min_rsi_entry):
                    
                    # Score = SBI * 10 + RSI (so SBI 10 with RSI 70 = 170)
                    momentum_score = health.sbi * 10 + health.rsi
                    candidates.append((ticker, health, momentum_score))
            
            # SORT BY MOMENTUM SCORE (best first)
            candidates.sort(key=lambda x: x[2], reverse=True)
            
            # Take top stocks up to max_for_parent
            slots_available = max_for_parent - positions_in_sector
            for ticker, health, score in candidates[:slots_available]:
                signals.append(StockSignal(
                    ticker=ticker,
                    parent=parent,
                    category=info.get('category', ''),
                    sbi=health.sbi,
                    rsi=health.rsi,
                    psar_bullish=True,
                    signal_type='entry',
                    reason=f"SBI={health.sbi}, RSI={health.rsi:.0f}, PSAR bullish"
                ))
            
            if len(signals) + len(self.positions) >= self.max_positions:
                break
        
        return signals
    
    # =========================================================================
    # ROTATION & EXIT SIGNALS
    # =========================================================================
    
    def find_rotation_candidate(self, parent: str, exclude: List[str]) -> Optional[StockSignal]:
        """
        Find best replacement stock in sector.
        Requires: PSAR bullish + RSI > 50 + SBI >= 7
        """
        info = PARENT_CHILD_MAPPING.get(parent, {})
        stocks = info.get('stocks', [])
        
        candidates = []
        for ticker in stocks:
            if ticker in exclude:
                continue
            
            health = self.get_stock_health(ticker)
            if not health:
                continue
            
            # Rotation candidate criteria (slightly lower bar than entry)
            if (health.sbi >= self.min_sbi_rotation and
                health.psar_bullish and
                health.rsi > self.min_rsi_entry):
                
                candidates.append((ticker, health.sbi, health.rsi))
        
        if not candidates:
            return None
        
        # Best candidate = highest SBI, then RSI
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
        best = candidates[0]
        
        return StockSignal(
            ticker=best[0],
            parent=parent,
            category=info.get('category', ''),
            sbi=best[1],
            rsi=best[2],
            psar_bullish=True,
            signal_type='rotation',
            reason=f"Rotation candidate: SBI={best[1]}, RSI={best[2]:.0f}"
        )
    
    def check_positions(self) -> Tuple[List[Tuple], List[StockSignal], List[str]]:
        """
        Check all current positions for rotation or exit.
        
        Behavior depends on strategy mode:
        - PARENT_BASED: Only exit on parent bearish, hold through stock weakness
        - ROTATION: Rotate on stock weakness (PSAR bearish OR RSI < 40)
        - WEIGHTED_ROTATION: Same as rotation + weighted allocation
        
        Returns:
        - rotation_signals: [(exit_signal, new_signal), ...]
        - exit_signals: [signal, ...] - exit with no rotation
        - hold_signals: [ticker, ...] - continue holding
        """
        rotations = []
        exits = []
        holds = []
        
        for ticker, position in list(self.positions.items()):
            parent = position.parent
            parent_status = self.sector_status.get(parent)
            
            # RULE 1: Parent bearish → EXIT ALL (all modes)
            if not parent_status or not parent_status.is_bullish:
                exits.append(StockSignal(
                    ticker=ticker,
                    parent=parent,
                    category=position.category,
                    sbi=0,
                    rsi=0,
                    psar_bullish=False,
                    signal_type='exit',
                    reason="Parent PSAR bearish"
                ))
                continue
            
            # RULE 2: Check stock health - behavior depends on mode
            health = self.get_stock_health(ticker)
            
            # In PARENT_BASED mode: Don't rotate on stock weakness
            if self.current_mode == StrategyMode.PARENT_BASED:
                holds.append(ticker)
                continue
            
            # In ROTATION or WEIGHTED_ROTATION mode: Check for weakness
            if health and health.is_weak:
                # Stock is weak - try to rotate
                current_holdings = [t for t, p in self.positions.items() if p.parent == parent]
                replacement = self.find_rotation_candidate(parent, current_holdings)
                
                if replacement:
                    # ROTATE
                    exit_signal = StockSignal(
                        ticker=ticker,
                        parent=parent,
                        category=position.category,
                        sbi=health.sbi,
                        rsi=health.rsi,
                        psar_bullish=health.psar_bullish,
                        signal_type='rotate_out',
                        reason=f"Weak: PSAR={'bull' if health.psar_bullish else 'bear'}, RSI={health.rsi:.0f}"
                    )
                    rotations.append((exit_signal, replacement))
                else:
                    # No replacement - EXIT
                    exits.append(StockSignal(
                        ticker=ticker,
                        parent=parent,
                        category=position.category,
                        sbi=health.sbi,
                        rsi=health.rsi,
                        psar_bullish=health.psar_bullish,
                        signal_type='exit',
                        reason=f"Weak + no rotation: PSAR={'bull' if health.psar_bullish else 'bear'}, RSI={health.rsi:.0f}"
                    ))
            else:
                # Stock is healthy - HOLD
                holds.append(ticker)
        
        return rotations, exits, holds
    
    # =========================================================================
    # ALLOCATION
    # =========================================================================
    
    def calculate_allocation(self, entry_signals: List[StockSignal], 
                            rotations: List[Tuple], exits: List[StockSignal]) -> Dict[str, float]:
        """
        Calculate target portfolio allocation.
        Uses weighted parent allocation.
        Scales up to use more capital in small account mode.
        """
        allocation = {}
        
        # Keep existing positions that aren't being exited
        exit_tickers = {s.ticker for s in exits}
        rotate_out_tickers = {s[0].ticker for s in rotations}
        
        for ticker, position in self.positions.items():
            if ticker not in exit_tickers and ticker not in rotate_out_tickers:
                allocation[ticker] = position.weight
        
        # Add rotation replacements
        for _, new_signal in rotations:
            parent_weight = self.get_parent_weight(new_signal.parent)
            base_weight = 0.10  # 10% base (was 5%)
            allocation[new_signal.ticker] = base_weight * parent_weight
        
        # Add new entries
        for signal in entry_signals:
            if signal.ticker not in allocation:
                parent_weight = self.get_parent_weight(signal.parent)
                base_weight = 0.10  # 10% base (was 5%)
                # SBI 10 gets bonus
                sbi_bonus = 1.25 if signal.sbi == 10 else 1.0
                allocation[signal.ticker] = base_weight * parent_weight * sbi_bonus
        
        # Normalize if over 100%
        total = sum(allocation.values())
        if total > 1.0:
            factor = 1.0 / total
            allocation = {k: v * factor for k, v in allocation.items()}
        
        # Scale UP if we have room (target 90% invested when we have signals)
        if total < 0.90 and len(allocation) > 0:
            scale_factor = 0.90 / total
            allocation = {k: v * scale_factor for k, v in allocation.items()}
        
        return allocation
    
    # =========================================================================
    # MAIN EXECUTION
    # =========================================================================
    
    def generate_signals(self) -> Dict:
        """
        Main entry point - generate all trading signals.
        """
        # Step 0: Detect market regime and set strategy mode
        self.detect_regime()
        
        # Step 1: Update sector status
        self.update_sector_status()
        
        # Step 2: Check existing positions for rotation/exit
        rotations, exits, holds = self.check_positions()
        
        # Step 3: Scan for new entries
        entries = self.scan_for_entries()
        
        # Step 4: Calculate allocation
        allocation = self.calculate_allocation(entries, rotations, exits)
        
        # Get ranked parents
        ranked_parents = self.rank_parents_by_strength()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'regime': self.regime_info,
            'strategy_mode': self.current_mode,
            'sector_status': {
                parent: {
                    'parent': s.parent,
                    'category': s.category,
                    'description': s.description,
                    'is_bullish': bool(s.is_bullish),
                    'days_bullish': int(s.days_bullish),
                    'psar_gap': float(s.psar_gap),
                    'adx': float(s.adx),
                    'strength_score': float(s.strength_score),
                    'weight': self.get_parent_weight(parent),
                }
                for parent, s in self.sector_status.items()
            },
            'ranked_parents': [
                {'parent': p, 'strength': float(s), 'weight': self.get_parent_weight(p)}
                for p, s in ranked_parents
            ],
            'active_sectors': [p for p, s in self.sector_status.items() if s.is_bullish],
            'inactive_sectors': [p for p, s in self.sector_status.items() if not s.is_bullish],
            'entry_signals': [
                {
                    'ticker': s.ticker,
                    'parent': s.parent,
                    'category': s.category,
                    'sbi': s.sbi,
                    'rsi': float(s.rsi),
                    'reason': s.reason,
                }
                for s in entries
            ],
            'rotation_signals': [
                {
                    'exit': {
                        'ticker': exit_s.ticker,
                        'reason': exit_s.reason,
                    },
                    'enter': {
                        'ticker': new_s.ticker,
                        'sbi': new_s.sbi,
                        'rsi': float(new_s.rsi),
                    }
                }
                for exit_s, new_s in rotations
            ],
            'exit_signals': [
                {
                    'ticker': s.ticker,
                    'parent': s.parent,
                    'reason': s.reason,
                }
                for s in exits
            ],
            'hold_positions': holds,
            'target_allocation': allocation,
            'current_positions': list(self.positions.keys()),
        }
    
    def print_report(self, signals: Dict):
        """Print formatted report."""
        print("\n" + "=" * 70)
        print("AdaptiveX2 SectorBot Report - Enhanced")
        print(f"Generated: {signals['timestamp']}")
        print("=" * 70)
        
        # Regime Info
        regime = signals.get('regime', {})
        mode = signals.get('strategy_mode', 'unknown')
        if regime:
            regime_name = regime.get('regime', 'unknown').upper()
            print(f"\n🎯 MARKET REGIME: {regime_name}")
            print(f"   Strategy Mode: {mode}")
            if 'spy_price' in regime:
                print(f"   SPY: ${regime['spy_price']:.2f} (200 SMA: ${regime['spy_sma200']:.2f})")
            if 'vix_level' in regime:
                print(f"   VIX: {regime['vix_level']:.1f}")
            if 'reason' in regime:
                print(f"   Reason: {regime['reason']}")
        
        # Ranked Parents
        print("\n🏆 TOP PARENTS (by strength)")
        print("-" * 50)
        for i, p in enumerate(signals['ranked_parents'][:10]):
            weight_str = "2x" if p['weight'] == 2.0 else ("1x" if p['weight'] == 1.0 else "0.5x")
            print(f"  {i+1}. {p['parent']}: strength={p['strength']:.1f}, weight={weight_str}")
        
        # Sector Status by Category
        print("\n📊 SECTOR STATUS")
        print("-" * 50)
        by_category = {}
        for parent, status in signals['sector_status'].items():
            cat = status['category']
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(status)
        
        for cat, statuses in by_category.items():
            print(f"\n{cat.upper()}:")
            for s in statuses:
                emoji = "🟢" if s['is_bullish'] else "🔴"
                weight = f"({s['weight']}x)" if s['is_bullish'] else ""
                print(f"  {emoji} {s['parent']}: {s['description']} {weight}")
                if s['is_bullish']:
                    print(f"      PSAR gap: {s['psar_gap']:+.1f}%, ADX: {s['adx']:.0f}, Days: {s['days_bullish']}")
        
        # Entry Signals
        print(f"\n📈 NEW ENTRY SIGNALS ({len(signals['entry_signals'])})")
        print("-" * 50)
        for s in signals['entry_signals']:
            print(f"  🟢 BUY {s['ticker']} ({s['parent']})")
            print(f"      {s['reason']}")
        
        # Rotation Signals
        print(f"\n🔄 ROTATION SIGNALS ({len(signals['rotation_signals'])})")
        print("-" * 50)
        for r in signals['rotation_signals']:
            print(f"  🔄 SELL {r['exit']['ticker']} → BUY {r['enter']['ticker']}")
            print(f"      Exit reason: {r['exit']['reason']}")
            print(f"      Enter: SBI={r['enter']['sbi']}, RSI={r['enter']['rsi']:.0f}")
        
        # Exit Signals
        print(f"\n📉 EXIT SIGNALS ({len(signals['exit_signals'])})")
        print("-" * 50)
        for s in signals['exit_signals']:
            print(f"  🔴 SELL {s['ticker']} ({s['parent']})")
            print(f"      {s['reason']}")
        
        # Hold Positions
        print(f"\n✋ HOLD POSITIONS ({len(signals['hold_positions'])})")
        print("-" * 50)
        for ticker in signals['hold_positions']:
            print(f"  ➡️  {ticker}")
        
        # Target Allocation
        print(f"\n🎯 TARGET ALLOCATION ({len(signals['target_allocation'])} positions)")
        print("-" * 50)
        sorted_alloc = sorted(signals['target_allocation'].items(), key=lambda x: -x[1])
        for ticker, weight in sorted_alloc:
            print(f"  {ticker}: {weight*100:.1f}%")
        total = sum(signals['target_allocation'].values())
        print(f"\n  Total Invested: {total*100:.1f}%")
        print(f"  Cash: {(1-total)*100:.1f}%")
        
        print("\n" + "=" * 70)


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    import yfinance as yf
    
    print("AdaptiveX2 SectorBot - Enhanced Test")
    print("=" * 60)
    
    bot = AdaptiveX2SectorBot()
    
    # Fetch sample data
    print("\nFetching price data...")
    test_parents = ['BTC-USD', 'GLD', 'XLK', 'SMH']
    test_stocks = ['MSTR', 'COIN', 'MARA', 'NEM', 'GOLD', 'AEM', 'NVDA', 'AMD', 'TSM']
    
    all_tickers = test_parents + test_stocks
    price_data = {}
    
    for ticker in all_tickers:
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="6mo")
            if len(df) > 20:
                price_data[ticker] = df
                print(f"  ✓ {ticker}: {len(df)} days")
        except Exception as e:
            print(f"  ✗ {ticker}: {e}")
    
    bot.set_price_data(price_data)
    
    print("\nGenerating signals...")
    signals = bot.generate_signals()
    
    bot.print_report(signals)
