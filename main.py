#!/usr/bin/env python3
"""
SectorSBITrader - Main Entry Point

A sector rotation strategy that uses parent signals (ETFs/assets) to determine
timing, then drills into individual stocks using the Signal Bullish Index (SBI).

Usage:
    python main.py                     # Run daily signal generation
    python main.py --scan              # Scan all sectors
    python main.py --sector BTC-USD    # Scan specific sector
    python main.py --backtest          # Run backtest

Environment Variables:
    SCHWAB_SBI_APP_KEY       - Schwab API key
    SCHWAB_SBI_APP_SECRET    - Schwab API secret
    SCHWAB_SBI_ACCOUNT_HASH  - Schwab account hash
"""

import argparse
from datetime import datetime
import sys


def run_scan(sector: str = None):
    """Run sector scan and display results."""
    from data_fetcher import DataFetcher
    from strategy import SectorSBIStrategy
    from config import PARENT_CHILD_MAPPING
    
    print("\n" + "=" * 60)
    print("SectorSBITrader - Sector Scan")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Fetch data
    fetcher = DataFetcher(cache_file='sbi_data_cache.pkl')
    
    if sector:
        # Fetch just the parent and its children
        if sector not in PARENT_CHILD_MAPPING:
            print(f"Error: Unknown sector '{sector}'")
            print(f"Available: {', '.join(PARENT_CHILD_MAPPING.keys())}")
            return
        
        tickers = [sector] + PARENT_CHILD_MAPPING[sector]['stocks']
        print(f"\nFetching data for {sector} sector ({len(tickers)} tickers)...")
        price_data, volume_data = fetcher.fetch_batch(tickers)
    else:
        # Fetch all data
        print("\nFetching data for all sectors...")
        price_data, volume_data = fetcher.get_data()
    
    # Run strategy
    strategy = SectorSBIStrategy(price_data, volume_data)
    
    if sector:
        # Analyze single sector
        analysis = strategy.analyze_sector(sector)
        print_sector_analysis(analysis)
    else:
        # Full allocation
        allocation = strategy.print_analysis_report()
        return allocation


def print_sector_analysis(analysis):
    """Print detailed sector analysis."""
    from strategy import ParentSignal
    
    print(f"\n{'='*60}")
    print(f"SECTOR: {analysis.parent} - {analysis.description}")
    print(f"{'='*60}")
    
    signal_icon = "🟢 BULLISH" if analysis.parent_signal == ParentSignal.BULLISH else "🔴 BEARISH"
    print(f"Parent Signal: {signal_icon}")
    print(f"Reason: {analysis.parent_reason}")
    
    if analysis.entry_candidates:
        print(f"\n✅ ENTRY CANDIDATES ({len(analysis.entry_candidates)}):")
        for stock in analysis.entry_candidates:
            weight = "2x" if stock.weight_multiplier == 2.0 else "1x"
            print(f"   {stock.ticker:6} | SBI: {stock.sbi_score}/10 | ${stock.price:.2f} | Weight: {weight}")
    else:
        print(f"\n⚠️ No entry candidates (SBI >= 9)")
    
    print(f"\nAll stocks ({len(analysis.stocks)}):")
    for stock in analysis.stocks:
        entry = "✅" if stock.is_entry_signal() else "  "
        print(f"   {entry} {stock.ticker:6} | SBI: {stock.sbi_score:2}/10 | ${stock.price:.2f}")


def run_backtest(start_date: str = None, end_date: str = None):
    """Run backtest and display results."""
    from data_fetcher import DataFetcher
    from backtester import Backtester
    
    start_date = start_date or '2022-01-01'
    end_date = end_date or datetime.now().strftime('%Y-%m-%d')
    
    print("\n" + "=" * 60)
    print("SectorSBITrader - Backtest")
    print("=" * 60)
    print(f"Period: {start_date} to {end_date}")
    
    # Fetch data
    print("\nFetching historical data...")
    fetcher = DataFetcher(cache_file='sbi_data_cache.pkl')
    price_data, volume_data = fetcher.get_data()
    
    # Run backtest
    print("\nRunning backtest...")
    bt = Backtester(price_data, volume_data)
    result = bt.run(start_date, end_date)
    
    # Print results
    bt.print_results(result)
    
    return result


def run_signals():
    """Generate daily signals."""
    from data_fetcher import DataFetcher
    from strategy import SectorSBIStrategy
    
    print("\n" + "=" * 60)
    print("SectorSBITrader - Daily Signal Generation")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Fetch fresh data
    print("\nFetching latest data...")
    fetcher = DataFetcher(cache_file='sbi_data_cache.pkl')
    price_data, volume_data = fetcher.get_data()
    
    # Generate allocation
    print("\nGenerating signals...")
    strategy = SectorSBIStrategy(price_data, volume_data)
    allocation = strategy.generate_allocation()
    
    # Print results
    for line in allocation.reasoning:
        print(line)
    
    return allocation


def main():
    parser = argparse.ArgumentParser(
        description='SectorSBITrader - Sector rotation with SBI stock selection',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                     # Generate daily signals
  python main.py --scan              # Full sector scan
  python main.py --sector BTC-USD    # Scan Bitcoin sector
  python main.py --sector XLK        # Scan Technology sector
  python main.py --backtest          # Run backtest (2022-present)
  python main.py --backtest --start 2023-01-01 --end 2024-12-31
        """
    )
    
    parser.add_argument('--scan', action='store_true',
                        help='Run full sector scan')
    parser.add_argument('--sector', type=str, default=None,
                        help='Scan specific sector (e.g., BTC-USD, XLK, GLD)')
    parser.add_argument('--backtest', action='store_true',
                        help='Run backtest')
    parser.add_argument('--start', type=str, default=None,
                        help='Backtest start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=None,
                        help='Backtest end date (YYYY-MM-DD)')
    parser.add_argument('--list-sectors', action='store_true',
                        help='List all available sectors')
    
    args = parser.parse_args()
    
    # List sectors
    if args.list_sectors:
        from config import PARENT_CHILD_MAPPING
        print("\nAvailable Sectors:")
        print("-" * 60)
        for parent, info in PARENT_CHILD_MAPPING.items():
            n_stocks = len(info['stocks'])
            print(f"  {parent:12} | {info['description']:25} | {n_stocks} stocks")
        return
    
    # Run backtest
    if args.backtest:
        run_backtest(args.start, args.end)
        return
    
    # Scan sector(s)
    if args.scan or args.sector:
        run_scan(args.sector)
        return
    
    # Default: generate signals
    run_signals()


if __name__ == "__main__":
    main()
