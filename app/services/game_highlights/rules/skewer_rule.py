"""Rule for detecting skewers."""

from typing import List, Optional
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen
from app.services.game_highlights.constants import PIECE_VALUES


class SkewerRule(HighlightRule):
    """Detects when a move creates a skewer (attacking a valuable piece, forcing it to move and exposing a less valuable piece behind it)."""
    
    # Minimum material difference between pieces for a meaningful skewer
    MIN_SKEWER_MATERIAL_DIFF = 200
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for skewer highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's skewer
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
                                if self._is_skewer(board_after, moved_piece_square, chess.WHITE):
                                    highlights.append(GameHighlight(
                                        move_number=move_num,
                                        is_white=True,
                                        move_notation=f"{move_num}. {move.white_move}",
                                        description="White executed a skewer",
                                        priority=40,
                                        rule_type="skewer"
                                    ))
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Black's skewer
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
                                if self._is_skewer(board_after, moved_piece_square, chess.BLACK):
                                    highlights.append(GameHighlight(
                                        move_number=move_num,
                                        is_white=False,
                                        move_notation=f"{move_num}. ...{move.black_move}",
                                        description="Black executed a skewer",
                                        priority=40,
                                        rule_type="skewer"
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
    
    def _is_skewer(self, board: chess.Board, piece_square: chess.Square, color: chess.Color) -> bool:
        """Check if a piece on the given square creates a skewer.
        
        Args:
            board: Board position after the move.
            piece_square: Square of the piece to check.
            color: Color of the piece.
        
        Returns:
            True if the piece creates a skewer (attacks valuable piece with less valuable piece behind it).
        """
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        piece = board.piece_at(piece_square)
        if piece is None or piece.color != color:
            return False
        
        # Only sliding pieces (rook, bishop, queen) can create skewers
        if piece.piece_type not in [chess.ROOK, chess.BISHOP, chess.QUEEN]:
            return False
        
        # Check if the attacking piece can be captured by an equal or less valuable piece
        # If so, the skewer is not exploitable (opponent can just trade)
        piece_letter = piece.symbol().lower()
        attacker_value = PIECE_VALUES.get(piece_letter, 0)
        can_be_captured_by_equal_or_less = False
        
        if board.is_attacked_by(opponent_color, piece_square):
            # Check all pieces attacking this square
            for attacker_sq in board.attackers(opponent_color, piece_square):
                attacker_piece = board.piece_at(attacker_sq)
                if attacker_piece:
                    attacker_piece_letter = attacker_piece.symbol().lower()
                    attacker_piece_value = PIECE_VALUES.get(attacker_piece_letter, 0)
                    # If opponent can capture with equal or less valuable piece, skewer is not exploitable
                    if attacker_piece_value <= attacker_value:
                        can_be_captured_by_equal_or_less = True
                        break
        
        if can_be_captured_by_equal_or_less:
            return False
        
        # Check all directions from the piece
        directions = [
            (1, 0), (-1, 0), (0, 1), (0, -1),  # Rook directions
            (1, 1), (1, -1), (-1, 1), (-1, -1)  # Bishop directions
        ]
        
        piece_file = chess.square_file(piece_square)
        piece_rank = chess.square_rank(piece_square)
        
        for df, dr in directions:
            # Check if this direction is valid for the piece type
            if piece.piece_type == chess.ROOK and (df != 0 and dr != 0):
                continue
            if piece.piece_type == chess.BISHOP and (df == 0 or dr == 0):
                continue
            
            # Look along this ray for enemy pieces
            first_piece_square = None
            first_piece_value = 0
            first_piece_distance = 0
            second_piece_square = None
            second_piece_value = 0
            
            for dist in range(1, 8):
                file = piece_file + df * dist
                rank = piece_rank + dr * dist
                
                if file < 0 or file > 7 or rank < 0 or rank > 7:
                    break
                
                sq = chess.square(file, rank)
                sq_piece = board.piece_at(sq)
                
                if sq_piece is None:
                    continue
                
                if sq_piece.color == color:
                    # Our own piece blocks the ray
                    break
                
                # Enemy piece found
                if first_piece_square is None:
                    first_piece_square = sq
                    first_piece_distance = dist
                    piece_letter = sq_piece.symbol().lower()
                    first_piece_value = PIECE_VALUES.get(piece_letter, 0)
                elif second_piece_square is None:
                    second_piece_square = sq
                    piece_letter = sq_piece.symbol().lower()
                    second_piece_value = PIECE_VALUES.get(piece_letter, 0)
                    break
            
            # Check if we have a skewer: valuable piece in front, less valuable piece behind
            # A skewer is only meaningful if:
            # 1. The valuable piece in front is undefended (or can be forced to move)
            # 2. The valuable piece is at least 2 squares away (not directly adjacent)
            # 3. The less valuable piece behind is UNDEFENDED (so it can be captured after the front piece moves)
            # 4. Verify meaningful skewer: front piece >=500cp AND back piece >=300cp
            if first_piece_square is not None and second_piece_square is not None:
                if first_piece_value >= second_piece_value + self.MIN_SKEWER_MATERIAL_DIFF:
                    # Verify meaningful skewer: front piece >=500cp AND back piece >=300cp
                    if first_piece_value >= 500 and second_piece_value >= 300:
                        # Check if the valuable piece in front is undefended
                        if not board.is_attacked_by(opponent_color, first_piece_square):
                            # Require the first piece to be at least 2 squares away
                            # (A skewer requires the valuable piece to be further away, not directly adjacent)
                            if first_piece_distance >= 2:
                                # CRITICAL: The piece behind must be undefended
                                # If it's defended, moving the front piece doesn't allow capture of the back piece
                                # Therefore, it's not a true skewer
                                if not board.is_attacked_by(opponent_color, second_piece_square):
                                    return True
        
        return False

