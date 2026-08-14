"""Side-aware half-move view for game highlight rules.

Rules should prefer iterating half-moves instead of duplicating white/black
branches that only differ in which MoveData fields they read.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterator, List, Optional, Tuple

import chess

from app.models.moveslist_model import MoveData
from app.services.game_highlights.base_rule import GameHighlight, RuleContext
from app.services.game_highlights.constants import PIECE_VALUES
from app.services.game_highlights.helpers import parse_evaluation, parse_fen, parse_destination_square
from app.utils.material_tracker import calculate_material_count

# Capture values within this many centipawns count as an equal trade.
EQUAL_CAPTURE_TOLERANCE_CP = 50


def equal_capture_values(first: str, second: str) -> bool:
    """True if both captures have nearly equal material value."""
    if not first or not second:
        return False
    a = PIECE_VALUES.get(first.lower(), 0)
    b = PIECE_VALUES.get(second.lower(), 0)
    return abs(a - b) <= EQUAL_CAPTURE_TOLERANCE_CP


@dataclass
class HalfMoveContext:
    """One ply (white or black) with the MoveData fields that side needs.

    Neighbor navigation is always in ply order, not MoveData-row order:

    - After White: reply is Black on the same row.
    - After Black: reply is White on the *next* row.
    """

    is_white: bool
    move_number: int
    san: str
    fen_before: str
    fen_after: str
    move: MoveData
    context: RuleContext
    cpl: str = ""
    assess: str = ""
    capture: str = ""
    eval_after: str = ""
    best: str = ""
    is_top3: bool = False
    cpl_2: str = ""
    cpl_3: str = ""
    _board_before: Optional[chess.Board] = field(default=None, repr=False, compare=False)
    _board_after: Optional[chess.Board] = field(default=None, repr=False, compare=False)

    @property
    def color(self) -> chess.Color:
        return chess.WHITE if self.is_white else chess.BLACK

    @property
    def side_name(self) -> str:
        return "White" if self.is_white else "Black"

    def board_before(self) -> Optional[chess.Board]:
        """Parsed position before this half-move (cached)."""
        if self._board_before is None and self.fen_before:
            self._board_before = parse_fen(self.fen_before)
        return self._board_before

    def board_after(self) -> Optional[chess.Board]:
        """Parsed position after this half-move (cached)."""
        if self._board_after is None and self.fen_after:
            self._board_after = parse_fen(self.fen_after)
        return self._board_after

    def eval_after_cp(self) -> Optional[float]:
        """White-relative evaluation after this half-move, in centipawns."""
        return parse_evaluation(self.eval_after) if self.eval_after else None

    def eval_before_cp(self) -> Optional[float]:
        """White-relative evaluation of the position immediately before this half-move.

        For White: prefer the previous row's ``eval_black`` (position White faces);
        fall back to ``eval_white`` if Black had no move/eval.
        For Black: use this row's ``eval_white`` (position after White's move).
        """
        if self.is_white:
            prev = self.context.prev_move
            if not prev:
                return None
            if prev.eval_black:
                return parse_evaluation(prev.eval_black)
            if prev.eval_white:
                return parse_evaluation(prev.eval_white)
            return None

        if self.move.eval_white:
            return parse_evaluation(self.move.eval_white)
        prev = self.context.prev_move
        if prev and prev.eval_black:
            return parse_evaluation(prev.eval_black)
        return None

    def eval_improvement_cp(self) -> Optional[float]:
        """Eval change from the mover's perspective (positive = better for mover).

        Engine evals are white-relative, so Black's improvement is ``before - after``.
        """
        before = self.eval_before_cp()
        after = self.eval_after_cp()
        if before is None or after is None:
            return None
        if self.is_white:
            return after - before
        return before - after

    def mover_eval_gain_cp(self, later_eval_cp: Optional[float]) -> Optional[float]:
        """Eval change for the mover from this position's eval_after to a later eval.

        Positive means the position became better for the side that played this move.
        """
        after_own = self.eval_after_cp()
        if after_own is None or later_eval_cp is None:
            return None
        if self.is_white:
            return later_eval_cp - after_own
        return after_own - later_eval_cp

    def move_notation(self) -> str:
        """Display notation, e.g. ``12. Nf3`` or ``12. ...Nf6``."""
        if self.is_white:
            return f"{self.move_number}. {self.san}"
        return f"{self.move_number}. ...{self.san}"

    def reply(self) -> Optional["HalfMoveContext"]:
        """Opponent's immediate reply half-move, if present.

        White → Black on the same full-move row.
        Black → White on the next full-move row.
        """
        if self.is_white:
            return half_move_for(self.move, self.context, is_white=False)

        nxt = self.context.next_move
        if nxt is None:
            return None
        reply_ctx = context_for_move_index(self.context, self.context.move_index + 1)
        return half_move_for(nxt, reply_ctx, is_white=True)

    def prior(self) -> Optional["HalfMoveContext"]:
        """Opponent's half-move immediately before this one, if present.

        Black → White on the same full-move row.
        White → Black on the previous full-move row.
        """
        if not self.is_white:
            return half_move_for(self.move, self.context, is_white=True)

        if self.context.move_index <= 0 or self.context.prev_move is None:
            return None
        prior_ctx = context_for_move_index(self.context, self.context.move_index - 1)
        return half_move_for(self.context.prev_move, prior_ctx, is_white=False)

    def cpl_float(self) -> Optional[float]:
        """Parse this half-move's CPL, or None if missing/invalid."""
        if not self.cpl:
            return None
        try:
            return float(self.cpl)
        except (ValueError, TypeError):
            return None

    def cpl_2_float(self) -> Optional[float]:
        """Parse PV2 CPL, or None if missing/invalid."""
        return _parse_optional_float(self.cpl_2)

    def cpl_3_float(self) -> Optional[float]:
        """Parse PV3 CPL, or None if missing/invalid."""
        return _parse_optional_float(self.cpl_3)

    def is_near_best(self, cpl_max: float = 10) -> bool:
        """True if this ply's CPL is present and strictly below ``cpl_max``."""
        cpl = self.cpl_float()
        return cpl is not None and cpl < cpl_max

    def favoring_mate_in(self) -> Optional[int]:
        """Mate-in N favoring this side from ``eval_after``, or None if not a mate score.

        White mates look like ``M3``; Black mates look like ``-M3``. Unparseable
        mate strings return ``0`` so callers can still treat them as mate threats.
        """
        raw = self.eval_after or ""
        if self.is_white:
            if not raw.startswith("M") or raw.startswith("-M"):
                return None
            try:
                return int(raw[1:])
            except (ValueError, TypeError):
                return 0
        if not raw.startswith("-M"):
            return None
        try:
            return int(raw[2:])
        except (ValueError, TypeError):
            return 0

    def is_favoring_mate_within(self, max_moves: int = 5) -> bool:
        """True if ``eval_after`` is a mate for this side in at most ``max_moves``."""
        mate_in = self.favoring_mate_in()
        return mate_in is not None and mate_in <= max_moves

    def is_good_move(self, max_cpl: Optional[float] = None) -> bool:
        """True if CPL is present and below the good-move threshold.

        Defaults to ``context.good_move_max_cpl``; pass ``max_cpl`` to override
        (e.g. a rule-local hardcoded gate).
        """
        cpl = self.cpl_float()
        if cpl is None:
            return False
        threshold = (
            float(self.context.good_move_max_cpl) if max_cpl is None else float(max_cpl)
        )
        return cpl < threshold

    def is_mistake(self, min_cpl: Optional[float] = None) -> bool:
        """True if CPL is present and strictly above the mistake threshold."""
        cpl = self.cpl_float()
        if cpl is None:
            return False
        threshold = (
            float(self.context.mistake_max_cpl) if min_cpl is None else float(min_cpl)
        )
        return cpl > threshold

    def is_blunder(self) -> bool:
        """True if assess is Blunder, or CPL exceeds the mistake threshold."""
        return self.assess == "Blunder" or self.is_mistake()

    def is_serious_error(self) -> bool:
        """True if this ply is a mistake-level error or worse.

        Includes assess labels Mistake / Miss / Blunder, or CPL above the
        inaccuracy threshold (so mid-tier mistakes are not treated as quiet).
        """
        if self.assess in ("Blunder", "Miss", "Mistake"):
            return True
        return self.is_mistake(min_cpl=float(self.context.inaccuracy_max_cpl))

    def alt_cpls_below(self, max_cpl: float) -> bool:
        """True if both PV2 and PV3 CPLs are present and strictly below ``max_cpl``."""
        cpl_2 = self.cpl_2_float()
        cpl_3 = self.cpl_3_float()
        return (
            cpl_2 is not None
            and cpl_3 is not None
            and cpl_2 < max_cpl
            and cpl_3 < max_cpl
        )

    def alt_cpls_above(self, min_cpl: float) -> bool:
        """True if both PV2 and PV3 CPLs are present and strictly above ``min_cpl``."""
        cpl_2 = self.cpl_2_float()
        cpl_3 = self.cpl_3_float()
        return (
            cpl_2 is not None
            and cpl_3 is not None
            and cpl_2 > min_cpl
            and cpl_3 > min_cpl
        )

    def eval_change_through(self, later: "HalfMoveContext") -> Optional[float]:
        """Mover-perspective eval change from this ply's before-eval to ``later``'s after-eval.

        Positive = better for the side that played this half-move.
        """
        before = self.eval_before_cp()
        after = later.eval_after_cp()
        if before is None or after is None:
            return None
        if self.is_white:
            return after - before
        return before - after

    def eval_drop_through(self, later: "HalfMoveContext") -> Optional[float]:
        """Mover-perspective eval worsening from this ply through ``later`` (positive = worse)."""
        change = self.eval_change_through(later)
        return None if change is None else -change

    def parse_move(self) -> Optional[chess.Move]:
        """``chess.Move`` for this SAN on the before-board, if parseable."""
        board = self.board_before()
        if board is None or not self.san:
            return None
        try:
            return board.parse_san(self.san)
        except (ValueError, chess.IllegalMoveError, chess.AmbiguousMoveError):
            return None

    def destination_square(self) -> Optional[chess.Square]:
        """Destination square of this half-move.

        Prefer parsing SAN on the before-board; if that board is unavailable
        (e.g. White's first ply with no previous FEN), fall back to SAN-only parsing.
        """
        move = self.parse_move()
        if move is not None:
            return move.to_square
        return parse_destination_square(self.san)

    def is_equal_trade_with_neighbors(
        self, *, with_prior: bool = True, with_reply: bool = True
    ) -> bool:
        """True if this capture is a near-equal trade vs prior and/or reply capture values."""
        if not self.capture:
            return False
        if with_prior:
            prior = self.prior()
            if prior and equal_capture_values(self.capture, prior.capture):
                return True
        if with_reply:
            reply = self.reply()
            if reply and equal_capture_values(self.capture, reply.capture):
                return True
        return False

    def captures_undefended_unit(self) -> bool:
        """True if this ply captures an enemy unit that had no defenders."""
        if not self.capture:
            return False
        board = self.board_before()
        chess_move = self.parse_move()
        if board is None or chess_move is None:
            return False

        if board.is_en_passant(chess_move):
            captured_sq = chess.square(
                chess.square_file(chess_move.to_square),
                chess.square_rank(chess_move.from_square),
            )
        else:
            captured_sq = chess_move.to_square

        target = board.piece_at(captured_sq)
        if target is None or target.color == self.color:
            return False
        return not board.is_attacked_by(not self.color, captured_sq)

    def own_material_drop_cp(self, later: "HalfMoveContext") -> Optional[int]:
        """Own material lost from before this ply to after ``later`` (positive = lost)."""
        before = self.board_before()
        after = later.board_after()
        if before is None or after is None:
            return None
        return calculate_material_count(before, self.is_white) - calculate_material_count(
            after, self.is_white
        )

    def capture_trade_net_cp(self) -> Optional[int]:
        """Net capture value: our capture minus reply capture (if any), in centipawns."""
        if not self.capture:
            return None
        gained = PIECE_VALUES.get(self.capture.lower(), 0)
        reply = self.reply()
        if reply and reply.capture:
            return gained - PIECE_VALUES.get(reply.capture.lower(), 0)
        return gained

    def count_near_best_continuation_pairs(
        self, *, cpl_max: float = 10, limit: int = 6
    ) -> int:
        """Count leading consecutive near-best ``(our, their)`` pairs after this ply."""
        count = 0
        for our, their in self.iter_continuation_pairs(limit=limit):
            if not our.is_near_best(cpl_max):
                break
            if their is None or not their.is_near_best(cpl_max):
                break
            count += 1
        return count

    def iter_following(
        self, *, limit: Optional[int] = None
    ) -> Iterator["HalfMoveContext"]:
        """Yield later plies in game order (opponent reply first, then alternating).

        This crosses MoveData rows when needed: after Black, the first yielded ply
        is White on the next row.
        """
        current = self.reply()
        count = 0
        while current is not None:
            yield current
            count += 1
            if limit is not None and count >= limit:
                return
            current = current.reply()

    def iter_continuation_pairs(
        self, *, limit: Optional[int] = None
    ) -> Iterator[Tuple["HalfMoveContext", Optional["HalfMoveContext"]]]:
        """Yield ``(our_continuation, opponent_reply)`` pairs after this ply.

        Walk in ply order for either side::

            opponent = self.reply()
            our = opponent.reply()
            their = our.reply()
            ...

        So when Black starts, the first ``our`` continuation is Black's next move
        *after* White's intervening reply on the next MoveData row — never "both
        sides on the same row" as a substitute for consecutive plies.
        """
        opponent = self.reply()
        if opponent is None:
            return
        our = opponent.reply()
        count = 0
        while our is not None:
            their = our.reply()
            yield our, their
            count += 1
            if limit is not None and count >= limit:
                return
            if their is None:
                return
            our = their.reply()

    def same_ply(self, other: "HalfMoveContext") -> bool:
        """True if ``other`` is the same side and move number as this half-move."""
        return (
            self.is_white == other.is_white
            and self.move_number == other.move_number
            and self.san == other.san
        )


