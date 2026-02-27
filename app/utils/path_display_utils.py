"""Utility functions for displaying file system paths in the UI.

Provides path truncation that respects actual pixel width and font metrics
(DPI scaling, user font size) so paths fit on one line without word wrap.
"""

from pathlib import Path
from typing import Union

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontMetrics


def truncate_path_for_display(
    path: Union[Path, str],
    max_width_px: int,
    font: QFont,
    ellipsis: str = "...",
) -> str:
    """Truncate a path in the middle so it fits within a given pixel width.

    Uses the provided font and QFontMetrics to measure text width, so the result
    respects user font size, font family, and DPI scaling. The path is shown
    as prefix + ellipsis + filename (e.g. C:\\Programs\\MyEngines\\...\\Stockfish.exe).

    Args:
        path: Path or path string to truncate.
        max_width_px: Maximum width in pixels the truncated string may occupy
            when rendered with the given font.
        font: Font used to render the path (determines actual width and DPI).
        ellipsis: String inserted between prefix and filename (default "...").

    Returns:
        Truncated path string that fits in max_width_px when drawn with font.
        If the full path fits, it is returned unchanged.
    """
    path_obj = Path(path) if isinstance(path, str) else path
    path_str = str(path_obj)
    metrics = QFontMetrics(font)

    if metrics.horizontalAdvance(path_str) <= max_width_px:
        return path_str

    name = path_obj.name
    ellipsis_width = metrics.horizontalAdvance(ellipsis)
    name_width = metrics.horizontalAdvance(name)

    if ellipsis_width + name_width > max_width_px:
        # Filename alone is too wide: show ellipsis + end of filename
        available = max_width_px - ellipsis_width
        if available <= 0:
            return ellipsis
        # Elide from the left so the extension and end of name stay visible
        return ellipsis + _elide_to_width(name, available, font, from_left=True)

    # Build prefix (path without filename) and shorten until it fits.
    # Result format: prefix + ellipsis + sep + name (e.g. C:\Programs\...\Stockfish.exe)
    sep = "\\" if "\\" in path_str else "/"
    try:
        parent = path_obj.parent
        prefix = str(parent) + sep if str(parent) != "." else ""
    except (ValueError, OSError):
        prefix = path_str[: path_str.rfind(sep) + 1] if sep in path_str else ""

    suffix = ellipsis + sep + name
    candidate = prefix + suffix
    while metrics.horizontalAdvance(candidate) > max_width_px and prefix:
        prefix = prefix.rstrip(sep)
        if not prefix:
            return ellipsis + sep + name
        last_sep = prefix.rfind(sep)
        if last_sep >= 0:
            prefix = prefix[: last_sep + 1]
        else:
            prefix = ""
        candidate = prefix + suffix

    return candidate if prefix else ellipsis + sep + name


def _elide_to_width(
    text: str, max_width_px: int, font: QFont, from_left: bool = False
) -> str:
    """Return text elided to fit max_width_px; optionally elide from the left."""
    metrics = QFontMetrics(font)
    if metrics.horizontalAdvance(text) <= max_width_px:
        return text
    if from_left:
        # Keep the end of the string (e.g. filename.extension)
        lead = "…"
        lead_width = metrics.horizontalAdvance(lead)
        available = max_width_px - lead_width
        for i in range(len(text), 0, -1):
            tail = text[-i:]
            if metrics.horizontalAdvance(tail) <= available:
                return lead + tail
        return lead + text[-1] if text else lead
    # Elide from the right (standard)
    return metrics.elidedText(text, Qt.TextElideMode.ElideMiddle, max_width_px)
