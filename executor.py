"""
Trading Executor
Manages portfolio positions and executes trades based on strategy signals
"""

import json
from datetime import datetime
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, asdict
from pathlib import Path

from strategy import Signal, StrategyState, TechnicalIndicators, SIGNAL_PRICES


# Approximate prices for affordability check (updated Dec 2024)
# Used to find affordable alternatives when primary signal is too expensive
# Now uses SCHX (not SPY/SPLG) and IAUM (not GLD) for small account compatibility
APPROX_PRICES = {
    "PDBC": 15,    # Cheapest
    "SPXU": 22,
    "IAUM": 26,    # Gold (was GLD at $242)
    "SCHA": 26,    # Small-cap (Russell 2000 proxy)
    "SCHX": 28,    # Large-cap S&P 500 (was SPY at $681)
    "SCHG": 28,    # Large-cap Growth (Nasdaq proxy)
    "UUP": 29,
    "TNA": 35,     # 3x Small-cap (Russell 2000)
    "BITU": 38,    # 2x Bitcoin
    "SCHO": 48,
    "IBIT": 51,    # Bitcoin ETF
    "TQQQ": 56,
    "SHY": 82,
    "UPRO": 90,
    "IEF": 92,
    "UGL": 95,     # 2x Gold
}


@dataclass
class Position:
    """Represents a portfolio position"""
    symbol: str
    quantity: int
    avg_cost: float
    current_price: float = 0.0
    market_value: float = 0.0
    
    def update_price(self, price: float):
        self.current_price = price
        self.market_value = self.quantity * price


@dataclass
class TradeExecution:
    """Record of an executed trade"""
    timestamp: datetime
    action: str  # "BUY" or "SELL"
    symbol: str
    quantity: int
    price: float
    reason: str
    order_id: Optional[str] = None


