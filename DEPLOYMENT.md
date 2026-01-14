# AdaptiveX2 SectorBot Deployment Guide

## Overview

SectorBot is a sector rotation strategy that:
- Trades individual stocks based on parent ETF signals
- Uses PSAR + RSI + SBI (10-point scale) for entries/exits
- Rotates within sectors to stronger stocks
- **Small Account Mode (Default):** 10 positions max, 2-3 per sector
- **Large Account Mode:** 20 positions max, 5 per sector

## Performance (Backtested)

| Year | SectorBot | SPY | QQQ | vs SPY | vs QQQ |
|------|-----------|-----|-----|--------|--------|
| 2022 | +45% | -19% | -33% | **+64%** | **+79%** |
| 2023 | +70% | +27% | +56% | **+43%** | **+15%** |
| 2024 | +114% | +26% | +28% | **+88%** | **+86%** |

Max Drawdown: ~5% (vs SPY ~25%, QQQ ~35%)

---

## Local Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Test Signal Generation

```bash
# Small account (default) - 10 positions
python main.py --signal-only

# Large account - 20 positions
python main.py --signal-only --large
```

### 3. Generate Patreon Report

```bash
python main.py --report
# Creates: sectorbot_report.jsx
```

---

## Schwab API Setup (For Live Trading)

### 1. Create Schwab Developer App

1. Go to https://developer.schwab.com
2. Create a new app
3. Note your **App Key** and **App Secret**
4. Set callback URL to: `https://127.0.0.1:8182/callback`

### 2. Set Environment Variables

For SectorBot (separate account from main AdaptiveX2):

```bash
export SCHWAB_SECTORBOT_APP_KEY="your_app_key"
export SCHWAB_SECTORBOT_APP_SECRET="your_app_secret"
export SCHWAB_SECTORBOT_ACCOUNT_HASH="your_account_hash"  # Optional
```

Or use a `.env` file:

```
SCHWAB_SECTORBOT_APP_KEY=your_app_key
SCHWAB_SECTORBOT_APP_SECRET=your_app_secret
SCHWAB_SECTORBOT_ACCOUNT_HASH=your_account_hash
```

### 3. First-Time Authentication

```bash
# This will open a browser for OAuth
python main.py --live

# Token saved to: sectorbot_token.json
```

### 4. Live Trading

```bash
# Dry run (shows what would trade)
python main.py --live

# REAL TRADES
python main.py --live --execute
```

---

## GitHub Actions Setup

### 1. Add Repository Secrets

Go to Settings → Secrets → Actions and add:

| Secret | Description |
|--------|-------------|
| `SCHWAB_SECTORBOT_APP_KEY` | Schwab API app key |
| `SCHWAB_SECTORBOT_APP_SECRET` | Schwab API app secret |
| `SCHWAB_SECTORBOT_ACCOUNT_HASH` | Account hash (optional) |
| `SCHWAB_SECTORBOT_TOKEN` | Base64 encoded token JSON |
| `SMTP_SERVER` | Email server (for reports) |
| `SMTP_PORT` | Email port |
| `SMTP_USERNAME` | Email username |
| `SMTP_PASSWORD` | Email password |
| `EMAIL_TO` | Your email address |

### 2. Encode Token for Secret

```bash
# After first local auth, encode the token
cat sectorbot_token.json | base64 -w 0
# Copy output to SCHWAB_SECTORBOT_TOKEN secret
```

### 3. Manual Workflow Dispatch

Go to Actions → SectorBot Trading → Run workflow

Options:
- **Mode:** signal-only, live-dry-run, live-execute
- **Account Size:** small (10 pos), large (20 pos)
- **Generate Report:** true/false

### 4. Scheduled Runs

Default schedule: 9:30 AM ET weekdays
- Generates signals
- Executes trades (small account)
- Emails JSX report

---

## File Structure

```
AdaptiveX2_SectorBot/
├── main.py                 # Main entry point
├── strategy.py             # SectorBot strategy logic
├── config.py               # Sector definitions (28 sectors)
├── sbi_calculator.py       # SBI score calculation
├── sectorbot_executor.py   # Schwab trade execution
├── synthetic_etf.py        # Synthetic ETF generation
├── meme_holdings.py        # Dynamic meme stock scraper
├── backtester.py           # Backtesting engine
├── backtester_boosted.py   # Enhanced backtester
├── requirements.txt        # Python dependencies
├── sectorbot_token.json    # Schwab OAuth token (local only)
└── .github/
    └── workflows/
        └── sectorbot.yml   # GitHub Actions workflow
```

---

## Usage Examples

```bash
# Daily signal check
python main.py

# Generate report for Patreon
python main.py --report

# Live trading dry run
python main.py --live

# EXECUTE REAL TRADES
python main.py --live --execute

# Large account mode
python main.py --live --execute --large

# CI/CD automation
python main.py --live --execute --auto-confirm
```

---

## Sectors (28 Total)

| Category | Parent ETFs |
|----------|-------------|
| **Technology** | QQQ, SMH, XLK |
| **Crypto** | IBIT, FETH, SOLQ, MEME |
| **Precious Metals** | GLD, SLV, GDX |
| **Energy** | XLE, URA |
| **International** | FXI, EWJ, INDA, EWZ, EEM |
| **Financials** | XLF, KRE |
| **Consumer** | XLC, XLY, XHB |
| **Industrials** | XLI |
| **Healthcare** | XLV |
| **AI Infrastructure** | TCAI |

---

## Troubleshooting

### Rate Limiting (429 Errors)

The bot includes 0.5s delays between API calls. If still hitting limits:
```python
# In main.py, increase delay
API_DELAY_SECONDS = 1.0
```

### Token Expired

```bash
# Delete old token and re-authenticate
rm sectorbot_token.json
python main.py --live
```

### Missing Sectors

If MEME or TCAI not generating signals:
```bash
# Check synthetic ETF generation
python -c "from synthetic_etf import fill_synthetic_etfs_from_holdings; print('OK')"
```

---

## Support

- **Patreon:** https://patreon.com/yourpage
- **Discord:** https://discord.gg/yourserver
- **Email:** your@email.com
