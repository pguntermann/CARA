"""Rule for detecting blundered pieces (queen/rook)."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation
from app.services.game_highlights.constants import (
    PIECE_VALUES, BLUNDERED_QUEEN_MIN_LOSS, BLUNDERED_ROOK_MIN_LOSS,
    BLUNDERED_QUEEN_EVAL_DROP, BLUNDERED_ROOK_EVAL_DROP
)


class BlunderedPieceRule(HighlightRule):
    """Detects when a side blunders a queen or rook."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for blundered piece highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        
        if not context.prev_move:
            return highlights
        
        # Check if opponent captured a queen or rook
        if move.white_capture in ["q", "r"]:
            # Black blundered a piece
            piece_lost = move.white_capture
            piece_count_before = context.prev_black_queens if piece_lost == "q" else context.prev_black_rooks
            piece_count_after = move.black_queens if piece_lost == "q" else move.black_rooks
            
            if piece_count_after < piece_count_before:
                # Calculate material loss
                material_loss = PIECE_VALUES.get(piece_lost, 0)
                
                # Check thresholds
                min_loss = BLUNDERED_QUEEN_MIN_LOSS if piece_lost == "q" else BLUNDERED_ROOK_MIN_LOSS
                min_eval_drop = BLUNDERED_QUEEN_EVAL_DROP if piece_lost == "q" else BLUNDERED_ROOK_EVAL_DROP
                
                if material_loss >= min_loss:
                    # Check if black's previous move was a blunder
                    prev_cpl = None
                    if context.prev_move.cpl_black:
                        try:
                            prev_cpl = float(context.prev_move.cpl_black)
                        except (ValueError, TypeError):
                            pass
                    
                    # Use mistake_max_cpl as threshold for blunder (blunder is worse than mistake)
                    # Typically blunder threshold is higher, but we use mistake_max_cpl as minimum
                    is_blunder = prev_cpl is not None and (prev_cpl > context.mistake_max_cpl or 
                                                          context.prev_move.assess_black == "Blunder")
                    
                    if is_blunder:
                        # Check if black's immediate follow-up move recovers the situation
                        # If the next move is a best move or strong tactical recovery, don't mark as blundered piece
                        recovery_move = False
                        if context.next_move:
                            next_cpl = None
                            if context.next_move.cpl_black:
                                try:
                                    next_cpl = float(context.next_move.cpl_black)
                                except (ValueError, TypeError):
                                    pass
                            
                            # Check if next move is best move or very strong (low CPL)
                            if (context.next_move.assess_black == "Best Move" or 
                                (next_cpl is not None and next_cpl <= 20)):
                                recovery_move = True
                            
                            # Also check if evaluation recovers significantly
                            if not recovery_move and context.next_move.eval_black and move.eval_white:
                                eval_after_capture = parse_evaluation(move.eval_white)
                                eval_after_recovery = parse_evaluation(context.next_move.eval_black)
                                if eval_after_capture is not None and eval_after_recovery is not None:
                                    eval_recovery = eval_after_recovery - eval_after_capture
                                    # If evaluation recovers by more than the eval drop threshold, it's a recovery
                                    if eval_recovery >= min_eval_drop:
                                        recovery_move = True
                        
                        if not recovery_move:
                            # Check if evaluation worsened significantly
                            eval_drop = 0
                            if context.prev_move.eval_black and move.eval_white:
                                eval_before = parse_evaluation(context.prev_move.eval_black)
                                eval_after = parse_evaluation(move.eval_white)
                                if eval_before is not None and eval_after is not None:
                                    eval_drop = eval_before - eval_after  # More negative = worse for black
                            
                            if eval_drop >= min_eval_drop:
                                piece_name = "queen" if piece_lost == "q" else "rook"
                                highlights.append(GameHighlight(
                                    move_number=context.prev_move.move_number,
                                    is_white=False,
                                    move_notation=f"{context.prev_move.move_number}. ...{context.prev_move.black_move}",
                                    description=f"Black blundered his {piece_name}",
                                    priority=50,
                                    rule_type="blundered_piece"
                                ))
        
        if move.black_capture in ["q", "r"]:
            # White blundered a piece
            piece_lost = move.black_capture
            piece_count_before = context.prev_white_queens if piece_lost == "q" else context.prev_white_rooks
            piece_count_after = move.white_queens if piece_lost == "q" else move.white_rooks
            
            if piece_count_after < piece_count_before:
                material_loss = PIECE_VALUES.get(piece_lost, 0)
                
                min_loss = BLUNDERED_QUEEN_MIN_LOSS if piece_lost == "q" else BLUNDERED_ROOK_MIN_LOSS
                min_eval_drop = BLUNDERED_QUEEN_EVAL_DROP if piece_lost == "q" else BLUNDERED_ROOK_EVAL_DROP
                
                if material_loss >= min_loss:
                    prev_cpl = None
                    if context.prev_move.cpl_white:
                        try:
                            prev_cpl = float(context.prev_move.cpl_white)
                        except (ValueError, TypeError):
                            pass
                    
                    # Use mistake_max_cpl as threshold for blunder (blunder is worse than mistake)
                    # Typically blunder threshold is higher, but we use mistake_max_cpl as minimum
                    is_blunder = prev_cpl is not None and (prev_cpl > context.mistake_max_cpl or 
                                                          context.prev_move.assess_white == "Blunder")
                    
                    if is_blunder:
                        # Check if white's immediate follow-up move recovers the situation
                        # If the next move is a best move or strong tactical recovery, don't mark as blundered piece
                        recovery_move = False
                        if context.next_move:
                            next_cpl = None
                            if context.next_move.cpl_white:
                                try:
                                    next_cpl = float(context.next_move.cpl_white)
                                except (ValueError, TypeError):
                                    pass
                            
                            # Check if next move is best move or very strong (low CPL)
                            if (context.next_move.assess_white == "Best Move" or 
                                (next_cpl is not None and next_cpl <= 20)):
                                recovery_move = True
                            
                            # Also check if evaluation recovers significantly
                            if not recovery_move and context.next_move.eval_white and move.eval_black:
                                eval_after_capture = parse_evaluation(move.eval_black)
                                eval_after_recovery = parse_evaluation(context.next_move.eval_white)
                                if eval_after_capture is not None and eval_after_recovery is not None:
                                    eval_recovery = eval_after_recovery - eval_after_capture
                                    # If evaluation recovers by more than the eval drop threshold, it's a recovery
                                    if eval_recovery >= min_eval_drop:
                                        recovery_move = True
                        
                        if not recovery_move:
                            eval_drop = 0
                            if context.prev_move.eval_white and move.eval_black:
                                eval_before = parse_evaluation(context.prev_move.eval_white)
                                eval_after = parse_evaluation(move.eval_black)
                                if eval_before is not None and eval_after is not None:
                                    eval_drop = eval_after - eval_before  # More positive = worse for white
                            
                            if eval_drop >= min_eval_drop:
                                piece_name = "queen" if piece_lost == "q" else "rook"
                                highlights.append(GameHighlight(
                                    move_number=context.prev_move.move_number,
                                    is_white=True,
                                    move_notation=f"{context.prev_move.move_number}. {context.prev_move.white_move}",
                                    description=f"White blundered his {piece_name}",
                                    priority=50,
                                    rule_type="blundered_piece"
                                ))
        
        return highlights

