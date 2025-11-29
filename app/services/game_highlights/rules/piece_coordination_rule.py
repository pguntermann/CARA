"""Rule for detecting piece coordination (multiple pieces working together)."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen
from app.services.game_highlights.constants import PIECE_VALUES


class PieceCoordinationRule(HighlightRule):
    """Detects when multiple pieces coordinate to attack the same target."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for piece coordination highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's piece coordination
        if move.white_move and move.cpl_white and context.move_index > 0:
            try:
                cpl = float(move.cpl_white)
                if cpl < 30:  # Good move
                    board_after = parse_fen(move.fen_white)
                    if board_after:
                        if self._has_piece_coordination(board_after, chess.WHITE):
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=True,
                                move_notation=f"{move_num}. {move.white_move}",
                                description="White's pieces coordinated effectively",
                                priority=33,
                                rule_type="piece_coordination"
                            ))
            except (ValueError, TypeError):
                pass
        
        # Black's piece coordination
        if move.black_move and move.cpl_black:
            try:
                cpl = float(move.cpl_black)
                if cpl < 30:  # Good move
                    board_after = parse_fen(move.fen_black)
                    if board_after:
                        if self._has_piece_coordination(board_after, chess.BLACK):
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=False,
                                move_notation=f"{move_num}. ...{move.black_move}",
                                description="Black's pieces coordinated effectively",
                                priority=33,
                                rule_type="piece_coordination"
                            ))
            except (ValueError, TypeError):
                pass
        
        return highlights
    
    def _has_piece_coordination(self, board: chess.Board, color: chess.Color) -> bool:
        """Check if multiple pieces (2+) attack the same valuable target (>=300cp)."""
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        
        # Check all opponent pieces
        for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]:
            for target_sq in board.pieces(piece_type, opponent_color):
                target_piece = board.piece_at(target_sq)
                if target_piece:
                    piece_letter = target_piece.symbol().lower()
                    piece_value = PIECE_VALUES.get(piece_letter, 0)
                    if piece_value >= 300 or piece_type == chess.KING:
                        # Count how many of our pieces attack this target
                        attackers = board.attackers(color, target_sq)
                        if len(attackers) >= 2:
                            return True
        
        return False

