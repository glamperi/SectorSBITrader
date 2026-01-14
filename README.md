# AdaptiveX2 SectorBot 🤖📈

A sector rotation trading system that combines **parent ETF PSAR signals** with **child stock SBI scoring** to find high-quality entries in bullish sectors.

## 🎯 Strategy Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  PARENT SIGNAL (Sector/Asset)     CHILD SIGNAL (Individual Stock)│
│  ─────────────────────────────    ───────────────────────────────│
│  BTC-USD PSAR Bullish?            MSTR SBI ≥ 9?                  │
│         │                                │                        │
│         ▼                                ▼                        │
│    ┌─────────┐                    ┌─────────────┐                │
│    │ Sector  │───── YES ─────────▶│ Stock       │                │
│    │ ACTIVE  │                    │ Qualifies   │──▶ BUY MSTR    │
│    └─────────┘                    └─────────────┘                │
│         │                                │                        │
│        NO                               NO                        │
│         │                                │                        │
│         ▼                                ▼                        │
│    EXIT all                         WAIT for                      │
│    sector stocks                    better setup                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Principles

1. **Parent determines exposure** - Only buy stocks when their sector ETF/crypto is PSAR bullish
2. **SBI filters entries** - Only buy stocks with SBI ≥ 9 (high-quality setups)
3. **Volatility-adjusted** - Crypto/meme stocks use relaxed ATR thresholds
4. **Exit on parent breakdown** - Sell all sector stocks when parent turns bearish

## 📊 SBI (Signal Bullish Index) Explained

SBI measures **entry quality** on a 0-10 scale. It's NOT just "is it going up?" but "is this a GOOD time to buy?"

### SBI Components

| Component | What It Measures | Score Range |
|-----------|------------------|-------------|
| **ATR Score** | Volatility (lower = better) | 0-10 |
| **Slope Score** | PSAR gap widening/narrowing | 0-10 |
| **ADX Score** | Trend strength | 0-10 |

### SBI Formula (varies by days in trend)

```
Day 1:     100% ATR Score
Day 2:     80% ATR + 20% Slope
Day 3:     60% ATR + 40% Slope
Days 4-5:  40% ATR + 40% Slope + 20% ADX
Days 6+:   40% Slope + 30% ADX + 30% ATR

PRSI(4) Bearish Penalty: -2 points (Days 3+)
```

### ATR Score (Volatility)

Lower ATR% = Higher score (less volatile = safer entry)

| ATR% (Day 6+) | Score | Interpretation |
|---------------|-------|----------------|
| < 2% | 10 | Very stable |
| < 2.5% | 9 | Stable |
| < 3% | 8 | Good |
| < 4% | 7 | Acceptable |
| < 5% | 6 | Borderline |
| ≥ 5% | 4 | Too volatile |

### Slope Score (Gap Direction)

Positive slope = PSAR gap widening = trend strengthening

| Gap Slope | Score | Interpretation |
|-----------|-------|----------------|
| ≥ +2 | 10 | Strongly widening |
| ≥ +1 | 9 | Widening |
| ≥ +0.5 | 8 | Slightly widening |
| ≥ -0.5 | 7 | Stable |
| ≥ -1 | 5 | Slightly narrowing |
| ≥ -2 | 3 | Narrowing |
| < -2 | 1 | Strongly narrowing |

### ADX Score (Trend Strength)

ADX measures HOW STRONG a trend is (not direction).

| ADX Value | Score | Interpretation |
|-----------|-------|----------------|
| ≥ 40 | 10 | Very strong trend |
| ≥ 30 | 8 | Strong trend |
| ≥ 25 | 6 | Moderate trend |
| ≥ 20 | 4 | Weak trend |
| < 20 | 2 | No trend / Choppy |

**How ADX is calculated:**
```
1. +DM = Today's High - Yesterday's High (if positive & > -DM)
2. -DM = Yesterday's Low - Today's Low (if positive & > +DM)
3. TR = True Range
4. +DI = 100 × (Smoothed +DM / Smoothed TR)
5. -DI = 100 × (Smoothed -DM / Smoothed TR)
6. DX = 100 × |+DI - -DI| / (+DI + -DI)
7. ADX = 14-period EMA of DX
```

