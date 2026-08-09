"""Rule for detecting discovered attacks."""

from typing import List, Optional, Tuple
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen
from app.services.game_highlights.constants import PIECE_VALUES


class DiscoveredAttackRule(HighlightRule):
    """Detects when a move creates a discovered attack (moving a piece reveals an attack by another piece behind it)."""
    
    # Minimum value of target piece for a meaningful discovered attack
    MIN_TARGET_PIECE_VALUE = 300

    PIECE_NAMES = {
        "p": "pawn",
        "n": "knight",
        "b": "bishop",
        "r": "rook",
        "q": "queen",
        "k": "king",
    }
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for discovered attack highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Skip discovered attacks in opening phase - they're usually not meaningful
        if move_num <= context.opening_end:
            return highlights
        
        # Check if current move is a simple recapture with equal material
        # This prevents false positives from simple recaptures
        is_simple_recapture = False
        if move.white_capture and move.black_capture:
            captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
            captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
            if abs(captured_by_white - captured_by_black) <= 50:
                is_simple_recapture = True
        
        if not is_simple_recapture and context.prev_move:
            if move.white_capture and context.prev_move.black_capture:
                captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
                captured_by_black = PIECE_VALUES.get(context.prev_move.black_capture.lower(), 0)
                if abs(captured_by_white - captured_by_black) <= 50:
                    is_simple_recapture = True
            if move.black_capture and context.prev_move.white_capture:
                captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
                captured_by_white = PIECE_VALUES.get(context.prev_move.white_capture.lower(), 0)
                if abs(captured_by_black - captured_by_white) <= 50:
                    is_simple_recapture = True
        
        if not is_simple_recapture and context.next_move:
            if move.white_capture and context.next_move.black_capture:
                captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
                captured_by_black = PIECE_VALUES.get(context.next_move.black_capture.lower(), 0)
                if abs(captured_by_white - captured_by_black) <= 50:
                    is_simple_recapture = True
            if move.black_capture and context.next_move.white_capture:
                captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
                captured_by_white = PIECE_VALUES.get(context.next_move.white_capture.lower(), 0)
                if abs(captured_by_black - captured_by_white) <= 50:
                    is_simple_recapture = True
        
        # White's discovered attack
        if move.white_move and move.cpl_white and context.move_index > 0 and not is_simple_recapture:
            try:
                cpl = float(move.cpl_white)
                if cpl >= context.good_move_max_cpl:
                    # Not a good move, skip
                    pass
                else:
                    board_after = parse_fen(move.fen_white)
                    if board_after and context.prev_move and context.prev_move.fen_black:
                        board_before = parse_fen(context.prev_move.fen_black)
                        if board_before:
                            moved_piece_square = self._find_moved_piece_square(
                                move.white_move, board_before, board_after, chess.WHITE
                            )
                            if moved_piece_square is not None:
                                discovered_info = self._has_discovered_attack(board_before, board_after, moved_piece_square, chess.WHITE)
                                if discovered_info:
                                    target_piece, is_check, target_value, is_undefended = discovered_info
                                    # Verify discovered attack is meaningful: require target >=300cp AND (undefended OR check)
                                    if target_piece and target_value >= self.MIN_TARGET_PIECE_VALUE and (is_undefended or is_check):
                                        piece_name = self.PIECE_NAMES.get(
                                            target_piece.lower(), target_piece
                                        )
                                        if is_check:
                                            description = f"White performed a discovered attack on Black's king"
                                            priority = 45
                                        else:
                                            description = f"White performed a discovered attack on Black's {piece_name}"
                                            priority = 40
                                        highlights.append(GameHighlight(
                                            move_number=move_num,
                                            is_white=True,
                                            move_notation=f"{move_num}. {move.white_move}",
                                            description=description,
                                            priority=priority,
                                            rule_type="discovered_attack"
                                        ))
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Black's discovered attack
        if move.black_move and move.cpl_black and not is_simple_recapture:
            try:
                cpl = float(move.cpl_black)
                if cpl >= context.good_move_max_cpl:
                    # Not a good move, skip
                    pass
                else:
                    board_after = parse_fen(move.fen_black)
                    if board_after and move.fen_white:
                        board_before = parse_fen(move.fen_white)
                        if board_before:
                            moved_piece_square = self._find_moved_piece_square(
                                move.black_move, board_before, board_after, chess.BLACK
                            )
                            if moved_piece_square is not None:
                                discovered_info = self._has_discovered_attack(board_before, board_after, moved_piece_square, chess.BLACK)
                                if discovered_info:
                                    target_piece, is_check, target_value, is_undefended = discovered_info
                                    # Verify discovered attack is meaningful: require target >=300cp AND (undefended OR check)
                                    if target_piece and target_value >= self.MIN_TARGET_PIECE_VALUE and (is_undefended or is_check):
                                        piece_name = self.PIECE_NAMES.get(
                                            target_piece.lower(), target_piece
                                        )
                                        if is_check:
                                            description = f"Black performed a discovered attack on White's king"
                                            priority = 45
                                        else:
                                            description = f"Black performed a discovered attack on White's {piece_name}"
                                            priority = 40
                                        highlights.append(GameHighlight(
                                            move_number=move_num,
                                            is_white=False,
                                            move_notation=f"{move_num}. ...{move.black_move}",
                                            description=description,
                                            priority=priority,
                                            rule_type="discovered_attack"
                                        ))
            except (ValueError, TypeError, AttributeError):
                pass
        
        return highlights
    
    def _find_moved_piece_square(self, move_san: str, board_before: chess.Board, 
                                 board_after: chess.Board, color: chess.Color) -> Optional[chess.Square]:
        """Find the square of the piece that moved.
        
        Args:
            move_san: Move in SAN notation.
            board_before: Board position before the move.
            board_after: Board position after the move.
            color: Color of the moving side.
        
        Returns:
            Square index of the moved piece, or None if not found.
        """
        try:
            # Parse destination square from move notation
            dest_part = move_san
            if "=" in dest_part:
                dest_part = dest_part.split("=")[0]
            if "x" in dest_part:
                parts = dest_part.split("x")
                if len(parts) > 1:
                    dest_part = parts[-1]
            if "+" in dest_part:
                dest_part = dest_part.replace("+", "")
            if "#" in dest_part:
                dest_part = dest_part.replace("#", "")
            
            if len(dest_part) >= 2:
                dest_square = chess.parse_square(dest_part[-2:])
                
                # Find which piece moved by comparing piece positions
                for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]:
                    pieces_before = list(board_before.pieces(piece_type, color))
                    pieces_after = list(board_after.pieces(piece_type, color))
                    
                    for sq in pieces_before:
                        if sq not in pieces_after:
                            if dest_square in pieces_after or board_after.piece_at(dest_square) == chess.Piece(piece_type, color):
                                return dest_square
                    
                    if len(pieces_after) > len(pieces_before):
                        if dest_square in pieces_after:
                            return dest_square
                
                piece_at_dest = board_after.piece_at(dest_square)
                if piece_at_dest and piece_at_dest.color == color:
                    return dest_square
        except (ValueError, AttributeError):
            pass
        return None
    
    def _find_source_square(self, dest_square: chess.Square, board_before: chess.Board,
                           board_after: chess.Board, color: chess.Color) -> Optional[chess.Square]:
        """Find the source square of a moved piece.
        
        Args:
            dest_square: Destination square of the move.
            board_before: Board position before the move.
            board_after: Board position after the move.
            color: Color of the moving side.
        
        Returns:
            Source square of the moved piece, or None if not found.
        """
        piece_at_dest = board_after.piece_at(dest_square)
        if piece_at_dest is None or piece_at_dest.color != color:
            return None
        
        piece_type = piece_at_dest.piece_type
        
        # Find which piece of this type moved
        pieces_before = list(board_before.pieces(piece_type, color))
        pieces_after = list(board_after.pieces(piece_type, color))
        
        for sq in pieces_before:
            if sq not in pieces_after:
                # This piece moved - verify it's now on destination
                if dest_square in pieces_after:
                    return sq
        
        return None
    
    def _has_discovered_attack(self, board_before: chess.Board, board_after: chess.Board,
                              moved_piece_square: chess.Square, color: chess.Color) -> Optional[Tuple[str, bool, int, bool]]:
        """Check if moving a piece creates a discovered attack.

        A discovered attack occurs when the moved piece was blocking a friendly
        sliding piece (R/B/Q) from attacking a valuable enemy piece, and after
        the move the slider's path to that target is open.

        Returns:
            (target_piece_letter, is_check, target_value, is_undefended) or None.
        """
        source_square = self._find_source_square(
            moved_piece_square, board_before, board_after, color
        )
        if source_square is None:
            return None

        # Moving along the discovery ray still leaves a blocker unless the piece
        # leaves that ray entirely (classic discovered attack / discovered check).
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        directions = [
            (1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1),
        ]

        for df, dr in directions:
            slider_piece, slider_sq = self._first_piece_on_ray(
                board_before, source_square, df, dr
            )
            if (
                slider_piece is None
                or slider_sq is None
                or slider_piece.color != color
                or not self._slider_can_use_direction(slider_piece.piece_type, df, dr)
            ):
                continue

            target_piece, target_sq = self._first_piece_on_ray(
                board_before, source_square, -df, -dr
            )
            if (
                target_piece is None
                or target_sq is None
                or target_piece.color != opponent_color
            ):
                continue

            target_letter = target_piece.symbol().lower()
            is_check = target_piece.piece_type == chess.KING
            target_value = (
                900 if is_check else PIECE_VALUES.get(target_letter, 0)
            )
            if target_value < self.MIN_TARGET_PIECE_VALUE and not is_check:
                continue

            # After the move the target must still be there and the ray open.
            target_after = board_after.piece_at(target_sq)
            if (
                target_after is None
                or target_after.color != opponent_color
                or target_after.piece_type != target_piece.piece_type
            ):
                continue
            if not self._ray_clear_between(board_after, slider_sq, target_sq):
                continue

            is_undefended = not board_after.is_attacked_by(opponent_color, target_sq)
            if self._is_meaningful_discovered_attack(
                board_after, slider_sq, target_letter, opponent_color, is_check
            ):
                return (target_letter, is_check, target_value, is_undefended)

        return None

    @staticmethod
    def _slider_can_use_direction(piece_type: chess.PieceType, df: int, dr: int) -> bool:
        if piece_type == chess.QUEEN:
            return True
        if piece_type == chess.ROOK:
            return df == 0 or dr == 0
        if piece_type == chess.BISHOP:
            return df != 0 and dr != 0
        return False

    @staticmethod
    def _first_piece_on_ray(
        board: chess.Board,
        start: chess.Square,
        df: int,
        dr: int,
    ) -> Tuple[Optional[chess.Piece], Optional[chess.Square]]:
        """Return the first piece along a ray from start (exclusive)."""
        file0 = chess.square_file(start)
        rank0 = chess.square_rank(start)
        for dist in range(1, 8):
            file = file0 + df * dist
            rank = rank0 + dr * dist
            if file < 0 or file > 7 or rank < 0 or rank > 7:
                break
            sq = chess.square(file, rank)
            piece = board.piece_at(sq)
            if piece is not None:
                return piece, sq
        return None, None

    @staticmethod
    def _ray_clear_between(
        board: chess.Board, from_sq: chess.Square, to_sq: chess.Square
    ) -> bool:
        """True if every square strictly between from_sq and to_sq is empty."""
        f0, r0 = chess.square_file(from_sq), chess.square_rank(from_sq)
        f1, r1 = chess.square_file(to_sq), chess.square_rank(to_sq)
        df, dr = f1 - f0, r1 - r0
        if df == 0 and dr == 0:
            return False
        step_f = 0 if df == 0 else df // abs(df)
        step_r = 0 if dr == 0 else dr // abs(dr)
        # Must be a straight rook/bishop ray.
        if df != 0 and dr != 0 and abs(df) != abs(dr):
            return False
        f, r = f0 + step_f, r0 + step_r
        while (f, r) != (f1, r1):
            if board.piece_at(chess.square(f, r)) is not None:
                return False
            f += step_f
            r += step_r
        return True

    def _is_meaningful_discovered_attack(self, board: chess.Board, attacker_square: chess.Square,
                                        target_piece_letter: str, opponent_color: chess.Color, is_check: bool) -> bool:
        """Check if a discovered attack is meaningful (not trivial).
        
        A discovered attack is meaningful if:
        - It delivers check (always meaningful)
        - It targets an undefended piece
        - It targets a piece more valuable than the moving piece
        
        Args:
            board: Board position after the move.
            attacker_square: Square of the discovering piece.
            target_piece_letter: Letter of the target piece (e.g., "q", "r").
            opponent_color: Color of the opponent.
            is_check: True if the discovered attack delivers check.
        
        Returns:
            True if the discovered attack is meaningful.
        """
        # Check is always meaningful
        if is_check:
            return True
        
        # Find the target piece on the board
        target_piece_type_map = {
            "q": chess.QUEEN,
            "r": chess.ROOK,
            "b": chess.BISHOP,
            "n": chess.KNIGHT,
            "p": chess.PAWN
        }
        target_piece_type = target_piece_type_map.get(target_piece_letter)
        if target_piece_type is None:
            return False
        
        # Find all opponent pieces of this type
        target_pieces = list(board.pieces(target_piece_type, opponent_color))
        
        # Check if any target piece is undefended or in an important square
        attacker_file = chess.square_file(attacker_square)
        attacker_rank = chess.square_rank(attacker_square)
        
        directions = [
            (1, 0), (-1, 0), (0, 1), (0, -1),  # Rook directions
            (1, 1), (1, -1), (-1, 1), (-1, -1)  # Bishop directions
        ]
        
        attacker_piece = board.piece_at(attacker_square)
        if attacker_piece is None:
            return False
        
        attacker_piece_type = attacker_piece.piece_type
        attacker_color = attacker_piece.color
        
        for df, dr in directions:
            # Check if this direction is valid for the piece type
            if attacker_piece_type == chess.ROOK and (df != 0 and dr != 0):
                continue
            if attacker_piece_type == chess.BISHOP and (df == 0 or dr == 0):
                continue
            
            # Look along this ray for target pieces
            for dist in range(1, 8):
                file = attacker_file + df * dist
                rank = attacker_rank + dr * dist
                
                if file < 0 or file > 7 or rank < 0 or rank > 7:
                    break
                
                sq = chess.square(file, rank)
                sq_piece = board.piece_at(sq)
                
                if sq_piece is None:
                    continue
                
                if sq_piece.color == opponent_color and sq_piece.piece_type == target_piece_type:
                    # Found target piece - check if it's meaningful
                    # Check if target is undefended (not defended by opponent's pieces)
                    if not board.is_attacked_by(opponent_color, sq):
                        return True  # Undefended piece - meaningful
                    
                    # Check if target is more valuable than attacker
                    target_value = PIECE_VALUES.get(target_piece_letter, 0)
                    attacker_letter = attacker_piece.symbol().lower()
                    attacker_value = PIECE_VALUES.get(attacker_letter, 0)
                    if target_value > attacker_value:
                        return True  # More valuable target - meaningful
                    
                    # Check if target is on an important square (king area)
                    if self._is_important_square(sq, opponent_color):
                        return True
                    
                    # This target piece blocks the ray - can't attack beyond it
                    break
                else:
                    # Our own piece or different piece blocks the ray
                    break
        
        return False
    
    def _is_important_square(self, square: chess.Square, opponent_color: chess.Color) -> bool:
        """Check if a square is important (near opponent's king).
        
        Args:
            square: Square to check.
            opponent_color: Color of the opponent.
        
        Returns:
            True if the square is near the opponent's king.
        """
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        
        if opponent_color == chess.WHITE:
            # Check squares near white king (ranks 6-7, files f-h)
            if rank >= 6 and file >= 5:
                return True
        else:  # BLACK
            # Check squares near black king (ranks 0-1, files f-h)
            if rank <= 1 and file >= 5:
                return True
        
        return False

