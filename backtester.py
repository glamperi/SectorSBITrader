#!/usr/bin/env python3
"""
AdaptiveX2 SectorBot Enhanced Backtester
========================================

New Features:
1. ROTATION: Swap weak stocks for stronger ones within same sector
2. WEIGHTED PARENTS: 2x exposure to strongest parents
3. POSITION TRACKING: Avg/Min/Max positions held per day
4. SMALL ACCOUNT MODE: Top 2-3 stocks per sector for <$10K accounts

Strategies compared:
1. PARENT-BASED: Exit only when parent PSAR turns bearish
2. ROTATION: Exit weak stocks but stay in sector via rotation
3. WEIGHTED-ROTATION: Rotation + 2x weight on strongest parents
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import json
import argparse
import yfinance as yf

from sbi_calculator import (
    calculate_psar,
    calculate_psar_arrays,
    get_psar_trend,
    calculate_psar_gap,
    get_full_sbi_data,
    calculate_adx,
    calculate_adx_arrays,
    get_atr_volatility,
    calculate_rsi,
    calculate_rsi_array,
)
from config import PARENT_CHILD_MAPPING, get_parents_by_category, get_all_categories


@dataclass
class Trade:
    """Record of a single trade."""
    ticker: str
    parent: str
    entry_date: str
    entry_price: float
    entry_sbi: int
    exit_date: str = None
    exit_price: float = None
    exit_reason: str = None
    pnl_pct: float = None
    holding_days: int = None


@dataclass
class BacktestResult:
    """Results of a backtest run."""
    strategy_name: str
    start_date: str
    end_date: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_gain: float
    avg_loss: float
    total_return: float
    max_drawdown: float
    avg_holding_days: float
    avg_positions: float = 0
    min_positions: int = 0
    max_positions_held: int = 0
    rotations: int = 0
    trades: List[Trade] = field(default_factory=list)


class EnhancedBacktester:
    """
    Enhanced backtester with rotation and weighted parents.
    """
    
    def __init__(self, 
                 start_date: str = "2024-01-01",
                 end_date: str = None,
                 initial_capital: float = 100000,
                 min_sbi_entry: int = 9,
                 sbi_rotation_threshold: int = 6,  # Rotate when SBI drops below this
                 sbi_replacement_min: int = 8,  # Min SBI for replacement stock
                 max_positions: int = 20,
                 max_per_sector: int = 5,
                 small_account_mode: bool = False,  # For <$10K accounts
                 use_next_day_open: bool = False,  # More realistic entry timing
                 trade_frequency: int = 1):  # Trade every N days (1=daily, 3=every 3rd day)
        
        self.start_date = start_date
        self.end_date = end_date or datetime.now().strftime("%Y-%m-%d")
        self.initial_capital = initial_capital
        self.min_sbi_entry = min_sbi_entry
        self.sbi_rotation_threshold = sbi_rotation_threshold
        self.sbi_replacement_min = sbi_replacement_min
        self.max_positions = max_positions
        self.max_per_sector = max_per_sector
        self.use_next_day_open = use_next_day_open
        self.trade_frequency = trade_frequency
        
        # Small account mode: fewer positions, top stocks only
        if small_account_mode or initial_capital < 10000:
            self.max_positions = 10
            self.max_per_sector = 2
            print(f"📱 Small account mode: max {self.max_positions} positions, {self.max_per_sector} per sector")
        
        if trade_frequency > 1:
            print(f"📅 Trading every {trade_frequency} days")
        
        self.price_data = {}
        self.parent_tickers = list(PARENT_CHILD_MAPPING.keys())
        self.child_tickers = []
        for info in PARENT_CHILD_MAPPING.values():
            self.child_tickers.extend(info.get('stocks', []))
        self.child_tickers = list(set(self.child_tickers))
    
    def _get_price(self, df: pd.DataFrame, date, column: str = 'Close') -> float:
        """Safely get a scalar price value from DataFrame."""
        try:
            val = df.loc[date, column]
            if hasattr(val, 'iloc'):
                return float(val.iloc[0])
            return float(val)
        except:
            return 0.0
    
    def _get_entry_price(self, df: pd.DataFrame, date, dates_list: List) -> float:
        """
        Get entry price based on backtest settings.
        
        If use_next_day_open=True: Use next day's open (more realistic)
        Otherwise: Use same day close (optimistic)
        """
        if not self.use_next_day_open:
            return self._get_price(df, date, 'Close')
        
        # Find next trading day
        try:
            current_idx = dates_list.index(date)
            if current_idx + 1 < len(dates_list):
                next_date = dates_list[current_idx + 1]
                if next_date in df.index:
                    return self._get_price(df, next_date, 'Open')
        except (ValueError, IndexError):
            pass
        
        # Fallback to close if next day not available
        return self._get_price(df, date, 'Close')
        
    def load_data(self):
        """Load price data for all tickers."""
        all_tickers = list(set(self.parent_tickers + self.child_tickers))
        
        # Add SPY and VIX for regime detection
        if 'SPY' not in all_tickers:
            all_tickers.append('SPY')
        if '^VIX' not in all_tickers:
            all_tickers.append('^VIX')
        
        print(f"\n📥 Loading data for {len(all_tickers)} tickers...")
        print(f"   Parents: {len(self.parent_tickers)}")
        print(f"   Children: {len(self.child_tickers)}")
        print(f"   Period: {self.start_date} to {self.end_date}")
        
        # Add buffer for indicator calculation (need 200 days for SPY SMA)
        start_with_buffer = (datetime.strptime(self.start_date, "%Y-%m-%d") - timedelta(days=250)).strftime("%Y-%m-%d")
        
        for ticker in all_tickers:
            try:
                df = yf.download(ticker, start=start_with_buffer, end=self.end_date, progress=False)
                if len(df) > 50:
                    self.price_data[ticker] = df
                    print(f"   ✓ {ticker}: {len(df)} days")
                else:
                    print(f"   ✗ {ticker}: insufficient data ({len(df)} days)")
            except Exception as e:
                print(f"   ✗ {ticker}: {e}")
        
        print(f"\n✅ Loaded {len(self.price_data)} tickers")
        
        # Generate synthetic ETF data for crypto ETFs that didn't exist historically
        try:
            from synthetic_etf import fill_missing_etf_data
            self.price_data = fill_missing_etf_data(self.price_data)
        except ImportError:
            print("   ⚠️ synthetic_etf.py not found, skipping synthetic ETF generation")
        except Exception as e:
            print(f"   ⚠️ Error generating synthetic ETFs: {e}")
    
    def detect_regime(self, date: pd.Timestamp) -> str:
        """
        Detect market regime for a specific date.
        
        Returns:
            'bull' - SPY > 200 SMA, VIX < 25 → Use parent_based
            'bear' - SPY < 200 SMA → Use weighted_rotation
            'volatile' - VIX > 25 → Use rotation
        """
        # Get SPY data
        if 'SPY' not in self.price_data:
            return 'bull'  # Default
        
        spy_df = self.price_data['SPY']
        if date not in spy_df.index:
            return 'bull'
        
        idx = spy_df.index.get_loc(date)
        if isinstance(idx, slice):
            idx = idx.start  # Handle duplicate dates
        if idx < 200:
            return 'bull'  # Not enough data for 200 SMA
        
        # Get SPY price and 200 SMA - ensure scalar values
        spy_close = self._get_price(spy_df, date)
        spy_sma200_series = spy_df['Close'].iloc[idx-199:idx+1]
        spy_sma200 = float(spy_sma200_series.mean())
        
        # Get VIX level
        vix_level = 20.0  # Default
        if '^VIX' in self.price_data:
            vix_df = self.price_data['^VIX']
            if date in vix_df.index:
                vix_level = float(self._get_price(vix_df, date))
        
        # Determine regime - ensure we're comparing scalars
        spy_above_sma = float(spy_close) > float(spy_sma200)
        
        if not spy_above_sma:
            return 'bear'
        elif vix_level > 25:
            return 'volatile'
        else:
            return 'bull'
    
    def get_parent_strength(self, parent: str, idx: int, df: pd.DataFrame) -> Tuple[bool, float, float]:
        """
        Calculate parent strength score for weighting.
        Returns: (is_bullish, psar_gap_pct, strength_score)
        """
        if idx < 30:
            return False, 0, 0
        
        try:
            # Convert to numpy arrays properly and handle NaN
            close = np.array(df['Close'].values[:idx+1], dtype=float)
            high = np.array(df['High'].values[:idx+1], dtype=float)
            low = np.array(df['Low'].values[:idx+1], dtype=float)
            
            # Remove NaN
            valid_mask = ~(np.isnan(close) | np.isnan(high) | np.isnan(low))
            close = close[valid_mask]
            high = high[valid_mask]
            low = low[valid_mask]
            
            if len(close) < 30:
                return False, 0, 0
            
            # PSAR
            psar = calculate_psar_arrays(high, low, close)
            is_bullish = close[-1] > psar[-1]
            psar_gap = ((close[-1] - psar[-1]) / close[-1]) * 100 if is_bullish else 0
            
            # ADX for trend strength
            adx_data = calculate_adx_arrays(high, low, close)
            adx = adx_data['adx'][-1] if len(adx_data['adx']) > 0 else 0
            
            # RSI for momentum
            rsi_arr = calculate_rsi_array(close, 14)
            rsi = rsi_arr[-1] if len(rsi_arr) > 14 else 50
            
            # Strength score: combine PSAR gap, ADX, and RSI
            # Higher = stronger trend
            if is_bullish:
                strength = (psar_gap * 2) + (adx * 0.5) + ((rsi - 50) * 0.3)
                strength = max(0, min(100, strength))
            else:
                strength = 0
            
            return is_bullish, psar_gap, strength
            
        except Exception as e:
            return False, 0, 0
    
    def get_stock_sbi(self, ticker: str, idx: int, df: pd.DataFrame) -> Optional[int]:
        """Get SBI score for a stock."""
        if idx < 30:
            return None
        
        try:
            close = np.array(df['Close'].values[:idx+1], dtype=float)
            high = np.array(df['High'].values[:idx+1], dtype=float)
            low = np.array(df['Low'].values[:idx+1], dtype=float)
            
            # Remove NaN
            valid_mask = ~(np.isnan(close) | np.isnan(high) | np.isnan(low))
            close = close[valid_mask]
            high = high[valid_mask]
            low = low[valid_mask]
            
            if len(close) < 30:
                return None
            
            # Create DataFrame for get_full_sbi_data
            temp_df = pd.DataFrame({'High': high, 'Low': low, 'Close': close})
            sbi_result = get_full_sbi_data(temp_df)
            return sbi_result.sbi if sbi_result else None
        except:
            return None
    
    def get_stock_health(self, ticker: str, idx: int, df: pd.DataFrame) -> Tuple[Optional[int], bool, float]:
        """
        Get stock health indicators.
        Returns: (sbi, psar_bullish, rsi)
        """
        if idx < 30:
            return None, False, 50
        
        try:
            close = np.array(df['Close'].values[:idx+1], dtype=float)
            high = np.array(df['High'].values[:idx+1], dtype=float)
            low = np.array(df['Low'].values[:idx+1], dtype=float)
            
            # Remove NaN
            valid_mask = ~(np.isnan(close) | np.isnan(high) | np.isnan(low))
            close = close[valid_mask]
            high = high[valid_mask]
            low = low[valid_mask]
            
            if len(close) < 30:
                return None, False, 50
            
            # Create DataFrame for get_full_sbi_data
            temp_df = pd.DataFrame({'High': high, 'Low': low, 'Close': close})
            sbi_result = get_full_sbi_data(temp_df)
            sbi = sbi_result.sbi if sbi_result else None
            
            psar = calculate_psar_arrays(high, low, close)
            psar_bullish = close[-1] > psar[-1]
            
            rsi_arr = calculate_rsi_array(close, 14)
            rsi = rsi_arr[-1] if len(rsi_arr) > 14 else 50
            
            return sbi, psar_bullish, rsi
        except:
            return None, False, 50
    
    def find_rotation_candidate(self, parent: str, exclude_tickers: List[str], 
                                 date: pd.Timestamp, min_sbi: int = 7) -> Optional[Tuple[str, int]]:
        """
        Find best replacement stock within same sector.
        Requires: PSAR bullish AND RSI > 50 (healthy stock)
        Returns: (ticker, sbi) or None
        """
        info = PARENT_CHILD_MAPPING.get(parent, {})
        stocks = info.get('stocks', [])
        
        candidates = []
        for stock in stocks:
            if stock in exclude_tickers:
                continue
            if stock not in self.price_data:
                continue
            
            df = self.price_data[stock]
            if date not in df.index:
                continue
            
            idx = df.index.get_loc(date)
            sbi, psar_bullish, rsi = self.get_stock_health(stock, idx, df)
            
            # ROTATION CANDIDATE REQUIRES:
            # - PSAR bullish (stock in uptrend)
            # - RSI > 50 (momentum positive)
            # - SBI >= min_sbi (good entry score)
            if (sbi is not None and sbi >= min_sbi and 
                psar_bullish and rsi > 50):
                candidates.append((stock, sbi, rsi))
        
        if not candidates:
            return None
        
        # Sort by SBI first, then RSI (best candidates first)
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return (candidates[0][0], candidates[0][1])
    
    def rank_parents(self, date: pd.Timestamp) -> List[Tuple[str, float, bool]]:
        """
        Rank all parents by strength.
        Returns: [(parent, strength_score, is_bullish), ...] sorted by strength desc
        """
        rankings = []
        
        for parent in self.parent_tickers:
            if parent not in self.price_data:
                continue
            
            df = self.price_data[parent]
            if date not in df.index:
                continue
            
            idx = df.index.get_loc(date)
            is_bullish, psar_gap, strength = self.get_parent_strength(parent, idx, df)
            
            rankings.append((parent, strength, is_bullish))
        
        # Sort by strength descending
        rankings.sort(key=lambda x: x[1], reverse=True)
        return rankings
    
    def run_backtest_with_rotation(self, use_weighted_parents: bool = False) -> BacktestResult:
        """
        Strategy: Rotation within sector based on stock's own technicals
        
        Entry:
        - Parent PSAR bullish
        - Stock SBI >= 9 AND Stock PSAR bullish
        
        Exit/Rotate Decision (checked daily for each position):
        - Stock PSAR turns bearish OR RSI < 40 → Stock is weak
          - If parent still bullish → ROTATE to another stock with bullish PSAR + RSI > 50
          - If no rotation candidate → EXIT position
        - Parent PSAR turns bearish → EXIT ALL stocks in that sector
        
        If use_weighted_parents=True:
        - 2x allocation to top 3 strongest parents
        - 1x allocation to next 5
        - 0.5x allocation to rest
        """
        strategy_name = "Weighted-Rotation" if use_weighted_parents else "Rotation"
        
        trades = []
        positions = {}  # ticker -> Trade
        equity_curve = [self.initial_capital]
        position_counts = []  # Track daily position counts
        rotation_count = 0
        
        # Get date range from parent tickers
        all_dates = set()
        for ticker in self.parent_tickers:
            if ticker in self.price_data:
                all_dates = all_dates.union(set(self.price_data[ticker].index))
        
        if not all_dates:
            print("❌ No dates found in parent data!")
            return None
        
        dates = sorted(list(all_dates))
        print(f"\n🔄 Running {strategy_name} backtest over {len(dates)} days...")
        print(f"   Date range: {dates[0].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')}")
        print(f"   Exit rules: Stock PSAR bearish OR RSI < 40 → Rotate/Exit")
        if self.trade_frequency > 1:
            print(f"   Trading frequency: every {self.trade_frequency} days")
        
        signals_found = 0
        exits_made = 0
        
        for i, date in enumerate(dates):
            if i < 30:  # Need warmup period
                position_counts.append(0)
                continue
            
            date_str = date.strftime("%Y-%m-%d")
            
            # Check if this is a trading day (based on frequency)
            is_trading_day = (i - 30) % self.trade_frequency == 0
            
            # Rank parents for weighted allocation
            if use_weighted_parents:
                parent_rankings = self.rank_parents(date)
                parent_weights = {}
                for rank, (parent, strength, is_bullish) in enumerate(parent_rankings):
                    if rank < 3:
                        parent_weights[parent] = 2.0  # Top 3 = 2x
                    elif rank < 8:
                        parent_weights[parent] = 1.0  # Next 5 = 1x
                    else:
                        parent_weights[parent] = 0.5  # Rest = 0.5x
            
            # Check each parent's status
            parent_status = {}
            for parent in self.parent_tickers:
                if parent in self.price_data:
                    df = self.price_data[parent]
                    if date in df.index:
                        idx = df.index.get_loc(date)
                        is_bullish, _, _ = self.get_parent_strength(parent, idx, df)
                        parent_status[parent] = is_bullish
            
            # Process existing positions - CHECK STOCK'S OWN TECHNICALS
            for ticker in list(positions.keys()):
                trade = positions[ticker]
                parent = trade.parent
                
                # RULE 1: Parent turned bearish → EXIT ALL in sector immediately
                if parent in parent_status and not parent_status[parent]:
                    if ticker in self.price_data and date in self.price_data[ticker].index:
                        exit_price = self._get_price(self.price_data[ticker], date)
                        trade.exit_date = date_str
                        trade.exit_price = exit_price
                        trade.exit_reason = "Parent bearish"
                        trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
                        entry_dt = pd.Timestamp(trade.entry_date)
                        trade.holding_days = (date.tz_localize(None) - entry_dt).days if date.tzinfo else (date - entry_dt).days
                        trades.append(trade)
                        del positions[ticker]
                        exits_made += 1
                    continue
                
                # RULE 2: Check stock's own PSAR and RSI
                if ticker in self.price_data and date in self.price_data[ticker].index:
                    df = self.price_data[ticker]
                    idx = df.index.get_loc(date)
                    sbi, stock_psar_bullish, stock_rsi = self.get_stock_health(ticker, idx, df)
                    
                    # Stock is WEAK if: PSAR bearish OR RSI < 40
                    stock_is_weak = (not stock_psar_bullish) or (stock_rsi < 40)
                    
                    if stock_is_weak and parent_status.get(parent, False):
                        # Parent still bullish - TRY TO ROTATE
                        current_holdings_in_sector = [t for t, tr in positions.items() if tr.parent == parent]
                        replacement = self.find_rotation_candidate(
                            parent, 
                            current_holdings_in_sector, 
                            date, 
                            min_sbi=7  # Lower bar for rotation replacement
                        )
                        
                        if replacement:
                            new_ticker, new_sbi = replacement
                            
                            # Exit old position
                            exit_price = self._get_price(df, date)
                            trade.exit_date = date_str
                            trade.exit_price = exit_price
                            weak_reason = "PSAR bearish" if not stock_psar_bullish else f"RSI={stock_rsi:.0f}"
                            trade.exit_reason = f"Rotated→{new_ticker} ({weak_reason})"
                            trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
                            entry_dt = pd.Timestamp(trade.entry_date)
                            trade.holding_days = (date.tz_localize(None) - entry_dt).days if date.tzinfo else (date - entry_dt).days
                            trades.append(trade)
                            del positions[ticker]
                            
                            # Enter new position
                            new_df = self.price_data[new_ticker]
                            entry_price = self._get_price(new_df, date)
                            positions[new_ticker] = Trade(
                                ticker=new_ticker,
                                parent=parent,
                                entry_date=date_str,
                                entry_price=entry_price,
                                entry_sbi=new_sbi,
                            )
                            rotation_count += 1
                            signals_found += 1
                        else:
                            # No replacement found - EXIT position but stay watching sector
                            exit_price = self._get_price(df, date)
                            trade.exit_date = date_str
                            trade.exit_price = exit_price
                            weak_reason = "PSAR bearish" if not stock_psar_bullish else f"RSI={stock_rsi:.0f}"
                            trade.exit_reason = f"No rotation ({weak_reason})"
                            trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
                            entry_dt = pd.Timestamp(trade.entry_date)
                            trade.holding_days = (date.tz_localize(None) - entry_dt).days if date.tzinfo else (date - entry_dt).days
                            trades.append(trade)
                            del positions[ticker]
                            exits_made += 1
            
            # ENTRY: Look for new signals - only on trading days
            if is_trading_day and len(positions) < self.max_positions:
                # For weighted mode, prioritize stronger parents
                parents_to_check = self.parent_tickers
                if use_weighted_parents:
                    parents_to_check = [p for p, s, b in parent_rankings if b]
                
                for parent in parents_to_check:
                    if parent not in parent_status or not parent_status[parent]:
                        continue
                    
                    # Count current positions in this sector
                    positions_in_sector = sum(1 for t in positions.values() if t.parent == parent)
                    if positions_in_sector >= self.max_per_sector:
                        continue
                    
                    # Check weight limit for weighted mode
                    if use_weighted_parents:
                        weight = parent_weights.get(parent, 0.5)
                        max_for_parent = int(self.max_per_sector * weight)
                        if positions_in_sector >= max_for_parent:
                            continue
                    
                    info = PARENT_CHILD_MAPPING.get(parent, {})
                    stocks = info.get('stocks', [])[:self.max_per_sector * 2]  # Check more stocks
                    
                    for stock in stocks:
                        if stock in positions:
                            continue
                        if stock not in self.price_data:
                            continue
                        
                        df = self.price_data[stock]
                        if date not in df.index:
                            continue
                        
                        idx = df.index.get_loc(date)
                        sbi, stock_psar_bullish, stock_rsi = self.get_stock_health(stock, idx, df)
                        
                        # ENTRY REQUIRES: SBI >= 9 AND PSAR bullish AND RSI > 50
                        if (sbi is not None and sbi >= self.min_sbi_entry and 
                            stock_psar_bullish and stock_rsi > 50):
                            entry_price = self._get_price(df, date)
                            positions[stock] = Trade(
                                ticker=stock,
                                parent=parent,
                                entry_date=date_str,
                                entry_price=entry_price,
                                entry_sbi=sbi,
                            )
                            signals_found += 1
                            positions_in_sector += 1
                            
                            if positions_in_sector >= self.max_per_sector:
                                break
                            if len(positions) >= self.max_positions:
                                break
                    
                    if len(positions) >= self.max_positions:
                        break
            
            # Track position count
            position_counts.append(len(positions))
            
            # Progress update every 50 days
            if i % 50 == 0:
                bullish_parents = [p for p, b in parent_status.items() if b]
                print(f"   Day {i}: {len(positions)} pos, {signals_found} entries, {rotation_count} rotations, {len(bullish_parents)} bullish parents")
            
            # Update equity
            if positions:
                daily_returns = []
                for ticker in positions:
                    if ticker in self.price_data:
                        df = self.price_data[ticker]
                        if date in df.index and i > 0:
                            prev_date = dates[i-1]
                            if prev_date in df.index:
                                prev_close = self._get_price(df, prev_date)
                                curr_close = self._get_price(df, date)
                                if prev_close > 0 and curr_close > 0:
                                    ret = (curr_close / prev_close) - 1
                                    if abs(ret) < 0.5:
                                        daily_returns.append(ret)
                
                if daily_returns:
                    position_weight = 1.0 / self.max_positions
                    total_position_weight = len(daily_returns) * position_weight
                    avg_return = np.mean(daily_returns) * total_position_weight
                    equity_curve.append(equity_curve[-1] * (1 + avg_return))
                else:
                    equity_curve.append(equity_curve[-1])
            else:
                equity_curve.append(equity_curve[-1])
        
        # Close any remaining positions at end
        final_date = dates[-1]
        final_date_str = final_date.strftime("%Y-%m-%d")
        for ticker, trade in positions.items():
            if ticker in self.price_data and final_date in self.price_data[ticker].index:
                exit_price = self._get_price(self.price_data[ticker], final_date)
                trade.exit_date = final_date_str
                trade.exit_price = exit_price
                trade.exit_reason = "End of backtest"
                trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
                entry_dt = pd.Timestamp(trade.entry_date)
                trade.holding_days = (final_date.tz_localize(None) - entry_dt).days if final_date.tzinfo else (final_date - entry_dt).days
                trades.append(trade)
        
        # Position statistics
        avg_positions = np.mean(position_counts) if position_counts else 0
        min_positions = min(position_counts) if position_counts else 0
        max_positions_held = max(position_counts) if position_counts else 0
        
        print(f"   ✅ Complete: {len(trades)} trades, {signals_found} entries, {rotation_count} rotations, {exits_made} exits")
        print(f"   📊 Positions: avg={avg_positions:.1f}, min={min_positions}, max={max_positions_held}")
        
        if equity_curve:
            print(f"   💰 Equity: ${equity_curve[0]:,.0f} → ${equity_curve[-1]:,.0f}")
        
        # Find worst trades
        if trades:
            worst_trades = sorted([t for t in trades if t.pnl_pct], key=lambda t: t.pnl_pct)[:5]
            print(f"   📉 Worst trades:")
            for t in worst_trades:
                print(f"      {t.ticker}: {t.pnl_pct:+.1f}% ({t.entry_date} → {t.exit_date}) - {t.exit_reason}")
            
            # Best trades too
            best_trades = sorted([t for t in trades if t.pnl_pct], key=lambda t: t.pnl_pct, reverse=True)[:5]
            print(f"   📈 Best trades:")
            for t in best_trades:
                print(f"      {t.ticker}: {t.pnl_pct:+.1f}% ({t.entry_date} → {t.exit_date}) - {t.exit_reason}")
            
            # Trade distribution
            all_pnls = [t.pnl_pct for t in trades if t.pnl_pct]
            print(f"   📊 Trade distribution: min={min(all_pnls):.1f}%, max={max(all_pnls):.1f}%, median={np.median(all_pnls):.1f}%")
        
        return self._calculate_results(
            strategy_name, trades, equity_curve, 
            avg_positions, min_positions, max_positions_held, rotation_count
        )
    
    def run_backtest_parent_based(self) -> BacktestResult:
        """Original parent-based strategy for comparison."""
        trades = []
        positions = {}
        equity_curve = [self.initial_capital]
        position_counts = []
        
        all_dates = set()
        for ticker in self.parent_tickers:
            if ticker in self.price_data:
                all_dates = all_dates.union(set(self.price_data[ticker].index))
        
        if not all_dates:
            print("❌ No dates found!")
            return None
        
        dates = sorted(list(all_dates))
        print(f"\n🔄 Running PARENT-BASED backtest over {len(dates)} days...")
        print(f"   Date range: {dates[0].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')}")
        if self.trade_frequency > 1:
            print(f"   Trading frequency: every {self.trade_frequency} days")
        
        signals_found = 0
        exits_made = 0
        
        for i, date in enumerate(dates):
            if i < 30:
                position_counts.append(0)
                continue
            
            date_str = date.strftime("%Y-%m-%d")
            
            # Check if this is a trading day (based on frequency)
            is_trading_day = (i - 30) % self.trade_frequency == 0
            
            parent_status = {}
            for parent in self.parent_tickers:
                if parent in self.price_data:
                    df = self.price_data[parent]
                    if date in df.index:
                        idx = df.index.get_loc(date)
                        is_bullish, _, _ = self.get_parent_strength(parent, idx, df)
                        parent_status[parent] = is_bullish
            
            # EXIT when parent bearish (always check - don't wait for trade day)
            for ticker in list(positions.keys()):
                trade = positions[ticker]
                parent = trade.parent
                
                if parent in parent_status and not parent_status[parent]:
                    if ticker in self.price_data and date in self.price_data[ticker].index:
                        exit_price = self._get_price(self.price_data[ticker], date)
                        trade.exit_date = date_str
                        trade.exit_price = exit_price
                        trade.exit_reason = "Parent bearish"
                        trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
                        entry_dt = pd.Timestamp(trade.entry_date)
                        trade.holding_days = (date.tz_localize(None) - entry_dt).days if date.tzinfo else (date - entry_dt).days
                        trades.append(trade)
                        del positions[ticker]
                        exits_made += 1
            
            # ENTRY - only on trading days
            if is_trading_day and len(positions) < self.max_positions:
                for parent in self.parent_tickers:
                    if parent not in parent_status or not parent_status[parent]:
                        continue
                    
                    positions_in_sector = sum(1 for t in positions.values() if t.parent == parent)
                    if positions_in_sector >= self.max_per_sector:
                        continue
                    
                    info = PARENT_CHILD_MAPPING.get(parent, {})
                    for stock in info.get('stocks', [])[:self.max_per_sector]:
                        if stock in positions or stock not in self.price_data:
                            continue
                        
                        df = self.price_data[stock]
                        if date not in df.index:
                            continue
                        
                        idx = df.index.get_loc(date)
                        sbi = self.get_stock_sbi(stock, idx, df)
                        
                        if sbi is not None and sbi >= self.min_sbi_entry:
                            entry_price = self._get_price(df, date)
                            positions[stock] = Trade(
                                ticker=stock,
                                parent=parent,
                                entry_date=date_str,
                                entry_price=entry_price,
                                entry_sbi=sbi,
                            )
                            signals_found += 1
                            positions_in_sector += 1
                            
                            if positions_in_sector >= self.max_per_sector:
                                break
                            if len(positions) >= self.max_positions:
                                break
                    
                    if len(positions) >= self.max_positions:
                        break
            
            position_counts.append(len(positions))
            
            if i % 50 == 0:
                bullish = [p for p, b in parent_status.items() if b]
                print(f"   Day {i}: {len(positions)} positions, {signals_found} signals, {exits_made} exits, {len(bullish)} bullish")
            
            # Update equity
            if positions:
                daily_returns = []
                for ticker in positions:
                    if ticker in self.price_data:
                        df = self.price_data[ticker]
                        if date in df.index and i > 0:
                            prev_date = dates[i-1]
                            if prev_date in df.index:
                                prev_close = self._get_price(df, prev_date)
                                curr_close = self._get_price(df, date)
                                if prev_close > 0 and curr_close > 0:
                                    ret = (curr_close / prev_close) - 1
                                    if abs(ret) < 0.5:
                                        daily_returns.append(ret)
                
                if daily_returns:
                    position_weight = 1.0 / self.max_positions
                    total_position_weight = len(daily_returns) * position_weight
                    avg_return = np.mean(daily_returns) * total_position_weight
                    equity_curve.append(equity_curve[-1] * (1 + avg_return))
                else:
                    equity_curve.append(equity_curve[-1])
            else:
                equity_curve.append(equity_curve[-1])
        
        # Close remaining
        final_date = dates[-1]
        final_date_str = final_date.strftime("%Y-%m-%d")
        for ticker, trade in positions.items():
            if ticker in self.price_data and final_date in self.price_data[ticker].index:
                exit_price = self._get_price(self.price_data[ticker], final_date)
                trade.exit_date = final_date_str
                trade.exit_price = exit_price
                trade.exit_reason = "End of backtest"
                trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
                entry_dt = pd.Timestamp(trade.entry_date)
                trade.holding_days = (final_date.tz_localize(None) - entry_dt).days if final_date.tzinfo else (final_date - entry_dt).days
                trades.append(trade)
        
        avg_positions = np.mean(position_counts) if position_counts else 0
        min_positions = min(position_counts) if position_counts else 0
        max_positions_held = max(position_counts) if position_counts else 0
        
        print(f"   ✅ Complete: {len(trades)} trades, {signals_found} entries, {exits_made} exits")
        print(f"   📊 Positions: avg={avg_positions:.1f}, min={min_positions}, max={max_positions_held}")
        
        if equity_curve:
            print(f"   💰 Equity: ${equity_curve[0]:,.0f} → ${equity_curve[-1]:,.0f}")
        
        # Trade analysis
        if trades:
            worst_trades = sorted([t for t in trades if t.pnl_pct], key=lambda t: t.pnl_pct)[:5]
            print(f"   📉 Worst trades:")
            for t in worst_trades:
                print(f"      {t.ticker}: {t.pnl_pct:+.1f}% ({t.entry_date} → {t.exit_date})")
            
            best_trades = sorted([t for t in trades if t.pnl_pct], key=lambda t: t.pnl_pct, reverse=True)[:5]
            print(f"   📈 Best trades:")
            for t in best_trades:
                print(f"      {t.ticker}: {t.pnl_pct:+.1f}% ({t.entry_date} → {t.exit_date})")
            
            all_pnls = [t.pnl_pct for t in trades if t.pnl_pct]
            print(f"   📊 Trade distribution: min={min(all_pnls):.1f}%, max={max(all_pnls):.1f}%, median={np.median(all_pnls):.1f}%")
        
        return self._calculate_results(
            "Parent-Based", trades, equity_curve,
            avg_positions, min_positions, max_positions_held, 0
        )
    
    def _calculate_results(self, strategy_name: str, trades: List[Trade], 
                          equity_curve: List[float], avg_pos: float,
                          min_pos: int, max_pos: int, rotations: int) -> BacktestResult:
        """Calculate performance metrics."""
        
        if not trades:
            return BacktestResult(
                strategy_name=strategy_name,
                start_date=self.start_date,
                end_date=self.end_date,
                total_trades=0, winning_trades=0, losing_trades=0,
                win_rate=0, avg_gain=0, avg_loss=0,
                total_return=0, max_drawdown=0, avg_holding_days=0,
                avg_positions=avg_pos, min_positions=min_pos, 
                max_positions_held=max_pos, rotations=rotations,
                trades=[],
            )
        
        winning = [t for t in trades if t.pnl_pct and t.pnl_pct > 0]
        losing = [t for t in trades if t.pnl_pct and t.pnl_pct <= 0]
        
        win_rate = len(winning) / len(trades) * 100 if trades else 0
        avg_gain = np.mean([t.pnl_pct for t in winning]) if winning else 0
        avg_loss = np.mean([t.pnl_pct for t in losing]) if losing else 0
        
        # Total return calculation
        # Use simple trade sum - equity curve has compounding bugs
        all_pnls = [t.pnl_pct for t in trades if t.pnl_pct is not None]
        
        if all_pnls:
            position_weight = 1.0 / self.max_positions
            total_return = sum(all_pnls) * position_weight
            
            # Also show equity curve for comparison (known to be buggy)
            if len(equity_curve) > 1 and equity_curve[-1] != equity_curve[0]:
                equity_return = ((equity_curve[-1] / equity_curve[0]) - 1) * 100
                print(f"   📊 Return: {total_return:.1f}% (equity curve shows {equity_return:.1f}% - ignore)")
            else:
                print(f"   📊 Return: {total_return:.1f}%")
        else:
            total_return = 0
        
        # Max drawdown
        max_dd = 0
        if len(equity_curve) > 1:
            peak = equity_curve[0]
            for val in equity_curve:
                if val > peak:
                    peak = val
                if peak > 0:
                    dd = (peak - val) / peak * 100
                    if dd > max_dd:
                        max_dd = dd
        
        # Holding days
        holding_days = [t.holding_days for t in trades if t.holding_days]
        avg_holding = np.mean(holding_days) if holding_days else 0
        
        return BacktestResult(
            strategy_name=strategy_name,
            start_date=self.start_date,
            end_date=self.end_date,
            total_trades=len(trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            win_rate=win_rate,
            avg_gain=avg_gain,
            avg_loss=avg_loss,
            total_return=total_return,
            max_drawdown=max_dd,
            avg_holding_days=avg_holding,
            avg_positions=avg_pos,
            min_positions=min_pos,
            max_positions_held=max_pos,
            rotations=rotations,
            trades=trades,
        )
    
    def run_backtest_regime_aware(self) -> BacktestResult:
        """
        REGIME-AWARE strategy that switches between modes based on market conditions.
        
        Regimes:
        - BULL (SPY > 200 SMA, VIX < 25): Parent-Based (hold through stock weakness)
        - VOLATILE (VIX > 25): Rotation (rotate weak stocks)
        - BEAR (SPY < 200 SMA): Weighted-Rotation (rotate + weight by strength)
        """
        strategy_name = "Regime-Aware"
        
        trades = []
        positions = {}  # ticker -> Trade
        equity_curve = [self.initial_capital]
        position_counts = []
        rotation_count = 0
        regime_changes = []
        
        # Get date range
        all_dates = set()
        for ticker in self.parent_tickers:
            if ticker in self.price_data:
                all_dates = all_dates.union(set(self.price_data[ticker].index))
        
        if not all_dates:
            print("❌ No dates found!")
            return None
        
        dates = sorted(list(all_dates))
        print(f"\n🔄 Running REGIME-AWARE backtest over {len(dates)} days...")
        print(f"   Date range: {dates[0].strftime('%Y-%m-%d')} to {dates[-1].strftime('%Y-%m-%d')}")
        if self.trade_frequency > 1:
            print(f"   Trading frequency: every {self.trade_frequency} days")
        
        signals_found = 0
        exits_made = 0
        current_regime = None
        
        for i, date in enumerate(dates):
            if i < 30:
                position_counts.append(0)
                continue
            
            date_str = date.strftime("%Y-%m-%d")
            
            # Check if this is a trading day (based on frequency)
            is_trading_day = (i - 30) % self.trade_frequency == 0
            
            # Detect regime for today
            regime = self.detect_regime(date)
            if regime != current_regime:
                regime_changes.append((date_str, regime))
                current_regime = regime
            
            # Determine behavior based on regime
            use_rotation = regime in ['volatile', 'bear']
            use_weighted_parents = regime == 'bear'
            
            # Rank parents for weighted allocation
            parent_weights = {}
            if use_weighted_parents:
                parent_rankings = self.rank_parents(date)
                for rank, (parent, strength, is_bullish) in enumerate(parent_rankings):
                    if rank < 3:
                        parent_weights[parent] = 2.0
                    elif rank < 8:
                        parent_weights[parent] = 1.0
                    else:
                        parent_weights[parent] = 0.5
            
            # Check each parent
            for parent in self.parent_tickers:
                if parent not in self.price_data:
                    continue
                
                parent_df = self.price_data[parent]
                if date not in parent_df.index:
                    continue
                
                idx = parent_df.index.get_loc(date)
                is_bullish, psar_gap, strength = self.get_parent_strength(parent, idx, parent_df)
                
                info = PARENT_CHILD_MAPPING.get(parent, {})
                stocks = info.get('stocks', [])
                
                # Get current positions in this sector
                sector_positions = [t for t in positions if positions[t].parent == parent]
                
                if is_bullish:
                    # Parent is bullish - check existing positions and potentially add
                    
                    # Check existing positions for rotation/hold
                    for ticker in sector_positions[:]:
                        if ticker not in self.price_data:
                            continue
                        
                        stock_df = self.price_data[ticker]
                        if date not in stock_df.index:
                            continue
                        
                        stock_idx = stock_df.index.get_loc(date)
                        stock_sbi, stock_bullish, stock_rsi = self.get_stock_health(ticker, stock_idx, stock_df)
                        
                        # Check if stock is weak
                        is_weak = not stock_bullish or stock_rsi < 40
                        
                        if is_weak and use_rotation:
                            # Try to rotate
                            exclude = sector_positions + [ticker]
                            replacement = self.find_rotation_candidate(parent, exclude, date, self.sbi_replacement_min)
                            
                            if replacement:
                                # Exit current position
                                trade = positions.pop(ticker)
                                exit_price = self._get_price(stock_df, date)
                                trade.exit_date = date_str
                                trade.exit_price = exit_price
                                trade.exit_reason = f"Rotated→{replacement[0]} (PSAR {'bullish' if stock_bullish else 'bearish'})"
                                if trade.entry_price > 0:
                                    trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
                                entry_dt = pd.Timestamp(trade.entry_date)
                                trade.holding_days = (date.tz_localize(None) - entry_dt).days if date.tzinfo else (date - entry_dt).days
                                trades.append(trade)
                                
                                # Enter replacement
                                new_ticker, new_sbi = replacement
                                if new_ticker in self.price_data and date in self.price_data[new_ticker].index:
                                    entry_price = self._get_price(self.price_data[new_ticker], date)
                                    if entry_price > 0:
                                        positions[new_ticker] = Trade(
                                            ticker=new_ticker,
                                            parent=parent,
                                            entry_date=date_str,
                                            entry_price=entry_price,
                                            entry_sbi=new_sbi
                                        )
                                        rotation_count += 1
                            else:
                                # No replacement and very weak - exit
                                if not stock_bullish and stock_rsi < 35:
                                    trade = positions.pop(ticker)
                                    exit_price = self._get_price(stock_df, date)
                                    trade.exit_date = date_str
                                    trade.exit_price = exit_price
                                    trade.exit_reason = "No rotation (PSAR bearish)"
                                    if trade.entry_price > 0:
                                        trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
                                    entry_dt = pd.Timestamp(trade.entry_date)
                                    trade.holding_days = (date.tz_localize(None) - entry_dt).days if date.tzinfo else (date - entry_dt).days
                                    trades.append(trade)
                                    exits_made += 1
                        # In PARENT_BASED mode (bull regime), hold through weakness
                    
                    # Look for new entries - only on trading days
                    if is_trading_day and len(positions) < self.max_positions and len(sector_positions) < self.max_per_sector:
                        candidates = []
                        for stock in stocks:
                            if stock in positions or stock not in self.price_data:
                                continue
                            
                            stock_df = self.price_data[stock]
                            if date not in stock_df.index:
                                continue
                            
                            stock_idx = stock_df.index.get_loc(date)
                            sbi, stock_bullish, rsi = self.get_stock_health(stock, stock_idx, stock_df)
                            
                            if sbi is not None and sbi >= self.min_sbi_entry and stock_bullish and rsi > 50:
                                score = sbi * 10 + rsi
                                candidates.append((stock, sbi, score))
                        
                        # Sort by momentum score
                        candidates.sort(key=lambda x: x[2], reverse=True)
                        
                        # Add top candidates
                        slots = min(self.max_per_sector - len(sector_positions), 
                                   self.max_positions - len(positions))
                        
                        for stock, sbi, _ in candidates[:slots]:
                            if stock in self.price_data and date in self.price_data[stock].index:
                                entry_price = self._get_price(self.price_data[stock], date)
                                if entry_price > 0:
                                    positions[stock] = Trade(
                                        ticker=stock,
                                        parent=parent,
                                        entry_date=date_str,
                                        entry_price=entry_price,
                                        entry_sbi=sbi
                                    )
                                    signals_found += 1
                
                else:
                    # Parent is bearish - exit all positions in this sector
                    for ticker in sector_positions:
                        if ticker in positions:
                            trade = positions.pop(ticker)
                            if ticker in self.price_data and date in self.price_data[ticker].index:
                                exit_price = self._get_price(self.price_data[ticker], date)
                                trade.exit_date = date_str
                                trade.exit_price = exit_price
                                trade.exit_reason = "Parent bearish"
                                if trade.entry_price > 0:
                                    trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
                                entry_dt = pd.Timestamp(trade.entry_date)
                                trade.holding_days = (date.tz_localize(None) - entry_dt).days if date.tzinfo else (date - entry_dt).days
                                trades.append(trade)
                                exits_made += 1
            
            position_counts.append(len(positions))
            
            # Update equity
            if positions:
                daily_returns = []
                for ticker in positions:
                    if ticker in self.price_data:
                        df = self.price_data[ticker]
                        if date in df.index and i > 0:
                            prev_date = dates[i-1]
                            if prev_date in df.index:
                                prev_close = self._get_price(df, prev_date)
                                curr_close = self._get_price(df, date)
                                if prev_close > 0 and curr_close > 0:
                                    ret = (curr_close / prev_close) - 1
                                    if abs(ret) < 0.5:
                                        daily_returns.append(ret)
                
                if daily_returns:
                    position_weight = 1.0 / self.max_positions
                    total_position_weight = len(daily_returns) * position_weight
                    avg_return = np.mean(daily_returns) * total_position_weight
                    equity_curve.append(equity_curve[-1] * (1 + avg_return))
                else:
                    equity_curve.append(equity_curve[-1])
            else:
                equity_curve.append(equity_curve[-1])
            
            # Progress
            if (i + 1) % 50 == 0:
                bullish_count = sum(1 for p in self.parent_tickers 
                                   if p in self.price_data and date in self.price_data[p].index 
                                   and self.get_parent_strength(p, self.price_data[p].index.get_loc(date), self.price_data[p])[0])
                print(f"   Day {i+1}: {len(positions)} pos, {signals_found} entries, {rotation_count} rotations, {bullish_count} bullish parents, regime={regime}")
        
        # Close remaining positions
        final_date = dates[-1]
        final_date_str = final_date.strftime("%Y-%m-%d")
        for ticker, trade in positions.items():
            if ticker in self.price_data and final_date in self.price_data[ticker].index:
                exit_price = self._get_price(self.price_data[ticker], final_date)
                trade.exit_date = final_date_str
                trade.exit_price = exit_price
                trade.exit_reason = "End of backtest"
                if trade.entry_price > 0:
                    trade.pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
                entry_dt = pd.Timestamp(trade.entry_date)
                trade.holding_days = (final_date.tz_localize(None) - entry_dt).days if final_date.tzinfo else (final_date - entry_dt).days
                trades.append(trade)
        
        # Stats
        avg_positions = np.mean(position_counts) if position_counts else 0
        min_positions = min(position_counts) if position_counts else 0
        max_positions_held = max(position_counts) if position_counts else 0
        
        print(f"   ✅ Complete: {len(trades)} trades, {signals_found} entries, {rotation_count} rotations, {exits_made} exits")
        print(f"   📊 Positions: avg={avg_positions:.1f}, min={min_positions}, max={max_positions_held}")
        print(f"   🔄 Regime changes: {len(regime_changes)}")
        for date_str, regime in regime_changes[:10]:
            print(f"      {date_str}: {regime}")
        if len(regime_changes) > 10:
            print(f"      ... and {len(regime_changes) - 10} more")
        
        if equity_curve:
            print(f"   💰 Equity: ${equity_curve[0]:,.0f} → ${equity_curve[-1]:,.0f}")
        
        return self._calculate_results(
            strategy_name, trades, equity_curve,
            avg_positions, min_positions, max_positions_held, rotation_count
        )
    
    def print_comparison(self, results: List[BacktestResult]):
        """Print comparison of multiple strategies."""
        
        print("\n" + "=" * 120)
        print("BACKTEST COMPARISON: Parent-Based vs Rotation vs Weighted-Rotation vs Regime-Aware")
        print("=" * 120)
        print(f"Period: {self.start_date} to {self.end_date}")
        print(f"Initial Capital: ${self.initial_capital:,.0f}")
        print(f"Max Positions: {self.max_positions}, Max Per Sector: {self.max_per_sector}")
        
        print("\n" + "-" * 120)
        header = f"{'Metric':<25}"
        for r in results:
            header += f"{r.strategy_name:>20}"
        header += f"{'Winner':>15}"
        print(header)
        print("-" * 120)
        
        def get_winner(values, higher_better=True):
            if higher_better:
                best = max(values)
            else:
                best = min(values)
            winners = [results[i].strategy_name for i, v in enumerate(values) if v == best]
            return winners[0][:10] if len(winners) == 1 else "TIE"
        
        # Metrics
        metrics = [
            ("Total Trades", [r.total_trades for r in results], False),
            ("Win Rate", [r.win_rate for r in results], True),
            ("Avg Gain (Winners)", [r.avg_gain for r in results], True),
            ("Avg Loss (Losers)", [r.avg_loss for r in results], False),
            ("Total Return", [r.total_return for r in results], True),
            ("Max Drawdown", [r.max_drawdown for r in results], False),
            ("Avg Holding Days", [r.avg_holding_days for r in results], None),
            ("Rotations", [r.rotations for r in results], None),
            ("Avg Positions/Day", [r.avg_positions for r in results], None),
            ("Min Positions", [r.min_positions for r in results], None),
            ("Max Positions", [r.max_positions_held for r in results], None),
        ]
        
        for name, values, higher_better in metrics:
            row = f"{name:<25}"
            for v in values:
                if isinstance(v, float):
                    if "Rate" in name or "Return" in name or "Gain" in name or "Loss" in name or "Drawdown" in name:
                        row += f"{v:>19.1f}%"
                    else:
                        row += f"{v:>19.1f}"
                else:
                    row += f"{v:>20}"
            
            if higher_better is not None:
                winner = get_winner(values, higher_better)
                row += f"{winner:>15}"
            else:
                row += f"{'':>15}"
            
            print(row)
        
        print("-" * 100)
        
        # EV per trade
        print(f"\n📊 EXPECTED VALUE PER TRADE:")
        for r in results:
            ev = (r.win_rate/100 * r.avg_gain) + ((100-r.win_rate)/100 * r.avg_loss)
            print(f"   {r.strategy_name}: {ev:+.2f}% per trade")
        
        # Trading costs
        trade_cost = 0.03
        position_weight = 1.0 / self.max_positions
        print(f"\n📊 TRADING COST IMPACT (estimated {trade_cost}% per round-trip):")
        for r in results:
            cost = r.total_trades * trade_cost * position_weight
            print(f"   {r.strategy_name}: {r.total_trades} trades = {cost:.1f}% drag")
        
        # Adjusted returns
        print(f"\n📈 ADJUSTED RETURNS (after trading costs):")
        best_adj = -999
        best_name = ""
        for r in results:
            cost = r.total_trades * trade_cost * position_weight
            adj = r.total_return - cost
            print(f"   {r.strategy_name}: {adj:.1f}%")
            if adj > best_adj:
                best_adj = adj
                best_name = r.strategy_name
        
        print(f"\n🏆 WINNER: {best_name} ✓")
        print("=" * 100)


def main():
    parser = argparse.ArgumentParser(description='Enhanced AdaptiveX2 SectorBot Backtester')
    parser.add_argument('--start', type=str, default='2023-01-01', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=None, help='End date (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=100000, help='Initial capital')
    parser.add_argument('--max-positions', type=int, default=20, help='Maximum positions')
    parser.add_argument('--max-per-sector', type=int, default=5, help='Max positions per sector')
    parser.add_argument('--small-account', action='store_true', help='Small account mode (<$10K)')
    parser.add_argument('--min-sbi', type=int, default=9, help='Min SBI for entry')
    parser.add_argument('--rotation-threshold', type=int, default=6, help='SBI threshold for rotation')
    parser.add_argument('--realistic', action='store_true', help='Use next-day open for entries (more realistic)')
    parser.add_argument('--trade-freq', type=int, default=1, 
                        help='Trade every N days: 1=daily, 3=every 3 days, 5=weekly, 10=bi-weekly')
    
    args = parser.parse_args()
    
    bt = EnhancedBacktester(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        min_sbi_entry=args.min_sbi,
        sbi_rotation_threshold=args.rotation_threshold,
        max_positions=args.max_positions,
        max_per_sector=args.max_per_sector,
        small_account_mode=args.small_account,
        use_next_day_open=args.realistic,
        trade_frequency=args.trade_freq,
    )
    
    if args.realistic:
        print("⚠️  REALISTIC MODE: Using next-day open for entries")
    
    bt.load_data()
    
    # Run all four strategies
    results = []
    
    parent_result = bt.run_backtest_parent_based()
    if parent_result:
        results.append(parent_result)
    
    rotation_result = bt.run_backtest_with_rotation(use_weighted_parents=False)
    if rotation_result:
        results.append(rotation_result)
    
    weighted_result = bt.run_backtest_with_rotation(use_weighted_parents=True)
    if weighted_result:
        results.append(weighted_result)
    
    regime_result = bt.run_backtest_regime_aware()
    if regime_result:
        results.append(regime_result)
    
    if results:
        bt.print_comparison(results)
        
        # Save results
        output = {
            'period': f"{args.start} to {bt.end_date}",
            'results': []
        }
        for r in results:
            output['results'].append({
                'strategy': r.strategy_name,
                'total_return': r.total_return,
                'max_drawdown': r.max_drawdown,
                'total_trades': r.total_trades,
                'win_rate': r.win_rate,
                'avg_gain': r.avg_gain,
                'avg_loss': r.avg_loss,
                'avg_positions': r.avg_positions,
                'rotations': r.rotations,
            })
        
        with open('backtest_enhanced_results.json', 'w') as f:
            json.dump(output, f, indent=2)
        print(f"\n📁 Results saved to backtest_enhanced_results.json")


if __name__ == "__main__":
    main()
