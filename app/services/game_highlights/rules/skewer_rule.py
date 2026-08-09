"""Rule for detecting skewers."""

from typing import List, Optional, Set, Tuple
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen
from app.services.game_highlights.constants import PIECE_VALUES


# (square, piece_value) for a skewer target
Target = Tuple[chess.Square, int]


class SkewerRule(HighlightRule):
    """Detects skewers: a slider aligning two enemy pieces on one line for material gain.

    Geometry covers both the classic x-ray (front piece blocks a rear one) and the
    interposed form (slider lands between two enemies). Both use the same material
    test: the tactic must force a profitable capture, or the game must cash it in
    for a net material gain (not an equal trade like Bxf3 Rxf3).
    """

    MIN_TARGET_VALUE = 300
    MIN_HEAVY_TARGET_VALUE = 500
    MIN_NET_GAIN = 200
    MIN_SKEWER_MATERIAL_DIFF = 200

    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for skewer highlights.

        Move quality is not required: a skewer can be real even when the engine
        prefers a faster win (e.g. Bb6 while dxe8=Q+ mates sooner).
        """
        highlights = []
        move_num = move.move_number

        if move.white_move and context.move_index > 0:
            try:
                board_after = parse_fen(move.fen_white)
                if board_after and context.prev_move and context.prev_move.fen_black:
                    board_before = parse_fen(context.prev_move.fen_black)
                    if board_before:
                        moved_sq = self._find_moved_piece_square(
                            move.white_move, board_before, board_after, chess.WHITE
                        )
                        if moved_sq is not None and self._is_skewer(
                            board_after, moved_sq, chess.WHITE, context, is_white=True
                        ):
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=True,
                                move_notation=f"{move_num}. {move.white_move}",
                                description="White executed a skewer",
                                priority=46,
                                rule_type="skewer",
                            ))
            except (ValueError, TypeError, AttributeError):
                pass

        if move.black_move:
            try:
                board_after = parse_fen(move.fen_black)
                if board_after and move.fen_white:
                    board_before = parse_fen(move.fen_white)
                    if board_before:
                        moved_sq = self._find_moved_piece_square(
                            move.black_move, board_before, board_after, chess.BLACK
                        )
                        if moved_sq is not None and self._is_skewer(
                            board_after, moved_sq, chess.BLACK, context, is_white=False
                        ):
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=False,
                                move_notation=f"{move_num}. ...{move.black_move}",
                                description="Black executed a skewer",
                                priority=46,
                                rule_type="skewer",
                            ))
            except (ValueError, TypeError, AttributeError):
                pass

        return highlights

    def _find_moved_piece_square(
        self,
        move_san: str,
        board_before: chess.Board,
        board_after: chess.Board,
        color: chess.Color,
    ) -> Optional[chess.Square]:
        """Find the destination square of the piece that moved."""
        try:
            dest_part = move_san
            if "=" in dest_part:
                dest_part = dest_part.split("=")[0]
            if "x" in dest_part:
                parts = dest_part.split("x")
                if len(parts) > 1:
                    dest_part = parts[-1]
            dest_part = dest_part.replace("+", "").replace("#", "")

            if len(dest_part) < 2:
                return None

            dest_square = chess.parse_square(dest_part[-2:])

            for piece_type in (
                chess.PAWN,
                chess.KNIGHT,
                chess.BISHOP,
                chess.ROOK,
                chess.QUEEN,
                chess.KING,
            ):
                pieces_before = list(board_before.pieces(piece_type, color))
                pieces_after = list(board_after.pieces(piece_type, color))

                for sq in pieces_before:
                    if sq not in pieces_after:
                        if dest_square in pieces_after or board_after.piece_at(
                            dest_square
                        ) == chess.Piece(piece_type, color):
                            return dest_square

                if len(pieces_after) > len(pieces_before) and dest_square in pieces_after:
                    return dest_square

            piece_at_dest = board_after.piece_at(dest_square)
            if piece_at_dest and piece_at_dest.color == color:
                return dest_square
        except (ValueError, AttributeError):
            pass
        return None

    def _is_skewer(
        self,
        board: chess.Board,
        piece_square: chess.Square,
        color: chess.Color,
        context: RuleContext,
        *,
        is_white: bool,
    ) -> bool:
        """True when the moved slider aligns two enemy pieces and wins material."""
        piece = board.piece_at(piece_square)
        if piece is None or piece.color != color:
            return False
        if piece.piece_type not in (chess.ROOK, chess.BISHOP, chess.QUEEN):
            return False
        if not self._attacker_is_safe(board, piece_square, color):
            return False

        pairs = self._skewer_target_pairs(board, piece_square, color)
        if not pairs:
            return False

        # Any qualifying pair that wins material is enough.
        for targets in pairs:
            target_sqs = {sq for sq, _ in targets}
            if self._forces_material_gain(board, piece_square, color, target_sqs):
                return True
            if self._realized_material_gain(
                board, piece_square, color, target_sqs, context, is_white=is_white
            ):
                return True
        return False

    def _attacker_is_safe(
        self, board: chess.Board, piece_square: chess.Square, color: chess.Color
    ) -> bool:
        """False when the opponent can take the skewering piece with equal/less value."""
        piece = board.piece_at(piece_square)
        if piece is None:
            return False
        attacker_value = self._piece_value(piece)
        opponent = not color
        if not board.is_attacked_by(opponent, piece_square):
            return True
        for attacker_sq in board.attackers(opponent, piece_square):
            attacker_piece = board.piece_at(attacker_sq)
            if attacker_piece and self._piece_value(attacker_piece) <= attacker_value:
                return False
        return True

    def _skewer_target_pairs(
        self, board: chess.Board, piece_square: chess.Square, color: chess.Color
    ) -> List[Tuple[Target, Target]]:
        """Enemy piece pairs on one axis through the slider (x-ray or interposed)."""
        piece = board.piece_at(piece_square)
        if piece is None:
            return []

        directions = (
            (1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1),
        )
        file0 = chess.square_file(piece_square)
        rank0 = chess.square_rank(piece_square)
        pairs: List[Tuple[Target, Target]] = []
        seen_axes = set()

        for df, dr in directions:
            if not self._direction_ok(piece.piece_type, df, dr):
                continue

            # Classic x-ray skewer: more valuable piece in front, lesser behind.
            # (Lesser in front of the king is a pin, not a skewer — e.g. Bb4→Nc3→Ke1.)
            two = self._enemies_on_ray(board, file0, rank0, df, dr, color, limit=2)
            if len(two) == 2 and self._is_classic_xray_values(two[0][1], two[1][1]):
                pairs.append((two[0], two[1]))

            # Interposed: one enemy each way on the same axis.
            # Skip if either target is the king — king + piece on a line with the
            # slider between them is a royal fork (e.g. Rc7+ vs Ka7/Bd7), not a skewer.
            axis = (abs(df), abs(dr))
            if axis in seen_axes:
                continue
            seen_axes.add(axis)
            a = self._enemies_on_ray(board, file0, rank0, df, dr, color, limit=1)
            b = self._enemies_on_ray(board, file0, rank0, -df, -dr, color, limit=1)
            if not a or not b:
                continue
            a_piece = board.piece_at(a[0][0])
            b_piece = board.piece_at(b[0][0])
            if (
                a_piece
                and b_piece
                and a_piece.piece_type != chess.KING
                and b_piece.piece_type != chess.KING
                and self._is_interposed_values(a[0][1], b[0][1])
            ):
                pairs.append((a[0], b[0]))

        return pairs

    def _is_classic_xray_values(self, front_val: int, back_val: int) -> bool:
        """Front piece more valuable than the one behind (skewer, not pin)."""
        if front_val >= 900 and back_val >= self.MIN_TARGET_VALUE:
            return True
        if front_val < self.MIN_HEAVY_TARGET_VALUE or back_val < self.MIN_TARGET_VALUE:
            return False
        return front_val >= back_val + self.MIN_SKEWER_MATERIAL_DIFF

    def _is_interposed_values(self, a_val: int, b_val: int) -> bool:
        """Two real pieces on opposite sides; at least one heavy (rook+) or royal."""
        if a_val < self.MIN_TARGET_VALUE or b_val < self.MIN_TARGET_VALUE:
            return False
        return max(a_val, b_val) >= self.MIN_HEAVY_TARGET_VALUE

    def _forces_material_gain(
        self,
        board: chess.Board,
        attacker_sq: chess.Square,
        color: chess.Color,
        target_sqs: Set[chess.Square],
    ) -> bool:
        """True when every opponent reply still leaves a profitable target capture."""
        if board.turn == color:
            return self._profitable_target_capture(board, attacker_sq, color, target_sqs)

        for move in board.legal_moves:
            if self._is_adequate_defense(board, move, attacker_sq, color, target_sqs):
                return False
        return True

    def _is_adequate_defense(
        self,
        board: chess.Board,
        move: chess.Move,
        attacker_sq: chess.Square,
        color: chess.Color,
        target_sqs: Set[chess.Square],
    ) -> bool:
        """Opponent reply that neutralizes profitable captures of the skewer targets."""
        opponent = not color
        if move.to_square == attacker_sq:
            see = self._capture_see(board, move, opponent)
            return see is not None and see >= 0

        new_targets = self._targets_after_move(move, target_sqs)
        board.push(move)
        try:
            still = board.piece_at(attacker_sq)
            if still is None or still.color != color:
                return True
            live = {
                sq
                for sq in new_targets
                if (p := board.piece_at(sq)) is not None and p.color == opponent
            }
            return not self._profitable_target_capture(board, attacker_sq, color, live)
        finally:
            board.pop()

    @staticmethod
    def _targets_after_move(
        move: chess.Move, target_sqs: Set[chess.Square]
    ) -> Set[chess.Square]:
        """Follow target pieces that move; drop targets captured by the reply."""
        updated: Set[chess.Square] = set()
        for sq in target_sqs:
            if move.from_square == sq:
                updated.add(move.to_square)
            elif move.to_square == sq:
                continue
            else:
                updated.add(sq)
        return updated

    def _profitable_target_capture(
        self,
        board: chess.Board,
        attacker_sq: chess.Square,
        color: chess.Color,
        target_sqs: Set[chess.Square],
    ) -> bool:
        piece = board.piece_at(attacker_sq)
        if piece is None or piece.color != color or not target_sqs:
            return False
        for move in board.legal_moves:
            if move.from_square != attacker_sq or move.to_square not in target_sqs:
                continue
            if not board.is_capture(move):
                continue
            see = self._capture_see(board, move, color)
            if see is not None and see >= self.MIN_NET_GAIN:
                return True
        return False

    def _realized_material_gain(
        self,
        board_after: chess.Board,
        attacker_sq: chess.Square,
        color: chess.Color,
        target_sqs: Set[chess.Square],
        context: RuleContext,
        *,
        is_white: bool,
    ) -> bool:
        """True when the game cashes the skewer in for a net material gain."""
        sans = self._following_sans(context, is_white=is_white)
        if not sans:
            return False

        board = board_after.copy()
        atk = attacker_sq
        live_targets = set(target_sqs)
        i = 0
        while i < len(sans):
            san = sans[i]
            try:
                move = board.parse_san(san)
            except (ValueError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                break

            mover_is_skewer_side = board.turn == color
            captured = board.piece_at(move.to_square)
            from_atk = atk is not None and move.from_square == atk
            cashed_target = move.to_square in live_targets

            live_targets = self._targets_after_move(move, live_targets)
            board.push(move)
            if from_atk:
                atk = move.to_square

            if (
                mover_is_skewer_side
                and from_atk
                and cashed_target
                and captured is not None
                and captured.color != color
            ):
                gain = self._piece_value(captured)
                loss = 0
                if i + 1 < len(sans):
                    try:
                        recapture = board.parse_san(sans[i + 1])
                    except (ValueError, chess.IllegalMoveError, chess.AmbiguousMoveError):
                        recapture = None
                    if recapture is not None and recapture.to_square == atk:
                        our_piece = board.piece_at(atk)
                        if our_piece is not None:
                            loss = self._piece_value(our_piece)
                        board.push(recapture)
                        atk = None
                        i += 2
                        if gain - loss >= self.MIN_NET_GAIN:
                            return True
                        continue
                if gain >= self.MIN_NET_GAIN:
                    return True
            i += 1
        return False

    def _following_sans(self, context: RuleContext, *, is_white: bool) -> List[str]:
        """SAN half-moves after the skewer, in play order."""
        moves = context.moves
        idx = context.move_index
        if idx < 0 or idx >= len(moves):
            return []

        current = moves[idx]
        sans: List[str] = []
        if is_white:
            if current.black_move:
                sans.append(current.black_move)
            for j in range(idx + 1, min(idx + 3, len(moves))):
                md = moves[j]
                if md.white_move:
                    sans.append(md.white_move)
                if md.black_move:
                    sans.append(md.black_move)
        else:
            for j in range(idx + 1, min(idx + 3, len(moves))):
                md = moves[j]
                if md.white_move:
                    sans.append(md.white_move)
                if md.black_move:
                    sans.append(md.black_move)
        return sans

    def _capture_see(
        self, board: chess.Board, move: chess.Move, color: chess.Color
    ) -> Optional[int]:
        """One-ply net: captured value minus our piece if the opponent can recapture.

        Using the recapturer's value (instead of ours) wrongly treats Bxc3 bxc3 as
        +200 when the knight is only pawn-defended; that exchange is equal.
        """
        captured = board.piece_at(move.to_square)
        mover = board.piece_at(move.from_square)
        if captured is None or mover is None:
            return None
        gain = self._piece_value(captured)
        our_value = self._piece_value(mover)
        board.push(move)
        try:
            opponent = not color
            if board.is_attacked_by(opponent, move.to_square):
                return gain - our_value
            return gain
        finally:
            board.pop()

    @staticmethod
    def _direction_ok(piece_type: chess.PieceType, df: int, dr: int) -> bool:
        if piece_type == chess.ROOK and df != 0 and dr != 0:
            return False
        if piece_type == chess.BISHOP and (df == 0 or dr == 0):
            return False
        return True

    @staticmethod
    def _piece_value(piece: chess.Piece) -> int:
        if piece.piece_type == chess.KING:
            return 900
        return PIECE_VALUES.get(piece.symbol().lower(), 0)

    def _enemies_on_ray(
        self,
        board: chess.Board,
        file0: int,
        rank0: int,
        df: int,
        dr: int,
        color: chess.Color,
        *,
        limit: int,
    ) -> List[Target]:
        found: List[Target] = []
        for dist in range(1, 8):
            file = file0 + df * dist
            rank = rank0 + dr * dist
            if file < 0 or file > 7 or rank < 0 or rank > 7:
                break
            sq = chess.square(file, rank)
            sq_piece = board.piece_at(sq)
            if sq_piece is None:
                continue
            if sq_piece.color == color:
                break
            found.append((sq, self._piece_value(sq_piece)))
            if len(found) >= limit:
                break
        return found
