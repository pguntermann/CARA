"""Utilities for CARA per-game tagging stored in PGN metadata."""

from __future__ import annotations

from typing import Iterable, List


PGN_TAG_NAME_GAME_TAGS = "CARAGameTags"


def parse_game_tags(raw_value: str) -> List[str]:
    """Parse semicolon-separated tags from a PGN header value.

    Rules (v1):
    - Split on ';'
    - Trim whitespace
    - Drop empty entries
    - De-duplicate case-insensitively (keep first occurrence's casing)
    """
    if not raw_value:
        return []
    parts = [p.strip() for p in str(raw_value).split(";")]
    result: List[str] = []
    seen_lower = set()
    for p in parts:
        if not p:
            continue
        key = p.casefold()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        result.append(p)
    return result


def format_game_tags(tags: Iterable[str]) -> str:
    """Format tags as a semicolon-separated string suitable for PGN header storage."""
    cleaned: List[str] = []
    seen_lower = set()
    for t in tags or []:
        if t is None:
            continue
        name = str(t).strip()
        if not name:
            continue
        # Semicolon is reserved as delimiter in v1
        if ";" in name:
            name = name.replace(";", "")
            name = name.strip()
            if not name:
                continue
        key = name.casefold()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        cleaned.append(name)
    return ";".join(cleaned)


def tags_display_text(tags: Iterable[str]) -> str:
    """Human-readable display value for database column / UI labels."""
    items = [str(t).strip() for t in (tags or []) if str(t).strip()]
    return ", ".join(items)

