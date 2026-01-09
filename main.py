#!/usr/bin/env python3
"""
AdaptiveX2 SectorBot - Main Entry Point
=======================================

Usage:
    python main.py --signal-only              # Just show signals (default small account)
    python main.py --signal-only --large      # Large account (20 positions)
    python main.py --live                     # Live trading with Schwab (dry run)
    python main.py --live --execute           # REAL trades!
    python main.py --json                     # Output JSON only
    python main.py --report                   # Generate Patreon JSX report

Strategy (Baseline - no boosts):
1. Parent PSAR bullish → Sector active
2. Stock entry: PSAR bullish + RSI > 50 + SBI >= 9
3. Stock exit/rotate: PSAR bearish OR RSI < 40
4. Small account: 10 positions max, 2-3 per sector
5. Large account: 20 positions max, 5 per sector

Performance (2022-2024):
- 2022: +45% (vs SPY -19%, QQQ -33%)
- 2023: +70% (vs SPY +27%, QQQ +56%)
- 2024: +114% (vs SPY +26%, QQQ +28%)
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
from typing import Dict, List, Optional

import warnings
warnings.filterwarnings('ignore', category=FutureWarning)

import yfinance as yf

from strategy import AdaptiveX2SectorBot
from config import PARENT_CHILD_MAPPING, get_all_tickers, DEFAULT_CONFIG, update_meme_holdings


# Rate limiting for API calls
API_DELAY_SECONDS = 0.5  # Delay between ticker fetches to avoid rate limiting


def fetch_all_data(tickers: list, period: str = "6mo", use_delay: bool = True) -> dict:
    """
    Fetch historical data for all tickers.
    Uses yfinance with rate limiting to avoid 429 errors.
    """
    print(f"\n📥 Fetching data for {len(tickers)} tickers...")
    print("-" * 50)
    
    data = {}
    success = 0
    failed = []
    
    # Try batch download first (faster but may hit rate limits)
    try:
        batch_data = yf.download(
            tickers=tickers,
            period=period,
            group_by='ticker',
            auto_adjust=True,
            threads=True,
            progress=True,
        )
        
        # Process batch results
        for ticker in tickers:
            try:
                if len(tickers) == 1:
                    df = batch_data
                else:
                    df = batch_data[ticker].dropna()
                
                if len(df) >= 20:
                    data[ticker] = df
                    success += 1
                else:
                    failed.append(ticker)
            except:
                failed.append(ticker)
                
    except Exception as e:
        print(f"⚠️ Batch download failed, falling back to individual: {e}")
        
        # Fall back to individual downloads with rate limiting
        for i, ticker in enumerate(tickers):
            try:
                if use_delay and i > 0:
                    time.sleep(API_DELAY_SECONDS)
                
                stock = yf.Ticker(ticker)
                df = stock.history(period=period)
                if len(df) >= 20:
                    data[ticker] = df
                    success += 1
                else:
                    failed.append(ticker)
            except Exception as e:
                failed.append(ticker)
            
            # Progress every 20 tickers
            if (i + 1) % 20 == 0:
                print(f"  Progress: {i+1}/{len(tickers)} ({success} loaded)")
    
    print(f"\n✅ Loaded {success} tickers")
    if failed:
        print(f"⚠️  Failed: {len(failed)} tickers")
        if len(failed) <= 10:
            print(f"   {', '.join(failed)}")
    
    # Generate synthetic ETF data for MEME, TCAI, crypto ETFs
    try:
        from synthetic_etf import fill_missing_etf_data, fill_synthetic_etfs_from_holdings
        data = fill_missing_etf_data(data)
        data = fill_synthetic_etfs_from_holdings(data)
    except ImportError as e:
        print(f"   ⚠️ Synthetic ETF module not available: {e}")
    except Exception as e:
        print(f"   ⚠️ Synthetic ETF generation error: {e}")
    
    return data


def run_signal_only(small_account: bool = True, output_json: bool = False, save_report: bool = True,
                    strategy_mode: str = None, regime_aware: bool = True, save_positions: bool = False):
    """
    Calculate and display strategy signals without trading.
    
    Args:
        small_account: Use small account limits (10 positions)
        output_json: Output JSON instead of formatted report
        save_report: Save signals to JSON file
        strategy_mode: Force specific mode (parent_based, rotation, weighted_rotation)
        regime_aware: Auto-detect market regime and switch modes
        save_positions: If True, save entry signals as tracked positions
    """
    account_type = "SMALL (10 pos)" if small_account else "LARGE (20 pos)"
    mode_str = f"Mode: {strategy_mode or 'REGIME-AWARE'}"
    
    print("\n" + "=" * 70)
    print(f"🤖 ADAPTIVEX2 SECTORBOT - {account_type}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   {mode_str}")
    print("=" * 70)
    
    # Update dynamic holdings (meme stocks, etc.)
    update_meme_holdings()
    
    # Get all tickers
    all_tickers = get_all_tickers()
    
    # Add SPY and VIX for regime detection if not already present
    if 'SPY' not in all_tickers:
        all_tickers.append('SPY')
    if '^VIX' not in all_tickers:
        all_tickers.append('^VIX')
    
    # Fetch data with rate limiting
    price_data = fetch_all_data(all_tickers, use_delay=True)
    
    # Initialize bot with strategy mode
    bot = AdaptiveX2SectorBot(
        small_account=small_account,
        strategy_mode=strategy_mode,
        regime_aware=regime_aware
    )
    bot.set_price_data(price_data)
    
    # Generate signals
    signals = bot.generate_signals()
    
    if output_json:
        print(json.dumps(signals, indent=2, default=str))
    else:
        # Print formatted report
        bot.print_report(signals)
        
        # Show current positions clearly
        print("\n" + "=" * 70)
        print("📋 POSITION TRACKING")
        print("-" * 70)
        
        if signals['current_positions']:
            print(f"   🔒 CURRENT POSITIONS ({len(signals['current_positions'])}):")
            for ticker in signals['current_positions']:
                print(f"      • {ticker}")
            print(f"\n   ⚠️  These are HELD positions - only exit on EXIT signal!")
        else:
            print("   📭 No current positions tracked")
            print("   💡 To track positions, update sectorbot_state.json after buying")
        
        # Action items
        print("\n" + "-" * 70)
        print("🎯 ACTION ITEMS FOR TODAY:")
        print("-" * 70)
        
        if signals['exit_signals']:
            print(f"\n   🔴 SELL ({len(signals['exit_signals'])}):")
            for s in signals['exit_signals']:
                print(f"      SELL {s['ticker']} - {s['reason']}")
        
        if signals['rotation_signals']:
            print(f"\n   🔄 ROTATE ({len(signals['rotation_signals'])}):")
            for r in signals['rotation_signals']:
                print(f"      SELL {r['exit']['ticker']} → BUY {r['enter']['ticker']}")
        
        # Only show entry signals if we have capacity
        current_count = len(signals['current_positions'])
        available_slots = bot.max_positions - current_count
        
        if available_slots > 0 and signals['entry_signals']:
            print(f"\n   🟢 NEW ENTRIES (you have {available_slots} slots):")
            for s in signals['entry_signals'][:available_slots]:
                print(f"      BUY {s['ticker']} ({s['parent']}) - SBI={s['sbi']}")
            if len(signals['entry_signals']) > available_slots:
                print(f"      ... and {len(signals['entry_signals']) - available_slots} more (no slots)")
        elif available_slots == 0:
            print(f"\n   ✋ FULL - No new entries (holding {current_count} positions)")
        else:
            print(f"\n   📭 No entry signals today")
        
        if not signals['exit_signals'] and not signals['rotation_signals'] and available_slots == 0:
            print(f"\n   ✅ HOLD ALL - No action needed today")
        
        # Summary
        print("\n" + "=" * 70)
        print("📊 SUMMARY")
        print("-" * 70)
        print(f"   Active Sectors: {len(signals['active_sectors'])}")
        print(f"   Entry Signals: {len(signals['entry_signals'])}")
        print(f"   Rotation Signals: {len(signals['rotation_signals'])}")
        print(f"   Exit Signals: {len(signals['exit_signals'])}")
        print(f"   Hold Positions: {len(signals['hold_positions'])}")
        print(f"   Target Positions: {len(signals['target_allocation'])}")
        
        if small_account:
            print(f"\n   📱 SMALL ACCOUNT MODE")
            print(f"      Max Positions: {bot.max_positions}")
            print(f"      Max Per Sector: {bot.max_per_sector}")
        else:
            print(f"\n   💼 LARGE ACCOUNT MODE")
            print(f"      Max Positions: {bot.max_positions}")
            print(f"      Max Per Sector: {bot.max_per_sector}")
        
        print("=" * 70)
        
        # Save report
        if save_report:
            report_file = f"sectorbot_allocation.json"
            with open(report_file, 'w') as f:
                json.dump(signals, f, indent=2, default=lambda x: 
                    bool(x) if hasattr(x, 'item') else 
                    float(x) if hasattr(x, 'dtype') else str(x))
            print(f"\n📁 Report saved to: {report_file}")
    
    # Auto-save entry signals as positions if requested
    if save_positions and signals['entry_signals']:
        print("\n" + "-" * 70)
        print("💾 SAVING ENTRY SIGNALS AS POSITIONS")
        print("-" * 70)
        
        for sig in signals['entry_signals']:
            ticker = sig['ticker']
            if ticker not in bot.positions:
                entry_price = bot.get_price(ticker) or 0
                entry_sbi = sig.get('sbi', 10)
                bot.add_position(ticker, sig['parent'], sig['category'], entry_price, entry_sbi=entry_sbi)
        
        print(f"✅ Saved {len(bot.positions)} positions to sectorbot_state.json")
    
    return signals, bot


def run_position_update(small_account: bool = True, auto_confirm: bool = False,
                        strategy_mode: str = None, regime_aware: bool = True):
    """
    Run signal generation and update position tracking.
    
    This mode:
    1. Shows current positions from sectorbot_state.json
    2. Generates signals
    3. Asks you to confirm trades you made
    4. Updates sectorbot_state.json automatically
    
    Use this after you manually trade to keep the system in sync!
    """
    from config import PARENT_CHILD_MAPPING
    
    account_type = "SMALL (10 pos)" if small_account else "LARGE (20 pos)"
    
    print("\n" + "=" * 70)
    print(f"🔄 SECTORBOT POSITION UPDATE - {account_type}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
    price_data = fetch_all_data(all_tickers, use_delay=True)
    
    # Initialize bot
    bot = AdaptiveX2SectorBot(
        small_account=small_account,
        strategy_mode=strategy_mode,
        regime_aware=regime_aware
    )
    bot.set_price_data(price_data)
    
    # Show current positions BEFORE generating signals
    print("\n" + "=" * 70)
    print("📋 CURRENT TRACKED POSITIONS")
    print("-" * 70)
    if bot.positions:
        for ticker, pos in bot.positions.items():
            current_price = bot.get_price(ticker) or 0
            entry_price = pos.entry_price or 0
            pnl = ((current_price / entry_price) - 1) * 100 if entry_price > 0 else 0
            print(f"   {ticker}: {pos.parent} | Entry: ${entry_price:.2f} | Now: ${current_price:.2f} | P/L: {pnl:+.1f}%")
    else:
        print("   📭 No positions tracked yet")
        print("   💡 Run with --init to set up initial positions")
    print("=" * 70)
    
    # Generate signals
    signals = bot.generate_signals()
    bot.print_report(signals)
    
    # Execute signals with confirmation
    print("\n" + "=" * 70)
    print("🎯 EXECUTE TRADES")
    print("-" * 70)
    
    if not signals['exit_signals'] and not signals['rotation_signals']:
        print("   ✅ No exits or rotations needed today")
        
        # Check for new entries if we have slots
        available = bot.max_positions - len(bot.positions)
        if available > 0 and signals['entry_signals']:
            print(f"\n   📈 You have {available} empty slots. New entry opportunities:")
            for sig in signals['entry_signals'][:available]:
                print(f"      • {sig['ticker']} ({sig['parent']}) - SBI={sig['sbi']}")
            
            if not auto_confirm:
                response = input("\n   ❓ Did you buy any of these? (enter tickers separated by comma, or 'n'): ")
                if response.lower() != 'n' and response.strip():
                    tickers = [t.strip().upper() for t in response.split(',')]
                    for ticker in tickers:
                        # Find the signal for this ticker
                        for sig in signals['entry_signals']:
                            if sig['ticker'].upper() == ticker:
                                entry_price = bot.get_price(ticker) or 0
                                bot.add_position(ticker, sig['parent'], sig['category'], entry_price)
                                break
    else:
        # Process exits and rotations
        bot.execute_signals(signals, confirm=not auto_confirm)
    
    print("\n" + "=" * 70)
    print(f"📊 FINAL POSITION COUNT: {len(bot.positions)}/{bot.max_positions}")
    print("=" * 70)
    
    return signals, bot


def init_positions(small_account: bool = True):
    """
    Interactive setup of initial positions.
    """
    from config import PARENT_CHILD_MAPPING
    
    print("\n" + "=" * 70)
    print("🚀 SECTORBOT INITIAL POSITION SETUP")
    print("=" * 70)
    print("\nEnter your current positions (or 'done' to finish):")
    print("Format: TICKER PRICE  (e.g., 'AAPL 185.50')")
    print("-" * 70)
    
    bot = AdaptiveX2SectorBot(small_account=small_account)
    
    while True:
        entry = input("\n> ").strip()
        if entry.lower() == 'done':
            break
        
        parts = entry.split()
        if len(parts) != 2:
            print("   ⚠️ Format: TICKER PRICE")
            continue
        
        ticker = parts[0].upper()
        try:
            price = float(parts[1])
        except:
            print("   ⚠️ Invalid price")
            continue
        
        # Find parent for this ticker
        parent = None
        category = ''
        for p, info in PARENT_CHILD_MAPPING.items():
            if ticker in info.get('stocks', []):
                parent = p
                category = info.get('category', '')
                break
        
        if not parent:
            print(f"   ⚠️ {ticker} not found in any sector")
            # Ask if they want to add anyway
            response = input(f"   Add anyway? Enter parent ticker (e.g., XLK) or 'n': ")
            if response.lower() == 'n':
                continue
            parent = response.upper()
            category = 'CUSTOM'
        
        bot.add_position(ticker, parent, category, price)
    
    print("\n" + "=" * 70)
    print(f"✅ Setup complete! {len(bot.positions)} positions saved")
    print("=" * 70)


def run_live_trading(small_account: bool = True, dry_run: bool = True, auto_confirm: bool = False):
    """
    Run live trading with Schwab API.
    Uses separate credentials for SectorBot account.
    """
    account_type = "SMALL (10 pos)" if small_account else "LARGE (20 pos)"
    mode = "DRY RUN" if dry_run else "LIVE EXECUTION"
    
    print("\n" + "=" * 70)
    print(f"🤖 ADAPTIVEX2 SECTORBOT - {account_type} - {mode}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Check for Schwab credentials (SectorBot uses separate account)
    app_key = os.environ.get('SCHWAB_SECTORBOT_APP_KEY') or os.environ.get('SCHWAB_APP_KEY')
    app_secret = os.environ.get('SCHWAB_SECTORBOT_APP_SECRET') or os.environ.get('SCHWAB_APP_SECRET')
    account_hash = os.environ.get('SCHWAB_SECTORBOT_ACCOUNT_HASH') or os.environ.get('SCHWAB_ACCOUNT_HASH')
    
    if not all([app_key, app_secret]):
        print("\n❌ ERROR: Schwab API credentials not found!")
        print("   Set environment variables:")
        print("   - SCHWAB_SECTORBOT_APP_KEY (or SCHWAB_APP_KEY)")
        print("   - SCHWAB_SECTORBOT_APP_SECRET (or SCHWAB_APP_SECRET)")
        print("   - SCHWAB_SECTORBOT_ACCOUNT_HASH (optional, for specific account)")
        sys.exit(1)
    
    # Confirmation for live trades
    if not dry_run and not auto_confirm:
        print("\n⚠️  WARNING: LIVE TRADING MODE - REAL ORDERS WILL BE PLACED")
        confirm = input("Type 'CONFIRM' to proceed: ")
        if confirm != "CONFIRM":
            print("Cancelled")
            sys.exit(0)
    elif not dry_run:
        print("\n⚠️  LIVE TRADING MODE (auto-confirmed)")
    
    # Update holdings and fetch data
    update_meme_holdings()
    all_tickers = get_all_tickers()
    price_data = fetch_all_data(all_tickers, use_delay=True)
    
    # Initialize bot
    bot = AdaptiveX2SectorBot(small_account=small_account)
    bot.set_price_data(price_data)
    
    # Generate signals
    signals = bot.generate_signals()
    
    # Print report
    bot.print_report(signals)
    
    # Get target allocation
    target_allocation = signals.get('target_allocation', [])
    
    if not target_allocation:
        print("\n📭 No positions to trade - all sectors inactive or no valid entries")
        return signals
    
    print("\n" + "=" * 70)
    print("📋 TARGET ALLOCATION")
    print("-" * 70)
    
    for pos in target_allocation:
        ticker = pos.get('ticker', 'N/A')
        sector = pos.get('sector', 'N/A')
        weight = pos.get('weight', 0) * 100
        sbi = pos.get('sbi', 'N/A')
        print(f"   {ticker:<8} {sector:<12} {weight:>5.1f}%  SBI={sbi}")
    
    print("-" * 70)
    print(f"   Total positions: {len(target_allocation)}")
    
    # Execute trades via Schwab
    try:
        from sectorbot_executor import SectorBotExecutor
        
        executor = SectorBotExecutor(
            app_key=app_key,
            app_secret=app_secret,
            account_hash=account_hash,
            dry_run=dry_run
        )
        
        # Get current positions
        current_positions = executor.get_positions()
        
        # Calculate trades needed
        trades = executor.calculate_trades(
            current_positions=current_positions,
            target_allocation=target_allocation
        )
        
        if trades:
            print("\n📈 TRADES TO EXECUTE:")
            print("-" * 70)
            for trade in trades:
                action = trade.get('action', 'BUY')
                ticker = trade.get('ticker', 'N/A')
                shares = trade.get('shares', 0)
                print(f"   {action:<6} {shares:>6} shares of {ticker}")
            
            # Execute
            if not dry_run:
                results = executor.execute_trades(trades)
                print("\n✅ EXECUTION RESULTS:")
                for result in results:
                    print(f"   {result}")
            else:
                print("\n🔍 DRY RUN - No trades executed")
        else:
            print("\n✅ Portfolio already matches target allocation")
            
    except ImportError:
        print("\n⚠️ SectorBot executor not available")
        print("   Create sectorbot_executor.py with Schwab integration")
    except Exception as e:
        print(f"\n❌ Execution error: {e}")
        raise
    
    return signals


def generate_patreon_report(signals: dict, output_path: str = "sectorbot_report.jsx"):
    """
    Generate a JSX report for Patreon updates.
    """
    from datetime import datetime
    
    # Build report data
    report_data = {
        "generated_at": datetime.now().isoformat(),
        "active_sectors": signals.get('active_sectors', []),
        "inactive_sectors": signals.get('inactive_sectors', []),
        "entry_signals": signals.get('entry_signals', []),
        "rotation_signals": signals.get('rotation_signals', []),
        "exit_signals": signals.get('exit_signals', []),
        "hold_positions": signals.get('hold_positions', []),
        "target_allocation": signals.get('target_allocation', []),
    }
    
    # Create JSX component
    jsx_content = f'''import React from 'react';

// SectorBot Report - Generated {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
// DO NOT EDIT - This file is auto-generated

const SectorBotReport = () => {{
  const reportData = {json.dumps(report_data, indent=2, default=str)};
  
  const formatDate = (dateStr) => {{
    return new Date(dateStr).toLocaleDateString('en-US', {{
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    }});
  }};

  return (
    <div className="bg-gray-900 text-white p-6 rounded-lg max-w-4xl mx-auto">
      <div className="border-b border-gray-700 pb-4 mb-6">
        <h1 className="text-2xl font-bold text-yellow-400">🤖 AdaptiveX2 SectorBot</h1>
        <p className="text-gray-400 text-sm">Generated: {{formatDate(reportData.generated_at)}}</p>
      </div>

      {{/* Summary Stats */}}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-gray-800 p-4 rounded">
          <div className="text-2xl font-bold text-green-400">{{reportData.active_sectors.length}}</div>
          <div className="text-gray-400 text-sm">Active Sectors</div>
        </div>
        <div className="bg-gray-800 p-4 rounded">
          <div className="text-2xl font-bold text-blue-400">{{reportData.entry_signals.length}}</div>
          <div className="text-gray-400 text-sm">Entry Signals</div>
        </div>
        <div className="bg-gray-800 p-4 rounded">
          <div className="text-2xl font-bold text-yellow-400">{{reportData.rotation_signals.length}}</div>
          <div className="text-gray-400 text-sm">Rotations</div>
        </div>
        <div className="bg-gray-800 p-4 rounded">
          <div className="text-2xl font-bold text-red-400">{{reportData.exit_signals.length}}</div>
          <div className="text-gray-400 text-sm">Exit Signals</div>
        </div>
      </div>

      {{/* Target Allocation */}}
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-yellow-400 mb-3">📊 Target Allocation</h2>
        <div className="bg-gray-800 rounded overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-700">
              <tr>
                <th className="text-left p-3">Ticker</th>
                <th className="text-left p-3">Sector</th>
                <th className="text-right p-3">Weight</th>
                <th className="text-right p-3">SBI</th>
              </tr>
            </thead>
            <tbody>
              {{reportData.target_allocation.map((pos, idx) => (
                <tr key={{idx}} className="border-t border-gray-700 hover:bg-gray-750">
                  <td className="p-3 font-mono font-bold text-green-400">{{pos.ticker}}</td>
                  <td className="p-3 text-gray-300">{{pos.sector}}</td>
                  <td className="p-3 text-right">{{(pos.weight * 100).toFixed(1)}}%</td>
                  <td className="p-3 text-right">
                    <span className={{`px-2 py-1 rounded ${{pos.sbi === 10 ? 'bg-green-600' : 'bg-yellow-600'}}`}}>
                      {{pos.sbi}}
                    </span>
                  </td>
                </tr>
              ))}}
            </tbody>
          </table>
        </div>
      </div>

      {{/* Active Sectors */}}
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-green-400 mb-3">✅ Active Sectors</h2>
        <div className="flex flex-wrap gap-2">
          {{reportData.active_sectors.map((sector, idx) => (
            <span key={{idx}} className="bg-green-900 text-green-300 px-3 py-1 rounded">
              {{sector.parent}} - {{sector.description}}
            </span>
          ))}}
        </div>
      </div>

      {{/* Entry Signals */}}
      {{reportData.entry_signals.length > 0 && (
        <div className="mb-6">
          <h2 className="text-xl font-semibold text-blue-400 mb-3">🚀 Entry Signals</h2>
          <div className="grid gap-2">
            {{reportData.entry_signals.map((sig, idx) => (
              <div key={{idx}} className="bg-blue-900/30 border border-blue-700 p-3 rounded">
                <span className="font-bold text-blue-300">{{sig.ticker}}</span>
                <span className="text-gray-400 mx-2">|</span>
                <span className="text-gray-300">{{sig.sector}}</span>
                <span className="text-gray-400 mx-2">|</span>
                <span className="text-green-400">SBI={{sig.sbi}}</span>
              </div>
            ))}}
          </div>
        </div>
      )}}

      {{/* Rotation Signals */}}
      {{reportData.rotation_signals.length > 0 && (
        <div className="mb-6">
          <h2 className="text-xl font-semibold text-yellow-400 mb-3">🔄 Rotation Signals</h2>
          <div className="grid gap-2">
            {{reportData.rotation_signals.map((sig, idx) => (
              <div key={{idx}} className="bg-yellow-900/30 border border-yellow-700 p-3 rounded">
                <span className="text-red-400">{{sig.from_ticker}}</span>
                <span className="text-gray-400 mx-2">→</span>
                <span className="text-green-400">{{sig.to_ticker}}</span>
                <span className="text-gray-400 mx-2">|</span>
                <span className="text-gray-300">{{sig.sector}}</span>
              </div>
            ))}}
          </div>
        </div>
      )}}

      {{/* Exit Signals */}}
      {{reportData.exit_signals.length > 0 && (
        <div className="mb-6">
          <h2 className="text-xl font-semibold text-red-400 mb-3">🚨 Exit Signals</h2>
          <div className="grid gap-2">
            {{reportData.exit_signals.map((sig, idx) => (
              <div key={{idx}} className="bg-red-900/30 border border-red-700 p-3 rounded">
                <span className="font-bold text-red-300">{{sig.ticker}}</span>
                <span className="text-gray-400 mx-2">|</span>
                <span className="text-gray-300">{{sig.reason}}</span>
              </div>
            ))}}
          </div>
        </div>
      )}}

      {{/* Disclaimer */}}
      <div className="mt-8 p-4 bg-gray-800 rounded border border-gray-700">
        <p className="text-gray-400 text-xs">
          ⚠️ DISCLAIMER: This is NOT financial advice. For educational purposes only.
          Past performance does not guarantee future results. You are responsible for your own decisions.
        </p>
      </div>
    </div>
  );
}};

export default SectorBotReport;
'''
    
    with open(output_path, 'w') as f:
        f.write(jsx_content)
    
    print(f"\n📄 JSX Report generated: {output_path}")
    return output_path


def print_usage():
    """Print usage message"""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                    ADAPTIVEX2 SECTORBOT                              ║
╠══════════════════════════════════════════════════════════════════════╣
║                                                                      ║
║  MODES:                                                              ║
║    --signal-only    Calculate signals only (no trading) [DEFAULT]    ║
║    --init           First-time setup: enter your positions           ║
║    --update         Update positions after you trade                 ║
║    --live           Live trading with Schwab                         ║
║    --report         Generate Patreon JSX report                      ║
║                                                                      ║
║  ACCOUNT SIZE:                                                       ║
║    (default)        Small account: 10 positions, 2-3 per sector      ║
║    --large          Large account: 20 positions, 5 per sector        ║
║                                                                      ║
║  STRATEGY MODE:                                                      ║
║    --mode auto      Auto-detect regime (default)                     ║
║    --mode parent_based   Hold through stock weakness                 ║
║    --mode rotation       Rotate weak stocks within sector            ║
║    --mode weighted_rotation  Rotate + weight top sectors             ║
║                                                                      ║
║  OPTIONS:                                                            ║
║    --json           Output JSON only                                 ║
║    --execute        Actually execute live trades (with --live)       ║
║    --auto-confirm   Skip confirmation prompt (for CI/CD)             ║
║    --no-save        Don't save report file                           ║
║                                                                      ║
║  WORKFLOW:                                                           ║
║    1. python main.py --save-positions   # First time: save positions ║
║    2. python main.py                    # Daily: check signals       ║
║    3. python main.py --update           # After trading: sync        ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
""")


