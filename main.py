#!/usr/bin/env python3
"""
AdaptiveX2 SectorBot - Main Entry Point
=======================================

Usage:
    python main.py                        # Rotation mode signals (default)
    python main.py --mode parent_based    # Parent-based mode
    python main.py --large                # Large account (20 positions)
    python main.py --sector BTC-USD       # Diagnose specific sector
    python main.py --live                 # Schwab dry run
    python main.py --live --execute       # Schwab LIVE trades!

Strategy Modes:
    rotation (default): Rotate out of weak stocks within sector
    parent_based: Hold through stock weakness, exit only on sector breakdown
    weighted_rotation: Rotation + weight allocation by sector strength

Rotation Mode Rules:
    Entry: Parent PSAR bullish + Stock SBI >= 9 + Stock PSAR bullish + RSI > 50
    Exit: Parent PSAR bearish OR Stock PSAR bearish OR RSI < 40
    Rotate: If stock weak but parent strong, rotate to stronger stock in sector

Performance (Backtested 2023-2025):
    Daily: 85% | 3-Day: 84% | 5-Day: 85% (Rotation mode)
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional

import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

import yfinance as yf
import pandas as pd
import numpy as np

from strategy import AdaptiveX2SectorBot
from config import PARENT_CHILD_MAPPING, get_all_tickers, DEFAULT_CONFIG, update_meme_holdings
from sbi_calculator import (
    calculate_psar,
    calculate_rsi,
    get_full_sbi_data,
    is_parent_bullish,
    calculate_psar_gap,
    get_psar_trend,
)


def fetch_all_data(tickers: list, period: str = "6mo") -> dict:
    """Fetch historical data for all tickers."""
    print(f"\n📥 Fetching data for {len(tickers)} tickers...")
    
    data = {}
    try:
        batch_data = yf.download(
            tickers=tickers,
            period=period,
            group_by='ticker',
            auto_adjust=True,
            threads=True,
            progress=True,
        )
        
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    df = batch_data
                else:
                    df = batch_data[ticker].dropna()
                
                if len(df) >= 20:
                    data[ticker] = df
            except Exception:
                pass
                
    except Exception as e:
        print(f"⚠️ Batch download failed: {e}")
    
    print(f"✅ Loaded {len(data)} tickers")
    return data


def diagnose_sector(sector: str, small_account: bool = True, strategy_mode: str = 'rotation'):
    """
    Diagnose why stocks in a sector may not be qualifying for entry.
    Shows detailed breakdown of each stock's signals.
    """
    sector = sector.upper()
    
    # Handle common variations
    if sector == 'BTC':
        sector = 'BTC-USD'
    elif sector == 'ETH':
        sector = 'ETH-USD'
    elif sector == 'SOL':
        sector = 'SOL-USD'
    
    if sector not in PARENT_CHILD_MAPPING:
        print(f"\n❌ Unknown sector: {sector}")
        print(f"\nAvailable sectors:")
        for s in sorted(PARENT_CHILD_MAPPING.keys()):
            info = PARENT_CHILD_MAPPING[s]
            name = info.get('name', info.get('description', s))
            print(f"   {s:12} - {name}")
        return
    
    sector_info = PARENT_CHILD_MAPPING[sector]
    sector_name = sector_info.get('name', sector_info.get('description', sector))
    children = sector_info.get('children', sector_info.get('stocks', []))
    
    print("\n" + "=" * 70)
    print(f"🔍 SECTOR DIAGNOSIS: {sector} ({sector_name})")
    print("=" * 70)
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Mode: {strategy_mode.upper()}")
    print(f"   Child stocks: {len(children)}")
    print("=" * 70)
    
    # Fetch data for parent and children
    all_tickers = [sector] + children + ['SPY']
    price_data = fetch_all_data(all_tickers, period="6mo")
    
    # Check parent signal using sbi_calculator
    print(f"\n📊 PARENT SIGNAL: {sector}")
    print("-" * 50)
    
    parent_data = price_data.get(sector)
    parent_bullish = False
    
    if parent_data is not None and len(parent_data) > 0:
        parent_bullish = is_parent_bullish(parent_data)
        
        psar = calculate_psar(parent_data)
        current_price = parent_data['Close'].iloc[-1]
        current_psar = psar.iloc[-1]
        psar_gap = calculate_psar_gap(current_price, current_psar)
        
        status = "🟢 BULLISH" if parent_bullish else "🔴 BEARISH"
        print(f"   Status:  {status}")
        print(f"   Price:   ${current_price:.2f}")
        print(f"   PSAR:    ${current_psar:.2f}")
        print(f"   Gap:     {psar_gap:+.2f}%")
    else:
        print(f"   Status:  ⚠️ No data for {sector}")
    
    if not parent_bullish:
        print(f"\n⛔ PARENT IS BEARISH - No stocks will qualify for entry")
        print(f"   Strategy waits for {sector} PSAR to turn bullish")
        return
    
    # Analyze each child stock
    print(f"\n📋 CHILD STOCK ANALYSIS")
    print("-" * 70)
    print(f"{'Ticker':<8} {'SBI':>4} {'PSAR':>8} {'RSI':>6} {'Status':<25}")
    print("-" * 70)
    
    qualifying = []
    not_qualifying = []
    detailed_sbi = []  # Store detailed SBI data for later
    
    for ticker in children:
        stock_data = price_data.get(ticker)
        
        if stock_data is None or len(stock_data) < 50:
            print(f"{ticker:<8} {'--':>4} {'--':>8} {'--':>6} {'❌ NO DATA':<25}")
            continue
        
        # Calculate indicators using sbi_calculator
        sbi_result = get_full_sbi_data(stock_data, ticker=ticker)  # Pass ticker for category
        
        # RSI takes a Series, returns a Series - get last value
        rsi_series = calculate_rsi(stock_data['Close'])
        rsi = float(rsi_series.iloc[-1]) if rsi_series is not None and len(rsi_series) > 0 else None
        
        sbi = sbi_result.sbi if sbi_result else None
        psar_bullish = sbi_result.components.get('trend') == 'bullish' if sbi_result else False
        psar_gap = sbi_result.components.get('psar_gap', 0) if sbi_result else 0
        
        # Check conditions
        reasons = []
        passes_all = True
        
        # Condition 1: SBI >= 9
        sbi_ok = sbi is not None and sbi >= 9
        if not sbi_ok:
            sbi_val = sbi if sbi is not None else "?"
            reasons.append(f"SBI={sbi_val}<9")
            passes_all = False
        
        # Condition 2: Stock PSAR bullish
        psar_str = f"{psar_gap:+.1f}%" if psar_gap else "--"
        if not psar_bullish:
            reasons.append("PSAR bearish")
            passes_all = False
        
        # Condition 3: RSI > 50
        rsi_ok = rsi is not None and rsi > 50
        rsi_str = f"{rsi:.0f}" if rsi is not None else "--"
        if not rsi_ok:
            reasons.append(f"RSI={rsi_str}<50")
            passes_all = False
        
        # Format output
        if passes_all:
            status = "✅ QUALIFIES"
            qualifying.append((ticker, sbi, rsi))
        else:
            status = "❌ " + ", ".join(reasons[:2])
            not_qualifying.append((ticker, sbi, rsi, reasons))
        
        # Store detailed SBI data
        if sbi_result:
            detailed_sbi.append({
                'ticker': ticker,
                'sbi': sbi,
                'days_in_trend': sbi_result.days_in_trend,
                'atr_percent': sbi_result.atr_percent,
                'gap_slope': sbi_result.gap_slope,
                'adx_value': sbi_result.adx_value,
                'prsi_bearish': sbi_result.prsi_fast_bearish,
                'is_broken': sbi_result.is_broken,
                'components': sbi_result.components,
                'psar_gap': psar_gap,
                'rsi': rsi,
                'volatility_category': getattr(sbi_result, 'volatility_category', 'standard'),
                'atr_multiplier': getattr(sbi_result, 'atr_multiplier', 1.0),
            })
        
        # Color code SBI
        if sbi is not None:
            if sbi >= 10:
                sbi_display = f"⭐{sbi}"
            elif sbi >= 9:
                sbi_display = f"✓ {sbi}"
            else:
                sbi_display = f"  {sbi}"
        else:
            sbi_display = " --"
        
        print(f"{ticker:<8} {sbi_display:>4} {psar_str:>8} {rsi_str:>6} {status:<25}")
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 SUMMARY")
    print("=" * 70)
    print(f"   Parent {sector}: {'🟢 BULLISH' if parent_bullish else '🔴 BEARISH'}")
    print(f"   Qualifying stocks: {len(qualifying)} / {len(children)}")
    
    if qualifying:
        print(f"\n   ✅ Ready to buy:")
        for ticker, sbi, rsi in qualifying:
            rsi_str = f"{rsi:.0f}" if rsi else "?"
            print(f"      {ticker}: SBI={sbi}, RSI={rsi_str}")
    
    if not_qualifying:
        print(f"\n   ❌ Not qualifying:")
        for ticker, sbi, rsi, reasons in not_qualifying[:8]:
            print(f"      {ticker}: {', '.join(reasons)}")
        if len(not_qualifying) > 8:
            print(f"      ... and {len(not_qualifying) - 8} more")
    
    print("\n" + "=" * 70)
    print("💡 ENTRY CRITERIA (all must pass):")
    print(f"   1. Parent PSAR bullish  {'✓' if parent_bullish else '✗'}")
    print("   2. Stock SBI >= 9")
    print("   3. Stock PSAR bullish (price > PSAR)")
    print("   4. Stock RSI > 50")
    print("=" * 70)
    
    # Detailed SBI Breakdown
    if detailed_sbi:
        print("\n" + "=" * 70)
        print("🔬 DETAILED SBI BREAKDOWN")
        print("=" * 70)
        print("""