def _parse_optional_float(raw: str) -> Optional[float]:
    if not raw:
        return None
    try:
        return float(raw)
    except (ValueError, TypeError):
        return None


def make_rule_context(
    moves: List[MoveData],
    move_index: int,
    **overrides: Any,
) -> RuleContext:
    """Build a ``RuleContext`` centered on ``moves[move_index]``.

    Previous piece counts and material come from the prior row when present.
    Pass ``RuleContext`` field overrides (``opening_end``, thresholds, etc.)
    as keyword arguments.
    """
    prev = moves[move_index - 1] if move_index > 0 else None
    nxt = moves[move_index + 1] if move_index + 1 < len(moves) else None
    if prev is not None:
        prev_fields = dict(
            prev_white_bishops=prev.white_bishops,
            prev_black_bishops=prev.black_bishops,
            prev_white_knights=prev.white_knights,
            prev_black_knights=prev.black_knights,
            prev_white_queens=prev.white_queens,
            prev_black_queens=prev.black_queens,
            prev_white_rooks=prev.white_rooks,
            prev_black_rooks=prev.black_rooks,
            prev_white_pawns=prev.white_pawns,
            prev_black_pawns=prev.black_pawns,
            prev_white_material=prev.white_material,
            prev_black_material=prev.black_material,
        )
    else:
        prev_fields = dict(
            prev_white_bishops=2,
            prev_black_bishops=2,
            prev_white_knights=2,
            prev_black_knights=2,
            prev_white_queens=1,
            prev_black_queens=1,
            prev_white_rooks=2,
            prev_black_rooks=2,
            prev_white_pawns=8,
            prev_black_pawns=8,
            prev_white_material=0,
            prev_black_material=0,
        )

    kwargs = dict(
        move_index=move_index,
        total_moves=len(moves),
        opening_end=15,
        middlegame_end=40,
        prev_move=prev,
        next_move=nxt,
        last_book_move_number=0,
        theory_departed=True,
        good_move_max_cpl=50,
        inaccuracy_max_cpl=100,
        mistake_max_cpl=200,
        shared_state={},
        moves=moves,
        **prev_fields,
    )
    kwargs.update(overrides)
    return RuleContext(**kwargs)