## 🔥 Volatility Categories (NEW)

Crypto and meme stocks are inherently more volatile. The SBI calculator now adjusts ATR thresholds by category:

| Category | Tickers | ATR Multiplier | Effect |
|----------|---------|----------------|--------|
| **Crypto** | MSTR, MARA, COIN, RIOT, CLSK, HOOD, etc. | **2.0x** | 6.5% ATR → 3.25% adjusted |
| **Meme** | GME, AMC, PLTR, SOFI, NIO, etc. | **1.75x** | Higher vol accepted |
| **High Vol** | AG, HL, MRNA, TQQQ, etc. | **1.5x** | Junior miners, biotech |
| **Standard** | AAPL, MSFT, etc. | **1.0x** | Normal thresholds |

### Example: MSTR Before/After

**Before (Standard thresholds):**
- Raw ATR: 6.53% → Score 4/10 (penalized)
- SBI = 7

**After (Crypto 2x multiplier):**
- Adjusted ATR: 6.53% ÷ 2.0 = 3.27%
- Adjusted ATR → Score 7-8/10
- SBI = 8

## 🚀 Usage

### Basic Commands

```bash
# Run daily signals (default rotation mode)
python main.py

# Different strategy modes
python main.py --mode rotation          # Rotate weak stocks (default)
python main.py --mode parent_based      # Hold through weakness
python main.py --mode weighted_rotation # Rotation + sector weighting

# Account sizes
python main.py                          # Small account (10 positions, 2/sector)
python main.py --large                  # Large account (20 positions, 5/sector)

# Output options
python main.py --json                   # JSON output only
python main.py --no-save                # Don't save to file
```

### Sector Diagnosis (NEW) 🔬

Diagnose why stocks in a sector aren't qualifying:

```bash
# Diagnose Bitcoin sector
python main.py --sector BTC-USD

# Diagnose other sectors
python main.py --sector GLD            # Gold miners
python main.py --sector XLK            # Technology
python main.py --sector SMH            # Semiconductors

# Short aliases work too
python main.py -s BTC                   # Same as BTC-USD
python main.py -s ETH                   # Same as ETH-USD
```

### Diagnosis Output Example

```
======================================================================
🔍 SECTOR DIAGNOSIS: BTC-USD (Bitcoin)
======================================================================

📊 PARENT SIGNAL: BTC-USD
--------------------------------------------------
   Status:  🟢 BULLISH
   Price:   $97,624.50
   PSAR:    $89,372.01
   Gap:     +9.23%

📋 CHILD STOCK ANALYSIS
----------------------------------------------------------------------
Ticker    SBI     PSAR    RSI Status                   
----------------------------------------------------------------------
MSTR        7   +15.9%     55 ❌ SBI=7<9                
RIOT        8   +22.7%     68 ❌ SBI=8<9                
HOOD      ⭐10    +7.8%     48 ❌ RSI=48<50              

🔬 DETAILED SBI BREAKDOWN
──────────────────────────────────────────────────
📊 MSTR [CRYPTO]: SBI = 7/10
──────────────────────────────────────────────────
   Days in trend: 8
   Formula (Day 8): 40% Slope + 30% ADX + 30% ATR

   Component Scores:
   ├─ ATR Score:   7/10  (Raw ATR% = 6.50% → Adjusted = 3.25%)
   │    └─ CRYPTO stock: 2.0x ATR allowance
   ├─ Slope Score: 10/10  (Gap Slope = +12.79)
   │    └─ Positive slope = gap widening = bullish
   └─ ADX Score:   6/10  (ADX = 26.2)
        └─ Higher ADX = stronger trend

   Calculation: SBI = 0.4×10 + 0.3×6 + 0.3×7 = 7.9

   🔍 Why SBI is low:
      • ADX score low (6) - moderate trend strength
```

### Live Trading (Schwab)

