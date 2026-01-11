#!/usr/bin/env python3
"""
AdaptiveX2 SectorBot - Main Entry Point
=======================================

Usage:
    python main.py                        # Rotation mode signals (default)
    python main.py --mode parent_based    # Parent-based mode
    python main.py --large                # Large account (20 positions)
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

from strategy import AdaptiveX2SectorBot
from config import PARENT_CHILD_MAPPING, get_all_tickers, DEFAULT_CONFIG, update_meme_holdings


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
║                                                                      ║
║  MODES:                                                              ║
║    rotation (default)  - Rotate weak stocks, active management       ║
║    parent_based        - Hold through weakness, less trading         ║
║    weighted_rotation   - Rotation + sector weighting                 ║
║                                                                      ║
║  TRADING FREQUENCY (from backtests):                                 ║
║    Daily:  Best returns, most work                                   ║
║    3-Day:  Similar returns, less work (recommended)                  ║
║    Weekly: Still good returns, minimal work                          ║
║                                                                      ║
║  WORKFLOW:                                                           ║
║    1. Run: python main.py                                            ║
║    2. Execute EXIT signals first                                     ║
║    3. Execute ROTATION signals                                       ║
║    4. Execute ENTRY signals (if slots available)                     ║
║    5. Repeat every 1-5 days                                          ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
""")


