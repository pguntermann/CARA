"""Rule for detecting defensive resources found."""

from typing import List, Optional
import chess
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation, parse_fen
from app.services.game_highlights.constants import (
    DEFENSIVE_THREAT_MIN_CPL,
    DEFENSIVE_EVAL_IMPROVEMENT_THRESHOLD,
    PIECE_VALUES
)


class DefensiveResourceRule(HighlightRule):
    """Detects when a side finds the only defensive resource."""
    
    MIN_VALUABLE_PIECE_VALUE = 300  # Minimum value for a piece to be considered valuable (bishop/knight/rook/queen)
    
    def _has_tactical_threat(self, board: chess.Board, color: chess.Color) -> bool:
        """Check if there's an actual tactical threat in the position.
        
        Args:
            board: Board position after opponent's move.
            color: Color of the side being threatened.
            
        Returns:
            True if there's a tactical threat (check, undefended attacked piece, or mate threat).
        """
        # Check if king is in check
        if board.is_check():
            return True
        
        # Check for undefended attacked pieces (valuable pieces only)
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        for piece_type in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]:
            for sq in board.pieces(piece_type, color):
                if board.is_attacked_by(opponent_color, sq):
                    # Check if the piece is undefended
                    if not board.is_attacked_by(color, sq):
                        piece = board.piece_at(sq)
                        if piece:
                            piece_letter = piece.symbol().lower()
                            piece_value = PIECE_VALUES.get(piece_letter, 0)
                            if piece_value >= self.MIN_VALUABLE_PIECE_VALUE:
                                return True
        
        # Check for mate threats (if there are many attackers around the king)
        king_square = board.king(color)
        if king_square is not None:
            attackers = board.attackers(opponent_color, king_square)
            if len(attackers) >= 2:
                # Multiple attackers on the king suggests a potential mate threat
                return True
        
        return False
    
    def _move_defends_threat(self, board_before: chess.Board, board_after: chess.Board, 
                            color: chess.Color) -> bool:
        """Check if the move actually defends against the threat.
        
        Args:
            board_before: Board position before the defensive move.
            board_after: Board position after the defensive move.
            color: Color of the side making the defensive move.
            
        Returns:
            True if the move addresses the threat (removes check, defends piece, etc.).
        """
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        
        # Check if move removed check
        if board_before.is_check() and not board_after.is_check():
            return True
        
        # Check if move defended an attacked piece
        # Find pieces that were attacked before but are now defended
        for piece_type in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]:
            for sq in board_before.pieces(piece_type, color):
                if board_before.is_attacked_by(opponent_color, sq):
                    if not board_before.is_attacked_by(color, sq):
                        # Piece was attacked and undefended before
                        # Check if it's now defended or no longer attacked
                        if (board_after.is_attacked_by(color, sq) or 
                            not board_after.is_attacked_by(opponent_color, sq)):
                            piece = board_before.piece_at(sq)
                            if piece:
                                piece_letter = piece.symbol().lower()
                                piece_value = PIECE_VALUES.get(piece_letter, 0)
                                if piece_value >= self.MIN_VALUABLE_PIECE_VALUE:
                                    return True
        
        # Check if move reduced attackers on the king
        king_square = board_before.king(color)
        if king_square is not None:
            attackers_before = len(board_before.attackers(opponent_color, king_square))
            attackers_after = len(board_after.attackers(opponent_color, king_square))
            if attackers_before >= 2 and attackers_after < attackers_before:
                return True
        
        return False
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for defensive resource highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        if context.prev_move:
            # Check for white's defensive resource
            if context.prev_move.cpl_black and move.cpl_white and move.white_move:
                try:
                    prev_cpl = float(context.prev_move.cpl_black)
                    curr_cpl = float(move.cpl_white)
                    
                    # Opponent created serious threat (higher threshold for unique defense)
                    # Verify defense was necessary: require opponent's previous move CPL > 150 (serious threat)
                    opponent_created_threat = prev_cpl > 150
                    
                    # Position is clearly bad after opponent's threat
                    evaluation_was_bad = False
                    if context.prev_move.eval_black:
                        eval_after_opponent = parse_evaluation(context.prev_move.eval_black)
                        if eval_after_opponent is not None:
                            # Check if evaluation is clearly bad (absolute threshold)
                            if eval_after_opponent < -150:
                                evaluation_was_bad = True
                            # Or check if it worsened significantly from before opponent's move
                            elif context.move_index >= 2:
                                move_before_opponent = context.moves[context.move_index - 2]
                                if move_before_opponent and move_before_opponent.eval_white:
                                    eval_before_opponent = parse_evaluation(move_before_opponent.eval_white)
                                    if eval_before_opponent is not None:
                                        evaluation_was_bad = (eval_after_opponent - eval_before_opponent) < -100
                    
                    # Check for actual tactical threat using FEN
                    # For white's defensive move, check position after black's previous move (before white's move)
                    has_actual_threat = False
                    move_defends_threat = False
                    if context.prev_move.fen_black and move.fen_white:
                        board_before = parse_fen(context.prev_move.fen_black)
                        board_after = parse_fen(move.fen_white)
                        if board_before and board_after:
                            has_actual_threat = self._has_tactical_threat(board_before, chess.WHITE)
                            if has_actual_threat:
                                move_defends_threat = self._move_defends_threat(board_before, board_after, chess.WHITE)
                    
                    # Defensive move must be good quality
                    move_is_good = curr_cpl < context.good_move_max_cpl
                    
                    # For "only defensive resource", the move MUST be the best move
                    # If it's truly the only defense, the engine would rank it as #1
                    move_is_best = (move.white_is_top3 and 
                                   move.best_white and 
                                   move.best_white.strip().lower() == move.white_move.strip().lower())
                    
                    # Enhanced: Verify other defensive options were significantly worse using PV2/PV3 CPL
                    is_only_defense = move_is_best
                    if move_is_best and move.cpl_white_2 and move.cpl_white_3:
                        try:
                            cpl_2 = float(move.cpl_white_2)
                            cpl_3 = float(move.cpl_white_3)
                            # If 2nd and 3rd best moves have high CPL (>100), this is truly the only good defense
                            if cpl_2 > 100 and cpl_3 > 100:
                                is_only_defense = True
                            else:
                                # Other defensive options exist, not truly "only" defense
                                is_only_defense = False
                        except (ValueError, TypeError):
                            pass  # Fall back to basic check if PV2/PV3 data unavailable
                    
                    # Evaluation must hold or improve (tighter threshold)
                    evaluation_improved = False
                    if context.prev_move.eval_black and move.eval_white:
                        eval_after_opponent = parse_evaluation(context.prev_move.eval_black)
                        eval_after_defense = parse_evaluation(move.eval_white)
                        if eval_after_opponent is not None and eval_after_defense is not None:
                            # Allow only small deterioration (20cp instead of 50cp)
                            evaluation_improved = eval_after_defense >= eval_after_opponent - DEFENSIVE_EVAL_IMPROVEMENT_THRESHOLD
                    
                    # Require actual tactical threat AND that the move defends it
                    # Use is_only_defense instead of move_is_best for stricter verification
                    if (opponent_created_threat or evaluation_was_bad) and has_actual_threat and move_defends_threat and move_is_good and is_only_defense and evaluation_improved:
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=True,
                            move_notation=f"{move_num}. {move.white_move}",
                            description="White found the only defensive resource",
                            priority=20,
                            rule_type="defensive_resource"
                        ))
                except (ValueError, TypeError):
                    pass
            
            # Check for black's defensive resource
            if context.prev_move.cpl_white and move.cpl_black and move.black_move:
                try:
                    prev_cpl = float(context.prev_move.cpl_white)
                    curr_cpl = float(move.cpl_black)
                    
                    # Opponent created serious threat (higher threshold for unique defense)
                    # Verify defense was necessary: require opponent's previous move CPL > 150 (serious threat)
                    opponent_created_threat = prev_cpl > 150
                    
                    # Position is clearly bad after opponent's threat
                    evaluation_was_bad = False
                    if context.prev_move.eval_white:
                        eval_after_opponent = parse_evaluation(context.prev_move.eval_white)
                        if eval_after_opponent is not None:
                            # Check if evaluation is clearly bad (absolute threshold)
                            if eval_after_opponent > 150:
                                evaluation_was_bad = True
                            # Or check if it worsened significantly from before opponent's move
                            elif context.move_index >= 2:
                                move_before_opponent = context.moves[context.move_index - 2]
                                if move_before_opponent and move_before_opponent.eval_black:
                                    eval_before_opponent = parse_evaluation(move_before_opponent.eval_black)
                                    if eval_before_opponent is not None:
                                        evaluation_was_bad = (eval_after_opponent - eval_before_opponent) > 100
                    
                    # Check for actual tactical threat using FEN
                    # For black's defensive move, check position after white's move in the same move number (before black's move)
                    has_actual_threat = False
                    move_defends_threat = False
                    if move.fen_white and move.fen_black:
                        board_before = parse_fen(move.fen_white)
                        board_after = parse_fen(move.fen_black)
                        if board_before and board_after:
                            has_actual_threat = self._has_tactical_threat(board_before, chess.BLACK)
                            if has_actual_threat:
                                move_defends_threat = self._move_defends_threat(board_before, board_after, chess.BLACK)
                    
                    # Defensive move must be good quality
                    move_is_good = curr_cpl < context.good_move_max_cpl
                    
                    # For "only defensive resource", the move MUST be the best move
                    # If it's truly the only defense, the engine would rank it as #1
                    move_is_best = (move.black_is_top3 and 
                                   move.best_black and 
                                   move.best_black.strip().lower() == move.black_move.strip().lower())
                    
                    # Enhanced: Verify other defensive options were significantly worse using PV2/PV3 CPL
                    is_only_defense = move_is_best
                    if move_is_best and move.cpl_black_2 and move.cpl_black_3:
                        try:
                            cpl_2 = float(move.cpl_black_2)
                            cpl_3 = float(move.cpl_black_3)
                            # If 2nd and 3rd best moves have high CPL (>100), this is truly the only good defense
                            if cpl_2 > 100 and cpl_3 > 100:
                                is_only_defense = True
                            else:
                                # Other defensive options exist, not truly "only" defense
                                is_only_defense = False
                        except (ValueError, TypeError):
                            pass  # Fall back to basic check if PV2/PV3 data unavailable
                    
                    # Evaluation must hold or improve (tighter threshold)
                    evaluation_improved = False
                    if context.prev_move.eval_white and move.eval_black:
                        eval_after_opponent = parse_evaluation(context.prev_move.eval_white)
                        eval_after_defense = parse_evaluation(move.eval_black)
                        if eval_after_opponent is not None and eval_after_defense is not None:
                            # Allow only small deterioration (20cp instead of 50cp)
                            evaluation_improved = eval_after_defense <= eval_after_opponent + DEFENSIVE_EVAL_IMPROVEMENT_THRESHOLD
                    
                    # Require actual tactical threat AND that the move defends it
                    # Use is_only_defense instead of move_is_best for stricter verification
                    if (opponent_created_threat or evaluation_was_bad) and has_actual_threat and move_defends_threat and move_is_good and is_only_defense and evaluation_improved:
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=False,
                            move_notation=f"{move_num}. ...{move.black_move}",
                            description="Black found the only defensive resource",
                            priority=20,
                            rule_type="defensive_resource"
                        ))
                except (ValueError, TypeError):
                    pass
        
        return highlights

