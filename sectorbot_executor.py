#!/usr/bin/env python3
"""
SectorBot Schwab Executor
=========================

Handles trade execution for AdaptiveX2 SectorBot via Schwab API.
Uses separate credentials from main AdaptiveX2 strategy.

Environment Variables:
    SCHWAB_SECTORBOT_APP_KEY      - Schwab API app key for SectorBot account
    SCHWAB_SECTORBOT_APP_SECRET   - Schwab API app secret
    SCHWAB_SECTORBOT_ACCOUNT_HASH - Account hash (optional, uses first if not set)
    SCHWAB_SECTORBOT_TOKEN_PATH   - Path to token file (default: sectorbot_token.json)
"""

import os
import json
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from decimal import Decimal


class SectorBotExecutor:
    """
    Executes SectorBot trades via Schwab API.
    """
    
    def __init__(self, 
                 app_key: str = None,
                 app_secret: str = None,
                 account_hash: str = None,
                 token_path: str = None,
                 dry_run: bool = True):
        """
        Initialize executor.
        
        Args:
            app_key: Schwab API app key
            app_secret: Schwab API app secret
            account_hash: Specific account hash (optional)
            token_path: Path to token file
            dry_run: If True, don't execute real trades
        """
        self.app_key = app_key or os.environ.get('SCHWAB_SECTORBOT_APP_KEY')
        self.app_secret = app_secret or os.environ.get('SCHWAB_SECTORBOT_APP_SECRET')
        self.account_hash = account_hash or os.environ.get('SCHWAB_SECTORBOT_ACCOUNT_HASH')
        self.token_path = token_path or os.environ.get('SCHWAB_SECTORBOT_TOKEN_PATH', 'sectorbot_token.json')
        self.dry_run = dry_run
        
        self.client = None
        self._init_client()
    
    def _init_client(self):
        """Initialize Schwab API client."""
        try:
            import schwab
            from schwab import auth
            
            # Try to load existing token
            if os.path.exists(self.token_path):
                self.client = auth.client_from_token_file(
                    self.token_path,
                    self.app_key,
                    self.app_secret
                )
                print("   ✅ Loaded existing Schwab token")
            else:
                # Need to authenticate
                print("\n⚠️  No token found. Starting OAuth flow...")
                print("   A browser window will open for authentication.")
                
                callback_url = os.environ.get('SCHWAB_CALLBACK_URL', 'https://127.0.0.1:8182/callback')
                
                self.client = auth.client_from_manual_flow(
                    self.app_key,
                    self.app_secret,
                    callback_url,
                    self.token_path
                )
                print("   ✅ Authentication successful")
                
        except ImportError:
            print("   ⚠️ schwab-py not installed. Install with: pip install schwab-py")
            self.client = None
        except Exception as e:
            print(f"   ❌ Schwab client init failed: {e}")
            self.client = None
    
    def get_account_info(self) -> dict:
        """Get account information."""
        if not self.client:
            return {}
        
        try:
            # Get all accounts if no specific hash
            if not self.account_hash:
                response = self.client.get_account_numbers()
                accounts = response.json()
                if accounts:
                    self.account_hash = accounts[0]['hashValue']
                    print(f"   Using account: {accounts[0].get('accountNumber', 'N/A')}")
            
            # Get account details
            response = self.client.get_account(self.account_hash)
            return response.json()
            
        except Exception as e:
            print(f"   ❌ Failed to get account info: {e}")
            return {}
    
    def get_positions(self) -> List[dict]:
        """
        Get current positions in the account.
        
        Returns:
            List of position dicts with ticker, quantity, market_value
        """
        if not self.client:
            return []
        
        try:
            account_info = self.get_account_info()
            
            positions = []
            securities = account_info.get('securitiesAccount', {})
            
            for pos in securities.get('positions', []):
                instrument = pos.get('instrument', {})
                ticker = instrument.get('symbol', '')
                
                positions.append({
                    'ticker': ticker,
                    'quantity': pos.get('longQuantity', 0) - pos.get('shortQuantity', 0),
                    'market_value': pos.get('marketValue', 0),
                    'average_price': pos.get('averagePrice', 0),
                    'current_price': pos.get('currentDayProfitLoss', 0) / pos.get('longQuantity', 1) + pos.get('averagePrice', 0) if pos.get('longQuantity', 0) > 0 else 0
                })
            
            return positions
            
        except Exception as e:
            print(f"   ❌ Failed to get positions: {e}")
            return []
    
    def get_buying_power(self) -> float:
        """Get available buying power."""
        if not self.client:
            return 0
        
        try:
            account_info = self.get_account_info()
            securities = account_info.get('securitiesAccount', {})
            
            # Use cash available for trading
            return securities.get('currentBalances', {}).get('cashAvailableForTrading', 0)
            
        except Exception as e:
            print(f"   ❌ Failed to get buying power: {e}")
            return 0
    
    def get_quote(self, ticker: str) -> float:
        """Get current quote for a ticker."""
        if not self.client:
            return 0
        
        try:
            response = self.client.get_quote(ticker)
            quote = response.json()
            
            # Get last price
            return quote.get(ticker, {}).get('quote', {}).get('lastPrice', 0)
            
        except Exception as e:
            print(f"   ⚠️ Failed to get quote for {ticker}: {e}")
            return 0
    
    def calculate_trades(self, 
                        current_positions: List[dict],
                        target_allocation: List[dict],
                        total_value: float = None) -> List[dict]:
        """
        Calculate trades needed to reach target allocation.
        
        Args:
            current_positions: List of current positions
            target_allocation: List of target positions with weights
            total_value: Total portfolio value (auto-calculated if None)
        
        Returns:
            List of trades to execute
        """
        # Build current position map
        current_map = {p['ticker']: p for p in current_positions}
        
        # Calculate total portfolio value
        if total_value is None:
            total_value = sum(p.get('market_value', 0) for p in current_positions)
            total_value += self.get_buying_power()
        
        if total_value <= 0:
            print("   ⚠️ No portfolio value found")
            return []
        
        print(f"\n   💰 Portfolio Value: ${total_value:,.2f}")
        
        # Build target map
        target_map = {}
        for t in target_allocation:
            ticker = t.get('ticker')
            weight = t.get('weight', 0)
            target_map[ticker] = weight
        
        trades = []
        
        # Calculate sells first (positions not in target)
        for ticker, pos in current_map.items():
            if ticker not in target_map:
                # Sell entire position
                trades.append({
                    'action': 'SELL',
                    'ticker': ticker,
                    'shares': pos['quantity'],
                    'reason': 'Not in target allocation'
                })
        
        # Calculate buys and rebalances
        for ticker, target_weight in target_map.items():
            target_value = total_value * target_weight
            current_value = current_map.get(ticker, {}).get('market_value', 0)
            
            diff_value = target_value - current_value
            
            # Get current price
            price = self.get_quote(ticker)
            if price <= 0:
                # Try to get from current position
                price = current_map.get(ticker, {}).get('current_price', 0)
            
            if price <= 0:
                print(f"   ⚠️ Could not get price for {ticker}, skipping")
                continue
            
            # Calculate shares to trade
            shares_diff = int(diff_value / price)
            
            # Only trade if significant (> $50 or > 1 share)
            if abs(diff_value) > 50 and abs(shares_diff) >= 1:
                if shares_diff > 0:
                    trades.append({
                        'action': 'BUY',
                        'ticker': ticker,
                        'shares': shares_diff,
                        'estimated_value': shares_diff * price,
                        'reason': 'New position' if ticker not in current_map else 'Rebalance up'
                    })
                else:
                    trades.append({
                        'action': 'SELL',
                        'ticker': ticker,
                        'shares': abs(shares_diff),
                        'estimated_value': abs(shares_diff) * price,
                        'reason': 'Rebalance down'
                    })
        
        return trades
    
    def execute_trades(self, trades: List[dict]) -> List[str]:
        """
        Execute a list of trades.
        
        Args:
            trades: List of trade dicts with action, ticker, shares
        
        Returns:
            List of result strings
        """
        if not self.client:
            return ["❌ No Schwab client available"]
        
        if self.dry_run:
            return ["🔍 DRY RUN - No trades executed"]
        
        results = []
        
        # Execute sells first to free up cash
        sells = [t for t in trades if t['action'] == 'SELL']
        buys = [t for t in trades if t['action'] == 'BUY']
        
        for trade in sells + buys:
            try:
                result = self._execute_single_trade(trade)
                results.append(result)
                
                # Rate limiting
                time.sleep(0.5)
                
            except Exception as e:
                results.append(f"❌ {trade['ticker']}: {e}")
        
        return results
    
    def _execute_single_trade(self, trade: dict) -> str:
        """Execute a single trade."""
        from schwab.orders.equities import equity_buy_market, equity_sell_market
        
        ticker = trade['ticker']
        shares = trade['shares']
        action = trade['action']
        
        if action == 'BUY':
            order = equity_buy_market(ticker, shares)
        else:
            order = equity_sell_market(ticker, shares)
        
        # Place order
        response = self.client.place_order(self.account_hash, order)
        
        if response.status_code in [200, 201]:
            return f"✅ {action} {shares} {ticker}"
        else:
            return f"❌ {action} {shares} {ticker}: {response.text}"


def main():
    """Test executor."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test SectorBot Executor')
    parser.add_argument('--positions', action='store_true', help='Show current positions')
    parser.add_argument('--account', action='store_true', help='Show account info')
    parser.add_argument('--quote', type=str, help='Get quote for ticker')
    
    args = parser.parse_args()
    
    executor = SectorBotExecutor(dry_run=True)
    
    if args.positions:
        positions = executor.get_positions()
        print("\n📊 Current Positions:")
        print("-" * 50)
        for pos in positions:
            print(f"   {pos['ticker']:<8} {pos['quantity']:>6} shares  ${pos['market_value']:>10,.2f}")
    
    if args.account:
        info = executor.get_account_info()
        print("\n💰 Account Info:")
        print(json.dumps(info, indent=2))
    
    if args.quote:
        price = executor.get_quote(args.quote)
        print(f"\n📈 {args.quote}: ${price:.2f}")


if __name__ == "__main__":
    main()
