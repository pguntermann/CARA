"""Apply move-quality NAGs to PGN from analysis classifications."""

from __future__ import annotations

import io
from copy import deepcopy
from typing import Any, Dict, List, Optional, Set, Tuple

import chess.pgn

from app.models.moveslist_model import MoveData
from app.models.database_model import GameData
from app.services.logging_service import LoggingService
from app.services.pgn_service import PgnService

# Standard move-quality NAGs ($1–$6). Other NAGs on a node are left alone.
QUALITY_NAGS: Set[int] = {
    chess.pgn.NAG_GOOD_MOVE,  # 1 !
    chess.pgn.NAG_MISTAKE,  # 2 ?
    chess.pgn.NAG_BRILLIANT_MOVE,  # 3 !!
    chess.pgn.NAG_BLUNDER,  # 4 ??
    chess.pgn.NAG_SPECULATIVE_MOVE,  # 5 !?
    chess.pgn.NAG_DUBIOUS_MOVE,  # 6 ?!
}

# Display order for configure dialog and defaults.
ASSESSMENT_LABELS: Tuple[str, ...] = (
    "Brilliant",
    "Best Move",
    "Good Move",
    "Book Move",
    "Inaccuracy",
    "Mistake",
    "Miss",
    "Blunder",
)

# Combo options: label → NAG code (None = write no quality NAG).
QUALITY_NAG_CHOICES: Tuple[Tuple[str, Optional[int]], ...] = (
    ("None", None),
    ("!  ($1)", chess.pgn.NAG_GOOD_MOVE),
    ("?  ($2)", chess.pgn.NAG_MISTAKE),
    ("!! ($3)", chess.pgn.NAG_BRILLIANT_MOVE),
    ("?? ($4)", chess.pgn.NAG_BLUNDER),
    ("!? ($5)", chess.pgn.NAG_SPECULATIVE_MOVE),
    ("?! ($6)", chess.pgn.NAG_DUBIOUS_MOVE),
)

# Per-classification defaults: enable + NAG (Good/Book off by design).
DEFAULT_MOVE_QUALITY_NAG_MAPPING: Dict[str, Dict[str, Any]] = {
    "Brilliant": {"enabled": True, "nag": chess.pgn.NAG_BRILLIANT_MOVE},
    "Best Move": {"enabled": True, "nag": chess.pgn.NAG_GOOD_MOVE},
    "Good Move": {"enabled": False, "nag": None},
    "Book Move": {"enabled": False, "nag": None},
    "Inaccuracy": {"enabled": True, "nag": chess.pgn.NAG_DUBIOUS_MOVE},
    "Mistake": {"enabled": True, "nag": chess.pgn.NAG_MISTAKE},
    "Miss": {"enabled": True, "nag": chess.pgn.NAG_BLUNDER},
    "Blunder": {"enabled": True, "nag": chess.pgn.NAG_BLUNDER},
}

# Backward-compatible flat map of enabled defaults (tests / older callers).
ASSESSMENT_TO_QUALITY_NAG: Dict[str, int] = {
    label: int(entry["nag"])
    for label, entry in DEFAULT_MOVE_QUALITY_NAG_MAPPING.items()
    if entry.get("enabled") and entry.get("nag") is not None
}

_VALID_NAGS: Set[int] = set(QUALITY_NAGS)


def default_move_quality_nag_mapping() -> Dict[str, Dict[str, Any]]:
    """Return a deep copy of the built-in classification→NAG mapping."""
    return deepcopy(DEFAULT_MOVE_QUALITY_NAG_MAPPING)