def main():
    parser = argparse.ArgumentParser(
        description="AdaptiveX2 SectorBot - Sector Rotation Strategy",
        add_help=True
    )
    
    # Mode selection
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        '--signal-only',
        action='store_true',
        default=True,
        help='Calculate signals only, no trading (default)'
    )
    mode_group.add_argument(
        '--live',
        action='store_true',
        help='Live trading with Schwab'
    )
    mode_group.add_argument(
        '--report',
        action='store_true',
        help='Generate Patreon JSX report'
    )
    
    # Account size
    parser.add_argument(
        '--large',
        action='store_true',
        help='Large account mode: 20 positions, 5 per sector (default: small account)'
    )
    
    # Output options
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output JSON only (no formatted report)'
    )
    parser.add_argument(
        '--no-save',
        action='store_true',
        help='Do not save report to file'
    )
    parser.add_argument(
        '--save-positions',
        action='store_true',
        help='Save entry signals as tracked positions (auto-init)'
    )
    
    # Strategy mode options
    parser.add_argument(
        '--mode',
        type=str,
        choices=['parent_based', 'rotation', 'weighted_rotation', 'auto'],
        default='auto',
        help='Strategy mode: parent_based (hold through weakness), rotation (rotate weak stocks), weighted_rotation (rotate + weight by sector strength), auto (detect regime)'
    )
    parser.add_argument(
        '--no-regime',
        action='store_true',
        help='Disable regime-aware mode switching (use --mode to set fixed mode)'
    )
    
    # Live trading options
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually execute live trades (use with --live)'
    )
    parser.add_argument(
        '--auto-confirm',
        action='store_true',
        help='Skip confirmation prompt (for CI/CD automation)'
    )
    
    # Position management
    mode_group.add_argument(
        '--update',
        action='store_true',
        help='Update position tracking after you trade'
    )
    mode_group.add_argument(
        '--init',
        action='store_true',
        help='Initialize positions (first-time setup)'
    )
    
    # Report options
    parser.add_argument(
        '--report-path',
        type=str,
        default='sectorbot_report.jsx',
        help='Output path for JSX report'
    )
    
    args = parser.parse_args()
    
    # Determine account size (default: small)
    small_account = not args.large
    
    # Determine strategy mode
    strategy_mode = None if args.mode == 'auto' else args.mode
    regime_aware = not args.no_regime
    
    try:
        if args.init:
            init_positions(small_account=small_account)
        elif args.update:
            run_position_update(
                small_account=small_account,
                auto_confirm=args.auto_confirm,
                strategy_mode=strategy_mode,
                regime_aware=regime_aware
            )
        elif args.live:
            run_live_trading(
                small_account=small_account,
                dry_run=not args.execute,
                auto_confirm=args.auto_confirm
            )
        elif args.report:
            # Run signal-only first to get data
            signals, bot = run_signal_only(
                small_account=small_account,
                output_json=False,
                save_report=False,
                strategy_mode=strategy_mode,
                regime_aware=regime_aware
            )
            # Generate JSX report
            generate_patreon_report(signals, args.report_path)
        else:
            # Default: signal-only
            run_signal_only(
                small_account=small_account,
                output_json=args.json,
                save_report=not args.no_save,
                strategy_mode=strategy_mode,
                regime_aware=regime_aware,
                save_positions=args.save_positions
            )
    
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
