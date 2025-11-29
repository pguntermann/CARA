"""Utility functions for tracking chess material balance."""

import chess
from typing import Dict


# Standard piece values (in centipawns)
PIECE_VALUES = {
    chess.PAWN: 100,
    chess.KNIGHT: 300,
    chess.BISHOP: 300,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0  # King has no material value
}


def calculate_material_balance(board: chess.Board) -> int:
    """Calculate material balance for a position.
    
    Args:
        board: Chess board position.
        
    Returns:
        Material balance in centipawns (positive = white advantage, negative = black advantage).
    """
    balance = 0
    
    for piece_type in PIECE_VALUES:
        if piece_type == chess.KING:
            continue  # Skip king (no material value)
        
        # Count white pieces
        white_count = len(board.pieces(piece_type, chess.WHITE))
        # Count black pieces
        black_count = len(board.pieces(piece_type, chess.BLACK))
        
        # Calculate balance (positive = white advantage)
        piece_value = PIECE_VALUES[piece_type]
        balance += (white_count - black_count) * piece_value
    
    return balance


def calculate_material_loss(board_before: chess.Board, board_after: chess.Board, 
                           is_white_to_move: bool) -> int:
    """Calculate material loss from a move.
    
    Args:
        board_before: Board position before the move.
        board_after: Board position after the move.
        is_white_to_move: True if white just moved, False if black just moved.
        
    Returns:
        Material loss in centipawns (positive = material was lost by the moving side).
    """
    balance_before = calculate_material_balance(board_before)
    balance_after = calculate_material_balance(board_after)
    
    if is_white_to_move:
        # White just moved - if balance decreased, white lost material
        # If balance increased, white gained material (negative loss)
        loss = balance_before - balance_after
    else:
        # Black just moved - if balance increased, black lost material
        # If balance decreased, black gained material (negative loss)
        loss = balance_after - balance_before
    
    # Loss is positive if material was lost, negative if material was gained
    return loss


def get_captured_piece_letter(board_before: chess.Board, move: chess.Move) -> str:
    """Get the letter of the captured piece (p, r, n, b, q, or "" if no capture or pawn).
    
    Args:
        board_before: Board position before the move.
        move: The move that was played.
        
    Returns:
        Letter of captured piece (p, r, n, b, q) or "" if no capture or pawn capture.
    """
    if not board_before.is_capture(move):
        return ""
    
    # Get the captured piece at the destination square before the move
    captured_piece = board_before.piece_at(move.to_square)
    if captured_piece is None:
        return ""
    
    # Map piece type to letter (lowercase for black pieces, but we want lowercase for all)
    piece_type = captured_piece.piece_type
    if piece_type == chess.PAWN:
        return "p"
    elif piece_type == chess.ROOK:
        return "r"
    elif piece_type == chess.KNIGHT:
        return "n"
    elif piece_type == chess.BISHOP:
        return "b"
    elif piece_type == chess.QUEEN:
        return "q"
    else:
        return ""


def calculate_material_count(board: chess.Board, is_white: bool) -> int:
    """Calculate material count for a specific side.
    
    Args:
        board: Chess board position.
        is_white: True for white, False for black.
        
    Returns:
        Material count in centipawns (excluding kings).
    """
    material = 0
    color = chess.WHITE if is_white else chess.BLACK
    
    for piece_type in PIECE_VALUES:
        if piece_type == chess.KING:
            continue  # Skip king (no material value)
        
        # Count pieces of this type for the specified color
        count = len(board.pieces(piece_type, color))
        piece_value = PIECE_VALUES[piece_type]
        material += count * piece_value
    
    return material


def count_pieces(board: chess.Board, is_white: bool) -> Dict[int, int]:
    """Count pieces for a specific side.
    
    Args:
        board: Chess board position.
        is_white: True for white, False for black.
        
    Returns:
        Dictionary mapping piece_type to count (excluding kings).
        Keys: chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN
    """
    color = chess.WHITE if is_white else chess.BLACK
    counts = {
        chess.QUEEN: len(board.pieces(chess.QUEEN, color)),
        chess.ROOK: len(board.pieces(chess.ROOK, color)),
        chess.BISHOP: len(board.pieces(chess.BISHOP, color)),
        chess.KNIGHT: len(board.pieces(chess.KNIGHT, color)),
        chess.PAWN: len(board.pieces(chess.PAWN, color))
    }
    return counts