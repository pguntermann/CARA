"""Service for move analysis calculations and classifications.

This service contains pure calculation logic extracted from GameAnalysisController
to make it reusable and testable without UI dependencies.
"""

from typing import Dict, Any, Optional, List
import chess
from app.utils.material_tracker import (
    calculate_material_loss,
    calculate_material_balance
)


class MoveAnalysisService:
    """Service for move analysis calculations and classifications."""
    
    @staticmethod
    def normalize_move(move: str) -> str:
        """Normalize move string for comparison.
        
        Removes check/checkmate symbols and converts to lowercase.
        
        Args:
            move: Move string in SAN notation.
            
        Returns:
            Normalized move string.
        """
        if not move:
            return ""
        # Remove check (+) and checkmate (#) symbols, convert to lowercase
        return move.replace("+", "").replace("#", "").lower().strip()
    
    @staticmethod
    def calculate_cpl(
        eval_before: float,
        eval_after: float,
        eval_after_best_move: Optional[float],
        is_white_move: bool,
        is_mate: bool,
        is_mate_before: bool,
        is_mate_after_best: bool,
        mate_moves: int,
        mate_moves_before: int,
        mate_moves_after_best: int,
        moves_match: bool
    ) -> float:
        """Calculate Centipawn Loss (CPL) for a move.
        
        Args:
            eval_before: Evaluation before the move (centipawns).
            eval_after: Evaluation after the played move (centipawns).
            eval_after_best_move: Evaluation after best move (centipawns), if available.
            is_white_move: True if white just moved, False if black.
            is_mate: True if position after move is mate.
            is_mate_before: True if position before move was mate.
            is_mate_after_best: True if position after best move is mate.
            mate_moves: Number of moves to mate after played move.
            mate_moves_before: Number of moves to mate before move.
            mate_moves_after_best: Number of moves to mate after best move.
            moves_match: True if played move matches best move.
            
        Returns:
            CPL value in centipawns.
        """
        # If moves match, CPL is always 0
        if moves_match:
            return 0.0
        
        # Handle mate positions specially
        if is_mate or is_mate_before or (eval_after_best_move is not None and is_mate_after_best):
            # Use best move evaluation if available for more accurate comparison
            if eval_after_best_move is not None:
                return MoveAnalysisService.calculate_cpl_for_mate(
                    is_white_move, eval_after_best_move, eval_after,
                    is_mate_after_best, mate_moves_after_best,
                    is_mate, mate_moves
                )
            else:
                # Fallback to old method if best move eval not available
                return MoveAnalysisService.calculate_cpl_for_mate(
                    is_white_move, eval_before, eval_after,
                    is_mate_before, mate_moves_before,
                    is_mate, mate_moves
                )
        else:
            # Normal centipawn evaluation
            # Use best move evaluation if available for more accurate comparison
            if eval_after_best_move is not None:
                # CPL = difference between evaluation after best move vs. evaluation after played move
                return abs(eval_after_best_move - eval_after)
            else:
                # Fallback to old method: compare eval_before vs. eval_after
                # For white moves, if eval decreases, white lost centipawns
                # For black moves, if eval increases, black lost centipawns
                if is_white_move:
                    # White just moved - eval should be from white's perspective
                    # If eval_before was positive and eval_after is less positive, white lost
                    eval_change = eval_before - eval_after
                else:
                    # Black just moved - eval should be from black's perspective
                    # If eval_before was negative and eval_after is less negative, black lost
                    eval_change = eval_after - eval_before
                
                # CPL is the absolute value of the loss
                return abs(eval_change)
    
    @staticmethod
    def calculate_cpl_for_mate(
        is_white_move: bool,
        eval_before: float,
        eval_after: float,
        is_mate_before: bool,
        mate_moves_before: int,
        is_mate_after: bool,
        mate_moves_after: int
    ) -> float:
        """Calculate CPL when mate positions are involved.
        
        Args:
            is_white_move: True if white just moved, False if black.
            eval_before: Evaluation before move (centipawns, may be mate-derived).
            eval_after: Evaluation after move (centipawns, may be mate-derived).
            is_mate_before: True if position before was mate.
            mate_moves_before: Mate moves before (positive = white winning, negative = black winning).
            is_mate_after: True if position after is mate.
            mate_moves_after: Mate moves after (positive = white winning, negative = black winning).
            
        Returns:
            CPL value in centipawns.
        """
        # If neither position is mate, this shouldn't be called, but handle it
        if not is_mate_before and not is_mate_after:
            # Fall back to normal calculation
            if is_white_move:
                return abs(eval_before - eval_after)
            else:
                return abs(eval_after - eval_before)
        
        # Both positions are mate
        if is_mate_before and is_mate_after:
            # Check if mate_moves_after is 0 (checkmate achieved)
            # Checkmate is always the best move - CPL should be 0
            if mate_moves_after == 0:
                # Checkmate achieved - this is the best move
                return 0.0
            
            # Mate moves: positive = white winning, negative = black winning
            # If mate is for the same side, compare distances
            # Same side is winning - calculate difference in mate distance
            if (mate_moves_before > 0 and mate_moves_after > 0) or (mate_moves_before < 0 and mate_moves_after < 0):
                # Same side is winning - calculate difference in mate distance
                # Note: mate_moves is the number of moves TO mate, so smaller = closer to mate = better
                mate_distance_before = abs(mate_moves_before)
                mate_distance_after = abs(mate_moves_after)
                mate_distance_change = mate_distance_after - mate_distance_before
                
                # Calculate CPL based on whether the move improved or worsened the position
                # mate_distance_change > 0 means mate got further away (worse for the winning side)
                # mate_distance_change < 0 means mate got closer (better for the winning side)
                
                # For the winning side: negative change (closer to mate) = good, positive change (further) = bad
                # For the losing side: any change that makes mate further away is good
                
                if is_white_move:
                    # White just moved
                    if mate_moves_after > 0:
                        # White is winning
                        # Negative change = closer to mate (good) = low CPL
                        # Positive change = further from mate (bad) = high CPL
                        if mate_distance_change <= 0:
                            # Mate got closer or stayed same - good move
                            return abs(mate_distance_change) * 50  # Small CPL
                        else:
                            # Mate got further away - bad move
                            return mate_distance_change * 100
                    else:
                        # Black is winning (white is losing)
                        # Negative change = mate got further away (good for white) = low CPL
                        # Positive change = mate got closer (bad for white) = high CPL
                        if mate_distance_change >= 0:
                            # Mate got closer or stayed same - bad for white
                            return mate_distance_change * 100
                        else:
                            # Mate got further away - good for white
                            return abs(mate_distance_change) * 50
                else:
                    # Black just moved
                    if mate_moves_after < 0:
                        # Black is winning
                        # Negative change = closer to mate (good) = low CPL
                        # Positive change = further from mate (bad) = high CPL
                        if mate_distance_change <= 0:
                            # Mate got closer or stayed same - good move
                            return abs(mate_distance_change) * 50
                        else:
                            # Mate got further away - bad move
                            return mate_distance_change * 100
                    else:
                        # White is winning (black is losing)
                        # Negative change = mate got further away (good for black) = low CPL
                        # Positive change = mate got closer (bad for black) = high CPL
                        if mate_distance_change >= 0:
                            # Mate got closer or stayed same - bad for black
                            return mate_distance_change * 100
                        else:
                            # Mate got further away - good for black
                            return abs(mate_distance_change) * 50
            
            else:
                # Mate switched sides - this is a huge mistake
                # Use the evaluation difference as CPL
                if is_white_move:
                    return abs(eval_before - eval_after)
                else:
                    return abs(eval_after - eval_before)
        
        # Only position before is mate
        elif is_mate_before:
            # Position before was mate, after is not
            # This means the move escaped mate (or the engine evaluation changed)
            # Calculate based on evaluation change
            if is_white_move:
                return abs(eval_before - eval_after)
            else:
                return abs(eval_after - eval_before)
        
        # Only position after is mate
        else:  # is_mate_after
            # Position before was not mate, after is mate
            # This could be a good move (creating mate) or a bad move (allowing mate)
            
            # Check if mate is for the side that just moved (creating mate) or opponent (allowing mate)
            # mate_moves_after = 0 means checkmate for the side to move
            # If white just moved and mate_moves_after = 0, then black is to move and black is mated → white created checkmate
            # If black just moved and mate_moves_after = 0, then white is to move and white is mated → black created checkmate
            if is_white_move:
                # White just moved - check if mate benefits white
                if mate_moves_after > 0:
                    # White created mate in N moves - this is a GOOD move
                    return 0.0
                elif mate_moves_after == 0:
                    # mate_moves_after = 0 means checkmate for the side to move (Black)
                    # Since White just moved, Black is to move and Black is mated → White created checkmate
                    # This is the BEST move - CPL should be 0
                    return 0.0
                else:
                    # White allowed mate for black (mate_moves_after < 0) - this is a BLUNDER
                    # CPL = difference in evaluation
                    return abs(eval_before - eval_after)
            else:
                # Black just moved - check if mate benefits black
                if mate_moves_after < 0:
                    # Black created mate in N moves - this is a GOOD move
                    return 0.0
                elif mate_moves_after == 0:
                    # mate_moves_after = 0 means checkmate for the side to move (White)
                    # Since Black just moved, White is to move and White is mated → Black created checkmate
                    # This is the BEST move - CPL should be 0
                    return 0.0
                else:
                    # Black allowed mate for white (mate_moves_after > 0) - this is a BLUNDER
                    return abs(eval_after - eval_before)
    
    @staticmethod
    def calculate_pv_cpl(pv_score: float, eval_after: float) -> float:
        """Calculate CPL for PV2/PV3 moves.
        
        Args:
            pv_score: Evaluation score for the PV move (centipawns).
            eval_after: Evaluation after the played move (centipawns).
            
        Returns:
            CPL value in centipawns.
        """
        return abs(pv_score - eval_after)
    
    @staticmethod
    def is_move_in_top3(
        played_move: str,
        best_move: str,
        pv2_move: str,
        pv3_move: str
    ) -> bool:
        """Check if played move is in top 3 moves.
        
        Args:
            played_move: Played move in SAN notation.
            best_move: Best move in SAN notation.
            pv2_move: PV2 move in SAN notation.
            pv3_move: PV3 move in SAN notation.
            
        Returns:
            True if played move matches any of the top 3 moves.
        """
        played_normalized = MoveAnalysisService.normalize_move(played_move)
        best_normalized = MoveAnalysisService.normalize_move(best_move)
        pv2_normalized = MoveAnalysisService.normalize_move(pv2_move)
        pv3_normalized = MoveAnalysisService.normalize_move(pv3_move)
        
        return (played_normalized == best_normalized or
                played_normalized == pv2_normalized or
                played_normalized == pv3_normalized)
    
    @staticmethod
    def assess_move_quality(
        cpl: float,
        eval_before: float,
        eval_after: float,
        move_info: Dict[str, Any],
        best_move_san: str,
        moves_match: bool,
        classification_thresholds: Dict[str, Any],
        material_sacrifice: int = 0
    ) -> str:
        """Assess move quality based on CPL and evaluation change.
        
        Args:
            cpl: Centipawn loss.
            eval_before: Evaluation before move.
            eval_after: Evaluation after move.
            move_info: Move information dictionary.
            best_move_san: Best move suggestion.
            moves_match: True if the played move matches the best move.
            classification_thresholds: Dictionary with thresholds:
                - good_move_max_cpl: Maximum CPL for "Good Move"
                - inaccuracy_max_cpl: Maximum CPL for "Inaccuracy"
                - mistake_max_cpl: Maximum CPL for "Mistake"
            material_sacrifice: Material sacrifice in centipawns (unused, kept for compatibility).
            
        Returns:
            Assessment string (e.g., "Best Move", "Good Move", etc.).
        """
        # Check if played move matches best move - this is always Best Move
        if moves_match:
            return "Best Move"
        
        # Check for miss (must be checked before Mistake/Blunder classification)
        if MoveAnalysisService.is_miss(
            move_info, best_move_san, classification_thresholds.get("best_move_is_mate", False), cpl
        ):
            return "Miss"
        
        # Check based on CPL thresholds
        good_move_max_cpl = classification_thresholds.get("good_move_max_cpl", 50)
        inaccuracy_max_cpl = classification_thresholds.get("inaccuracy_max_cpl", 100)
        mistake_max_cpl = classification_thresholds.get("mistake_max_cpl", 200)
        
        if cpl <= good_move_max_cpl:
            return "Good Move"
        elif cpl <= inaccuracy_max_cpl:
            return "Inaccuracy"
        elif cpl <= mistake_max_cpl:
            return "Mistake"
        else:
            # Anything above mistake_max_cpl is a Blunder
            return "Blunder"
    
    @staticmethod
    def is_brilliant_move(
        eval_before: float,
        eval_after: float,
        move_info: Dict[str, Any],
        best_move_san: str,
        cpl: float,
        classification_thresholds: Dict[str, Any],
        material_sacrifice: int
    ) -> bool:
        """Check if a move is brilliant (Chess.com criteria).
        
        Args:
            eval_before: Evaluation before move (centipawns).
            eval_after: Evaluation after move (centipawns).
            move_info: Move information dictionary.
            best_move_san: Best move suggestion.
            cpl: Centipawn loss (difference from best move).
            classification_thresholds: Dictionary with thresholds (see assess_move_quality).
            material_sacrifice: Material sacrifice in centipawns.
            
        Returns:
            True if move is brilliant, False otherwise.
        """
        # Calculate eval swing
        eval_swing = eval_after - eval_before
        is_white_move = move_info["is_white_move"]
        
        min_material_sacrifice = classification_thresholds.get("min_material_sacrifice", 100)
        min_eval_swing = classification_thresholds.get("min_eval_swing", 200)
        max_eval_before = classification_thresholds.get("max_eval_before", 500)
        exclude_already_winning = classification_thresholds.get("exclude_already_winning", True)
        
        # Check 1: Material sacrifice (must be piece level)
        if material_sacrifice < min_material_sacrifice:
            return False
        
        # Check 2: Eval swing threshold
        if is_white_move:
            if eval_swing < min_eval_swing:
                return False
        else:
            if eval_swing > -min_eval_swing:
                return False
        
        # Check 3: Exclude if already completely winning (configurable)
        if exclude_already_winning:
            if is_white_move:
                if eval_before > max_eval_before:
                    return False
            else:
                if eval_before < -max_eval_before:
                    return False
        
        # All checks passed
        return True
    
    @staticmethod
    def is_miss(
        move_info: Dict[str, Any],
        best_move_san: str,
        best_move_is_mate: bool,
        cpl: float,
        classification_thresholds: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Check if a move is a miss (failed to capitalize on tactical opportunity).
        
        A miss occurs when:
        1. The best move is a tactical opportunity (capture or checkmate)
        2. The played move fails to capitalize on this opportunity
        3. The CPL is significant (>= 100 centipawns)
        4. The move would be classified as Mistake/Blunder or Inaccuracy with high CPL
        
        Args:
            move_info: Move information dictionary.
            best_move_san: Best move suggestion in SAN notation.
            best_move_is_mate: True if best move leads to checkmate.
            cpl: Centipawn loss.
            classification_thresholds: Optional dictionary with thresholds.
            
        Returns:
            True if move is a miss, False otherwise.
        """
        # 1. Must have significant CPL (missed at least 1 pawn)
        if cpl < 100:
            return False
        
        # Get board_before for move analysis
        board_before = move_info["board_before"]
        
        # 2. Best move must be a tactical opportunity (capture or checkmate)
        best_move_is_tactical = False
        if best_move_is_mate:
            best_move_is_tactical = True
        else:
            # Check if best move is a capture
            try:
                # Try to parse best move from SAN
                best_move = board_before.parse_san(best_move_san)
                if board_before.is_capture(best_move):
                    best_move_is_tactical = True
            except Exception:
                # If parsing fails, check SAN notation for capture symbol 'x'
                if 'x' in best_move_san:
                    best_move_is_tactical = True
        
        if not best_move_is_tactical:
            return False
        
        # 3. Played move should NOT be a capture or checkmate
        # If the played move was already a capture or checkmate, it's not a "miss"
        # (the player didn't miss the opportunity, they just chose a different capture/mate)
        played_move = move_info["move"]
        played_move_san = move_info["move_san"]
        board_after = move_info["board_after"]
        
        # Check if played move is a checkmate
        played_move_is_mate = False
        if '#' in played_move_san:
            # Checkmate symbol in SAN notation
            played_move_is_mate = True
        elif board_after.is_checkmate():
            # Position after move is checkmate
            played_move_is_mate = True
        
        # Check if played move is a capture
        played_move_is_capture = board_before.is_capture(played_move)
        
        # If played move is a capture or checkmate, it's not a miss
        if played_move_is_capture or played_move_is_mate:
            return False
        
        # 4. Assessment should indicate a significant error
        # Check if move would be classified as Mistake/Blunder or Inaccuracy with high CPL
        # Miss can be Mistake, Blunder, or Inaccuracy if CPL is high enough
        if classification_thresholds:
            inaccuracy_max_cpl = classification_thresholds.get("inaccuracy_max_cpl", 100)
            mistake_max_cpl = classification_thresholds.get("mistake_max_cpl", 200)
            
            if cpl <= inaccuracy_max_cpl:
                # Would be classified as Good Move or Inaccuracy - not a miss
                return False
            elif cpl <= mistake_max_cpl:
                # Would be classified as Inaccuracy - only miss if CPL is high enough
                if cpl < 150:
                    return False
        else:
            # Default thresholds if not provided
            if cpl <= 100:
                return False
            elif cpl <= 200:
                if cpl < 150:
                    return False
        
        return True
    
    @staticmethod
    def calculate_material_sacrifice(
        move_info: Dict[str, Any],
        moves_sequence: List[Dict[str, Any]],
        current_index: int,
        lookahead_plies: int = 1
    ) -> int:
        """Calculate material sacrifice for a move.
        
        This method checks for material sacrifice in two ways:
        1. Direct material loss: The move itself loses material
        2. Forced material loss: The move leaves a piece en prise (undefended)
           and the opponent captures it on their next move(s).
        
        A move is NOT considered a sacrifice if:
        - The move itself captures material (gains material)
        - The opponent's later capture is unrelated to the current move
        
        Args:
            move_info: Current move information dictionary.
            moves_sequence: List of all moves in the game sequence.
            current_index: Index of current move in moves_sequence.
            lookahead_plies: Number of plies to look ahead (default: 1 for immediate capture).
            
        Returns:
            Material sacrifice in centipawns (positive = material was sacrificed).
        """
        if current_index is None or current_index < 0 or current_index >= len(moves_sequence):
            return 0
        
        board_before = move_info["board_before"]
        board_after = move_info["board_after"]
        move = move_info["move"]
        is_white_move = move_info["is_white_move"]
        
        # Check 1: Direct material loss (move itself loses material)
        direct_loss = calculate_material_loss(
            board_before,
            board_after,
            is_white_move
        )
        if direct_loss > 0:
            # Direct sacrifice - move itself loses material
            return direct_loss
        
        # Check 2: If current move is a capture (gains material), it's not a sacrifice
        if board_before.is_capture(move):
            # Current move captures material - not a sacrifice
            return 0
        
        # Check 3: Forced material loss (piece left en prise) over look-ahead window
        balance_after_current = calculate_material_balance(board_after)
        max_material_loss = 0
        
        # Check material balance over next plies
        for i in range(1, min(lookahead_plies + 1, len(moves_sequence) - current_index)):
            if current_index + i >= len(moves_sequence):
                break
            
            next_move_info = moves_sequence[current_index + i]
            
            # Only check opponent's moves (alternating turns)
            if next_move_info["is_white_move"] == move_info["is_white_move"]:
                continue  # Same side - skip
            
            # Check if opponent's move is a capture
            next_move = next_move_info["move"]
            next_board_before = next_move_info["board_before"]
            
            if next_board_before.is_capture(next_move):
                # Opponent captures something - check if it's a piece left en prise
                captured_square = next_move.to_square
                captured_piece = board_after.piece_at(captured_square)
                
                if captured_piece is not None:
                    # Check if the captured piece was left undefended after current move
                    # (i.e., it was left en prise)
                    piece_color = captured_piece.color
                    opponent_color = chess.BLACK if piece_color == chess.WHITE else chess.WHITE
                    
                    # Check if the piece was undefended after the current move
                    is_undefended = not board_after.is_attacked_by(opponent_color, captured_square)
                    
                    if is_undefended:
                        # Piece was left en prise - calculate material loss
                        balance_after_next = calculate_material_balance(next_move_info["board_after"])
                        
                        # Calculate material loss for current side
                        if is_white_move:
                            # White's move: if balance decreases, White lost material
                            material_loss = balance_after_current - balance_after_next
                        else:
                            # Black's move: if balance increases, Black lost material
                            material_loss = balance_after_next - balance_after_current
                        
                        # Track maximum material loss in the look-ahead window
                        if material_loss > max_material_loss:
                            max_material_loss = material_loss
        
        return max_material_loss
    
    @staticmethod
    def format_evaluation(centipawns: float, is_mate: bool, mate_moves: int, is_white_move: bool) -> str:
        """Format evaluation for display.
        
        Args:
            centipawns: Evaluation in centipawns.
            is_mate: True if mate was found.
            mate_moves: Number of moves to mate (positive = white winning, negative = black winning, 0 = checkmate for side to move).
            is_white_move: True if white just moved, False if black just moved.
            
        Returns:
            Formatted evaluation string.
        """
        if is_mate:
            if mate_moves > 0:
                # White is winning (mate in N moves for white)
                # Evaluation is positive from white's perspective
                return f"M{mate_moves}"
            elif mate_moves < 0:
                # Black is winning (mate in N moves for black)
                # Evaluation is negative from white's perspective
                # Show as -M0, -M1, etc. to indicate black is winning
                return f"-M{abs(mate_moves)}"
            else:
                # mate_moves = 0 means checkmate for the side to move
                # If white just moved and mate_moves = 0, then black is to move and black is mated → white wins → M0
                # If black just moved and mate_moves = 0, then white is to move and white is mated → black wins → -M0
                if is_white_move:
                    # White just moved, black is mated → white wins
                    return "M0"
                else:
                    # Black just moved, white is mated → black wins
                    return "-M0"
        else:
            # Convert centipawns to pawns with one decimal
            pawns = centipawns / 100.0
            sign = "+" if pawns >= 0 else ""
            return f"{sign}{pawns:.1f}"
    
    @staticmethod
    def format_cpl(cpl: float) -> str:
        """Format CPL for display.
        
        Args:
            cpl: Centipawn loss.
            
        Returns:
            Formatted CPL string.
        """
        return f"{int(cpl)}"

