"""Rule for detecting material imbalances."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext


class MaterialImbalanceRule(HighlightRule):
    """Detects material imbalances (piece for pawns, rook for minor)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for material imbalance highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Fact #2: Material imbalance (piece for pawns)
        if move.white_capture in ["b", "n"]:
            pawn_diff = context.prev_black_pawns - move.black_pawns
            if pawn_diff >= 2:
                highlights.append(GameHighlight(
                    move_number=move_num,
                    is_white=True,
                    move_notation=f"{move_num}. {move.white_move}",
                    description=f"White traded {move.white_capture.upper()} for {pawn_diff} pawns",
                    priority=25,
                    rule_type="material_imbalance"
                ))
        
        if move.black_capture in ["b", "n"]:
            pawn_diff = context.prev_white_pawns - move.white_pawns
            if pawn_diff >= 2:
                highlights.append(GameHighlight(
                    move_number=move_num,
                    is_white=False,
                    move_notation=f"{move_num}. ...{move.black_move}",
                    description=f"Black traded {move.black_capture.upper()} for {pawn_diff} pawns",
                    priority=25,
                    rule_type="material_imbalance"
                ))
        
        # Fact #3: Material imbalance (rook for minor)
        # "Traded rook for minor piece" means: lost a rook, gained a minor piece
        # Check if side captured a minor piece AND lost a rook, but did NOT lose a minor piece
        # Only flag as a trade if the rook gets recaptured (look ahead adaptively)
        # Exclude "Best Move" assessments - those are positional sacrifices, not material imbalances
        if move.white_capture in ["b", "n"]:
            rook_lost = move.white_rooks < context.prev_white_rooks
            minor_lost = (move.white_bishops + move.white_knights) < (context.prev_white_bishops + context.prev_white_knights)
            # Rook for minor: captured minor, lost rook, but didn't lose a minor
            # Skip if this was the best move (positional sacrifice, not a material imbalance)
            if rook_lost and not minor_lost and move.assess_white != "Best Move":
                # Check for same-move recapture first (opponent captures rook on same move)
                same_move_recapture = (move.black_capture == "r")
                # If not same-move, look ahead adaptively to see if the rook gets recaptured
                if same_move_recapture or self._is_rook_recaptured(context, move_index=context.move_index, is_white=True, 
                                           initial_rook_count=move.white_rooks):
                    highlights.append(GameHighlight(
                        move_number=move_num,
                        is_white=True,
                        move_notation=f"{move_num}. {move.white_move}",
                        description="White traded rook for minor piece",
                        priority=32,
                        rule_type="material_imbalance"
                    ))
        
        if move.black_capture in ["b", "n"]:
            rook_lost = move.black_rooks < context.prev_black_rooks
            minor_lost = (move.black_bishops + move.black_knights) < (context.prev_black_bishops + context.prev_black_knights)
            # Rook for minor: captured minor, lost rook, but didn't lose a minor
            # Skip if this was the best move (positional sacrifice, not a material imbalance)
            if rook_lost and not minor_lost and move.assess_black != "Best Move":
                # Check for same-move recapture first (opponent captures rook on same move)
                same_move_recapture = (move.white_capture == "r")
                # If not same-move, look ahead adaptively to see if the rook gets recaptured
                if same_move_recapture or self._is_rook_recaptured(context, move_index=context.move_index, is_white=False,
                                           initial_rook_count=move.black_rooks):
                    highlights.append(GameHighlight(
                        move_number=move_num,
                        is_white=False,
                        move_notation=f"{move_num}. ...{move.black_move}",
                        description="Black traded rook for minor piece",
                        priority=32,
                        rule_type="material_imbalance"
                    ))
        
        return highlights
    
    def _is_rook_recaptured(self, context: RuleContext, move_index: int, is_white: bool, 
                            initial_rook_count: int) -> bool:
        """Check if a rook gets recaptured within an adaptive look-ahead window.
        
        Strategy:
        - Start with 2 moves ahead
        - If the last move in the window is a capture, extend by 1 more move
        - Continue extending if captures keep happening
        - Return True if opponent captures a rook (recapture), False otherwise
        
        Args:
            context: Rule context with moves list.
            move_index: Index of the current move in context.moves.
            is_white: True if checking white's rook, False for black.
            initial_rook_count: Rook count after the initial capture (not used, but kept for clarity).
        
        Returns:
            True if rook gets recaptured within the adaptive window, False otherwise.
        """
        if not context.moves or move_index >= len(context.moves) - 1:
            return False
        
        # Start with 2 moves ahead
        look_ahead = 2
        max_look_ahead = 10  # Safety limit to prevent infinite loops
        
        while look_ahead <= max_look_ahead:
            # Check if we can look this far ahead
            if move_index + look_ahead >= len(context.moves):
                break
            
            # Check all moves in the current window
            for i in range(1, look_ahead + 1):
                if move_index + i >= len(context.moves):
                    break
                
                future_move = context.moves[move_index + i]
                
                # Check if the opponent captured a rook (recapture)
                # If we're checking white's rook, black should capture it
                # If we're checking black's rook, white should capture it
                if is_white:
                    # White lost rook, check if black captures rook
                    if future_move.black_capture == "r":
                        return True
                else:
                    # Black lost rook, check if white captures rook
                    if future_move.white_capture == "r":
                        return True
            
            # Check if the last move in the current window is a capture
            last_move_in_window = context.moves[move_index + look_ahead]
            is_capture = bool((is_white and last_move_in_window.white_capture) or 
                            (not is_white and last_move_in_window.black_capture))
            
            if is_capture:
                # Extend window by 1 more move
                look_ahead += 1
            else:
                # No capture at the end, stop looking
                break
        
        # No recapture found within the adaptive window
        return False

