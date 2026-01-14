#!/usr/bin/env python3
"""
SectorBot Daily Signal Image Generator
Generates a PNG image for Patreon subscribers

Usage:
    python generate_sectorbot_image.py                           # Run scan and generate
    python generate_sectorbot_image.py --json sectorbot.json     # Use existing JSON
    python generate_sectorbot_image.py --output my_signal.png    # Custom output path
"""

from PIL import Image, ImageDraw, ImageFont
import json
import argparse
from datetime import datetime
import os
import sys

# Colors
DARK_BG = (10, 14, 23)
CARD_BG = (26, 35, 50)
GOLD = (212, 165, 75)
TEXT_WHITE = (229, 231, 235)
TEXT_MUTED = (156, 163, 175)
SUCCESS = (34, 197, 94)
DANGER = (239, 68, 68)
BLUE = (59, 130, 246)
YELLOW = (234, 179, 8)


def load_signal_data(json_path=None):
    """Load signal data from JSON file or run scan."""
    
    # Try loading from JSON file first
    if json_path and os.path.exists(json_path):
        print(f"📂 Loading from {json_path}...")
        try:
            with open(json_path, 'r') as f:
                data = json.load(f)
            
            # Debug: show what we loaded
            print(f"   Type: {type(data)}")
            if isinstance(data, dict):
                print(f"   Keys: {list(data.keys())[:10]}")
                if 'target_allocation' in data:
                    ta = data['target_allocation']
                    print(f"   target_allocation type: {type(ta)}, len: {len(ta) if hasattr(ta, '__len__') else 'N/A'}")
            
            # Validate it's a dict with expected keys
            if isinstance(data, dict) and 'target_allocation' in data:
                return data
            else:
                print(f"⚠️ JSON file doesn't have expected format, running scan...")
        except Exception as e:
            print(f"⚠️ Failed to load JSON: {e}")
    
    # Run scan to generate data
    print("📊 Running SectorBot scan...")
    try:
        from main import run_signal_only
        signals = run_signal_only(small_account=True, output_json=False, save_report=True)
        if isinstance(signals, dict):
            return signals
        else:
            print(f"⚠️ Scan returned unexpected type: {type(signals)}")
            return get_sample_data()
    except Exception as e:
        print(f"❌ Failed to run scan: {e}")
        import traceback
        traceback.print_exc()
        return get_sample_data()


def get_sample_data():
    """Return sample data for testing."""
    return {
        "generated_at": datetime.now().isoformat(),
        "active_sectors": [
            {"parent": "QQQ", "description": "Technology"},
            {"parent": "IBIT", "description": "Bitcoin"},
            {"parent": "GLD", "description": "Gold"},
        ],
        "inactive_sectors": [
            {"parent": "XLE", "description": "Energy"},
        ],
        "target_allocation": [
            {"ticker": "NVDA", "sector": "QQQ", "weight": 0.10, "sbi": 10},
            {"ticker": "MSTR", "sector": "IBIT", "weight": 0.10, "sbi": 10},
            {"ticker": "AVGO", "sector": "SMH", "weight": 0.10, "sbi": 9},
            {"ticker": "META", "sector": "XLC", "weight": 0.10, "sbi": 9},
            {"ticker": "GFI", "sector": "GDX", "weight": 0.10, "sbi": 9},
        ],
        "entry_signals": [
            {"ticker": "COIN", "sector": "IBIT", "sbi": 10},
        ],
        "rotation_signals": [
            {"from_ticker": "AMD", "to_ticker": "NVDA", "sector": "SMH"},
        ],
        "exit_signals": [
            {"ticker": "BABA", "reason": "Parent bearish"},
        ],
    }


