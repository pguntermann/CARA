"""Shared loaders for opening-book integrity tests."""

from __future__ import annotations

import os
import sys
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.opening_encyclopedia_service import OpeningEncyclopediaService
from app.services.opening_service import (
    OpeningService,
    fen_after_sans,
    parse_move_sans,
)

# GitHub Actions sets CI=true; keep this suite local-only (~1 min book scan).
SKIP_IN_CI = os.environ.get("CI", "").strip().lower() in {"1", "true", "yes"}
SKIP_REASON = "opening integrity suite is local-only (not run on GitHub CI)"


def load_tests_if_not_ci(loader, standard_tests, pattern):  # type: ignore[no-untyped-def]
    """Hook for unittest discover: omit this package when CI is set."""
    if SKIP_IN_CI:
        return unittest.TestSuite()
    return standard_tests

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.services.opening_encyclopedia_service import OpeningEncyclopediaService
from app.services.opening_service import (
    OpeningService,
    fen_after_sans,
    parse_move_sans,
)

CONFIG: Dict[str, Any] = {
    "resources": {
        "ecolists_path": str(REPO_ROOT / "app/resources/ecolists"),
        "encyclopedia_db_path": str(REPO_ROOT / "app/resources/encyclopedia/openings.db"),
    }
}


@dataclass(frozen=True)
class BaseRow:
    fen: str
    eco: str
    name: str
    moves: str
    src: str


def opening_service() -> OpeningService:
    svc = OpeningService(CONFIG)
    svc.load()
    return svc


def encyclopedia_service() -> OpeningEncyclopediaService:
    return OpeningEncyclopediaService(CONFIG)


def iter_base_rows(svc: OpeningService) -> List[BaseRow]:
    rows: List[BaseRow] = []
    for fen, entry in (svc._eco_base or {}).items():
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        eco = str(entry.get("eco") or "").strip()
        if not name or not eco:
            continue
        rows.append(
            BaseRow(
                fen=str(fen),
                eco=eco,
                name=name,
                moves=str(entry.get("moves") or "").strip(),
                src=str(entry.get("src") or "").strip(),
            )
        )
    return rows


def collision_groups(svc: OpeningService, rows: Iterable[BaseRow]) -> Dict[str, List[BaseRow]]:
    groups: Dict[str, List[BaseRow]] = {}
    for row in rows:
        groups.setdefault(OpeningService.book_key(row.fen), []).append(row)
    return {key: group for key, group in groups.items() if len(group) > 1}


def replay_fen(row: BaseRow) -> Optional[str]:
    sans = parse_move_sans(row.moves)
    if not sans:
        return None
    return fen_after_sans(sans)


def display_tuple(svc: OpeningService, fen: str) -> Optional[Tuple[str, str]]:
    display = svc.lookup_opening_display(fen)
    if display is None:
        return None
    return (display.eco.strip(), display.name.strip())


def rewrite_fen(
    fen: str,
    *,
    stm: Optional[str] = None,
    castling: Optional[str] = None,
    ep: Optional[str] = None,
    clocks: Optional[Tuple[str, str]] = None,
) -> str:
    """Replace selected FEN fields; pad to the six-field form if needed."""
    parts = (fen or "").split()
    while len(parts) < 6:
        parts.append("-" if len(parts) in (2, 3) else "0")
    placement, side, castle, ep_sq, half, full = parts[:6]
    if stm is not None:
        side = stm
    if castling is not None:
        castle = castling
    if ep is not None:
        ep_sq = ep
    if clocks is not None:
        half, full = clocks
    return f"{placement} {side} {castle} {ep_sq} {half} {full}"
    display = svc.lookup_opening_display(fen)
    if display is None:
        return None
    return (display.eco, display.name)
