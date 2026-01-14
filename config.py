"""
SectorBot Configuration
=======================
Parent-Child mappings for sector rotation strategy.

To add more stocks to a sector:
1. Find the parent (e.g., BTC-USD)
2. Add tickers to the 'stocks' list

To add a new sector:
1. Add a new key to PARENT_CHILD_MAPPING
2. Include 'name', 'category', and 'stocks' keys
"""

import os
from dataclasses import dataclass
from typing import Dict, List, Optional

# =============================================================================
# PARENT-CHILD SECTOR MAPPINGS
# =============================================================================

PARENT_CHILD_MAPPING = {
    # =========================================================================
    # CRYPTO
    # =========================================================================
    'BTC-USD': {
        'name': 'Bitcoin',
        'category': 'crypto',
        'stocks': [
            # Bitcoin miners
            'MSTR',   # Strategy (MicroStrategy) - largest BTC holder
            'MARA',   # Marathon Digital - major miner
            'CLSK',   # CleanSpark - growing miner
            'RIOT',   # Riot Platforms - major miner
            'BTBT',   # Bit Digital - miner
            'HUT',    # Hut 8 Mining
            'CIFR',   # Cipher Mining
            'WULF',   # TeraWulf - green miner
            'CORZ',   # Core Scientific
            'BITF',   # Bitfarms
            'HIVE',   # HIVE Digital
            'IREN',   # Iris Energy
            'ARBK',   # Argo Blockchain
            
            # Bitcoin-exposed companies
            'COIN',   # Coinbase - crypto exchange
            'HOOD',   # Robinhood - crypto trading
            'SQ',     # Block (Square) - Bitcoin on balance sheet
            'PYPL',   # PayPal - crypto services
            
            # Bitcoin ETFs (for reference, usually trade parent directly)
            # 'IBIT',   # iShares Bitcoin Trust
            # 'FBTC',   # Fidelity Bitcoin
            # 'GBTC',   # Grayscale Bitcoin Trust
        ]
    },
    
    'ETH-USD': {
        'name': 'Ethereum',
        'category': 'crypto',
        'stocks': [
            'COIN',   # Coinbase
            'HOOD',   # Robinhood
            'ETHE',   # Grayscale Ethereum Trust
            # Add ETH-specific plays here
        ]
    },
    
    'SOL-USD': {
        'name': 'Solana',
        'category': 'crypto',
        'stocks': [
            'COIN',   # Coinbase
            'HOOD',   # Robinhood
            # Add SOL-specific plays here when available
        ]
    },
    
    # =========================================================================
    # PRECIOUS METALS
    # =========================================================================
    'GLD': {
        'name': 'Gold',
        'category': 'precious_metals',
        'stocks': [
            # Senior gold miners
            'NEM',    # Newmont - largest gold miner
            'GOLD',   # Barrick Gold
            'AEM',    # Agnico Eagle
            'KGC',    # Kinross Gold
            'AU',     # AngloGold Ashanti
            'HMY',    # Harmony Gold
            'GFI',    # Gold Fields
            
            # Mid-tier miners
            'EGO',    # Eldorado Gold
            'BTG',    # B2Gold
            'IAG',    # IAMGOLD
            'NGD',    # New Gold
            'OGC',    # OceanaGold
            
            # Royalty/Streaming
            'WPM',    # Wheaton Precious Metals
            'FNV',    # Franco-Nevada
            'RGLD',   # Royal Gold
            
            # Gold ETFs/Miners ETF
            'GDX',    # VanEck Gold Miners
            'GDXJ',   # VanEck Junior Gold Miners
        ]
    },
    
    'SLV': {
        'name': 'Silver',
        'category': 'precious_metals',
        'stocks': [
            # Primary silver miners
            'PAAS',   # Pan American Silver
            'AG',     # First Majestic Silver
            'HL',     # Hecla Mining
            'CDE',    # Coeur Mining
            'MAG',    # MAG Silver
            'FSM',    # Fortuna Silver
            'EXK',    # Endeavour Silver
            'SVM',    # Silvercorp Metals
            
            # Silver ETFs
            'SIL',    # Global X Silver Miners
            'SILJ',   # ETFMG Prime Junior Silver
        ]
    },
    
    # =========================================================================
    # S&P 500 SECTORS
    # =========================================================================
    'XLK': {
        'name': 'Technology',
        'category': 'sector',
        'stocks': [
            'AAPL',   # Apple
            'MSFT',   # Microsoft
            'NVDA',   # NVIDIA
            'AVGO',   # Broadcom
            'CRM',    # Salesforce
            'ADBE',   # Adobe
            'CSCO',   # Cisco
            'ACN',    # Accenture
            'ORCL',   # Oracle
            'INTC',   # Intel
            'IBM',    # IBM
            'INTU',   # Intuit
            'AMD',    # AMD
            'QCOM',   # Qualcomm
            'TXN',    # Texas Instruments
            'NOW',    # ServiceNow
            'AMAT',   # Applied Materials
            'MU',     # Micron
            'ADI',    # Analog Devices
            'LRCX',   # Lam Research
        ]
    },
    
    'XLF': {
        'name': 'Financials',
        'category': 'sector',
        'stocks': [
            'JPM',    # JPMorgan Chase
            'BAC',    # Bank of America
            'WFC',    # Wells Fargo
            'GS',     # Goldman Sachs
            'MS',     # Morgan Stanley
            'BLK',    # BlackRock
            'SCHW',   # Charles Schwab
            'C',      # Citigroup
            'AXP',    # American Express
            'SPGI',   # S&P Global
            'PGR',    # Progressive
            'CB',     # Chubb
            'MMC',    # Marsh McLennan
            'ICE',    # Intercontinental Exchange
            'CME',    # CME Group
            'USB',    # US Bancorp
            'PNC',    # PNC Financial
            'TFC',    # Truist
            'AIG',    # AIG
            'MET',    # MetLife
        ]
    },
    
    'XLV': {
        'name': 'Healthcare',
        'category': 'sector',
        'stocks': [
            'UNH',    # UnitedHealth
            'JNJ',    # Johnson & Johnson
            'LLY',    # Eli Lilly
            'PFE',    # Pfizer
            'ABBV',   # AbbVie
            'MRK',    # Merck
            'TMO',    # Thermo Fisher
            'ABT',    # Abbott Labs
            'DHR',    # Danaher
            'BMY',    # Bristol-Myers
            'AMGN',   # Amgen
            'GILD',   # Gilead
            'CVS',    # CVS Health
            'ISRG',   # Intuitive Surgical
            'VRTX',   # Vertex
            'SYK',    # Stryker
            'REGN',   # Regeneron
            'MDT',    # Medtronic
            'ZTS',    # Zoetis
            'BDX',    # Becton Dickinson
        ]
    },
    
    'XLE': {
        'name': 'Energy',
        'category': 'sector',
        'stocks': [
            'XOM',    # Exxon Mobil
            'CVX',    # Chevron
            'COP',    # ConocoPhillips
            'EOG',    # EOG Resources
            'SLB',    # Schlumberger
            'MPC',    # Marathon Petroleum
            'PXD',    # Pioneer Natural
            'PSX',    # Phillips 66
            'VLO',    # Valero
            'OXY',    # Occidental
            'WMB',    # Williams Companies
            'KMI',    # Kinder Morgan
            'HAL',    # Halliburton
            'DVN',    # Devon Energy
            'HES',    # Hess
            'FANG',   # Diamondback
            'BKR',    # Baker Hughes
            'OKE',    # ONEOK
            'TRGP',   # Targa Resources
            'MRO',    # Marathon Oil
        ]
    },
    
    'XLI': {
        'name': 'Industrials',
        'category': 'sector',
        'stocks': [
            'CAT',    # Caterpillar
            'HON',    # Honeywell
            'UNP',    # Union Pacific
            'BA',     # Boeing
            'RTX',    # RTX (Raytheon)
            'DE',     # Deere
            'GE',     # GE Aerospace
            'LMT',    # Lockheed Martin
            'UPS',    # UPS
            'ADP',    # ADP
            'MMM',    # 3M
            'ETN',    # Eaton
            'ITW',    # Illinois Tool Works
            'EMR',    # Emerson
            'FDX',    # FedEx
            'NOC',    # Northrop Grumman
            'GD',     # General Dynamics
            'CSX',    # CSX
            'NSC',    # Norfolk Southern
            'WM',     # Waste Management
        ]
    },
    
    'XLY': {
        'name': 'Consumer Discretionary',
        'category': 'sector',
        'stocks': [
            'AMZN',   # Amazon
            'TSLA',   # Tesla
            'HD',     # Home Depot
            'MCD',    # McDonald's
            'NKE',    # Nike
            'LOW',    # Lowe's
            'SBUX',   # Starbucks
            'TJX',    # TJX Companies
            'BKNG',   # Booking Holdings
            'CMG',    # Chipotle
            'MAR',    # Marriott
            'ORLY',   # O'Reilly Auto
            'AZO',    # AutoZone
            'GM',     # General Motors
            'F',      # Ford
            'ROST',   # Ross Stores
            'DHI',    # D.R. Horton
            'LEN',    # Lennar
            'YUM',    # Yum! Brands
            'EBAY',   # eBay
        ]
    },
    
    'XLP': {
        'name': 'Consumer Staples',
        'category': 'sector',
        'stocks': [
            'PG',     # Procter & Gamble
            'KO',     # Coca-Cola
            'PEP',    # PepsiCo
            'COST',   # Costco
            'WMT',    # Walmart
            'PM',     # Philip Morris
            'MO',     # Altria
            'MDLZ',   # Mondelez
            'CL',     # Colgate-Palmolive
            'KMB',    # Kimberly-Clark
            'GIS',    # General Mills
            'STZ',    # Constellation Brands
            'SYY',    # Sysco
            'KHC',    # Kraft Heinz
            'HSY',    # Hershey
            'K',      # Kellanova
            'CAG',    # Conagra
            'ADM',    # ADM
            'KR',     # Kroger
            'EL',     # Estee Lauder
        ]
    },
    
    'XLU': {
        'name': 'Utilities',
        'category': 'sector',
        'stocks': [
            'NEE',    # NextEra Energy
            'DUK',    # Duke Energy
            'SO',     # Southern Company
            'D',      # Dominion Energy
            'AEP',    # American Electric Power
            'SRE',    # Sempra
            'EXC',    # Exelon
            'XEL',    # Xcel Energy
            'ED',     # Consolidated Edison
            'PEG',    # PSEG
            'WEC',    # WEC Energy
            'ES',     # Eversource
            'AWK',    # American Water Works
            'DTE',    # DTE Energy
            'ETR',    # Entergy
            'FE',     # FirstEnergy
            'AEE',    # Ameren
            'CMS',    # CMS Energy
            'CNP',    # CenterPoint
            'ATO',    # Atmos Energy
        ]
    },
    
    'XLC': {
        'name': 'Communication Services',
        'category': 'sector',
        'stocks': [
            'META',   # Meta Platforms
            'GOOGL',  # Alphabet A
            'GOOG',   # Alphabet C
            'NFLX',   # Netflix
            'DIS',    # Disney
            'VZ',     # Verizon
            'T',      # AT&T
            'CMCSA',  # Comcast
            'TMUS',   # T-Mobile
            'CHTR',   # Charter
            'EA',     # Electronic Arts
            'WBD',    # Warner Bros Discovery
            'TTWO',   # Take-Two
            'OMC',    # Omnicom
            'IPG',    # Interpublic
            'LYV',    # Live Nation
            'MTCH',   # Match Group
            'PARA',   # Paramount
            'FOX',    # Fox Corp
            'FOXA',   # Fox Corp A
        ]
    },
    
    'XLRE': {
        'name': 'Real Estate',
        'category': 'sector',
        'stocks': [
            'AMT',    # American Tower
            'PLD',    # Prologis
            'CCI',    # Crown Castle
            'EQIX',   # Equinix
            'SPG',    # Simon Property
            'PSA',    # Public Storage
            'WELL',   # Welltower
            'DLR',    # Digital Realty
            'O',      # Realty Income
            'AVB',    # AvalonBay
            'EQR',    # Equity Residential
            'VTR',    # Ventas
            'SBAC',   # SBA Communications
            'WY',     # Weyerhaeuser
            'ARE',    # Alexandria RE
            'EXR',    # Extra Space Storage
            'MAA',    # Mid-America Apt
            'UDR',    # UDR Inc
            'ESS',    # Essex Property
            'INVH',   # Invitation Homes
        ]
    },
    
    'XLB': {
        'name': 'Materials',
        'category': 'sector',
        'stocks': [
            'LIN',    # Linde
            'APD',    # Air Products
            'SHW',    # Sherwin-Williams
            'FCX',    # Freeport-McMoRan
            'ECL',    # Ecolab
            'NEM',    # Newmont
            'NUE',    # Nucor
            'DOW',    # Dow Inc
            'DD',     # DuPont
            'CTVA',   # Corteva
            'PPG',    # PPG Industries
            'VMC',    # Vulcan Materials
            'MLM',    # Martin Marietta
            'ALB',    # Albemarle
            'IFF',    # IFF
            'STLD',   # Steel Dynamics
            'CF',     # CF Industries
            'MOS',    # Mosaic
            'BALL',   # Ball Corp
            'PKG',    # Packaging Corp
        ]
    },
    
    # =========================================================================
    # INDUSTRIES / THEMATIC
    # =========================================================================
    'SMH': {
        'name': 'Semiconductors',
        'category': 'industry',
        'stocks': [
            'NVDA',   # NVIDIA
            'AVGO',   # Broadcom
            'AMD',    # AMD
            'QCOM',   # Qualcomm
            'TXN',    # Texas Instruments
            'INTC',   # Intel
            'MU',     # Micron
            'AMAT',   # Applied Materials
            'LRCX',   # Lam Research
            'ADI',    # Analog Devices
            'KLAC',   # KLA Corp
            'MRVL',   # Marvell
            'NXPI',   # NXP Semi
            'ON',     # ON Semiconductor
            'SWKS',   # Skyworks
            'MCHP',   # Microchip
            'MPWR',   # Monolithic Power
            'TER',    # Teradyne
            'ENTG',   # Entegris
            'LSCC',   # Lattice Semi
        ]
    },
    
    'IBB': {
        'name': 'Biotech',
        'category': 'industry',
        'stocks': [
            'AMGN',   # Amgen
            'GILD',   # Gilead
            'VRTX',   # Vertex
            'REGN',   # Regeneron
            'BIIB',   # Biogen
            'MRNA',   # Moderna
            'ILMN',   # Illumina
            'ALNY',   # Alnylam
            'SGEN',   # Seagen
            'BMRN',   # BioMarin
            'EXAS',   # Exact Sciences
            'INCY',   # Incyte
            'BGNE',   # BeiGene
            'UTHR',   # United Therapeutics
            'HALO',   # Halozyme
            'PCVX',   # Vaxcyte
            'ARGX',   # argenx
            'SRPT',   # Sarepta
            'RARE',   # Ultragenyx
            'IONS',   # Ionis
        ]
    },
    
    'KRE': {
        'name': 'Regional Banks',
        'category': 'industry',
        'stocks': [
            'FITB',   # Fifth Third
            'RF',     # Regions Financial
            'HBAN',   # Huntington
            'CFG',    # Citizens Financial
            'KEY',    # KeyCorp
            'MTB',    # M&T Bank
            'ZION',   # Zions
            'CMA',    # Comerica
            'FHN',    # First Horizon
            'SNV',    # Synovus
            'WAL',    # Western Alliance
            'EWBC',   # East West Bancorp
            'PNFP',   # Pinnacle Financial
            'GBCI',   # Glacier Bancorp
            'UBSI',   # United Bankshares
            'VLY',    # Valley National
            'FNB',    # FNB Corp
            'BOKF',   # BOK Financial
            'ONB',    # Old National
            'OZK',    # Bank OZK
        ]
    },
    
    'XHB': {
        'name': 'Homebuilders',
        'category': 'industry',
        'stocks': [
            'DHI',    # D.R. Horton
            'LEN',    # Lennar
            'NVR',    # NVR Inc
            'PHM',    # PulteGroup
            'TOL',    # Toll Brothers
            'KBH',    # KB Home
            'TMHC',   # Taylor Morrison
            'MTH',    # Meritage Homes
            'MHO',    # M/I Homes
            'CCS',    # Century Communities
            'HD',     # Home Depot
            'LOW',    # Lowe's
            'SHW',    # Sherwin-Williams
            'MAS',    # Masco
            'BLDR',   # Builders FirstSource
            'WSM',    # Williams-Sonoma
            'RH',     # RH (Restoration Hardware)
            'FBIN',   # Fortune Brands
            'FBHS',   # Fortune Brands Home
            'WHR',    # Whirlpool
        ]
    },
    
    # =========================================================================
    # INTERNATIONAL
    # =========================================================================
    'FXI': {
        'name': 'China Large-Cap',
        'category': 'international',
        'stocks': [
            'BABA',   # Alibaba
            'JD',     # JD.com
            'PDD',    # PDD Holdings
            'BIDU',   # Baidu
            'NIO',    # NIO
            'LI',     # Li Auto
            'XPEV',   # XPeng
            'NTES',   # NetEase
            'TME',    # Tencent Music
            'BILI',   # Bilibili
            'IQ',     # iQIYI
            'FUTU',   # Futu Holdings
            'TAL',    # TAL Education
            'MNSO',   # MINISO
            'ZTO',    # ZTO Express
            'VNET',   # VNET Group
            'QFIN',   # Qifu Technology
            'YUMC',   # Yum China
            'EDU',    # New Oriental
            'ATHM',   # Autohome
        ]
    },
    
    'EWJ': {
        'name': 'Japan',
        'category': 'international',
        'stocks': [
            'TM',     # Toyota
            'SONY',   # Sony
            'MUFG',   # Mitsubishi UFJ
            'NMR',    # Nomura
            'HMC',    # Honda
            'SMFG',   # Sumitomo Mitsui
            'MFG',    # Mizuho Financial
            'IX',     # ORIX
            'KB',     # KB Financial (Korean but related)
            'CAJ',    # Canon
        ]
    },
    
    'INDA': {
        'name': 'India',
        'category': 'international',
        'stocks': [
            'INFY',   # Infosys
            'WIT',    # Wipro
            'HDB',    # HDFC Bank
            'IBN',    # ICICI Bank
            'SIFY',   # Sify Technologies
            'RDY',    # Dr. Reddy's
            'TTM',    # Tata Motors
            'VEDL',   # Vedanta
            'WNS',    # WNS Holdings
            'AZRE',   # Azure Power
        ]
    },
    
    # =========================================================================
    # MEME / HIGH VOLATILITY
    # =========================================================================
    'MEME': {
        'name': 'Meme Stocks',
        'category': 'meme',
        'stocks': [
            'GME',    # GameStop
            'AMC',    # AMC Entertainment
            'BBBY',   # Bed Bath & Beyond
            'BB',     # BlackBerry
            'PLTR',   # Palantir
            'SOFI',   # SoFi
            'WISH',   # ContextLogic
            'CLOV',   # Clover Health
            'SPCE',   # Virgin Galactic
            'TLRY',   # Tilray
            'NIO',    # NIO
            'LCID',   # Lucid Motors
            'RIVN',   # Rivian
            'FFIE',   # Faraday Future
            'MULN',   # Mullen Automotive
        ]
    },
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_all_parents() -> List[str]:
    """Get list of all parent tickers."""
    return list(PARENT_CHILD_MAPPING.keys())


def get_children(parent: str) -> List[str]:
    """Get children for a parent ticker."""
    if parent in PARENT_CHILD_MAPPING:
        return PARENT_CHILD_MAPPING[parent].get('stocks', [])
    return []


def get_all_tickers() -> List[str]:
    """Get all unique tickers (parents + children)."""
    tickers = set()
    for parent, info in PARENT_CHILD_MAPPING.items():
        tickers.add(parent)
        tickers.update(info.get('stocks', []))
    return list(tickers)


def get_parents_by_category(category: str) -> List[str]:
    """Get parents filtered by category."""
    return [p for p, info in PARENT_CHILD_MAPPING.items() 
            if info.get('category') == category]


def get_all_categories() -> List[str]:
    """Get list of all unique categories."""
    return list(set(info.get('category', 'other') 
                   for info in PARENT_CHILD_MAPPING.values()))


def get_category_allocation(category: str) -> float:
    """Get suggested allocation for a category (placeholder)."""
    allocations = {
        'crypto': 0.20,
        'precious_metals': 0.15,
        'sector': 0.10,
        'industry': 0.10,
        'international': 0.05,
        'meme': 0.05,
    }
    return allocations.get(category, 0.05)


def update_meme_holdings():
    """Update meme stock children based on current holdings (placeholder)."""
    # This could read from a file or API to get current meme stock trends
    pass


# =============================================================================
# DEFAULT CONFIGURATION
# =============================================================================

@dataclass
class StrategyConfig:
    """Strategy configuration settings."""
    max_positions: int = 20
    max_stocks_per_sector: int = 5
    min_sbi_entry: int = 9
    min_rsi_entry: float = 50.0
    weak_rsi_threshold: float = 40.0
    rotation_enabled: bool = True
    weighted_allocation: bool = False


DEFAULT_CONFIG = StrategyConfig()


# =============================================================================
# TESTING
# =============================================================================

if __name__ == "__main__":
    print("SectorBot Configuration")
    print("=" * 60)
    
    print(f"\nTotal parents: {len(PARENT_CHILD_MAPPING)}")
    print(f"Total unique tickers: {len(get_all_tickers())}")
    
    print("\nCategories:")
    for cat in get_all_categories():
        parents = get_parents_by_category(cat)
        print(f"  {cat}: {len(parents)} parents")
    
    print("\nBTC-USD children:")
    for child in get_children('BTC-USD'):
        print(f"  - {child}")
