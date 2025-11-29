"""Rule for detecting pawn promotion threats."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen


class PawnPromotionThreatRule(HighlightRule):
    """Detects when an advanced pawn threatens promotion."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for pawn promotion threat highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's pawn promotion threat
        if move.white_move and len(move.white_move) >= 2 and move.white_move[0].islower():
            board_after = parse_fen(move.fen_white)
            if board_after and context.prev_move and context.prev_move.fen_black:
                board_before = parse_fen(context.prev_move.fen_black)
                if board_before:
                    if self._creates_promotion_threat(board_before, board_after, chess.WHITE):
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=True,
                            move_notation=f"{move_num}. {move.white_move}",
                            description="White created a pawn promotion threat",
                            priority=40,
                            rule_type="pawn_promotion_threat"
                        ))
        
        # Black's pawn promotion threat
        if move.black_move and len(move.black_move) >= 2 and move.black_move[0].islower():
            board_after = parse_fen(move.fen_black)
            if board_after and move.fen_white:
                board_before = parse_fen(move.fen_white)
                if board_before:
                    if self._creates_promotion_threat(board_before, board_after, chess.BLACK):
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=False,
                            move_notation=f"{move_num}. ...{move.black_move}",
                            description="Black created a pawn promotion threat",
                            priority=40,
                            rule_type="pawn_promotion_threat"
                        ))
        
        return highlights
    
    def _creates_promotion_threat(self, board_before: chess.Board, board_after: chess.Board, 
                                  color: chess.Color) -> bool:
        """Check if move creates a pawn promotion threat."""
        pawns_before = list(board_before.pieces(chess.PAWN, color))
        pawns_after = list(board_after.pieces(chess.PAWN, color))
        
        # Find pawns that advanced
        for pawn_sq in pawns_after:
            pawn_rank = chess.square_rank(pawn_sq)
            
            # Check if pawn is on 6th or 7th rank (white) or 1st or 2nd rank (black)
            if color == chess.WHITE:
                if pawn_rank >= 5:  # 6th or 7th rank (0-indexed: 5 or 6)
                    # Check if this pawn was on a lower rank before
                    was_advanced = False
                    for prev_pawn_sq in pawns_before:
                        if chess.square_file(prev_pawn_sq) == chess.square_file(pawn_sq):
                            prev_rank = chess.square_rank(prev_pawn_sq)
                            if prev_rank < pawn_rank:
                                was_advanced = True
                                break
                    
                    if was_advanced or pawn_sq not in pawns_before:
                        # Check if pawn is supported
                        is_supported = board_after.is_attacked_by(color, pawn_sq)
                        if is_supported:
                            return True
            else:  # BLACK
                if pawn_rank <= 2:  # 1st or 2nd rank (0-indexed: 0 or 1)
                    was_advanced = False
                    for prev_pawn_sq in pawns_before:
                        if chess.square_file(prev_pawn_sq) == chess.square_file(pawn_sq):
                            prev_rank = chess.square_rank(prev_pawn_sq)
                            if prev_rank > pawn_rank:
                                was_advanced = True
                                break
                    
                    if was_advanced or pawn_sq not in pawns_before:
                        is_supported = board_after.is_attacked_by(color, pawn_sq)
                        if is_supported:
                            return True
        
        return False

