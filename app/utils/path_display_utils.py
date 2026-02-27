"""Utility functions for displaying file system paths and text in the UI.

Provides middle truncation that respects actual pixel width and font metrics
(DPI scaling, user font size) so text fits on one line without word wrap.
"""

from pathlib import Path
from typing import Union

from PyQt6.QtGui import QFont, QFontMetrics


def truncate_text_middle(
    text: str,
    max_width_px: int,
    font: QFont,
    ellipsis: str = "...",
) -> str:
    """Truncate a string in the middle so it fits within a given pixel width.

    Shows start + ellipsis + end. Uses the provided font and QFontMetrics so the
    result respects DPI and font size. Reused for paths and filenames.

    Args:
        text: String to truncate.
        max_width_px: Maximum width in pixels when rendered with the given font.
        font: Font used to render the text.
        ellipsis: String inserted in the middle (default "...").

    Returns:
        Truncated string that fits in max_width_px, or the original if it already fits.
    """
    if not text:
        return text
    metrics = QFontMetrics(font)
    if metrics.horizontalAdvance(text) <= max_width_px:
        return text

    ellipsis_width = metrics.horizontalAdvance(ellipsis)
    available = max_width_px - ellipsis_width
    if available <= 0:
        return ellipsis

    n = len(text)
    max_suffix_width = available // 2
    suffix_width = metrics.horizontalAdvance(text)
    j = 0
    while j < n and suffix_width > max_suffix_width:
        j += 1
        if j < n:
            suffix_width = metrics.horizontalAdvance(text[j:])
    suffix = text[j:] if j < n else text[-1:]
    suffix_width = metrics.horizontalAdvance(suffix)

    remaining = available - suffix_width
    if remaining <= 0:
        return ellipsis + suffix

    prefix = ""
    for i in range(j, -1, -1):
        part = text[:i]
        if metrics.horizontalAdvance(part) <= remaining:
            prefix = part
            break

    return prefix + ellipsis + suffix


def truncate_path_for_display(
    path: Union[Path, str],
    max_width_px: int,
    font: QFont,
    ellipsis: str = "...",
) -> str:
    """Truncate a path in the middle so it fits within a given pixel width.

    Delegates to truncate_text_middle with the path as a string.
    """
    path_str = str(Path(path) if isinstance(path, str) else path)
    return truncate_text_middle(path_str, max_width_px, font, ellipsis)