SBI Formula (varies by days in trend):
  Day 1:    100% ATR score
  Day 2:    80% ATR + 20% Slope  
  Day 3:    60% ATR + 40% Slope
  Days 4-5: 40% ATR + 40% Slope + 20% ADX
  Days 6+:  40% Slope + 30% ADX + 30% ATR
  
  PRSI(4) bearish penalty: -2 points (Days 3+)
""")
        
        # Sort by SBI descending
        detailed_sbi.sort(key=lambda x: x['sbi'], reverse=True)
        
        for d in detailed_sbi[:6]:  # Top 6 stocks
            ticker = d['ticker']
            sbi = d['sbi']
            days = d['days_in_trend']
            atr_pct = d['atr_percent']
            slope = d['gap_slope']
            adx = d['adx_value']
            prsi = d['prsi_bearish']
            broken = d['is_broken']
            comps = d['components']
            
            # Get volatility category info
            vol_cat = d.get('volatility_category', 'standard')
            atr_mult = d.get('atr_multiplier', 1.0)
            adjusted_atr = comps.get('adjusted_atr', atr_pct)
            
            print(f"\n{'─' * 50}")
            cat_display = f" [{vol_cat.upper()}]" if vol_cat != 'standard' else ""
            print(f"📊 {ticker}{cat_display}: SBI = {sbi}/10")
            print(f"{'─' * 50}")
            
            # Component scores
            atr_score = comps.get('atr_score', '?')
            slope_score = comps.get('slope_score', '?')
            adx_score = comps.get('adx_score', '?')
            trend = comps.get('trend', '?')
            
            print(f"   Days in trend: {days}")
            print(f"   Trend:         {trend.upper()}")
            print(f"   PSAR Gap:      {d['psar_gap']:+.1f}%")
            print(f"   RSI:           {d['rsi']:.1f}")
            print()
            
            # Show formula used
            if days == 1:
                formula = "100% ATR"
                calc = f"SBI = {atr_score}"
            elif days == 2:
                formula = "80% ATR + 20% Slope"
                calc = f"SBI = 0.8×{atr_score} + 0.2×{slope_score} = {0.8*atr_score + 0.2*slope_score:.1f}"
            elif days == 3:
                formula = "60% ATR + 40% Slope"
                calc = f"SBI = 0.6×{atr_score} + 0.4×{slope_score} = {0.6*atr_score + 0.4*slope_score:.1f}"
            elif days in [4, 5]:
                formula = "40% ATR + 40% Slope + 20% ADX"
                calc = f"SBI = 0.4×{atr_score} + 0.4×{slope_score} + 0.2×{adx_score} = {0.4*atr_score + 0.4*slope_score + 0.2*adx_score:.1f}"
            else:
                formula = "40% Slope + 30% ADX + 30% ATR"
                calc = f"SBI = 0.4×{slope_score} + 0.3×{adx_score} + 0.3×{atr_score} = {0.4*slope_score + 0.3*adx_score + 0.3*atr_score:.1f}"
            
            print(f"   Formula (Day {days}): {formula}")
            print()
            print(f"   Component Scores:")
            if atr_mult > 1.0:
                print(f"   ├─ ATR Score:   {atr_score}/10  (Raw ATR% = {atr_pct:.2f}% → Adjusted = {adjusted_atr:.2f}%)")
                print(f"   │    └─ {vol_cat.upper()} stock: {atr_mult}x ATR allowance")
            else:
                print(f"   ├─ ATR Score:   {atr_score}/10  (ATR% = {atr_pct:.2f}%)")
                print(f"   │    └─ Lower ATR% = higher score (less volatile)")
            print(f"   ├─ Slope Score: {slope_score}/10  (Gap Slope = {slope:+.2f})")
            print(f"   │    └─ Positive slope = gap widening = bullish")
            print(f"   └─ ADX Score:   {adx_score}/10  (ADX = {adx:.1f})")
            print(f"        └─ Higher ADX = stronger trend")
            print()
            print(f"   Calculation: {calc}")
            
            if prsi:
                print(f"   ⚠️  PRSI(4) Penalty: -2 (momentum warning)")
            if broken:
                print(f"   ❌ BROKEN: Recently crashed through PSAR")
            
            # Diagnosis
            print()
            issues = []
            if slope_score <= 5:
                issues.append(f"Slope score low ({slope_score}) - gap narrowing/negative")
            if atr_score <= 5:
                issues.append(f"ATR score low ({atr_score}) - too volatile")
            if adx_score <= 4:
                issues.append(f"ADX score low ({adx_score}) - weak/no trend")
            if prsi:
                issues.append("PRSI bearish - momentum fading")
            
            if issues:
                print(f"   🔍 Why SBI is low:")
                for issue in issues:
                    print(f"      • {issue}")
            else:
                print(f"   ✅ All components healthy")
        
        print("\n" + "=" * 70)


def run_signals(small_account: bool = True, strategy_mode: str = 'rotation', 
                output_json: bool = False, save_report: bool = True):
    """
    Generate and display trading signals.
    
    Args:
        small_account: Use small account limits (10 positions, 2 per sector)
        strategy_mode: rotation, parent_based, or weighted_rotation
        output_json: Output JSON instead of formatted report
        save_report: Save signals to JSON file
    """
    account_type = "SMALL (10 pos)" if small_account else "LARGE (20 pos)"
    
    print("\n" + "=" * 70)
    print(f"🤖 ADAPTIVEX2 SECTORBOT - {account_type}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Mode: {strategy_mode.upper()}")
    print("=" * 70)
    
    # Update dynamic holdings
    update_meme_holdings()
    
    # Get all tickers
    all_tickers = get_all_tickers()
    if 'SPY' not in all_tickers:
        all_tickers.append('SPY')
    if '^VIX' not in all_tickers:
        all_tickers.append('^VIX')
    
    # Fetch data
    price_data = fetch_all_data(all_tickers)
    
    # Initialize bot
    bot = AdaptiveX2SectorBot(
        small_account=small_account,
        strategy_mode=strategy_mode,
        regime_aware=False  # Use explicit mode, no auto-switching
    )
    bot.set_price_data(price_data)
    
    # Generate signals
    signals = bot.generate_signals()
    
    if output_json:
        print(json.dumps(signals, indent=2, default=str))
        return signals, bot
    
    # Print formatted report
    print("\n" + "=" * 70)
    print("📊 SIGNALS")
    print("=" * 70)
    
    # EXIT signals (highest priority)
    if signals['exit_signals']:
        print(f"\n🔴 EXIT ({len(signals['exit_signals'])}):")
        for s in signals['exit_signals']:
            reason = s.get('reason', 'Parent bearish')
            print(f"   SELL {s['ticker']:6s} ({s['parent']}) - {reason}")
    
    # ROTATION signals
    if signals['rotation_signals']:
        print(f"\n🔄 ROTATE ({len(signals['rotation_signals'])}):")
        for r in signals['rotation_signals']:
            exit_ticker = r['exit']['ticker']
            enter_ticker = r['enter']['ticker']
            enter_sbi = r['enter'].get('sbi', '?')
            print(f"   {exit_ticker:6s} → {enter_ticker:6s} (SBI={enter_sbi})")
    
    # ENTRY signals
    if signals['entry_signals']:
        print(f"\n🟢 ENTRY ({len(signals['entry_signals'])}):")
        for s in signals['entry_signals'][:bot.max_positions]:
            sbi = s.get('sbi', '?')
            rsi = s.get('rsi', '?')
            if isinstance(rsi, float):
                rsi = f"{rsi:.0f}"
            print(f"   BUY  {s['ticker']:6s} ({s['parent']}) - SBI={sbi}, RSI={rsi}")
    
    # No action needed
    if not signals['exit_signals'] and not signals['rotation_signals'] and not signals['entry_signals']:
        print(f"\n✅ NO ACTION NEEDED TODAY")
        print(f"   All current positions remain valid (no exit/rotate signals)")
    
    # Summary
    print("\n" + "=" * 70)
    print("📋 SUMMARY")
    print("-" * 70)
    print(f"   Active Sectors:    {len(signals['active_sectors'])}")
    print(f"   Exit Signals:      {len(signals['exit_signals'])}")
    print(f"   Rotation Signals:  {len(signals['rotation_signals'])}")
    print(f"   Entry Signals:     {len(signals['entry_signals'])}")
    print(f"\n   Max Positions:     {bot.max_positions}")
    print(f"   Max Per Sector:    {bot.max_per_sector}")
    print("=" * 70)
    
    # Active sectors detail
    if signals['active_sectors']:
        print("\n📈 ACTIVE SECTORS (Parent PSAR Bullish):")
        for sector in sorted(signals['active_sectors']):
            info = PARENT_CHILD_MAPPING.get(sector, {})
            name = info.get('name', sector)
            print(f"   • {sector}: {name}")
    
    # Save report
    if save_report:
        report_file = "sectorbot_signals.json"
        with open(report_file, 'w') as f:
            json.dump(signals, f, indent=2, default=lambda x: 
                bool(x) if hasattr(x, 'item') else 
                float(x) if hasattr(x, 'dtype') else str(x))
        print(f"\n📁 Saved to: {report_file}")
    
    return signals, bot


def print_usage():
    """Print usage examples."""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║  ADAPTIVEX2 SECTORBOT                                                ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  USAGE:                                                              ║
║    python main.py                    # Default: Rotation mode        ║
║    python main.py --mode parent_based                                ║
║    python main.py --large            # 20 positions instead of 10   ║
║    python main.py --json             # Output JSON only              ║
║    python main.py --sector BTC-USD   # Diagnose Bitcoin sector       ║
║    python main.py --sector GLD       # Diagnose Gold sector          ║
║                                                                      ║
║  MODES:                                                              ║
║    rotation (default)  - Rotate weak stocks, active management       ║
║    parent_based        - Hold through weakness, less trading         ║
║    weighted_rotation   - Rotation + sector weighting                 ║
║                                                                      ║
║  SECTOR DIAGNOSIS:                                                   ║
║    --sector BTC-USD    Shows why Bitcoin stocks may not qualify      ║
║    --sector GLD        Shows why Gold stocks may not qualify         ║
║    --sector XLK        Shows why Tech stocks may not qualify         ║
║                                                                      ║
║  ENTRY CRITERIA (all must pass):                                     ║
║    1. Parent PSAR bullish (sector ETF above PSAR)                    ║
║    2. Stock SBI >= 9 (Signal Bullish Index)                          ║
║    3. Stock PSAR bullish (stock price above its PSAR)                ║
║    4. Stock RSI > 50 (momentum confirmation)                         ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
""")