def normalize_move_quality_nag_mapping(
    raw: Optional[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Merge user mapping with defaults; clamp NAG codes to $1–$6 or None."""
    result = default_move_quality_nag_mapping()
    if not isinstance(raw, dict):
        return result

    for label in ASSESSMENT_LABELS:
        entry = raw.get(label)
        if not isinstance(entry, dict):
            continue
        enabled = bool(entry.get("enabled", result[label]["enabled"]))
        nag_raw = entry.get("nag", result[label]["nag"])
        nag: Optional[int]
        if nag_raw is None or nag_raw == "" or nag_raw == 0:
            nag = None
        else:
            try:
                nag_int = int(nag_raw)
            except (TypeError, ValueError):
                nag = result[label]["nag"]
            else:
                nag = nag_int if nag_int in _VALID_NAGS else result[label]["nag"]
        result[label] = {"enabled": enabled, "nag": nag}
    return result


def load_move_quality_nag_mapping_from_settings() -> Dict[str, Dict[str, Any]]:
    """Load effective mapping from user settings (defaults when unset)."""
    try:
        from app.services.user_settings_service import UserSettingsService

        settings = UserSettingsService.get_instance().get_settings()
        game_analysis = settings.get("game_analysis", {}) if isinstance(settings, dict) else {}
        raw = game_analysis.get("move_quality_nag_mapping") if isinstance(game_analysis, dict) else None
        return normalize_move_quality_nag_mapping(raw if isinstance(raw, dict) else None)
    except Exception:
        return default_move_quality_nag_mapping()


def nag_for_assessment(
    assessment: Optional[str],
    mapping: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Optional[int]:
    """Return the quality NAG for an assessment label, or None if none should be written."""
    if not assessment:
        return None
    key = str(assessment).strip()
    # Brilliant detection may emit "Brilliant (...)" — treat as Brilliant.
    if key.startswith("Brilliant"):
        key = "Brilliant"

    effective = (
        normalize_move_quality_nag_mapping(mapping)
        if mapping is not None
        else DEFAULT_MOVE_QUALITY_NAG_MAPPING
    )
    entry = effective.get(key)
    if not entry or not entry.get("enabled"):
        return None
    nag = entry.get("nag")
    if nag is None:
        return None
    try:
        nag_int = int(nag)
    except (TypeError, ValueError):
        return None
    return nag_int if nag_int in _VALID_NAGS else None


def _replace_quality_nags(node: chess.pgn.ChildNode, nag: Optional[int]) -> None:
    """Remove $1–$6 from ``node`` and optionally set one replacement quality NAG."""
    node.nags -= QUALITY_NAGS
    if nag is not None:
        node.nags.add(int(nag))


class MoveQualityNagService:
    """Rewrite mainline move-quality NAGs from analysis assessments."""

    @staticmethod
    def apply_to_game(
        game: GameData,
        moves: List[MoveData],
        mapping: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> bool:
        """Update ``game.pgn`` mainline quality NAGs from ``moves`` assessments.

        For each mainline half-move:
        - strips existing quality NAGs ($1–$6);
        - writes the mapped NAG when the assessment maps to one;
        - leaves disabled / None / unknown assessments without a quality NAG;
        - preserves non-quality NAGs.

        When ``mapping`` is None, the effective mapping is loaded from user settings.

        Returns:
            True if the PGN was updated successfully.
        """
        if game is None or not moves:
            return False
        pgn_text = getattr(game, "pgn", None) or ""
        if not str(pgn_text).strip():
            return False

        effective = (
            normalize_move_quality_nag_mapping(mapping)
            if mapping is not None
            else load_move_quality_nag_mapping_from_settings()
        )

        try:
            chess_game = chess.pgn.read_game(io.StringIO(pgn_text))
            if chess_game is None:
                return False

            node: chess.pgn.GameNode = chess_game
            for move_data in moves:
                # White half-move
                if not node.variations:
                    break
                white_node = node.variation(0)
                if getattr(move_data, "white_move", ""):
                    _replace_quality_nags(
                        white_node,
                        nag_for_assessment(
                            getattr(move_data, "assess_white", ""), effective
                        ),
                    )
                node = white_node

                # Black half-move
                if getattr(move_data, "black_move", ""):
                    if not node.variations:
                        break
                    black_node = node.variation(0)
                    _replace_quality_nags(
                        black_node,
                        nag_for_assessment(
                            getattr(move_data, "assess_black", ""), effective
                        ),
                    )
                    node = black_node

            game.pgn = PgnService.export_game_to_pgn(chess_game)
            return True
        except Exception as e:
            LoggingService.get_instance().error(
                f"Failed to apply move quality NAGs: {e}", exc_info=e
            )
            return False
