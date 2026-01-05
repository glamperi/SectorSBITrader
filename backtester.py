"""
SectorSBITrader - Backtester

Simulates the strategy over historical data to evaluate performance.

Key Features:
- Simulates parent signal checks (PSAR)
- Calculates SBI scores for child stocks
- Applies entry/exit rules
- Tracks portfolio value and returns
- Compares to benchmark (SPY buy & hold)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

from config import PARENT_CHILD_MAPPING, DEFAULT_CONFIG, get_all_tickers
from sbi_calculator import SBICalculator, TechnicalIndicators
from strategy import ParentSignal


@dataclass
class BacktestPosition:
    """Position during backtest."""
    ticker: str
    parent: str
    entry_date: datetime
    entry_price: float
    entry_sbi: int
    weight: float  # Position weight in portfolio
    shares: float
    exit_date: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    
    def pnl(self) -> float:
        """Calculate realized P&L."""
        if self.exit_price is None:
            return 0
        return (self.exit_price - self.entry_price) * self.shares
    
    def pnl_pct(self) -> float:
        """Calculate realized P&L percentage."""
        if self.exit_price is None or self.entry_price == 0:
            return 0
        return ((self.exit_price - self.entry_price) / self.entry_price) * 100


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    start_date: datetime
    end_date: datetime
    initial_value: float
    final_value: float
    total_return: float  # Percentage
    cagr: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    
    # Comparison
    benchmark_return: float
    alpha: float
    
    # Time series
    equity_curve: pd.Series
    drawdown_curve: pd.Series
    
    # Trade details
    trades: List[BacktestPosition]
    
    # Daily holdings
    daily_holdings: pd.DataFrame


class Backtester:
    """
    Backtests the SectorSBITrader strategy.
    """
    
    def __init__(self, price_data: Dict[str, pd.Series],
                 volume_data: Dict[str, pd.Series] = None,
                 config=None):
        """
        Args:
            price_data: Dict mapping ticker to price series
            volume_data: Dict mapping ticker to volume series
            config: Strategy configuration
        """
        self.price_data = price_data
        self.volume_data = volume_data or {}
        self.config = config or DEFAULT_CONFIG
        self.sbi_calc = SBICalculator()
        self.indicators = TechnicalIndicators()
    
    def _get_price_on_date(self, ticker: str, date: datetime) -> Optional[float]:
        """Get price for a ticker on a specific date."""
        prices = self.price_data.get(ticker, pd.Series())
        if len(prices) == 0:
            return None
        
        # Find closest date
        try:
            if date in prices.index:
                return float(prices.loc[date])
            
            # Find nearest previous date
            mask = prices.index <= date
            if mask.any():
                nearest = prices.index[mask][-1]
                return float(prices.loc[nearest])
        except:
            pass
        
        return None
    
    def _get_prices_up_to_date(self, ticker: str, date: datetime, lookback: int = 250) -> pd.Series:
        """Get price series up to and including a date."""
        prices = self.price_data.get(ticker, pd.Series())
        if len(prices) == 0:
            return pd.Series()
        
        mask = prices.index <= date
        return prices[mask].tail(lookback)
    
    def _check_parent_signal_on_date(self, parent_ticker: str, date: datetime) -> ParentSignal:
        """Check parent signal on a specific date using PSAR."""
        prices = self._get_prices_up_to_date(parent_ticker, date, 250)
        
        if len(prices) < 50:
            return ParentSignal.UNKNOWN
        
        psar = self.indicators.psar(prices)
        
        if prices.iloc[-1] > psar.iloc[-1]:
            return ParentSignal.BULLISH
        else:
            return ParentSignal.BEARISH
    
    def _calculate_sbi_on_date(self, ticker: str, date: datetime) -> Tuple[int, float]:
        """
        Calculate SBI score for a stock on a specific date.
        
        Returns:
            (sbi_score, weight_multiplier)
        """
        prices = self._get_prices_up_to_date(ticker, date, 250)
        
        if len(prices) < 201:
            return 0, 0.0
        
        # Get volume if available
        volume = None
        if ticker in self.volume_data:
            volume_series = self.volume_data[ticker]
            mask = volume_series.index <= date
            volume = volume_series[mask].tail(250)
        
        result = self.sbi_calc.calculate(ticker, prices, volume)
        return result.sbi_score, result.weight_multiplier
    
    def run(self, start_date: str, end_date: str, initial_capital: float = 10000,
            rebalance_frequency: str = 'daily') -> BacktestResult:
        """
        Run backtest over specified period.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            initial_capital: Starting portfolio value
            rebalance_frequency: 'daily' or 'weekly'
        
        Returns:
            BacktestResult with full analysis
        """
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)
        
        # Get trading days from SPY
        spy_prices = self.price_data.get('SPY', pd.Series())
        if len(spy_prices) == 0:
            raise ValueError("SPY data required for backtest")
        
        trading_days = spy_prices.index[(spy_prices.index >= start) & (spy_prices.index <= end)]
        
        if len(trading_days) == 0:
            raise ValueError(f"No trading days in range {start_date} to {end_date}")
        
        print(f"Running backtest: {start_date} to {end_date}")
        print(f"Trading days: {len(trading_days)}")
        print(f"Initial capital: ${initial_capital:,.2f}")
        print()
        
        # Initialize tracking
        portfolio_value = initial_capital
        cash = initial_capital
        positions: Dict[str, BacktestPosition] = {}  # ticker -> position
        
        equity_curve = []
        daily_holdings_data = []
        all_trades = []
        
        # Track parent signals
        parent_signals: Dict[str, ParentSignal] = {}
        
        # Main simulation loop
        for i, date in enumerate(trading_days):
            # Progress indicator
            if i % 50 == 0:
                print(f"  Processing day {i+1}/{len(trading_days)} ({date.strftime('%Y-%m-%d')})")
            
            # 1. Update current prices and portfolio value
            current_value = cash
            for ticker, pos in positions.items():
                price = self._get_price_on_date(ticker, date)
                if price:
                    current_value += price * pos.shares
            
            # 2. Check for exits (parent signals turning bearish)
            exits_today = []
            for parent_ticker in PARENT_CHILD_MAPPING:
                signal = self._check_parent_signal_on_date(parent_ticker, date)
                prev_signal = parent_signals.get(parent_ticker, ParentSignal.UNKNOWN)
                
                # If parent turned bearish, exit all positions from this sector
                if signal == ParentSignal.BEARISH and prev_signal == ParentSignal.BULLISH:
                    sector_info = PARENT_CHILD_MAPPING[parent_ticker]
                    for stock in sector_info['stocks']:
                        if stock in positions:
                            exits_today.append((stock, parent_ticker))
                
                parent_signals[parent_ticker] = signal
            
            # Process exits
            for ticker, parent in exits_today:
                pos = positions[ticker]
                exit_price = self._get_price_on_date(ticker, date)
                if exit_price:
                    pos.exit_date = date
                    pos.exit_price = exit_price
                    pos.exit_reason = f"Parent {parent} turned bearish"
                    
                    cash += exit_price * pos.shares
                    all_trades.append(pos)
                    del positions[ticker]
            
            # 3. Check for entries (only on rebalance days)
            is_rebalance_day = (rebalance_frequency == 'daily') or (date.weekday() == 0)  # Monday for weekly
            
            if is_rebalance_day and i >= 200:  # Need 200 days of history for SBI
                entries_today = []
                
                for parent_ticker, sector_info in PARENT_CHILD_MAPPING.items():
                    if parent_signals.get(parent_ticker) != ParentSignal.BULLISH:
                        continue
                    
                    # Check each stock in bullish sector
                    for stock in sector_info['stocks']:
                        if stock in positions:
                            continue  # Already have position
                        
                        sbi, weight = self._calculate_sbi_on_date(stock, date)
                        
                        if sbi >= 9:  # Entry signal
                            price = self._get_price_on_date(stock, date)
                            if price and price > 0:
                                entries_today.append((stock, parent_ticker, sbi, weight, price))
                
                # Calculate position sizes and enter
                if entries_today:
                    total_weight = sum(w for _, _, _, w, _ in entries_today)
                    available_cash = cash * 0.95  # Keep 5% cash buffer
                    
                    for stock, parent, sbi, weight, price in entries_today:
                        # Position size based on weight
                        position_value = available_cash * (weight / total_weight) if total_weight > 0 else 0
                        position_value = min(position_value, available_cash * self.config.max_position_pct * 2)
                        
                        if position_value >= 100:  # Minimum position size
                            shares = position_value / price
                            
                            pos = BacktestPosition(
                                ticker=stock,
                                parent=parent,
                                entry_date=date,
                                entry_price=price,
                                entry_sbi=sbi,
                                weight=weight,
                                shares=shares
                            )
                            positions[stock] = pos
                            cash -= position_value
            
            # 4. Record daily state
            holdings = {}
            for ticker, pos in positions.items():
                price = self._get_price_on_date(ticker, date)
                if price:
                    holdings[ticker] = price * pos.shares
            
            daily_holdings_data.append({
                'date': date,
                'portfolio_value': current_value,
                'cash': cash,
                'positions': len(positions),
                **holdings
            })
            
            equity_curve.append({'date': date, 'value': current_value})
        
        # Close any remaining positions at end
        for ticker, pos in positions.items():
            exit_price = self._get_price_on_date(ticker, end)
            if exit_price:
                pos.exit_date = end
                pos.exit_price = exit_price
                pos.exit_reason = "End of backtest"
                all_trades.append(pos)
        
        # Calculate results
        equity_df = pd.DataFrame(equity_curve).set_index('date')
        equity_series = equity_df['value']
        
        final_value = equity_series.iloc[-1]
        total_return = ((final_value - initial_capital) / initial_capital) * 100
        
        # CAGR
        years = (end - start).days / 365.25
        cagr = ((final_value / initial_capital) ** (1/years) - 1) * 100 if years > 0 else 0
        
        # Drawdown
        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max * 100
        max_drawdown = drawdown.min()
        
        # Daily returns
        daily_returns = equity_series.pct_change().dropna()
        
        # Sharpe ratio (assuming 0% risk-free rate)
        sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() > 0 else 0
        
        # Sortino ratio
        downside = daily_returns[daily_returns < 0]
        sortino = (daily_returns.mean() / downside.std()) * np.sqrt(252) if len(downside) > 0 and downside.std() > 0 else 0
        
        # Trade statistics
        winning_trades = [t for t in all_trades if t.pnl() > 0]
        losing_trades = [t for t in all_trades if t.pnl() <= 0]
        
        win_rate = len(winning_trades) / len(all_trades) * 100 if all_trades else 0
        avg_win = np.mean([t.pnl_pct() for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t.pnl_pct() for t in losing_trades]) if losing_trades else 0
        
        total_wins = sum(t.pnl() for t in winning_trades)
        total_losses = abs(sum(t.pnl() for t in losing_trades))
        profit_factor = total_wins / total_losses if total_losses > 0 else 999
        
        # Benchmark (SPY buy & hold)
        spy_start = self._get_price_on_date('SPY', start)
        spy_end = self._get_price_on_date('SPY', end)
        benchmark_return = ((spy_end - spy_start) / spy_start) * 100 if spy_start else 0
        
        alpha = total_return - benchmark_return
        
        # Create result
        result = BacktestResult(
            start_date=start,
            end_date=end,
            initial_value=initial_capital,
            final_value=final_value,
            total_return=total_return,
            cagr=cagr,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            total_trades=len(all_trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            benchmark_return=benchmark_return,
            alpha=alpha,
            equity_curve=equity_series,
            drawdown_curve=drawdown,
            trades=all_trades,
            daily_holdings=pd.DataFrame(daily_holdings_data)
        )
        
        return result
    
    def print_results(self, result: BacktestResult):
        """Print backtest results."""
        print("\n" + "=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        
        print(f"\nPeriod: {result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}")
        print(f"Initial Value: ${result.initial_value:,.2f}")
        print(f"Final Value: ${result.final_value:,.2f}")
        
        print(f"\n{'Metric':<25} {'Strategy':<15} {'SPY B&H':<15}")
        print("-" * 55)
        print(f"{'Total Return':<25} {result.total_return:>13.2f}% {result.benchmark_return:>13.2f}%")
        print(f"{'CAGR':<25} {result.cagr:>13.2f}%")
        print(f"{'Alpha':<25} {result.alpha:>13.2f}%")
        print(f"{'Max Drawdown':<25} {result.max_drawdown:>13.2f}%")
        print(f"{'Sharpe Ratio':<25} {result.sharpe_ratio:>13.2f}")
        print(f"{'Sortino Ratio':<25} {result.sortino_ratio:>13.2f}")
        
        print(f"\n{'Trade Statistics':<25}")
        print("-" * 40)
        print(f"{'Total Trades':<25} {result.total_trades:>10}")
        print(f"{'Winning Trades':<25} {result.winning_trades:>10}")
        print(f"{'Losing Trades':<25} {result.losing_trades:>10}")
        print(f"{'Win Rate':<25} {result.win_rate:>9.1f}%")
        print(f"{'Avg Win':<25} {result.avg_win:>9.2f}%")
        print(f"{'Avg Loss':<25} {result.avg_loss:>9.2f}%")
        print(f"{'Profit Factor':<25} {result.profit_factor:>10.2f}")


if __name__ == "__main__":
    print("SectorSBITrader Backtester")
    print("=" * 50)
    print("\nUsage:")
    print("  from backtester import Backtester")
    print("  from data_fetcher import DataFetcher")
    print()
    print("  fetcher = DataFetcher()")
    print("  price_data, volume_data = fetcher.fetch_all()")
    print()
    print("  bt = Backtester(price_data, volume_data)")
    print("  result = bt.run('2022-01-01', '2024-12-31')")
    print("  bt.print_results(result)")
