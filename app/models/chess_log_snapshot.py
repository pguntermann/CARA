"""Data containers for Chess Log PDF export snapshots."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

import chess


@dataclass
class TagRowSnapshot:
    """Immutable snapshot of one _TagRowWidget's current state for PDF export."""

    move_label: str
    preset: str
    entries: List[Dict[str, Any]]
    fen: Optional[str]
    played_move: Optional[chess.Move]
    show_ignore: bool
    best_move: Optional[chess.Move] = field(default=None)
    is_flipped: bool = field(default=False)
    is_shallow: bool = field(default=False)
    is_vague: bool = field(default=False)
    # Per-category flag sets for 3x3 rows (empty for CLAMP/CCT).
    # shallow_cats: which of Why1/Why2/Why3 are flagged GENERIC.
    # vague_cats: {"Why4"} when the lesson is FILLER, else empty.
    shallow_cats: FrozenSet[str] = field(default_factory=frozenset)
    vague_cats: FrozenSet[str] = field(default_factory=frozenset)
