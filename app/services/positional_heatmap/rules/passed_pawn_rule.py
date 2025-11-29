"""Rule for evaluating passed pawns."""

from typing import Dict
import chess

from app.services.positional_heatmap.base_rule import PositionalRule


class PassedPawnRule(PositionalRule):
    """Rule that evaluates passed pawns.
    
    A passed pawn is a pawn with no enemy pawns in front of it on the same file
    or adjacent files. Passed pawns are generally advantageous.
    """
    
    def __init__(self, config: Dict) -> None:
        """Initialize the passed pawn rule.
        
        Args:
            config: Rule configuration dictionary.
        """
        super().__init__(config)
        self.passed_pawn_score = config.get('score', 20.0)
    
    def evaluate(self, board: chess.Board, perspective: chess.Color) -> Dict[chess.Square, float]:
        """Evaluate passed pawns in the position.
        
        Args:
            board: Current chess position.
            perspective: Color to evaluate from.
        
        Returns:
            Dictionary mapping square -> score.
            Positive scores for passed pawns. Blocked pawns are not evaluated.
        """
        scores: Dict[chess.Square, float] = {}
        opponent = not perspective
        
        # Get all pawns for the perspective color
        pawns = board.pieces(chess.PAWN, perspective)
        
        # Central files (c, d, e, f)
        central_files = [2, 3, 4, 5]  # c, d, e, f
        
        for pawn_square in pawns:
            file = chess.square_file(pawn_square)
            rank = chess.square_rank(pawn_square)
            
            # Get the pawn's actual color
            piece = board.piece_at(pawn_square)
            if piece is None:
                continue
            pawn_color = piece.color
            
            # Initialize pawn score
            pawn_score = 0.0
            
            # Check if pawn is on starting rank - cannot be passed
            is_on_starting_rank = self._is_on_starting_rank(rank, pawn_color)
            if is_on_starting_rank:
                # Pawn on starting rank - not passed, skip evaluation
                # Don't add any score (central pawn bonus should be handled by a separate rule)
                continue
            
            # Check if pawn is blocked - cannot be passed
            # Blocked pawns should not get scores from the passed pawn rule
            is_blocked = self._is_blocked_pawn(board, file, rank, pawn_color)
            if is_blocked:
                # Blocked pawn - not passed, skip evaluation
                # Don't add any score (blocked pawn penalties should be handled by a separate rule)
                continue
            
            # Bonus for central pawns (control center) - only for non-starting rank, non-blocked pawns
            if file in central_files:
                pawn_score = 10.0
            
            # Check if pawn is attacked/defended (needed for passed pawn evaluation)
            is_attacked = board.is_attacked_by(opponent, pawn_square)
            is_defended = board.is_attacked_by(pawn_color, pawn_square)
            
            # Re-check starting rank before checking if passed (safety check)
            # This ensures we never evaluate starting rank pawns as passed
            if self._is_on_starting_rank(rank, pawn_color):
                # Pawn on starting rank - not passed, but may still have central bonus
                if pawn_score != 0.0:
                    scores[pawn_square] = pawn_score
                continue
            
            # Check if pawn is passed (only if not blocked and not on starting rank)
            is_passed = self._is_passed_pawn(board, file, rank, pawn_color)
            
            if is_passed:
                # Passed pawn - calculate bonus scaled by rank advancement
                # The closer to promotion, the bigger the bonus
                base_bonus = self._passed_pawn_bonus(rank, pawn_color)
                passed_bonus = base_bonus
                
                # Adjust bonus based on pawn's situation
                if is_attacked and not is_defended:
                    # Attacked and undefended passed pawn is less valuable
                    # For advanced passed pawns (rank 4+), they're neutral (0.0) - not valuable but not penalized
                    # Only apply negative penalty for early-rank passed pawns
                    if rank < 4:  # Early rank (rank 2-3, chess ranks 3-4)
                        # Early rank passed pawn that's attacked and undefended is weak
                        pawn_score = 0.0  # Reset central bonus
                        passed_bonus = -base_bonus * 0.5  # Negative score
                    else:
                        # Advanced passed pawn (rank 4+, chess rank 5+) - neutral (0.0)
                        # Even advanced passed pawns that are attacked and undefended are often liabilities
                        passed_bonus = 0.0  # Neutral - not valuable but not penalized
                elif is_attacked:
                    # Attacked but defended passed pawn is less valuable
                    passed_bonus *= 0.4  # Reduce to 40% of original bonus
                
                pawn_score += passed_bonus
            else:
                # Not passed - don't return a score for non-passed pawns
                # (Weak advanced pawns should be handled by a separate rule if needed)
                # Reset pawn_score to 0 to avoid returning central pawn bonus for non-passed pawns
                pawn_score = 0.0
            
            # Only add score if it's non-zero
            if pawn_score != 0.0:
                scores[pawn_square] = pawn_score
        
        return scores
    
    def _is_on_starting_rank(self, rank: int, color: chess.Color) -> bool:
        """Check if a pawn is on its starting rank.
        
        Args:
            rank: Pawn's rank (0-7).
            color: Pawn's color.
        
        Returns:
            True if pawn is on starting rank, False otherwise.
        """
        if color == chess.WHITE:
            return rank <= 1  # White pawns start on rank 1
        else:  # BLACK
            return rank >= 6  # Black pawns start on rank 6
    
    def _passed_pawn_bonus(self, rank: int, color: chess.Color) -> float:
        """Calculate passed pawn bonus scaled by rank advancement.
        
        The closer to promotion, the bigger the bonus.
        - Starting rank pawns: excluded (should not call this method)
        - Early ranks: tiny bonus (almost negligible)
        - Advanced ranks: medium bonus
        - Near promotion: huge bonus
        
        Args:
            rank: Pawn's rank (0-7).
            color: Pawn's color.
        
        Returns:
            Scaled bonus based on rank advancement.
        """
        if color == chess.WHITE:
            # White pawn: rank 2 = tiny bonus, rank 7 = huge bonus
            # rank 2: (2-1)*5 = 5.0
            # rank 3: (3-1)*5 = 10.0
            # rank 4: (4-1)*5 = 15.0
            # rank 5: (5-1)*5 = 20.0
            # rank 6: (6-1)*5 = 25.0
            # rank 7: (7-1)*5 = 30.0
            if rank <= 1:
                return 0.0  # Starting rank - should not happen, but safety check
            return (rank - 1) * 5.0
        else:  # BLACK
            # Black pawn: rank 5 = tiny bonus, rank 0 = huge bonus
            # rank 5: (6-5)*5 = 5.0
            # rank 4: (6-4)*5 = 10.0
            # rank 3: (6-3)*5 = 15.0
            # rank 2: (6-2)*5 = 20.0
            # rank 1: (6-1)*5 = 25.0
            # rank 0: (6-0)*5 = 30.0
            if rank >= 6:
                return 0.0  # Starting rank - should not happen, but safety check
            return (6 - rank) * 5.0
    
    def _is_passed_pawn(self, board: chess.Board, file: int, rank: int, color: chess.Color) -> bool:
        """Check if a pawn is passed.
        
        A passed pawn has no enemy pawns in front of it on the same file
        or adjacent files. A pawn on its starting rank cannot be passed.
        
        Args:
            board: Current position.
            file: Pawn's file (0-7).
            rank: Pawn's rank (0-7).
            color: Pawn's color.
        
        Returns:
            True if pawn is passed, False otherwise.
        """
        # Safety check: pawns on starting rank cannot be passed
        if self._is_on_starting_rank(rank, color):
            return False
        
        opponent = not color
        opponent_pawns = board.pieces(chess.PAWN, opponent)
        
        # Determine ranks ahead (pawns move forward)
        if color == chess.WHITE:
            # White pawn: check ranks ahead (higher rank numbers)
            ranks_to_check = range(rank + 1, 8)
        else:  # BLACK
            # Black pawn: check ranks ahead (lower rank numbers)
            ranks_to_check = range(rank - 1, -1, -1)
        
        # Check files: same file and adjacent files
        files_to_check = [file]
        if file > 0:
            files_to_check.append(file - 1)
        if file < 7:
            files_to_check.append(file + 1)
        
        # Check if any enemy pawns are in the path
        for check_rank in ranks_to_check:
            for check_file in files_to_check:
                check_square = chess.square(check_file, check_rank)
                if check_square in opponent_pawns:
                    return False  # Enemy pawn blocks the path
        
        return True  # No enemy pawns in path
    
    def _is_blocked_pawn(self, board: chess.Board, file: int, rank: int, color: chess.Color) -> bool:
        """Check if a pawn is blocked (has a piece directly in front).
        
        Args:
            board: Current position.
            file: Pawn's file (0-7).
            rank: Pawn's rank (0-7).
            color: Pawn's color.
        
        Returns:
            True if pawn is blocked, False otherwise.
        """
        # Determine square directly in front
        if color == chess.WHITE:
            if rank >= 7:
                return False  # Can't move forward anyway
            front_square = chess.square(file, rank + 1)
        else:  # BLACK
            if rank <= 0:
                return False  # Can't move forward anyway
            front_square = chess.square(file, rank - 1)
        
        # Check if there's any piece (friend or foe) in front
        return board.piece_at(front_square) is not None
    
    def _is_open_file(self, board: chess.Board, file: int, pawn_square: chess.Square, 
                      color: chess.Color) -> bool:
        """Check if a pawn is on an open file (no friendly pawns on the file).
        
        Args:
            board: Current position.
            file: Pawn's file (0-7).
            pawn_square: The pawn's square.
            color: Pawn's color.
        
        Returns:
            True if pawn is on an open file, False otherwise.
        """
        friendly_pawns = board.pieces(chess.PAWN, color)
        for friendly_pawn_square in friendly_pawns:
            if friendly_pawn_square != pawn_square:
                if chess.square_file(friendly_pawn_square) == file:
                    return False  # Another friendly pawn on the same file
        return True  # No other friendly pawns on the file
    
    def _is_weak_advanced_pawn(self, board: chess.Board, file: int, rank: int, 
                                color: chess.Color, is_attacked: bool, is_defended: bool) -> bool:
        """Check if a pawn is a weak advanced pawn.
        
        A weak advanced pawn is:
        1. Advanced (on rank 4+ for white, rank 3- for black)
        2. Not well supported (no friendly pawns on adjacent files behind it)
        
        Args:
            board: Current position.
            file: Pawn's file (0-7).
            rank: Pawn's rank (0-7).
            color: Pawn's color.
            is_attacked: Whether pawn is attacked by opponent.
            is_defended: Whether pawn is defended by friendly pieces.
        
        Returns:
            True if pawn is a weak advanced pawn, False otherwise.
        """
        # Check if pawn is advanced
        if color == chess.WHITE:
            if rank < 4:  # Not advanced enough (needs to be rank 4+)
                return False
        else:  # BLACK
            if rank > 4:  # Not advanced enough (needs to be rank 4 or less)
                return False
        
        # Check if pawn has friendly pawns on adjacent files behind it
        friendly_pawns = board.pieces(chess.PAWN, color)
        adjacent_files = []
        if file > 0:
            adjacent_files.append(file - 1)
        if file < 7:
            adjacent_files.append(file + 1)
        
        for adj_file in adjacent_files:
            if color == chess.WHITE:
                # Check for friendly pawns on lower ranks (behind)
                for check_rank in range(rank):
                    check_square = chess.square(adj_file, check_rank)
                    if check_square in friendly_pawns:
                        return False  # Has support
            else:  # BLACK
                # Check for friendly pawns on higher ranks (behind)
                for check_rank in range(rank + 1, 8):
                    check_square = chess.square(adj_file, check_rank)
                    if check_square in friendly_pawns:
                        return False  # Has support
        
        # Advanced pawn without support is weak
        return True
