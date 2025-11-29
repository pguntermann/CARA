"""Rule for detecting back rank weakness."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen


class BackRankWeaknessRule(HighlightRule):
    """Detects when king is trapped on back rank with no escape squares."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for back rank weakness highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's back rank weakness
        if move.white_move:
            board_after = parse_fen(move.fen_white)
            if board_after:
                if self._has_back_rank_weakness(board_after, chess.WHITE):
                    highlights.append(GameHighlight(
                        move_number=move_num,
                        is_white=True,
                        move_notation=f"{move_num}. {move.white_move}",
                        description="White's king is vulnerable on the back rank",
                        priority=43,
                        rule_type="back_rank_weakness"
                    ))
        
        # Black's back rank weakness
        if move.black_move:
            board_after = parse_fen(move.fen_black)
            if board_after:
                if self._has_back_rank_weakness(board_after, chess.BLACK):
                    highlights.append(GameHighlight(
                        move_number=move_num,
                        is_white=False,
                        move_notation=f"{move_num}. ...{move.black_move}",
                        description="Black's king is vulnerable on the back rank",
                        priority=43,
                        rule_type="back_rank_weakness"
                    ))
        
        return highlights
    
    def _has_back_rank_weakness(self, board: chess.Board, color: chess.Color) -> bool:
        """Check if king is trapped on back rank with opponent's rooks/queens on that rank."""
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        
        # Get king position
        king_square = board.king(color)
        if king_square is None:
            return False
        
        king_rank = chess.square_rank(king_square)
        
        # Check if king is on back rank
        if color == chess.WHITE:
            if king_rank != 0:  # Not on 1st rank
                return False
        else:  # BLACK
            if king_rank != 7:  # Not on 8th rank
                return False
        
        # Check if all escape squares are blocked by own pawns
        king_file = chess.square_file(king_square)
        escape_squares = []
        
        # Check squares in front of king
        if color == chess.WHITE:
            if king_rank < 7:
                escape_squares.append(chess.square(king_file, king_rank + 1))
        else:  # BLACK
            if king_rank > 0:
                escape_squares.append(chess.square(king_file, king_rank - 1))
        
        # Check diagonal escape squares
        for df in [-1, 1]:
            file = king_file + df
            if 0 <= file <= 7:
                if color == chess.WHITE and king_rank < 7:
                    escape_squares.append(chess.square(file, king_rank + 1))
                elif color == chess.BLACK and king_rank > 0:
                    escape_squares.append(chess.square(file, king_rank - 1))
        
        # Check if all escape squares are blocked by own pawns
        all_blocked = True
        for sq in escape_squares:
            piece = board.piece_at(sq)
            if piece is None or piece.piece_type != chess.PAWN or piece.color != color:
                all_blocked = False
                break
        
        if not all_blocked:
            return False
        
        # Check if opponent has rooks or queens on the back rank
        back_rank = 0 if color == chess.WHITE else 7
        for file in range(8):
            sq = chess.square(file, back_rank)
            piece = board.piece_at(sq)
            if piece and piece.color == opponent_color:
                if piece.piece_type in [chess.ROOK, chess.QUEEN]:
                    return True
        
        return False

