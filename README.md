# SectorSBITrader 🎯

A sector rotation trading strategy that uses **parent signals** (sector ETFs, BTC, GLD, etc.) to determine timing, then **drills into individual stocks** using the **Signal Bullish Index (SBI)** for position selection.

## 🚀 Quick Start

```bash
# Install dependencies
pip install yfinance pandas numpy

# Run daily signal generation
python main.py

# Scan all sectors
python main.py --scan

# Scan specific sector
python main.py --sector BTC-USD

# Run backtest
python main.py --backtest --start 2023-01-01 --end 2024-12-31

# List available sectors
python main.py --list-sectors
```

## 📊 Strategy Overview

### Core Concept

```
┌─────────────────────────────────────────────────────────────────┐
│                      STRATEGY FLOW                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. CHECK PARENT SIGNAL (Sector ETF / Asset)                    │
│     └── Is BTC-USD > PSAR? → Bullish                           │
│     └── Is XLK > PSAR? → Bullish                               │
│                                                                 │
│  2. IF PARENT BULLISH → SCAN CHILD STOCKS                       │
│     └── Calculate SBI (0-10) for each stock                    │
│     └── SBI = 10 → Enter with 2x weight                        │
│     └── SBI = 9  → Enter with 1x weight                        │
│     └── SBI < 9  → No entry                                    │
│                                                                 │
│  3. LOCK WEIGHTS UNTIL PARENT TURNS BEARISH                     │
│     └── Keep 2x weight even if SBI drops to 7                  │
│     └── Don't add more even if SBI stays at 10                 │
│                                                                 │
│  4. EXIT WHEN PARENT TURNS BEARISH                              │
│     └── Exit ALL positions in that sector                      │
│     └── Don't exit on individual stock signals                 │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Signal Bullish Index (SBI)

A 10-point scoring system measuring how bullish a stock is:

| # | Indicator | Bullish Condition |
|---|-----------|-------------------|
| 1 | SMA(20) | Price > SMA(20) |
| 2 | SMA(50) | Price > SMA(50) |
| 3 | SMA(200) | Price > SMA(200) |
| 4 | RSI(14) | RSI > 50 |
| 5 | RSI(14) | RSI < 70 (not overbought) |
| 6 | MACD | MACD > Signal Line |
| 7 | MACD Histogram | Histogram > 0 |
| 8 | PSAR | Price > PSAR |
| 9 | Momentum | 20-day return > 0% |
| 10 | Volume | Volume > 20-day avg |

**Entry Requirements:**
- SBI = 10 → 2x weight multiplier
- SBI = 9 → 1x weight multiplier
- SBI < 9 → No entry

## 📁 Project Structure

```
SectorSBITrader/
├── config.py           # Configuration and sector mappings
├── sbi_calculator.py   # SBI calculation logic
├── strategy.py         # Main strategy implementation
├── data_fetcher.py     # Data retrieval (yfinance)
├── backtester.py       # Historical simulation
├── main.py             # CLI entry point
└── README.md           # This file
```

## 🗂️ Sector Mappings

### Crypto (Parent: BTC-USD, ETH-USD, SOL-USD)
| Parent | Child Stocks |
|--------|--------------|
| BTC-USD | MSTR, MARA, XXI, MTPLF, COIN, CLSK |
| ETH-USD | BMNR, SBET, FETH |
| SOL-USD | FSOL |

### Precious Metals (Parent: GLD, SLV)
| Parent | Child Stocks |
|--------|--------------|
| GLD | GDX, AU, KGC, HMY, AEM, GFI, NEM, GOLD, WPM, FNV |
| SLV | PAAS, AG, HL, CDE, MAG, FSM |

### S&P 500 Sectors
| Parent | Description | Sample Stocks |
|--------|-------------|---------------|
| XLK | Technology | AAPL, MSFT, NVDA, AVGO... |
| XLF | Financials | JPM, V, MA, BAC... |
| XLV | Healthcare | LLY, UNH, JNJ, ABBV... |
| XLY | Consumer Disc | AMZN, TSLA, HD, MCD... |
| XLC | Comm Services | META, GOOGL, NFLX, DIS... |
| XLI | Industrials | GE, CAT, RTX, UNP... |
| XLP | Staples | PG, KO, PEP, COST... |
| XLE | Energy | XOM, CVX, COP, SLB... |
| XLU | Utilities | NEE, SO, DUK, CEG... |
| XLRE | Real Estate | PLD, AMT, EQIX, WELL... |
| XLB | Materials | LIN, SHW, APD, FCX... |

### Industries
| Parent | Description | Sample Stocks |
|--------|-------------|---------------|
| SMH | Semiconductors | NVDA, TSM, AVGO, AMD... |
| IBB | Biotech | VRTX, AMGN, GILD, REGN... |
| KRE | Regional Banks | HBAN, RF, CFG, KEY... |
| XHB | Homebuilders | DHI, LEN, NVR, PHM... |
| URA | Nuclear/Uranium | CCJ, CEG, VST, SMR... |

### International
| Parent | Country | Sample Stocks |
|--------|---------|---------------|
| FXI | China | BABA, JD, PDD, BIDU... |
| EWJ | Japan | TM, SONY, MUFG... |
| INDA | India | INFY, WIT, HDB, IBN... |
| EWZ | Brazil | VALE, PBR, ITUB... |
| EEM | Emerging | TSM, BABA, VALE... |

## ⚙️ Configuration

Edit `config.py` to customize:

```python
@dataclass
class StrategyConfig:
    # SBI Entry Thresholds
    sbi_10_weight: float = 2.0    # Weight for SBI=10
    sbi_9_weight: float = 1.0     # Weight for SBI=9
    
    # Position Management
    max_stocks_per_sector: int = 10
    max_total_positions: int = 50
    
    # Sector Allocations
    sector_allocations = {
        'crypto': 0.25,           # 25% to crypto
        'precious_metals': 0.20,  # 20% to gold/silver
        'sp500_sectors': 0.30,    # 30% to S&P sectors
        'industries': 0.15,       # 15% to industries
        'international': 0.10,    # 10% to international
    }