```bash
# Dry run (test without executing)
python main.py --dry-run

# Live trading (with confirmation prompts)
python main.py --live

# Automated (skip prompts)
python main.py --live --auto-confirm
```

### Help

```bash
python main.py --help                   # Show all options
python main.py --usage                  # Show detailed usage examples
```

## 📋 Entry Criteria

All 4 conditions must pass for a stock to qualify:

| # | Criterion | Check |
|---|-----------|-------|
| 1 | Parent PSAR Bullish | Sector ETF/crypto price > PSAR |
| 2 | Stock SBI ≥ 9 | High-quality setup |
| 3 | Stock PSAR Bullish | Stock price > its PSAR |
| 4 | Stock RSI > 50 | Momentum confirmation |

## 🏗️ Sector Mappings

### Crypto
| Parent | Children |
|--------|----------|
| BTC-USD | MSTR, MARA, CLSK, RIOT, COIN, HOOD, BTBT, HUT, CIFR, WULF |
| ETH-USD | COIN, HOOD, SQ, PYPL |
| SOL-USD | (Solana ETFs when available) |

### Precious Metals
| Parent | Children |
|--------|----------|
| GLD | GDX, NEM, GOLD, AEM, KGC, AU, HMY, GFI, WPM, FNV |
| SLV | PAAS, AG, HL, CDE, MAG, FSM |

### S&P 500 Sectors
| Parent | Category | Example Children |
|--------|----------|------------------|
| XLK | Technology | AAPL, MSFT, NVDA, AVGO, CRM |
| XLF | Financials | JPM, BAC, WFC, GS, MS |
| XLV | Healthcare | UNH, JNJ, PFE, ABBV, MRK |
| XLE | Energy | XOM, CVX, COP, EOG, SLB |
| XLI | Industrials | CAT, HON, UNP, BA, RTX |
| XLY | Cons. Disc. | AMZN, TSLA, HD, MCD, NKE |
| XLP | Cons. Staples | PG, KO, PEP, COST, WMT |
| XLU | Utilities | NEE, DUK, SO, D, AEP |
| XLC | Communications | META, GOOGL, NFLX, DIS, VZ |
| XLRE | Real Estate | AMT, PLD, CCI, EQIX, SPG |
| XLB | Materials | LIN, APD, SHW, FCX, NEM |

### Industries & International
| Parent | Category |
|--------|----------|
| SMH | Semiconductors |
| IBB | Biotech |
| KRE | Regional Banks |
| XHB | Homebuilders |
| OIH | Oil Services |
| ITA | Aerospace/Defense |
| FXI | China |
| EWJ | Japan |
| INDA | India |
| EWZ | Brazil |
| EEM | Emerging Markets |

## 📁 Project Structure

```
SectorSBITrader/
├── main.py                      # Entry point with CLI
├── strategy.py                  # AdaptiveX2SectorBot class
├── sbi_calculator.py            # SBI calculation with volatility categories
├── config.py                    # Sector mappings and configuration
├── generate_sectorbot_image_v2.py  # Patreon PNG image generator
├── schwab_auth.py               # Schwab API authentication
├── sectorbot_signals.json       # Latest signals output
└── sectorbot_state.json         # Position tracking (if enabled)
```

## ⚙️ Configuration

### Environment Variables

```bash
# Schwab API (for live trading)
export SCHWAB_SECTORBOT_APP_KEY='your_app_key'
export SCHWAB_SECTORBOT_APP_SECRET='your_app_secret'
export SCHWAB_SECTORBOT_ACCOUNT_HASH='your_account_hash'
```

### Strategy Modes

| Mode | Description | Trading Frequency |
|------|-------------|-------------------|
| `rotation` | Rotate out of weak stocks | Higher (more signals) |
| `parent_based` | Only exit on parent breakdown | Lower (fewer trades) |
| `weighted_rotation` | Rotation + sector weighting | Medium |

## 🔄 Workflow

### Daily Signal Generation

