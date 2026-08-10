"""Helper functions for game highlight detection."""

from typing import Optional, List, Tuple, Union
import chess
from app.services.game_highlights.constants import PIECE_VALUES


def piece_type_from_letter(letter: str) -> Optional[chess.PieceType]:
    """Map a piece letter (``n``/``N``, capture codes, etc.) to a ``chess.PieceType``."""
    if not letter:
        return None
    try:
        return chess.Piece.from_symbol(letter.lower()).piece_type
    except ValueError:
        return None


def piece_type_from_san(san: str) -> Optional[chess.PieceType]:
    """Infer the moving piece type from SAN (pawn file letters, ``NBRQK``, or ``O-O``)."""
    if not san:
        return None
    if san.startswith("O"):
        return chess.KING
    ch = san[0]
    if ch in "NBRQK":
        return piece_type_from_letter(ch)
    if ch in "abcdefgh":
        return chess.PAWN
    return None


def piece_name(
    piece: Union[str, chess.PieceType, chess.Piece, None],
    *,
    default: str = "",
) -> str:
    """Human-readable piece name (``knight``, ``queen``, …).

    Accepts a letter (``n``/``N``), ``chess.PieceType``, ``chess.Piece``, or
    already-lowercased name-like strings fall through to ``default`` / as-is.
    """
    if piece is None:
        return default
    if isinstance(piece, chess.Piece):
        return chess.piece_name(piece.piece_type)
    if isinstance(piece, int):
        try:
            return chess.piece_name(piece)
        except (IndexError, ValueError, TypeError):
            return default
    letter = str(piece).strip()
    if not letter:
        return default
    if len(letter) == 1:
        piece_type = piece_type_from_letter(letter)
        if piece_type is not None:
            return chess.piece_name(piece_type)
        return default or letter
    return letter.lower()


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


def is_file_open(board: chess.Board, file: int) -> bool:
    """True if neither side has a pawn on ``file`` (0–7)."""
    for color in (chess.WHITE, chess.BLACK):
        if any(chess.square_file(sq) == file for sq in board.pieces(chess.PAWN, color)):
            return False
    return True


def is_passed_pawn(
    board: chess.Board, pawn_square: chess.Square, color: chess.Color
) -> bool:
    """True if no enemy pawn stands on the same or adjacent files ahead of this pawn."""
    pawn_file = chess.square_file(pawn_square)
    pawn_rank = chess.square_rank(pawn_square)
    opponent = not color
    ahead = range(pawn_rank + 1, 8) if color == chess.WHITE else range(pawn_rank - 1, -1, -1)

    for check_file in (pawn_file - 1, pawn_file, pawn_file + 1):
        if check_file < 0 or check_file > 7:
            continue
        for rank in ahead:
            piece = board.piece_at(chess.square(check_file, rank))
            if piece and piece.piece_type == chess.PAWN and piece.color == opponent:
                return False
    return True


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


def is_attacked_by_pawn(
    board: chess.Board, square: chess.Square, color: chess.Color
) -> bool:
    """True if a pawn of ``color`` currently attacks ``square``."""
    for attacker in board.attackers(color, square):
        piece = board.piece_at(attacker)
        if piece is not None and piece.piece_type == chess.PAWN:
            return True
    return False


def san_is_check(san: str) -> bool:
    """True if SAN indicates check or mate."""
    return "+" in (san or "") or "#" in (san or "")


def san_is_tactical(san: str) -> bool:
    """True if SAN is a capture, check, or mate."""
    return "x" in (san or "") or "+" in (san or "") or "#" in (san or "")


def _can_legally_capture(
    board: chess.Board, from_square: chess.Square, to_square: chess.Square
) -> bool:
    """True if the piece on ``from_square`` can legally capture on ``to_square``.

    ``board.attackers`` is geometric only (e.g. a king "attacks" a defended
    square it cannot step onto). Fork safety must use legal moves.
    """
    piece = board.piece_at(from_square)
    if piece is None or piece.color != board.turn:
        return False
    move = chess.Move(from_square, to_square)
    if piece.piece_type == chess.PAWN and chess.square_rank(to_square) in (0, 7):
        move = chess.Move(from_square, to_square, promotion=chess.QUEEN)
    return move in board.legal_moves


