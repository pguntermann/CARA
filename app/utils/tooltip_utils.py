"""Utility functions for tooltip formatting."""


def wrap_tooltip_text(text: str) -> str:
    """Wrap plain text tooltip in HTML for themed QToolTip rendering.

    Qt rich-text tips wrap to the hovered widget's width, which cramps short
    labels. Multi-line tips keep each line intact; a single paragraph still
    wraps inside a bounded width.
    """
    if text.strip().startswith('<'):
        return text

    escaped_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    lines = escaped_text.split('\n')
    if len(lines) == 1:
        return (
            f'<html><div style="min-width: 220px; max-width: 360px;">'
            f'{lines[0]}</div></html>'
        )
    inner = "".join(
        f'<div style="white-space: nowrap;">{line}</div>' for line in lines
    )
    return f"<html>{inner}</html>"