def context_for_move_index(base: RuleContext, move_index: int) -> RuleContext:
    """Rebuild a ``RuleContext`` centered on ``base.moves[move_index]``."""
    moves = base.moves
    if move_index < 0 or move_index >= len(moves):
        raise IndexError(f"move_index {move_index} out of range for {len(moves)} moves")

    prev = moves[move_index - 1] if move_index > 0 else None
    nxt = moves[move_index + 1] if move_index + 1 < len(moves) else None
    kwargs = dict(
        move_index=move_index,
        total_moves=len(moves),
        prev_move=prev,
        next_move=nxt,
        moves=moves,
    )
    if prev is not None:
        kwargs.update(
            prev_white_bishops=prev.white_bishops,
            prev_black_bishops=prev.black_bishops,
            prev_white_knights=prev.white_knights,
            prev_black_knights=prev.black_knights,
            prev_white_queens=prev.white_queens,
            prev_black_queens=prev.black_queens,
            prev_white_rooks=prev.white_rooks,
            prev_black_rooks=prev.black_rooks,
            prev_white_pawns=prev.white_pawns,
            prev_black_pawns=prev.black_pawns,
            prev_white_material=prev.white_material,
            prev_black_material=prev.black_material,
        )
    else:
        kwargs.update(
            prev_white_bishops=2,
            prev_black_bishops=2,
            prev_white_knights=2,
            prev_black_knights=2,
            prev_white_queens=1,
            prev_black_queens=1,
            prev_white_rooks=2,
            prev_black_rooks=2,
            prev_white_pawns=8,
            prev_black_pawns=8,
            prev_white_material=0,
            prev_black_material=0,
        )
    return replace(base, **kwargs)


