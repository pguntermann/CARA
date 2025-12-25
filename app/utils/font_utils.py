"""Utility functions for font handling."""

from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication
from typing import Optional

# Cache for DPI multiplier (calculated once at startup)
_dpi_multiplier_cache: Optional[float] = None


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


def get_font_size_multiplier() -> float:
    """Get font size multiplier based on screen DPI.
    
    Returns a multiplier to apply to base font sizes to ensure
    consistent visual appearance across different displays.
    
    The multiplier is calculated based on the screen's logical DPI:
    - At 96 DPI (Windows default): multiplier = 1.0
    - At 72 DPI (macOS default): multiplier = 1.33 (larger fonts)
    - At 144 DPI (Retina): multiplier = 0.67 (smaller fonts)
    
    The multiplier is cached after first calculation since DPI doesn't
    change during application runtime.
    
    Returns:
        Multiplier (typically 0.8-1.5x depending on DPI)
    """
    global _dpi_multiplier_cache
    
    # Return cached value if available
    if _dpi_multiplier_cache is not None:
        return _dpi_multiplier_cache
    
    # Try to get QApplication instance
    app = QApplication.instance()
    if app is None:
        # No QApplication yet, return default
        _dpi_multiplier_cache = 1.0
        return _dpi_multiplier_cache
    
    # Get primary screen
    screen = app.primaryScreen()
    if screen is None:
        _dpi_multiplier_cache = 1.0
        return _dpi_multiplier_cache
    
    # Get logical DPI (what Qt uses for font rendering)
    logical_dpi = screen.logicalDotsPerInch()
    
    # Standard reference: 96 DPI (Windows default)
    # Calculate multiplier: higher DPI = smaller multiplier needed
    # Formula: scale based on ratio to 96 DPI
    base_dpi = 96.0
    multiplier = base_dpi / logical_dpi
    
    # Clamp to reasonable range (0.8x to 1.5x)
    multiplier = max(0.8, min(1.5, multiplier))
    
    # Cache the result
    _dpi_multiplier_cache = multiplier
    return multiplier


def scale_font_size(base_size: float) -> int:
    """Scale a font size based on screen DPI.
    
    Convenience function that applies the DPI multiplier to a base font size.
    
    Args:
        base_size: Base font size in points.
        
    Returns:
        Scaled font size in points as an integer.
    """
    return int(round(base_size * get_font_size_multiplier()))

