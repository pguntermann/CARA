"""Rule for detecting decoy tactics (sacrificing material to lure opponent's piece to vulnerable square)."""

from typing import List, Optional, Tuple
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import (
    parse_fen, 
    can_profitably_fork_square,
    can_profitably_skewer_square,
    can_profitably_pin_square,
    check_tactical_pattern_on_follow_up_moves,
    parse_destination_square
)
from app.services.game_highlights.constants import PIECE_VALUES, MATERIAL_SACRIFICE_THRESHOLD


class DecoyRule(HighlightRule):
    """Detects when a move creates a decoy (sacrificing material to lure opponent's piece to vulnerable square)."""
    
    # Minimum value of target piece for a meaningful decoy
    MIN_TARGET_PIECE_VALUE = 300
    
    # Mapping from piece letter to full piece name
    PIECE_NAMES = {
        "p": "pawn",
        "n": "knight",
        "b": "bishop",
        "r": "rook",
        "q": "queen",
        "k": "king"
    }
    
    def _get_piece_name(self, piece_letter: str) -> str:
        """Convert piece letter to full piece name.
        
        Args:
            piece_letter: Single letter piece identifier (p, n, b, r, q, k).
        
        Returns:
            Full piece name (pawn, knight, bishop, rook, queen, king).
        """
        return self.PIECE_NAMES.get(piece_letter.lower(), piece_letter.capitalize())
    
    def _create_decoy_highlight(self, move_num: int, move_notation: str, is_white: bool,
                                piece_name: str, tactical_type: str) -> GameHighlight:
        """Create a GameHighlight for a decoy tactic.
        
        Args:
            move_num: Move number.
            move_notation: Move notation (e.g., "17. Bc4" or "17. ...Rc8").
            is_white: True if white executed the decoy, False if black.
            piece_name: Full name of the lured piece (e.g., "queen", "rook").
            tactical_type: Type of tactical pattern ("fork", "pin", "skewer", "checkmate").
        
        Returns:
            GameHighlight instance.
        """
        side = "White" if is_white else "Black"
        opponent_side = "Black" if is_white else "White"
        tactical_desc = tactical_type.replace("_", " ").title()
        
        if tactical_type == "checkmate":
            description = f"{side} executed a decoy, luring {opponent_side}'s {piece_name} into {tactical_desc}"
        else:
            description = f"{side} executed a decoy, luring {opponent_side}'s {piece_name} away, enabling a {tactical_desc}"
        
        priority = 48 if tactical_type == "checkmate" else 45
        
        return GameHighlight(
            move_number=move_num,
            is_white=is_white,
            move_notation=move_notation,
            description=description,
            priority=priority,
            rule_type="decoy"
        )
    
    def _check_equal_trade_with_tactical_follow_up(self, move, opponent_move, context: RuleContext,
                                                  material_sacrificed: int, captured_value: int,
                                                  cpl: float, color: chess.Color,
                                                  move_num: int) -> Optional[GameHighlight]:
        """Check if an equal trade is followed by a tactical pattern (making it a decoy).
        
        Args:
            move: Current move data (the sacrifice).
            opponent_move: Move where opponent captured.
            context: Rule context.
            material_sacrificed: Material lost by the sacrificing side.
            captured_value: Value of what opponent captured.
            cpl: Centipawn loss of the move.
            color: Color of the sacrificing side.
            move_num: Move number.
        
        Returns:
            GameHighlight if decoy found, None otherwise.
        """
        if material_sacrificed < MATERIAL_SACRIFICE_THRESHOLD or cpl >= context.good_move_max_cpl:
            return None
        
        # Find opponent capture index
        opponent_capture_index = None
        if opponent_move == move:
            # Same move - use current move index
            opponent_capture_index = context.move_index
        else:
            # Different move - search for it
            for i, m in enumerate(context.moves):
                if m == opponent_move:
                    opponent_capture_index = i
                    break
        
        if opponent_capture_index is None or opponent_capture_index + 1 >= len(context.moves):
            return None
        
        # Get board after capture
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        if color == chess.WHITE:
            board_after_capture = parse_fen(opponent_move.fen_black)
            board_before_capture = parse_fen(context.prev_move.fen_white) if context.move_index > 0 and context.prev_move else None
        else:
            board_after_capture = parse_fen(opponent_move.fen_white)
            board_before_capture = parse_fen(context.prev_move.fen_black) if context.move_index > 0 and context.prev_move else None
        
        if not board_after_capture:
            return None
        
        # Find the capturing piece
        captured_piece_square = self._find_capturing_piece(
            board_before_capture,
            board_after_capture,
            opponent_move,
            opponent_color
        )
        
        if not captured_piece_square:
            return None
        
        # Get follow-up moves
        follow_up_moves = []
        for i in range(1, min(3, len(context.moves) - opponent_capture_index)):
            if opponent_capture_index + i < len(context.moves):
                follow_up_moves.append(context.moves[opponent_capture_index + i])
        
        # Check for tactical pattern
        tactical_type = check_tactical_pattern_on_follow_up_moves(
            board_after_capture,
            follow_up_moves,
            captured_piece_square,
            color,
            max_moves_to_check=2
        )
        
        if not tactical_type:
            return None
        
        # Create highlight
        captured_piece = board_after_capture.piece_at(captured_piece_square)
        if not captured_piece:
            return None
        
        piece_name = self._get_piece_name(captured_piece.symbol().lower())
        move_notation = f"{move_num}. {move.white_move}" if color == chess.WHITE else f"{move_num}. ...{move.black_move}"
        
        return self._create_decoy_highlight(move_num, move_notation, color == chess.WHITE, piece_name, tactical_type)
    
    def _check_true_sacrifice_decoy(self, move, opponent_move, context: RuleContext,
                                    material_sacrificed: int, opponent_captured_value: int,
                                    net_material_loss: int, cpl: float, color: chess.Color,
                                    move_num: int) -> Optional[GameHighlight]:
        """Check if a true sacrifice (not an equal trade) creates a decoy.
        
        Args:
            move: Current move data (the sacrifice).
            opponent_move: Move where opponent captured.
            context: Rule context.
            material_sacrificed: Material lost by the sacrificing side.
            opponent_captured_value: Value of what opponent captured.
            net_material_loss: Net material loss after opponent's capture.
            cpl: Centipawn loss of the move.
            color: Color of the sacrificing side.
            move_num: Move number.
        
        Returns:
            GameHighlight if decoy found, None otherwise.
        """
        if (net_material_loss < MATERIAL_SACRIFICE_THRESHOLD or 
            opponent_captured_value <= 0 or 
            cpl >= context.good_move_max_cpl):
            return None
        
        decoy_info = self._is_decoy(move, opponent_move, context, color)
        
        if not decoy_info:
            return None
        
        # Verify decoy actually worked: require opponent's capture move CPL < 30 (opponent was forced to capture)
        opponent_forced_to_capture = False
        if color == chess.WHITE:
            if opponent_move.cpl_black:
                try:
                    opponent_cpl = float(opponent_move.cpl_black)
                    opponent_forced_to_capture = opponent_cpl < 30
                except (ValueError, TypeError):
                    pass
        else:  # BLACK
            if opponent_move.cpl_white:
                try:
                    opponent_cpl = float(opponent_move.cpl_white)
                    opponent_forced_to_capture = opponent_cpl < 30
                except (ValueError, TypeError):
                    pass
        
        if not opponent_forced_to_capture:
            return None
        
        target_piece, tactical_type = decoy_info
        piece_name = self._get_piece_name(target_piece)
        move_notation = f"{move_num}. {move.white_move}" if color == chess.WHITE else f"{move_num}. ...{move.black_move}"
        
        return self._create_decoy_highlight(move_num, move_notation, color == chess.WHITE, piece_name, tactical_type)
    
    def _evaluate_decoy_for_side(self, move, context: RuleContext, is_white: bool) -> List[GameHighlight]:
        """Evaluate decoy for one side (white or black).
        
        Args:
            move: Current move data.
            context: Rule context.
            is_white: True to evaluate white's decoy, False for black's.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        if is_white:
            # Skip if no CPL data or first move
            if context.move_index == 0:
                return highlights
            # Check if CPL data exists (can be "0" for best moves)
            if move.cpl_white is None or move.cpl_white == "":
                return highlights
            try:
                cpl = float(move.cpl_white)
            except (ValueError, TypeError):
                return highlights
            material_sacrificed = context.prev_white_material - move.white_material
            own_capture = move.white_capture
            opponent_capture = move.black_capture
            color = chess.WHITE
            opponent_color = chess.BLACK
        else:
            # Skip if no CPL data or first move
            if context.move_index == 0:
                return highlights
            # Check if CPL data exists (can be "0" for best moves)
            if move.cpl_black is None or move.cpl_black == "":
                return highlights
            try:
                cpl = float(move.cpl_black)
            except (ValueError, TypeError):
                return highlights
            material_sacrificed = context.prev_black_material - move.black_material
            own_capture = move.black_capture
            opponent_capture = move.white_capture
            color = chess.BLACK
            opponent_color = chess.WHITE
        
        try:
            # Early exits: not a sacrifice
            if own_capture or material_sacrificed <= 0:
                return highlights
            
            # Case 1: Opponent captured on same move
            if opponent_capture:
                captured_value = PIECE_VALUES.get(opponent_capture.lower(), 0)
                
                # Check if opponent's material increased (they gained from capturing)
                # If opponent's material increased by approximately the captured value, they captured something we moved there
                # (e.g., we moved a piece there and they captured it - this is a non-capture sacrifice/decoy)
                # If opponent's material didn't increase, they captured something we already had (not a decoy)
                opponent_material_change = 0
                if is_white:
                    opponent_material_change = move.black_material - context.prev_black_material
                else:
                    opponent_material_change = move.white_material - context.prev_white_material
                
                # If opponent's material increased, they captured something we moved there (decoy)
                # If opponent's material decreased, they captured something we already had (not a decoy)
                # If opponent's material stayed same, check if we moved to the capture square
                is_non_capture_sacrifice = False
                if opponent_material_change > 0:
                    is_non_capture_sacrifice = True
                elif opponent_material_change == 0:
                    # Material tracking might not reflect capture immediately
                    # Check if material_sacrificed matches captured_value (we lost what they captured)
                    # AND verify from move notation that we moved a piece to the capture square
                    if abs(material_sacrificed - captured_value) <= 50:
                        # Try to verify from move notation: did we move to the square that got captured?
                        if is_white:
                            our_move = move.white_move
                            opp_move = move.black_move
                        else:
                            our_move = move.black_move
                            opp_move = move.white_move
                        
                        # Extract destination square from our move and opponent's capture
                        dest_square = parse_destination_square(our_move)
                        opp_dest_square = parse_destination_square(opp_move)
                        
                        # If we moved to the same square that opponent captured, it's a decoy
                        if dest_square and opp_dest_square and dest_square == opp_dest_square:
                            is_non_capture_sacrifice = True
                
                if is_non_capture_sacrifice:
                    # Non-capture sacrifice: we moved a piece that opponent captured
                    # The material_sacrificed is what we lost (the piece we moved)
                    # Net material loss = what we lost (since opponent didn't lose anything, or even gained)
                    net_material_loss = material_sacrificed
                    if net_material_loss >= MATERIAL_SACRIFICE_THRESHOLD and cpl < context.good_move_max_cpl:
                        highlight = self._check_true_sacrifice_decoy(
                            move, move, context, material_sacrificed, captured_value,
                            net_material_loss, cpl, color, move_num
                        )
                        if highlight:
                            highlights.append(highlight)
                    return highlights
                
                # If opponent's material didn't increase by the captured value, they captured something we already had
                # This is not a decoy - it's just the opponent capturing something
                if not own_capture:
                    return highlights
                
                # If opponent's material decreased, it's a trade (both sides lost material)
                # Only check for decoy if we also captured (making it a trade with tactical follow-up)
                if not own_capture:
                    # Opponent captured and their material decreased, but we didn't capture
                    # This means opponent captured something we had, and we didn't recapture
                    # This is not a decoy - it's just the opponent capturing something
                    return highlights
                
                # Both sides captured (trade scenario)
                # Equal trade: check for tactical follow-up
                if abs(material_sacrificed - captured_value) <= 50:
                    highlight = self._check_equal_trade_with_tactical_follow_up(
                        move, move, context, material_sacrificed, captured_value, cpl, color, move_num
                    )
                    if highlight:
                        highlights.append(highlight)
                    return highlights
                
                # True sacrifice: material loss > what opponent captured
                if material_sacrificed >= MATERIAL_SACRIFICE_THRESHOLD and cpl < context.good_move_max_cpl:
                    net_material_loss = material_sacrificed - captured_value
                    highlight = self._check_true_sacrifice_decoy(
                        move, move, context, material_sacrificed, captured_value,
                        net_material_loss, cpl, color, move_num
                    )
                    if highlight:
                        highlights.append(highlight)
                    return highlights
            
            # Case 2: No opponent capture on same move - check next move
            if material_sacrificed < MATERIAL_SACRIFICE_THRESHOLD or cpl >= context.good_move_max_cpl:
                return highlights
            
            opponent_move = None
            if context.move_index + 1 < len(context.moves):
                next_move = context.moves[context.move_index + 1]
                if (is_white and next_move.black_capture) or (not is_white and next_move.white_capture):
                    opponent_move = next_move
            
            if opponent_move:
                opponent_captured_value = PIECE_VALUES.get(
                    (opponent_move.black_capture if is_white else opponent_move.white_capture).lower(), 0
                )
                net_material_loss = material_sacrificed - opponent_captured_value if own_capture else material_sacrificed
                
                highlight = self._check_true_sacrifice_decoy(
                    move, opponent_move, context, material_sacrificed, opponent_captured_value,
                    net_material_loss, cpl, color, move_num
                )
                if highlight:
                    highlights.append(highlight)
        
        except (ValueError, TypeError, AttributeError):
            pass
        
        return highlights
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for decoy highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        # Skip decoys in opening phase - they're usually not meaningful
        if move.move_number <= context.opening_end:
            return []
        
        highlights = []
        highlights.extend(self._evaluate_decoy_for_side(move, context, is_white=True))
        highlights.extend(self._evaluate_decoy_for_side(move, context, is_white=False))
        return highlights
    
    def _is_decoy(self, sacrifice_move, opponent_capture_move, context: RuleContext, color: chess.Color) -> Optional[Tuple[str, str]]:
        """Check if a sacrifice creates a decoy by luring opponent's piece to a vulnerable square.
        
        This method now uses helper methods to check if follow-up moves create profitable tactical patterns.
        It only checks actual follow-up moves (not setup), ensuring the tactic is actually executed.
        
        Args:
            sacrifice_move: Move data for the sacrifice.
            opponent_capture_move: Move data for when opponent captured.
            context: Rule context with move history.
            color: Color of the player who sacrificed (WHITE or BLACK).
        
        Returns:
            Tuple of (target_piece_letter, tactical_type) if decoy found, None otherwise.
            target_piece_letter: Letter of the piece that was lured (e.g., "q", "r", "k").
            tactical_type: Type of tactical pattern ("fork", "pin", "checkmate", "skewer").
        """
        opponent_color = chess.BLACK if color == chess.WHITE else chess.WHITE
        
        # Get board positions
        # Need to determine which board positions to use based on when the capture happened
        if color == chess.WHITE:
            board_after_sacrifice = parse_fen(sacrifice_move.fen_white)
            # If opponent captured on same move, use black's FEN from same move
            # If opponent captured on next move, use black's FEN from next move
            if opponent_capture_move == sacrifice_move:
                board_after_capture = parse_fen(opponent_capture_move.fen_black)
                board_before_capture = board_after_sacrifice
            else:
                board_after_capture = parse_fen(opponent_capture_move.fen_black)
                # Board before capture is the position after sacrifice (white's FEN)
                board_before_capture = board_after_sacrifice
        else:
            board_after_sacrifice = parse_fen(sacrifice_move.fen_black)
            if opponent_capture_move == sacrifice_move:
                board_after_capture = parse_fen(opponent_capture_move.fen_white)
                board_before_capture = board_after_sacrifice
            else:
                board_after_capture = parse_fen(opponent_capture_move.fen_white)
                board_before_capture = board_after_sacrifice
        
        if not board_after_sacrifice or not board_after_capture or not board_before_capture:
            return None
        
        # Find which piece captured (the piece that was lured)
        captured_piece_square = self._find_capturing_piece(
            board_before_capture, board_after_capture, opponent_capture_move, opponent_color
        )
        
        if captured_piece_square is None:
            return None
        
        captured_piece = board_after_capture.piece_at(captured_piece_square)
        if captured_piece is None:
            return None
        
        captured_piece_letter = captured_piece.symbol().lower()
        captured_piece_value = PIECE_VALUES.get(captured_piece_letter, 0)
        
        # Only meaningful if captured piece is valuable (>= 300cp) or is the king
        is_king = (captured_piece.piece_type == chess.KING)
        if captured_piece_value < self.MIN_TARGET_PIECE_VALUE and not is_king:
            return None
        
        # IMPORTANT: Verify this is a true decoy, not a direct tactical move
        # A decoy requires the tactical pattern to appear AFTER the opponent captures,
        # not immediately after the sacrifice. We verify this by checking that the
        # tactical pattern exists on the board_after_capture (after opponent captures),
        # not on board_after_sacrifice (before opponent captures).
        # The captured_piece_square is where the opponent's piece is AFTER capturing,
        # so checking tactical patterns there ensures it's a true decoy.
        
        # Check if the captured piece is now vulnerable to a tactical pattern
        # Find the move index where the opponent captured
        opponent_capture_index = None
        if opponent_capture_move == sacrifice_move:
            # Same move - use current move index
            opponent_capture_index = context.move_index
        else:
            # Different move - search for it
            for i, m in enumerate(context.moves):
                if m == opponent_capture_move:
                    opponent_capture_index = i
                    break
        
        # Check on the move(s) after the opponent's capture (if they exist)
        # IMPORTANT: Only check actual follow-up moves to ensure the tactic is executed, not just that it exists
        if opponent_capture_index is not None and opponent_capture_index + 1 < len(context.moves):
            # Get follow-up moves (check up to 2 moves ahead)
            follow_up_moves = []
            for i in range(1, min(3, len(context.moves) - opponent_capture_index)):
                if opponent_capture_index + i < len(context.moves):
                    follow_up_moves.append(context.moves[opponent_capture_index + i])
            
            # Check if any follow-up move creates a profitable tactical pattern
            tactical_type = check_tactical_pattern_on_follow_up_moves(
                board_after_capture,
                follow_up_moves,
                captured_piece_square,
                color,
                max_moves_to_check=2
            )
            
            if tactical_type:
                return (captured_piece_letter, tactical_type)
        
        return None
    
    def _find_capturing_piece(self, board_before: chess.Board, board_after: chess.Board,
                              capture_move, capturing_color: chess.Color) -> Optional[chess.Square]:
        """Find the square of the piece that captured.
        
        Args:
            board_before: Board position before the capture.
            board_after: Board position after the capture.
            capture_move: Move data for the capture.
            capturing_color: Color of the capturing side.
        
        Returns:
            Square of the capturing piece, or None if not found.
        """
        try:
            # Parse destination square from move notation
            if capturing_color == chess.WHITE:
                move_san = capture_move.white_move
            else:
                move_san = capture_move.black_move
            
            if not move_san:
                return None
            
            dest_part = move_san
            if "=" in dest_part:
                dest_part = dest_part.split("=")[0]
            if "+" in dest_part:
                dest_part = dest_part.replace("+", "")
            if "#" in dest_part:
                dest_part = dest_part.replace("#", "")
            
            # Extract square after "x"
            if "x" in dest_part:
                parts = dest_part.split("x")
                if len(parts) > 1:
                    dest_part = parts[-1]
            
            if len(dest_part) >= 2:
                dest_square = chess.parse_square(dest_part[-2:])
                
                # Find which piece moved to this square by comparing positions
                # Check all piece types
                for piece_type in [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]:
                    pieces_before = list(board_before.pieces(piece_type, capturing_color))
                    pieces_after = list(board_after.pieces(piece_type, capturing_color))
                    
                    # Find piece that disappeared from before position and is now on destination
                    for sq in pieces_before:
                        if sq not in pieces_after:
                            # This piece moved - verify it's now on destination square
                            if dest_square in pieces_after or board_after.piece_at(dest_square) == chess.Piece(piece_type, capturing_color):
                                return dest_square
                    
                    # Handle promotions (piece count increases)
                    if len(pieces_after) > len(pieces_before):
                        if dest_square in pieces_after:
                            return dest_square
                
                # Fallback: if destination square has a piece of the right color, assume that's it
                piece_at_dest = board_after.piece_at(dest_square)
                if piece_at_dest and piece_at_dest.color == capturing_color:
                    return dest_square
        except (ValueError, AttributeError):
            pass
        return None

