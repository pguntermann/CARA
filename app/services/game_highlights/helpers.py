"""Helper functions for game highlight detection."""

from typing import Optional, List, Tuple
import chess
from app.services.game_highlights.constants import PIECE_VALUES


def parse_fen(fen: str) -> Optional[chess.Board]:
    """Parse FEN string into a chess.Board object.
    
    Args:
        fen: FEN string.
        
    Returns:
        chess.Board instance or None if parsing fails.
    """
    if not fen:
        return None
    try:
        board = chess.Board(fen)
        return board
    except (ValueError, AttributeError):
        return None


def is_central_square(square: chess.Square) -> bool:
    """Check if a square is central (d4, d5, e4, e5, c4, c5, f4, f5).
    
    Args:
        square: chess.Square index.
        
    Returns:
        True if square is central, False otherwise.
    """
    from app.services.game_highlights.constants import CENTRAL_SQUARES
    return square in CENTRAL_SQUARES


def get_piece_square(board: chess.Board, piece_type: chess.PieceType, color: chess.Color) -> Optional[chess.Square]:
    """Get the square of a piece (for single-piece types like queen, king).
    
    Args:
        board: chess.Board instance.
        piece_type: Type of piece to find.
        color: Color of piece to find.
        
    Returns:
        Square index or None if not found or multiple pieces exist.
    """
    pieces = list(board.pieces(piece_type, color))
    if len(pieces) == 1:
        return pieces[0]
    return None


def bishops_opposite_colors(board: chess.Board, color: chess.Color) -> bool:
    """Check if a side's bishops are on opposite colors.
    
    Args:
        board: chess.Board instance.
        color: Color to check (chess.WHITE or chess.BLACK).
        
    Returns:
        True if bishops are on opposite colors, False otherwise.
    """
    bishops = list(board.pieces(chess.BISHOP, color))
    if len(bishops) != 2:
        return False
    # Check if bishops are on opposite colors
    square1 = bishops[0]
    square2 = bishops[1]
    file1 = chess.square_file(square1)
    rank1 = chess.square_rank(square1)
    file2 = chess.square_file(square2)
    rank2 = chess.square_rank(square2)
    
    # Check if squares are on opposite colors
    is_light1 = (file1 + rank1) % 2 == 0
    is_light2 = (file2 + rank2) % 2 == 0
    return is_light1 != is_light2


def is_kingside_file(file: int) -> bool:
    """Check if a file is on the kingside (f, g, h files).
    
    Args:
        file: File index (0-7, where 0=a, 7=h).
        
    Returns:
        True if kingside, False otherwise.
    """
    return file >= 5  # f, g, h files (indices 5, 6, 7)


def is_queenside_file(file: int) -> bool:
    """Check if a file is on the queenside (a, b, c files).
    
    Args:
        file: File index (0-7, where 0=a, 7=h).
        
    Returns:
        True if queenside, False otherwise.
    """
    return file <= 2  # a, b, c files (indices 0, 1, 2)


def are_adjacent_files(file1: int, file2: int) -> bool:
    """Check if two files are exactly adjacent.
    
    Args:
        file1: First file index (0-7).
        file2: Second file index (0-7).
        
    Returns:
        True if files are exactly adjacent, False otherwise.
    """
    return abs(file1 - file2) == 1


def parse_evaluation(eval_str: Optional[str]) -> Optional[float]:
    """Parse evaluation string to float.
    
    Args:
        eval_str: Evaluation string (e.g., "+0.5", "-1.2", "M2", "-M3").
        
    Returns:
        Float value in centipawns, or None if parsing fails.
        Mate scores (M2, -M3) return None.
    """
    if not eval_str:
        return None
    
    try:
        # Handle mate scores (M2, -M3, etc.)
        if eval_str.startswith("M") or eval_str.startswith("-M"):
            return None
        
        # Remove + sign if present
        eval_str = eval_str.lstrip("+")
        
        # Convert to float (in pawns) then to centipawns
        return float(eval_str) * 100.0
    except (ValueError, AttributeError):
        return None


# Minimum value for a piece to be considered "valuable" for tactical patterns
MIN_VALUABLE_PIECE_VALUE = 300


