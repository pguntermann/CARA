"""Service for parsing PV strings and extracting positional plans (piece trajectories)."""

import chess
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass


@dataclass
class PieceTrajectory:
    """Represents a piece's trajectory through a PV sequence."""
    
    piece_type: str  # 'p', 'r', 'n', 'b', 'q', 'k'
    piece_color: bool  # True for white, False for black
    squares: List[int]  # List of square indices (chess.Square) the piece visits
    ply_indices: List[int]  # Ply indices (0-based) in the PV sequence when piece moves to each square
    starting_square: Optional[int] = None  # Starting square of the piece (for marker display)


class PvPlanParserService:
    """Service for extracting positional plans from PV strings."""
    
    def __init__(self, min_moves_for_plan: int = 2) -> None:
        """Initialize the PV plan parser service.
        
        Args:
            min_moves_for_plan: Minimum number of times a piece must move to qualify as a plan.
        """
        self.min_moves_for_plan = min_moves_for_plan
    
    def extract_plan(self, pv_string: str, current_fen: str, max_pieces: int = 1) -> List[PieceTrajectory]:
        """Extract trajectories for the most-moved pieces from a PV string.
        
        Only tracks pieces for the side that is currently on the move (even moves if white to move,
        odd moves if black to move).
        
        Args:
            pv_string: Space-separated moves in algebraic notation (e.g., "Nf3 d5 Nc3").
            current_fen: FEN string of the current position.
            max_pieces: Maximum number of piece trajectories to return (1-3). Default is 1.
            
        Returns:
            List of PieceTrajectory objects (up to max_pieces). Empty list if no plans found.
        """
        if not pv_string or not pv_string.strip():
            return []
        
        # Parse moves from PV string
        moves = self._parse_pv_moves(pv_string, current_fen)
        if not moves:
            return []
        
        # Get which side is to move in the current position
        board = chess.Board(current_fen)
        is_white_to_move = board.turn == chess.WHITE
        
        # Track piece movements through the sequence (only for side to move)
        piece_movements = self._track_piece_movements(moves, current_fen, is_white_to_move)
        
        # Find the most-moved pieces (up to max_pieces)
        most_moved_list = self._find_most_moved_pieces(piece_movements, max_pieces)
        
        trajectories = []
        # Track unique pieces to avoid duplicates
        # Use (piece_type, piece_color, starting_square) to distinguish different pieces of same type
        # If same piece is tracked with different starting squares, keep the one with most moves
        seen_pieces: Dict[Tuple[str, bool, Optional[int]], Dict] = {}
        
        for most_moved in most_moved_list:
            if most_moved and len(most_moved['squares']) >= self.min_moves_for_plan:
                # Get the starting square (index 0 with move_number -1)
                starting_square = most_moved['squares'][0] if most_moved['squares'] else None
                piece_type = most_moved['piece_type']
                piece_color = most_moved['piece_color']
                piece_identity = (piece_type, piece_color, starting_square)
                
                # Count actual moves (excluding starting position)
                move_count = len([m for m in most_moved['ply_indices'] if m >= 0])
                
                # If we haven't seen this exact piece (type, color, starting square), use it
                if piece_identity not in seen_pieces:
                    seen_pieces[piece_identity] = most_moved
                else:
                    # Same piece tracked multiple times - keep the one with more moves
                    existing_move_count = len([m for m in seen_pieces[piece_identity]['ply_indices'] if m >= 0])
                    if move_count > existing_move_count:
                        seen_pieces[piece_identity] = most_moved
        
        # Now create trajectories from the deduplicated pieces
        for most_moved in seen_pieces.values():
            # Get the starting square (index 0 with ply_index -1)
            starting_square = most_moved['squares'][0] if most_moved['squares'] else None
            
            # Exclude the starting square (index 0) from the trajectory squares
            # Only show squares the piece actually moves TO
            # The starting square is at index 0 with ply_index -1
            trajectory_squares = []
            trajectory_ply_indices = []
            
            for i, square in enumerate(most_moved['squares']):
                ply_idx = most_moved['ply_indices'][i] if i < len(most_moved['ply_indices']) else -1
                # Only include squares where the piece actually moves (ply_idx >= 0)
                # Skip the starting position (ply_idx == -1)
                if ply_idx >= 0:
                    trajectory_squares.append(square)
                    trajectory_ply_indices.append(ply_idx)
            
            # Need at least min_moves_for_plan actual moves (not including starting position)
            if len(trajectory_squares) >= self.min_moves_for_plan:
                trajectories.append(PieceTrajectory(
                    piece_type=most_moved['piece_type'],
                    piece_color=most_moved['piece_color'],
                    squares=trajectory_squares,
                    ply_indices=trajectory_ply_indices,
                    starting_square=starting_square
                ))
        
        return trajectories
    
    def _parse_pv_moves(self, pv_string: str, current_fen: str) -> List[chess.Move]:
        """Parse PV string into chess.Move objects.
        
        Args:
            pv_string: Space-separated moves in algebraic notation.
            current_fen: FEN string of the current position.
            
        Returns:
            List of chess.Move objects. If any move fails to parse or is invalid,
            parsing stops and returns moves parsed up to that point.
        """
        moves = []
        board = chess.Board(current_fen)
        
        move_strings = pv_string.strip().split()
        for move_str in move_strings:
            try:
                # Try to parse as algebraic notation
                move = board.parse_san(move_str)
                
                # Validate that the move is legal
                if move not in board.legal_moves:
                    # Invalid move - stop parsing to prevent board state desync
                    break
                
                moves.append(move)
                board.push(move)
            except (ValueError, chess.InvalidMoveError):
                # If parsing fails, stop parsing to prevent board state desync
                break
        
        return moves
    
    def _track_piece_movements(self, moves: List[chess.Move], start_fen: str, is_white_to_move: bool) -> Dict[str, Dict]:
        """Track which pieces move and where they go.
        
        Only tracks moves for the side that is currently on the move.
        Uses explicit board state replay to identify pieces accurately.
        
        Args:
            moves: List of chess.Move objects.
            start_fen: Starting FEN position.
            is_white_to_move: True if white is to move, False if black is to move.
            
        Returns:
            Dictionary mapping piece identifiers to movement data.
            Key format: "{color}_{piece_type}_{initial_square}"
            Value: {
                'piece_type': str,
                'piece_color': bool,
                'squares': List[int],
                'ply_indices': List[int]
            }
        """
        piece_movements: Dict[str, Dict] = {}
        
        # Track which pieces we've seen and their current squares
        # Key: piece identifier "{color}_{piece_type}_{initial_square}"
        # Value: current square where the piece is located
        piece_current_square: Dict[str, int] = {}
        
        # Track promoted pieces: map (to_square after promotion) -> (promotion_square, promoted_piece_type, promotion_ply)
        # This helps us identify promoted pieces when they move later
        promoted_pieces: Dict[int, Tuple[int, str, int]] = {}  # to_square -> (promotion_square, piece_type, ply_index)
        
        # Get initial board state to find starting squares
        initial_board = chess.Board(start_fen)
        
        # Replay moves and track piece movements explicitly
        for move_num, move in enumerate(moves):
            # Determine if this move is for the side we're tracking
            # Move 0 is always for the side that is to move in the starting position
            # Move 1 is for the opposite side, move 2 is back to the starting side, etc.
            is_tracked_side_move = (move_num % 2 == 0)
            
            # Replay board state up to (but not including) this move
            board_before = chess.Board(start_fen)
            for prev_move in moves[:move_num]:
                board_before.push(prev_move)
            
            # Get the piece that is about to move (from the actual board state)
            from_square = move.from_square
            to_square = move.to_square
            piece = board_before.piece_at(from_square)
            
            # Check if this is a promotion move
            if move.promotion is not None and is_tracked_side_move:
                # This is a promotion move - track it immediately
                promoted_piece_type = chess.piece_symbol(move.promotion).lower()
                promoted_piece_color = is_white_to_move
                
                # The promotion square (to_square) is where the promoted piece "starts"
                promotion_square = to_square
                
                # Create piece key for the promoted piece
                piece_key = f"{'w' if promoted_piece_color else 'b'}_{promoted_piece_type}_{promotion_square}"
                
                # Track the promotion as the first move of the promoted piece
                if piece_key not in piece_movements:
                    piece_movements[piece_key] = {
                        'piece_type': promoted_piece_type,
                        'piece_color': promoted_piece_color,
                        'squares': [promotion_square],  # Starting square is the promotion square
                        'ply_indices': [move_num]  # Promotion move itself is the first move
                    }
                    piece_current_square[piece_key] = promotion_square
                    # Record this as a promoted piece for later reference
                    promoted_pieces[promotion_square] = (promotion_square, promoted_piece_type, move_num)
                else:
                    # Key already exists (shouldn't happen for promotions, but handle it)
                    piece_movements[piece_key]['squares'].append(promotion_square)
                    piece_movements[piece_key]['ply_indices'].append(move_num)
                    piece_current_square[piece_key] = promotion_square
                
                # Continue to next move (promotion is already tracked)
                continue
            
            if not is_tracked_side_move:
                # Skip moves for the opposite side
                continue
            
            if not piece or piece.color != is_white_to_move:
                # Not a piece we're tracking - skip
                continue
            
            # Validate that this is a legal move for this piece type
            try:
                test_board = board_before.copy()
                if move not in test_board.legal_moves:
                    # Invalid move - skip
                    continue
            except:
                # Error checking move - skip
                continue
            
            piece_type = piece.symbol().lower()
            piece_color = piece.color
            
            # Find if we're already tracking this piece
            # First check: look for a tracked piece currently on the from_square
            tracked_piece_key = None
            for piece_key, current_square in piece_current_square.items():
                if current_square == from_square:
                    # Verify it's the same piece type and color
                    tracked_data = piece_movements[piece_key]
                    if (tracked_data['piece_type'] == piece_type and 
                        tracked_data['piece_color'] == piece_color):
                        tracked_piece_key = piece_key
                        break
            
            # Second check: if not found, check if from_square appears in any tracked trajectory
            # This handles cases where piece_current_square might be out of sync
            if not tracked_piece_key:
                for piece_key, tracked_data in piece_movements.items():
                    if (tracked_data['piece_type'] == piece_type and 
                        tracked_data['piece_color'] == piece_color):
                        # Check if from_square is in this piece's trajectory
                        if from_square in tracked_data['squares']:
                            # This piece has been to from_square - check if it's the most recent square
                            squares = tracked_data['squares']
                            # Find the index of from_square
                            from_index = squares.index(from_square)
                            # Check if this is the last square in the trajectory (most recent position)
                            if from_index == len(squares) - 1:
                                tracked_piece_key = piece_key
                                break
            
            # Third check: for unique pieces (king/queen), if we have any tracked piece of same type/color,
            # it must be the same piece
            if not tracked_piece_key and piece_type in {'k', 'q'}:
                for piece_key, tracked_data in piece_movements.items():
                    if (tracked_data['piece_type'] == piece_type and 
                        tracked_data['piece_color'] == piece_color):
                        tracked_piece_key = piece_key
                        break
            
            if tracked_piece_key:
                # We're already tracking this piece
                # Always add the move to track the complete trajectory sequence
                # (including revisits to previously visited squares)
                piece_movements[tracked_piece_key]['squares'].append(to_square)
                piece_movements[tracked_piece_key]['ply_indices'].append(move_num)
                # Update current square
                piece_current_square[tracked_piece_key] = to_square
            else:
                # New piece to track - find its actual starting square
                # First check if this is a promoted piece that we already tracked
                initial_square = None
                is_promoted_piece = False
                
                # Check if from_square matches a promoted piece we've seen
                if from_square in promoted_pieces:
                    promotion_square, promoted_type, promotion_ply = promoted_pieces[from_square]
                    if promoted_type == piece_type:
                        # This is the promoted piece - use the promotion square as starting square
                        initial_square = promotion_square
                        is_promoted_piece = True
                        # Find the existing piece_key for this promoted piece
                        piece_key = f"{'w' if piece_color else 'b'}_{piece_type}_{promotion_square}"
                        if piece_key in piece_movements:
                            # We're already tracking this promoted piece - add this move
                            piece_movements[piece_key]['squares'].append(to_square)
                            piece_movements[piece_key]['ply_indices'].append(move_num)
                            piece_current_square[piece_key] = to_square
                            continue  # Move already tracked, continue to next move
                
                if not is_promoted_piece:
                    # Replay moves to current position
                    replay_board = chess.Board(start_fen)
                    for replay_move in moves[:move_num]:
                        replay_board.push(replay_move)
                    
                    # Get the piece that's currently on from_square (after replaying moves)
                    current_piece = replay_board.piece_at(from_square)
                    
                    if current_piece and current_piece.symbol().lower() == piece_type and current_piece.color == piece_color:
                        # Find which square this piece started on in the initial position
                        # For unique pieces (king/queen), there's only one - find it directly
                        if piece_type in {'k', 'q'}:
                            for square in chess.SQUARES:
                                init_piece = initial_board.piece_at(square)
                                if (init_piece and 
                                    init_piece.symbol().lower() == piece_type and 
                                    init_piece.color == piece_color):
                                    initial_square = square
                                    break
                        else:
                            # For non-unique pieces, trace which one reached from_square
                            # Track each piece's position through the moves
                            piece_positions: Dict[int, int] = {}  # init_square -> current_square
                            
                            # Initialize: map each piece of this type/color to its starting square
                            for init_square in chess.SQUARES:
                                init_piece = initial_board.piece_at(init_square)
                                if (init_piece and 
                                    init_piece.symbol().lower() == piece_type and 
                                    init_piece.color == piece_color):
                                    piece_positions[init_square] = init_square
                            
                            # Replay moves to track where each piece ends up
                            test_board = chess.Board(start_fen)
                            for test_move in moves[:move_num]:
                                test_from = test_move.from_square
                                test_to = test_move.to_square
                                
                                # Update piece positions if this move affects any tracked piece
                                for init_sq, current_sq in list(piece_positions.items()):
                                    if current_sq == test_from:
                                        # This piece moved
                                        piece_positions[init_sq] = test_to
                                
                                test_board.push(test_move)
                            
                            # Find which initial piece is now on from_square
                            for init_sq, current_sq in piece_positions.items():
                                if current_sq == from_square:
                                    initial_square = init_sq
                                    break
                    
                    # If we couldn't find the starting square, use from_square as fallback
                    # (this might happen with parsing errors)
                    if initial_square is None:
                        initial_square = from_square
                
                piece_key = f"{'w' if piece_color else 'b'}_{piece_type}_{initial_square}"
                
                # Check if this key already exists
                if piece_key not in piece_movements:
                    piece_movements[piece_key] = {
                        'piece_type': piece_type,
                        'piece_color': piece_color,
                        'squares': [initial_square, to_square],  # Starting square + first destination
                        'ply_indices': [-1, move_num]  # -1 for starting position, move_num for first move
                    }
                    piece_current_square[piece_key] = to_square
                else:
                    # Key already exists - merge with existing entry
                    # Always add the move to track the complete trajectory sequence
                    piece_movements[piece_key]['squares'].append(to_square)
                    piece_movements[piece_key]['ply_indices'].append(move_num)
                    piece_current_square[piece_key] = to_square
        
        return piece_movements
    
    def _find_most_moved_piece(self, piece_movements: Dict[str, Dict]) -> Optional[Dict]:
        """Find the piece that moves the most times.
        
        Args:
            piece_movements: Dictionary of piece movement data.
            
        Returns:
            Dictionary for the most-moved piece, or None if no piece moves enough.
        """
        results = self._find_most_moved_pieces(piece_movements, 1)
        return results[0] if results else None
    
    def _find_most_moved_pieces(self, piece_movements: Dict[str, Dict], max_pieces: int) -> List[Dict]:
        """Find the pieces that move the most times (up to max_pieces).
        
        Args:
            piece_movements: Dictionary of piece movement data.
            max_pieces: Maximum number of pieces to return (1-3).
            
        Returns:
            List of dictionaries for the most-moved pieces, sorted by move count (descending).
            Empty list if no pieces move enough.
        """
        if not piece_movements:
            return []
        
        # Count moves per piece (excluding starting position)
        move_counts = []
        # Track unique pieces to avoid duplicates
        # For unique pieces (king, queen), use (piece_type, piece_color) as key
        # For non-unique pieces, use (piece_type, piece_color, starting_square)
        unique_pieces = {'k', 'q'}  # King and Queen are unique (only one per side)
        seen_pieces: Dict[Tuple[str, bool, Optional[int]], Dict] = {}
        
        for key, data in piece_movements.items():
            # Number of moves = number of squares - 1 (excluding start)
            move_count = len([m for m in data['ply_indices'] if m >= 0])
            if move_count >= self.min_moves_for_plan:
                piece_type = data['piece_type']
                piece_color = data['piece_color']
                starting_square = data['squares'][0] if data['squares'] else None
                
                # For unique pieces, use (type, color) as key; for others, include starting square
                if piece_type in unique_pieces:
                    piece_identity = (piece_type, piece_color, None)  # None indicates unique piece
                else:
                    piece_identity = (piece_type, piece_color, starting_square)
                
                # If we haven't seen this piece, or this one has more moves, use it
                if piece_identity not in seen_pieces:
                    seen_pieces[piece_identity] = (move_count, data)
                else:
                    # Same piece tracked multiple times - keep the one with more moves
                    existing_move_count, _ = seen_pieces[piece_identity]
                    if move_count > existing_move_count:
                        seen_pieces[piece_identity] = (move_count, data)
        
        # Extract the data from seen_pieces and sort by move count
        move_counts = list(seen_pieces.values())
        
        if not move_counts:
            return []
        
        # Sort by move count (descending) and take top max_pieces
        move_counts.sort(key=lambda x: x[0], reverse=True)
        return [data for _, data in move_counts[:max_pieces]]

