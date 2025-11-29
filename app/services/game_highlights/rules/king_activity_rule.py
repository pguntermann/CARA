"""Rule for detecting king activity in endgame."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen, parse_evaluation


class KingActivityRule(HighlightRule):
    """Detects when king becomes active in endgame."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for king activity highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Only check in endgame
        if move.move_number < context.middlegame_end:
            return highlights
        
        # White's king activity (exclude castling)
        if move.white_move and "K" in move.white_move and not (move.white_move.startswith("O-") or move.white_move.startswith("O-O")):
            board_after = parse_fen(move.fen_white)
            if board_after and context.prev_move and context.prev_move.fen_black:
                board_before = parse_fen(context.prev_move.fen_black)
                if board_before:
                    king_sq_after = board_after.king(chess.WHITE)
                    king_sq_before = board_before.king(chess.WHITE)
                    
                    if king_sq_after is not None and king_sq_before is not None:
                        king_rank_after = chess.square_rank(king_sq_after)
                        king_rank_before = chess.square_rank(king_sq_before)
                        
                        # Check if king moved forward (ranks 3-6 for white)
                        if king_rank_after >= 3 and king_rank_after <= 6 and king_rank_after > king_rank_before:
                            # Verify evaluation is improving
                            eval_improving = True
                            if move.eval_white and context.prev_move.eval_white:
                                eval_before = parse_evaluation(context.prev_move.eval_white)
                                eval_after = parse_evaluation(move.eval_white)
                                if eval_before is not None and eval_after is not None:
                                    eval_improving = eval_after > eval_before
                            
                            if eval_improving:
                                highlights.append(GameHighlight(
                                    move_number=move_num,
                                    is_white=True,
                                    move_notation=f"{move_num}. {move.white_move}",
                                    description="White's king became active in the endgame",
                                    priority=27,
                                    rule_type="king_activity"
                                ))
        
        # Black's king activity (exclude castling)
        if move.black_move and "K" in move.black_move and not (move.black_move.startswith("O-") or move.black_move.startswith("O-O")):
            board_after = parse_fen(move.fen_black)
            if board_after and move.fen_white:
                board_before = parse_fen(move.fen_white)
                if board_before:
                    king_sq_after = board_after.king(chess.BLACK)
                    king_sq_before = board_before.king(chess.BLACK)
                    
                    if king_sq_after is not None and king_sq_before is not None:
                        king_rank_after = chess.square_rank(king_sq_after)
                        king_rank_before = chess.square_rank(king_sq_before)
                        
                        # Check if king moved forward (ranks 2-5 for black)
                        if king_rank_after <= 4 and king_rank_after >= 1 and king_rank_after < king_rank_before:
                            eval_improving = True
                            if move.eval_black and context.prev_move.eval_black:
                                eval_before = parse_evaluation(context.prev_move.eval_black)
                                eval_after = parse_evaluation(move.eval_black)
                                if eval_before is not None and eval_after is not None:
                                    eval_improving = eval_after < eval_before  # Inverted for black
                            
                            if eval_improving:
                                highlights.append(GameHighlight(
                                    move_number=move_num,
                                    is_white=False,
                                    move_notation=f"{move_num}. ...{move.black_move}",
                                    description="Black's king became active in the endgame",
                                    priority=27,
                                    rule_type="king_activity"
                                ))
        
        return highlights

