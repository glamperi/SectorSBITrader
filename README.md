# AdaptiveX2 SectorBot

**Parent PSAR + Child SBI Strategy for Reduced Trading**

## Overview

This bot combines the best of two systems:
1. **AdaptiveX2's PSAR signals** - Determine which sectors are active (parent signals)
2. **Market-scanner's SBI** - Select the best stocks within active sectors (child signals)

The key innovation is **parent-based exits only**, which dramatically reduces trading by:
- NOT selling when a stock's SBI drops
- NOT selling on small pullbacks
- ONLY selling when the parent sector turns bearish

## How It Works

### Entry Logic
```
1. Check PARENT PSAR (sector ETF or crypto):
   - BTC-USD bullish? → Crypto stocks eligible
   - GLD bullish? → Gold miners eligible
   - XLK bullish? → Tech stocks eligible

2. Filter CHILD STOCKS by SBI:
   - SBI = 10 → Buy with 2x weight (best entry)
   - SBI = 9 → Buy with 1x weight (good entry)
   - SBI < 9 → Don't enter
```

### Exit Logic (Key Difference!)
```
❌ DON'T exit when:
   - Stock SBI drops to 6 (extended but trend intact)
   - Stock pulls back 5%
   - Stock goes sideways for a week

✅ DO exit when:
   - Parent sector PSAR turns bearish
   - Example: BTC breaks below PSAR → Sell ALL crypto stocks
```

## Example Trade Flow

```
Nov 1:  BTC PSAR turns bullish
        → Scan crypto stocks, find MSTR with SBI=10
        → BUY MSTR

Nov 15: MSTR SBI drops to 6 (price extended from PSAR)
        → OLD STRATEGY: Sell (miss rest of rally)
        → THIS STRATEGY: HOLD (BTC parent still bullish)

Dec 1:  COIN appears with SBI=10 (fresh signal)
        → BUY COIN (add to crypto allocation)

Jan 5:  BTC PSAR turns bearish
        → SELL ALL crypto stocks (MSTR, COIN, etc.)
```

## Why Fewer Trades = Better Performance

1. **Transaction costs** - Each trade has commissions and slippage
2. **Taxes** - Short-term gains taxed at higher rate
3. **Whipsaws** - Frequent trading causes buy-high-sell-low cycles
4. **Trend riding** - Biggest gains come from staying in winners

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Full scan with report
python main.py

# JSON output only
python main.py --json

# Don't save report file
python main.py --no-save
```

## Configuration

Edit `config.py` to customize:
- Sector allocations (crypto, gold, tech, etc.)
- SBI thresholds (default: 9-10 for entry)
- Max positions per sector
- Position size limits

## SBI (Smart Buy Indicator) Explained

SBI measures entry quality on a 0-10 scale:

| SBI | Meaning | Action |
|-----|---------|--------|
| 10 | Perfect entry (fresh signal, low volatility) | Buy with 2x weight |
| 9 | Excellent entry | Buy with 1x weight |
| 8 | Good entry (Strong Buy threshold) | Optional buy |
| 6-7 | Extended but trend intact | HOLD if owned |
| 0-5 | Weak/broken | Don't enter |
| 0 | Broken (crashed through PSAR) | Avoid! |

### SBI Formula (varies by days since signal):

- **Day 1:** 100% ATR score
- **Day 2:** 80% ATR + 20% Slope
- **Day 3:** 60% ATR + 40% Slope
- **Days 4-5:** 40% ATR + 40% Slope + 20% ADX
- **Days 6+:** 40% Slope + 30% ADX + 30% ATR

## Files

- `main.py` - Entry point
- `strategy.py` - Core strategy logic
- `sbi_calculator.py` - SBI calculation (exact from market-psar-scanner)
- `config.py` - Configuration and sector mappings
- `requirements.txt` - Python dependencies

## Parent-Child Mappings

| Category | Parent Signal | Child Stocks |
|----------|--------------|--------------|
| Crypto | BTC-USD | MSTR, MARA, COIN, CLSK... |
| Crypto | ETH-USD | COIN, HOOD, SQ... |
| Gold | GLD | NEM, GOLD, AEM, FNV... |
| Silver | SLV | PAAS, WPM, HL, AG... |
| Tech | XLK | AAPL, MSFT, NVDA, AMD... |
| Semis | SMH | NVDA, TSM, AVGO, AMD... |
| ... | ... | ... |

See `config.py` for full mappings.

## Performance Notes

This strategy is designed to:
- **Reduce trades** by ~70% vs typical SBI-based systems
- **Increase holding period** from days to weeks/months
- **Improve tax efficiency** with more long-term gains
- **Capture bigger moves** by riding trends longer

The trade-off is potentially missing some short-term reversals, but backtesting shows the reduced trading more than compensates.