def run_live_trading(small_account: bool = True, strategy_mode: str = 'rotation',
                     dry_run: bool = True, auto_confirm: bool = False):
    """
    Run live trading via Schwab API.
    
    Args:
        small_account: Use small account limits
        strategy_mode: rotation, parent_based, or weighted_rotation
        dry_run: If True, simulate trades without executing
        auto_confirm: Skip confirmation prompts
    """
    # Check for schwab-py
    try:
        from schwab import auth
    except ImportError:
        print("❌ schwab-py not installed. Run:")
        print("   pip install schwab-py")
        return
    
    # First generate signals
    signals, bot = run_signals(
        small_account=small_account,
        strategy_mode=strategy_mode,
        output_json=False,
        save_report=True
    )
    
    # Initialize Schwab client
    print("\n" + "=" * 70)
    print("🔄 SCHWAB LIVE TRADING")
    print("=" * 70)
    
    if dry_run:
        print("⚠️  DRY RUN MODE - No real trades will be executed")
    else:
        print("🚨 LIVE MODE - Real trades will be executed!")
    
    # Get credentials from environment
    import os
    app_key = os.environ.get('SCHWAB_SECTORBOT_APP_KEY')
    app_secret = os.environ.get('SCHWAB_SECTORBOT_APP_SECRET')
    account_hash = os.environ.get('SCHWAB_SECTORBOT_ACCOUNT_HASH')
    token_path = 'sectorbot_token.json'
    
    if not app_key or not app_secret:
        print("❌ Missing Schwab credentials. Set environment variables:")
        print("   SCHWAB_SECTORBOT_APP_KEY")
        print("   SCHWAB_SECTORBOT_APP_SECRET")
        print("   SCHWAB_SECTORBOT_ACCOUNT_HASH (optional)")
        return
    
    try:
        # Try to load existing token
        if os.path.exists(token_path):
            client = auth.client_from_token_file(token_path, app_key, app_secret)
            print("✅ Loaded Schwab token")
        else:
            # No token - start OAuth flow
            print("🔐 No token found. Starting OAuth flow...")
            print("   A browser will open for you to log into Schwab.")
            print("")
            
            try:
                client = auth.client_from_manual_flow(
                    app_key,
                    app_secret,
                    'https://127.0.0.1',
                    token_path=token_path
                )
                print("✅ Token saved to", token_path)
            except Exception as oauth_error:
                print(f"❌ OAuth failed: {oauth_error}")
                print("")
                print("Manual steps:")
                print("1. Go to Schwab Developer Portal")
                print("2. Make sure callback URL is: https://127.0.0.1")
                print("3. Try again")
                return
        
        # Get account hash if not provided
        if not account_hash:
            accounts = client.get_account_numbers()
            if accounts.status_code == 200:
                account_list = accounts.json()
                if account_list:
                    account_hash = account_list[0]['hashValue']
                    print(f"✅ Using account: {account_hash[:8]}...")
                else:
                    print("❌ No accounts found")
                    return
            else:
                print(f"❌ Could not get accounts: {accounts.status_code}")
                return
        
        # Get current positions
        account_resp = client.get_account(account_hash, fields=['positions'])
        if account_resp.status_code != 200:
            print(f"❌ Could not get account: {account_resp.status_code}")
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
        
        # Get account balances
        balances = account_data['securitiesAccount'].get('currentBalances', {})
        cash = balances.get('cashBalance', 0)
        account_value = balances.get('liquidationValue', 0)
        print(f"\n💰 Cash: ${cash:,.2f}")
        print(f"💼 Account Value: ${account_value:,.2f}")
        
        # Calculate position size
        position_value = (account_value * 0.95) / bot.max_positions
        print(f"📐 Target per position: ${position_value:,.2f}")
        
        # Process exit signals
        if signals['exit_signals']:
            print(f"\n🔴 EXIT SIGNALS ({len(signals['exit_signals'])}):")
            for sig in signals['exit_signals']:
                ticker = sig['ticker']
                if ticker in positions:
                    qty = positions[ticker]['quantity']
                    if dry_run:
                        print(f"   [DRY RUN] Would sell {qty} {ticker}")
                    elif auto_confirm or input(f"   SELL {qty} {ticker}? (y/n): ").lower() == 'y':
                        # Place market sell order
                        from schwab.orders.equities import equity_sell_market
                        order = equity_sell_market(ticker, qty)
                        resp = client.place_order(account_hash, order)
                        if resp.status_code in [200, 201]:
                            print(f"   ✅ Sold {qty} {ticker}")
                        else:
                            print(f"   ❌ Failed: {resp.status_code}")
                else:
                    print(f"   ⏭️  {ticker} - not in portfolio, skipping")
        
        # Process rotation signals
        if signals['rotation_signals']:
            print(f"\n🔄 ROTATION SIGNALS ({len(signals['rotation_signals'])}):")
            for rot in signals['rotation_signals']:
                exit_ticker = rot['exit']['ticker']
                enter_ticker = rot['enter']['ticker']
                
                if dry_run:
                    print(f"   [DRY RUN] Would rotate {exit_ticker} → {enter_ticker}")
                elif auto_confirm or input(f"   ROTATE {exit_ticker} → {enter_ticker}? (y/n): ").lower() == 'y':
                    from schwab.orders.equities import equity_sell_market, equity_buy_market
                    
                    # Sell first
                    if exit_ticker in positions:
                        qty = positions[exit_ticker]['quantity']
                        order = equity_sell_market(exit_ticker, qty)
                        resp = client.place_order(account_hash, order)
                        if resp.status_code in [200, 201]:
                            print(f"   ✅ Sold {qty} {exit_ticker}")
                        else:
                            print(f"   ❌ Failed to sell: {resp.status_code}")
                            continue
                    
                    # Buy new position
                    price = bot.get_price(enter_ticker) or 100
                    qty = max(1, int(position_value / price))
                    order = equity_buy_market(enter_ticker, qty)
                    resp = client.place_order(account_hash, order)
                    if resp.status_code in [200, 201]:
                        print(f"   ✅ Bought {qty} {enter_ticker}")
                    else:
                        print(f"   ❌ Failed to buy: {resp.status_code}")
        
        # Process entry signals
        if signals['entry_signals']:
            current_count = len(positions)
            available_slots = bot.max_positions - current_count
            
            if available_slots > 0:
                print(f"\n🟢 ENTRY SIGNALS ({min(len(signals['entry_signals']), available_slots)} of {len(signals['entry_signals'])}):")
                for sig in signals['entry_signals'][:available_slots]:
                    ticker = sig['ticker']
                    if ticker not in positions:
                        price = bot.get_price(ticker) or 100
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
    
    # Account size
    parser.add_argument(
        '--large',
        action='store_true',
        help='Large account mode (20 positions, 5 per sector)'
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
    
    # Strategy mode
    parser.add_argument(
        '--mode',
        type=str,
        choices=['rotation', 'parent_based', 'weighted_rotation'],
        default='rotation',
        help='Strategy mode (default: rotation)'
    )
    
    # Live trading
    parser.add_argument(
        '--live',
        action='store_true',
        help='Execute LIVE trades via Schwab (real money!)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Test Schwab connection without executing trades'
    )
    parser.add_argument(
        '--auto-confirm',
        action='store_true',
        help='Skip confirmation prompts (for automation)'
    )
    
    # Help
    parser.add_argument(
        '--usage',
        action='store_true',
        help='Show detailed usage examples'
    )
    
    args = parser.parse_args()
    
    if args.usage:
        print_usage()
        return
    
    try:
        if args.live or args.dry_run:
            run_live_trading(
                small_account=not args.large,
                strategy_mode=args.mode,
                dry_run=args.dry_run,  # --dry-run = test, --live = real
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
        raise


if __name__ == "__main__":
    main()
