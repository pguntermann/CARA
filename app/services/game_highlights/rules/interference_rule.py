"""Rule for detecting interference (blocking opponent's piece coordination)."""

from typing import List, Optional
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen
from app.services.game_highlights.constants import PIECE_VALUES


class InterferenceRule(HighlightRule):
    """Detects when a move blocks opponent's piece coordination by inserting piece between them."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for interference highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's interference
        # Interference is about placing a piece between two enemy pieces, not capturing
        if move.white_move and move.cpl_white and context.move_index > 0 and not move.white_capture:
            try:
                cpl = float(move.cpl_white)
                if cpl < context.good_move_max_cpl:
                    board_after = parse_fen(move.fen_white)
                    if board_after and context.prev_move and context.prev_move.fen_black:
                        board_before = parse_fen(context.prev_move.fen_black)
                        if board_before:
                            moved_piece_square = self._find_moved_piece_square(
                                move.white_move, board_before, board_after, chess.WHITE
                            )
                            if moved_piece_square is not None:
                                if self._creates_interference(board_before, board_after, moved_piece_square, chess.WHITE):
                                    highlights.append(GameHighlight(
                                        move_number=move_num,
                                        is_white=True,
                                        move_notation=f"{move_num}. {move.white_move}",
                                        description="White created interference",
                                        priority=38,
                                        rule_type="interference"
                                    ))
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Black's interference
        # Interference is about placing a piece between two enemy pieces, not capturing
        if move.black_move and move.cpl_black and not move.black_capture:
            try:
                cpl = float(move.cpl_black)
                if cpl < context.good_move_max_cpl:
                    board_after = parse_fen(move.fen_black)
                    if board_after and move.fen_white:
                        board_before = parse_fen(move.fen_white)
                        if board_before:
                            moved_piece_square = self._find_moved_piece_square(
                                move.black_move, board_before, board_after, chess.BLACK
                            )
                            if moved_piece_square is not None:
                                if self._creates_interference(board_before, board_after, moved_piece_square, chess.BLACK):
                                    highlights.append(GameHighlight(
                                        move_number=move_num,
                                        is_white=False,
                                        move_notation=f"{move_num}. ...{move.black_move}",
                                        description="Black created interference",
                                        priority=38,
                                        rule_type="interference"
                                    ))
            except (ValueError, TypeError, AttributeError):
                pass
        
        return highlights
    
    def _find_moved_piece_square(self, move_san: str, board_before: chess.Board, 
                                 board_after: chess.Board, color: chess.Color) -> Optional[chess.Square]:
        """Find the square of the piece that moved."""
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
                dest_square = chess.parse_square(dest_part[-2:])
                piece_at_dest = board_after.piece_at(dest_square)
                if piece_at_dest and piece_at_dest.color == color:
                    return dest_square
        except (ValueError, AttributeError):
            pass
        return None
    
    def _creates_interference(self, board_before: chess.Board, board_after: chess.Board,
                             moved_square: chess.Square, color: chess.Color) -> bool:
        """Check if the moved piece creates interference between opponent's pieces.
        
        Interference requires:
        1. The move is NOT a capture (interference is about placing a piece, not removing one)
        2. Two opponent pieces are on the same line (rank, file, or diagonal)
        3. There was a CLEAR PATH between these two pieces BEFORE the move
        4. The moved piece is placed BETWEEN these two pieces, blocking their coordination
        """
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        
        # CRITICAL: Interference is about PLACING a piece between two enemy pieces,
        # not removing one. If the destination square had an opponent piece before
        # (i.e., it's a capture), this is NOT interference.
        piece_before_on_square = board_before.piece_at(moved_square)
        if piece_before_on_square and piece_before_on_square.color == opponent_color:
            return False  # This is a capture, not interference
        
        # Check if moved piece is between two opponent pieces on the same line
        moved_file = chess.square_file(moved_square)
        moved_rank = chess.square_rank(moved_square)
        
        # Check all directions (file, rank, diagonals)
        directions = [
            (1, 0), (-1, 0), (0, 1), (0, -1),  # Rook directions
            (1, 1), (1, -1), (-1, 1), (-1, -1)  # Bishop directions
        ]
        
        for df, dr in directions:
            # Find opponent pieces on this line BEFORE the move
            opponent_pieces_before = []
            
            # Check direction 1 (positive)
            for dist in range(1, 8):
                file = moved_file + df * dist
                rank = moved_rank + dr * dist
                if file < 0 or file > 7 or rank < 0 or rank > 7:
                    break
                sq = chess.square(file, rank)
                piece_before = board_before.piece_at(sq)
                if piece_before and piece_before.color == opponent_color:
                    opponent_pieces_before.append(sq)
                elif piece_before:
                    break  # Any piece (ours or opponent's) blocks the line
            
            # Check direction 2 (negative)
            for dist in range(1, 8):
                file = moved_file - df * dist
                rank = moved_rank - dr * dist
                if file < 0 or file > 7 or rank < 0 or rank > 7:
                    break
                sq = chess.square(file, rank)
                piece_before = board_before.piece_at(sq)
                if piece_before and piece_before.color == opponent_color:
                    opponent_pieces_before.append(sq)
                elif piece_before:
                    break  # Any piece (ours or opponent's) blocks the line
            
            # Need at least two opponent pieces on this line
            if len(opponent_pieces_before) < 2:
                continue
            
            # Check if there was a CLEAR PATH between any two of these pieces BEFORE the move
            # (i.e., they could see each other)
            for i, piece1 in enumerate(opponent_pieces_before):
                for piece2 in opponent_pieces_before[i+1:]:
                    # Verify pieces are valuable (>= 300cp)
                    piece1_obj = board_before.piece_at(piece1)
                    piece2_obj = board_before.piece_at(piece2)
                    if not piece1_obj or not piece2_obj:
                        continue
                    
                    if piece1_obj.piece_type not in (chess.ROOK, chess.BISHOP, chess.QUEEN):
                        continue
                    if piece2_obj.piece_type not in (chess.ROOK, chess.BISHOP, chess.QUEEN):
                        continue
                    
                    piece1_value = PIECE_VALUES.get(piece1_obj.symbol().lower(), 0)
                    piece2_value = PIECE_VALUES.get(piece2_obj.symbol().lower(), 0)
                    
                    if piece1_value < 300 and piece2_value < 300:
                        continue  # Not valuable enough
                    
                    # Check if there was a clear path between piece1 and piece2 BEFORE the move
                    if not self._has_clear_path_before(board_before, piece1, piece2, moved_square, df, dr):
                        continue
                    
                    # Check if moved piece is placed BETWEEN piece1 and piece2
                    if self._is_between_on_line(moved_square, piece1, piece2, df, dr):
                        return True
        
        return False
    
    def _has_clear_path_before(self, board_before: chess.Board, piece1: chess.Square,
                               piece2: chess.Square, moved_square: chess.Square,
                               df: int, dr: int) -> bool:
        """Check if there was a clear path between piece1 and piece2 BEFORE the move.
        
        This verifies that the two pieces could see each other (were coordinating)
        before the interference move was made.
        """
        p1_file = chess.square_file(piece1)
        p1_rank = chess.square_rank(piece1)
        p2_file = chess.square_file(piece2)
        p2_rank = chess.square_rank(piece2)
        moved_file = chess.square_file(moved_square)
        moved_rank = chess.square_rank(moved_square)
        
        # Determine the direction from piece1 to piece2
        if df == 0:  # Vertical line
            if p1_file != p2_file:
                return False
            start_rank = min(p1_rank, p2_rank)
            end_rank = max(p1_rank, p2_rank)
            # Check all squares between piece1 and piece2
            for rank in range(start_rank + 1, end_rank):
                sq = chess.square(p1_file, rank)
                # If there was a piece on this square before (other than the moved piece's square),
                # the path was not clear
                if sq != moved_square and board_before.piece_at(sq) is not None:
                    return False
            return True
        elif dr == 0:  # Horizontal line
            if p1_rank != p2_rank:
                return False
            start_file = min(p1_file, p2_file)
            end_file = max(p1_file, p2_file)
            # Check all squares between piece1 and piece2
            for file in range(start_file + 1, end_file):
                sq = chess.square(file, p1_rank)
                if sq != moved_square and board_before.piece_at(sq) is not None:
                    return False
            return True
        else:  # Diagonal
            # Check if they're on the same diagonal
            if abs(p1_file - p2_file) != abs(p1_rank - p2_rank):
                return False
            
            file_step = 1 if p2_file > p1_file else -1
            rank_step = 1 if p2_rank > p1_rank else -1
            
            file = p1_file + file_step
            rank = p1_rank + rank_step
            
            # Check all squares between piece1 and piece2
            while file != p2_file and rank != p2_rank:
                sq = chess.square(file, rank)
                if sq != moved_square and board_before.piece_at(sq) is not None:
                    return False
                file += file_step
                rank += rank_step
            
            return True
    
    def _is_between_on_line(self, square: chess.Square, piece1: chess.Square, 
                            piece2: chess.Square, df: int, dr: int) -> bool:
        """Check if square is between piece1 and piece2 on the given line."""
        sq_file = chess.square_file(square)
        sq_rank = chess.square_rank(square)
        p1_file = chess.square_file(piece1)
        p1_rank = chess.square_rank(piece1)
        p2_file = chess.square_file(piece2)
        p2_rank = chess.square_rank(piece2)
        
        # Check if square is on the line between piece1 and piece2
        if df == 0:  # Vertical line
            if sq_file == p1_file == p2_file:
                return min(p1_rank, p2_rank) < sq_rank < max(p1_rank, p2_rank)
        elif dr == 0:  # Horizontal line
            if sq_rank == p1_rank == p2_rank:
                return min(p1_file, p2_file) < sq_file < max(p1_file, p2_file)
        else:  # Diagonal
            # Check if square is on the same diagonal
            if abs(sq_file - p1_file) == abs(sq_rank - p1_rank) and abs(sq_file - p2_file) == abs(sq_rank - p2_rank):
                return (min(p1_file, p2_file) < sq_file < max(p1_file, p2_file) and
                        min(p1_rank, p2_rank) < sq_rank < max(p1_rank, p2_rank))
        
        return False

