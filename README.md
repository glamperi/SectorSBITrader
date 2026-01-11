# AdaptiveX2 SectorBot

Sector rotation strategy that trades ETF sectors and their top stocks.

## Performance (Backtested)

| Year | Market | Rotation (3-Day) | vs SPY |
|------|--------|------------------|--------|
| 2023-2025 | Bull | +83.5% | +40% better |
| 2022 | Bear | +13.6% | +33% better |
| 2018 | Choppy | +3.2% | +9% better |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run signals (default: rotation mode)
python main.py

# Different modes
python main.py --mode rotation          # Default - rotate weak stocks
python main.py --mode parent_based      # Hold through weakness
python main.py --mode weighted_rotation # Rotation + sector weighting

# Large account (20 positions instead of 10)
python main.py --large

# Schwab live trading
python main.py --live                   # Dry run (no real trades)
python main.py --live --execute         # REAL trades!
```

## Trading Workflow (3-Day Frequency)

Based on backtesting, checking signals every 3 days gives optimal results:

**Monday, Wednesday, Friday:**
1. Run `python main.py`
2. Execute EXIT signals first
3. Execute ROTATION signals (sell → buy)
4. Execute ENTRY signals if you have open slots

## Strategy Rules (Rotation Mode)

**Entry:**
- Parent ETF PSAR bullish
- Stock SBI ≥ 9
- Stock PSAR bullish
- Stock RSI > 50

**Exit:**
- Parent ETF PSAR turns bearish → EXIT all stocks in sector
- Stock PSAR bearish OR RSI < 40 → ROTATE to stronger stock

**Position Limits (Small Account):**
- Max 10 positions total
- Max 2 per sector

## GitHub Actions Setup

### 1. Fork/Clone Repository

### 2. Schwab API Setup (for automated trading)

1. Go to [Schwab Developer Portal](https://developer.schwab.com)
2. Create an app and get your API credentials
3. Add these secrets in GitHub → Settings → Secrets:

| Secret | Description |
|--------|-------------|
| `SCHWAB_SECTORBOT_APP_KEY` | Your Schwab API app key |
| `SCHWAB_SECTORBOT_APP_SECRET` | Your Schwab API app secret |
| `SCHWAB_SECTORBOT_ACCOUNT_HASH` | Your account hash (optional) |
| `SCHWAB_SECTORBOT_TOKEN` | OAuth token (created after first auth) |

### 3. First-Time Schwab Authentication

Run locally once to generate the OAuth token:

```bash
python -c "
from schwab import auth
import os

# Replace with your credentials
APP_KEY = 'your_app_key'
APP_SECRET = 'your_app_secret'
CALLBACK_URL = 'https://127.0.0.1:8182'

# This opens a browser for OAuth
client = auth.client_from_manual_flow(APP_KEY, APP_SECRET, CALLBACK_URL, 'sectorbot_token.json')
print('Token saved to sectorbot_token.json')
"
```

Then copy the token contents to the `SCHWAB_SECTORBOT_TOKEN` secret.

### 4. Optional: Email Notifications

| Secret | Description | Example |
|--------|-------------|---------|
| `SMTP_SERVER` | Email server | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` |
| `SMTP_USERNAME` | Your email | `you@gmail.com` |
| `SMTP_PASSWORD` | App password | (use Gmail app password) |
| `EMAIL_TO` | Recipient email | `you@gmail.com` |

### 5. Schedule

Default: Runs Mon/Wed/Fri at 9:30 AM ET (market open)

- **Scheduled runs**: Automatically execute trades via Schwab
- **Manual runs**: Choose signal-only, dry-run, or live-execute

## Account Size Recommendations

| Account Size | Mode | Max Positions | Per Stock |
|--------------|------|---------------|-----------|
| $1,000 | Small | 10 | $100 each |
| $5,000 | Small | 10 | $500 each |
| $10,000+ | Large | 20 | $500 each |

**$1,000 will work** but positions will be small ($100 each). Consider:
- Using fewer positions manually (5-6 instead of 10)
- Waiting until you have $2-3K for better diversification
- Commission-free broker is essential at this size

## Files

| File | Purpose |
|------|---------|
| `main.py` | Run signals and live trading |
| `strategy.py` | Core strategy logic |
| `config.py` | Sector/stock mappings |
| `executor.py` | Schwab API integration |
| `backtester.py` | Backtest strategies |
| `sectorbot_signals.json` | Output signals |

## Backtesting

```bash
# Test different frequencies
python backtester.py --start 2023-01-01 --end 2025-12-31 --small-account --trade-freq 3

# Test specific year
python backtester.py --start 2022-01-01 --end 2022-12-31 --small-account

# Options
--trade-freq N    # Trade every N days (1=daily, 3=recommended, 5=weekly)
--small-account   # 10 positions max
--realistic       # Use next-day open for entries
```

## FAQ

**Q: Why 3-day frequency?**
A: Backtests show similar returns to daily with less work and slippage.

**Q: Which mode should I use?**
A: `rotation` for most markets. `parent_based` if you want less trading.

**Q: Can I use this with Fidelity?**
A: Yes! Run `python main.py` for signals, execute trades manually in Fidelity.

**Q: How do I replicate Schwab trades in Fidelity?**
A: Check the signals output after each run and manually place the same trades.

**Q: What if I miss a day?**
A: Run it when you can. The strategy is forgiving - missing one signal day won't ruin returns.
