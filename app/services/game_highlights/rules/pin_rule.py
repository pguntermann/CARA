"""Rule for detecting pins."""

from typing import List, Optional
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen
from app.services.game_highlights.constants import PIECE_VALUES


class PinRule(HighlightRule):
    """Detects when a move creates a meaningful pin (pinning an enemy piece to a more valuable piece)."""
    
    # Minimum value of pinned piece for a meaningful pin
    MIN_PINNED_PIECE_VALUE = 300
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for pin highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's pin
        if move.white_move and move.cpl_white and context.move_index > 0:
            try:
                cpl = float(move.cpl_white)
                if cpl >= context.good_move_max_cpl:
                    # Not a good move, skip
                    pass
                else:
                    board_after = parse_fen(move.fen_white)
                    if board_after and context.prev_move and context.prev_move.fen_black:
                        board_before = parse_fen(context.prev_move.fen_black)
                        if board_before:
                            moved_piece_square = self._find_moved_piece_square(
                                move.white_move, board_before, board_after, chess.WHITE
                            )
                            if moved_piece_square is not None:
                                pinned_square = self._find_pinned_piece(board_after, moved_piece_square, chess.WHITE)
                                if pinned_square is not None:
                                    highlights.append(GameHighlight(
                                        move_number=move_num,
                                        is_white=True,
                                        move_notation=f"{move_num}. {move.white_move}",
                                        description="White created a pin",
                                        priority=38,
                                        rule_type="pin"
                                    ))
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Black's pin
        if move.black_move and move.cpl_black:
            try:
                cpl = float(move.cpl_black)
                if cpl >= context.good_move_max_cpl:
                    # Not a good move, skip
                    pass
                else:
                    board_after = parse_fen(move.fen_black)
                    if board_after and move.fen_white:
                        board_before = parse_fen(move.fen_white)
                        if board_before:
                            moved_piece_square = self._find_moved_piece_square(
                                move.black_move, board_before, board_after, chess.BLACK
                            )
                            if moved_piece_square is not None:
                                pinned_square = self._find_pinned_piece(board_after, moved_piece_square, chess.BLACK)
                                if pinned_square is not None:
                                    highlights.append(GameHighlight(
                                        move_number=move_num,
                                        is_white=False,
                                        move_notation=f"{move_num}. ...{move.black_move}",
                                        description="Black created a pin",
                                        priority=38,
                                        rule_type="pin"
                                    ))
            except (ValueError, TypeError, AttributeError):
                pass
        
        return highlights
    
    def _find_moved_piece_square(self, move_san: str, board_before: chess.Board, 
                                 board_after: chess.Board, color: chess.Color) -> Optional[chess.Square]:
        """Find the square of the piece that moved.
        
        Args:
            move_san: Move in SAN notation.
            board_before: Board position before the move.
            board_after: Board position after the move.
            color: Color of the moving side.
        
        Returns:
            Square index of the moved piece, or None if not found.
        """
        try:
            # Parse destination square from move notation
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
                dest_square = chess.parse_square(dest_part[-2:])
                
                # Find which piece moved by comparing piece positions
                for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]:
                    pieces_before = list(board_before.pieces(piece_type, color))
                    pieces_after = list(board_after.pieces(piece_type, color))
                    
                    for sq in pieces_before:
                        if sq not in pieces_after:
                            if dest_square in pieces_after or board_after.piece_at(dest_square) == chess.Piece(piece_type, color):
                                return dest_square
                    
                    if len(pieces_after) > len(pieces_before):
                        if dest_square in pieces_after:
                            return dest_square
                
                piece_at_dest = board_after.piece_at(dest_square)
                if piece_at_dest and piece_at_dest.color == color:
                    return dest_square
        except (ValueError, AttributeError):
            pass
        return None
    
    def _find_pinned_piece(self, board: chess.Board, attacker_square: chess.Square, attacker_color: chess.Color) -> Optional[chess.Square]:
        """Find if the moved piece creates a pin on an enemy piece.
        
        Args:
            board: Board position after the move.
            attacker_square: Square of the attacking piece.
            attacker_color: Color of the attacking piece.
        
        Returns:
            Square of pinned piece if found, None otherwise.
        """
        opponent_color = chess.BLACK if attacker_color == chess.WHITE else chess.WHITE
        attacker_piece = board.piece_at(attacker_square)
        if attacker_piece is None or attacker_piece.color != attacker_color:
            return None
        
        # Only sliding pieces (rook, bishop, queen) can create pins
        if attacker_piece.piece_type not in [chess.ROOK, chess.BISHOP, chess.QUEEN]:
            return None
        
        # Use python-chess is_pinned to correctly identify pinned pieces
        # is_pinned checks if a piece cannot move because it's blocking an attack on a more valuable piece
        # However, we need to verify the piece is actually pinned (cannot move away)
        # A piece is only truly pinned if moving it would expose the king to check
        # If it can capture the attacker, it's not a pin - it's just an attack
        for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN]:
            for sq in board.pieces(piece_type, opponent_color):
                if board.is_pinned(opponent_color, sq):
                    # Verify the pin is created by our attacker
                    # Check if attacker is on the same line as pinned piece
                    pinned_piece = board.piece_at(sq)
                    if pinned_piece:
                        piece_letter = pinned_piece.symbol().lower()
                        pinned_value = PIECE_VALUES.get(piece_letter, 0)
                        
                        # Verify pin is exploitable: pinned piece >=300cp AND target behind >=500cp
                        if pinned_value >= self.MIN_PINNED_PIECE_VALUE:
                            # Check if attacker is on the same line as pinned piece
                            if self._is_on_same_line(attacker_square, sq, attacker_piece.piece_type):
                                # Verify the attacker is actually creating the pin by checking the ray
                                if self._attacker_creates_pin(board, attacker_square, sq, opponent_color):
                                    # Check if there's a more valuable piece behind (target >=500cp)
                                    target_value = self._get_target_piece_value(board, attacker_square, sq, opponent_color)
                                    if target_value >= 500:
                                        # CRITICAL: Verify the piece is actually pinned (cannot move)
                                        # A piece is only pinned if moving it would expose the king to check
                                        # If it can capture the attacker, it's not a true pin
                                        if self._is_truly_pinned(board, sq, attacker_square, opponent_color):
                                            return sq
        
        return None
    
    def _attacker_creates_pin(self, board: chess.Board, attacker_square: chess.Square,
                             pinned_square: chess.Square, opponent_color: chess.Color) -> bool:
        """Verify that the attacker is actually creating the pin.
        
        A pin means the pinned piece is blocking an attack on a more valuable piece.
        This method verifies that the attacker is on the ray between the pinned piece
        and the more valuable piece it's protecting.
        
        Args:
            board: Board position.
            attacker_square: Square of the attacking piece.
            pinned_square: Square of the pinned piece.
            opponent_color: Color of the opponent.
        
        Returns:
            True if the attacker is creating the pin.
        """
        attacker_file = chess.square_file(attacker_square)
        attacker_rank = chess.square_rank(attacker_square)
        pinned_file = chess.square_file(pinned_square)
        pinned_rank = chess.square_rank(pinned_square)
        
        # Calculate direction from attacker to pinned piece
        df = pinned_file - attacker_file
        dr = pinned_rank - attacker_rank
        
        if df == 0 and dr == 0:
            return False
        
        # Normalize direction
        if df != 0:
            df = df // abs(df)
        if dr != 0:
            dr = dr // abs(dr)
        
        # Continue along the ray past the pinned piece to find what it's protecting
        for dist in range(1, 8):
            file = pinned_file + df * dist
            rank = pinned_rank + dr * dist
            
            if file < 0 or file > 7 or rank < 0 or rank > 7:
                break
            
            sq = chess.square(file, rank)
            sq_piece = board.piece_at(sq)
            
            if sq_piece is None:
                continue
            
            if sq_piece.color == opponent_color:
                # Found what the pinned piece is protecting
                # The attacker must be on the ray between the pinned piece and this target
                # This is already verified by is_pinned, so return True
                return True
            else:
                # Our own piece blocks the ray
                break
        
        return False
    
    def _is_truly_pinned(self, board: chess.Board, pinned_square: chess.Square,
                        attacker_square: chess.Square, opponent_color: chess.Color) -> bool:
        """Verify that a piece is truly pinned (cannot move away from the pin line).
        
        A piece is only truly pinned if moving it would expose the king to check.
        If the piece can capture the attacker, it's not a true pin - it's just an attack.
        
        Args:
            board: Board position.
            pinned_square: Square of the potentially pinned piece.
            attacker_square: Square of the attacking piece.
            opponent_color: Color of the opponent (owner of pinned piece).
        
        Returns:
            True if the piece is truly pinned (cannot move without exposing king).
        """
        # Check if the pinned piece can capture the attacker
        # If it can, it's not a true pin
        pinned_piece = board.piece_at(pinned_square)
        if pinned_piece is None:
            return False
        
        # Check if pinned piece can move to attacker's square
        if board.is_attacked_by(opponent_color, attacker_square):
            # The pinned piece can capture the attacker, so it's not truly pinned
            return False
        
        # Check if the pinned piece can move to any square that doesn't expose the king
        # A truly pinned piece can only move along the pin line (if at all)
        # Try moving the piece to a square not on the pin line
        pinned_file = chess.square_file(pinned_square)
        pinned_rank = chess.square_rank(pinned_square)
        attacker_file = chess.square_file(attacker_square)
        attacker_rank = chess.square_rank(attacker_square)
        
        # Calculate direction from attacker to pinned piece
        df = pinned_file - attacker_file
        dr = pinned_rank - attacker_rank
        
        # Normalize direction
        if df != 0:
            df_norm = df // abs(df)
        else:
            df_norm = 0
        if dr != 0:
            dr_norm = dr // abs(dr)
        else:
            dr_norm = 0
        
        # Check if pinned piece can move to any square not on the pin line
        for move in board.legal_moves:
            if move.from_square == pinned_square:
                to_sq = move.to_square
                to_file = chess.square_file(to_sq)
                to_rank = chess.square_rank(to_sq)
                
                # Calculate direction from attacker to destination
                to_df = to_file - attacker_file
                to_dr = to_rank - attacker_rank
                
                # Normalize
                if to_df != 0:
                    to_df_norm = to_df // abs(to_df)
                else:
                    to_df_norm = 0
                if to_dr != 0:
                    to_dr_norm = to_dr // abs(to_dr)
                else:
                    to_dr_norm = 0
                
                # If destination is not on the pin line, check if it exposes the king
                if not (to_df_norm == df_norm and to_dr_norm == dr_norm):
                    # Piece can move off the pin line - check if this exposes the king
                    board_copy = board.copy()
                    board_copy.push(move)
                    if not board_copy.is_check():
                        # Piece can move off the pin line without exposing king - not truly pinned
                        return False
        
        # Piece cannot move off the pin line without exposing king - truly pinned
        return True
    
    def _is_on_same_line(self, square1: chess.Square, square2: chess.Square, piece_type: chess.PieceType) -> bool:
        """Check if two squares are on the same line (rank, file, or diagonal).
        
        Args:
            square1: First square.
            square2: Second square.
            piece_type: Type of piece (to determine line type).
        
        Returns:
            True if squares are on the same line.
        """
        file1 = chess.square_file(square1)
        rank1 = chess.square_rank(square1)
        file2 = chess.square_file(square2)
        rank2 = chess.square_rank(square2)
        
        if piece_type == chess.ROOK:
            return file1 == file2 or rank1 == rank2
        elif piece_type == chess.BISHOP:
            return abs(file1 - file2) == abs(rank1 - rank2)
        elif piece_type == chess.QUEEN:
            return (file1 == file2 or rank1 == rank2 or 
                   abs(file1 - file2) == abs(rank1 - rank2))
        return False
    
    def _get_target_piece_value(self, board: chess.Board, attacker_square: chess.Square,
                                pinned_square: chess.Square, opponent_color: chess.Color) -> int:
        """Get the value of the target piece behind the pinned piece.
        
        Args:
            board: Board position.
            attacker_square: Square of the attacking piece.
            pinned_square: Square of the pinned piece.
            opponent_color: Color of the opponent.
        
        Returns:
            Value of the target piece behind (0 if not found or king).
        """
        attacker_file = chess.square_file(attacker_square)
        attacker_rank = chess.square_rank(attacker_square)
        pinned_file = chess.square_file(pinned_square)
        pinned_rank = chess.square_rank(pinned_square)
        
        # Calculate direction from attacker to pinned piece
        df = pinned_file - attacker_file
        dr = pinned_rank - attacker_rank
        
        if df == 0 and dr == 0:
            return 0
        
        # Normalize direction
        if df != 0:
            df = df // abs(df)
        if dr != 0:
            dr = dr // abs(dr)
        
        # Continue along the ray past the pinned piece
        for dist in range(1, 8):
            file = pinned_file + df * dist
            rank = pinned_rank + dr * dist
            
            if file < 0 or file > 7 or rank < 0 or rank > 7:
                break
            
            sq = chess.square(file, rank)
            sq_piece = board.piece_at(sq)
            
            if sq_piece is None:
                continue
            
            if sq_piece.color == opponent_color:
                # Found target piece behind the pinned piece
                piece_letter = sq_piece.symbol().lower()
                piece_value = PIECE_VALUES.get(piece_letter, 0)
                # King is special case - return high value (900cp) to indicate king is target
                if sq_piece.piece_type == chess.KING:
                    return 900
                return piece_value
            else:
                # Our own piece blocks the ray
                break
        
        return 0
    
    def _has_more_valuable_piece_behind(self, board: chess.Board, attacker_square: chess.Square,
                                       pinned_square: chess.Square, opponent_color: chess.Color) -> bool:
        """Check if there's a more valuable piece behind the pinned piece.
        
        Args:
            board: Board position.
            attacker_square: Square of the attacking piece.
            pinned_square: Square of the potentially pinned piece.
            opponent_color: Color of the opponent.
        
        Returns:
            True if there's a more valuable piece behind the pinned piece.
        """
        attacker_file = chess.square_file(attacker_square)
        attacker_rank = chess.square_rank(attacker_square)
        pinned_file = chess.square_file(pinned_square)
        pinned_rank = chess.square_rank(pinned_square)
        
        # Calculate direction from attacker to pinned piece
        df = pinned_file - attacker_file
        dr = pinned_rank - attacker_rank
        
        if df == 0 and dr == 0:
            return False
        
        # Normalize direction
        if df != 0:
            df = df // abs(df)
        if dr != 0:
            dr = dr // abs(dr)
        
        pinned_piece = board.piece_at(pinned_square)
        if pinned_piece is None:
            return False
        
        pinned_value = PIECE_VALUES.get(pinned_piece.symbol().lower(), 0)
        
        # Continue along the ray past the pinned piece
        for dist in range(1, 8):
            file = pinned_file + df * dist
            rank = pinned_rank + dr * dist
            
            if file < 0 or file > 7 or rank < 0 or rank > 7:
                break
            
            sq = chess.square(file, rank)
            sq_piece = board.piece_at(sq)
            
            if sq_piece is None:
                continue
            
            if sq_piece.color == opponent_color:
                # More valuable piece behind the pinned piece
                piece_letter = sq_piece.symbol().lower()
                piece_value = PIECE_VALUES.get(piece_letter, 0)
                if piece_value > pinned_value:
                    return True
            else:
                # Our own piece blocks the ray
                break
        
        return False

