"""Canonical category ordering for Chess Log presets.

Provides the authoritative display ordering for CLAMP and CCT category names
so chart legends and tag dialogs stay in sync.
"""

from __future__ import annotations

from typing import List, Tuple

CLAMP_ORDER: Tuple[str, ...] = ("C", "L", "A", "M", "P")
CCT_ORDER: Tuple[str, ...] = ("Checks", "Captures", "Threats")


def order_categories(
    preset: str,
    present: List[str],
) -> List[str]:
    """Return `present` reordered per canonical preset order.

    Rules:
    - Known categories come first, in canonical order.
    - Unknown categories (unexpected values) are appended alphabetically.
    - Empty string (uncategorized) is always last.

    Args:
        preset: Preset name ("CLAMP", "CCT", or other).
        present: Categories actually present in the data.
    """
    if preset == "CLAMP":
        canonical = list(CLAMP_ORDER)
    elif preset == "CCT":
        canonical = list(CCT_ORDER)
    else:
        canonical = []

    present_set = set(present)
    known = [c for c in canonical if c in present_set]
    known_set = set(known)
    unknown = sorted(c for c in present_set if c not in known_set and c != "")
    uncategorized = [""] if "" in present_set else []
    return known + unknown + uncategorized