class TradingExecutor:
    """
    Executes trades based on strategy signals
    Handles position management and order execution
    
    SAFETY FEATURES:
    - Cash-only trading (NO MARGIN)
    - Hard position limits
    - Pre-trade validation
    """
    
    def __init__(
        self,
        schwab_client,
        account_hash: str,
        allocation_pct: float = 0.95,  # Use 95% of account value
        dry_run: bool = True,
        max_position_value: float = None,  # Optional hard cap on position size
        allow_margin: bool = False  # HARD RESTRICTION - Never use margin
    ):
        """
        Initialize the trading executor
        
        Args:
            schwab_client: Authenticated SchwabClient instance
            account_hash: Schwab account hash to trade in
            allocation_pct: Percentage of account to allocate to strategy
            dry_run: If True, log trades but don't execute
            max_position_value: Maximum dollar value for any position (safety cap)
            allow_margin: Whether to allow margin trading (DEFAULT: False - CASH ONLY)
        """
        self.client = schwab_client
        self.account_hash = account_hash
        self.allocation_pct = allocation_pct
        self.dry_run = dry_run
        self.max_position_value = max_position_value
        self.allow_margin = allow_margin  # Should ALWAYS be False for safety
        self.trade_history: List[TradeExecution] = []
        self.current_position: Optional[str] = None
        
        # Safety check - warn if margin is enabled
        if self.allow_margin:
            print("âš ï¸  WARNING: Margin trading is enabled. This is risky!")
        else:
            print("âœ“ CASH-ONLY mode enabled (no margin)")
    
    def get_account_value(self) -> float:
        """Get total account value (cash + positions)"""
        try:
            account = self.client.get_account(self.account_hash)
            return account['securitiesAccount']['currentBalances']['liquidationValue']
        except Exception as e:
            print(f"Error getting account value: {e}")
            return 0.0
    
    def get_cash_balance(self) -> float:
        """
        Get available CASH balance for TRADING (not withdrawal)
        
        Schwab has two different "available" amounts:
        - Settled Funds (To Trade): Can use to buy securities = cashBalance
        - Cash to Withdraw: Can transfer out = availableFundsNonMarginableTrade
        
        We want the TRADING limit (cashBalance), not withdrawal limit.
        """
        try:
            account = self.client.get_account(self.account_hash)
            balances = account['securitiesAccount']['currentBalances']
            
            if self.allow_margin:
                # Use full buying power (includes margin) - DANGEROUS
                return balances.get('buyingPower', 0)
            else:
                # CASH ONLY - use settled cash for trading
                # 'cashBalance' = settled funds available for trading
                cash = balances.get('cashBalance', 0)
                
                # Safety check: ensure we're not using margin
                # If margin_balance > 0, we've borrowed - don't allow more
                margin_debt = balances.get('marginBalance', 0)
                if margin_debt > 0:
                    # We have margin debt - only use cash minus what we owe
                    print(f"âš ï¸ Margin debt detected: ${margin_debt:.2f}")
                    cash = max(0, cash - margin_debt)
                
                return cash
        except Exception as e:
            print(f"Error getting cash balance: {e}")
            return 0.0
    
    def get_margin_status(self) -> dict:
        """Check account margin status for safety verification"""
        try:
            account = self.client.get_account(self.account_hash)
            balances = account['securitiesAccount']['currentBalances']
            
            return {
                'account_type': account['securitiesAccount'].get('type', 'UNKNOWN'),
                'cash_balance': balances.get('cashBalance', 0),
                'buying_power': balances.get('buyingPower', 0),
                'margin_balance': balances.get('marginBalance', 0),
                'available_funds': balances.get('availableFunds', 0),
                'available_funds_non_margin': balances.get('availableFundsNonMarginableTrade', 0),
            }
        except Exception as e:
            print(f"Error getting margin status: {e}")
            return {}
    
    def validate_trade_safety(self, symbol: str, quantity: int, action: str) -> tuple:
        """
        Validate that a trade is safe before execution
        
        Returns:
            (is_safe, reason)
        """
        if action == "BUY":
            price = self.get_current_price(symbol)
            total_cost = quantity * price
            cash_available = self.get_cash_balance()
            
            # Check 1: Do we have enough cash (not margin)?
            if total_cost > cash_available:
                return False, f"Insufficient CASH: need ${total_cost:.2f}, have ${cash_available:.2f} cash"
            
            # Check 2: Does this exceed our max position limit?
            if self.max_position_value and total_cost > self.max_position_value:
                return False, f"Exceeds max position: ${total_cost:.2f} > ${self.max_position_value:.2f} limit"
            
            # Check 3: Verify we're not accidentally using margin
            margin_status = self.get_margin_status()
            if margin_status.get('margin_balance', 0) > 0:
                print(f"âš ï¸  Warning: Account has margin balance of ${margin_status['margin_balance']:.2f}")
            
            return True, "Trade validated"
        
        return True, "Sell order validated"
    
    def find_affordable_signal(self, original_signal: Signal, cash_available: float, price_data: dict = None) -> tuple:
        """
        Find an affordable alternative if the original signal is too expensive
        
        Args:
            original_signal: The strategy's recommended signal
            cash_available: Cash available in account
            price_data: Optional price data for momentum ranking
        
        Returns:
            (affordable_signal, reason)
        """
        original_price = APPROX_PRICES.get(original_signal.value, 100)
        
        # Can we afford the original signal?
        if cash_available >= original_price * 1.05:  # 5% buffer
            return original_signal, "Original signal affordable"
        
        print(f"\nâš ï¸  ${cash_available:.2f} cannot buy {original_signal.value} (~${original_price})")
        print("   Looking for affordable alternatives...")
        
        # Build list of affordable alternatives sorted by price (cheapest first for reliability)
        affordable = []
        for signal in Signal:
            price = APPROX_PRICES.get(signal.value, 999)
            if cash_available >= price * 1.05:
                affordable.append((signal, price))
        
        if not affordable:
            return None, f"No affordable signals with ${cash_available:.2f}"
        
        # Sort by price (so we definitely can afford it)
        affordable.sort(key=lambda x: x[1])
        
        # Prefer similar category if possible
        category_map = {
            "defensive": [Signal.SPXU, Signal.SCHO],
            "growth": [Signal.TQQQ, Signal.UPRO],
            "moderate": [Signal.SCHX, Signal.SHY, Signal.IEF],
            "commodity": [Signal.PDBC, Signal.IAUM],
            "dollar": [Signal.UUP],
        }
        
        # Find original's category
        original_category = None
        for cat, signals in category_map.items():
            if original_signal in signals:
                original_category = cat
                break
        
        # Try to find affordable signal in same category
        if original_category:
            for signal, price in affordable:
                if signal in category_map.get(original_category, []):
                    print(f"   âœ“ Found {signal.value} (~${price}) in same category")
                    return signal, f"Affordable alternative in {original_category} category"
        
        # Otherwise just pick cheapest affordable
        best = affordable[0]
        print(f"   âœ“ Falling back to {best[0].value} (~${best[1]})")
        return best[0], "Cheapest affordable alternative"
    
    def get_positions(self) -> Dict[str, Position]:
        """Get current positions in account (excludes sold/zero positions)"""
        positions = {}
        try:
            account = self.client.get_account(self.account_hash, fields="positions")
            for pos in account.get('securitiesAccount', {}).get('positions', []):
                symbol = pos['instrument']['symbol']
                long_qty = pos.get('longQuantity', 0)
                short_qty = pos.get('shortQuantity', 0)
                net_qty = int(long_qty - short_qty)
                
                # Skip positions with zero or negative quantity (sold)
                if net_qty <= 0:
                    continue
                    
                positions[symbol] = Position(
                    symbol=symbol,
                    quantity=net_qty,
                    avg_cost=pos.get('averagePrice', 0),
                    current_price=pos.get('currentDayProfitLoss', 0) / long_qty + pos.get('averagePrice', 0) if long_qty > 0 else 0,
                    market_value=pos.get('marketValue', 0)
                )
        except Exception as e:
            print(f"Error getting positions: {e}")
        return positions
    
    def get_current_price(self, symbol: str) -> float:
        """Get current price for a symbol"""
        try:
            response = self.client.get_quote(symbol)
            if response.status_code == 200:
                data = response.json()
                return data[symbol]['quote']['lastPrice']
        except Exception as e:
            print(f"Error getting price for {symbol}: {e}")
        return 0.0
    
    def _check_order_status(self, order_id: str) -> str:
        """
        Check the status of a placed order
        
        Returns:
            Order status string: 'FILLED', 'CANCELED', 'QUEUED', 'WORKING', etc.
        """
        try:
            from datetime import datetime, timedelta
            
            # Get today's orders
            today = datetime.now().strftime('%Y-%m-%dT00:00:00.000Z')
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00.000Z')
            
            orders = self.client.get_orders(
                self.account_hash, 
                from_date=today,
                to_date=tomorrow
            )
            
            for order in orders:
                if str(order.get('orderId')) == str(order_id):
                    status = order.get('status', 'UNKNOWN')
                    
                    # Log additional info if cancelled
                    if status == 'CANCELED':
                        cancel_time = order.get('cancelTime', 'N/A')
                        close_time = order.get('closeTime', 'N/A')
                        print(f"  Order cancelled at: {cancel_time or close_time}")
                    
                    return status
            
            return 'NOT_FOUND'
            
        except Exception as e:
            print(f"Error checking order status: {e}")
            return 'ERROR'
    
    def calculate_shares(self, symbol: str, target_value: float) -> int:
        """Calculate number of shares to buy given target dollar value"""
        price = self.get_current_price(symbol)
        if price <= 0:
            return 0
        return int(target_value / price)
    
    def verify_no_margin_used(self) -> bool:
        """
        Verify we haven't accidentally used margin
        CRITICAL SAFETY CHECK - runs before every trade
        """
        status = self.get_margin_status()
        margin_debt = status.get('margin_balance', 0)
        
        print("\n--- MARGIN SAFETY CHECK ---")
        print(f"Account Type: {status.get('account_type', 'UNKNOWN')}")
        print(f"Cash Balance: ${status.get('cash_balance', 0):,.2f}")
        print(f"Margin Balance: ${margin_debt:,.2f}")
        
        # Show the actual trading cash available
        trading_cash = self.get_cash_balance()
        print(f"Available (Cash Only): ${trading_cash:,.2f}")
        
        if margin_debt > 0:
            print(f"ðŸš¨ CRITICAL: Margin debt detected: ${margin_debt:,.2f}")
            print("ðŸš¨ HALTING ALL TRADES until margin is paid off!")
            print("ðŸš¨ Please deposit cash or sell positions to clear margin.")
            return False
        
        print("âœ… No margin debt - safe to proceed")
        print("----------------------------")
        return True

    def execute_rebalance(self, state: StrategyState) -> List[TradeExecution]:
        """
        Execute rebalance based on strategy signal
        
        Args:
            state: StrategyState with the signal to execute
        
        Returns:
            List of executed trades
        """
        original_signal = state.signal
        target_symbol = state.signal.value  # May be overridden for small accounts
        executions = []
        
        print("\n" + "=" * 60)
        print("TRADE EXECUTION")
        print("=" * 60)
        print(f"Strategy Signal: {original_signal.value}")
        print(f"Dry Run: {self.dry_run}")
        
        # CRITICAL: Verify no margin is being used before ANY trade
        if not self.dry_run and not self.verify_no_margin_used():
            print("\nðŸš¨ ABORTING: Margin safety check failed!")
            return executions
        
        # Get current state
        positions = self.get_positions()
        account_value = self.get_account_value()
        target_allocation = account_value * self.allocation_pct
        
        print(f"Account Value: ${account_value:,.2f}")
        print(f"Target Allocation: ${target_allocation:,.2f}")
        if positions:
            print(f"Current Positions: {list(positions.keys())}")
        else:
            print(f"Current Positions: None (cash only)")
        
        # SMALL ACCOUNT CHECK: Can we afford the signal?
        affordable_signal, affordability_reason = self.find_affordable_signal(
            state.signal, target_allocation
        )
        
        if affordable_signal is None:
            print(f"\nðŸš¨ Cannot afford ANY signal with ${target_allocation:.2f}")
            print("ðŸš¨ Please add more funds (minimum ~$15 for PDBC)")
            return executions
        
        if affordable_signal != state.signal:
            print(f"\nðŸ“‰ SMALL ACCOUNT ADJUSTMENT:")
            print(f"   Original signal: {state.signal.value}")
            print(f"   Affordable signal: {affordable_signal.value}")
            print(f"   Reason: {affordability_reason}")
            target_symbol = affordable_signal.value
        else:
            target_symbol = state.signal.value
        
        # Check if we need to rebalance
        current_holdings = [s for s, p in positions.items() if p.quantity > 0 and s in [sig.value for sig in Signal]]
        
        if target_symbol in current_holdings and len(current_holdings) == 1:
            print(f"\nâœ“ Already holding {target_symbol}, no rebalance needed")
            return executions
        
        # STEP 1: Sell existing strategy positions
        for symbol, position in positions.items():
            if symbol in [sig.value for sig in Signal] and symbol != target_symbol:
                if position.quantity > 0:
                    print(f"\nSelling {position.quantity} shares of {symbol}...")
                    execution = self._execute_sell(
                        symbol=symbol,
                        quantity=position.quantity,
                        reason=f"Rebalance: {symbol} â†’ {target_symbol}"
                    )
                    if execution:
                        executions.append(execution)
        
        # STEP 2: Buy target position
        # Recalculate after sells
        if not self.dry_run:
            import time
            time.sleep(2)  # Wait for orders to fill
        
        cash_available = self.get_cash_balance() if not self.dry_run else target_allocation
        shares_to_buy = self.calculate_shares(target_symbol, cash_available * 0.99)  # Leave 1% buffer
        
        if shares_to_buy > 0:
            print(f"\nBuying {shares_to_buy} shares of {target_symbol}...")
            execution = self._execute_buy(
                symbol=target_symbol,
                quantity=shares_to_buy,
                reason=f"Strategy signal: {target_symbol}"
            )
            if execution:
                executions.append(execution)
        
        self.current_position = target_symbol
        self.trade_history.extend(executions)
        
        print("\n" + "-" * 40)
        print(f"Trades Executed: {len(executions)}")
        for trade in executions:
            print(f"  {trade.action} {trade.quantity} {trade.symbol} @ ${trade.price:.2f}")
        print("=" * 60)
        
        return executions
    
    def _execute_buy(self, symbol: str, quantity: int, reason: str) -> Optional[TradeExecution]:
        """Execute a buy order with safety validation"""
        price = self.get_current_price(symbol)
        
        # SAFETY: Validate trade before execution
        if not self.dry_run:
            is_safe, validation_msg = self.validate_trade_safety(symbol, quantity, "BUY")
            if not is_safe:
                print(f"  ðŸš¨ TRADE BLOCKED: {validation_msg}")
                return None
            print(f"  âœ… {validation_msg}")
        
        execution = TradeExecution(
            timestamp=datetime.now(),
            action="BUY",
            symbol=symbol,
            quantity=quantity,
            price=price,
            reason=reason
        )
        
        if self.dry_run:
            print(f"  [DRY RUN] Would buy {quantity} {symbol} @ ${price:.2f}")
            return execution
        
        try:
            from schwab_client import create_marketable_limit_order
            
            # Get current ask price for limit order
            ask_price = self.get_current_price(symbol)
            
            # Create limit order slightly above ask (acts like market but safer)
            order = create_marketable_limit_order(symbol, quantity, ask_price, "BUY", buffer_pct=0.5)
            limit_price = float(order['price'])
            
            print(f"  Placing LIMIT BUY @ ${limit_price:.2f} (ask: ${ask_price:.2f})")
            
            response = self.client.place_order(self.account_hash, order)
            
            if response.status_code in [200, 201]:
                # Extract order ID from Location header
                location = response.headers.get('Location', '')
                order_id = location.split('/')[-1] if location else None
                execution.order_id = order_id
                print(f"  âœ“ Order placed: {order_id}")
                
                # Verify order wasn't immediately cancelled
                if order_id:
                    import time
                    time.sleep(2)  # Wait for Schwab to process
                    status = self._check_order_status(order_id)
                    if status == 'CANCELED':
                        print(f"  âš ï¸ Order was CANCELLED by Schwab - check buying power/settlement")
                        return None
                    elif status in ['FILLED', 'QUEUED', 'ACCEPTED', 'WORKING', 'PENDING_ACTIVATION']:
                        print(f"  âœ“ Order status: {status}")
                
                return execution
            else:
                print(f"  âœ— Order failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"  âœ— Error placing buy order: {e}")
            return None
    
    def _execute_sell(self, symbol: str, quantity: int, reason: str) -> Optional[TradeExecution]:
        """Execute a sell order"""
        price = self.get_current_price(symbol)
        
        execution = TradeExecution(
            timestamp=datetime.now(),
            action="SELL",
            symbol=symbol,
            quantity=quantity,
            price=price,
            reason=reason
        )
        
        if self.dry_run:
            print(f"  [DRY RUN] Would sell {quantity} {symbol} @ ${price:.2f}")
            return execution
        
        try:
            from schwab_client import create_marketable_limit_order
            
            # Get current bid price for limit order
            bid_price = self.get_current_price(symbol)
            
            # Create limit order slightly below bid (acts like market but safer)
            order = create_marketable_limit_order(symbol, quantity, bid_price, "SELL", buffer_pct=0.5)
            limit_price = float(order['price'])
            
            print(f"  Placing LIMIT SELL @ ${limit_price:.2f} (bid: ${bid_price:.2f})")
            
            response = self.client.place_order(self.account_hash, order)
            
            if response.status_code in [200, 201]:
                location = response.headers.get('Location', '')
                order_id = location.split('/')[-1] if location else None
                execution.order_id = order_id
                print(f"  âœ“ Order placed: {order_id}")
                
                # Verify order wasn't immediately cancelled
                if order_id:
                    import time
                    time.sleep(2)  # Wait for Schwab to process
                    status = self._check_order_status(order_id)
                    if status == 'CANCELED':
                        print(f"  âš ï¸ Order was CANCELLED by Schwab - check buying power/settlement")
                        return None
                    elif status in ['FILLED', 'QUEUED', 'ACCEPTED', 'WORKING', 'PENDING_ACTIVATION']:
                        print(f"  âœ“ Order status: {status}")
                
                return execution
            else:
                print(f"  âœ— Order failed: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"  âœ— Error placing sell order: {e}")
            return None
    
    def save_trade_history(self, filepath: str = "trade_history.json"):
        """Save trade history to file"""
        history = []
        for trade in self.trade_history:
            record = {
                "timestamp": trade.timestamp.isoformat(),
                "action": trade.action,
                "symbol": trade.symbol,
                "quantity": trade.quantity,
                "price": trade.price,
                "reason": trade.reason,
                "order_id": trade.order_id
            }
            history.append(record)
        
        # Append to existing history if file exists
        existing = []
        try:
            with open(filepath, 'r') as f:
                existing = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        
        existing.extend(history)
        
        with open(filepath, 'w') as f:
            json.dump(existing, f, indent=2)
        print(f"Trade history saved to {filepath}")
    
    def execute_allocation(self, allocation) -> List[TradeExecution]:
        """
        Execute rebalance based on multi-position allocation
        
        Args:
            allocation: PortfolioAllocation with positions dict {Signal: weight}
        
        Returns:
            List of executed trades
        """
        from strategy_prsipsar import Signal as PSARSignal, PortfolioAllocation
        
        executions = []
        
        print("\n" + "=" * 60)
        print("TRADE EXECUTION - MULTI-POSITION")
        print("=" * 60)
        print(f"Target Allocation: {allocation}")
        print(f"Dry Run: {self.dry_run}")
        
        # CRITICAL: Verify no margin is being used before ANY trade
        if not self.dry_run and not self.verify_no_margin_used():
            print("\nðŸš¨ ABORTING: Margin safety check failed!")
            return executions
        
        # Get current state
        positions = self.get_positions()
        account_value = self.get_account_value()
        target_total = account_value * self.allocation_pct
        
        print(f"\nAccount Value: ${account_value:,.2f}")
        print(f"Allocation Budget: ${target_total:,.2f}")
        if positions:
            print(f"Current Positions: {list(positions.keys())}")
        else:
            print(f"Current Positions: None (cash only)")
        
        # Get target symbols and weights
        target_positions = {}
        for signal, weight in allocation.positions.items():
            symbol = signal.value
            target_value = target_total * weight
            target_positions[symbol] = {
                'weight': weight,
                'target_value': target_value,
                'signal': signal
            }
        
        print(f"\nTarget Positions:")
        for symbol, data in target_positions.items():
            print(f"  {symbol}: {data['weight']*100:.0f}% = ${data['target_value']:,.2f}")
        
        # STEP 1: Identify positions to sell (not in target OR overweight)
        # Get all strategy-related symbols
        strategy_symbols = [s.value for s in PSARSignal]
        
        for symbol, position in positions.items():
            if symbol in strategy_symbols:
                current_shares = position.quantity
                if current_shares <= 0:
                    continue
                    
                price = self.get_current_price(symbol)
                if price <= 0:
                    price = APPROX_PRICES.get(symbol, 50)
                current_value = current_shares * price
                
                # Case 1: Position not in target at all - sell everything
                if symbol not in target_positions:
                    print(f"\nSelling {current_shares} shares of {symbol} (not in target)...")
                    execution = self._execute_sell(
                        symbol=symbol,
                        quantity=current_shares,
                        reason=f"Rebalance: {symbol} no longer in target allocation"
                    )
                    if execution:
                        executions.append(execution)
                
                # Case 2: Position is overweight - sell excess (with 5% tolerance)
                else:
                    target_value = target_positions[symbol]['target_value']
                    excess_value = current_value - target_value
                    tolerance = target_value * 0.05  # 5% tolerance
                    
                    if excess_value > tolerance:
                        shares_to_sell = int(excess_value / price)
                        if shares_to_sell > 0:
                            print(f"\nReducing {symbol}: ${current_value:,.2f} â†’ ${target_value:,.2f} (selling {shares_to_sell} shares)...")
                            execution = self._execute_sell(
                                symbol=symbol,
                                quantity=shares_to_sell,
                                reason=f"Rebalance: Reducing {symbol} from {current_value/target_total*100:.0f}% to {target_positions[symbol]['weight']*100:.0f}%"
                            )
                            if execution:
                                executions.append(execution)
        
        # STEP 2: Wait for sells to settle
        if not self.dry_run and executions:
            import time
            print("\nWaiting for sells to settle...")
            time.sleep(3)
        
        # STEP 3: Get updated cash balance and buy target positions
        if self.dry_run:
            # In dry run, use target_total
            available_cash = target_total
        else:
            available_cash = self.get_cash_balance()
        
        print(f"\nCash Available: ${available_cash:,.2f}")
        
        # Buy each target position
        for symbol, data in target_positions.items():
            target_value = data['target_value']
            current_value = 0
            current_shares = 0
            
            if symbol in positions:
                current_shares = positions[symbol].quantity
                price = self.get_current_price(symbol)
                current_value = current_shares * price if price > 0 else 0
            
            # Calculate how much more to buy
            value_to_buy = target_value - current_value
            
            # Use 5% tolerance - skip if within 5% of target
            tolerance = target_value * 0.05
            if abs(value_to_buy) < tolerance:
                print(f"\n{symbol}: At target (${current_value:,.2f} â‰ˆ ${target_value:,.2f}, within 5%)")
                continue
            
            if value_to_buy < 0:
                # We're overweight - should have been handled in sell step
                print(f"\n{symbol}: Overweight (${current_value:,.2f} > ${target_value:,.2f}) - should have sold above")
                continue
            
            # Calculate shares to buy
            price = self.get_current_price(symbol)
            if price <= 0:
                price = APPROX_PRICES.get(symbol, 50)  # Fallback to approx
            
            shares_to_buy = int(value_to_buy / price)
            
            if shares_to_buy <= 0:
                print(f"\n{symbol}: Cannot afford additional shares (need ${value_to_buy:.2f}, price ${price:.2f})")
                continue
            
            # Check affordability
            cost = shares_to_buy * price
            if cost > available_cash:
                # Reduce shares to what we can afford
                shares_to_buy = int(available_cash * 0.95 / price)
                if shares_to_buy <= 0:
                    print(f"\n{symbol}: Insufficient cash (need ${cost:.2f}, have ${available_cash:.2f})")
                    continue
                cost = shares_to_buy * price
            
            print(f"\nBuying {shares_to_buy} shares of {symbol} @ ~${price:.2f} = ${cost:.2f}...")
            execution = self._execute_buy(
                symbol=symbol,
                quantity=shares_to_buy,
                reason=f"Target allocation: {data['weight']*100:.0f}% {symbol}"
            )
            if execution:
                executions.append(execution)
                available_cash -= cost
        
        self.trade_history.extend(executions)
        
        print("\n" + "-" * 40)
        print(f"Trades Executed: {len(executions)}")
        for trade in executions:
            print(f"  {trade.action} {trade.quantity} {trade.symbol} @ ${trade.price:.2f}")
        print("=" * 60)
        
        return executions


class PaperTradingExecutor(TradingExecutor):
    """
    Paper trading executor for testing without real money
    Simulates account state and order execution
    """
    
    def __init__(
        self,
        initial_cash: float = 100000.0,
        data_fetcher = None
    ):
        """
        Initialize paper trading executor
        
        Args:
            initial_cash: Starting cash balance
            data_fetcher: DataFetcher for getting prices
        """
        self.cash = initial_cash
        self.initial_cash = initial_cash
        self.positions: Dict[str, Position] = {}
        self.data_fetcher = data_fetcher
        self.trade_history: List[TradeExecution] = []
        self.current_position: Optional[str] = None
        self.dry_run = False  # Paper trading executes "real" paper trades
        self.allocation_pct = 0.95  # Use 95% of cash
        self.max_position_value = None  # No limit for paper trading
        self.allow_margin = False
    
    def get_account_value(self) -> float:
        """Get total account value"""
        total = self.cash
        for position in self.positions.values():
            if self.data_fetcher:
                price = self.data_fetcher.get_current_price(position.symbol)
                position.update_price(price)
            total += position.market_value
        return total
    
    def get_cash_balance(self) -> float:
        """Get available cash"""
        return self.cash
    
    def get_positions(self) -> Dict[str, Position]:
        """Get current positions"""
        return self.positions.copy()
    
    def get_current_price(self, symbol: str) -> float:
        """Get current price"""
        if self.data_fetcher:
            return self.data_fetcher.get_current_price(symbol)
        return 0.0
    
    def get_margin_status(self) -> dict:
        """Paper trading has no margin"""
        return {
            'account_type': 'PAPER',
            'cash_balance': self.cash,
            'buying_power': self.cash,
            'margin_balance': 0,
            'available_funds': self.cash,
            'available_funds_non_margin': self.cash,
        }
    
    def verify_no_margin_used(self) -> bool:
        """Paper trading never uses margin"""
        print("\n--- MARGIN SAFETY CHECK ---")
        print("Account Type: PAPER (simulated)")
        print(f"Cash Balance: ${self.cash:,.2f}")
        print("Margin Balance: $0.00 (N/A for paper)")
        print("âœ… Paper trading - no margin possible")
        print("----------------------------")
        return True
    
    def validate_trade_safety(self, symbol: str, quantity: int, action: str) -> tuple:
        """Paper trading validation - just check cash"""
        if action == "BUY":
            price = self.get_current_price(symbol)
            total_cost = quantity * price
            if total_cost > self.cash:
                return False, f"Insufficient cash: need ${total_cost:.2f}, have ${self.cash:.2f}"
            return True, "Paper trade validated"
        return True, "Sell validated"

    def _execute_buy(self, symbol: str, quantity: int, reason: str) -> Optional[TradeExecution]:
        """Execute paper buy"""
        price = self.get_current_price(symbol)
        cost = quantity * price
        
        if cost > self.cash:
            print(f"  âœ— Insufficient funds: need ${cost:.2f}, have ${self.cash:.2f}")
            return None
        
        self.cash -= cost
        
        if symbol in self.positions:
            pos = self.positions[symbol]
            total_cost = (pos.quantity * pos.avg_cost) + cost
            pos.quantity += quantity
            pos.avg_cost = total_cost / pos.quantity
        else:
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=quantity,
                avg_cost=price,
                current_price=price,
                market_value=cost
            )
        
        execution = TradeExecution(
            timestamp=datetime.now(),
            action="BUY",
            symbol=symbol,
            quantity=quantity,
            price=price,
            reason=reason,
            order_id=f"PAPER-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        
        print(f"  âœ“ [PAPER] Bought {quantity} {symbol} @ ${price:.2f} = ${cost:.2f}")
        return execution
    
    def _execute_sell(self, symbol: str, quantity: int, reason: str) -> Optional[TradeExecution]:
        """Execute paper sell"""
        if symbol not in self.positions or self.positions[symbol].quantity < quantity:
            print(f"  âœ— Insufficient shares to sell")
            return None
        
        price = self.get_current_price(symbol)
        proceeds = quantity * price
        
        self.cash += proceeds
        self.positions[symbol].quantity -= quantity
        
        if self.positions[symbol].quantity == 0:
            del self.positions[symbol]
        
        execution = TradeExecution(
            timestamp=datetime.now(),
            action="SELL",
            symbol=symbol,
            quantity=quantity,
            price=price,
            reason=reason,
            order_id=f"PAPER-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        
        print(f"  âœ“ [PAPER] Sold {quantity} {symbol} @ ${price:.2f} = ${proceeds:.2f}")
        return execution
    
    def print_portfolio_summary(self):
        """Print current portfolio state"""
        print("\n" + "=" * 50)
        print("PAPER PORTFOLIO SUMMARY")
        print("=" * 50)
        print(f"Cash: ${self.cash:,.2f}")
        print(f"\nPositions:")
        for symbol, pos in self.positions.items():
            print(f"  {symbol}: {pos.quantity} shares @ ${pos.current_price:.2f} = ${pos.market_value:,.2f}")
        print(f"\nTotal Value: ${self.get_account_value():,.2f}")
        print(f"P/L: ${self.get_account_value() - self.initial_cash:,.2f} ({((self.get_account_value() / self.initial_cash) - 1) * 100:.2f}%)")
        print("=" * 50)
    
    def execute_rebalance(self, state: StrategyState) -> List[TradeExecution]:
        """
        Execute paper rebalance based on strategy signal
        """
        original_signal = state.signal
        executions = []
        
        print("\n" + "=" * 60)
        print("PAPER TRADE EXECUTION")
        print("=" * 60)
        print(f"Strategy Signal: {original_signal.value}")
        
        # Get current state
        account_value = self.get_account_value()
        target_allocation = account_value * self.allocation_pct
        
        print(f"Account Value: ${account_value:,.2f}")
        print(f"Target Allocation: ${target_allocation:,.2f}")
        print(f"Current Positions: {list(self.positions.keys())}")
        
        # SMALL ACCOUNT CHECK: Can we afford the signal?
        affordable_signal, affordability_reason = self.find_affordable_signal(
            state.signal, target_allocation
        )
        
        if affordable_signal is None:
            print(f"\nðŸš¨ Cannot afford ANY signal with ${target_allocation:.2f}")
            print("ðŸš¨ Please add more funds (minimum ~$15 for PDBC)")
            return executions
        
        if affordable_signal != state.signal:
            print(f"\nðŸ“‰ SMALL ACCOUNT ADJUSTMENT:")
            print(f"   Original signal: {state.signal.value}")
            print(f"   Affordable signal: {affordable_signal.value}")
            print(f"   Reason: {affordability_reason}")
            target_symbol = affordable_signal.value
        else:
            target_symbol = state.signal.value
        
        # Check if we need to rebalance
        current_holdings = [s for s, p in self.positions.items() if p.quantity > 0 and s in [sig.value for sig in Signal]]
        
        if target_symbol in current_holdings and len(current_holdings) == 1:
            print(f"\nâœ“ Already holding {target_symbol}, no rebalance needed")
            return executions
        
        # STEP 1: Sell existing strategy positions
        for symbol, position in list(self.positions.items()):
            if symbol in [sig.value for sig in Signal] and symbol != target_symbol:
                if position.quantity > 0:
                    print(f"\nSelling {position.quantity} shares of {symbol}...")
                    execution = self._execute_sell(
                        symbol=symbol,
                        quantity=position.quantity,
                        reason=f"Rebalance: {symbol} â†’ {target_symbol}"
                    )
                    if execution:
                        executions.append(execution)
        
        # STEP 2: Buy target position
        price = self.get_current_price(target_symbol)
        if price > 0:
            shares_to_buy = int((self.cash * 0.99) / price)  # Leave 1% buffer
            
            if shares_to_buy > 0:
                print(f"\nBuying {shares_to_buy} shares of {target_symbol}...")
                execution = self._execute_buy(
                    symbol=target_symbol,
                    quantity=shares_to_buy,
                    reason=f"Strategy signal: {target_symbol}"
                )
                if execution:
                    executions.append(execution)
            else:
                print(f"\nâš ï¸ Cannot afford any shares of {target_symbol} at ${price:.2f}")
        
        self.current_position = target_symbol
        self.trade_history.extend(executions)
        
        print("\n" + "-" * 40)
        print(f"Trades Executed: {len(executions)}")
        for trade in executions:
            print(f"  {trade.action} {trade.quantity} {trade.symbol} @ ${trade.price:.2f}")
        print("=" * 60)
        
        return executions
    
    def find_affordable_signal(self, original_signal: Signal, cash_available: float) -> tuple:
        """Find affordable alternative for paper trading"""
        original_price = APPROX_PRICES.get(original_signal.value, 100)
        
        if cash_available >= original_price * 1.05:
            return original_signal, "Original signal affordable"
        
        print(f"\nâš ï¸  ${cash_available:.2f} cannot buy {original_signal.value} (~${original_price})")
        print("   Looking for affordable alternatives...")
        
        affordable = []
        for signal in Signal:
            price = APPROX_PRICES.get(signal.value, 999)
            if cash_available >= price * 1.05:
                affordable.append((signal, price))
        
        if not affordable:
            return None, f"No affordable signals with ${cash_available:.2f}"
        
        affordable.sort(key=lambda x: x[1])
        best = affordable[0]
        print(f"   âœ“ Falling back to {best[0].value} (~${best[1]})")
        return best[0], "Cheapest affordable alternative"
