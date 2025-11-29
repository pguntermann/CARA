"""Rule for evaluating backward pawns."""

from typing import Dict
import chess

from app.services.positional_heatmap.base_rule import PositionalRule


class BackwardPawnRule(PositionalRule):
    """Rule that evaluates backward pawns.
    
    A backward pawn is a pawn that is behind friendly pawns on adjacent files
    and cannot advance safely. Backward pawns are generally weak.
    """
    
    def __init__(self, config: Dict) -> None:
        """Initialize the backward pawn rule.
        
        Args:
            config: Rule configuration dictionary.
        """
        super().__init__(config)
        self.backward_pawn_penalty = config.get('score', -15.0)
        self.defended_pawn_penalty = config.get('defended_score', -8.0)
    
    def evaluate(self, board: chess.Board, perspective: chess.Color) -> Dict[chess.Square, float]:
        """Evaluate backward pawns in the position.
        
        Args:
            board: Current chess position.
            perspective: Color to evaluate from.
        
        Returns:
            Dictionary mapping square -> score.
            Negative scores for backward pawns.
        """
        scores: Dict[chess.Square, float] = {}
        
        # Get all pawns for the perspective color
        pawns = board.pieces(chess.PAWN, perspective)
        
        for pawn_square in pawns:
            file = chess.square_file(pawn_square)
            rank = chess.square_rank(pawn_square)
            
            if self._is_backward_pawn(board, file, rank, perspective):
                # Check if the pawn itself is defended by adjacent pawns
                is_defended = self._is_pawn_defended_by_adjacent_pawn(board, file, rank, perspective)
                if is_defended:
                    scores[pawn_square] = self.defended_pawn_penalty
                else:
                    scores[pawn_square] = self.backward_pawn_penalty
        
        return scores
    
    def _is_backward_pawn(self, board: chess.Board, file: int, rank: int, color: chess.Color) -> bool:
        """Check if a pawn is backward.
        
        A backward pawn:
        1. Has friendly pawns on adjacent files that are ahead of it
        2. Cannot advance safely (would be attacked by enemy pawns)
        
        Args:
            board: Current position.
            file: Pawn's file (0-7).
            rank: Pawn's rank (0-7).
            color: Pawn's color.
        
        Returns:
            True if pawn is backward, False otherwise.
        """
        friendly_pawns = board.pieces(chess.PAWN, color)
        opponent_pawns = board.pieces(chess.PAWN, not color)
        
        # Check adjacent files for friendly pawns ahead
        adjacent_files = []
        if file > 0:
            adjacent_files.append(file - 1)
        if file < 7:
            adjacent_files.append(file + 1)
        
        has_friendly_pawns_ahead = False
        
        if color == chess.WHITE:
            # White pawn: check if adjacent files have pawns on higher ranks
            for adj_file in adjacent_files:
                for check_rank in range(rank + 1, 8):
                    check_square = chess.square(adj_file, check_rank)
                    if check_square in friendly_pawns:
                        has_friendly_pawns_ahead = True
                        break
                if has_friendly_pawns_ahead:
                    break
        else:
            # Black pawn: check if adjacent files have pawns on lower ranks
            for adj_file in adjacent_files:
                for check_rank in range(rank - 1, -1, -1):
                    check_square = chess.square(adj_file, check_rank)
                    if check_square in friendly_pawns:
                        has_friendly_pawns_ahead = True
                        break
                if has_friendly_pawns_ahead:
                    break
        
        if not has_friendly_pawns_ahead:
            return False  # Not backward if no friendly pawns ahead
        
        # Check if pawn can advance safely
        # A backward pawn cannot advance because it would be attacked
        if color == chess.WHITE:
            if rank >= 7:
                return True  # Can't advance anyway
            front_square = chess.square(file, rank + 1)
        else:
            if rank <= 0:
                return True  # Can't advance anyway
            front_square = chess.square(file, rank - 1)
        
        # Check if advancing would be attacked by enemy pawns
        # A pawn is only backward if it cannot advance safely AND cannot be defended by friendly pawns
        # Check diagonal attacks from enemy pawns on adjacent files
        attack_files = []
        if file > 0:
            attack_files.append(file - 1)
        if file < 7:
            attack_files.append(file + 1)
        
        # Check if any enemy pawns can attack the front square
        can_be_attacked = False
        attacking_pawns = []
        
        for attack_file in attack_files:
            if attack_file < 0 or attack_file > 7:
                continue
            
            # Check all enemy pawns on this adjacent file
            for attack_square in opponent_pawns:
                attack_file_check = chess.square_file(attack_square)
                attack_rank_check = chess.square_rank(attack_square)
                
                if attack_file_check != attack_file:
                    continue
                
                # Check if this enemy pawn can attack the front square
                if color == chess.WHITE:
                    front_rank = rank + 1
                    if attack_rank_check >= front_rank:
                        # Enemy pawn can attack the square in front
                        can_be_attacked = True
                        attacking_pawns.append(attack_square)
                else:
                    front_rank = rank - 1
                    if attack_rank_check <= front_rank:
                        # Enemy pawn can attack the square in front
                        can_be_attacked = True
                        attacking_pawns.append(attack_square)
        
        if not can_be_attacked:
            return False  # Can advance safely, not backward
        
        # Check if friendly pawns can defend the front square
        # If a friendly pawn on an adjacent file can defend it, it's not truly backward
        if color == chess.WHITE:
            front_rank = rank + 1
            # Check if friendly pawns on adjacent files can defend f3
            # A pawn on g2 (rank 1) can defend f3 (rank 2) diagonally
            for defense_file in attack_files:
                if defense_file < 0 or defense_file > 7:
                    continue
                for defense_square in friendly_pawns:
                    defense_file_check = chess.square_file(defense_square)
                    defense_rank_check = chess.square_rank(defense_square)
                    
                    if defense_file_check != defense_file:
                        continue
                    
                    # Check if this friendly pawn can defend the front square
                    # For white: friendly pawn must be exactly 1 rank below to defend upward diagonally
                    # A pawn on g2 (file 6, rank 1) can attack f3 (file 5, rank 2) diagonally
                    # A pawn on g3 (file 6, rank 2) can attack f4 (file 5, rank 3) diagonally
                    if defense_rank_check == front_rank - 1:
                        # Friendly pawn can defend the square in front (diagonally)
                        # We're already checking pawns on adjacent files (defense_file == attack_file)
                        # So this pawn can defend the front square
                        return False  # Not backward, can be defended
        else:
            front_rank = rank - 1
            # Check if friendly pawns on adjacent files can defend
            for defense_file in attack_files:
                if defense_file < 0 or defense_file > 7:
                    continue
                for defense_square in friendly_pawns:
                    defense_file_check = chess.square_file(defense_square)
                    defense_rank_check = chess.square_rank(defense_square)
                    
                    if defense_file_check != defense_file:
                        continue
                    
                    # Check if this friendly pawn can defend the front square
                    # For black: friendly pawn must be exactly 1 rank above to defend downward diagonally
                    if defense_rank_check == front_rank + 1:
                        # Friendly pawn can defend the square in front (diagonally)
                        # We're already checking pawns on adjacent files (defense_file == attack_file)
                        # So this pawn can defend the front square
                        return False  # Not backward, can be defended
        
        # Can be attacked and cannot be defended by friendly pawns
        return True  # Backward pawn
    
    def _is_pawn_defended_by_adjacent_pawn(self, board: chess.Board, file: int, rank: int, color: chess.Color) -> bool:
        """Check if a pawn is defended by an adjacent friendly pawn.
        
        A pawn is defended by an adjacent pawn if there's a friendly pawn on an adjacent file
        that can attack the pawn's square diagonally.
        
        Args:
            board: Current position.
            file: Pawn's file (0-7).
            rank: Pawn's rank (0-7).
            color: Pawn's color.
            
        Returns:
            True if pawn is defended by an adjacent pawn, False otherwise.
        """
        friendly_pawns = board.pieces(chess.PAWN, color)
        pawn_square = chess.square(file, rank)
        
        # Check adjacent files
        adjacent_files = []
        if file > 0:
            adjacent_files.append(file - 1)
        if file < 7:
            adjacent_files.append(file + 1)
        
        # Check if any friendly pawn on adjacent files can defend this pawn
        for adj_file in adjacent_files:
            for defense_square in friendly_pawns:
                defense_file = chess.square_file(defense_square)
                defense_rank = chess.square_rank(defense_square)
                
                if defense_file != adj_file:
                    continue
                
                # Check if this friendly pawn can attack the pawn's square diagonally
                if color == chess.WHITE:
                    # For white: friendly pawn must be exactly 1 rank below to defend upward diagonally
                    # A pawn on b2 (file 1, rank 1) can attack c3 (file 2, rank 2) diagonally
                    if defense_rank == rank - 1:
                        # Check if the pawn can actually attack the square (diagonal)
                        # A pawn on adjacent file, 1 rank below, can attack diagonally
                        return True
                else:
                    # For black: friendly pawn must be exactly 1 rank above to defend downward diagonally
                    # A pawn on b7 (file 1, rank 6) can attack c6 (file 2, rank 5) diagonally
                    if defense_rank == rank + 1:
                        # Check if the pawn can actually attack the square (diagonal)
                        # A pawn on adjacent file, 1 rank above, can attack diagonally
                        return True
        
        return False

