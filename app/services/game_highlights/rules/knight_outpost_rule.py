"""Rule for detecting knight outposts (knight on advanced square that cannot be attacked by pawns)."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen


class KnightOutpostRule(HighlightRule):
    """Detects when a knight moves to an outpost (advanced square that cannot be attacked by pawns)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for knight outpost highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's knight outpost
        # Exclude capture moves - outposts are positional, not tactical
        if move.white_move and ("N" in move.white_move or move.white_move.startswith("N")) and not move.white_capture:
            board_after = parse_fen(move.fen_white)
            if board_after and context.prev_move and context.prev_move.fen_black:
                board_before = parse_fen(context.prev_move.fen_black)
                if board_before:
                    knight_square = self._find_knight_square(board_after, chess.WHITE, move.white_move)
                    if knight_square is not None:
                        if self._is_knight_outpost(board_after, knight_square, chess.WHITE):
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=True,
                                move_notation=f"{move_num}. {move.white_move}",
                                description="White established a knight outpost",
                                priority=26,
                                rule_type="knight_outpost"
                            ))
        
        # Black's knight outpost
        # Exclude capture moves - outposts are positional, not tactical
        if move.black_move and ("N" in move.black_move or move.black_move.startswith("N")) and not move.black_capture:
            board_after = parse_fen(move.fen_black)
            if board_after and move.fen_white:
                board_before = parse_fen(move.fen_white)
                if board_before:
                    knight_square = self._find_knight_square(board_after, chess.BLACK, move.black_move)
                    if knight_square is not None:
                        if self._is_knight_outpost(board_after, knight_square, chess.BLACK):
                            highlights.append(GameHighlight(
                                move_number=move_num,
                                is_white=False,
                                move_notation=f"{move_num}. ...{move.black_move}",
                                description="Black established a knight outpost",
                                priority=26,
                                rule_type="knight_outpost"
                            ))
        
        return highlights
    
    def _find_knight_square(self, board: chess.Board, color: chess.Color, move_san: str):
        """Find the knight square from move notation."""
        try:
            dest_part = move_san
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
                piece_at_dest = board.piece_at(dest_square)
                if piece_at_dest and piece_at_dest.piece_type == chess.KNIGHT and piece_at_dest.color == color:
                    return dest_square
        except (ValueError, AttributeError):
            pass
        return None
    
    def _is_knight_outpost(self, board: chess.Board, knight_square: chess.Square, color: chess.Color) -> bool:
        """Check if knight is on an outpost (advanced square that cannot be attacked by opponent's pawns).
        
        An outpost square must:
        - Be protected by friendly pawns (REQUIRED)
        - Cannot be attacked by enemy pawns (current or potential)
        - Be on an advanced rank (opponent's side of the board)
        - Not be on edge files (a/h)
        """
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        knight_file = chess.square_file(knight_square)
        knight_rank = chess.square_rank(knight_square)
        
        # Outposts are typically not on edge files (a/h)
        # Edge files are less valuable for outposts
        if knight_file == 0 or knight_file == 7:
            return False
        
        # Check if knight is in opponent's half
        # For white: ranks 4-7 (0-indexed: ranks 3-6)
        # For black: ranks 1-4 (0-indexed: ranks 0-3)
        if color == chess.WHITE:
            if knight_rank < 3:  # Not in black's half (ranks 0-2 are white's side)
                return False
        else:  # BLACK
            if knight_rank > 3:  # Not in white's half (ranks 4-7 are black's side)
                return False
        
        # REQUIRED: Outpost must be protected by friendly pawns
        # This is a defining characteristic of an outpost square
        if not self._is_protected_by_pawns(board, knight_file, knight_rank, color):
            return False
        
        # Check if square can be attacked by opponent's pawns (current position)
        if self._can_be_attacked_by_pawns(board, knight_file, knight_rank, opponent_color):
            return False
        
        # Check if square can be attacked by opponent's pawns advancing
        # This is critical - if an enemy pawn can advance to attack the square, it's not an outpost
        if self._can_be_attacked_by_advancing_pawns(board, knight_file, knight_rank, opponent_color):
            return False
        
        return True
    
    def _is_protected_by_pawns(self, board: chess.Board, file: int, rank: int, color: chess.Color) -> bool:
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
    
    def _can_be_attacked_by_pawns(self, board: chess.Board, file: int, rank: int, color: chess.Color) -> bool:
        """Check if a square can be attacked by pawns of the given color (current position).
        
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
    
    def _can_be_attacked_by_advancing_pawns(self, board: chess.Board, file: int, rank: int, color: chess.Color) -> bool:
        """Check if a square can be attacked by enemy pawns that can advance.
        
        This checks if enemy pawns on the same file or adjacent files can advance
        to attack the square. This is important for outpost detection - if a pawn
        can advance to attack the square, it's not a true outpost.
        
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
            # Check same file - if there's a white pawn on the same file on a higher rank,
            # it can advance to attack this square diagonally
            if rank < 7:
                for pawn_rank in range(rank + 1, 8):
                    pawn_square = chess.square(file, pawn_rank)
                    if pawn_square in enemy_pawns:
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
            # Check same file - if there's a black pawn on the same file on a lower rank,
            # it can advance to attack this square diagonally
            if rank > 0:
                for pawn_rank in range(rank - 1, -1, -1):
                    pawn_square = chess.square(file, pawn_rank)
                    if pawn_square in enemy_pawns:
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