def can_profitably_fork_square(board: chess.Board, attacker_square: chess.Square,
                               target_square: chess.Square, color: chess.Color) -> bool:
    """Check if a piece can profitably fork a target square along with another piece.
    
    A fork is profitable if:
    - At least one of the forked pieces is undefended (can win material), OR
    - The fork attacks the king (check) along with at least one valuable piece (forcing)
    
    Args:
        board: Board position.
        attacker_square: Square of the potential forking piece.
        target_square: Square of the target piece (must be included in fork).
        color: Color of the forking side.
        
    Returns:
        True if the piece can profitably fork the target square.
    """
    opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
    attacker_piece = board.piece_at(attacker_square)
    if attacker_piece is None or attacker_piece.color != color:
        return False
    
    # Get all squares this piece can attack
    attacked_squares = board.attacks(attacker_square)
    
    # Count enemy pieces that can be forked (including target)
    enemy_pieces_attacked = []
    target_attacked = False
    attacks_king = False
    
    for sq in attacked_squares:
        enemy_piece = board.piece_at(sq)
        if enemy_piece and enemy_piece.color == opponent_color:
            piece_value = PIECE_VALUES.get(enemy_piece.symbol().lower(), 0)
            is_king = (enemy_piece.piece_type == chess.KING)
            if piece_value >= MIN_VALUABLE_PIECE_VALUE or is_king:
                is_undefended = not board.is_attacked_by(opponent_color, sq)
                enemy_pieces_attacked.append((sq, piece_value, is_king, is_undefended))
                if sq == target_square:
                    target_attacked = True
                if is_king:
                    attacks_king = True
    
    # Fork requires attacking at least 2 valuable pieces (or king + valuable piece), including the target
    if len(enemy_pieces_attacked) < 2 or not target_attacked:
        return False
    
    # For a profitable fork, at least one of the forked pieces must be undefended
    # OR the fork must attack the king (check) along with a valuable piece (forcing)
    undefended_count = sum(1 for _, _, _, is_undef in enemy_pieces_attacked if is_undef)
    
    # Fork is profitable if:
    # 1. At least one forked piece is undefended (can win material), OR
    # 2. Fork attacks the king (check) + at least one valuable piece (forcing)
    if undefended_count > 0 or (attacks_king and len(enemy_pieces_attacked) >= 2):
        return True
    
    # All forked pieces are defended - not a profitable fork
    return False


def can_profitably_skewer_square(board: chess.Board, attacker_square: chess.Square,
                                 target_square: chess.Square, color: chess.Color) -> bool:
    """Check if a piece can profitably skewer a target square.
    
    A skewer is profitable if:
    - The valuable piece in front is undefended (can be captured), OR
    - The king is in check (forced to move, revealing piece behind)
    - The piece behind is undefended (can be captured after front piece moves)
    
    Args:
        board: Board position.
        attacker_square: Square of the potential skewering piece.
        target_square: Square of the target piece (must be the less valuable piece in front).
        color: Color of the skewering side.
        
    Returns:
        True if the piece can profitably skewer the target square.
    """
    opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
    attacker_piece = board.piece_at(attacker_square)
    target_piece = board.piece_at(target_square)
    
    if attacker_piece is None or attacker_piece.color != color:
        return False
    if target_piece is None or target_piece.color != opponent_color:
        return False
    
    # Only sliding pieces (rook, bishop, queen) can create skewers
    if attacker_piece.piece_type not in [chess.ROOK, chess.BISHOP, chess.QUEEN]:
        return False
    
    # Check if target is on the same line as attacker
    attacker_file = chess.square_file(attacker_square)
    attacker_rank = chess.square_rank(attacker_square)
    target_file = chess.square_file(target_square)
    target_rank = chess.square_rank(target_square)
    
    # Check if on same file, rank, or diagonal
    on_same_file = (attacker_file == target_file)
    on_same_rank = (attacker_rank == target_rank)
    on_same_diagonal = (abs(attacker_file - target_file) == abs(attacker_rank - target_rank))
    
    # Check if direction is valid for piece type
    if attacker_piece.piece_type == chess.ROOK and not (on_same_file or on_same_rank):
        return False
    if attacker_piece.piece_type == chess.BISHOP and not on_same_diagonal:
        return False
    
    # Check if there's a more valuable piece behind the target
    df = 1 if target_file > attacker_file else (-1 if target_file < attacker_file else 0)
    dr = 1 if target_rank > attacker_rank else (-1 if target_rank < attacker_rank else 0)
    
    # Look beyond the target for a more valuable piece
    target_value = PIECE_VALUES.get(target_piece.symbol().lower(), 0)
    for dist in range(1, 8):
        file = target_file + df * dist
        rank = target_rank + dr * dist
        
        if file < 0 or file > 7 or rank < 0 or rank > 7:
            break
        
        sq = chess.square(file, rank)
        sq_piece = board.piece_at(sq)
        
        if sq_piece is None:
            continue
        
        if sq_piece.color == opponent_color:
            behind_value = PIECE_VALUES.get(sq_piece.symbol().lower(), 0)
            # Check if piece behind is more valuable (skewer pattern)
            if behind_value >= target_value + 200:  # Minimum difference for skewer
                # Check if the valuable piece behind is undefended
                if not board.is_attacked_by(opponent_color, sq):
                    # Check if target (front piece) is undefended OR king is in check
                    is_king_in_check = (target_piece.piece_type == chess.KING and board.is_check())
                    if not board.is_attacked_by(opponent_color, target_square) or is_king_in_check:
                        return True
        else:
            # Our own piece blocks
            break
    
    return False


