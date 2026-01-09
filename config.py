"""
AdaptiveX2 SectorBot Configuration
===================================

Parent PSAR signals control sector activation.
Child stocks are filtered by SBI 9-10 for entry.
Exit ONLY when parent turns bearish (not when SBI drops).
"""

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# =============================================
# SCHWAB API CONFIGURATION
# =============================================
SCHWAB_APP_KEY = os.getenv('SCHWAB_SBI_APP_KEY', '')
SCHWAB_APP_SECRET = os.getenv('SCHWAB_SBI_APP_SECRET', '')
SCHWAB_ACCOUNT_HASH = os.getenv('SCHWAB_SBI_ACCOUNT_HASH', '')
SCHWAB_REFRESH_TOKEN = os.getenv('SCHWAB_SBI_REFRESH_TOKEN', '')
TOKEN_FILE = os.path.expanduser('~/.schwab_sbi_tokens.json')


# =============================================
# STRATEGY SETTINGS
# =============================================

@dataclass
class StrategyConfig:
    """Configuration for AdaptiveX2 SectorBot strategy."""
    
    # SBI Entry Thresholds
    min_sbi_for_entry: int = 9  # Only enter on SBI 9-10
    sbi_10_weight: float = 2.0  # Weight multiplier for SBI=10 stocks
    sbi_9_weight: float = 1.0   # Weight multiplier for SBI=9 stocks
    
    # EXIT RULES - KEY DIFFERENCE
    # We do NOT exit when SBI drops - only when PARENT turns bearish
    exit_on_sbi_drop: bool = False  # NEW: Don't sell just because SBI drops
    exit_on_parent_bearish: bool = True  # Exit ALL sector positions when parent turns bearish
    
    # Position Limits
    max_stocks_per_sector: int = 5   # Max stocks to hold per sector
    max_total_positions: int = 25    # Max total positions
    
    # Sector Allocation (% of portfolio when sector is active)
    sector_allocations: Dict[str, float] = field(default_factory=lambda: {
        'crypto': 0.25,          # BTC, ETH, SOL combined
        'precious_metals': 0.20,  # Gold + Silver
        'sp500_sectors': 0.30,    # XLK, XLF, XLV, etc.
        'industries': 0.15,       # SMH, IBB, KRE, etc.
        'international': 0.10,    # FXI, EWJ, INDA, etc.
    })
    
    # Within each category, allocate to sub-sectors based on parent momentum
    # Example: If crypto is 25% and BTC is stronger than ETH, BTC gets more
    use_momentum_weighting: bool = True
    
    # Risk Management
    max_position_pct: float = 0.10  # Max 10% in any single stock
    min_position_pct: float = 0.02  # Min 2% position size
    
    # Leverage
    use_leverage: bool = False  # Individual stocks = no leverage


DEFAULT_CONFIG = StrategyConfig()


# =============================================
# PARENT → CHILD STOCK MAPPING
# =============================================

