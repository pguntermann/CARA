"""Rule for detecting castling."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen


class CastlingRule(HighlightRule):
    """Detects castling moves."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for castling highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Fact #8: Castling (kingside)
        if move.white_move == "O-O" and context.move_index > 0:
            prev_move = context.prev_move
            if prev_move and prev_move.fen_black:
                board_before = parse_fen(prev_move.fen_black)
                board_after = parse_fen(move.fen_white)
                
                if board_before and board_after:
                    had_kingside_right = board_before.castling_rights & chess.BB_H1
                    lost_kingside_right = not (board_after.castling_rights & chess.BB_H1)
                    
                    if had_kingside_right and lost_kingside_right:
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=True,
                            move_notation=f"{move_num}. O-O",
                            description="White castled kingside",
                            priority=15,
                            rule_type="castling"
                        ))
        
        if move.black_move == "O-O":
            board_before = parse_fen(move.fen_white)
            board_after = parse_fen(move.fen_black)
            
            if board_before and board_after:
                had_kingside_right = board_before.castling_rights & chess.BB_H8
                lost_kingside_right = not (board_after.castling_rights & chess.BB_H8)
                
                if had_kingside_right and lost_kingside_right:
                    highlights.append(GameHighlight(
                        move_number=move_num,
                        is_white=False,
                        move_notation=f"{move_num}. ...O-O",
                        description="Black castled kingside",
                        priority=15,
                        rule_type="castling"
                    ))
        
        # Fact #9: Castling (queenside)
        if move.white_move == "O-O-O" and context.move_index > 0:
            prev_move = context.prev_move
            if prev_move and prev_move.fen_black:
                board_before = parse_fen(prev_move.fen_black)
                board_after = parse_fen(move.fen_white)
                
                if board_before and board_after:
                    had_queenside_right = board_before.castling_rights & chess.BB_A1
                    lost_queenside_right = not (board_after.castling_rights & chess.BB_A1)
                    
                    if had_queenside_right and lost_queenside_right:
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=True,
                            move_notation=f"{move_num}. O-O-O",
                            description="White castled queenside",
                            priority=15,
                            rule_type="castling"
                        ))
        
        if move.black_move == "O-O-O":
            board_before = parse_fen(move.fen_white)
            board_after = parse_fen(move.fen_black)
            
            if board_before and board_after:
                had_queenside_right = board_before.castling_rights & chess.BB_A8
                lost_queenside_right = not (board_after.castling_rights & chess.BB_A8)
                
                if had_queenside_right and lost_queenside_right:
                    highlights.append(GameHighlight(
                        move_number=move_num,
                        is_white=False,
                        move_notation=f"{move_num}. ...O-O-O",
                        description="Black castled queenside",
                        priority=15,
                        rule_type="castling"
                    ))
        
        return highlights

