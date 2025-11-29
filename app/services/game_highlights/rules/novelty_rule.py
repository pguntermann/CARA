"""Rule for detecting novelties."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext


class NoveltyRule(HighlightRule):
    """Detects novelties (not in top 3, but good move)."""
    
    # Minimum move number before novelties are detected (skip early moves)
    MIN_MOVE_NUMBER = 7
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for novelty highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Skip early moves (before move 7)
        if move_num < self.MIN_MOVE_NUMBER:
            return highlights
        
        # Fact #7: Novelty (not in top 3, but good)
        # Deduplication (once per side per phase) is handled in highlight_detector.py
        if move.white_move and move.cpl_white:
            try:
                cpl = float(move.cpl_white)
                if cpl < context.good_move_max_cpl and not move.white_is_top3:
                    # Enhanced: Check quality proximity to top 3 using PV2/PV3 CPL
                    is_near_top_novelty = False
                    if move.cpl_white_2:
                        try:
                            cpl_2 = float(move.cpl_white_2)
                            # If move is within 20cp of 2nd best, it's a "near-top novelty"
                            if cpl < cpl_2 + 20:
                                is_near_top_novelty = True
                        except (ValueError, TypeError):
                            pass
                    
                    priority = 18 if is_near_top_novelty else 15
                    description = "White played a novelty (not in top 3 engine moves)"
                    if is_near_top_novelty:
                        description = "White played a creative move close to engine recommendations"
                    
                    highlights.append(GameHighlight(
                        move_number=move_num,
                        is_white=True,
                        move_notation=f"{move_num}. {move.white_move}",
                        description=description,
                        priority=priority,
                        rule_type="novelty"
                    ))
            except (ValueError, TypeError):
                pass
        
        if move.black_move and move.cpl_black:
            try:
                cpl = float(move.cpl_black)
                if cpl < context.good_move_max_cpl and not move.black_is_top3:
                    # Enhanced: Check quality proximity to top 3 using PV2/PV3 CPL
                    is_near_top_novelty = False
                    if move.cpl_black_2:
                        try:
                            cpl_2 = float(move.cpl_black_2)
                            # If move is within 20cp of 2nd best, it's a "near-top novelty"
                            if cpl < cpl_2 + 20:
                                is_near_top_novelty = True
                        except (ValueError, TypeError):
                            pass
                    
                    priority = 18 if is_near_top_novelty else 15
                    description = "Black played a novelty (not in top 3 engine moves)"
                    if is_near_top_novelty:
                        description = "Black played a creative move close to engine recommendations"
                    
                    highlights.append(GameHighlight(
                        move_number=move_num,
                        is_white=False,
                        move_notation=f"{move_num}. ...{move.black_move}",
                        description=description,
                        priority=priority,
                        rule_type="novelty"
                    ))
            except (ValueError, TypeError):
                pass
        
        return highlights

