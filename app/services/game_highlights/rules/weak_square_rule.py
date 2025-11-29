"""Rule for detecting weak squares (squares that cannot be attacked by pawns)."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen


class WeakSquareRule(HighlightRule):
    """Detects when a piece moves to a weak square (cannot be attacked by opponent's pawns)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for weak square highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's weak square occupation
        if move.white_move and move.cpl_white and context.move_index > 0:
            try:
                cpl = float(move.cpl_white)
                if cpl < context.good_move_max_cpl:
                    board_after = parse_fen(move.fen_white)
                    if board_after and context.prev_move and context.prev_move.fen_black:
                        board_before = parse_fen(context.prev_move.fen_black)
                        if board_before:
                            moved_piece_square = self._find_moved_piece_square(
                                move.white_move, board_before, board_after, chess.WHITE
                            )
                            if moved_piece_square is not None:
                                if self._is_weak_square_outpost(board_after, moved_piece_square, chess.WHITE):
                                    highlights.append(GameHighlight(
                                        move_number=move_num,
                                        is_white=True,
                                        move_notation=f"{move_num}. {move.white_move}",
                                        description="White occupied a weak square",
                                        priority=23,
                                        rule_type="weak_square"
                                    ))
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Black's weak square occupation
        if move.black_move and move.cpl_black:
            try:
                cpl = float(move.cpl_black)
                if cpl < context.good_move_max_cpl:
                    board_after = parse_fen(move.fen_black)
                    if board_after and move.fen_white:
                        board_before = parse_fen(move.fen_white)
                        if board_before:
                            moved_piece_square = self._find_moved_piece_square(
                                move.black_move, board_before, board_after, chess.BLACK
                            )
                            if moved_piece_square is not None:
                                if self._is_weak_square_outpost(board_after, moved_piece_square, chess.BLACK):
                                    highlights.append(GameHighlight(
                                        move_number=move_num,
                                        is_white=False,
                                        move_notation=f"{move_num}. ...{move.black_move}",
                                        description="Black occupied a weak square",
                                        priority=23,
                                        rule_type="weak_square"
                                    ))
            except (ValueError, TypeError, AttributeError):
                pass
        
        return highlights
    
    def _find_moved_piece_square(self, move_san: str, board_before: chess.Board, 
                                 board_after: chess.Board, color: chess.Color):
        """Find the square of the piece that moved."""
        try:
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
                piece_at_dest = board_after.piece_at(dest_square)
                if piece_at_dest and piece_at_dest.color == color:
                    return dest_square
        except (ValueError, AttributeError):
            pass
        return None
    
    def _is_weak_square_outpost(self, board: chess.Board, square: chess.Square, color: chess.Color) -> bool:
        """Check if square is a weak square (cannot be attacked by opponent's pawns) and is defended."""
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        square_file = chess.square_file(square)
        square_rank = chess.square_rank(square)
        
        # Check if square is in opponent's half
        if color == chess.WHITE:
            if square_rank < 4:  # Not in black's half
                return False
        else:  # BLACK
            if square_rank > 3:  # Not in white's half
                return False
        
        # Check if square cannot be attacked by opponent's pawns
        opponent_pawns = board.pieces(chess.PAWN, opponent_color)
        can_be_attacked_by_pawn = False
        
        for pawn_sq in opponent_pawns:
            pawn_file = chess.square_file(pawn_sq)
            pawn_rank = chess.square_rank(pawn_sq)
            
            # Check if pawn can attack this square
            if opponent_color == chess.WHITE:
                # White pawns attack diagonally forward
                if abs(pawn_file - square_file) == 1 and square_rank == pawn_rank + 1:
                    can_be_attacked_by_pawn = True
                    break
            else:  # BLACK
                # Black pawns attack diagonally forward
                if abs(pawn_file - square_file) == 1 and square_rank == pawn_rank - 1:
                    can_be_attacked_by_pawn = True
                    break
        
        if can_be_attacked_by_pawn:
            return False
        
        # Check if square is defended by own pieces
        is_defended = board.is_attacked_by(color, square)
        
        return is_defended

