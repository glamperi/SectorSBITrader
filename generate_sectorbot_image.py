#!/usr/bin/env python3
"""
AdaptiveX2 SectorBot Daily Signal Image Generator
SIMPLIFIED VERSION - Clean, clear signals only

Usage:
    python generate_sectorbot_image.py --json sectorbot_signals.json
    python generate_sectorbot_image.py --output my_signal.png
"""

from PIL import Image, ImageDraw, ImageFont
import json
import argparse
from datetime import datetime

# Colors
DARK_BG = (10, 14, 23)
CARD_BG = (26, 35, 50)
GOLD = (212, 165, 75)
TEXT_WHITE = (229, 231, 235)
TEXT_MUTED = (156, 163, 175)
SUCCESS = (34, 197, 94)
DANGER = (239, 68, 68)
YELLOW = (234, 179, 8)
CYAN = (34, 211, 238)


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
    """Generate clean SectorBot signal PNG."""
    
    # Image dimensions
    width = 700
    height = 900
    
    img = Image.new('RGB', (width, height), DARK_BG)
    draw = ImageDraw.Draw(img)
    
    # Fonts
    font_title = get_font(32, bold=True)
    font_subtitle = get_font(16)
    font_section = get_font(20, bold=True)
    font_normal = get_font(16)
    font_small = get_font(14)
    font_tiny = get_font(12)
    
    y = 30
    
    # === HEADER ===
    draw.text((width // 2, y), "AdaptiveX2 SectorBot", font=font_title, fill=GOLD, anchor="mt")
    y += 45
    
    # Date
    timestamp = signal_data.get("timestamp", datetime.now().isoformat())
    try:
        dt = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
        date_str = dt.strftime("%B %d, %Y")
    except:
        date_str = datetime.now().strftime("%B %d, %Y")
    
    draw.text((width // 2, y), date_str, font=font_subtitle, fill=TEXT_WHITE, anchor="mt")
    y += 35
    
    # Divider
    draw.line([(50, y), (width - 50, y)], fill=GOLD, width=2)
    y += 25
    
    # === ACTIVE SECTORS (Bullish Parents) ===
    draw.text((50, y), "BULLISH SECTORS", font=font_section, fill=GOLD)
    y += 35
    
    active_sectors = signal_data.get("active_sectors", [])
    sector_status = signal_data.get("sector_status", {})
    
    if active_sectors:
        # Create cards for bullish sectors
        card_width = 95
        card_height = 50
        cards_per_row = 6
        card_spacing = 8
        total_cards_width = min(len(active_sectors), cards_per_row) * card_width + (min(len(active_sectors), cards_per_row) - 1) * card_spacing
        start_x = (width - total_cards_width) // 2
        
        for i, sector in enumerate(active_sectors[:12]):
            row = i // cards_per_row
            col = i % cards_per_row
            
            x = start_x + col * (card_width + card_spacing)
            card_y = y + row * (card_height + 8)
            
            # Get sector info
            info = sector_status.get(sector, {})
            days = info.get("days_bullish", 0)
            
            # Draw card
            draw.rounded_rectangle(
                (x, card_y, x + card_width, card_y + card_height),
                radius=6, fill=CARD_BG, outline=SUCCESS, width=2
            )
            
            # Sector name
            draw.text((x + card_width // 2, card_y + 12), sector, font=font_small, fill=TEXT_WHITE, anchor="mt")
            # Days bullish
            draw.text((x + card_width // 2, card_y + 32), f"Day {days}", font=font_tiny, fill=SUCCESS, anchor="mt")
        
        rows_used = (len(active_sectors[:12]) + cards_per_row - 1) // cards_per_row
        y += rows_used * (card_height + 8) + 25
    else:
        draw.text((width // 2, y), "No bullish sectors today", font=font_normal, fill=TEXT_MUTED, anchor="mt")
        y += 35
    
    y += 10
    
    # === TODAY'S BUY SIGNALS ===
    draw.text((50, y), "TODAY'S BUY SIGNALS", font=font_section, fill=SUCCESS)
    y += 35
    
    entry_signals = signal_data.get("entry_signals", [])
    
    if entry_signals:
        # Table header
        draw.rectangle([50, y, width - 50, y + 30], fill=CARD_BG)
        draw.text((70, y + 7), "Ticker", font=font_small, fill=TEXT_MUTED)
        draw.text((180, y + 7), "Sector", font=font_small, fill=TEXT_MUTED)
        draw.text((320, y + 7), "SBI", font=font_small, fill=TEXT_MUTED)
        draw.text((420, y + 7), "RSI", font=font_small, fill=TEXT_MUTED)
        draw.text((520, y + 7), "Action", font=font_small, fill=TEXT_MUTED)
        y += 35
        
        for i, sig in enumerate(entry_signals[:10]):
            ticker = sig.get("ticker", "?")
            parent = sig.get("parent", "?")
            sbi = sig.get("sbi", "?")
            rsi = sig.get("rsi", 0)
            
            # Alternating row bg
            row_bg = (18, 24, 35) if i % 2 == 0 else DARK_BG
            draw.rectangle([50, y, width - 50, y + 32], fill=row_bg)
            
            # Ticker (bold, green)
            draw.text((70, y + 8), ticker, font=font_normal, fill=SUCCESS)
            # Parent sector
            draw.text((180, y + 8), parent, font=font_normal, fill=CYAN)
            # SBI score
            sbi_color = SUCCESS if sbi == 10 else YELLOW if sbi == 9 else TEXT_MUTED
            draw.text((320, y + 8), str(sbi), font=font_normal, fill=sbi_color)
            # RSI
            draw.text((420, y + 8), f"{rsi:.0f}" if isinstance(rsi, float) else str(rsi), font=font_normal, fill=TEXT_WHITE)
            # Action
            draw.text((520, y + 8), "BUY", font=font_normal, fill=SUCCESS)
            
            y += 34
    else:
        draw.text((width // 2, y + 10), "No new buy signals today", font=font_normal, fill=TEXT_MUTED, anchor="mt")
        y += 50
    
    y += 20
    
    # === EXIT SIGNALS (if any) ===
    exit_signals = signal_data.get("exit_signals", [])
    if exit_signals:
        draw.text((50, y), "EXIT SIGNALS", font=font_section, fill=DANGER)
        y += 30
        
        for sig in exit_signals[:5]:
            ticker = sig.get("ticker", "?")
            reason = sig.get("reason", "Parent bearish")
            draw.text((70, y), f"SELL {ticker}", font=font_normal, fill=DANGER)
            draw.text((200, y), reason[:35], font=font_small, fill=TEXT_MUTED)
            y += 28
        y += 15
    
    # === ROTATION SIGNALS (if any) ===
    rotation_signals = signal_data.get("rotation_signals", [])
    if rotation_signals:
        draw.text((50, y), "ROTATION SIGNALS", font=font_section, fill=YELLOW)
        y += 30
        
        for sig in rotation_signals[:5]:
            exit_info = sig.get("exit", {})
            enter_info = sig.get("enter", {})
            from_t = exit_info.get("ticker", "?")
            to_t = enter_info.get("ticker", "?")
            draw.text((70, y), f"{from_t} → {to_t}", font=font_normal, fill=YELLOW)
            y += 28
        y += 15
    
    # === STRATEGY BOX (at bottom) ===
    box_y = height - 180
    draw.rectangle([40, box_y, width - 40, box_y + 90], fill=CARD_BG, outline=GOLD, width=1)
    
    draw.text((width // 2, box_y + 12), "STRATEGY RULES", font=font_section, fill=GOLD, anchor="mt")
    
    rules = [
        "• Enter stocks with SBI ≥ 9 when Parent PSAR is BULLISH",
        "• Exit ALL positions when Parent turns BEARISH",
        "• Individual stocks only (no leveraged ETFs)"
    ]
    
    rule_y = box_y + 38
    for rule in rules:
        draw.text((60, rule_y), rule, font=font_small, fill=TEXT_WHITE)
        rule_y += 18
    
    # === DISCLAIMER ===
    y = height - 70
    draw.line([(50, y), (width - 50, y)], fill=(50, 60, 80), width=1)
    y += 15
    
    disclaimer = [
        "NOT financial advice. Educational purposes only.",
        "GL Tradewinds LLC | Past performance ≠ future results"
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
    parser.add_argument('--json', type=str, required=True, help='Path to signal JSON file')
    parser.add_argument('--output', type=str, default='sectorbot_signal.png', help='Output image path')
    
    args = parser.parse_args()
    
    try:
        with open(args.json, 'r') as f:
            signal_data = json.load(f)
        create_signal_image(signal_data, args.output)
    except Exception as e:
        print(f"❌ Error: {e}")
        raise


if __name__ == "__main__":
    main()