def can_profitably_pin_square(board: chess.Board, attacker_square: chess.Square,
                              target_square: chess.Square, color: chess.Color) -> bool:
    """Check if a piece can profitably pin a target square.
    
    A pin is profitable if:
    - The pinned piece cannot move away without exposing a more valuable piece behind it
    - The pinned piece cannot capture the attacker
    - The pinned piece is actually pinned (cannot move off the line)
    
    Args:
        board: Board position.
        attacker_square: Square of the potential pinning piece.
        target_square: Square of the target piece to be pinned.
        color: Color of the pinning side.
        
    Returns:
        True if the piece can profitably pin the target square.
    """
    opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
    attacker_piece = board.piece_at(attacker_square)
    target_piece = board.piece_at(target_square)
    
    if attacker_piece is None or attacker_piece.color != color:
        return False
    if target_piece is None or target_piece.color != opponent_color:
        return False
    
    # Only sliding pieces (rook, bishop, queen) can create pins
    if attacker_piece.piece_type not in [chess.ROOK, chess.BISHOP, chess.QUEEN]:
        return False
    
    # Check if target is on the same line as attacker
    attacker_file = chess.square_file(attacker_square)
    attacker_rank = chess.square_rank(attacker_square)
    target_file = chess.square_file(target_square)
    target_rank = chess.square_rank(target_square)
    
    # Check if on same file, rank, or diagonal
    on_same_file = (attacker_file == target_file)
    on_same_rank = (attacker_rank == target_rank)
    on_same_diagonal = (abs(attacker_file - target_file) == abs(attacker_rank - target_rank))
    
    # Check if direction is valid for piece type
    if attacker_piece.piece_type == chess.ROOK and not (on_same_file or on_same_rank):
        return False
    if attacker_piece.piece_type == chess.BISHOP and not on_same_diagonal:
        return False
    
    # Check if there's a more valuable piece behind the target (the king or a valuable piece)
    df = 1 if target_file > attacker_file else (-1 if target_file < attacker_file else 0)
    dr = 1 if target_rank > attacker_rank else (-1 if target_rank < attacker_rank else 0)
    
    # Look beyond the target for a more valuable piece (usually the king)
    target_value = PIECE_VALUES.get(target_piece.symbol().lower(), 0)
    for dist in range(1, 8):
        file = target_file + df * dist
        rank = target_rank + dr * dist
        
        if file < 0 or file > 7 or rank < 0 or rank > 7:
            break
        
        sq = chess.square(file, rank)
        sq_piece = board.piece_at(sq)
        
        if sq_piece is None:
            continue
        
        if sq_piece.color == opponent_color:
            behind_value = PIECE_VALUES.get(sq_piece.symbol().lower(), 0)
            is_king = (sq_piece.piece_type == chess.KING)
            # Check if piece behind is more valuable (pin pattern)
            # Usually the king (value 0) is behind, making any piece in front "pinned"
            if is_king or behind_value >= target_value + 200:
                # Verify the target is truly pinned (cannot move away without exposing the piece behind)
                # Check if target can capture the attacker
                if board.is_attacked_by(opponent_color, attacker_square):
                    # Target can capture attacker - not a true pin
                    return False
                # Check if target can move off the line without exposing the piece behind
                # This is a simplified check - a true pin means the target cannot move
                # without exposing something more valuable
                return True
        else:
            # Our own piece blocks
            break
    
    return False


