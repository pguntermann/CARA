"""Rule for detecting discovered attacks."""

from typing import List, Optional, Tuple
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen
from app.services.game_highlights.constants import PIECE_VALUES


class DiscoveredAttackRule(HighlightRule):
    """Detects when a move creates a discovered attack (moving a piece reveals an attack by another piece behind it)."""
    
    # Minimum value of target piece for a meaningful discovered attack
    MIN_TARGET_PIECE_VALUE = 300
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for discovered attack highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # Skip discovered attacks in opening phase - they're usually not meaningful
        if move_num <= context.opening_end:
            return highlights
        
        # Check if current move is a simple recapture with equal material
        # This prevents false positives from simple recaptures
        is_simple_recapture = False
        if move.white_capture and move.black_capture:
            captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
            captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
            if abs(captured_by_white - captured_by_black) <= 50:
                is_simple_recapture = True
        
        if not is_simple_recapture and context.prev_move:
            if move.white_capture and context.prev_move.black_capture:
                captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
                captured_by_black = PIECE_VALUES.get(context.prev_move.black_capture.lower(), 0)
                if abs(captured_by_white - captured_by_black) <= 50:
                    is_simple_recapture = True
            if move.black_capture and context.prev_move.white_capture:
                captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
                captured_by_white = PIECE_VALUES.get(context.prev_move.white_capture.lower(), 0)
                if abs(captured_by_black - captured_by_white) <= 50:
                    is_simple_recapture = True
        
        if not is_simple_recapture and context.next_move:
            if move.white_capture and context.next_move.black_capture:
                captured_by_white = PIECE_VALUES.get(move.white_capture.lower(), 0)
                captured_by_black = PIECE_VALUES.get(context.next_move.black_capture.lower(), 0)
                if abs(captured_by_white - captured_by_black) <= 50:
                    is_simple_recapture = True
            if move.black_capture and context.next_move.white_capture:
                captured_by_black = PIECE_VALUES.get(move.black_capture.lower(), 0)
                captured_by_white = PIECE_VALUES.get(context.next_move.white_capture.lower(), 0)
                if abs(captured_by_black - captured_by_white) <= 50:
                    is_simple_recapture = True
        
        # White's discovered attack
        if move.white_move and move.cpl_white and context.move_index > 0 and not is_simple_recapture:
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
                                discovered_info = self._has_discovered_attack(board_before, board_after, moved_piece_square, chess.WHITE)
                                if discovered_info:
                                    target_piece, is_check, target_value, is_undefended = discovered_info
                                    # Verify discovered attack is meaningful: require target >=300cp AND (undefended OR check)
                                    if target_piece and target_value >= self.MIN_TARGET_PIECE_VALUE and (is_undefended or is_check):
                                        piece_name = target_piece.capitalize() if target_piece != "p" else "pawn"
                                        if is_check:
                                            description = f"White performed a discovered attack on Black's king"
                                            priority = 45
                                        else:
                                            description = f"White performed a discovered attack on Black's {piece_name}"
                                            priority = 40
                                        highlights.append(GameHighlight(
                                            move_number=move_num,
                                            is_white=True,
                                            move_notation=f"{move_num}. {move.white_move}",
                                            description=description,
                                            priority=priority,
                                            rule_type="discovered_attack"
                                        ))
            except (ValueError, TypeError, AttributeError):
                pass
        
        # Black's discovered attack
        if move.black_move and move.cpl_black and not is_simple_recapture:
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
                                discovered_info = self._has_discovered_attack(board_before, board_after, moved_piece_square, chess.BLACK)
                                if discovered_info:
                                    target_piece, is_check, target_value, is_undefended = discovered_info
                                    # Verify discovered attack is meaningful: require target >=300cp AND (undefended OR check)
                                    if target_piece and target_value >= self.MIN_TARGET_PIECE_VALUE and (is_undefended or is_check):
                                        piece_name = target_piece.capitalize() if target_piece != "p" else "pawn"
                                        if is_check:
                                            description = f"Black performed a discovered attack on White's king"
                                            priority = 45
                                        else:
                                            description = f"Black performed a discovered attack on White's {piece_name}"
                                            priority = 40
                                        highlights.append(GameHighlight(
                                            move_number=move_num,
                                            is_white=False,
                                            move_notation=f"{move_num}. ...{move.black_move}",
                                            description=description,
                                            priority=priority,
                                            rule_type="discovered_attack"
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
    
    def _find_source_square(self, dest_square: chess.Square, board_before: chess.Board,
                           board_after: chess.Board, color: chess.Color) -> Optional[chess.Square]:
        """Find the source square of a moved piece.
        
        Args:
            dest_square: Destination square of the move.
            board_before: Board position before the move.
            board_after: Board position after the move.
            color: Color of the moving side.
        
        Returns:
            Source square of the moved piece, or None if not found.
        """
        piece_at_dest = board_after.piece_at(dest_square)
        if piece_at_dest is None or piece_at_dest.color != color:
            return None
        
        piece_type = piece_at_dest.piece_type
        
        # Find which piece of this type moved
        pieces_before = list(board_before.pieces(piece_type, color))
        pieces_after = list(board_after.pieces(piece_type, color))
        
        for sq in pieces_before:
            if sq not in pieces_after:
                # This piece moved - verify it's now on destination
                if dest_square in pieces_after:
                    return sq
        
        return None
    
    def _has_discovered_attack(self, board_before: chess.Board, board_after: chess.Board,
                              moved_piece_square: chess.Square, color: chess.Color) -> Optional[Tuple[str, bool, int, bool]]:
        """Check if moving a piece creates a discovered attack.
        
        Args:
            board_before: Board position before the move.
            board_after: Board position after the move.
            moved_piece_square: Square of the piece after it moved.
            color: Color of the moving side.
        
        Returns:
            Tuple of (target_piece_letter, is_check, target_value, is_undefended) if discovered attack found, None otherwise.
            target_piece_letter: Letter of the piece being attacked (e.g., "q", "r", "k").
            is_check: True if the discovered attack delivers check.
            target_value: Value of the target piece in centipawns.
            is_undefended: True if the target piece is undefended.
        """
        # Find the source square of the moved piece
        source_square = self._find_source_square(moved_piece_square, board_before, board_after, color)
        if source_square is None:
            return None
        
        # Check if there's a piece behind the source square that now attacks an enemy piece
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        
        # Calculate the direction of movement (from source to destination)
        source_file = chess.square_file(source_square)
        source_rank = chess.square_rank(source_square)
        dest_file = chess.square_file(moved_piece_square)
        dest_rank = chess.square_rank(moved_piece_square)
        
        move_df = dest_file - source_file
        move_dr = dest_rank - source_rank
        
        # Only check the direction opposite to movement (behind the source square)
        # Normalize direction to unit vector
        if move_df != 0:
            move_df = move_df // abs(move_df)
        if move_dr != 0:
            move_dr = move_dr // abs(move_dr)
        
        # Look behind the source square (opposite direction from movement)
        # This is the direction where a piece might be that was blocked by the moved piece
        behind_df = -move_df
        behind_dr = -move_dr
        
        # Only check if there's actual movement (not a null move)
        if behind_df == 0 and behind_dr == 0:
            return False
        
        # Look along the "behind" direction for a sliding piece
        for dist in range(1, 8):
            file = source_file + behind_df * dist
            rank = source_rank + behind_dr * dist
            
            if file < 0 or file > 7 or rank < 0 or rank > 7:
                break
            
            sq = chess.square(file, rank)
            sq_piece = board_before.piece_at(sq)
            
            if sq_piece is None:
                continue
            
            if sq_piece.color != color:
                # Enemy piece blocks the ray
                break
            
            # Our piece found - check if it's a sliding piece that can now attack
            if sq_piece.piece_type in [chess.ROOK, chess.BISHOP, chess.QUEEN]:
                # Check if this direction is valid for the piece type
                if sq_piece.piece_type == chess.ROOK and (behind_df != 0 and behind_dr != 0):
                    continue
                if sq_piece.piece_type == chess.BISHOP and (behind_df == 0 or behind_dr == 0):
                    continue
                
                # CRITICAL: Verify that the moved piece was actually blocking an attack
                # Check if the piece behind attacks a valuable piece AFTER the move
                # AND that this attack was blocked by the moved piece BEFORE the move
                attack_info = self._attacks_valuable_piece(board_after, sq, sq_piece.piece_type, opponent_color)
                if attack_info:
                    target_piece_letter, is_check, target_square = attack_info
                    # Verify the attack was blocked before: check if there's a valuable piece
                    # on the same line that the moved piece was blocking
                    if self._was_attack_blocked(board_before, source_square, sq, sq_piece.piece_type, opponent_color, behind_df, behind_dr):
                        # Get target value and check if undefended
                        target_value = PIECE_VALUES.get(target_piece_letter, 0)
                        if target_piece_letter == "k":
                            target_value = 900  # King is special case
                        is_undefended = not board_after.is_attacked_by(opponent_color, target_square) if target_square is not None else False
                        # Additional meaningfulness check: ensure the discovered attack is meaningful
                        if self._is_meaningful_discovered_attack(board_after, sq, target_piece_letter, opponent_color, is_check):
                            return (target_piece_letter, is_check, target_value, is_undefended)
        
        return None
    
    def _attacks_valuable_piece(self, board: chess.Board, attacker_square: chess.Square,
                               piece_type: chess.PieceType, opponent_color: chess.Color) -> Optional[Tuple[str, bool, chess.Square]]:
        """Check if a piece attacks a valuable enemy piece.
        
        Args:
            board: Board position.
            attacker_square: Square of the attacking piece.
            piece_type: Type of the attacking piece.
            opponent_color: Color of the opponent.
        
        Returns:
            Tuple of (target_piece_letter, is_check, target_square) if attacks valuable piece, None otherwise.
            target_piece_letter: Letter of the piece being attacked (e.g., "q", "r", "k").
            is_check: True if the attack delivers check.
            target_square: Square of the target piece.
        """
        attacker_file = chess.square_file(attacker_square)
        attacker_rank = chess.square_rank(attacker_square)
        
        directions = [
            (1, 0), (-1, 0), (0, 1), (0, -1),  # Rook directions
            (1, 1), (1, -1), (-1, 1), (-1, -1)  # Bishop directions
        ]
        
        for df, dr in directions:
            # Check if this direction is valid for the piece type
            if piece_type == chess.ROOK and (df != 0 and dr != 0):
                continue
            if piece_type == chess.BISHOP and (df == 0 or dr == 0):
                continue
            
            # Look along this ray for enemy pieces
            for dist in range(1, 8):
                file = attacker_file + df * dist
                rank = attacker_rank + dr * dist
                
                if file < 0 or file > 7 or rank < 0 or rank > 7:
                    break
                
                sq = chess.square(file, rank)
                sq_piece = board.piece_at(sq)
                
                if sq_piece is None:
                    continue
                
                if sq_piece.color == opponent_color:
                    # Enemy piece found - check if it's valuable
                    piece_letter = sq_piece.symbol().lower()
                    piece_value = PIECE_VALUES.get(piece_letter, 0)
                    is_check = (sq_piece.piece_type == chess.KING)
                    # Check if it's valuable (>= 300cp) or if it's the king (check)
                    if piece_value >= self.MIN_TARGET_PIECE_VALUE or is_check:
                        return (piece_letter, is_check, sq)
                    # Even if not valuable, this piece blocks the ray - can't attack beyond it
                    break
                else:
                    # Our own piece blocks the ray
                    break
        
        return None
    
    def _was_attack_blocked(self, board: chess.Board, blocker_square: chess.Square,
                           attacker_square: chess.Square, piece_type: chess.PieceType,
                           opponent_color: chess.Color, direction_df: int, direction_dr: int) -> bool:
        """Check if the blocker was actually blocking an attack from the attacker.
        
        This verifies that the blocker is on the same line as the attacker's attack,
        and that there's a valuable piece behind the blocker that the attacker can now reach.
        
        Args:
            board: Board position before the move.
            blocker_square: Square of the piece that was blocking (the moved piece).
            attacker_square: Square of the piece that might have been blocked.
            piece_type: Type of the attacking piece.
            opponent_color: Color of the opponent.
            direction_df: File direction from attacker to blocker (normalized).
            direction_dr: Rank direction from attacker to blocker (normalized).
        
        Returns:
            True if the blocker was actually blocking a valuable piece attack.
        """
        attacker_file = chess.square_file(attacker_square)
        attacker_rank = chess.square_rank(attacker_square)
        blocker_file = chess.square_file(blocker_square)
        blocker_rank = chess.square_rank(blocker_square)
        
        # Verify blocker is on the same line as attacker in the given direction
        # Calculate actual direction from attacker to blocker
        att_to_block_df = blocker_file - attacker_file
        att_to_block_dr = blocker_rank - attacker_rank
        
        # Normalize to unit vector
        if att_to_block_df != 0:
            att_to_block_df_norm = att_to_block_df // abs(att_to_block_df)
        else:
            att_to_block_df_norm = 0
        if att_to_block_dr != 0:
            att_to_block_dr_norm = att_to_block_dr // abs(att_to_block_dr)
        else:
            att_to_block_dr_norm = 0
        
        # Check if normalized direction matches the expected direction
        if att_to_block_df_norm != direction_df or att_to_block_dr_norm != direction_dr:
            return False
        
        # Check if direction is valid for piece type
        if piece_type == chess.ROOK and (direction_df != 0 and direction_dr != 0):
            return False
        if piece_type == chess.BISHOP and (direction_df == 0 or direction_dr == 0):
            return False
        
        # Continue past the blocker in the same direction to find the target
        # The target should be behind the blocker, in the same direction as attacker->blocker
        for dist in range(1, 8):
            file = blocker_file + direction_df * dist
            rank = blocker_rank + direction_dr * dist
            
            if file < 0 or file > 7 or rank < 0 or rank > 7:
                break
            
            sq = chess.square(file, rank)
            sq_piece = board.piece_at(sq)
            
            if sq_piece is None:
                continue
            
            if sq_piece.color == opponent_color:
                # Enemy piece found behind the blocker - this is the target
                piece_letter = sq_piece.symbol().lower()
                piece_value = PIECE_VALUES.get(piece_letter, 0)
                is_king = (sq_piece.piece_type == chess.KING)
                # Check if it's valuable (>= 300cp) or if it's the king (check)
                if piece_value >= self.MIN_TARGET_PIECE_VALUE or is_king:
                    # Verify the attacker can actually attack this target along this line
                    # by checking if attacker, blocker, and target are collinear
                    target_file = chess.square_file(sq)
                    target_rank = chess.square_rank(sq)
                    
                    # Calculate direction from attacker to target
                    att_to_targ_df = target_file - attacker_file
                    att_to_targ_dr = target_rank - attacker_rank
                    
                    # Normalize
                    if att_to_targ_df != 0:
                        att_to_targ_df_norm = att_to_targ_df // abs(att_to_targ_df)
                    else:
                        att_to_targ_df_norm = 0
                    if att_to_targ_dr != 0:
                        att_to_targ_dr_norm = att_to_targ_dr // abs(att_to_targ_dr)
                    else:
                        att_to_targ_dr_norm = 0
                    
                    # Attacker, blocker, and target must be on the same line
                    if att_to_targ_df_norm == direction_df and att_to_targ_dr_norm == direction_dr:
                        return True
            else:
                # Our own piece blocks the ray
                break
        
        return False
    
    def _is_meaningful_discovered_attack(self, board: chess.Board, attacker_square: chess.Square,
                                        target_piece_letter: str, opponent_color: chess.Color, is_check: bool) -> bool:
        """Check if a discovered attack is meaningful (not trivial).
        
        A discovered attack is meaningful if:
        - It delivers check (always meaningful)
        - It targets an undefended piece
        - It targets a piece more valuable than the moving piece
        
        Args:
            board: Board position after the move.
            attacker_square: Square of the discovering piece.
            target_piece_letter: Letter of the target piece (e.g., "q", "r").
            opponent_color: Color of the opponent.
            is_check: True if the discovered attack delivers check.
        
        Returns:
            True if the discovered attack is meaningful.
        """
        # Check is always meaningful
        if is_check:
            return True
        
        # Find the target piece on the board
        target_piece_type_map = {
            "q": chess.QUEEN,
            "r": chess.ROOK,
            "b": chess.BISHOP,
            "n": chess.KNIGHT,
            "p": chess.PAWN
        }
        target_piece_type = target_piece_type_map.get(target_piece_letter)
        if target_piece_type is None:
            return False
        
        # Find all opponent pieces of this type
        target_pieces = list(board.pieces(target_piece_type, opponent_color))
        
        # Check if any target piece is undefended or in an important square
        attacker_file = chess.square_file(attacker_square)
        attacker_rank = chess.square_rank(attacker_square)
        
        directions = [
            (1, 0), (-1, 0), (0, 1), (0, -1),  # Rook directions
            (1, 1), (1, -1), (-1, 1), (-1, -1)  # Bishop directions
        ]
        
        attacker_piece = board.piece_at(attacker_square)
        if attacker_piece is None:
            return False
        
        attacker_piece_type = attacker_piece.piece_type
        attacker_color = attacker_piece.color
        
        for df, dr in directions:
            # Check if this direction is valid for the piece type
            if attacker_piece_type == chess.ROOK and (df != 0 and dr != 0):
                continue
            if attacker_piece_type == chess.BISHOP and (df == 0 or dr == 0):
                continue
            
            # Look along this ray for target pieces
            for dist in range(1, 8):
                file = attacker_file + df * dist
                rank = attacker_rank + dr * dist
                
                if file < 0 or file > 7 or rank < 0 or rank > 7:
                    break
                
                sq = chess.square(file, rank)
                sq_piece = board.piece_at(sq)
                
                if sq_piece is None:
                    continue
                
                if sq_piece.color == opponent_color and sq_piece.piece_type == target_piece_type:
                    # Found target piece - check if it's meaningful
                    # Check if target is undefended (not defended by opponent's pieces)
                    if not board.is_attacked_by(opponent_color, sq):
                        return True  # Undefended piece - meaningful
                    
                    # Check if target is more valuable than attacker
                    target_value = PIECE_VALUES.get(target_piece_letter, 0)
                    attacker_letter = attacker_piece.symbol().lower()
                    attacker_value = PIECE_VALUES.get(attacker_letter, 0)
                    if target_value > attacker_value:
                        return True  # More valuable target - meaningful
                    
                    # Check if target is on an important square (king area)
                    if self._is_important_square(sq, opponent_color):
                        return True
                    
                    # This target piece blocks the ray - can't attack beyond it
                    break
                else:
                    # Our own piece or different piece blocks the ray
                    break
        
        return False
    
    def _is_important_square(self, square: chess.Square, opponent_color: chess.Color) -> bool:
        """Check if a square is important (near opponent's king).
        
        Args:
            square: Square to check.
            opponent_color: Color of the opponent.
        
        Returns:
            True if the square is near the opponent's king.
        """
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        
        if opponent_color == chess.WHITE:
            # Check squares near white king (ranks 6-7, files f-h)
            if rank >= 6 and file >= 5:
                return True
        else:  # BLACK
            # Check squares near black king (ranks 0-1, files f-h)
            if rank <= 1 and file >= 5:
                return True
        
        return False