def get_font(size, bold=False):
    """Get font with fallback."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "arial.ttf",
    ]
    
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except:
            pass
    
    return ImageFont.load_default()


def create_signal_image(signal_data: dict, output_path: str = "sectorbot_signal.png"):
    """Generate the SectorBot signal PNG image."""
    
    # Defensive: ensure we have a dict
    if not isinstance(signal_data, dict):
        print(f"⚠️ signal_data is {type(signal_data)}, using sample data")
        signal_data = get_sample_data()
    
    # Image dimensions
    width = 800
    height = 1000  # Shorter since cleaner layout
    
    # Create image
    img = Image.new('RGB', (width, height), DARK_BG)
    draw = ImageDraw.Draw(img)
    
    # Fonts
    font_title = get_font(32, bold=True)
    font_medium = get_font(20, bold=True)
    font_normal = get_font(16)
    font_small = get_font(14)
    font_tiny = get_font(11)
    
    y = 20
    
    # Header
    draw.text((width // 2, y), "🤖 SectorBot", font=font_title, fill=GOLD, anchor="mt")
    y += 45
    
    # Date
    generated = signal_data.get("generated_at", datetime.now().isoformat())
    if isinstance(generated, str):
        try:
            dt = datetime.fromisoformat(generated.replace('Z', '+00:00'))
            date_str = dt.strftime("%B %d, %Y %I:%M %p ET")
        except:
            date_str = generated
    else:
        date_str = datetime.now().strftime("%B %d, %Y %I:%M %p ET")
    
    draw.text((width // 2, y), date_str, font=font_small, fill=TEXT_MUTED, anchor="mt")
    y += 35
    
    # Divider
    draw.line([(50, y), (width - 50, y)], fill=GOLD, width=2)
    y += 20
    
    # Summary stats
    active_count = len(signal_data.get("active_sectors", []))
    entry_count = len(signal_data.get("entry_signals", []))
    rotation_count = len(signal_data.get("rotation_signals", []))
    exit_count = len(signal_data.get("exit_signals", []))
    position_count = len(signal_data.get("target_allocation", []))
    
    # Stats boxes
    box_width = 150
    box_height = 60
    box_y = y
    boxes = [
        (f"{active_count}", "Active Sectors", SUCCESS),
        (f"{position_count}", "Positions", BLUE),
        (f"{entry_count}", "Entries", SUCCESS),
        (f"{exit_count}", "Exits", DANGER),
    ]
    
    box_x_start = (width - (box_width * 4 + 30)) // 2
    for i, (value, label, color) in enumerate(boxes):
        box_x = box_x_start + i * (box_width + 10)
        draw.rectangle([box_x, box_y, box_x + box_width, box_y + box_height], fill=CARD_BG, outline=color, width=2)
        draw.text((box_x + box_width // 2, box_y + 15), value, font=font_medium, fill=color, anchor="mt")
        draw.text((box_x + box_width // 2, box_y + 40), label, font=font_tiny, fill=TEXT_MUTED, anchor="mt")
    
    y = box_y + box_height + 25
    
    # Target Allocation Table
    draw.text((50, y), "📊 TARGET ALLOCATION", font=font_medium, fill=GOLD)
    y += 30
    
    # Table header - Ticker, Sector, Weight (no SBI)
    draw.rectangle([50, y, width - 50, y + 30], fill=CARD_BG)
    draw.text((70, y + 7), "Ticker", font=font_small, fill=TEXT_MUTED)
    draw.text((220, y + 7), "Sector", font=font_small, fill=TEXT_MUTED)
    draw.text((500, y + 7), "Weight", font=font_small, fill=TEXT_MUTED)
    y += 35
    
    # Build lookup from entry_signals for sector info
    entry_lookup = {}
    for sig in signal_data.get("entry_signals", []):
        if isinstance(sig, dict):
            ticker = sig.get("ticker")
            if ticker:
                entry_lookup[ticker] = sig.get("parent", "")
    
    # Table rows
    raw_allocations = signal_data.get("target_allocation", {})
    
    # Convert to list
    allocations = []
    if isinstance(raw_allocations, dict):
        for ticker, value in raw_allocations.items():
            weight = value if isinstance(value, (int, float)) else value.get("weight", 0)
            sector = entry_lookup.get(ticker, "")  # Get sector from entry_signals
            allocations.append({"ticker": ticker, "weight": weight, "sector": sector})
    elif isinstance(raw_allocations, list):
        allocations = raw_allocations
    
    # Sort by weight descending
    try:
        allocations = sorted(allocations, key=lambda x: x.get('weight', 0), reverse=True)
    except:
        pass
    
    display_allocations = allocations[:12]
    total_allocations = len(allocations)
    
    for pos in display_allocations:
        ticker = pos.get("ticker", "N/A")
        sector = pos.get("sector", "")
        weight = pos.get("weight", 0)
        
        # Row background
        draw.rectangle([50, y, width - 50, y + 28], fill=(20, 28, 40))
        
        # Ticker (bold green)
        draw.text((70, y + 5), ticker, font=font_normal, fill=SUCCESS)
        
        # Sector
        draw.text((220, y + 5), str(sector)[:20], font=font_normal, fill=TEXT_WHITE)
        
        # Weight
        weight_str = f"{weight * 100:.1f}%"
        draw.text((500, y + 5), weight_str, font=font_normal, fill=TEXT_WHITE)
        
        y += 30
    
    if total_allocations > 12:
        draw.text((70, y + 5), f"... and {total_allocations - 12} more", font=font_small, fill=TEXT_MUTED)
        y += 25
    
    y += 15
    
    # Active Sectors
    draw.text((50, y), "✅ ACTIVE SECTORS", font=font_medium, fill=SUCCESS)
    y += 28
    
    active_sectors = signal_data.get("active_sectors", [])
    
    # Handle different formats: list of strings or list of dicts
    sector_names = []
    for s in active_sectors[:10]:
        if isinstance(s, dict):
            sector_names.append(s.get('parent', s.get('ticker', 'N/A')))
        else:
            sector_names.append(str(s))
    
    sector_text = ", ".join(sector_names) if sector_names else "None"
    if len(active_sectors) > 10:
        sector_text += f" +{len(active_sectors) - 10} more"
    
    # Wrap text
    draw.text((60, y), sector_text if sector_text else "None", font=font_normal, fill=TEXT_WHITE)
    y += 30
    
    # Rotation Signals (only show if there are any)
    rotations = signal_data.get("rotation_signals", [])
    if rotations:
        draw.text((50, y), "🔄 ROTATION SIGNALS", font=font_medium, fill=YELLOW)
        y += 28
        for sig in rotations[:5]:
            if isinstance(sig, dict):
                from_t = sig.get("from_ticker", sig.get("from", "N/A"))
                to_t = sig.get("to_ticker", sig.get("to", "N/A"))
                sector = sig.get("sector", sig.get("parent", "N/A"))
                draw.text((60, y), f"• {from_t} → {to_t} ({sector})", font=font_normal, fill=YELLOW)
            else:
                draw.text((60, y), f"• {sig}", font=font_normal, fill=YELLOW)
            y += 24
        y += 10
    
    # Exit Signals (only show if there are any)
    exits = signal_data.get("exit_signals", [])
    if exits:
        draw.text((50, y), "🚨 EXIT SIGNALS", font=font_medium, fill=DANGER)
        y += 28
        for sig in exits[:5]:
            if isinstance(sig, dict):
                ticker = sig.get("ticker", "N/A")
                reason = sig.get("reason", "Sector bearish")
                draw.text((60, y), f"• {ticker}: {reason}", font=font_normal, fill=DANGER)
            else:
                draw.text((60, y), f"• {sig}", font=font_normal, fill=DANGER)
            y += 24
        y += 10
    
    # Performance box
    y = height - 180
    draw.rectangle([50, y, width - 50, y + 80], fill=CARD_BG, outline=GOLD, width=1)
    draw.text((width // 2, y + 10), "📈 BACKTEST PERFORMANCE (2022-2024)", font=font_small, fill=GOLD, anchor="mt")
    draw.text((width // 2, y + 35), "2022: +45% (SPY -19%)  |  2023: +70% (SPY +27%)  |  2024: +114% (SPY +26%)", font=font_small, fill=TEXT_WHITE, anchor="mt")
    draw.text((width // 2, y + 55), "Max Drawdown: ~5% vs SPY ~25%", font=font_small, fill=SUCCESS, anchor="mt")
    
    # Disclaimer
    y = height - 90
    draw.line([(50, y), (width - 50, y)], fill=(50, 60, 80), width=1)
    y += 10
    
    disclaimer = [
        "⚠️ DISCLAIMER: This is NOT financial advice.",
        "For educational purposes only. Past performance ≠ future results.",
        "You are responsible for your own investment decisions."
    ]
    for line in disclaimer:
        draw.text((width // 2, y), line, font=font_tiny, fill=TEXT_MUTED, anchor="mt")
        y += 16
    
    # Save
    img.save(output_path, "PNG", quality=95)
    print(f"✅ Image saved: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Generate SectorBot signal image')
    parser.add_argument('--json', type=str, default='sectorbot_allocation.json', help='Path to signal JSON file')
    parser.add_argument('--output', type=str, default='sectorbot_signal.png', help='Output image path')
    
    args = parser.parse_args()
    
    signal_data = load_signal_data(args.json)
    create_signal_image(signal_data, args.output)


if __name__ == "__main__":
    main()