def half_move_for(
    move: MoveData, context: RuleContext, *, is_white: bool
) -> Optional[HalfMoveContext]:
    """Build a half-move for one side, or None if that side did not move."""
    if is_white:
        san = move.white_move or ""
        if not san:
            return None
        fen_before = ""
        if context.prev_move and context.prev_move.fen_black:
            fen_before = context.prev_move.fen_black
        return HalfMoveContext(
            is_white=True,
            move_number=move.move_number,
            san=san,
            fen_before=fen_before,
            fen_after=move.fen_white or "",
            move=move,
            context=context,
            cpl=move.cpl_white or "",
            assess=move.assess_white or "",
            capture=move.white_capture or "",
            eval_after=move.eval_white or "",
            best=move.best_white or "",
            is_top3=bool(move.white_is_top3),
            cpl_2=move.cpl_white_2 or "",
            cpl_3=move.cpl_white_3 or "",
        )

    san = move.black_move or ""
    if not san:
        return None
    return HalfMoveContext(
        is_white=False,
        move_number=move.move_number,
        san=san,
        fen_before=move.fen_white or "",
        fen_after=move.fen_black or "",
        move=move,
        context=context,
        cpl=move.cpl_black or "",
        assess=move.assess_black or "",
        capture=move.black_capture or "",
        eval_after=move.eval_black or "",
        best=move.best_black or "",
        is_top3=bool(move.black_is_top3),
        cpl_2=move.cpl_black_2 or "",
        cpl_3=move.cpl_black_3 or "",
    )