PARENT_CHILD_MAPPING = {
    # =========================================
    # CRYPTO (tied to BTC/ETH/SOL signals)
    # =========================================
    'BTC-USD': {
        'description': 'Bitcoin',
        'category': 'crypto',
        'etf_1x': 'IBIT',
        'etf_2x': 'BITU',
        'stocks': [
            'MSTR',   # MicroStrategy - largest BTC holder
            'MARA',   # Marathon Digital - BTC miner
            'CLSK',   # CleanSpark - BTC miner
            'RIOT',   # Riot Platforms - BTC miner
            'COIN',   # Coinbase - crypto exchange
            'HOOD',   # Robinhood - crypto trading
            'BTBT',   # Bit Digital - BTC miner
            'HUT',    # Hut 8 Mining
            'CIFR',   # Cipher Mining
            'WULF',   # TeraWulf - BTC miner
            'XYZ',    # Block (formerly SQ, crypto services)
            'PYPL',   # PayPal (crypto)
        ],
    },
    'ETH-USD': {
        'description': 'Ethereum',
        'category': 'crypto',
        'etf_1x': 'FETH',
        'etf_2x': 'ETHU',
        'stocks': [
            'SBET',   # SharpLink - ETH treasury vehicle
            'BMNR',   # BitMine Immersion - largest ETH holder
            'BTCS',   # Blockchain Technology Consensus Solutions
            'BTBT',   # Bit Digital - ETH treasury
        ],
    },
    'SOL-USD': {
        'description': 'Solana',
        'category': 'crypto',
        'etf_1x': None,  # SOLQ delisted
        'etf_2x': 'SOLT',
        'stocks': [
            'COIN',   # Coinbase
            'HOOD',   # Robinhood
        ],
    },
    
    # =========================================
    # PRECIOUS METALS
    # =========================================
    'GLD': {
        'description': 'Gold',
        'category': 'precious_metals',
        'etf_1x': 'GDX',
        'etf_2x': 'NUGT',
        'stocks': [
            'NEM',    # Newmont - largest gold miner
            'GOLD',   # Barrick Gold
            'AEM',    # Agnico Eagle
            'FNV',    # Franco-Nevada (royalty)
            'WPM',    # Wheaton Precious Metals (streaming)
            'GFI',    # Gold Fields
            'KGC',    # Kinross Gold
            'AU',     # AngloGold Ashanti
            'HMY',    # Harmony Gold
            'EGO',    # Eldorado Gold
        ],
    },
    'SLV': {
        'description': 'Silver',
        'category': 'precious_metals',
        'etf_1x': 'SIL',
        'etf_2x': 'AGQ',
        'stocks': [
            'PAAS',   # Pan American Silver
            'WPM',    # Wheaton (also silver streaming)
            'HL',     # Hecla Mining
            'AG',     # First Majestic Silver
            'CDE',    # Coeur Mining
            'EXK',    # Endeavour Silver (replacing delisted MAG)
        ],
    },
    
    # =========================================
    # S&P 500 SECTORS
    # =========================================
    'XLK': {
        'description': 'Technology',
        'category': 'sp500_sectors',
        'etf_1x': 'XLK',
        'etf_2x': 'ROM',
        'stocks': [
            'AAPL', 'MSFT', 'NVDA', 'AVGO', 'CRM',
            'ADBE', 'CSCO', 'ACN', 'ORCL', 'AMD',
        ],
    },
    'XLF': {
        'description': 'Financials',
        'category': 'sp500_sectors',
        'etf_1x': 'XLF',
        'etf_2x': 'UYG',
        'stocks': [
            'JPM', 'V', 'MA', 'BAC', 'WFC',
            'GS', 'MS', 'AXP', 'SPGI', 'BLK',
        ],
    },
    'XLV': {
        'description': 'Healthcare',
        'category': 'sp500_sectors',
        'etf_1x': 'XLV',
        'etf_2x': 'RXL',
        'stocks': [
            'LLY', 'UNH', 'JNJ', 'ABBV', 'MRK',
            'TMO', 'ABT', 'PFE', 'ISRG', 'AMGN',
        ],
    },
    'XLY': {
        'description': 'Consumer Discretionary',
        'category': 'sp500_sectors',
        'etf_1x': 'XLY',
        'etf_2x': 'UCC',
        'stocks': [
            'AMZN', 'TSLA', 'HD', 'MCD', 'NKE',
            'LOW', 'SBUX', 'TJX', 'BKNG', 'CMG',
        ],
    },
    'XLC': {
        'description': 'Communication Services',
        'category': 'sp500_sectors',
        'etf_1x': 'XLC',
        'etf_2x': None,
        'stocks': [
            'META', 'GOOGL', 'NFLX', 'DIS', 'CMCSA',
            'VZ', 'T', 'TMUS', 'EA', 'TTWO',
        ],
    },
    'XLI': {
        'description': 'Industrials',
        'category': 'sp500_sectors',
        'etf_1x': 'XLI',
        'etf_2x': 'UXI',
        'stocks': [
            'GE', 'CAT', 'RTX', 'UNP', 'HON',
            'DE', 'BA', 'LMT', 'UPS', 'MMM',
        ],
    },
    'XLE': {
        'description': 'Energy',
        'category': 'sp500_sectors',
        'etf_1x': 'XLE',
        'etf_2x': 'DIG',
        'stocks': [
            'XOM', 'CVX', 'COP', 'SLB', 'EOG',
            'MPC', 'PSX', 'VLO', 'OXY', 'BKR',
        ],
    },
    'OIH': {
        'description': 'Oil Services',
        'category': 'industries',
        'etf_1x': 'OIH',
        'etf_2x': None,
        'stocks': [
            'SLB',    # Schlumberger - largest oilfield services
            'BKR',    # Baker Hughes
            'HAL',    # Halliburton
            'NOV',    # NOV Inc (drilling equipment)
            'FTI',    # TechnipFMC
            'CHX',    # ChampionX
            'HP',     # Helmerich & Payne (drilling)
            'PTEN',   # Patterson-UTI Energy
            'RIG',    # Transocean (offshore drilling)
            'VAL',    # Valaris (offshore drilling)
        ],
    },
    'XLU': {
        'description': 'Utilities',
        'category': 'sp500_sectors',
        'etf_1x': 'XLU',
        'etf_2x': 'UPW',
        'stocks': [
            'NEE', 'SO', 'DUK', 'CEG', 'SRE',
            'AEP', 'D', 'EXC', 'XEL', 'ED',
        ],
    },
    'XLP': {
        'description': 'Consumer Staples',
        'category': 'sp500_sectors',
        'etf_1x': 'XLP',
        'etf_2x': None,
        'stocks': [
            'PG', 'KO', 'PEP', 'COST', 'WMT',
            'PM', 'MO', 'CL', 'MDLZ', 'KHC',
        ],
    },
    'XLB': {
        'description': 'Materials',
        'category': 'sp500_sectors',
        'etf_1x': 'XLB',
        'etf_2x': 'UYM',
        'stocks': [
            'LIN', 'SHW', 'APD', 'FCX', 'ECL',
            'NUE', 'DOW', 'DD', 'VMC', 'MLM',
        ],
    },
    'XLRE': {
        'description': 'Real Estate',
        'category': 'sp500_sectors',
        'etf_1x': 'XLRE',
        'etf_2x': 'URE',
        'stocks': [
            'PLD', 'AMT', 'EQIX', 'WELL', 'SPG',
            'PSA', 'O', 'DLR', 'CCI', 'AVB',
        ],
    },
    
    # =========================================
    # INDUSTRY ETFs
    # =========================================
    'SMH': {
        'description': 'Semiconductors',
        'category': 'industries',
        'etf_1x': 'SMH',
        'etf_2x': 'SOXL',
        'stocks': [
            'NVDA', 'TSM', 'AVGO', 'AMD', 'ASML',
            'QCOM', 'TXN', 'LRCX', 'AMAT', 'MU',
        ],
    },
    'IBB': {
        'description': 'Biotech',
        'category': 'industries',
        'etf_1x': 'IBB',
        'etf_2x': 'LABU',
        'stocks': [
            'VRTX', 'AMGN', 'GILD', 'REGN', 'BIIB',
            'MRNA', 'ILMN', 'ALNY', 'BMRN', 'ARGX',  # ARGX replacing SGEN (acquired by Pfizer)
        ],
    },
    'KRE': {
        'description': 'Regional Banks',
        'category': 'industries',
        'etf_1x': 'KRE',
        'etf_2x': None,
        'stocks': [
            'HBAN', 'RF', 'CFG', 'KEY', 'FITB',
            'MTB', 'ZION', 'CMA', 'FHN', 'WAL',
        ],
    },
    'XHB': {
        'description': 'Homebuilders',
        'category': 'industries',
        'etf_1x': 'XHB',
        'etf_2x': None,
        'stocks': [
            'DHI', 'LEN', 'NVR', 'PHM', 'TOL',
            'KBH', 'TMHC', 'MTH', 'MHO', 'GRBK',  # GRBK replacing MDC (delisted)
        ],
    },
    'URA': {
        'description': 'Uranium/Nuclear',
        'category': 'industries',
        'etf_1x': 'URA',
        'etf_2x': None,
        'stocks': [
            'CCJ', 'CEG', 'VST', 'SMR', 'LEU',
            'NNE', 'DNN', 'OKLO', 'UEC', 'NLR',
        ],
    },
    'ITA': {
        'description': 'Aerospace & Defense',
        'category': 'industries',
        'etf_1x': 'ITA',
        'etf_2x': None,
        'stocks': [
            'RTX', 'LMT', 'BA', 'NOC', 'GD',
            'TDG', 'LHX', 'HII', 'TXT', 'AXON',
        ],
    },
    'MEME': {
        'description': 'Meme Stocks',
        'category': 'meme',
        'etf_1x': 'MEME',  # Roundhill MEME ETF
        'etf_2x': None,
        'stocks': [
            # Top holdings from stockanalysis.com/etf/meme/holdings/
            # Updated monthly via meme_holdings.py
            'GME',    # GameStop - 6.52%
            'MSTR',   # MicroStrategy - 5.89%
            'HOOD',   # Robinhood - 5.54%
            'RDDT',   # Reddit - 5.46%
            'IONQ',   # IonQ - 5.44%
            'COIN',   # Coinbase - 5.37%
            'RKLB',   # Rocket Lab - 5.35%
            'SOFI',   # SoFi - 5.30%
            'PLTR',   # Palantir - 5.26%
            'AMC',    # AMC - 4.54%
            'AFRM',   # Affirm - 4.49%
            'UPST',   # Upstart - 4.44%
            'CVNA',   # Carvana - 4.43%
            'LCID',   # Lucid - 4.15%
            'RIVN',   # Rivian - 4.09%
            'DNA',    # Ginkgo Bioworks - 3.83%
            'JOBY',   # Joby Aviation - 3.73%
            'OPEN',   # Opendoor - 3.48%
            'PLUG',   # Plug Power - 3.37%
            'MARA',   # Marathon Digital - 2.99%
        ],
        'dynamic': True,  # Flag to refresh from meme_holdings.py monthly
    },
    
    # =========================================
    # INTERNATIONAL
    # =========================================
    'FXI': {
        'description': 'China',
        'category': 'international',
        'etf_1x': 'FXI',
        'etf_2x': 'YINN',
        'stocks': [
            'BABA', 'JD', 'PDD', 'BIDU', 'NIO',
            'XPEV', 'LI', 'NTES', 'TME', 'BILI',
        ],
    },
    'EWJ': {
        'description': 'Japan',
        'category': 'international',
        'etf_1x': 'EWJ',
        'etf_2x': 'EZJ',
        'stocks': [
            'TM', 'SONY', 'MUFG', 'SMFG', 'HMC',
            'NTDOY', 'MFG',  # MFG (Mizuho) replacing delisted CAJ
        ],
    },
    'INDA': {
        'description': 'India',
        'category': 'international',
        'etf_1x': 'INDA',
        'etf_2x': 'INDL',
        'stocks': [
            'INFY', 'WIT', 'HDB', 'IBN', 'RDY', 'SIFY',  # SIFY replacing delisted TTM
        ],
    },
    'EWZ': {
        'description': 'Brazil',
        'category': 'international',
        'etf_1x': 'EWZ',
        'etf_2x': 'UBR',
        'stocks': [
            'VALE', 'PBR', 'ITUB', 'BBD', 'ABEV', 'NU',
        ],
    },
    'EEM': {
        'description': 'Emerging Markets',
        'category': 'international',
        'etf_1x': 'EEM',
        'etf_2x': 'EET',
        'stocks': [
            'TSM', 'BABA', 'VALE', 'PDD', 'INFY',
            'JD', 'NU', 'MELI', 'SE',
        ],
    },
    
    # =========================================
    # AI INFRASTRUCTURE (NEW)
    # =========================================
    'TCAI': {
        'description': 'AI Infrastructure',
        'category': 'ai_infrastructure',
        'etf_1x': 'TCAI',  # Tortoise AI Infrastructure ETF
        'etf_2x': None,
        'stocks': [
            # Top holdings from tortoisecapital.com/etf/tortoise-ai-infrastructure-etf
            # Data centers, power, networking, compute
            'CIEN',   # Ciena Corp - 5.55% - Networking
            'STX',    # Seagate - 4.79% - Storage
            'VRT',    # Vertiv - 4.66% - Data center cooling
            'PWR',    # Quanta Services - 4.12% - Power infrastructure
            'WDC',    # Western Digital - 4.01% - Storage
            'NRG',    # NRG Energy - 3.96% - Power
            'DELL',   # Dell Technologies - 3.93% - Servers
            'NVT',    # nVent Electric - 3.80% - Electrical infrastructure
            'MU',     # Micron - 3.39% - Memory
            'EQT',    # EQT Corp - 3.23% - Natural gas
            'CIFR',   # Cipher Mining - 3.21% - Bitcoin mining/AI compute
            'MTZ',    # MasTec - 3.16% - Infrastructure construction
            'MYRG',   # MYR Group - 2.86% - Electrical construction
            'IREN',   # IREN Ltd - 2.64% - Bitcoin mining/AI compute
            'CORZ',   # Core Scientific - 2.46% - Bitcoin mining/AI compute
            'EXE',    # Expand Energy - 2.45% - Natural gas
            'WULF',   # Terawulf - 2.45% - Bitcoin mining/AI compute
            'PRIM',   # Primoris Services - 2.34% - Infrastructure
            'PSTG',   # Pure Storage - 2.31% - Storage
            'CEG',    # Constellation Energy - 2.30% - Nuclear power
            'WMB',    # Williams Companies - 2.17% - Natural gas pipelines
            'ANET',   # Arista Networks - 2.00% - Networking
            'VST',    # Vistra - 2.00% - Power
            'EVRG',   # Evergy - 1.95% - Utilities
            'APH',    # Amphenol - 1.80% - Connectors
            'ET',     # Energy Transfer - 1.49% - Pipelines
            'ETR',    # Entergy - 1.44% - Utilities
            'MOD',    # Modine Manufacturing - 1.43% - Thermal management
            'GEV',    # GE Vernova - 1.42% - Power equipment
            'SRE',    # Sempra - 1.33% - Utilities
            'SNDK',   # Sandisk - 1.28% - Storage
            'DLR',    # Digital Realty - 1.22% - Data centers
            'CAT',    # Caterpillar - 1.03% - Construction equipment
            'TLN',    # Talen Energy - 1.02% - Power
            'NVDA',   # NVIDIA - 0.92% - AI chips
            'DTM',    # DT Midstream - 0.89% - Pipelines
            'SMCI',   # Super Micro Computer - 0.88% - AI servers
            'CMI',    # Cummins - 0.71% - Power generators
            'CLS',    # Celestica - 0.57% - Electronics manufacturing
            'EQIX',   # Equinix - 0.57% - Data centers
        ],
    },
}


