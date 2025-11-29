"""Rule for detecting breakthrough sacrifice (sacrificing piece to break through defenses)."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_evaluation
from app.services.game_highlights.constants import PIECE_VALUES


class BreakthroughSacrificeRule(HighlightRule):
    """Detects when a piece is sacrificed to break through opponent's defenses."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for breakthrough sacrifice highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        if not context.prev_move or not context.next_move:
            return highlights
        
        # White's breakthrough sacrifice
        if move.white_capture and move.cpl_white:
            try:
                # Check if white sacrificed a piece (>=300cp)
                material_before = context.prev_white_material
                material_after = move.white_material
                material_sacrificed = material_before - material_after
                
                if material_sacrificed >= 300:
                    # CRITICAL: Check if material is regained in follow-up moves
                    # If material is regained (or more is gained), it's not a sacrifice -
                    # it's a forced tactical sequence
                    material_regained = self._check_material_regained(
                        context, move_num, is_white=True, material_sacrificed=material_sacrificed
                    )
                    
                    if not material_regained:
                        # Material was NOT regained - this could be a true sacrifice
                        # Check if evaluation improves >200cp after opponent's response
                        eval_after_sacrifice = None
                        if move.eval_white:
                            eval_after_sacrifice = parse_evaluation(move.eval_white)
                        
                        eval_after_response = None
                        if context.next_move.eval_black:
                            eval_after_response = parse_evaluation(context.next_move.eval_black)
                        
                        if eval_after_sacrifice is not None and eval_after_response is not None:
                            eval_improvement = eval_after_response - eval_after_sacrifice
                            if eval_improvement > 200:
                                highlights.append(GameHighlight(
                                    move_number=move_num,
                                    is_white=True,
                                    move_notation=f"{move_num}. {move.white_move}",
                                    description="White sacrificed a piece to break through",
                                    priority=44,
                                    rule_type="breakthrough_sacrifice"
                                ))
            except (ValueError, TypeError):
                pass
        
        # Black's breakthrough sacrifice
        if move.black_capture and move.cpl_black:
            try:
                material_before = context.prev_black_material
                material_after = move.black_material
                material_sacrificed = material_before - material_after
                
                if material_sacrificed >= 300:
                    # CRITICAL: Check if material is regained in follow-up moves
                    # If material is regained (or more is gained), it's not a sacrifice -
                    # it's a forced tactical sequence
                    material_regained = self._check_material_regained(
                        context, move_num, is_white=False, material_sacrificed=material_sacrificed
                    )
                    
                    if not material_regained:
                        # Material was NOT regained - this could be a true sacrifice
                        eval_after_sacrifice = None
                        if move.eval_black:
                            eval_after_sacrifice = parse_evaluation(move.eval_black)
                        
                        eval_after_response = None
                        if context.next_move.eval_white:
                            eval_after_response = parse_evaluation(context.next_move.eval_white)
                        
                        if eval_after_sacrifice is not None and eval_after_response is not None:
                            eval_improvement = eval_after_sacrifice - eval_after_response  # Inverted for black
                            if eval_improvement > 200:
                                highlights.append(GameHighlight(
                                    move_number=move_num,
                                    is_white=False,
                                    move_notation=f"{move_num}. ...{move.black_move}",
                                    description="Black sacrificed a piece to break through",
                                    priority=44,
                                    rule_type="breakthrough_sacrifice"
                                ))
            except (ValueError, TypeError):
                pass
        
        return highlights
    
    def _check_material_regained(self, context: RuleContext, move_num: int, 
                                 is_white: bool, material_sacrificed: int) -> bool:
        """Check if material is regained within a few moves after the 'sacrifice'.
        
        If material is regained (or more is gained) within 2-3 moves, it's not a
        sacrifice - it's a forced tactical sequence.
        
        We check for net material gain: if the material after the sequence is
        better than or equal to the material before the sacrifice, it's not a true sacrifice.
        
        Args:
            context: Rule context with move history.
            move_num: Move number of the potential sacrifice.
            is_white: True if checking white's material, False for black.
            material_sacrificed: Amount of material that was 'sacrificed'.
        
        Returns:
            True if material is regained within follow-up moves, False otherwise.
        """
        if not context.moves:
            return False
        
        # Find the move index
        move_index = None
        for i, m in enumerate(context.moves):
            if m.move_number == move_num:
                move_index = i
                break
        
        if move_index is None or move_index == 0:
            return False
        
        # Get material BEFORE the sacrifice (to compare against)
        prev_move = context.moves[move_index - 1]
        if is_white:
            material_before_sacrifice = prev_move.white_material
        else:
            material_before_sacrifice = prev_move.black_material
        
        # Check for captures in follow-up moves that indicate material is being regained
        # A tactical sequence typically involves capturing pieces to regain material
        # Check up to 4 moves ahead to catch longer sequences
        for i in range(1, min(5, len(context.moves) - move_index)):
            check_index = move_index + i
            if check_index >= len(context.moves):
                break
            
            check_move = context.moves[check_index]
            
            # Check if there's a capture that would indicate material regain
            if is_white:
                if check_move.white_capture:
                    # White captured something - check if it's a significant piece
                    # (not just a pawn, which might not fully compensate)
                    capture_value = self._get_capture_value(check_move.white_capture)
                    # If we capture a piece worth at least 80% of what we sacrificed,
                    # consider material regained (handles cases where material tracking
                    # might not perfectly reflect the exchange)
                    if capture_value >= material_sacrificed * 0.8:
                        return True
                
                # Also check if material is now better than or equal to material before sacrifice
                material_now = check_move.white_material
                if material_now >= material_before_sacrifice - 50:
                    return True
            else:
                if check_move.black_capture:
                    capture_value = self._get_capture_value(check_move.black_capture)
                    if capture_value >= material_sacrificed * 0.8:
                        return True
                
                material_now = check_move.black_material
                if material_now >= material_before_sacrifice - 50:
                    return True
        
        return False
    
    def _get_capture_value(self, capture_piece: str) -> int:
        """Get the centipawn value of a captured piece.
        
        Args:
            capture_piece: Single character representing the captured piece (p, n, b, r, q).
        
        Returns:
            Centipawn value of the piece.
        """
        piece_values = {
            'p': 100,  # Pawn
            'n': 300,  # Knight
            'b': 300,  # Bishop
            'r': 500,  # Rook
            'q': 900,  # Queen
        }
        return piece_values.get(capture_piece.lower(), 0)