def iter_half_moves(move: MoveData, context: RuleContext) -> Iterator[HalfMoveContext]:
    """Yield white then black half-moves present on this full-move row."""
    white = half_move_for(move, context, is_white=True)
    if white is not None:
        yield white
    black = half_move_for(move, context, is_white=False)
    if black is not None:
        yield black


def paired_move_notation(start: HalfMoveContext, end: HalfMoveContext) -> str:
    """Notation spanning a starter half-move and its reply."""
    if start.is_white and not end.is_white and start.move_number == end.move_number:
        return f"{start.move_number}. {start.san} ... {end.san}"
    return f"{start.move_notation()} {end.move_notation()}"


def make_highlight(
    half: HalfMoveContext,
    description: str,
    *,
    priority: int,
    rule_type: str,
    move_number_end: Optional[int] = None,
    move_notation: Optional[str] = None,
) -> GameHighlight:
    """Build a GameHighlight from a half-move."""
    return GameHighlight(
        move_number=half.move_number,
        is_white=half.is_white,
        move_notation=move_notation if move_notation is not None else half.move_notation(),
        description=description,
        move_number_end=move_number_end,
        priority=priority,
        rule_type=rule_type,
    )


def evaluate_for_each_side(
    move: MoveData,
    context: RuleContext,
    detect,
) -> List[GameHighlight]:
    """Run ``detect(half) -> List[GameHighlight]`` for each side that moved."""
    highlights: List[GameHighlight] = []
    for half in iter_half_moves(move, context):
        highlights.extend(detect(half))
    return highlights
