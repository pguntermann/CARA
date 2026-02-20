"""Utility functions for tooltip formatting."""

from typing import Optional


def wrap_tooltip_text(text: str) -> str:
    """Wrap plain text tooltip in HTML for automatic word-wrapping.
    
    Qt tooltips only wrap automatically when formatted as rich text (HTML).
    This function wraps plain text in HTML to enable automatic word-wrapping
    using Qt's default tooltip width.
    
    Args:
        text: Plain text tooltip content.
        
    Returns:
        HTML-wrapped tooltip text that will automatically wrap at Qt's default width.
    """
    # If text is already HTML (starts with <), return as-is
    if text.strip().startswith('<'):
        return text
    
    # Escape HTML special characters
    escaped_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    
    # Wrap in HTML - Qt will automatically word-wrap rich text at its default width
    return f'<html>{escaped_text}</html>'
