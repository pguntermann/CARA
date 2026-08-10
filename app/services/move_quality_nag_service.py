"""Apply move-quality NAGs to PGN from analysis classifications."""

from __future__ import annotations

import io
from typing import Dict, List, Optional, Set

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

# Classification → NAG. Good Move / Book Move intentionally omitted (no NAG).
ASSESSMENT_TO_QUALITY_NAG: Dict[str, int] = {
    "Brilliant": chess.pgn.NAG_BRILLIANT_MOVE,
    "Best Move": chess.pgn.NAG_GOOD_MOVE,
    "Inaccuracy": chess.pgn.NAG_DUBIOUS_MOVE,
    "Mistake": chess.pgn.NAG_MISTAKE,
    "Miss": chess.pgn.NAG_BLUNDER,
    "Blunder": chess.pgn.NAG_BLUNDER,
}


def nag_for_assessment(assessment: Optional[str]) -> Optional[int]:
    """Return the quality NAG for an assessment label, or None if none should be written."""
    if not assessment:
        return None
    key = str(assessment).strip()
    # Brilliant detection may emit "Brilliant (...)" — treat as Brilliant.
    if key.startswith("Brilliant"):
        key = "Brilliant"
    return ASSESSMENT_TO_QUALITY_NAG.get(key)


def _replace_quality_nags(node: chess.pgn.ChildNode, nag: Optional[int]) -> None:
    """Remove $1–$6 from ``node`` and optionally set one replacement quality NAG."""
    node.nags -= QUALITY_NAGS
    if nag is not None:
        node.nags.add(int(nag))


class MoveQualityNagService:
    """Rewrite mainline move-quality NAGs from analysis assessments."""

    @staticmethod
    def apply_to_game(game: GameData, moves: List[MoveData]) -> bool:
        """Update ``game.pgn`` mainline quality NAGs from ``moves`` assessments.

        For each mainline half-move:
        - strips existing quality NAGs ($1–$6);
        - writes the mapped NAG when the assessment maps to one;
        - leaves Good/Book (and unknown) without a quality NAG;
        - preserves non-quality NAGs.

        Returns:
            True if the PGN was updated successfully.
        """
        if game is None or not moves:
            return False
        pgn_text = getattr(game, "pgn", None) or ""
        if not str(pgn_text).strip():
            return False

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
                        white_node, nag_for_assessment(getattr(move_data, "assess_white", ""))
                    )
                node = white_node

                # Black half-move
                if getattr(move_data, "black_move", ""):
                    if not node.variations:
                        break
                    black_node = node.variation(0)
                    _replace_quality_nags(
                        black_node, nag_for_assessment(getattr(move_data, "assess_black", ""))
                    )
                    node = black_node

            game.pgn = PgnService.export_game_to_pgn(chess_game)
            return True
        except Exception as e:
            LoggingService.get_instance().error(
                f"Failed to apply move quality NAGs: {e}", exc_info=e
            )
            return False