1. Fetch price data for all parents and children
2. Calculate parent PSAR status (bullish/bearish)
3. For each bullish parent:
   - Scan children for SBI ≥ 9
   - Check RSI > 50 and stock PSAR bullish
4. Generate entry/exit/rotation signals
5. Output to console and JSON file

### Trade Execution (Schwab)

1. Run `--dry-run` first to preview trades
2. Run `--live` to execute with confirmation
3. Run `--live --auto-confirm` for automation

## 📈 Example Session

```bash
$ python main.py

======================================================================
🤖 ADAPTIVEX2 SECTORBOT - SMALL (10 pos)
   Time: 2026-01-14 12:00:00
   Mode: ROTATION
======================================================================

📥 Fetching data for 330 tickers...
✅ Loaded 330 tickers

======================================================================
📊 SIGNALS
======================================================================

🟢 ENTRY (3):
   BUY  XOM    (XLE) - SBI=10, RSI=69
   BUY  EOG    (XLE) - SBI=10, RSI=62
   BUY  NEM    (GLD) - SBI=9, RSI=72

📋 SUMMARY
----------------------------------------------------------------------
   Active Sectors:    26
   Entry Signals:     3
   Max Positions:     10

📁 Saved to: sectorbot_signals.json
```

## ⚠️ Disclaimer

This software is for educational purposes only. Trading involves substantial risk of loss. Past performance does not guarantee future results. Always do your own research.

---

## 🎨 Patreon Signal Image Generation

Generate professional PNG images for sharing signals on Patreon:

### Setup

```bash
pip install pillow
```

### Usage

```bash
# Generate sample image (for testing)
python generate_sectorbot_image_v2.py --sample

# Generate from JSON signal file
python generate_sectorbot_image_v2.py --json sectorbot_signals.json

# Custom output filename
python generate_sectorbot_image_v2.py --json sectorbot_signals.json --output daily_signal.png
```

### JSON Input Format

The image generator expects a JSON file with this structure:

```json
{
  "generated_at": "2026-01-14T12:00:00",
  "parent_signals": [
    {
      "parent": "BTC-USD",
      "name": "Bitcoin", 
      "psar_status": "BULLISH",
      "psar_trend_days": 12,
      "psar_gap": 9.23
    },
    {
      "parent": "GLD",
      "name": "Gold",
      "psar_status": "BULLISH", 
      "psar_trend_days": 45,
      "psar_gap": 3.5
    }
  ],
  "entry_signals": [
    {
      "ticker": "XOM",
      "parent": "XLE",
      "sbi": 10,
      "rsi": 69
    }
  ],
  "exit_signals": [
    {
      "ticker": "NVDA",
      "parent": "SMH",
      "reason": "Parent turned bearish"
    }
  ],
  "rotation_signals": [
    {
      "from_ticker": "MARA",
      "to_ticker": "CLSK",
      "parent": "BTC-USD"
    }
  ],
  "target_allocation": [
    {
      "ticker": "MSTR",
      "parent": "BTC-USD",
      "weight": 0.15,
      "sbi": 9,
      "entry_date": "2025-01-02"
    }
  ]
}
```

### Output

The generator creates an 850x1100px PNG image with:
- **Header**: "AdaptiveX2 SectorBot" with date
- **Parent Signals**: Visual cards showing PSAR status (🟢/🔴) + trend days
- **Current Positions**: Table with ticker, parent, weight%, SBI, entry date
- **Entry Signals**: New BUY recommendations
- **Rotation Signals**: Within-sector swaps
- **Exit Signals**: SELL recommendations
- **Strategy Rules**: Quick reference box
- **Disclaimer**: Footer

### GitHub Actions Integration

Add to your workflow to auto-generate and upload:

```yaml
- name: Generate Patreon Image
  run: |
    python main.py --json > sectorbot_signals.json
    python generate_sectorbot_image_v2.py --json sectorbot_signals.json --output signal.png

- name: Upload to Patreon (example)
  run: |
    # Your upload script here
    curl -X POST "https://your-upload-endpoint" -F "file=@signal.png"
```

---

**Built with 🧠 by Gary & Claude**
