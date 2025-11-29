"""Rule for evaluating king safety."""

from typing import Dict
import chess

from app.services.positional_heatmap.base_rule import PositionalRule


class KingSafetyRule(PositionalRule):
    """Rule that evaluates king safety.
    
    Evaluates factors like:
    - Open files near the king (weakness)
    - Pawn shield around king (strength)
    - Piece proximity to king
    """
    
    def __init__(self, config: Dict) -> None:
        """Initialize the king safety rule.
        
        Args:
            config: Rule configuration dictionary.
        """
        super().__init__(config)
        self.open_file_penalty = config.get('open_file_penalty', -10.0)
        self.pawn_shield_bonus = config.get('pawn_shield_bonus', 5.0)
        self.exposed_king_penalty = config.get('exposed_king_penalty', -15.0)
    
    def evaluate(self, board: chess.Board, perspective: chess.Color) -> Dict[chess.Square, float]:
        """Evaluate king safety in the position.
        
        Args:
            board: Current chess position.
            perspective: Color to evaluate from.
        
        Returns:
            Dictionary mapping square -> score.
            Negative scores for unsafe king positions, positive for safe positions.
        """
        scores: Dict[chess.Square, float] = {}
        
        # Get king square
        king_square = board.king(perspective)
        if king_square is None:
            return scores  # No king (shouldn't happen in normal chess)
        
        king_file = chess.square_file(king_square)
        king_rank = chess.square_rank(king_square)
        
        # Check if king is in check - this is the most critical safety issue
        # A king in check should get a significant negative score
        # Check if the king of the perspective color is attacked by the opponent
        opponent = not perspective
        is_in_check = board.is_attacked_by(opponent, king_square)
        if is_in_check:
            # King is in check - this is a critical safety issue
            # Override all other considerations with a strong negative score
            king_score = -30.0  # Strong penalty for being in check
        else:
            # Start with base score (kings are generally safe in normal positions)
            king_score = 0.0
            
            # Check for open files near the king
            open_files = self._get_open_files_near_king(board, king_file, perspective)
            if open_files:
                # Penalty for each open file near king
                king_score += len(open_files) * self.open_file_penalty
            
            # Check for semi-open files near the king (opponent has no pawns on the file)
            # Semi-open files are dangerous because the opponent can attack down that file
            # A semi-open file near the king is almost as dangerous as an open file
            semi_open_files = self._get_semi_open_files_near_king(board, king_file, perspective)
            if semi_open_files:
                # Penalty for each semi-open file near king
                # If the king is on a semi-open file, it's very dangerous (use full penalty)
                # Otherwise, use 90% of open file penalty
                for file in semi_open_files:
                    if file == king_file:
                        # King is on the semi-open file - very dangerous
                        # Use a much higher penalty than open file because the king is directly exposed
                        # This should result in a negative score below the neutral threshold
                        king_score += self.open_file_penalty * 2.0  # 200% of open file penalty
                    else:
                        # Semi-open file adjacent to king - still dangerous
                        king_score += self.open_file_penalty * 0.9  # 90% of open file penalty
            
            # Check pawn shield (this should give positive score in starting position)
            pawn_shield_score = self._evaluate_pawn_shield(board, king_file, king_rank, perspective)
            # Reduce pawn shield bonus if king is on a semi-open file (less protection)
            if semi_open_files and king_file in semi_open_files:
                # King is on a semi-open file - reduce pawn shield effectiveness significantly
                # The pawn shield is less effective because the opponent can attack down the file
                pawn_shield_score *= 0.3  # Reduce to 30% effectiveness
            king_score += pawn_shield_score
            
            # Check if king is exposed (no pawns in front)
            if self._is_king_exposed(board, king_file, king_rank, perspective):
                king_score += self.exposed_king_penalty
        
        # Only add score if it's non-zero (kings should generally be positive in safe positions)
        if king_score != 0.0:
            scores[king_square] = king_score
        
        return scores
    
    def _get_open_files_near_king(self, board: chess.Board, king_file: int, 
                                  color: chess.Color) -> list:
        """Get open files near the king.
        
        An open file has no pawns of either color.
        
        Args:
            board: Current position.
            king_file: King's file (0-7).
            color: King's color.
        
        Returns:
            List of open file numbers near the king.
        """
        open_files = []
        
        # Check files: king's file and adjacent files
        files_to_check = [king_file]
        if king_file > 0:
            files_to_check.append(king_file - 1)
        if king_file < 7:
            files_to_check.append(king_file + 1)
        
        all_pawns = board.pieces(chess.PAWN, chess.WHITE) | board.pieces(chess.PAWN, chess.BLACK)
        
        for file in files_to_check:
            # Check if file has any pawns
            has_pawns = any(chess.square_file(sq) == file for sq in all_pawns)
            if not has_pawns:
                open_files.append(file)
        
        return open_files
    
    def _get_semi_open_files_near_king(self, board: chess.Board, king_file: int, 
                                        color: chess.Color) -> list:
        """Get semi-open files near the king.
        
        A semi-open file has no pawns of the opponent's color, but has pawns of the friendly color.
        This is dangerous for the king because the opponent can attack down that file.
        
        Args:
            board: Current position.
            king_file: King's file (0-7).
            color: King's color.
        
        Returns:
            List of semi-open file numbers near the king.
        """
        semi_open_files = []
        opponent = not color
        
        # Check files: king's file and adjacent files
        files_to_check = [king_file]
        if king_file > 0:
            files_to_check.append(king_file - 1)
        if king_file < 7:
            files_to_check.append(king_file + 1)
        
        friendly_pawns = board.pieces(chess.PAWN, color)
        opponent_pawns = board.pieces(chess.PAWN, opponent)
        
        for file in files_to_check:
            # Check if file has friendly pawns
            has_friendly_pawns = any(chess.square_file(sq) == file for sq in friendly_pawns)
            # Check if file has opponent pawns
            has_opponent_pawns = any(chess.square_file(sq) == file for sq in opponent_pawns)
            
            # Semi-open file: friendly has pawns, opponent doesn't
            if has_friendly_pawns and not has_opponent_pawns:
                semi_open_files.append(file)
        
        return semi_open_files
    
    def _evaluate_pawn_shield(self, board: chess.Board, king_file: int, king_rank: int,
                              color: chess.Color) -> float:
        """Evaluate pawn shield around king.
        
        Args:
            board: Current position.
            king_file: King's file (0-7).
            king_rank: King's rank (0-7).
            color: King's color.
        
        Returns:
            Score for pawn shield (positive = good, negative = bad).
        """
        friendly_pawns = board.pieces(chess.PAWN, color)
        score = 0.0
        
        # Check files near king
        files_to_check = [king_file]
        if king_file > 0:
            files_to_check.append(king_file - 1)
        if king_file < 7:
            files_to_check.append(king_file + 1)
        
        # Count pawns in front of king (pawn shield)
        # For white, "in front" means higher ranks (1, 2, ...)
        # For black, "in front" means lower ranks (6, 5, ...)
        if color == chess.WHITE:
            # White king: check ranks in front (higher ranks)
            ranks_to_check = range(king_rank + 1, 8) if king_rank < 7 else []
        else:
            # Black king: check ranks in front (lower ranks)
            ranks_to_check = range(king_rank - 1, -1, -1) if king_rank > 0 else []
        
        pawn_count = 0
        for file in files_to_check:
            for rank in ranks_to_check[:2]:  # Check first 2 ranks in front
                check_square = chess.square(file, rank)
                if check_square in friendly_pawns:
                    pawn_count += 1
        
        # Bonus for pawn shield
        score = pawn_count * self.pawn_shield_bonus
        
        return score
    
    def _is_king_exposed(self, board: chess.Board, king_file: int, king_rank: int,
                         color: chess.Color) -> bool:
        """Check if king is exposed (no pawns in front).
        
        Args:
            board: Current position.
            king_file: King's file (0-7).
            king_rank: King's rank (0-7).
            color: King's color.
        
        Returns:
            True if king is exposed, False otherwise.
        """
        friendly_pawns = board.pieces(chess.PAWN, color)
        
        # Check files near king
        files_to_check = [king_file]
        if king_file > 0:
            files_to_check.append(king_file - 1)
        if king_file < 7:
            files_to_check.append(king_file + 1)
        
        # Check if there are any pawns in front of king
        # For white, "in front" means higher ranks (1, 2, ...)
        # For black, "in front" means lower ranks (6, 5, ...)
        if color == chess.WHITE:
            # White king: check ranks in front (higher ranks)
            ranks_to_check = range(king_rank + 1, 8) if king_rank < 7 else []
        else:
            # Black king: check ranks in front (lower ranks)
            ranks_to_check = range(king_rank - 1, -1, -1) if king_rank > 0 else []
        
        # Check if pawns are in front of king
        for file in files_to_check:
            for rank in ranks_to_check:
                check_square = chess.square(file, rank)
                if check_square in friendly_pawns:
                    return False  # Has pawn shield
        
        return True  # No pawns in front = exposed

