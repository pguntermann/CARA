"""Rule for evaluating outpost squares."""

from typing import Dict
import chess

from app.services.positional_heatmap.base_rule import PositionalRule


class OutpostSquareRule(PositionalRule):
    """Rule that evaluates outpost squares.
    
    An outpost square is a square that:
    - Must be protected by friendly pawns (REQUIRED)
    - Cannot be attacked by enemy pawns (current or potential)
    - Is on an advanced rank (opponent's side of the board)
    - Is in a strategically important area (usually central, not on edge files)
    - Is occupied by a piece (especially knights)
    
    Outpost squares are strong positions for pieces, especially knights.
    The pawn protection provides a stable base, while immunity from enemy pawn
    attacks makes the position difficult to challenge.
    """

    def __init__(self, config: Dict) -> None:
        """Initialize the outpost square rule.
        
        Args:
            config: Rule configuration dictionary.
        """
        super().__init__(config)
        self.knight_bonus = config.get('knight_bonus', 12.0)
        self.bishop_bonus = config.get('bishop_bonus', 8.0)
        self.central_bonus = config.get('central_bonus', 3.0)
        self.protected_bonus = config.get('protected_bonus', 2.0)

    def evaluate(self, board: chess.Board, perspective: chess.Color) -> Dict[chess.Square, float]:
        """Evaluate outpost squares in the position.
        
        Args:
            board: Current chess position.
            perspective: Color to evaluate from.
        
        Returns:
            Dictionary mapping square -> score.
            Positive scores for pieces on outpost squares.
        """
        scores: Dict[chess.Square, float] = {}
        opponent = not perspective
        
        # Central squares (d4, d5, e4, e5, c5, c4, f4, f5)
        central_squares = [
            chess.D4, chess.D5, chess.E4, chess.E5,
            chess.C4, chess.C5, chess.F4, chess.F5
        ]
        
        # Evaluate pieces that could be on outposts (knights and bishops primarily)
        for piece_type in [chess.KNIGHT, chess.BISHOP]:
            pieces = board.pieces(piece_type, perspective)
            
            for piece_square in pieces:
                file = chess.square_file(piece_square)
                rank = chess.square_rank(piece_square)
                
                # Check if square is an outpost
                is_outpost = self._is_outpost_square(board, file, rank, perspective)
                
                if is_outpost:
                    outpost_score = 0.0
                    
                    # Base bonus depends on piece type
                    if piece_type == chess.KNIGHT:
                        outpost_score = self.knight_bonus
                    elif piece_type == chess.BISHOP:
                        outpost_score = self.bishop_bonus
                    
                    # Additional bonus for central outposts
                    if piece_square in central_squares:
                        outpost_score += self.central_bonus
                    
                    # Note: Pawn protection is now a requirement (checked in _is_outpost_square)
                    # The protected_bonus is kept for potential future use (e.g., multiple pawn protection)
                    # but is not currently used since protection is mandatory
                    
                    scores[piece_square] = outpost_score
        
        return scores
    
    def _is_outpost_square(self, board: chess.Board, file: int, rank: int,
                           color: chess.Color) -> bool:
        """Check if a square is an outpost square.
        
        An outpost square:
        - Must be protected by friendly pawns (REQUIRED)
        - Cannot be attacked by enemy pawns (current or potential)
        - Is on an advanced rank (4th-7th ranks for white, 1st-4th ranks for black)
        - Is in a strategically important area (not on edge files a/h)
        
        Args:
            board: Current position.
            file: Square's file (0-7).
            rank: Square's rank (0-7).
            color: Color to evaluate for.
        
        Returns:
            True if square is an outpost square.
        """
        opponent = not color
        
        # Outposts are typically not on edge files (a/h)
        # Edge files are less valuable for outposts
        if file == 0 or file == 7:
            return False
        
        # Outposts must be on advanced ranks
        # For white: ranks 4-7 (0-indexed: ranks 3-6) - the 5th, 6th, 7th, 8th ranks
        # For black: ranks 0-3 (0-indexed: ranks 0-3) - the 1st, 2nd, 3rd, 4th ranks
        if color == chess.WHITE:
            # White outposts must be on ranks 3-6 (0-indexed), which are ranks 4-7 in chess notation
            if rank < 3:
                return False
        else:
            # Black outposts must be on ranks 0-3 (0-indexed), which are ranks 1-4 in chess notation
            if rank > 3:
                return False
        
        # REQUIRED: Outpost must be protected by friendly pawns
        # This is a defining characteristic of an outpost square
        if not self._is_protected_by_pawns(board, file, rank, color):
            return False
        
        # Check if square can be attacked by enemy pawns (current position)
        # If it can be attacked by enemy pawns, it's not an outpost
        if self._can_be_attacked_by_pawns(board, file, rank, opponent):
            return False
        
        # Check if square can be attacked by enemy pawns advancing
        # This is critical - if an enemy pawn can advance to attack the square, it's not an outpost
        if self._can_be_attacked_by_advancing_pawns(board, file, rank, opponent):
            return False
        
        # Square is an outpost if it:
        # - Is protected by friendly pawns (REQUIRED)
        # - Cannot be attacked by enemy pawns (current or potential)
        # - Is on an advanced rank
        # - Is not on an edge file
        return True
    
    def _can_be_attacked_by_pawns(self, board: chess.Board, file: int, rank: int,
                                 color: chess.Color) -> bool:
        """Check if a square can be attacked by pawns of the given color.
        
        Args:
            board: Current position.
            file: Square's file (0-7).
            rank: Square's rank (0-7).
            color: Color of pawns to check.
        
        Returns:
            True if square can be attacked by pawns of the given color.
        """
        enemy_pawns = board.pieces(chess.PAWN, color)
        
        # Check if any pawn of the given color can attack this square
        # Pawns attack diagonally forward
        if color == chess.WHITE:
            # White pawns attack diagonally forward (up)
            if rank > 0:
                # Check left diagonal
                if file > 0:
                    left_diag_square = chess.square(file - 1, rank - 1)
                    if left_diag_square in enemy_pawns:
                        return True
                # Check right diagonal
                if file < 7:
                    right_diag_square = chess.square(file + 1, rank - 1)
                    if right_diag_square in enemy_pawns:
                        return True
        else:
            # Black pawns attack diagonally forward (down)
            if rank < 7:
                # Check left diagonal
                if file > 0:
                    left_diag_square = chess.square(file - 1, rank + 1)
                    if left_diag_square in enemy_pawns:
                        return True
                # Check right diagonal
                if file < 7:
                    right_diag_square = chess.square(file + 1, rank + 1)
                    if right_diag_square in enemy_pawns:
                        return True
        
        return False
    
    def _can_be_attacked_by_advancing_pawns(self, board: chess.Board, file: int, rank: int,
                                            color: chess.Color) -> bool:
        """Check if a square can be attacked by enemy pawns that can advance.
        
        This checks if enemy pawns on the same file or adjacent files can advance
        to attack the square. This is important for outpost detection - if a pawn
        can advance to attack the square, it's not a true outpost.
        
        For example, if a white piece is on d3 and there's a black pawn on d5,
        the pawn can advance to d4 and attack d3 diagonally.
        
        Args:
            board: Current position.
            file: Square's file (0-7).
            rank: Square's rank (0-7).
            color: Color of pawns to check.
        
        Returns:
            True if square can be attacked by advancing pawns.
        """
        enemy_pawns = board.pieces(chess.PAWN, color)
        
        if color == chess.WHITE:
            # White pawns attack diagonally forward (up)
            # For a square at (file, rank), white pawns can attack it if:
            # - A pawn on (file, rank+1) can advance to (file, rank) and attack diagonally
            # - A pawn on (file-1, rank+1) can advance to attack diagonally
            # - A pawn on (file+1, rank+1) can advance to attack diagonally
            
            # Check same file - if there's a white pawn on the same file on a higher rank,
            # it can advance to attack this square diagonally
            if rank < 7:
                for pawn_rank in range(rank + 1, 8):
                    pawn_square = chess.square(file, pawn_rank)
                    if pawn_square in enemy_pawns:
                        # There's a pawn on this file that can advance to attack
                        return True
                
                # Check left diagonal - pawn on adjacent file (file-1) can advance to attack
                if file > 0:
                    for pawn_rank in range(rank + 1, 8):
                        pawn_square = chess.square(file - 1, pawn_rank)
                        if pawn_square in enemy_pawns:
                            return True
                
                # Check right diagonal - pawn on adjacent file (file+1) can advance to attack
                if file < 7:
                    for pawn_rank in range(rank + 1, 8):
                        pawn_square = chess.square(file + 1, pawn_rank)
                        if pawn_square in enemy_pawns:
                            return True
        else:
            # Black pawns attack diagonally forward (down)
            # For a square at (file, rank), black pawns can attack it if:
            # - A pawn on (file, rank-1) can advance to (file, rank) and attack diagonally
            # - A pawn on (file-1, rank-1) can advance to attack diagonally
            # - A pawn on (file+1, rank-1) can advance to attack diagonally
            
            # Check same file - if there's a black pawn on the same file on a lower rank,
            # it can advance to attack this square diagonally
            if rank > 0:
                for pawn_rank in range(rank - 1, -1, -1):
                    pawn_square = chess.square(file, pawn_rank)
                    if pawn_square in enemy_pawns:
                        # There's a pawn on this file that can advance to attack
                        return True
                
                # Check left diagonal - pawn on adjacent file (file-1) can advance to attack
                if file > 0:
                    for pawn_rank in range(rank - 1, -1, -1):
                        pawn_square = chess.square(file - 1, pawn_rank)
                        if pawn_square in enemy_pawns:
                            return True
                
                # Check right diagonal - pawn on adjacent file (file+1) can advance to attack
                if file < 7:
                    for pawn_rank in range(rank - 1, -1, -1):
                        pawn_square = chess.square(file + 1, pawn_rank)
                        if pawn_square in enemy_pawns:
                            return True
        
        return False
    
    def _is_protected_by_pawns(self, board: chess.Board, file: int, rank: int,
                               color: chess.Color) -> bool:
        """Check if a square is protected by friendly pawns.
        
        Args:
            board: Current position.
            file: Square's file (0-7).
            rank: Square's rank (0-7).
            color: Color to check protection for.
        
        Returns:
            True if square is protected by friendly pawns.
        """
        friendly_pawns = board.pieces(chess.PAWN, color)
        
        # Check if any friendly pawn can attack this square
        # Pawns attack diagonally forward
        if color == chess.WHITE:
            # White pawns attack diagonally forward (up)
            if rank > 0:
                # Check left diagonal
                if file > 0:
                    left_diag_square = chess.square(file - 1, rank - 1)
                    if left_diag_square in friendly_pawns:
                        return True
                # Check right diagonal
                if file < 7:
                    right_diag_square = chess.square(file + 1, rank - 1)
                    if right_diag_square in friendly_pawns:
                        return True
        else:
            # Black pawns attack diagonally forward (down)
            if rank < 7:
                # Check left diagonal
                if file > 0:
                    left_diag_square = chess.square(file - 1, rank + 1)
                    if left_diag_square in friendly_pawns:
                        return True
                # Check right diagonal
                if file < 7:
                    right_diag_square = chess.square(file + 1, rank + 1)
                    if right_diag_square in friendly_pawns:
                        return True
        
        return False