```

## 🔄 Workflow Example

### Day 1: BTC-USD turns bullish
```
Parent Signal: BTC-USD > PSAR → BULLISH

Scanning child stocks:
  MSTR: SBI = 10 → ENTER (2x weight)
  COIN: SBI = 9  → ENTER (1x weight)
  MARA: SBI = 7  → SKIP
  CLSK: SBI = 8  → SKIP
```

### Day 15: Market volatile but BTC still bullish
```
Parent Signal: BTC-USD still > PSAR → HOLD

Current positions:
  MSTR: Keep 2x weight (even if SBI dropped to 8)
  COIN: Keep 1x weight
```

### Day 30: BTC-USD turns bearish
```
Parent Signal: BTC-USD < PSAR → EXIT ALL

Action: Sell MSTR, COIN
       (Exit entire Bitcoin sector)
```

## 🔐 Schwab Integration

Set environment variables:

```bash
export SCHWAB_SBI_APP_KEY="your_app_key"
export SCHWAB_SBI_APP_SECRET="your_app_secret"
export SCHWAB_SBI_ACCOUNT_HASH="your_account_hash"
```

## 📈 Backtest

```bash
# Full backtest
python main.py --backtest

# Custom date range
python main.py --backtest --start 2023-01-01 --end 2024-12-31
```

Output includes:
- Total Return & CAGR
- Max Drawdown
- Sharpe & Sortino Ratios
- Win Rate & Profit Factor
- Comparison to SPY buy & hold

## 🔗 Related Projects

- **AdaptiveX2** (DippyQutie) - ETF-based momentum strategy
- This project extends the concept to individual stocks

## 📝 Key Differences from AdaptiveX2

| Feature | AdaptiveX2 | SectorSBITrader |
|---------|------------|-----------------|
| Instruments | ETFs (QLD, BITU...) | Individual stocks |
| Signal Source | Direct PSAR | Parent ETF PSAR |
| Entry Criteria | PSAR bullish | Parent bullish + SBI ≥ 9 |
| Exit Rule | Individual PSAR | Parent turns bearish |
| Leverage | 2x ETFs | 1x stocks (no leverage) |
| Weight Logic | Momentum-based | SBI score (2x/1x) |

---

*Built as a separate trading bot from AdaptiveX2*
*Designed for a dedicated Schwab account*
