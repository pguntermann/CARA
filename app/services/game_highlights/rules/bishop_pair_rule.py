"""Rule for detecting bishop pair secured/gained."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen, bishops_opposite_colors


class BishopPairRule(HighlightRule):
    """Detects when a side secures or gains the bishop pair."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for bishop pair highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White secures the bishop pair
        if move.white_bishops == 2 and move.black_bishops < 2:
            if context.prev_white_bishops < 2 or (context.prev_black_bishops >= 2 and move.white_capture == "b"):
                board = parse_fen(move.fen_white)
                if board and bishops_opposite_colors(board, chess.WHITE):
                    is_equalized = False
                    if context.next_move and context.next_move.black_capture == "b" and context.next_move.black_move:
                        is_equalized = True
                    if move.black_move and move.black_capture == "b":
                        is_equalized = True
                    
                    if not is_equalized:
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=True,
                            move_notation=f"{move_num}. {move.white_move}",
                            description="White secured the bishop pair",
                            priority=28,
                            rule_type="bishop_pair"
                        ))
        
        # Black secures the bishop pair
        if move.black_bishops == 2 and move.white_bishops < 2:
            if context.prev_black_bishops < 2 or (context.prev_white_bishops >= 2 and move.black_capture == "b"):
                board = parse_fen(move.fen_black)
                if board and bishops_opposite_colors(board, chess.BLACK):
                    is_equalized = False
                    if context.next_move and context.next_move.white_capture == "b" and context.next_move.white_move:
                        is_equalized = True
                    if move.white_move and move.white_capture == "b":
                        is_equalized = True
                    
                    if not is_equalized:
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=False,
                            move_notation=f"{move_num}. ...{move.black_move}",
                            description="Black secured the bishop pair",
                            priority=28,
                            rule_type="bishop_pair"
                        ))
        
        # White gained the bishop pair (through opponent's move)
        if move.white_bishops == 2 and context.prev_white_bishops == 1:
            if move.black_move and not move.white_capture and not move.white_move:
                highlights.append(GameHighlight(
                    move_number=move_num,
                    is_white=False,
                    move_notation=f"{move_num}. ...{move.black_move}",
                    description="White gained the bishop pair",
                    priority=32,
                    rule_type="bishop_pair"
                ))
        
        # Black gained the bishop pair (through opponent's move)
        if move.black_bishops == 2 and context.prev_black_bishops == 1:
            if move.white_move and not move.black_capture and not move.black_move:
                highlights.append(GameHighlight(
                    move_number=move_num,
                    is_white=True,
                    move_notation=f"{move_num}. {move.white_move}",
                    description="Black gained the bishop pair",
                    priority=32,
                    rule_type="bishop_pair"
                ))
        
        return highlights