def check_tactical_pattern_on_follow_up_moves(board_after_capture: chess.Board,
                                              follow_up_moves: List,
                                              target_square: chess.Square,
                                              color: chess.Color,
                                              max_moves_to_check: int = 2) -> Optional[str]:
    """Check if any of the follow-up moves create a profitable tactical pattern on the target square.
    
    This validates that the tactical pattern is actually executed, not just that it exists.
    A decoy requires that the tactic leads to a net material win, so we must look forward
    to verify the tactic is actually capitalizable.
    
    Args:
        board_after_capture: Board position after the opponent's capture.
        follow_up_moves: List of move data for follow-up moves to check.
        target_square: Square of the piece that was lured.
        color: Color of the player who executed the decoy.
        max_moves_to_check: Maximum number of follow-up moves to check (default 2).
        
    Returns:
        Tactical pattern type ("fork", "pin", "checkmate", "skewer", "check") if found, None otherwise.
    """
    opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
    target_piece = board_after_capture.piece_at(target_square)
    if not target_piece or target_piece.color != opponent_color:
        return None
    
    target_value = PIECE_VALUES.get(target_piece.symbol().lower(), 0)
    
    # Get material before first follow-up move (from board_after_capture)
    # Calculate material from board position
    def calculate_material(board: chess.Board, side_color: chess.Color) -> int:
        """Calculate total material value for a side."""
        total = 0
        for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            pieces = list(board.pieces(piece_type, side_color))
            piece_value = PIECE_VALUES.get(chess.Piece(piece_type, side_color).symbol().lower(), 0)
            total += len(pieces) * piece_value
        return total
    
    material_before_follow_up = calculate_material(board_after_capture, color)
    
    # Check each follow-up move
    for i, follow_up_move in enumerate(follow_up_moves[:max_moves_to_check]):
        if color == chess.WHITE:
            board_after_follow_up = parse_fen(follow_up_move.fen_white)
            move_san = follow_up_move.white_move
            material_after = follow_up_move.white_material
            material_before = material_before_follow_up if i == 0 else (follow_up_moves[i-1].white_material if i > 0 else None)
        else:
            board_after_follow_up = parse_fen(follow_up_move.fen_black)
            move_san = follow_up_move.black_move
            material_after = follow_up_move.black_material
            material_before = material_before_follow_up if i == 0 else (follow_up_moves[i-1].black_material if i > 0 else None)
        
        if not board_after_follow_up:
            continue
        
        # Parse the destination square from the move
        dest_square = parse_destination_square(move_san)
        if dest_square is None:
            continue
        
        # Check if this move creates a profitable fork on the target square
        if can_profitably_fork_square(board_after_follow_up, dest_square, target_square, color):
            return "fork"
        
        # Check if this move creates a profitable pin on the target square
        if can_profitably_pin_square(board_after_follow_up, dest_square, target_square, color):
            return "pin"
        
        # Check if this move creates a profitable skewer on the target square
        if can_profitably_skewer_square(board_after_follow_up, dest_square, target_square, color):
            return "skewer"
        
        # Check if this delivers checkmate and the target (king) is involved
        if board_after_follow_up.is_checkmate():
            if target_piece.piece_type == chess.KING:
                return "checkmate"
        
        # Check if this move gives check and leads to material gain
        # This handles cases like Rxe8+ where check wins material (e.g., captures a piece)
        # For a decoy, we need to verify the check leads to a net material win by looking forward
        if board_after_follow_up.is_check():
            # Check material change on this move
            material_gain_this_move = 0
            if material_before is not None and material_after is not None:
                material_gain_this_move = material_after - material_before
            
            # IMPORTANT: For a decoy, the check might capture material on the same move
            # This is the case for Rxe8+ where the check itself captures the knight
            # We should check if material increased on this move (indicating a capture)
            if material_gain_this_move >= MIN_VALUABLE_PIECE_VALUE:
                return "fork"  # Generic "tactical pattern" for check+material gain
            
            # Also check if the move is a capture (indicated by 'x' in SAN)
            # For a decoy, a check that captures material is profitable
            # We check the board directly to verify a capture occurred, since material tracking
            # might not be accurate or updated immediately
            if "x" in move_san:
                # Check if material increased (if tracking is accurate)
                if material_before is not None and material_after is not None:
                    if material_after - material_before >= 200:
                        return "fork"  # Generic "tactical pattern" for check+capture
                
                # Even if material tracking doesn't show an increase, a check+capture is likely profitable
                # This handles cases where material tracking is delayed or inaccurate
                # For decoy purposes, if we have check + capture notation, it's a profitable tactical pattern
                return "fork"  # Generic "tactical pattern" for check+capture
            
            # Look at the next move to see if material was gained (opponent's response)
            # For a decoy, the check should lead to material gain after opponent responds
            if i + 1 < len(follow_up_moves):
                next_move = follow_up_moves[i + 1]
                if color == chess.WHITE:
                    material_after_next = next_move.white_material
                else:
                    material_after_next = next_move.black_material
                
                # Calculate net material gain after opponent's response
                net_material_gain = material_after_next - material_before if material_before is not None else 0
                
                # If we gained material after the check sequence, it's profitable
                if net_material_gain >= MIN_VALUABLE_PIECE_VALUE:
                    return "fork"  # Generic "tactical pattern" for check+material gain
            
            # Also check if target piece becomes vulnerable (undefended) after the check
            target_after = board_after_follow_up.piece_at(target_square)
            if target_after and target_after.color == opponent_color:
                # Check if target is now undefended (can be captured)
                if not board_after_follow_up.is_attacked_by(opponent_color, target_square):
                    # Target is undefended - verify we can attack it or will gain material
                    # For a decoy, if check + target is undefended, it's likely profitable
                    if target_value >= MIN_VALUABLE_PIECE_VALUE:
                        # Look ahead one more move to see if we capture it
                        if i + 1 < len(follow_up_moves):
                            next_move = follow_up_moves[i + 1]
                            if color == chess.WHITE:
                                material_after_next = next_move.white_material
                            else:
                                material_after_next = next_move.black_material
                            
                            net_gain = material_after_next - material_before if material_before is not None else 0
                            if net_gain >= target_value - 200:  # Allow some tolerance
                                return "fork"  # Generic tactical pattern
                        else:
                            # No next move, but check + undefended valuable piece is likely profitable
                            if target_value >= MIN_VALUABLE_PIECE_VALUE:
                                return "fork"  # Generic tactical pattern
    
    return None


def parse_destination_square(move_san: str) -> Optional[chess.Square]:
    """Parse the destination square from a move in SAN notation.
    
    Args:
        move_san: Move in SAN notation (e.g., "Rxe8+", "Nf3", "Qxc4").
        
    Returns:
        Destination square, or None if not found.
    """
    try:
        dest_part = move_san
        if "=" in dest_part:
            dest_part = dest_part.split("=")[0]
        if "x" in dest_part:
            parts = dest_part.split("x")
            if len(parts) > 1:
                dest_part = parts[-1]
        if "+" in dest_part:
            dest_part = dest_part.replace("+", "")
        if "#" in dest_part:
            dest_part = dest_part.replace("#", "")
        
        if len(dest_part) >= 2:
            return chess.parse_square(dest_part[-2:])
    except (ValueError, AttributeError):
        pass
    return None

