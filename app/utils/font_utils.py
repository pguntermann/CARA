"""Utility functions for font handling."""

from PyQt6.QtGui import QFontDatabase
from typing import Optional


def resolve_font_family(font_family: str) -> str:
    """Resolve font family with fallback support.
    
    If font_family contains comma-separated fonts (e.g., "Cascadia Mono, Menlo"),
    returns the first available font. This prevents PyQt from trying to load
    missing fonts, which causes performance warnings.
    
    Args:
        font_family: Font family string, possibly with comma-separated fallbacks.
        
    Returns:
        First available font family, or the first one in the list if none found
        (Qt will handle fallback in that case).
    """
    if not font_family or ',' not in font_family:
        return font_family
    
    # Split by comma and try each font
    fonts = [f.strip() for f in font_family.split(',')]
    available_fonts = set(QFontDatabase.families())
    
    for font in fonts:
        # Check exact match
        if font in available_fonts:
            return font
        # Check case-insensitive match
        for available in available_fonts:
            if available.lower() == font.lower():
                return available
    
    # If none found, return the first one (Qt will handle fallback)
    return fonts[0] if fonts else font_family

