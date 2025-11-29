"""Rule for detecting isolated pawns."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen


class IsolatedPawnRule(HighlightRule):
    """Detects when a pawn becomes isolated (no friendly pawns on adjacent files)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for isolated pawn highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's isolated pawn
        if move.white_move and len(move.white_move) >= 2 and move.white_move[0].islower():
            board_after = parse_fen(move.fen_white)
            if board_after and context.prev_move and context.prev_move.fen_black:
                board_before = parse_fen(context.prev_move.fen_black)
                if board_before:
                    isolated_pawns = self._find_new_isolated_pawns(board_before, board_after, chess.WHITE)
                    if isolated_pawns:
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=True,
                            move_notation=f"{move_num}. {move.white_move}",
                            description="White created an isolated pawn",
                            priority=21,
                            rule_type="isolated_pawn"
                        ))
        
        # Black's isolated pawn
        if move.black_move and len(move.black_move) >= 2 and move.black_move[0].islower():
            board_after = parse_fen(move.fen_black)
            if board_after and move.fen_white:
                board_before = parse_fen(move.fen_white)
                if board_before:
                    isolated_pawns = self._find_new_isolated_pawns(board_before, board_after, chess.BLACK)
                    if isolated_pawns:
                        highlights.append(GameHighlight(
                            move_number=move_num,
                            is_white=False,
                            move_notation=f"{move_num}. ...{move.black_move}",
                            description="Black created an isolated pawn",
                            priority=21,
                            rule_type="isolated_pawn"
                        ))
        
        return highlights
    
    def _find_new_isolated_pawns(self, board_before: chess.Board, board_after: chess.Board, 
                                 color: chess.Color) -> List[chess.Square]:
        """Find pawns that became isolated after the move."""
        pawns_before = list(board_before.pieces(chess.PAWN, color))
        pawns_after = list(board_after.pieces(chess.PAWN, color))
        
        new_isolated = []
        
        # Check all pawns that exist after the move
        for pawn_sq in pawns_after:
            pawn_file = chess.square_file(pawn_sq)
            
            # Check if pawn was isolated before
            was_isolated_before = self._is_isolated(pawns_before, pawn_file)
            
            # Check if pawn is isolated after
            is_isolated_after = self._is_isolated(pawns_after, pawn_file)
            
            # If it became isolated (wasn't before, is now)
            if not was_isolated_before and is_isolated_after:
                new_isolated.append(pawn_sq)
        
        # Also check if a pawn was removed that made remaining pawns isolated
        for pawn_sq_before in pawns_before:
            if pawn_sq_before not in pawns_after:
                # A pawn was removed - check if remaining pawns became isolated
                removed_file = chess.square_file(pawn_sq_before)
                for pawn_sq_after in pawns_after:
                    pawn_file = chess.square_file(pawn_sq_after)
                    # Check if this pawn is on adjacent file to removed pawn
                    if abs(pawn_file - removed_file) == 1:
                        # Check if this pawn is now isolated
                        if self._is_isolated(pawns_after, pawn_file):
                            if pawn_sq_after not in new_isolated:
                                new_isolated.append(pawn_sq_after)
        
        return new_isolated
    
    def _is_isolated(self, pawns: List[chess.Square], file: int) -> bool:
        """Check if a pawn on the given file is isolated."""
        # Check adjacent files
        adjacent_files = [file - 1, file + 1]
        
        for adj_file in adjacent_files:
            if adj_file < 0 or adj_file > 7:
                continue
            
            # Check if there's a pawn on this adjacent file
            for pawn_sq in pawns:
                if chess.square_file(pawn_sq) == adj_file:
                    return False  # Not isolated, has adjacent pawn
        
        return True  # Isolated, no pawns on adjacent files

