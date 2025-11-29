"""Rule for detecting piece centralization."""

from typing import List
import chess

from app.services.game_highlights.base_rule import HighlightRule, GameHighlight, RuleContext
from app.services.game_highlights.helpers import parse_fen, is_central_square


class CentralizationRule(HighlightRule):
    """Detects when a piece is centralized (moves to center from non-central square)."""
    
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move for centralization highlights.
        
        Args:
            move: Current move data.
            context: Rule context.
        
        Returns:
            List of GameHighlight instances.
        """
        highlights = []
        move_num = move.move_number
        
        # White's centralization
        if move.white_move and context.move_index > 0:
            board_after = parse_fen(move.fen_white)
            if board_after and context.prev_move and context.prev_move.fen_black:
                board_before = parse_fen(context.prev_move.fen_black)
                
                if board_before:
                    piece_char = move.white_move[0].upper()
                    if piece_char in ["N", "B", "Q"]:
                        piece_type = chess.KNIGHT if piece_char == "N" else chess.BISHOP if piece_char == "B" else chess.QUEEN
                        
                        dest_part = move.white_move
                        if "=" in dest_part:
                            dest_part = dest_part.split("=")[0]
                        if "x" in dest_part:
                            parts = dest_part.split("x")
                            if len(parts) > 1:
                                dest_part = parts[-1]
                        
                        if len(dest_part) >= 2:
                            try:
                                dest_square = chess.parse_square(dest_part[-2:])
                                if is_central_square(dest_square):
                                    pieces_before = list(board_before.pieces(piece_type, chess.WHITE))
                                    pieces_after = list(board_after.pieces(piece_type, chess.WHITE))
                                    
                                    source_square = None
                                    for sq in pieces_before:
                                        if sq not in pieces_after:
                                            source_square = sq
                                            break
                                    
                                    if source_square is None and len(pieces_after) > len(pieces_before):
                                        if dest_square in pieces_after:
                                            source_square = None
                                    elif source_square is not None:
                                        if not is_central_square(source_square):
                                            # Require CPL < 30 OR eval improvement >50cp
                                            centralization_meaningful = False
                                            if move.cpl_white:
                                                try:
                                                    cpl = float(move.cpl_white)
                                                    if cpl < 30:
                                                        centralization_meaningful = True
                                                except (ValueError, TypeError):
                                                    pass
                                            
                                            if not centralization_meaningful and move.eval_white and context.prev_move and context.prev_move.eval_white:
                                                from app.services.game_highlights.helpers import parse_evaluation
                                                eval_before = parse_evaluation(context.prev_move.eval_white)
                                                eval_after = parse_evaluation(move.eval_white)
                                                if eval_before is not None and eval_after is not None:
                                                    eval_improvement = eval_after - eval_before
                                                    if eval_improvement > 50:
                                                        centralization_meaningful = True
                                            
                                            if centralization_meaningful:
                                                piece_name = "knight" if piece_char == "N" else "bishop" if piece_char == "B" else "queen"
                                                highlights.append(GameHighlight(
                                                    move_number=move_num,
                                                    is_white=True,
                                                    move_notation=f"{move_num}. {move.white_move}",
                                                    description=f"White centralized the {piece_name}",
                                                    priority=15,
                                                    rule_type="centralization"
                                                ))
                            except (ValueError, AttributeError):
                                pass
        
        # Black's centralization
        if move.black_move:
            board_after = parse_fen(move.fen_black)
            if board_after and move.fen_white:
                board_before = parse_fen(move.fen_white)
                
                if board_before:
                    piece_char = move.black_move[0].upper()
                    if piece_char in ["N", "B", "Q"]:
                        piece_type = chess.KNIGHT if piece_char == "N" else chess.BISHOP if piece_char == "B" else chess.QUEEN
                        
                        dest_part = move.black_move
                        if "=" in dest_part:
                            dest_part = dest_part.split("=")[0]
                        if "x" in dest_part:
                            parts = dest_part.split("x")
                            if len(parts) > 1:
                                dest_part = parts[-1]
                        
                        if len(dest_part) >= 2:
                            try:
                                dest_square = chess.parse_square(dest_part[-2:])
                                if is_central_square(dest_square):
                                    pieces_before = list(board_before.pieces(piece_type, chess.BLACK))
                                    pieces_after = list(board_after.pieces(piece_type, chess.BLACK))
                                    
                                    source_square = None
                                    for sq in pieces_before:
                                        if sq not in pieces_after:
                                            source_square = sq
                                            break
                                    
                                    if source_square is None and len(pieces_after) > len(pieces_before):
                                        if dest_square in pieces_after:
                                            source_square = None
                                    elif source_square is not None:
                                        if not is_central_square(source_square):
                                            piece_name = "knight" if piece_char == "N" else "bishop" if piece_char == "B" else "queen"
                                            highlights.append(GameHighlight(
                                                move_number=move_num,
                                                is_white=False,
                                                move_notation=f"{move_num}. ...{move.black_move}",
                                                description=f"Black centralized the {piece_name}",
                                                priority=15,
                                                rule_type="centralization"
                                            ))
                            except (ValueError, AttributeError):
                                pass
        
        return highlights

