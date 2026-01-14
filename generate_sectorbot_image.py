#!/usr/bin/env python3
"""
AdaptiveX2 SectorBot Daily Signal Image Generator
Parent signal (PSAR) → Individual stocks (SBI=10)

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
CYAN = (34, 211, 238)


def get_sample_data():
    """Return sample data for testing/demo."""
    return {
        "generated_at": datetime.now().isoformat(),
        "strategy": "AdaptiveX2 SectorBot",
        
        # Parent sectors and their status
        "parent_signals": [
            {"parent": "BTC-USD", "name": "Bitcoin", "psar_status": "BULLISH", "psar_trend_days": 12},
            {"parent": "GLD", "name": "Gold", "psar_status": "BULLISH", "psar_trend_days": 8},
            {"parent": "XLK", "name": "Technology", "psar_status": "BEARISH", "psar_trend_days": 3},
            {"parent": "XLV", "name": "Healthcare", "psar_status": "BULLISH", "psar_trend_days": 5},
            {"parent": "SMH", "name": "Semiconductors", "psar_status": "BEARISH", "psar_trend_days": 2},
            {"parent": "XLE", "name": "Energy", "psar_status": "BEARISH", "psar_trend_days": 15},
        ],
        
        # Current positions (stocks held)
        "target_allocation": [
            {"ticker": "MSTR", "parent": "BTC-USD", "weight": 0.15, "sbi": 10, "entry_date": "2025-01-02"},
            {"ticker": "COIN", "parent": "BTC-USD", "weight": 0.10, "sbi": 10, "entry_date": "2025-01-02"},
            {"ticker": "GFI", "parent": "GLD", "weight": 0.10, "sbi": 10, "entry_date": "2025-01-05"},
            {"ticker": "NEM", "parent": "GLD", "weight": 0.10, "sbi": 10, "entry_date": "2025-01-05"},
            {"ticker": "AEM", "parent": "GLD", "weight": 0.08, "sbi": 9, "entry_date": "2025-01-06"},
            {"ticker": "LLY", "parent": "XLV", "weight": 0.12, "sbi": 10, "entry_date": "2025-01-10"},
            {"ticker": "UNH", "parent": "XLV", "weight": 0.10, "sbi": 10, "entry_date": "2025-01-10"},
        ],
        
        # Today's signals
        "entry_signals": [
            {"ticker": "ABBV", "parent": "XLV", "sbi": 10, "reason": "New SBI=10 in bullish sector"},
        ],
        
        "rotation_signals": [
            {"from_ticker": "MARA", "to_ticker": "CLSK", "parent": "BTC-USD", "reason": "SBI 7->10"},
        ],
        
        "exit_signals": [
            {"ticker": "NVDA", "parent": "SMH", "reason": "Parent turned bearish"},
            {"ticker": "AMD", "parent": "SMH", "reason": "Parent turned bearish"},
        ],
        
        # Backtest stats (placeholder)
        "backtest": {
            "total_return": "+285%",
            "spy_return": "+52%",
            "max_drawdown": "-12%",
            "sharpe": 1.45,
        }
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


def draw_rounded_rect(draw, coords, radius, fill, outline=None, width=1):
    """Draw a rounded rectangle."""
    x1, y1, x2, y2 = coords
    draw.rounded_rectangle(coords, radius=radius, fill=fill, outline=outline, width=width)


def create_signal_image(signal_data: dict, output_path: str = "sectorbot_signal.png"):
    """Generate the SectorBot signal PNG image."""
    
    if not isinstance(signal_data, dict):
        signal_data = get_sample_data()
    
    # Image dimensions
    width = 850
    height = 1100
    
    img = Image.new('RGB', (width, height), DARK_BG)
    draw = ImageDraw.Draw(img)
    
    # Fonts
    font_title = get_font(28, bold=True)
    font_subtitle = get_font(16)
    font_section = get_font(18, bold=True)
    font_normal = get_font(15)
    font_small = get_font(13)
    font_tiny = get_font(11)
    
    y = 25
    
    # === HEADER ===
    draw.text((width // 2, y), "AdaptiveX2 SectorBot", font=font_title, fill=GOLD, anchor="mt")
    y += 35
    
    draw.text((width // 2, y), "Parent Signal + SBI Stock Selection", font=font_small, fill=TEXT_MUTED, anchor="mt")
    y += 25
    
    # Date
    generated = signal_data.get("generated_at", datetime.now().isoformat())
    try:
        dt = datetime.fromisoformat(str(generated).replace('Z', '+00:00'))
        date_str = dt.strftime("%B %d, %Y")
    except:
        date_str = datetime.now().strftime("%B %d, %Y")
    
    draw.text((width // 2, y), date_str, font=font_subtitle, fill=TEXT_WHITE, anchor="mt")
    y += 35
    
    # Divider
    draw.line([(40, y), (width - 40, y)], fill=GOLD, width=2)
    y += 20
    
    # === PARENT SIGNALS SECTION ===
    draw.text((50, y), "PARENT SIGNALS (PSAR)", font=font_section, fill=GOLD)
    y += 30
    
    parent_signals = signal_data.get("parent_signals", [])
    
    # Create cards for parent signals
    card_width = 125
    card_height = 55
    cards_per_row = 6
    card_spacing = 8
    total_cards_width = cards_per_row * card_width + (cards_per_row - 1) * card_spacing
    start_x = (width - total_cards_width) // 2
    
    for i, parent in enumerate(parent_signals[:12]):
        row = i // cards_per_row
        col = i % cards_per_row
        
        x = start_x + col * (card_width + card_spacing)
        card_y = y + row * (card_height + 8)
        
        ticker = parent.get("parent", "N/A")
        name = parent.get("name", ticker)
        status = parent.get("psar_status", "UNKNOWN")
        days = parent.get("psar_trend_days", 0)
        
        # Card color based on status
        if status == "BULLISH":
            outline_color = SUCCESS
            status_text = f"+ Day {days}"
        else:
            outline_color = DANGER
            status_text = f"- Day {days}"
        
        draw_rounded_rect(draw, (x, card_y, x + card_width, card_y + card_height), 
                         radius=6, fill=CARD_BG, outline=outline_color, width=2)
        
        # Ticker
        draw.text((x + card_width // 2, card_y + 12), ticker, font=font_small, fill=TEXT_WHITE, anchor="mt")
        # Status
        status_color = SUCCESS if status == "BULLISH" else DANGER
        draw.text((x + card_width // 2, card_y + 32), status_text, font=font_tiny, fill=status_color, anchor="mt")
    
    rows_used = (len(parent_signals[:12]) + cards_per_row - 1) // cards_per_row
    y += rows_used * (card_height + 8) + 25
    
    # === CURRENT POSITIONS ===
    draw.text((50, y), "CURRENT POSITIONS", font=font_section, fill=GOLD)
    y += 28
    
    # Table header
    draw.rectangle([50, y, width - 50, y + 28], fill=CARD_BG)
    draw.text((70, y + 6), "Ticker", font=font_small, fill=TEXT_MUTED)
    draw.text((180, y + 6), "Parent", font=font_small, fill=TEXT_MUTED)
    draw.text((320, y + 6), "Weight", font=font_small, fill=TEXT_MUTED)
    draw.text((420, y + 6), "SBI", font=font_small, fill=TEXT_MUTED)
    draw.text((500, y + 6), "Entry", font=font_small, fill=TEXT_MUTED)
    y += 32
    
    allocations = signal_data.get("target_allocation", [])
    if isinstance(allocations, dict):
        allocations = [{"ticker": k, "weight": v} for k, v in allocations.items()]
    
    # Sort by weight
    try:
        allocations = sorted(allocations, key=lambda x: x.get('weight', 0), reverse=True)
    except:
        pass
    
    for pos in allocations[:10]:
        ticker = pos.get("ticker", "N/A")
        parent = pos.get("parent", "-")
        weight = pos.get("weight", 0)
        sbi = pos.get("sbi", "-")
        entry = pos.get("entry_date", "-")
        if entry and len(entry) > 5:
            entry = entry[5:]  # Just MM-DD
        
        # Alternating row bg
        row_bg = (18, 24, 35) if allocations.index(pos) % 2 == 0 else DARK_BG
        draw.rectangle([50, y, width - 50, y + 26], fill=row_bg)
        
        draw.text((70, y + 5), ticker, font=font_normal, fill=SUCCESS)
        draw.text((180, y + 5), str(parent)[:12], font=font_normal, fill=CYAN)
        draw.text((320, y + 5), f"{weight * 100:.1f}%", font=font_normal, fill=TEXT_WHITE)
        
        sbi_color = SUCCESS if sbi == 10 else YELLOW if sbi == 9 else TEXT_MUTED
        draw.text((420, y + 5), str(sbi), font=font_normal, fill=sbi_color)
        draw.text((500, y + 5), str(entry), font=font_normal, fill=TEXT_MUTED)
        
        y += 28
    
    if len(allocations) > 10:
        draw.text((70, y + 3), f"... +{len(allocations) - 10} more positions", font=font_small, fill=TEXT_MUTED)
        y += 22
    
    y += 15
    
    # === ENTRY SIGNALS ===
    entries = signal_data.get("entry_signals", [])
    if entries:
        draw.text((50, y), ">> ENTRY SIGNALS", font=font_section, fill=SUCCESS)
        y += 26
        for sig in entries[:5]:
            ticker = sig.get("ticker", "N/A")
            parent = sig.get("parent", "-")
            sbi = sig.get("sbi", 10)
            draw.text((70, y), f"BUY {ticker}", font=font_normal, fill=SUCCESS)
            draw.text((200, y), f"Parent: {parent}", font=font_small, fill=CYAN)
            draw.text((380, y), f"SBI: {sbi}", font=font_small, fill=SUCCESS)
            y += 24
        y += 10
    
    # === ROTATION SIGNALS ===
    rotations = signal_data.get("rotation_signals", [])
    if rotations:
        draw.text((50, y), "<> ROTATION SIGNALS", font=font_section, fill=YELLOW)
        y += 26
        for sig in rotations[:5]:
            from_t = sig.get("from_ticker", "?")
            to_t = sig.get("to_ticker", "?")
            parent = sig.get("parent", "-")
            draw.text((70, y), f"{from_t} -> {to_t}", font=font_normal, fill=YELLOW)
            draw.text((250, y), f"({parent})", font=font_small, fill=TEXT_MUTED)
            y += 24
        y += 10
    
    # === EXIT SIGNALS ===
    exits = signal_data.get("exit_signals", [])
    if exits:
        draw.text((50, y), "!! EXIT SIGNALS", font=font_section, fill=DANGER)
        y += 26
        for sig in exits[:5]:
            ticker = sig.get("ticker", "N/A")
            reason = sig.get("reason", "Parent bearish")
            draw.text((70, y), f"SELL {ticker}", font=font_normal, fill=DANGER)
            draw.text((200, y), reason[:40], font=font_small, fill=TEXT_MUTED)
            y += 24
        y += 10
    
    # === STRATEGY SUMMARY BOX ===
    y = height - 200
    draw.rectangle([40, y, width - 40, y + 100], fill=CARD_BG, outline=GOLD, width=1)
    
    draw.text((width // 2, y + 12), "STRATEGY RULES", font=font_section, fill=GOLD, anchor="mt")
    
    rules = [
        "1. Enter stocks with SBI=10 when Parent PSAR is BULLISH",
        "2. Hold position as long as Parent stays BULLISH",
        "3. Exit ALL positions in sector when Parent turns BEARISH",
        "4. No 2x leverage - individual stocks only"
    ]
    
    rule_y = y + 35
    for rule in rules:
        draw.text((60, rule_y), rule, font=font_small, fill=TEXT_WHITE)
        rule_y += 18
    
    # === DISCLAIMER ===
    y = height - 85
    draw.line([(40, y), (width - 40, y)], fill=(50, 60, 80), width=1)
    y += 12
    
    disclaimer = [
        "DISCLAIMER: NOT financial advice. Educational purposes only.",
        "GL Tradewinds LLC | Past performance does not guarantee future results.",
    ]
    for line in disclaimer:
        draw.text((width // 2, y), line, font=font_tiny, fill=TEXT_MUTED, anchor="mt")
        y += 16
    
    # Save
    img.save(output_path, "PNG", quality=95)
    print(f"[OK] Image saved: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description='Generate AdaptiveX2 SectorBot signal image')
    parser.add_argument('--json', type=str, help='Path to signal JSON file')
    parser.add_argument('--output', type=str, default='sectorbot_signal.png', help='Output image path')
    parser.add_argument('--sample', action='store_true', help='Use sample data')
    
    args = parser.parse_args()
    
    if args.sample or not args.json:
        signal_data = get_sample_data()
    else:
        try:
            with open(args.json, 'r') as f:
                signal_data = json.load(f)
        except Exception as e:
            print(f"Failed to load {args.json}: {e}")
            signal_data = get_sample_data()
    
    create_signal_image(signal_data, args.output)


if __name__ == "__main__":
    main()