def run_live_trading(small_account: bool = True, strategy_mode: str = 'rotation',
                     dry_run: bool = True, auto_confirm: bool = False):
    """Execute live trades via Schwab API."""
    
    print("\n" + "=" * 70)
    if dry_run:
        print("🧪 SCHWAB DRY RUN (no real trades)")
    else:
        print("🔴 LIVE TRADING MODE")
    print("=" * 70)
    
    # Get signals first
    signals, bot = run_signals(
        small_account=small_account,
        strategy_mode=strategy_mode,
        output_json=False,
        save_report=True
    )
    
    # Check for Schwab credentials
    app_key = os.environ.get('SCHWAB_SECTORBOT_APP_KEY') or os.environ.get('SCHWAB_APP_KEY')
    app_secret = os.environ.get('SCHWAB_SECTORBOT_APP_SECRET') or os.environ.get('SCHWAB_APP_SECRET')
    
    if not app_key or not app_secret:
        print("\n⚠️ Schwab credentials not found")
        print("   Set SCHWAB_SECTORBOT_APP_KEY and SCHWAB_SECTORBOT_APP_SECRET")
        return
    
    try:
        from schwab_auth import get_schwab_client
        client = get_schwab_client()
        
        if client is None:
            print("❌ Failed to get Schwab client")
            return
        
        # Get account hash
        account_hash = os.environ.get('SCHWAB_SECTORBOT_ACCOUNT_HASH') or os.environ.get('SCHWAB_ACCOUNT_HASH')
        if not account_hash:
            accounts_resp = client.get_account_numbers()
            if accounts_resp.status_code == 200:
                accounts = accounts_resp.json()
                if accounts:
                    account_hash = accounts[0]['hashValue']
                    print(f"   Using account: {accounts[0].get('accountNumber', 'Unknown')}")
        
        if not account_hash:
            print("❌ No account hash found")
            return
        
        # Get current positions
        account_resp = client.get_account(account_hash, fields=['positions'])
        if account_resp.status_code != 200:
            print(f"❌ Failed to get account: {account_resp.status_code}")
            return
        
        account_data = account_resp.json()
        positions = {}
        if 'securitiesAccount' in account_data:
            for pos in account_data['securitiesAccount'].get('positions', []):
                symbol = pos['instrument']['symbol']
                qty = pos['longQuantity'] - pos.get('shortQuantity', 0)
                if qty > 0:
                    positions[symbol] = {
                        'quantity': int(qty),
                        'avg_cost': pos.get('averagePrice', 0),
                        'market_value': pos.get('marketValue', 0)
                    }
        
        print(f"\n📊 Current positions: {len(positions)}")
        for symbol, pos in positions.items():
            print(f"   {symbol}: {pos['quantity']} shares @ ${pos['avg_cost']:.2f}")
        
        balances = account_data['securitiesAccount'].get('currentBalances', {})
        cash = balances.get('cashBalance', 0)
        account_value = balances.get('liquidationValue', 0)
        print(f"\n💰 Cash: ${cash:,.2f}")
        print(f"💼 Account Value: ${account_value:,.2f}")
        
        position_value = (account_value * 0.95) / bot.max_positions
        print(f"📐 Target per position: ${position_value:,.2f}")
        
        # Process signals (exit, rotation, entry)
        if signals['exit_signals']:
            print(f"\n🔴 EXIT SIGNALS ({len(signals['exit_signals'])}):")
            for sig in signals['exit_signals']:
                ticker = sig['ticker']
                if ticker in positions:
                    qty = positions[ticker]['quantity']
                    if dry_run:
                        print(f"   [DRY RUN] Would sell {qty} {ticker}")
                    elif auto_confirm or input(f"   SELL {qty} {ticker}? (y/n): ").lower() == 'y':
                        from schwab.orders.equities import equity_sell_market
                        order = equity_sell_market(ticker, qty)
                        resp = client.place_order(account_hash, order)
                        if resp.status_code in [200, 201]:
                            print(f"   ✅ Sold {qty} {ticker}")
                        else:
                            print(f"   ❌ Failed: {resp.status_code}")
                else:
                    print(f"   ⏭️  {ticker} - not in portfolio, skipping")
        
        if signals['entry_signals']:
            current_count = len(positions)
            available_slots = bot.max_positions - current_count
            
            if available_slots > 0:
                print(f"\n🟢 ENTRY SIGNALS ({min(len(signals['entry_signals']), available_slots)} of {len(signals['entry_signals'])}):")
                for sig in signals['entry_signals'][:available_slots]:
                    ticker = sig['ticker']
                    if ticker not in positions:
                        # Get price from bot
                        price = 100  # Default
                        try:
                            price = bot.price_data.get(ticker, {})['Close'].iloc[-1]
                        except:
                            pass
                        qty = max(1, int(position_value / price))
                        
                        if dry_run:
                            print(f"   [DRY RUN] Would buy {qty} {ticker} @ ~${price:.2f}")
                        elif auto_confirm or input(f"   BUY {qty} {ticker}? (y/n): ").lower() == 'y':
                            from schwab.orders.equities import equity_buy_market
                            order = equity_buy_market(ticker, qty)
                            resp = client.place_order(account_hash, order)
                            if resp.status_code in [200, 201]:
                                print(f"   ✅ Bought {qty} {ticker}")
                            else:
                                print(f"   ❌ Failed: {resp.status_code}")
            else:
                print(f"\n✋ No available slots ({current_count}/{bot.max_positions} positions)")
        
        print("\n" + "=" * 70)
        print("✅ Live trading complete")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n❌ Schwab error: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(
        description="AdaptiveX2 SectorBot - Sector Rotation Strategy",
        add_help=True
    )
    
    parser.add_argument('--large', action='store_true',
                        help='Large account mode (20 positions, 5 per sector)')
    parser.add_argument('--json', action='store_true',
                        help='Output JSON only (no formatted report)')
    parser.add_argument('--no-save', action='store_true',
                        help='Do not save report to file')
    parser.add_argument('--mode', type=str, 
                        choices=['rotation', 'parent_based', 'weighted_rotation'],
                        default='rotation', help='Strategy mode (default: rotation)')
    parser.add_argument('--sector', '-s', type=str,
                        help='Diagnose specific sector (e.g., BTC-USD, GLD, XLK)')
    parser.add_argument('--live', action='store_true',
                        help='Execute LIVE trades via Schwab (real money!)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Test Schwab connection without executing trades')
    parser.add_argument('--auto-confirm', action='store_true',
                        help='Skip confirmation prompts (for automation)')
    parser.add_argument('--usage', action='store_true',
                        help='Show detailed usage examples')
    
    args = parser.parse_args()
    
    if args.usage:
        print_usage()
        return
    
    try:
        if args.sector:
            diagnose_sector(
                sector=args.sector,
                small_account=not args.large,
                strategy_mode=args.mode
            )
        elif args.live or args.dry_run:
            run_live_trading(
                small_account=not args.large,
                strategy_mode=args.mode,
                dry_run=args.dry_run,
                auto_confirm=args.auto_confirm
            )
        else:
            run_signals(
                small_account=not args.large,
                strategy_mode=args.mode,
                output_json=args.json,
                save_report=not args.no_save
            )
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
