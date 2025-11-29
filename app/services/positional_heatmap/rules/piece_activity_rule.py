"""Rule for evaluating piece activity."""

from typing import Dict
import chess

from app.services.positional_heatmap.base_rule import PositionalRule


class PieceActivityRule(PositionalRule):
    """Rule that evaluates piece activity.
    
    Evaluates how active pieces are based on:
    - Number of legal moves
    - Control of central squares
    - Piece mobility
    """
    
    def __init__(self, config: Dict) -> None:
        """Initialize the piece activity rule.
        
        Args:
            config: Rule configuration dictionary.
        """
        super().__init__(config)
        self.activity_bonus_per_move = config.get('activity_bonus_per_move', 1.0)
        self.central_square_bonus = config.get('central_square_bonus', 3.0)
        self.doubled_rooks_bonus = config.get('doubled_rooks_bonus', 20.0)
    
    def evaluate(self, board: chess.Board, perspective: chess.Color) -> Dict[chess.Square, float]:
        """Evaluate piece activity in the position.
        
        Args:
            board: Current chess position.
            perspective: Color to evaluate from.
        
        Returns:
            Dictionary mapping square -> score.
            Positive scores for active pieces.
        """
        scores: Dict[chess.Square, float] = {}
        
        # Central squares (d4, d5, e4, e5)
        central_squares = [chess.E4, chess.E5, chess.D4, chess.D5]
        
        # Evaluate each piece type
        for piece_type in [chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            pieces = board.pieces(piece_type, perspective)
            
            for piece_square in pieces:
                activity_score = 0.0
                
                # Count legal moves (mobility) for this piece's color
                # board.legal_moves only returns moves for the current side to move,
                # so we need to check moves for the perspective color specifically
                if perspective == board.turn:
                    # Current side to move - can use board.legal_moves directly
                    legal_moves = [move for move in board.legal_moves 
                                 if move.from_square == piece_square]
                    num_moves = len(legal_moves)
                else:
                    # Not current side to move - need to generate moves for this piece's color
                    # Create a temporary board copy and set turn to perspective color
                    temp_board = board.copy()
                    temp_board.turn = perspective
                    legal_moves = [move for move in temp_board.generate_legal_moves() 
                                 if move.from_square == piece_square]
                    num_moves = len(legal_moves)
                
                # Get attacks and central attacks (used multiple times)
                attacks = board.attacks(piece_square)
                central_attacks = sum(1 for sq in central_squares if sq in attacks)
                
                # Base score for having moves (positive for active pieces)
                # Scale by piece type with caps: Knight +2.0 cap +12, Bishop +2.5 cap +15, Rook +3.0 cap +18, Queen +4.0 cap +24
                if num_moves > 0:
                    # Get piece-specific bonus per move and cap
                    if piece_type == chess.KNIGHT:
                        bonus_per_move = 2.0
                        max_bonus = 12.0
                    elif piece_type == chess.BISHOP:
                        bonus_per_move = 2.5
                        max_bonus = 15.0
                    elif piece_type == chess.ROOK:
                        bonus_per_move = 3.0
                        max_bonus = 18.0
                    elif piece_type == chess.QUEEN:
                        bonus_per_move = 4.0
                        max_bonus = 24.0
                    else:
                        # Fallback (shouldn't happen for these piece types)
                        bonus_per_move = self.activity_bonus_per_move
                        max_bonus = float('inf')
                    
                    # Calculate mobility bonus with cap
                    mobility_bonus = min(num_moves * bonus_per_move, max_bonus)
                    activity_score += mobility_bonus
                    
                    # Bonus for controlling central squares (active pieces)
                    activity_score += central_attacks * self.central_square_bonus
                    
                    # Bonus for doubled rooks on open files
                    if piece_type == chess.ROOK:
                        piece_file = chess.square_file(piece_square)
                        # Check if this rook is on an open file with another rook
                        if self._is_doubled_rooks_on_open_file(board, piece_file, perspective):
                            activity_score += self.doubled_rooks_bonus
                else:
                    # Penalty for blocked pieces (no legal moves)
                    # But only for pieces that should be able to move (rooks, bishops, queens)
                    # Reduce penalty for pieces that are still useful (e.g., controlling squares)
                    if piece_type in [chess.ROOK, chess.BISHOP, chess.QUEEN]:
                        # For rooks, check if they're in reasonable positions (e.g., on starting squares)
                        # ChessBase shows rooks on starting squares as green even if they can't move
                        # Check this FIRST, before central attacks check
                        if piece_type == chess.ROOK:
                            # Rooks on back rank (rank 0 for white, rank 7 for black) 
                            # or 7th/2nd rank (rank 6 for black, rank 1 for white) are in reasonable positions
                            piece_rank = chess.square_rank(piece_square)
                            if (perspective == chess.WHITE and piece_rank in [0, 1]) or \
                               (perspective == chess.BLACK and piece_rank in [6, 7]):
                                # Rook on back rank or 7th/2nd rank is in reasonable position, give small positive score
                                activity_score = 2.0  # Small positive score for rooks in reasonable positions
                            elif central_attacks > 0:
                                # Piece still controls center, less penalty
                                activity_score = -5.0  # Reduced penalty
                            else:
                                # Piece is truly blocked and not useful
                                activity_score = -10.0
                        elif piece_type == chess.BISHOP:
                            # Bishops on common development squares are fine even if temporarily blocked
                            if self._is_development_square_for_bishop(piece_square, perspective):
                                # Bishop on a development square, even if blocked, gets a small positive score
                                activity_score = 2.0  # Similar to back-rank rooks
                            elif central_attacks > 0:
                                # Piece still controls center, less penalty
                                activity_score = -5.0  # Reduced penalty
                            else:
                                # Piece is truly blocked and not useful
                                activity_score = -10.0
                        elif piece_type == chess.QUEEN:
                            # Queens on starting square (d1 for white, d8 for black) or in center ranks are in reasonable positions
                            piece_rank = chess.square_rank(piece_square)
                            piece_file = chess.square_file(piece_square)
                            # Check if queen is on starting square
                            is_on_starting_square = (perspective == chess.WHITE and piece_rank == 0 and piece_file == 3) or \
                                                     (perspective == chess.BLACK and piece_rank == 7 and piece_file == 3)
                            # Check if queen is in center ranks (ranks 2-5 for white, ranks 2-5 for black)
                            is_in_center_ranks = (perspective == chess.WHITE and 2 <= piece_rank <= 5) or \
                                                  (perspective == chess.BLACK and 2 <= piece_rank <= 5)
                            if is_on_starting_square or is_in_center_ranks:
                                # Queen on starting square or in center ranks is in reasonable position, give small positive score
                                activity_score = 2.0  # Small positive score for queens in reasonable positions
                            elif central_attacks > 0:
                                # Piece still controls center - this is good even if immobile
                                activity_score = 2.0  # Small positive bonus for center control
                            else:
                                # Piece is truly blocked and not useful
                                activity_score = -10.0
                        elif central_attacks > 0:
                            # Piece still controls center - this is good even if immobile
                            activity_score = 2.0  # Small positive bonus for center control
                        else:
                            # Piece is truly blocked and not useful
                            activity_score = -10.0
                    # Knights in starting position can't move, but that's normal
                    # Check if knight is on edge square (liability) or central square (still useful)
                    elif piece_type == chess.KNIGHT:
                        # Get knight's file and rank
                        piece_file = chess.square_file(piece_square)
                        piece_rank = chess.square_rank(piece_square)
                        # Check if knight is on edge square (files a/h or ranks 0/7)
                        is_on_edge = (piece_file == 0 or piece_file == 7) or (piece_rank == 0 or piece_rank == 7)
                        if is_on_edge:
                            # Knight on edge square is a liability
                            activity_score = -5.0  # Penalty for edge knights
                        elif central_attacks > 0:
                            # Knight on central square still controls center
                            activity_score = 2.0  # Small positive bonus for center control
                        else:
                            # Knight in reasonable position but not on edge
                            activity_score = 0.0  # Neutral
                
                # Only add score if it's non-zero
                if activity_score != 0.0:
                    scores[piece_square] = activity_score
        
        return scores
    
    def _is_development_square_for_bishop(self, square: chess.Square, color: chess.Color) -> bool:
        """Check if a square is a common development square for a bishop.
        
        Common development squares are squares where bishops are typically placed
        during development, even if temporarily blocked.
        
        Args:
            square: Chess square to check.
            color: Bishop's color.
        
        Returns:
            True if square is a common development square for this color's bishop.
        """
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        
        if color == chess.WHITE:
            # Common development squares for white bishops:
            # - Back rank: c1, f1
            # - Second rank: d2, e2, g2
            # - Third rank: c3, f3 (less common but still reasonable)
            if rank == 0:  # Back rank
                return file in [2, 5]  # c1, f1
            elif rank == 1:  # Second rank
                return file in [3, 4, 6]  # d2, e2, g2
            elif rank == 2:  # Third rank
                return file in [2, 5]  # c3, f3
        else:  # BLACK
            # Common development squares for black bishops:
            # - Back rank: c8, f8
            # - Seventh rank: d7, e7, g7
            # - Sixth rank: c6, f6 (less common but still reasonable)
            if rank == 7:  # Back rank
                return file in [2, 5]  # c8, f8
            elif rank == 6:  # Seventh rank
                return file in [3, 4, 6]  # d7, e7, g7
            elif rank == 5:  # Sixth rank
                return file in [2, 5]  # c6, f6
        
        return False
    
    def _is_doubled_rooks_on_open_file(self, board: chess.Board, file: int, color: chess.Color) -> bool:
        """Check if there are doubled rooks on an open file.
        
        Doubled rooks on an open file is a significant tactical advantage.
        An open file has no pawns of either color.
        
        Args:
            board: Current position.
            file: File to check (0-7).
            color: Color of the rooks.
            
        Returns:
            True if there are doubled rooks on an open file, False otherwise.
        """
        # Get all rooks for this color
        rooks = board.pieces(chess.ROOK, color)
        
        # Count rooks on this file
        rooks_on_file = [sq for sq in rooks if chess.square_file(sq) == file]
        
        if len(rooks_on_file) < 2:
            return False  # Need at least 2 rooks
        
        # Check if the file is open (no pawns of either color)
        white_pawns = board.pieces(chess.PAWN, chess.WHITE)
        black_pawns = board.pieces(chess.PAWN, chess.BLACK)
        
        has_white_pawns = any(chess.square_file(sq) == file for sq in white_pawns)
        has_black_pawns = any(chess.square_file(sq) == file for sq in black_pawns)
        
        # File is open if no pawns of either color
        is_open_file = not has_white_pawns and not has_black_pawns
        
        return is_open_file

