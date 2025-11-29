"""Rule for detecting forks."""

from typing import List, Optional
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen
from app.services.game_highlights.constants import PIECE_VALUES


class ForkRule(HighlightRule):
    """Detects when a move creates a fork (attacking two or more enemy pieces simultaneously)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for fork highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's fork
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
                                if self._is_fork(board_after, moved_piece_square, chess.WHITE):
                                    # Verify fork actually caused good CPL: check if CPL < 30 AND PV2/PV3 CPL > 50
                                    fork_was_best = cpl < 30
                                    if fork_was_best and move.cpl_white_2 and move.cpl_white_3:
                                        try:
                                            cpl_2 = float(move.cpl_white_2)
                                            cpl_3 = float(move.cpl_white_3)
                                            # If 2nd and 3rd best moves have high CPL (>50), fork was clearly best option
                                            if cpl_2 > 50 and cpl_3 > 50:
                                                fork_was_best = True
                                            else:
                                                fork_was_best = False
                                        except (ValueError, TypeError):
                                            pass  # Fall back to basic check if PV2/PV3 data unavailable
                                    
                                    if fork_was_best:
                                        highlights.append(GameHighlight(
                                            move_number=move_num,
                                            is_white=True,
                                            move_notation=f"{move_num}. {move.white_move}",
                                            description="White executed a fork",
                                            priority=45,
                                            rule_type="fork"
                                        ))
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Black's fork
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
                                if self._is_fork(board_after, moved_piece_square, chess.BLACK):
                                    # Verify fork actually caused good CPL: check if CPL < 30 AND PV2/PV3 CPL > 50
                                    fork_was_best = cpl < 30
                                    if fork_was_best and move.cpl_black_2 and move.cpl_black_3:
                                        try:
                                            cpl_2 = float(move.cpl_black_2)
                                            cpl_3 = float(move.cpl_black_3)
                                            # If 2nd and 3rd best moves have high CPL (>50), fork was clearly best option
                                            if cpl_2 > 50 and cpl_3 > 50:
                                                fork_was_best = True
                                            else:
                                                fork_was_best = False
                                        except (ValueError, TypeError):
                                            pass  # Fall back to basic check if PV2/PV3 data unavailable
                                    
                                    if fork_was_best:
                                        highlights.append(GameHighlight(
                                            move_number=move_num,
                                            is_white=False,
                                            move_notation=f"{move_num}. ...{move.black_move}",
                                            description="Black executed a fork",
                                            priority=45,
                                            rule_type="fork"
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
                # Check all piece types
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
    
    def _is_fork(self, board: chess.Board, piece_square: chess.Square, color: chess.Color) -> bool:
        """Check if a piece on the given square creates a fork.
        
        Args:
            board: Board position after the move.
            piece_square: Square of the piece to check.
            color: Color of the piece.
        
        Returns:
            True if the piece forks two or more enemy pieces, with at least one undefended or net material gain.
        """
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        piece = board.piece_at(piece_square)
        if piece is None or piece.color != color:
            return False
        
        # Check if the attacking piece can be captured by an equal or less valuable piece
        # If so, the fork is not exploitable (opponent can just trade)
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
                    # If opponent can capture with equal or less valuable piece, fork is not exploitable
                    if attacker_piece_value <= attacker_value:
                        can_be_captured_by_equal_or_less = True
                        break
        
        if can_be_captured_by_equal_or_less:
            return False
        
        # Get all squares attacked by this piece
        attacked_squares = board.attacks(piece_square)
        
        # Find enemy pieces on attacked squares
        enemy_pieces = []
        valuable_pieces = []
        undefended_valuable_count = 0
        attacks_king = False
        
        for sq in attacked_squares:
            enemy_piece = board.piece_at(sq)
            if enemy_piece and enemy_piece.color == opponent_color:
                enemy_pieces.append((sq, enemy_piece))
                piece_letter = enemy_piece.symbol().lower()
                piece_value = PIECE_VALUES.get(piece_letter, 0)
                
                # Check if this is the king (special case for forks)
                if enemy_piece.piece_type == chess.KING:
                    attacks_king = True
                
                # Track valuable pieces (>= 300cp: bishop/knight/rook/queen)
                if piece_value >= 300:
                    valuable_pieces.append(sq)
                    # Check if this valuable piece is undefended (not defended by opponent's own pieces)
                    if not board.is_attacked_by(opponent_color, sq):
                        undefended_valuable_count += 1
        
        # Fork requires attacking at least 2 enemy pieces
        if len(enemy_pieces) < 2:
            return False
        
        # Special case: Fork that includes the king (check) + at least one valuable piece
        # This is a very powerful tactical pattern and should be recognized
        if attacks_king and len(valuable_pieces) >= 1:
            # If the valuable piece is undefended, it's a clear fork
            if undefended_valuable_count == len(valuable_pieces):
                return True
        
        # Standard fork: at least 2 valuable pieces (>= 300cp), all undefended
        # This ensures the fork is actually exploitable (opponent can't save both pieces)
        if len(valuable_pieces) >= 2 and undefended_valuable_count == len(valuable_pieces):
            return True
        
        return False

