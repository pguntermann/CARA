"""Rule for detecting missed tactical opportunities."""

from typing import List
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
# No constants needed - using context.mistake_max_cpl


class TacticalOpportunityRule(HighlightRule):
    """Detects missed tactical opportunities (missed captures)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for missed tactical opportunity highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Fact #16: Tactical opportunity missed
        # Expand detection: check if best move is check ("+") OR mate ("#") OR if CPL difference >200cp
        if move.best_white and ("x" in move.best_white or "+" in move.best_white or "#" in move.best_white) and move.best_white != move.white_move:
            if move.cpl_white:
                try:
                    cpl = float(move.cpl_white)
                    # Check if best move eval shows mate or significant CPL difference
                    is_tactical = False
                    if "+" in move.best_white or "#" in move.best_white:
                        is_tactical = True
                    elif "x" in move.best_white:
                        is_tactical = True
                    # Also check if CPL difference >200cp (significant tactical opportunity)
                    if not is_tactical and move.cpl_white_2:
                        try:
                            cpl_2 = float(move.cpl_white_2)
                            if cpl - cpl_2 > 200:
                                is_tactical = True
                        except (ValueError, TypeError):
                            pass
                    
                    if is_tactical and cpl > context.mistake_max_cpl:
                        # Check if multiple good alternatives were missed (using PV2/PV3 CPL)
                        multiple_opportunities = False
                        if move.cpl_white_2 and move.cpl_white_3:
                            try:
                                cpl_2 = float(move.cpl_white_2)
                                cpl_3 = float(move.cpl_white_3)
                                # If 2nd and 3rd best moves also have low CPL (<30), multiple good alternatives were missed
                                if cpl_2 < 30 and cpl_3 < 30:
                                    multiple_opportunities = True
                            except (ValueError, TypeError):
                                pass
                        
                        description = f"White missed a tactical opportunity (best move was {move.best_white})"
                        priority = 30 if multiple_opportunities else 25
                        if multiple_opportunities:
                            description = f"White missed multiple tactical opportunities (best move was {move.best_white})"
                        
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=True,
                            move_notation=f"{move_num}. {move.white_move}",
                            description=description,
                            priority=priority,
                            rule_type="tactical_opportunity"
                        ))
                except (ValueError, TypeError):
                    pass
        
        if move.best_black and ("x" in move.best_black or "+" in move.best_black or "#" in move.best_black) and move.best_black != move.black_move:
            if move.cpl_black:
                try:
                    cpl = float(move.cpl_black)
                    # Check if best move eval shows mate or significant CPL difference
                    is_tactical = False
                    if "+" in move.best_black or "#" in move.best_black:
                        is_tactical = True
                    elif "x" in move.best_black:
                        is_tactical = True
                    # Also check if CPL difference >200cp (significant tactical opportunity)
                    if not is_tactical and move.cpl_black_2:
                        try:
                            cpl_2 = float(move.cpl_black_2)
                            if cpl - cpl_2 > 200:
                                is_tactical = True
                        except (ValueError, TypeError):
                            pass
                    
                    if is_tactical and cpl > context.mistake_max_cpl:
                        # Check if multiple good alternatives were missed (using PV2/PV3 CPL)
                        multiple_opportunities = False
                        if move.cpl_black_2 and move.cpl_black_3:
                            try:
                                cpl_2 = float(move.cpl_black_2)
                                cpl_3 = float(move.cpl_black_3)
                                # If 2nd and 3rd best moves also have low CPL (<30), multiple good alternatives were missed
                                if cpl_2 < 30 and cpl_3 < 30:
                                    multiple_opportunities = True
                            except (ValueError, TypeError):
                                pass
                        
                        description = f"Black missed a tactical opportunity (best move was {move.best_black})"
                        priority = 30 if multiple_opportunities else 25
                        if multiple_opportunities:
                            description = f"Black missed multiple tactical opportunities (best move was {move.best_black})"
                        
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=False,
                            move_notation=f"{move_num}. ...{move.black_move}",
                            description=description,
                            priority=priority,
                            rule_type="tactical_opportunity"
                        ))
                except (ValueError, TypeError):
                    pass
        
        return highlights

