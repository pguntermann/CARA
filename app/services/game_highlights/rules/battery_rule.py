"""Rule for detecting battery creation (two aligned pieces on the same line)."""

from typing import List, Optional, Tuple
import chess
from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen


class BatteryRule(HighlightRule):
    """Detects when a move creates a battery (two aligned pieces on the same line)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for battery highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Skip batteries in opening phase - they're usually not meaningful
        if move_num <= context.opening_end:
            return highlights
        
        # White's battery
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
                                battery_info = self._creates_battery(
                                    board_before, board_after, moved_piece_square, chess.WHITE, context
                                )
                                if battery_info:
                                    line_type, line_desc = battery_info
                                    highlights.append(GameHighlight(
                                        move_number=move_num,
                                        is_white=True,
                                        move_notation=f"{move_num}. {move.white_move}",
                                        description=f"White created a battery on the {line_desc}",
                                        priority=35,
                                        rule_type="battery"
                                    ))
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Black's battery
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
                                battery_info = self._creates_battery(
                                    board_before, board_after, moved_piece_square, chess.BLACK, context
                                )
                                if battery_info:
                                    line_type, line_desc = battery_info
                                    highlights.append(GameHighlight(
                                        move_number=move_num,
                                        is_white=False,
                                        move_notation=f"{move_num}. ...{move.black_move}",
                                        description=f"Black created a battery on the {line_desc}",
                                        priority=35,
                                        rule_type="battery"
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
                    
                    # Find piece that disappeared from before position
                    for sq in pieces_before:
                        if sq not in pieces_after:
                            # This piece moved - verify it's now on destination square
                            if dest_square in pieces_after or board_after.piece_at(dest_square) == chess.Piece(piece_type, color):
                                return dest_square
                    
                    # Handle promotions (piece count increases)
                    if len(pieces_after) > len(pieces_before):
                        if dest_square in pieces_after:
                            return dest_square
                
                # Fallback: if destination square has a piece of the right color, assume that's it
                piece_at_dest = board_after.piece_at(dest_square)
                if piece_at_dest and piece_at_dest.color == color:
                    return dest_square
        except (ValueError, AttributeError):
            pass
        return None
    
    def _creates_battery(self, board_before: chess.Board, board_after: chess.Board,
                        moved_piece_square: chess.Square, color: chess.Color, context: RuleContext) -> Optional[Tuple[str, str]]:
        """Check if the move creates a battery.
        
        Args:
            board_before: Board position before the move.
            board_after: Board position after the move.
            moved_piece_square: Square of the moved piece.
            color: Color of the moving side.
            
        Returns:
            Tuple of (line_type, line_description) if battery created, None otherwise.
            line_type: "file", "rank", or "diagonal"
            line_description: Human-readable description (e.g., "e file", "4th rank", "a1-h8 diagonal")
        """
        # Find the moved piece's previous position by comparing before and after boards
        moved_piece = board_after.piece_at(moved_piece_square)
        if moved_piece is None:
            return None
        moved_piece_type = moved_piece.piece_type
        
        # Find where the moved piece was before the move
        moved_piece_before_square = None
        pieces_before = list(board_before.pieces(moved_piece_type, color))
        pieces_after = list(board_after.pieces(moved_piece_type, color))
        
        # The moved piece is on moved_piece_square after the move
        # Find which square it was on before by finding a square that had the piece before but doesn't after
        for sq in pieces_before:
            if sq not in pieces_after:
                # This square lost a piece of this type - it's likely the moved piece's previous position
                # Verify by checking if the piece type matches
                piece_at_sq_before = board_before.piece_at(sq)
                if piece_at_sq_before and piece_at_sq_before.piece_type == moved_piece_type:
                    moved_piece_before_square = sq
                    break
        
        # If we couldn't find it (e.g., promotion), check if piece was already on destination
        if moved_piece_before_square is None:
            if board_before.piece_at(moved_piece_square) and board_before.piece_at(moved_piece_square).piece_type == moved_piece_type:
                moved_piece_before_square = moved_piece_square
        
        if moved_piece is None or moved_piece.color != color:
            return None
        
        # Only rooks, queens, and bishops can form batteries
        if moved_piece_type not in [chess.ROOK, chess.QUEEN, chess.BISHOP]:
            return None
        
        moved_file = chess.square_file(moved_piece_square)
        moved_rank = chess.square_rank(moved_piece_square)
        
        # Check for batteries on files, ranks, and diagonals
        # Check all friendly rooks, queens, and bishops
        for piece_type in [chess.ROOK, chess.QUEEN, chess.BISHOP]:
            for other_sq in board_after.pieces(piece_type, color):
                if other_sq == moved_piece_square:
                    continue  # Skip the moved piece itself
                
                other_piece = board_after.piece_at(other_sq)
                if other_piece is None:
                    continue
                
                # Exclude batteries where the other piece is still in its starting position
                # This prevents false positives from captures that happen to align with undeveloped pieces
                if self._is_in_starting_position(other_sq, other_piece.piece_type, color):
                    continue
                
                other_file = chess.square_file(other_sq)
                other_rank = chess.square_rank(other_sq)
                
                # Check if on same file
                if moved_file == other_file:
                    # Both pieces must be able to move along files (rook or queen)
                    if moved_piece_type in [chess.ROOK, chess.QUEEN] and other_piece.piece_type in [chess.ROOK, chess.QUEEN]:
                        # Check if aligned (no pieces blocking)
                        if self._are_aligned(board_after, moved_piece_square, other_sq, "file"):
                            # Check if battery is new (didn't exist before)
                            if not self._battery_existed(board_before, moved_piece_square, other_sq, "file", color, moved_piece_type, moved_piece_before_square):
                                # Check if battery creates a threat and line is open
                                if self._battery_creates_threat(board_after, moved_piece_square, other_sq, "file", color):
                                    if self._line_is_open(board_after, moved_piece_square, other_sq, "file", color):
                                        if self._line_points_toward_opponent(moved_piece_square, other_sq, "file", color):
                                            # Verify battery is actually threatening: require at least one target square in opponent's king area
                                            if self._battery_threatens_king_area(board_after, moved_piece_square, other_sq, "file", color):
                                                file_name = chr(ord('a') + moved_file)
                                                return ("file", f"{file_name} file")
                
                # Check if on same rank
                if moved_rank == other_rank:
                    # Both pieces must be able to move along ranks (rook or queen)
                    if moved_piece_type in [chess.ROOK, chess.QUEEN] and other_piece.piece_type in [chess.ROOK, chess.QUEEN]:
                        # Check if aligned (no pieces blocking)
                        if self._are_aligned(board_after, moved_piece_square, other_sq, "rank"):
                            # Check if battery is new (didn't exist before)
                            if not self._battery_existed(board_before, moved_piece_square, other_sq, "rank", color, moved_piece_type, moved_piece_before_square):
                                # Check if battery creates a threat and line is open
                                if self._battery_creates_threat(board_after, moved_piece_square, other_sq, "rank", color):
                                    if self._line_is_open(board_after, moved_piece_square, other_sq, "rank", color):
                                        if self._line_points_toward_opponent(moved_piece_square, other_sq, "rank", color):
                                            # Verify battery is actually threatening: require at least one target square in opponent's king area
                                            if self._battery_threatens_king_area(board_after, moved_piece_square, other_sq, "rank", color):
                                                rank_name = str(moved_rank + 1)  # Convert 0-based to 1-based
                                                return ("rank", f"{rank_name}th rank")
                
                # Check if on same diagonal
                if abs(moved_file - other_file) == abs(moved_rank - other_rank) and moved_file != other_file:
                    # Both pieces must be able to move along diagonals (bishop or queen)
                    if moved_piece_type in [chess.BISHOP, chess.QUEEN] and other_piece.piece_type in [chess.BISHOP, chess.QUEEN]:
                        # Check if aligned (no pieces blocking)
                        if self._are_aligned(board_after, moved_piece_square, other_sq, "diagonal"):
                            # Check if battery is new (didn't exist before)
                            if not self._battery_existed(board_before, moved_piece_square, other_sq, "diagonal", color, moved_piece_type, moved_piece_before_square):
                                # Check if battery creates a threat
                                if self._battery_creates_threat(board_after, moved_piece_square, other_sq, "diagonal", color):
                                    # Verify battery is actually threatening: require at least one target square in opponent's king area
                                    if self._battery_threatens_king_area(board_after, moved_piece_square, other_sq, "diagonal", color):
                                        diagonal_desc = self._get_diagonal_description(moved_piece_square, other_sq)
                                        return ("diagonal", diagonal_desc)
        
        return None
    
    def _is_in_starting_position(self, square: chess.Square, piece_type: chess.PieceType, color: chess.Color) -> bool:
        """Check if a piece is still in its starting position.
        
        Args:
            square: Square to check.
            piece_type: Type of piece.
            color: Color of the piece.
            
        Returns:
            True if the piece is in its starting position, False otherwise.
        """
        if piece_type == chess.ROOK:
            if color == chess.WHITE:
                return square in [chess.A1, chess.H1]
            else:  # BLACK
                return square in [chess.A8, chess.H8]
        elif piece_type == chess.BISHOP:
            if color == chess.WHITE:
                return square in [chess.C1, chess.F1]
            else:  # BLACK
                return square in [chess.C8, chess.F8]
        elif piece_type == chess.KNIGHT:
            if color == chess.WHITE:
                return square in [chess.B1, chess.G1]
            else:  # BLACK
                return square in [chess.B8, chess.G8]
        # Queens and kings can be in starting position, but we don't exclude them
        # as they can form batteries from starting position (though rare)
        return False
    
    def _are_aligned(self, board: chess.Board, square1: chess.Square, square2: chess.Square, 
                    line_type: str) -> bool:
        """Check if two squares are aligned with no pieces blocking between them.
        
        Args:
            board: Board position.
            square1: First square.
            square2: Second square.
            line_type: "file", "rank", or "diagonal".
            
        Returns:
            True if squares are aligned with no blocking pieces.
        """
        file1 = chess.square_file(square1)
        rank1 = chess.square_rank(square1)
        file2 = chess.square_file(square2)
        rank2 = chess.square_rank(square2)
        
        # Determine direction
        if line_type == "file":
            # Same file, different ranks
            if rank1 == rank2:
                return True  # Same square (shouldn't happen, but handle it)
            df = 0
            dr = 1 if rank2 > rank1 else -1
            start_rank = min(rank1, rank2)
            end_rank = max(rank1, rank2)
        elif line_type == "rank":
            # Same rank, different files
            if file1 == file2:
                return True  # Same square (shouldn't happen, but handle it)
            df = 1 if file2 > file1 else -1
            dr = 0
            start_file = min(file1, file2)
            end_file = max(file1, file2)
        else:  # diagonal
            df = 1 if file2 > file1 else -1
            dr = 1 if rank2 > rank1 else -1
            # For diagonal, check squares between
            dist = abs(file2 - file1)
            if dist <= 1:
                return True  # Adjacent squares, no blocking possible
        
        # Check squares between the two pieces
        # Any piece (same color or opposite color) blocking the line prevents a true battery
        # In chess theory, a battery requires pieces to work together, which is impossible if blocked
        if line_type == "file":
            for rank in range(start_rank + 1, end_rank):
                check_sq = chess.square(file1, rank)
                blocking_piece = board.piece_at(check_sq)
                if blocking_piece is not None:
                    return False  # Blocked by any piece (same color or opposite color)
        elif line_type == "rank":
            for file in range(start_file + 1, end_file):
                check_sq = chess.square(file, rank1)
                blocking_piece = board.piece_at(check_sq)
                if blocking_piece is not None:
                    return False  # Blocked by any piece (same color or opposite color)
        else:  # diagonal
            for dist in range(1, abs(file2 - file1)):
                check_file = file1 + df * dist
                check_rank = rank1 + dr * dist
                check_sq = chess.square(check_file, check_rank)
                blocking_piece = board.piece_at(check_sq)
                if blocking_piece is not None:
                    return False  # Blocked by any piece (same color or opposite color)
        
        return True
    
    def _battery_existed(self, board: chess.Board, square1: chess.Square, square2: chess.Square,
                        line_type: str, color: chess.Color, moved_piece_type: chess.PieceType,
                        moved_piece_before_square: Optional[chess.Square]) -> bool:
        """Check if a battery already existed before the move.
        
        Args:
            board: Board position before the move.
            square1: Square of the moved piece (after move).
            square2: Square of the other piece in the battery (after move).
            line_type: "file", "rank", or "diagonal".
            color: Color of the pieces.
            moved_piece_type: Type of the moved piece.
            moved_piece_before_square: Square where the moved piece was before the move (None if unknown).
            
        Returns:
            True if the battery already existed before the move.
        """
        # Check if piece on square2 existed before (it should, since it's the other piece in the battery)
        piece2_before = board.piece_at(square2)
        if piece2_before is None or piece2_before.color != color:
            return False  # Other piece wasn't there before
        
        # If we know where the moved piece was before, check if that position already formed a battery
        if moved_piece_before_square is not None:
            # Check if the moved piece's previous position and square2 already formed a battery
            if self._on_same_line(moved_piece_before_square, square2, line_type):
                if self._are_aligned(board, moved_piece_before_square, square2, line_type):
                    return True  # Battery existed before with moved piece at its previous position
        
        # Also check if piece was already on destination square before the move
        piece1_before = board.piece_at(square1)
        if piece1_before is not None and piece1_before.color == color and piece1_before.piece_type == moved_piece_type:
            # Piece was already on square1 before - check if it was aligned with square2
            if self._on_same_line(square1, square2, line_type):
                if self._are_aligned(board, square1, square2, line_type):
                    return True  # Battery existed before
        
        return False
    
    def _on_same_line(self, square1: chess.Square, square2: chess.Square, line_type: str) -> bool:
        """Check if two squares are on the same line type.
        
        Args:
            square1: First square.
            square2: Second square.
            line_type: "file", "rank", or "diagonal".
            
        Returns:
            True if squares are on the same line type.
        """
        file1 = chess.square_file(square1)
        rank1 = chess.square_rank(square1)
        file2 = chess.square_file(square2)
        rank2 = chess.square_rank(square2)
        
        if line_type == "file":
            return file1 == file2
        elif line_type == "rank":
            return rank1 == rank2
        else:  # diagonal
            return abs(file1 - file2) == abs(rank1 - rank2) and file1 != file2
    
    def _get_diagonal_description(self, square1: chess.Square, square2: chess.Square) -> str:
        """Get human-readable description of a diagonal.
        
        Args:
            square1: First square (one piece in the battery).
            square2: Second square (other piece in the battery).
            
        Returns:
            Description like "a1-h8 diagonal" showing the full diagonal from edge to edge.
        """
        file1 = chess.square_file(square1)
        rank1 = chess.square_rank(square1)
        file2 = chess.square_file(square2)
        rank2 = chess.square_rank(square2)
        
        # Calculate direction vector
        df = file2 - file1
        dr = rank2 - rank1
        
        # Normalize direction (should be -1, 0, or 1 for each component)
        if df != 0:
            df_norm = df // abs(df)
        else:
            df_norm = 0
        if dr != 0:
            dr_norm = dr // abs(dr)
        else:
            dr_norm = 0
        
        # Find the starting endpoint by extending backwards from both pieces
        # We need to find which piece is closer to the starting edge
        # For a diagonal, we extend in the negative direction of the diagonal vector
        
        # Calculate how far each piece can go backwards
        # Backwards means opposite to the direction vector
        if df_norm > 0:  # Going right, backwards is left
            back_dist1_file = file1
            back_dist2_file = file2
        elif df_norm < 0:  # Going left, backwards is right
            back_dist1_file = 7 - file1
            back_dist2_file = 7 - file2
        else:
            back_dist1_file = 0
            back_dist2_file = 0
        
        if dr_norm > 0:  # Going up, backwards is down
            back_dist1_rank = rank1
            back_dist2_rank = rank2
        elif dr_norm < 0:  # Going down, backwards is up
            back_dist1_rank = 7 - rank1
            back_dist2_rank = 7 - rank2
        else:
            back_dist1_rank = 0
            back_dist2_rank = 0
        
        # For a diagonal, we're limited by the minimum of file and rank distances
        back_dist1 = min(back_dist1_file, back_dist1_rank)
        back_dist2 = min(back_dist2_file, back_dist2_rank)
        
        # Use the piece that can go back further (closer to the starting edge)
        if back_dist1 >= back_dist2:
            start_file = file1 - df_norm * back_dist1
            start_rank = rank1 - dr_norm * back_dist1
        else:
            start_file = file2 - df_norm * back_dist2
            start_rank = rank2 - dr_norm * back_dist2
        
        # Find the ending endpoint by extending forwards from both pieces
        # Forwards means in the same direction as the diagonal vector
        if df_norm > 0:  # Going right, forwards is right
            forward_dist1_file = 7 - file1
            forward_dist2_file = 7 - file2
        elif df_norm < 0:  # Going left, forwards is left
            forward_dist1_file = file1
            forward_dist2_file = file2
        else:
            forward_dist1_file = 0
            forward_dist2_file = 0
        
        if dr_norm > 0:  # Going up, forwards is up
            forward_dist1_rank = 7 - rank1
            forward_dist2_rank = 7 - rank2
        elif dr_norm < 0:  # Going down, forwards is down
            forward_dist1_rank = rank1
            forward_dist2_rank = rank2
        else:
            forward_dist1_rank = 0
            forward_dist2_rank = 0
        
        # For a diagonal, we're limited by the minimum of file and rank distances
        forward_dist1 = min(forward_dist1_file, forward_dist1_rank)
        forward_dist2 = min(forward_dist2_file, forward_dist2_rank)
        
        # Use the piece that can go forward further (closer to the ending edge)
        if forward_dist1 >= forward_dist2:
            end_file = file1 + df_norm * forward_dist1
            end_rank = rank1 + dr_norm * forward_dist1
        else:
            end_file = file2 + df_norm * forward_dist2
            end_rank = rank2 + dr_norm * forward_dist2
        
        # Convert to square names
        start_sq = chess.square(start_file, start_rank)
        end_sq = chess.square(end_file, end_rank)
        
        start_name = chess.square_name(start_sq)
        end_name = chess.square_name(end_sq)
        
        return f"{start_name}-{end_name} diagonal"
    
    def _battery_creates_threat(self, board: chess.Board, square1: chess.Square, square2: chess.Square,
                               line_type: str, color: chess.Color) -> bool:
        """Check if the battery creates a threat by attacking opponent pieces or important squares.
        
        Args:
            board: Board position.
            square1: First square (one piece in the battery).
            square2: Second square (other piece in the battery).
            line_type: "file", "rank", or "diagonal".
            color: Color of the pieces forming the battery.
            
        Returns:
            True if the battery attacks opponent pieces or important squares.
        """
        opponent_color = not color
        file1 = chess.square_file(square1)
        rank1 = chess.square_rank(square1)
        file2 = chess.square_file(square2)
        rank2 = chess.square_rank(square2)
        
        # Determine direction along the line
        if line_type == "file":
            df = 0
            dr = 1 if rank2 > rank1 else -1
            start_rank = min(rank1, rank2)
            end_rank = max(rank1, rank2)
        elif line_type == "rank":
            df = 1 if file2 > file1 else -1
            dr = 0
            start_file = min(file1, file2)
            end_file = max(file1, file2)
        else:  # diagonal
            df = 1 if file2 > file1 else -1
            dr = 1 if rank2 > rank1 else -1
        
        # Check squares along the line beyond the battery pieces
        # We check in both directions from the battery
        
        # Check direction 1: from square1 away from square2
        if line_type == "file":
            # Check ranks beyond square1 (away from square2)
            for rank in range(rank1 + dr, -1 if dr < 0 else 8, dr):
                if rank == rank1 or rank == rank2:
                    continue
                check_sq = chess.square(file1, rank)
                piece = board.piece_at(check_sq)
                if piece is not None:
                    if piece.color == opponent_color:
                        return True  # Attacks opponent piece
                    else:
                        break  # Blocked by friendly piece
                # Check if this is an important square (king area for files)
                if self._is_important_square(check_sq, line_type, opponent_color):
                    return True
        elif line_type == "rank":
            # Check files beyond square1 (away from square2)
            for file in range(file1 + df, -1 if df < 0 else 8, df):
                if file == file1 or file == file2:
                    continue
                check_sq = chess.square(file, rank1)
                piece = board.piece_at(check_sq)
                if piece is not None:
                    if piece.color == opponent_color:
                        return True  # Attacks opponent piece
                    else:
                        break  # Blocked by friendly piece
                # Check if this is an important square
                if self._is_important_square(check_sq, line_type, opponent_color):
                    return True
        else:  # diagonal
            # Check squares beyond square1 (away from square2)
            dist = 1
            while True:
                check_file = file1 + df * dist
                check_rank = rank1 + dr * dist
                if check_file < 0 or check_file > 7 or check_rank < 0 or check_rank > 7:
                    break
                check_sq = chess.square(check_file, check_rank)
                if check_sq == square2:
                    dist += 1
                    continue
                piece = board.piece_at(check_sq)
                if piece is not None:
                    if piece.color == opponent_color:
                        return True  # Attacks opponent piece
                    else:
                        break  # Blocked by friendly piece
                # Check if this is an important square (especially king area)
                if self._is_important_square(check_sq, line_type, opponent_color):
                    return True
                dist += 1
        
        # Check direction 2: from square2 away from square1
        if line_type == "file":
            # Check ranks beyond square2 (away from square1)
            for rank in range(rank2 - dr, -1 if -dr < 0 else 8, -dr):
                if rank == rank1 or rank == rank2:
                    continue
                check_sq = chess.square(file2, rank)
                piece = board.piece_at(check_sq)
                if piece is not None:
                    if piece.color == opponent_color:
                        return True  # Attacks opponent piece
                    else:
                        break  # Blocked by friendly piece
                # Check if this is an important square
                if self._is_important_square(check_sq, line_type, opponent_color):
                    return True
        elif line_type == "rank":
            # Check files beyond square2 (away from square1)
            for file in range(file2 - df, -1 if -df < 0 else 8, -df):
                if file == file1 or file == file2:
                    continue
                check_sq = chess.square(file, rank2)
                piece = board.piece_at(check_sq)
                if piece is not None:
                    if piece.color == opponent_color:
                        return True  # Attacks opponent piece
                    else:
                        break  # Blocked by friendly piece
                # Check if this is an important square
                if self._is_important_square(check_sq, line_type, opponent_color):
                    return True
        else:  # diagonal
            # Check squares beyond square2 (away from square1)
            dist = 1
            while True:
                check_file = file2 - df * dist
                check_rank = rank2 - dr * dist
                if check_file < 0 or check_file > 7 or check_rank < 0 or check_rank > 7:
                    break
                check_sq = chess.square(check_file, check_rank)
                if check_sq == square1:
                    dist += 1
                    continue
                piece = board.piece_at(check_sq)
                if piece is not None:
                    if piece.color == opponent_color:
                        return True  # Attacks opponent piece
                    else:
                        break  # Blocked by friendly piece
                # Check if this is an important square (especially king area)
                if self._is_important_square(check_sq, line_type, opponent_color):
                    return True
                dist += 1
        
        return False
    
    def _is_important_square(self, square: chess.Square, line_type: str, opponent_color: chess.Color) -> bool:
        """Check if a square is important (king area, weak square).
        
        Args:
            square: Square to check.
            line_type: "file", "rank", or "diagonal".
            opponent_color: Color of the opponent.
            
        Returns:
            True if the square is in the opponent's king area or is a weak square.
        """
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        
        # For diagonals, check if square is near opponent's king starting position
        # (e.g., h7 for white king, h2 for black king - common tactical targets)
        if line_type == "diagonal":
            if opponent_color == chess.WHITE:
                # Check squares near white king (e.g., h7, g6, f5)
                if rank >= 5 and file >= 5:
                    return True
            else:  # BLACK
                # Check squares near black king (e.g., h2, g3, f4)
                if rank <= 2 and file >= 5:
                    return True
        
        # For files, check if square is in opponent's back rank area
        if line_type == "file":
            if opponent_color == chess.WHITE:
                # Check ranks 6-7 (near white's back rank)
                if rank >= 6:
                    return True
            else:  # BLACK
                # Check ranks 0-1 (near black's back rank)
                if rank <= 1:
                    return True
        
        # For ranks, check if square is in opponent's king side
        if line_type == "rank":
            if opponent_color == chess.WHITE:
                # Check files f-h (king side)
                if file >= 5:
                    return True
            else:  # BLACK
                # Check files f-h (king side)
                if file >= 5:
                    return True
        
        return False
    
    def _line_is_open(self, board: chess.Board, square1: chess.Square, square2: chess.Square,
                     line_type: str, color: chess.Color) -> bool:
        """Check if a file or rank is open (no friendly pawns blocking).
        
        Args:
            board: Board position.
            square1: First square (one piece in the battery).
            square2: Second square (other piece in the battery).
            line_type: "file" or "rank" (diagonals don't need this check).
            color: Color of the pieces forming the battery.
            
        Returns:
            True if the line is open (no friendly pawns blocking).
        """
        if line_type == "diagonal":
            # Diagonals don't have pawns blocking in the same way
            return True
        
        file1 = chess.square_file(square1)
        rank1 = chess.square_rank(square1)
        file2 = chess.square_file(square2)
        rank2 = chess.square_rank(square2)
        
        if line_type == "file":
            # Check if there are any friendly pawns on this file
            file = file1
            for rank in range(8):
                check_sq = chess.square(file, rank)
                piece = board.piece_at(check_sq)
                if piece and piece.piece_type == chess.PAWN and piece.color == color:
                    return False  # Friendly pawn blocking the file
            return True
        else:  # rank
            # Check if there are any friendly pawns on this rank
            rank = rank1
            for file in range(8):
                check_sq = chess.square(file, rank)
                piece = board.piece_at(check_sq)
                if piece and piece.piece_type == chess.PAWN and piece.color == color:
                    return False  # Friendly pawn blocking the rank
            return True
    
    def _battery_threatens_king_area(self, board: chess.Board, square1: chess.Square, square2: chess.Square,
                                    line_type: str, color: chess.Color) -> bool:
        """Check if battery threatens opponent's king area.
        
        Args:
            board: Board position.
            square1: First square (one piece in the battery).
            square2: Second square (other piece in the battery).
            line_type: "file", "rank", or "diagonal".
            color: Color of the pieces forming the battery.
        
        Returns:
            True if battery threatens at least one square in opponent's king area.
        """
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        file1 = chess.square_file(square1)
        rank1 = chess.square_rank(square1)
        file2 = chess.square_file(square2)
        rank2 = chess.square_rank(square2)
        
        # Determine direction along the line
        if line_type == "file":
            df = 0
            dr = 1 if rank2 > rank1 else -1
        elif line_type == "rank":
            df = 1 if file2 > file1 else -1
            dr = 0
        else:  # diagonal
            df = 1 if file2 > file1 else -1
            dr = 1 if rank2 > rank1 else -1
        
        # Check squares along the line beyond the battery pieces toward opponent's king area
        # Check direction 1: from square1 away from square2
        if line_type == "file":
            for rank in range(rank1 + dr, -1 if dr < 0 else 8, dr):
                if rank == rank1 or rank == rank2:
                    continue
                check_sq = chess.square(file1, rank)
                # Check if this square is in opponent's king area (ranks 6-7 for white, 0-1 for black)
                if opponent_color == chess.WHITE:
                    if rank >= 6:
                        return True
                else:  # BLACK
                    if rank <= 1:
                        return True
        elif line_type == "rank":
            for file in range(file1 + df, -1 if df < 0 else 8, df):
                if file == file1 or file == file2:
                    continue
                check_sq = chess.square(file, rank1)
                # For ranks, check if square is in opponent's king side (files f-h)
                if file >= 5:
                    return True
        else:  # diagonal
            dist = 1
            while True:
                check_file = file1 + df * dist
                check_rank = rank1 + dr * dist
                if check_file < 0 or check_file > 7 or check_rank < 0 or check_rank > 7:
                    break
                check_sq = chess.square(check_file, check_rank)
                if check_sq == square2:
                    dist += 1
                    continue
                # Check if this square is in opponent's king area
                if opponent_color == chess.WHITE:
                    if check_rank >= 5 and check_file >= 5:
                        return True
                else:  # BLACK
                    if check_rank <= 2 and check_file >= 5:
                        return True
                dist += 1
        
        # Check direction 2: from square2 away from square1
        if line_type == "file":
            for rank in range(rank2 - dr, -1 if -dr < 0 else 8, -dr):
                if rank == rank1 or rank == rank2:
                    continue
                check_sq = chess.square(file2, rank)
                if opponent_color == chess.WHITE:
                    if rank >= 6:
                        return True
                else:  # BLACK
                    if rank <= 1:
                        return True
        elif line_type == "rank":
            for file in range(file2 - df, -1 if -df < 0 else 8, -df):
                if file == file1 or file == file2:
                    continue
                check_sq = chess.square(file, rank2)
                if file >= 5:
                    return True
        else:  # diagonal
            dist = 1
            while True:
                check_file = file2 - df * dist
                check_rank = rank2 - dr * dist
                if check_file < 0 or check_file > 7 or check_rank < 0 or check_rank > 7:
                    break
                check_sq = chess.square(check_file, check_rank)
                if check_sq == square1:
                    dist += 1
                    continue
                if opponent_color == chess.WHITE:
                    if check_rank >= 5 and check_file >= 5:
                        return True
                else:  # BLACK
                    if check_rank <= 2 and check_file >= 5:
                        return True
                dist += 1
        
        return False
    
    def _line_points_toward_opponent(self, square1: chess.Square, square2: chess.Square,
                                    line_type: str, color: chess.Color) -> bool:
        """Check if a file or rank points toward the opponent's position.
        
        Args:
            square1: First square (one piece in the battery).
            square2: Second square (other piece in the battery).
            line_type: "file" or "rank" (diagonals always point toward opponent if they create threat).
            color: Color of the pieces forming the battery.
            
        Returns:
            True if the line points toward the opponent's half of the board.
        """
        if line_type == "diagonal":
            # Diagonals that create threats are always meaningful
            return True
        
        file1 = chess.square_file(square1)
        rank1 = chess.square_rank(square1)
        file2 = chess.square_file(square2)
        rank2 = chess.square_rank(square2)
        
        if line_type == "file":
            # For files, at least one piece should be in or past the center
            # White: rank >= 3 (past center), Black: rank <= 4 (past center)
            if color == chess.WHITE:
                return rank1 >= 3 or rank2 >= 3
            else:  # BLACK
                return rank1 <= 4 or rank2 <= 4
        else:  # rank
            # For ranks, the battery should be on a rank that can attack opponent's position
            # White: rank >= 3, Black: rank <= 4
            if color == chess.WHITE:
                return rank1 >= 3
            else:  # BLACK
                return rank1 <= 4

