"""Rule for detecting pawn breaks."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen, is_central_square
from app.services.game_highlights.constants import PIECE_VALUES


class PawnBreakRule(HighlightRule):
    """Detects central pawn breaks."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for pawn break highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Fact #10: Pawn break
        if move.white_move and len(move.white_move) >= 2 and move.white_move[0].islower():
            is_pawn_capture = (
                "x" in move.white_move and
                move.white_capture == "p"
            )
            if is_pawn_capture:
                # Check if this is an immediate equal pawn recapture (pawn for pawn)
                is_equal_pawn_recapture = False
                
                # Check if opponent recaptures on the same turn with a pawn
                if move.black_capture == "p":
                    captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
                    captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
                    if abs(captured_by_white - captured_by_black) <= 50:
                        is_equal_pawn_recapture = True
                
                # Check if opponent recaptures on next move with a pawn
                if not is_equal_pawn_recapture and context.next_move and context.next_move.black_capture == "p":
                    captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
                    captured_by_black = PIECE_VALUES.get(context.next_move.black_capture.lower(), 0)
                    if abs(captured_by_white - captured_by_black) <= 50:
                        is_equal_pawn_recapture = True
                
                # Skip if it's a simple equal pawn exchange
                if not is_equal_pawn_recapture:
                    board_after = parse_fen(move.fen_white)
                    if board_after and context.prev_move and context.prev_move.fen_black:
                        board_before = parse_fen(context.prev_move.fen_black)
                        
                        if board_before:
                            dest_part = move.white_move[-2:] if "=" not in move.white_move else move.white_move.split("=")[0][-2:]
                            try:
                                dest_square = chess.parse_square(dest_part)
                                if is_central_square(dest_square):
                                    dest_file = chess.square_file(dest_square)
                                    dest_rank = chess.square_rank(dest_square)
                                    
                                    # Find the pawn that moved
                                    white_pawns_before = list(board_before.pieces(chess.PAWN, chess.WHITE))
                                    white_pawns_after = list(board_after.pieces(chess.PAWN, chess.WHITE))
                                    
                                    source_square = None
                                    for sq in white_pawns_before:
                                        if sq not in white_pawns_after:
                                            source_square = sq
                                            break
                                    
                                    if source_square:
                                        source_rank = chess.square_rank(source_square)
                                        # Verify pawn advanced forward (rank increased for white)
                                        if dest_rank > source_rank:
                                            # Verify break creates threats: opens file/rank for rooks OR creates passed pawn
                                            break_creates_threat = False
                                            # Check if file is now open (no pawns of either color on this file)
                                            file_is_open = self._is_file_open(board_after, dest_file)
                                            # Check if this creates a passed pawn
                                            creates_passed_pawn = self._creates_passed_pawn(board_after, dest_square, chess.WHITE)
                                            break_creates_threat = file_is_open or creates_passed_pawn
                                            
                                            if break_creates_threat:
                                                highlights.append(GameHighlight(
                                                    move_number=move_num,
                                                    is_white=True,
                                                    move_notation=f"{move_num}. {move.white_move}",
                                                    description="White executed a central pawn break",
                                                    priority=25,
                                                    rule_type="pawn_break"
                                                ))
                            except (ValueError, AttributeError):
                                pass
        
        if move.black_move and len(move.black_move) >= 2 and move.black_move[0].islower():
            is_pawn_capture = (
                "x" in move.black_move and
                move.black_capture == "p"
            )
            if is_pawn_capture:
                # Check if this is an immediate equal pawn recapture (pawn for pawn)
                is_equal_pawn_recapture = False
                
                # Check if opponent recaptures on the same turn with a pawn
                if move.white_capture == "p":
                    captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
                    captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
                    if abs(captured_by_black - captured_by_white) <= 50:
                        is_equal_pawn_recapture = True
                
                # Check if opponent recaptures on next move with a pawn
                if not is_equal_pawn_recapture and context.next_move and context.next_move.white_capture == "p":
                    captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
                    captured_by_white = PIECE_VALUES.get(context.next_move.white_capture.lower(), 0)
                    if abs(captured_by_black - captured_by_white) <= 50:
                        is_equal_pawn_recapture = True
                
                # Skip if it's a simple equal pawn exchange
                if not is_equal_pawn_recapture:
                    board_after = parse_fen(move.fen_black)
                    if board_after and move.fen_white:
                        board_before = parse_fen(move.fen_white)
                        
                        if board_before:
                            dest_part = move.black_move[-2:] if "=" not in move.black_move else move.black_move.split("=")[0][-2:]
                            try:
                                dest_square = chess.parse_square(dest_part)
                                if is_central_square(dest_square):
                                    dest_file = chess.square_file(dest_square)
                                    dest_rank = chess.square_rank(dest_square)
                                    
                                    black_pawns_before = list(board_before.pieces(chess.PAWN, chess.BLACK))
                                    black_pawns_after = list(board_after.pieces(chess.PAWN, chess.BLACK))
                                    
                                    source_square = None
                                    for sq in black_pawns_before:
                                        if sq not in black_pawns_after:
                                            source_square = sq
                                            break
                                    
                                    if source_square:
                                        source_rank = chess.square_rank(source_square)
                                        # Verify pawn advanced forward (rank decreased for black)
                                        if dest_rank < source_rank:
                                            # Verify break creates threats: opens file/rank for rooks OR creates passed pawn
                                            break_creates_threat = False
                                            # Check if file is now open (no pawns of either color on this file)
                                            file_is_open = self._is_file_open(board_after, dest_file)
                                            # Check if this creates a passed pawn
                                            creates_passed_pawn = self._creates_passed_pawn(board_after, dest_square, chess.BLACK)
                                            break_creates_threat = file_is_open or creates_passed_pawn
                                            
                                            if break_creates_threat:
                                                highlights.append(GameHighlight(
                                                    move_number=move_num,
                                                    is_white=False,
                                                    move_notation=f"{move_num}. ...{move.black_move}",
                                                    description="Black executed a central pawn break",
                                                    priority=25,
                                                    rule_type="pawn_break"
                                                ))
                            except (ValueError, AttributeError):
                                pass
        
        return highlights
    
    def _is_file_open(self, board: chess.Board, file: int) -> bool:
        """Check if a file is open (no pawns of either color on this file).
        
        Args:
            board: Board position.
            file: File to check (0-7).
        
        Returns:
            True if file is open, False otherwise.
        """
        white_pawns = board.pieces(chess.PAWN, chess.WHITE)
        black_pawns = board.pieces(chess.PAWN, chess.BLACK)
        
        has_white_pawns = any(chess.square_file(sq) == file for sq in white_pawns)
        has_black_pawns = any(chess.square_file(sq) == file for sq in black_pawns)
        
        # File is open if no pawns of either color
        return not has_white_pawns and not has_black_pawns
    
    def _creates_passed_pawn(self, board: chess.Board, pawn_square: chess.Square, color: chess.Color) -> bool:
        """Check if a pawn is a passed pawn (no enemy pawns in front on same or adjacent files).
        
        Args:
            board: Board position.
            pawn_square: Square of the pawn.
            color: Color of the pawn.
        
        Returns:
            True if pawn is passed, False otherwise.
        """
        pawn_file = chess.square_file(pawn_square)
        pawn_rank = chess.square_rank(pawn_square)
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        
        # Check for enemy pawns on same file ahead
        for rank in range(pawn_rank + 1, 8) if color == chess.WHITE else range(pawn_rank - 1, -1, -1):
            check_sq = chess.square(pawn_file, rank)
            piece = board.piece_at(check_sq)
            if piece and piece.piece_type == chess.PAWN and piece.color == opponent_color:
                return False  # Enemy pawn on same file ahead
        
        # Check for enemy pawns on adjacent files ahead
        for adj_file in [pawn_file - 1, pawn_file + 1]:
            if adj_file < 0 or adj_file > 7:
                continue
            for rank in range(pawn_rank + 1, 8) if color == chess.WHITE else range(pawn_rank - 1, -1, -1):
                check_sq = chess.square(adj_file, rank)
                piece = board.piece_at(check_sq)
                if piece and piece.piece_type == chess.PAWN and piece.color == opponent_color:
                    return False  # Enemy pawn on adjacent file ahead
        
        return True  # No enemy pawns in path

