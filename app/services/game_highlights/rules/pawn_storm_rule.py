"""Rule for detecting pawn storms."""

from typing import List, Optional, Set, Tuple

import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.constants import PAWN_STORM_WINDOW
from app.services.game_highlights.half_move import (
    HalfMoveContext,
    context_for_move_index,
    half_move_for,
    iter_half_moves,
    make_highlight,
)
from app.services.game_highlights.helpers import (
    are_adjacent_files,
    is_kingside_file,
    is_queenside_file,
    piece_type_from_san,
)


class PawnStormRule(HighlightRule):
    """Detects coordinated non-capture pawn advances on a flank (pawn storms)."""

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for pawn storm highlights."""
        created: Set[Tuple[bool, str, int]] = context.shared_state.setdefault(
            "pawn_storm_created", set()
        )
        highlights: List[GameHighlight] = []
        for half in iter_half_moves(move, context):
            hit = self._evaluate_half(half, created)
            if hit is not None:
                highlights.append(hit)
        return highlights

    def _evaluate_half(
        self,
        half: HalfMoveContext,
        created: Set[Tuple[bool, str, int]],
    ) -> Optional[GameHighlight]:
        move_num = half.move_number
        # Skip the opening; storms are middlegame/endgame flank plans.
        if move_num <= half.context.opening_end:
            return None

        info = self._flank_advance(half)
        if info is None:
            return None
        side, _dest_file = info

        recent = self._recent_flank_advances(half, side)
        files_involved = sorted({f for _, f in recent})
        if len(files_involved) < 2:
            return None

        board_after = half.board_after()
        if board_after is None:
            return None

        for i in range(len(files_involved) - 1):
            file1, file2 = files_involved[i], files_involved[i + 1]
            if not are_adjacent_files(file1, file2):
                continue
            if not any(f == file1 for _, f in recent) or not any(f == file2 for _, f in recent):
                continue

            file1_ranks = [
                chess.square_rank(sq)
                for sq in board_after.pieces(chess.PAWN, half.color)
                if chess.square_file(sq) == file1
            ]
            file2_ranks = [
                chess.square_rank(sq)
                for sq in board_after.pieces(chess.PAWN, half.color)
                if chess.square_file(sq) == file2
            ]
            if not file1_ranks or not file2_ranks:
                continue

            min_rank_diff = min(abs(r1 - r2) for r1 in file1_ranks for r2 in file2_ranks)
            if min_rank_diff > 1:
                continue

            ranks = file1_ranks + file2_ranks
            if half.is_white:
                advancing = max(ranks) >= 5
            else:
                advancing = min(ranks) <= 2
            if not advancing:
                continue

            storm_key = (half.is_white, side, move_num)
            if storm_key in created:
                return None
            created.add(storm_key)
            return make_highlight(
                half,
                f"{half.side_name} initiated a pawn storm on the {side}",
                priority=22,
                rule_type="pawn_storm",
            )

        return None

    def _flank_advance(self, half: HalfMoveContext) -> Optional[Tuple[str, int]]:
        """Return ``(side, dest_file)`` for a non-capture flank pawn advance."""
        if piece_type_from_san(half.san) != chess.PAWN or half.capture:
            return None
        parsed = half.parse_move()
        if parsed is None:
            return None
        if chess.square_file(parsed.from_square) != chess.square_file(parsed.to_square):
            return None

        src_rank = chess.square_rank(parsed.from_square)
        dest_rank = chess.square_rank(parsed.to_square)
        if half.is_white:
            if dest_rank <= src_rank:
                return None
        elif dest_rank >= src_rank:
            return None

        dest_file = chess.square_file(parsed.to_square)
        if is_kingside_file(dest_file):
            return "kingside", dest_file
        if is_queenside_file(dest_file):
            return "queenside", dest_file
        return None

    def _recent_flank_advances(
        self, half: HalfMoveContext, side: str
    ) -> List[Tuple[int, int]]:
        """``(move_number, dest_file)`` for our flank advances in the storm window."""
        recent: List[Tuple[int, int]] = []
        base = half.context
        start_idx = max(0, base.move_index - PAWN_STORM_WINDOW + 1)
        for j in range(start_idx, base.move_index):
            row_ctx = context_for_move_index(base, j)
            prior = half_move_for(base.moves[j], row_ctx, is_white=half.is_white)
            if not prior.san:
                continue
            info = self._flank_advance(prior)
            if info is not None and info[0] == side:
                recent.append((prior.move_number, info[1]))

        info = self._flank_advance(half)
        if info is not None and info[0] == side:
            recent.append((half.move_number, info[1]))
        return recent