# =============================================
# HELPER FUNCTIONS
# =============================================

def update_meme_holdings():
    """
    Dynamically update meme stock holdings from live sources.
    Call this before running scans to get fresh meme stocks.
    """
    try:
        from meme_holdings import get_meme_holdings
        result = get_meme_holdings(use_cache=True)
        if result and result['stocks']:
            PARENT_CHILD_MAPPING['MEME']['stocks'] = result['stocks']
            print(f"   🎮 Updated MEME holdings: {len(result['stocks'])} stocks from {result['source']}")
    except ImportError:
        print("   ⚠️ meme_holdings.py not found, using static list")
    except Exception as e:
        print(f"   ⚠️ Could not update meme holdings: {e}")


def get_all_tickers() -> List[str]:
    """Get all tickers needed for data fetching."""
    tickers = set()
    
    for parent, info in PARENT_CHILD_MAPPING.items():
        tickers.add(parent)
        if info.get('etf_1x'):
            tickers.add(info['etf_1x'])
        if info.get('etf_2x'):
            tickers.add(info['etf_2x'])
        tickers.update(info['stocks'])
    
    # Remove any None values
    tickers.discard(None)
    
    return sorted(list(tickers))


def get_parents_by_category(category: str) -> List[str]:
    """Get all parent tickers for a category."""
    return [parent for parent, info in PARENT_CHILD_MAPPING.items() 
            if info['category'] == category]


