"""Rule for detecting rook lift (rook moves to higher rank to create threats)."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen, parse_evaluation


class RookLiftRule(HighlightRule):
    """Detects when a rook moves to a higher rank to create threats."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for rook lift highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's rook lift
        if move.white_move and ("R" in move.white_move or move.white_move.startswith("R")):
            board_after = parse_fen(move.fen_white)
            if board_after and context.prev_move and context.prev_move.fen_black:
                board_before = parse_fen(context.prev_move.fen_black)
                if board_before:
                    rook_sq_after = self._find_rook_square(board_after, chess.WHITE, move.white_move)
                    rook_sq_before = self._find_rook_square_before(board_before, board_after, chess.WHITE)
                    
                    if rook_sq_after is not None and rook_sq_before is not None:
                        rook_rank_after = chess.square_rank(rook_sq_after)
                        rook_rank_before = chess.square_rank(rook_sq_before)
                        
                        # Check if rook moved from rank 1-2 to rank 3+
                        if rook_rank_before <= 1 and rook_rank_after >= 2:
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
                                    description="White lifted the rook to create threats",
                                    priority=24,
                                    rule_type="rook_lift"
                                ))
        
        # Black's rook lift
        if move.black_move and ("R" in move.black_move or move.black_move.startswith("R")):
            board_after = parse_fen(move.fen_black)
            if board_after and move.fen_white:
                board_before = parse_fen(move.fen_white)
                if board_before:
                    rook_sq_after = self._find_rook_square(board_after, chess.BLACK, move.black_move)
                    rook_sq_before = self._find_rook_square_before(board_before, board_after, chess.BLACK)
                    
                    if rook_sq_after is not None and rook_sq_before is not None:
                        rook_rank_after = chess.square_rank(rook_sq_after)
                        rook_rank_before = chess.square_rank(rook_sq_before)
                        
                        # Check if rook moved from rank 7-8 to rank 6-
                        if rook_rank_before >= 6 and rook_rank_after <= 5:
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
                                    description="Black lifted the rook to create threats",
                                    priority=24,
                                    rule_type="rook_lift"
                                ))
        
        return highlights
    
    def _find_rook_square(self, board: chess.Board, color: chess.Color, move_san: str):
        """Find the rook square from move notation."""
        try:
            dest_part = move_san
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
                piece_at_dest = board.piece_at(dest_square)
                if piece_at_dest and piece_at_dest.piece_type == chess.ROOK and piece_at_dest.color == color:
                    return dest_square
        except (ValueError, AttributeError):
            pass
        return None
    
    def _find_rook_square_before(self, board_before: chess.Board, board_after: chess.Board, 
                                 color: chess.Color):
        """Find which rook moved by comparing before/after positions."""
        rooks_before = list(board_before.pieces(chess.ROOK, color))
        rooks_after = list(board_after.pieces(chess.ROOK, color))
        
        # Find rook that disappeared from before position
        for rook_sq in rooks_before:
            if rook_sq not in rooks_after:
                return rook_sq
        
        return None

