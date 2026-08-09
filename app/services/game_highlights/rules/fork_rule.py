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
        if move.white_move and move.cpl_white is not None and move.cpl_white != "" and context.move_index > 0:
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
                                if self._is_fork(
                                    board_after, moved_piece_square, chess.WHITE
                                ):
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
        if move.black_move and move.cpl_black is not None and move.cpl_black != "":
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
                                if self._is_fork(
                                    board_after, moved_piece_square, chess.BLACK
                                ):
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
    
    def _is_fork(
        self,
        board: chess.Board,
        piece_square: chess.Square,
        color: chess.Color,
    ) -> bool:
        """Check if a piece on the given square creates a fork.

        A fork requires attacking two or more enemy pieces after the move.
        Capturing an undefended piece with check is not itself a fork — the
        captured unit is gone (e.g. Rxf4+ only checks the king afterward).

        Exploitable forks include:
        - undefended target worth more than the forker
        - forker cheaper than every valuable target (up after a recapture)
        - royal fork that also attacks free material still on the board
          (e.g. Nxc7+ checks the king and attacks an undefended pawn on a6)
        """
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        piece = board.piece_at(piece_square)
        if piece is None or piece.color != color:
            return False

        # Forker safety / cheap elimination:
        # - Hanging forker (not defended by its own side) that the opponent can capture
        #   is not an exploitable fork — they simply take it (e.g. Bxc3 hanging to Qxc3).
        # - If the forker is defended, equal-or-lesser capturers can still trade out cheaply.
        piece_letter = piece.symbol().lower()
        attacker_value = PIECE_VALUES.get(piece_letter, 0)
        forker_defended = board.is_attacked_by(color, piece_square)
        opponent_attackers = list(board.attackers(opponent_color, piece_square))

        if opponent_attackers and not forker_defended:
            return False

        if forker_defended:
            for attacker_sq in opponent_attackers:
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
                target_letter = enemy_piece.symbol().lower()
                piece_value = PIECE_VALUES.get(target_letter, 0)

                if enemy_piece.piece_type == chess.KING:
                    attacks_king = True
                    continue

                defended = board.is_attacked_by(opponent_color, sq)
                # Free loot of any value (including pawns) for royal-fork material.
                if piece_value >= 100 and not defended:
                    undefended_free_count += 1
                    if piece_value > attacker_value:
                        undefended_higher_value_count += 1

                # Valuable pieces (>= 300cp: bishop/knight/rook/queen)
                if piece_value >= 300:
                    valuable_values.append(piece_value)

        # Fork requires attacking at least 2 enemy pieces after the move.
        if len(enemy_pieces) < 2:
            return False

        # Royal fork: king + valuable piece, or king + free material still on board.
        # Standard fork: ≥2 valuable pieces.
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