def get_all_categories() -> List[str]:
    """Get all category names."""
    return list(DEFAULT_CONFIG.sector_allocations.keys())


def get_category_allocation(category: str) -> float:
    """Get the allocation percentage for a category."""
    return DEFAULT_CONFIG.sector_allocations.get(category, 0.0)


# =============================================
# PRINT SUMMARY
# =============================================

if __name__ == "__main__":
    print("AdaptiveX2 SectorBot Configuration")
    print("=" * 60)
    
    all_tickers = get_all_tickers()
    print(f"\nTotal tickers to track: {len(all_tickers)}")
    
    print("\nParent signals by category:")
    for cat in get_all_categories():
        parents = get_parents_by_category(cat)
        alloc = get_category_allocation(cat)
        print(f"  {cat} ({alloc*100:.0f}%): {', '.join(parents)}")
    
    print("\nStrategy settings:")
    print(f"  Min SBI for entry: {DEFAULT_CONFIG.min_sbi_for_entry}")
    print(f"  Exit on SBI drop: {DEFAULT_CONFIG.exit_on_sbi_drop}")
    print(f"  Exit on parent bearish: {DEFAULT_CONFIG.exit_on_parent_bearish}")
    print(f"  Max stocks per sector: {DEFAULT_CONFIG.max_stocks_per_sector}")
