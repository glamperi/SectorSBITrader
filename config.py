"""
SectorSBITrader Configuration

Schwab API credentials and strategy settings.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# =============================================
# SCHWAB API CONFIGURATION
# =============================================
# Set these via environment variables for security
SCHWAB_APP_KEY = os.getenv('SCHWAB_SBI_APP_KEY', '')
SCHWAB_APP_SECRET = os.getenv('SCHWAB_SBI_APP_SECRET', '')
SCHWAB_ACCOUNT_HASH = os.getenv('SCHWAB_SBI_ACCOUNT_HASH', '')
SCHWAB_REFRESH_TOKEN = os.getenv('SCHWAB_SBI_REFRESH_TOKEN', '')

# Token file location
TOKEN_FILE = os.path.expanduser('~/.schwab_sbi_tokens.json')

# =============================================
# STRATEGY SETTINGS
# =============================================

@dataclass
class StrategyConfig:
    """Configuration for SectorSBITrader strategy."""
    
    # SBI Entry Thresholds
    sbi_10_weight: float = 2.0  # Weight multiplier for SBI=10 stocks
    sbi_9_weight: float = 1.0   # Weight multiplier for SBI=9 stocks
    min_sbi_for_entry: int = 9  # Minimum SBI score to enter (9 or 10)
    
    # Position Management
    max_stocks_per_sector: int = 10  # Max stocks to scan per sector
    max_total_positions: int = 50    # Max total positions across all sectors
    
    # Exit Rules
    exit_on_parent_bearish: bool = True  # Exit ALL sector positions when parent turns bearish
    lock_weights_until_exit: bool = True  # Keep initial weights even if SBI changes
    
    # Sector Allocation (from AdaptiveX2)
    # These percentages determine how much of portfolio goes to each category
    sector_allocations: Dict[str, float] = field(default_factory=lambda: {
        'crypto': 0.25,      # BTC, ETH, SOL combined
        'precious_metals': 0.20,  # Gold + Silver
        'sp500_sectors': 0.30,    # XLK, XLF, XLV, etc.
        'industries': 0.15,       # SMH, IBB, KRE, etc.
        'international': 0.10,    # FXI, EWJ, INDA, etc.
    })
    
    # Leverage Settings
    use_leverage: bool = False  # Individual stocks = no leverage (1x only)
    
    # Risk Management
    max_position_pct: float = 0.10  # Max 10% in any single stock
    min_position_pct: float = 0.01  # Min 1% position size
    
    # Rebalance Settings
    rebalance_threshold: float = 0.05  # Rebalance if weight drifts 5% from target


# Default configuration
DEFAULT_CONFIG = StrategyConfig()


# =============================================
# PARENT → CHILD STOCK MAPPING
# =============================================
# This maps sector/asset signals to their child stocks

PARENT_CHILD_MAPPING = {
    # =========================================
    # CRYPTO (tied to BTC/ETH/SOL signals)
    # =========================================
    'BTC-USD': {
        'description': 'Bitcoin',
        'category': 'crypto',
        'etf_1x': 'IBIT',
        'etf_2x': 'BITU',
        'stocks': ['MSTR', 'MARA', 'XXI', 'MTPLF', 'COIN', 'CLSK'],
    },
    'ETH-USD': {
        'description': 'Ethereum',
        'category': 'crypto',
        'etf_1x': 'FETH',
        'etf_2x': 'ETHU',
        'stocks': ['BMNR', 'SBET', 'FETH'],
    },
    'SOL-USD': {
        'description': 'Solana',
        'category': 'crypto',
        'etf_1x': 'BSOL',
        'etf_2x': 'SOLT',
        'stocks': ['FSOL'],
    },
    
    # =========================================
    # PRECIOUS METALS (tied to GLD/SLV signals)
    # =========================================
    'GLD': {
        'description': 'Gold',
        'category': 'precious_metals',
        'etf_1x': 'GDX',
        'etf_2x': 'NUGT',
        'stocks': ['GDX', 'AU', 'KGC', 'HMY', 'AEM', 'GFI', 'NEM', 'GOLD', 'WPM', 'FNV'],
    },
    'SLV': {
        'description': 'Silver',
        'category': 'precious_metals',
        'etf_1x': 'SIL',
        'etf_2x': 'AGQ',
        'stocks': ['PAAS', 'AG', 'HL', 'CDE', 'MAG', 'FSM'],
    },
    
    # =========================================
    # S&P 500 SECTORS
    # =========================================
    'XLK': {
        'description': 'Technology',
        'category': 'sp500_sectors',
        'etf_1x': 'XLK',
        'etf_2x': 'USD',
        'stocks': ['AAPL', 'MSFT', 'NVDA', 'AVGO', 'CRM', 'ADBE', 'CSCO', 'ACN', 'ORCL', 'IBM'],
    },
    'XLF': {
        'description': 'Financials',
        'category': 'sp500_sectors',
        'etf_1x': 'XLF',
        'etf_2x': 'UYG',
        'stocks': ['JPM', 'V', 'MA', 'BAC', 'WFC', 'GS', 'MS', 'AXP', 'SPGI', 'BLK'],
    },
    'XLV': {
        'description': 'Healthcare',
        'category': 'sp500_sectors',
        'etf_1x': 'XLV',
        'etf_2x': 'RXL',
        'stocks': ['LLY', 'UNH', 'JNJ', 'ABBV', 'MRK', 'TMO', 'ABT', 'PFE', 'ISRG', 'AMGN'],
    },
    'XLY': {
        'description': 'Consumer Discretionary',
        'category': 'sp500_sectors',
        'etf_1x': 'XLY',
        'etf_2x': 'UCC',
        'stocks': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'LOW', 'SBUX', 'TJX', 'BKNG', 'CMG'],
    },
    'XLC': {
        'description': 'Communication Services',
        'category': 'sp500_sectors',
        'etf_1x': 'XLC',
        'etf_2x': None,  # No 2x available
        'stocks': ['META', 'GOOGL', 'GOOG', 'NFLX', 'DIS', 'CMCSA', 'VZ', 'T', 'TMUS', 'EA'],
    },
    'XLI': {
        'description': 'Industrials',
        'category': 'sp500_sectors',
        'etf_1x': 'XLI',
        'etf_2x': 'UXI',
        'stocks': ['GE', 'CAT', 'RTX', 'UNP', 'HON', 'DE', 'BA', 'LMT', 'UPS', 'MMM'],
    },
    'XLP': {
        'description': 'Consumer Staples',
        'category': 'sp500_sectors',
        'etf_1x': 'XLP',
        'etf_2x': None,  # No 2x available
        'stocks': ['PG', 'KO', 'PEP', 'COST', 'WMT', 'PM', 'MO', 'CL', 'MDLZ', 'KHC'],
    },
    'XLE': {
        'description': 'Energy',
        'category': 'sp500_sectors',
        'etf_1x': 'XLE',
        'etf_2x': 'DIG',
        'stocks': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'HAL'],
    },
    'XLU': {
        'description': 'Utilities',
        'category': 'sp500_sectors',
        'etf_1x': 'XLU',
        'etf_2x': 'UPW',
        'stocks': ['NEE', 'SO', 'DUK', 'CEG', 'SRE', 'AEP', 'D', 'EXC', 'XEL', 'ED'],
    },
    'XLRE': {
        'description': 'Real Estate',
        'category': 'sp500_sectors',
        'etf_1x': 'XLRE',
        'etf_2x': 'URE',
        'stocks': ['PLD', 'AMT', 'EQIX', 'WELL', 'SPG', 'PSA', 'O', 'DLR', 'CCI', 'AVB'],
    },
    'XLB': {
        'description': 'Materials',
        'category': 'sp500_sectors',
        'etf_1x': 'XLB',
        'etf_2x': 'UYM',
        'stocks': ['LIN', 'SHW', 'APD', 'FCX', 'ECL', 'NEM', 'NUE', 'DOW', 'DD', 'VMC'],
    },
    
    # =========================================
    # INDUSTRY ETFs
    # =========================================
    'SMH': {
        'description': 'Semiconductors',
        'category': 'industries',
        'etf_1x': 'SMH',
        'etf_2x': 'USD',
        'stocks': ['NVDA', 'TSM', 'AVGO', 'AMD', 'ASML', 'QCOM', 'TXN', 'LRCX', 'AMAT', 'ADI'],
    },
    'IBB': {
        'description': 'Biotech',
        'category': 'industries',
        'etf_1x': 'IBB',
        'etf_2x': 'BIB',
        'stocks': ['VRTX', 'AMGN', 'GILD', 'REGN', 'BIIB', 'MRNA', 'ILMN', 'ALNY', 'BMRN'],
    },
    'KRE': {
        'description': 'Regional Banks',
        'category': 'industries',
        'etf_1x': 'KRE',
        'etf_2x': None,
        'stocks': ['HBAN', 'RF', 'CFG', 'KEY', 'FITB', 'MTB', 'ZION', 'CMA', 'FHN', 'WAL'],
    },
    'XHB': {
        'description': 'Homebuilders',
        'category': 'industries',
        'etf_1x': 'XHB',
        'etf_2x': None,
        'stocks': ['DHI', 'LEN', 'NVR', 'PHM', 'TOL', 'KBH', 'TMHC', 'MTH', 'MHO', 'MDC'],
    },
    'XOP': {
        'description': 'Oil & Gas Exploration',
        'category': 'industries',
        'etf_1x': 'XOP',
        'etf_2x': 'DIG',
        'stocks': ['XOM', 'CVX', 'COP', 'EOG', 'DVN', 'MRO', 'APA', 'FANG', 'OVV'],
    },
    'ITA': {
        'description': 'Aerospace & Defense',
        'category': 'industries',
        'etf_1x': 'ITA',
        'etf_2x': None,
        'stocks': ['RTX', 'LMT', 'BA', 'NOC', 'GD', 'TDG', 'LHX', 'HII', 'TXT', 'AXON'],
    },
    'URA': {
        'description': 'Nuclear/Uranium',
        'category': 'industries',
        'etf_1x': 'URA',
        'etf_2x': None,
        'stocks': ['CCJ', 'CEG', 'VST', 'SMR', 'LEU', 'NNE', 'DNN', 'OKLO', 'NLR', 'UEC'],
    },
    
    # =========================================
    # INTERNATIONAL
    # =========================================
    'FXI': {
        'description': 'China',
        'category': 'international',
        'etf_1x': 'FXI',
        'etf_2x': 'XPP',
        'stocks': ['BABA', 'JD', 'PDD', 'BIDU', 'NIO', 'XPEV', 'LI', 'NTES', 'TME', 'BILI'],
    },
    'EWJ': {
        'description': 'Japan',
        'category': 'international',
        'etf_1x': 'EWJ',
        'etf_2x': 'EZJ',
        'stocks': ['TM', 'SONY', 'MUFG', 'SMFG', 'HMC', 'NTDOY', 'CAJ'],
    },
    'EWG': {
        'description': 'Germany',
        'category': 'international',
        'etf_1x': 'EWG',
        'etf_2x': 'UPV',
        'stocks': ['SAP', 'SIEGY', 'DB', 'VWAGY', 'BMWYY'],
    },
    'INDA': {
        'description': 'India',
        'category': 'international',
        'etf_1x': 'INDA',
        'etf_2x': 'INDL',
        'stocks': ['INFY', 'WIT', 'HDB', 'IBN', 'RDY', 'TTM'],
    },
    'EWZ': {
        'description': 'Brazil',
        'category': 'international',
        'etf_1x': 'EWZ',
        'etf_2x': 'UBR',
        'stocks': ['VALE', 'PBR', 'ITUB', 'BBD', 'ABEV', 'NU'],
    },
    'EEM': {
        'description': 'Emerging Markets',
        'category': 'international',
        'etf_1x': 'EEM',
        'etf_2x': 'EET',
        'stocks': ['TSM', 'BABA', 'VALE', 'PDD', 'INFY', 'JD', 'NU', 'MELI', 'SE'],
    },
}


def get_all_tickers() -> List[str]:
    """Get all tickers needed for data fetching (parents + children)."""
    tickers = set()
    
    for parent, info in PARENT_CHILD_MAPPING.items():
        tickers.add(parent)
        tickers.add(info['etf_1x'])
        if info.get('etf_2x'):
            tickers.add(info['etf_2x'])
        tickers.update(info['stocks'])
    
    # Add VIX for fear/safety checks
    tickers.add('^VIX')
    tickers.add('VIXM')
    
    return sorted(list(tickers))


def get_parents_by_category(category: str) -> List[str]:
    """Get all parent tickers for a category."""
    return [parent for parent, info in PARENT_CHILD_MAPPING.items() 
            if info['category'] == category]


# Print summary when module is imported
if __name__ == "__main__":
    print("SectorSBITrader Configuration")
    print("=" * 50)
    
    all_tickers = get_all_tickers()
    print(f"\nTotal tickers to track: {len(all_tickers)}")
    
    print("\nParent signals by category:")
    for cat in ['crypto', 'precious_metals', 'sp500_sectors', 'industries', 'international']:
        parents = get_parents_by_category(cat)
        print(f"  {cat}: {', '.join(parents)}")
    
    print(f"\nSector allocations:")
    for cat, alloc in DEFAULT_CONFIG.sector_allocations.items():
        print(f"  {cat}: {alloc*100:.0f}%")