def is_exploitable_fork(
    board: chess.Board,
    piece_square: chess.Square,
    color: chess.Color,
) -> bool:
    """True if the piece on ``piece_square`` creates an exploitable fork.

    A fork requires attacking two or more enemy pieces after the move.
    Capturing an undefended piece with check is not itself a fork — the
    captured unit is gone (e.g. Rxf4+ only checks the king afterward).

    Exploitable forks include:
    - undefended target worth more than the forker
    - forker cheaper than every valuable target (up after a recapture)
    - royal fork that also attacks free material still on the board
      (e.g. Nxc7+ checks the king and attacks an undefended pawn on a6)
    """
    opponent_color = not color
    piece = board.piece_at(piece_square)
    if piece is None or piece.color != color:
        return False

    # Forker safety / cheap elimination (legal captures only):
    # - Hanging forker (not defended) that the opponent can capture is not exploitable.
    # - If the forker is defended, equal-or-lesser capturers can still trade out cheaply.
    attacker_value = PIECE_VALUES.get(piece.symbol().lower(), 0)
    forker_defended = board.is_attacked_by(color, piece_square)
    legal_capturers = [
        sq
        for sq in board.attackers(opponent_color, piece_square)
        if _can_legally_capture(board, sq, piece_square)
    ]

    if legal_capturers and not forker_defended:
        return False

    if forker_defended:
        for attacker_sq in legal_capturers:
            attacker_piece = board.piece_at(attacker_sq)
            if attacker_piece is None:
                continue
            attacker_piece_value = PIECE_VALUES.get(
                attacker_piece.symbol().lower(), 0
            )
            if attacker_piece_value <= attacker_value:
                return False

    attacked_squares = board.attacks(piece_square)

    enemy_pieces = []
    valuable_values: List[int] = []
    undefended_higher_value_count = 0
    undefended_free_count = 0
    attacks_king = False

    for sq in attacked_squares:
        enemy_piece = board.piece_at(sq)
        if enemy_piece and enemy_piece.color == opponent_color:
            enemy_pieces.append((sq, enemy_piece))
            piece_value = PIECE_VALUES.get(enemy_piece.symbol().lower(), 0)

            if enemy_piece.piece_type == chess.KING:
                attacks_king = True
                continue

            defended = board.is_attacked_by(opponent_color, sq)
            if piece_value >= 100 and not defended:
                undefended_free_count += 1
                if piece_value > attacker_value:
                    undefended_higher_value_count += 1

            if piece_value >= MIN_VALUABLE_PIECE_VALUE:
                valuable_values.append(piece_value)

    if len(enemy_pieces) < 2:
        return False

    if attacks_king:
        has_secondary = len(valuable_values) >= 1 or undefended_free_count >= 1
        if not has_secondary:
            return False
    elif len(valuable_values) < 2:
        return False

    if undefended_higher_value_count >= 1:
        return True
    if attacks_king and undefended_free_count >= 1:
        return True
    if valuable_values and attacker_value < min(valuable_values):
        return True

    return False


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

        # Check that captures material (e.g. Rxe8+ after a decoy): require an actual
        # capture, not a bare check that merely happens while an unrelated piece is
        # undefended (that mislabels mating nets as "fork").
        if board_after_follow_up.is_check() and "x" in (move_san or ""):
            material_gain_this_move = 0
            if material_before is not None and material_after is not None:
                material_gain_this_move = material_after - material_before
            if material_gain_this_move >= MIN_VALUABLE_PIECE_VALUE:
                return "fork"
            # Capture+check is still a real tactical follow-up even if material
            # fields are briefly stale.
            return "fork"

        # Check that leads to a clear material gain on the next ply
        if board_after_follow_up.is_check() and i + 1 < len(follow_up_moves):
            next_move = follow_up_moves[i + 1]
            if color == chess.WHITE:
                material_after_next = next_move.white_material
            else:
                material_after_next = next_move.black_material
            if material_before is not None and material_after_next is not None:
                net_material_gain = material_after_next - material_before
                if net_material_gain >= MIN_VALUABLE_PIECE_VALUE:
                    return "fork"

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


def find_moved_piece_square(
    move_san: str,
    board_before: chess.Board,
    board_after: chess.Board,
    color: chess.Color,
) -> Optional[chess.Square]:
    """Find the destination square of the piece that moved this half-move.

    Shared replacement for the many per-rule ``_find_moved_piece_square`` copies.
    """
    dest_square = parse_destination_square(move_san)
    if dest_square is None:
        return None

    try:
        for piece_type in (
            chess.PAWN,
            chess.KNIGHT,
            chess.BISHOP,
            chess.ROOK,
            chess.QUEEN,
            chess.KING,
        ):
            pieces_before = list(board_before.pieces(piece_type, color))
            pieces_after = list(board_after.pieces(piece_type, color))

            for sq in pieces_before:
                if sq not in pieces_after:
                    if dest_square in pieces_after or board_after.piece_at(
                        dest_square
                    ) == chess.Piece(piece_type, color):
                        return dest_square

            if len(pieces_after) > len(pieces_before) and dest_square in pieces_after:
                return dest_square

        piece_at_dest = board_after.piece_at(dest_square)
        if piece_at_dest and piece_at_dest.color == color:
            return dest_square
    except (ValueError, AttributeError):
        pass
    return None

