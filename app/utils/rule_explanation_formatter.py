"""Utility class for formatting positional heatmap rule explanations."""

from typing import Dict, Optional
import chess


class RuleExplanationFormatter:
    """Formats positional heatmap rule explanations into natural language tooltips."""
    
    @staticmethod
    def format_evaluation_tooltip(piece_info: Dict, board: chess.Board, square: chess.Square, 
                                   config: Optional[Dict] = None) -> str:
        """Format evaluation information as natural language tooltip.
        
        Args:
            piece_info: Dictionary with piece evaluation info from get_detailed_evaluation.
            board: Current chess position.
            square: Square of the piece.
            config: Optional configuration dictionary. If None, uses defaults.
        
        Returns:
            Formatted tooltip text (HTML).
        """
        piece_symbol = piece_info.get('piece', '?')
        square_name = piece_info.get('square', '?').upper()
        color = piece_info.get('color', 'unknown')
        total_score = piece_info.get('total_score', 0.0)
        rules = piece_info.get('rules', [])
        
        # Get piece color for attack/defense checks
        piece = board.piece_at(square)
        if piece:
            piece_color = piece.color
            piece_type = piece.piece_type
            opponent = not piece_color
            is_attacked = board.is_attacked_by(opponent, square)
            is_defended = board.is_attacked_by(piece_color, square)
        else:
            piece_color = chess.WHITE  # Default, shouldn't happen
            piece_type = None
            is_attacked = False
            is_defended = False
        
        # Build structured data for tooltip
        tooltip_data = {
            'header': f"{color.capitalize()} {piece_symbol} on {square_name}",
            'positional_assessment': [],  # List of items: {'symbol': '•'|'✓'|'⚠', 'text': str, 'color': str}
            'position_status': [],  # List of items: {'symbol': '•', 'text': str}
            'combined_evaluation': None,  # {'summary': str, 'total': float} or None
            'overall': None  # str
        }
        
        # Add piece-specific context
        piece_context = RuleExplanationFormatter._get_piece_context(board, square, piece_type, piece_color)
        if piece_context:
            # Extract text from "  • " prefix
            context_text = piece_context[4:] if piece_context.startswith('  • ') else piece_context
            tooltip_data['positional_assessment'].append({
                'symbol': '•',
                'text': context_text,
                'color': 'text'
            })
        
        # Add rule explanations
        if not rules:
            tooltip_data['positional_assessment'].append({
                'symbol': None,
                'text': 'No significant positional factors apply.',
                'color': 'text'
            })
        else:
            positive_rules = []
            negative_rules = []
            
            for rule_info in rules:
                rule_name = rule_info.get('name', 'Unknown')
                raw_score = rule_info.get('score', 0.0)
                weight = rule_info.get('weight', 1.0)
                weighted_score = rule_info.get('weighted_score', raw_score * weight)
                
                # Get natural language explanation
                explanation = RuleExplanationFormatter._get_rule_explanation(
                    rule_name, raw_score, weighted_score, 
                    board, square, piece_color, piece_type,
                    is_attacked, is_defended
                )
                
                # Determine if this is a positive or negative factor
                # For Piece Activity, check actual move count rather than rule score
                # (since rule might have wrong score if piece is not current side to move)
                is_positive = False
                if rule_name == "Piece Activity":
                    # Check actual move count for this piece's color
                    if piece_color == board.turn:
                        legal_moves = [move for move in board.legal_moves if move.from_square == square]
                        num_moves = len(legal_moves)
                    else:
                        temp_board = board.copy()
                        temp_board.turn = piece_color
                        legal_moves = [move for move in temp_board.generate_legal_moves() if move.from_square == square]
                        num_moves = len(legal_moves)
                    
                    # Having moves is positive, no moves is negative
                    is_positive = (num_moves > 0)
                else:
                    # For other rules, use the weighted score
                    is_positive = (weighted_score > 0)
                
                if is_positive:
                    positive_rules.append(explanation)
                elif weighted_score < 0:
                    negative_rules.append(explanation)
            
            # Show positive factors first
            for explanation in positive_rules:
                tooltip_data['positional_assessment'].append({
                    'symbol': '✓',
                    'text': explanation,
                    'color': 'positive'
                })
            
            # Then negative factors
            for explanation in negative_rules:
                tooltip_data['positional_assessment'].append({
                    'symbol': '⚠',
                    'text': explanation,
                    'color': 'negative'
                })
        
        # Add position status
        if is_attacked or is_defended:
            if is_attacked and not is_defended:
                tooltip_data['position_status'].append({
                    'symbol': '•',
                    'text': 'Under attack and not defended'
                })
            elif is_attacked and is_defended:
                tooltip_data['position_status'].append({
                    'symbol': '•',
                    'text': 'Under attack but defended'
                })
            elif is_defended:
                tooltip_data['position_status'].append({
                    'symbol': '•',
                    'text': 'Defended'
                })
        
        # Simplified calculation (only if multiple rules)
        if len(rules) > 1:
            rule_summaries = []
            for rule_info in rules:
                weighted_score = rule_info.get('weighted_score', 0.0)
                rule_name = rule_info.get('name', 'Unknown')
                if abs(weighted_score) > 0.1:  # Only show significant contributions
                    if weighted_score > 0:
                        rule_summaries.append(f"{rule_name} (+{weighted_score:.1f})")
                    else:
                        rule_summaries.append(f"{rule_name} ({weighted_score:.1f})")
            
            if rule_summaries:
                tooltip_data['combined_evaluation'] = {
                    'summary': " + ".join(rule_summaries),
                    'total': total_score
                }
        
        # Overall evaluation with natural language
        overall_desc = RuleExplanationFormatter._get_overall_evaluation_description(total_score)
        tooltip_data['overall'] = overall_desc
        
        # Convert structured data to HTML with proper alignment
        return RuleExplanationFormatter._format_as_html_structured(tooltip_data, config, board, square, piece_color, piece_type, is_attacked, is_defended)
    
    @staticmethod
    def _get_piece_context(board: chess.Board, square: chess.Square, 
                           piece_type: Optional[int], piece_color: chess.Color) -> str:
        """Get piece-specific contextual information.
        
        Args:
            board: Current chess position.
            square: Square of the piece.
            piece_type: Type of piece (chess.PAWN, chess.KNIGHT, etc.).
            piece_color: Color of the piece.
        
        Returns:
            Contextual description string.
        """
        if piece_type is None:
            return ""
        
        rank = chess.square_rank(square)
        file = chess.square_file(square)
        file_name = chr(ord('a') + file)
        rank_name = str(rank + 1) if piece_color == chess.WHITE else str(8 - rank)
        
        context_parts = []
        
        if piece_type == chess.PAWN:
            # Show rank advancement
            if piece_color == chess.WHITE:
                squares_to_promotion = 7 - rank
            else:
                squares_to_promotion = rank
            
            if squares_to_promotion > 0:
                context_parts.append(f"on rank {rank_name} ({squares_to_promotion} squares from promotion)")
            
            # Check if central pawn
            if file in [2, 3, 4, 5]:  # c, d, e, f files
                context_parts.append("central pawn")
            elif file in [0, 7]:  # a, h files
                context_parts.append("edge pawn")
        
        elif piece_type == chess.ROOK:
            # Check if on open/semi-open file
            opponent = not piece_color
            friendly_pawns = board.pieces(chess.PAWN, piece_color)
            opponent_pawns = board.pieces(chess.PAWN, opponent)
            
            has_friendly_pawns = any(chess.square_file(sq) == file for sq in friendly_pawns)
            has_opponent_pawns = any(chess.square_file(sq) == file for sq in opponent_pawns)
            
            if not has_friendly_pawns and not has_opponent_pawns:
                context_parts.append("on open file")
            elif not has_opponent_pawns:
                context_parts.append("on semi-open file")
        
        elif piece_type == chess.KNIGHT:
            # Check if on edge or central
            if file in [2, 3, 4, 5] and rank in [2, 3, 4, 5]:
                context_parts.append("central position")
            elif file in [0, 7] or rank in [0, 7]:
                context_parts.append("edge position")
        
        elif piece_type == chess.BISHOP:
            # Check if on long diagonal
            if (file + rank) % 2 == 0:  # Same color squares
                if file in [2, 3, 4, 5] and rank in [2, 3, 4, 5]:
                    context_parts.append("central diagonal")
        
        elif piece_type == chess.KING:
            # Show king safety context
            opponent = not piece_color
            is_in_check = board.is_attacked_by(opponent, square)
            if is_in_check:
                context_parts.append("in check")
        
        if context_parts:
            return "  • " + ", ".join(context_parts)
        return ""
    
    @staticmethod
    def _get_rule_explanation(rule_name: str, raw_score: float, weighted_score: float,
                              board: chess.Board, square: chess.Square, 
                              piece_color: chess.Color, piece_type: Optional[int],
                              is_attacked: bool, is_defended: bool) -> str:
        """Get natural language explanation for a rule.
        
        Args:
            rule_name: Name of the rule.
            raw_score: Raw score from the rule.
            weighted_score: Weighted score.
            board: Current chess position.
            square: Square of the piece.
            piece_color: Color of the piece.
            piece_type: Type of piece.
            is_attacked: Whether the piece is attacked.
            is_defended: Whether the piece is defended.
        
        Returns:
            Natural language explanation string.
        """
        rank = chess.square_rank(square)
        file = chess.square_file(square)
        
        if rule_name == "Passed Pawn":
            if piece_color == chess.WHITE:
                squares_to_promotion = 7 - rank
            else:
                squares_to_promotion = rank
            
            explanation = f"Passed pawn: This pawn has no enemy pawns blocking its path to promotion"
            if squares_to_promotion > 0:
                explanation += f" ({squares_to_promotion} squares from promotion)"
            
            if is_attacked and not is_defended:
                explanation += ". However, it's under attack and not defended, making it vulnerable"
            elif is_attacked:
                explanation += ". It's under attack but defended"
            elif is_defended:
                explanation += ". It's defended"
        
        elif rule_name == "Backward Pawn":
            explanation = "Backward pawn: This pawn is behind friendly pawns on adjacent files and cannot advance safely because it would be attacked by enemy pawns"
            # Check if the pawn is defended by an adjacent pawn
            # Verify piece exists on board and has valid color
            piece_on_board = board.piece_at(square)
            if piece_type == chess.PAWN and piece_on_board and piece_on_board.piece_type == chess.PAWN:
                # Check if there's a friendly pawn on an adjacent file that can defend this pawn
                friendly_pawns = board.pieces(chess.PAWN, piece_on_board.color)
                adjacent_files = []
                if file > 0:
                    adjacent_files.append(file - 1)
                if file < 7:
                    adjacent_files.append(file + 1)
                
                is_defended_by_adjacent = False
                for adj_file in adjacent_files:
                    for defense_square in friendly_pawns:
                        defense_file = chess.square_file(defense_square)
                        defense_rank = chess.square_rank(defense_square)
                        
                        if defense_file != adj_file:
                            continue
                        
                        # Check if this friendly pawn can defend the pawn diagonally
                        if piece_on_board.color == chess.WHITE:
                            if defense_rank == rank - 1:
                                is_defended_by_adjacent = True
                                break
                        else:
                            if defense_rank == rank + 1:
                                is_defended_by_adjacent = True
                                break
                    
                    if is_defended_by_adjacent:
                        break
                
                if is_defended_by_adjacent:
                    explanation += ", but it is defended by an adjacent pawn (less weak)"
        
        elif rule_name == "Isolated Pawn":
            explanation = "Isolated pawn: This pawn has no friendly pawns on adjacent files to support it, making it a target for attack"
        
        elif rule_name == "Doubled Pawn":
            explanation = "Doubled pawn: Multiple pawns on the same file cannot defend each other, creating a structural weakness"
        
        elif rule_name == "King Safety":
            if weighted_score < 0:
                explanation = "King safety: The king is exposed to attack"
                opponent = not piece_color
                is_in_check = board.is_attacked_by(opponent, square)
                if is_in_check:
                    explanation += " and is in check"
            else:
                explanation = "King safety: The king is well-protected by pawns"
        
        elif rule_name == "Weak Square":
            explanation = "Weak square: This square is attacked by enemy pieces and cannot be defended by friendly pieces"
            if piece_type == chess.PAWN:
                explanation += " (or defended by pawns)"
        
        elif rule_name == "Piece Activity":
            # Count legal moves for this piece's color
            # board.legal_moves only returns moves for the current side to move,
            # so we need to check moves for the piece's color specifically
            if piece_color == board.turn:
                # Current side to move - can use board.legal_moves directly
                legal_moves = [move for move in board.legal_moves if move.from_square == square]
                num_moves = len(legal_moves)
            else:
                # Not current side to move - need to generate moves for this piece's color
                # Create a temporary board copy and set turn to piece's color
                temp_board = board.copy()
                temp_board.turn = piece_color
                legal_moves = [move for move in temp_board.generate_legal_moves() if move.from_square == square]
                num_moves = len(legal_moves)
            
            if num_moves > 0:
                explanation = f"Piece activity: This piece has {num_moves} legal moves"
                if num_moves >= 8:
                    explanation += " (very active)"
                elif num_moves >= 5:
                    explanation += " (active)"
                else:
                    explanation += " (moderately active)"
                
                # Check for doubled rooks on open file
                # Verify piece exists on board and has valid color
                piece_on_board = board.piece_at(square)
                if piece_type == chess.ROOK and piece_on_board and piece_on_board.piece_type == chess.ROOK:
                    piece_file = chess.square_file(square)
                    rooks = board.pieces(chess.ROOK, piece_on_board.color)
                    rooks_on_file = [sq for sq in rooks if chess.square_file(sq) == piece_file]
                    
                    if len(rooks_on_file) >= 2:
                        # Check if file is open
                        white_pawns = board.pieces(chess.PAWN, chess.WHITE)
                        black_pawns = board.pieces(chess.PAWN, chess.BLACK)
                        has_white_pawns = any(chess.square_file(sq) == piece_file for sq in white_pawns)
                        has_black_pawns = any(chess.square_file(sq) == piece_file for sq in black_pawns)
                        is_open_file = not has_white_pawns and not has_black_pawns
                        
                        if is_open_file:
                            explanation += ". Doubled rooks on open file (significant tactical advantage)"
            else:
                explanation = "Piece activity: This piece has no legal moves (blocked)"
                if piece_type == chess.ROOK:
                    explanation += ". Rooks need open files to be effective"
                elif piece_type == chess.BISHOP:
                    explanation += ". Bishops need open diagonals to be effective"
        
        elif rule_name == "Undeveloped Piece":
            # Get piece type name for explanation
            piece_type_name = ""
            if piece_type == chess.KNIGHT:
                piece_type_name = "knight"
            elif piece_type == chess.BISHOP:
                piece_type_name = "bishop"
            elif piece_type == chess.ROOK:
                piece_type_name = "rook"
            else:
                piece_type_name = "piece"
            
            explanation = f"Undeveloped piece: This {piece_type_name} is still on its starting square and blocked by pawns, preventing it from participating in the game"
            if piece_type == chess.ROOK:
                explanation += ". Rooks need to be developed to open files to be effective"
            elif piece_type == chess.BISHOP:
                explanation += ". Bishops need to be developed to active diagonals to be effective"
            elif piece_type == chess.KNIGHT:
                explanation += ". Knights need to be developed to central squares to be effective"
        
        elif rule_name == "Outpost Square":
            # Get piece type name for explanation
            piece_type_name = ""
            if piece_type == chess.KNIGHT:
                piece_type_name = "knight"
            elif piece_type == chess.BISHOP:
                piece_type_name = "bishop"
            else:
                piece_type_name = "piece"
            
            explanation = f"Outpost square: This {piece_type_name} is on an outpost square - a square that is protected by friendly pawns and cannot be attacked by enemy pawns"
            if piece_type == chess.KNIGHT:
                explanation += ". Knights on outpost squares are particularly strong, as they cannot be easily dislodged and have a secure base for operations"
            elif piece_type == chess.BISHOP:
                explanation += ". Bishops on outpost squares have secure positions protected by pawns and good mobility"
            
            explanation += ". The pawn protection ensures the piece has a stable base, while the immunity from enemy pawn attacks makes it difficult to challenge"
        
        else:
            # Fallback for unknown rules
            if weighted_score > 0:
                explanation = f"{rule_name}: Positive factor (+{weighted_score:.1f})"
            elif weighted_score < 0:
                explanation = f"{rule_name}: Negative factor ({weighted_score:.1f})"
            else:
                explanation = f"{rule_name}: Neutral"
        
        return explanation
    
    @staticmethod
    def _get_overall_evaluation_description(total_score: float) -> str:
        """Get natural language description of overall evaluation.
        
        Args:
            total_score: Total weighted score.
        
        Returns:
            Natural language description.
        """
        abs_score = abs(total_score)
        
        if abs_score < 0.5:
            return "Neutral position"
        elif abs_score < 5.0:
            if total_score > 0:
                return f"Slightly favorable (+{total_score:.1f})"
            else:
                return f"Slightly unfavorable ({total_score:.1f})"
        elif abs_score < 15.0:
            if total_score > 0:
                return f"Favorable position (+{total_score:.1f})"
            else:
                return f"Unfavorable position ({total_score:.1f})"
        elif abs_score < 30.0:
            if total_score > 0:
                return f"Strong position (+{total_score:.1f})"
            else:
                return f"Weak position ({total_score:.1f})"
        else:
            if total_score > 0:
                return f"Very strong position (+{total_score:.1f})"
            else:
                return f"Very weak position ({total_score:.1f})"
    
    @staticmethod
    def _format_as_html_structured(tooltip_data: Dict, config: Optional[Dict], 
                                   board: chess.Board, square: chess.Square,
                                   piece_color: chess.Color, piece_type: Optional[int],
                                   is_attacked: bool, is_defended: bool) -> str:
        """Format structured tooltip data as HTML with proper alignment.
        
        Args:
            tooltip_data: Structured dictionary with tooltip sections.
            config: Optional configuration dictionary.
            board: Current chess position.
            square: Square of the piece.
            piece_color: Color of the piece.
            piece_type: Type of piece.
            is_attacked: Whether piece is attacked.
            is_defended: Whether piece is defended.
        
        Returns:
            HTML-formatted string with proper alignment.
        """
        # Get tooltip configuration or use defaults
        if config:
            tooltip_config = config.get('ui', {}).get('positional_heatmap', {}).get('tooltip', {})
        else:
            tooltip_config = {}
        
        # Extract configuration values with defaults
        max_width = tooltip_config.get('max_width', 400)
        font_family = tooltip_config.get('font_family', 'Helvetica Neue')
        font_size = tooltip_config.get('font_size', 11)
        line_height = tooltip_config.get('line_height', 1.5)
        padding = tooltip_config.get('padding', 10)
        spacing = tooltip_config.get('spacing', 4)
        section_spacing = tooltip_config.get('section_spacing', 6)
        bg_color = tooltip_config.get('background_color', [45, 45, 50])
        border_color = tooltip_config.get('border_color', [60, 60, 65])
        border_width = tooltip_config.get('border_width', 1)
        border_radius = tooltip_config.get('border_radius', 5)
        text_color = tooltip_config.get('text_color', [220, 220, 220])
        header_font_size = tooltip_config.get('header_font_size', 12)
        header_color = tooltip_config.get('header_color', [240, 240, 240])
        positive_color = tooltip_config.get('positive_color', [100, 255, 100])
        negative_color = tooltip_config.get('negative_color', [255, 200, 100])
        calculation_indent = tooltip_config.get('calculation_indent', 12)
        calc_bg = tooltip_config.get('calculation_background', [35, 35, 40])
        calc_padding = tooltip_config.get('calculation_padding', 6)
        
        # Escape HTML special characters
        def escape_html(text: str) -> str:
            """Escape HTML special characters."""
            return (text.replace('&', '&amp;')
                       .replace('<', '&lt;')
                       .replace('>', '&gt;'))
        
        # Build HTML content
        html_lines = []
        
        # Container with background, border, and padding
        container_style = (
            f"max-width: {max_width}px; "
            f"word-wrap: break-word; "
            f"white-space: normal; "
            f"font-family: '{font_family}'; "
            f"font-size: {font_size}pt; "
            f"line-height: {line_height}; "
            f"padding: {padding}px; "
            f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]}); "
            f"border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]}); "
            f"border-radius: {border_radius}px; "
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        )
        html_lines.append(f'<div style="{container_style}">')
        
        # Header
        html_lines.append(f'<div style="margin-bottom: {spacing}px; background: transparent;">{escape_html(tooltip_data["header"])}</div>')
        html_lines.append(f'<div style="height: {spacing}px; background: transparent;"></div>')
        
        # Positional Assessment section
        if tooltip_data['positional_assessment']:
            html_lines.append(
                f'<div style="font-weight: bold; '
                f'font-size: {header_font_size}pt; '
                f'color: rgb({header_color[0]}, {header_color[1]}, {header_color[2]}); '
                f'margin-top: {section_spacing}px; '
                f'margin-bottom: {spacing}px; background: transparent;">Positional Assessment:</div>'
            )
            
            # Single table for all assessment items
            html_lines.append(
                '<table style="width: 100%; border-collapse: collapse; margin-bottom: 0px; background: transparent;">'
            )
            
            for item in tooltip_data['positional_assessment']:
                symbol = item.get('symbol')
                text = item.get('text', '')
                color_type = item.get('color', 'text')
                
                # Determine symbol color
                if color_type == 'positive':
                    symbol_color = f'rgb({positive_color[0]}, {positive_color[1]}, {positive_color[2]})'
                elif color_type == 'negative':
                    symbol_color = f'rgb({negative_color[0]}, {negative_color[1]}, {negative_color[2]})'
                else:
                    symbol_color = f'rgb({text_color[0]}, {text_color[1]}, {text_color[2]})'
                
                # Determine text color
                text_color_rgb = f'rgb({text_color[0]}, {text_color[1]}, {text_color[2]})'
                
                html_lines.append('<tr>')
                if symbol:
                    # Item with symbol
                    html_lines.append(
                        f'<td style="width: 25px; text-align: center; vertical-align: top; padding: 0; padding-right: 4px; background: transparent;">'
                        f'<span style="color: {symbol_color};">{symbol}</span>'
                        f'</td>'
                    )
                else:
                    # Item without symbol (full width)
                    html_lines.append(
                        f'<td colspan="2" style="text-align: left; vertical-align: top; padding: 0; background: transparent;">'
                        f'<span style="color: {text_color_rgb};">{escape_html(text)}</span>'
                        f'</td>'
                    )
                    html_lines.append('</tr>')
                    continue
                
                html_lines.append(
                    f'<td style="text-align: left; vertical-align: top; padding: 0; background: transparent;">'
                    f'<span style="color: {text_color_rgb};">{escape_html(text)}</span>'
                    f'</td>'
                )
                html_lines.append('</tr>')
            
            html_lines.append('</table>')
            html_lines.append(f'<div style="height: {spacing}px; background: transparent;"></div>')
        
        # Position Status section
        if tooltip_data['position_status']:
            html_lines.append(
                f'<div style="font-weight: bold; '
                f'font-size: {header_font_size}pt; '
                f'color: rgb({header_color[0]}, {header_color[1]}, {header_color[2]}); '
                f'margin-top: {section_spacing}px; '
                f'margin-bottom: {spacing}px; background: transparent;">Position Status:</div>'
            )
            
            # Single table for all status items
            html_lines.append(
                '<table style="width: 100%; border-collapse: collapse; margin-bottom: 0px; background: transparent;">'
            )
            
            for item in tooltip_data['position_status']:
                symbol = item.get('symbol', '•')
                text = item.get('text', '')
                
                html_lines.append('<tr>')
                html_lines.append(
                    f'<td style="width: 25px; text-align: center; vertical-align: top; padding: 0; padding-right: 4px; background: transparent;">'
                    f'<span style="color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});">{symbol}</span>'
                    f'</td>'
                )
                html_lines.append(
                    f'<td style="text-align: left; vertical-align: top; padding: 0; background: transparent;">'
                    f'<span style="color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});">{escape_html(text)}</span>'
                    f'</td>'
                )
                html_lines.append('</tr>')
            
            html_lines.append('</table>')
            html_lines.append(f'<div style="height: {spacing}px; background: transparent;"></div>')
        
        # Combined Evaluation section
        if tooltip_data['combined_evaluation']:
            html_lines.append(
                f'<div style="font-weight: bold; '
                f'font-size: {header_font_size}pt; '
                f'color: rgb({header_color[0]}, {header_color[1]}, {header_color[2]}); '
                f'margin-top: {section_spacing}px; '
                f'margin-bottom: {spacing}px; background: transparent;">Combined Evaluation:</div>'
            )
            
            summary = tooltip_data['combined_evaluation']['summary']
            total = tooltip_data['combined_evaluation']['total']
            
            html_lines.append(
                f'<div style="margin-left: {calculation_indent}px; '
                f'padding: {calc_padding}px; '
                f'background-color: rgb({calc_bg[0]}, {calc_bg[1]}, {calc_bg[2]}); '
                f'border-radius: 3px; '
                f'font-family: monospace; '
                f'margin-bottom: {spacing}px; background: transparent;">'
                f'<div style="background: transparent;">{escape_html(summary)}</div>'
                f'<div style="background: transparent;">= {total:.1f}</div>'
                f'</div>'
            )
        
        # Overall evaluation
        if tooltip_data['overall']:
            html_lines.append(f'<div style="height: {spacing}px; background: transparent;"></div>')
            html_lines.append(
                f'<div style="margin-bottom: {spacing}px; background: transparent;">'
                f'Overall: {escape_html(tooltip_data["overall"])}'
                f'</div>'
            )
        
        html_lines.append('</div>')
        
        return ''.join(html_lines)
    
    @staticmethod
    def _format_as_html(lines: list, config: Optional[Dict] = None) -> str:
        """Format tooltip lines as HTML with word-wrapping and enhanced styling.
        
        Args:
            lines: List of text lines to format.
            config: Optional configuration dictionary. If None, uses defaults.
        
        Returns:
            HTML-formatted string with word-wrapping and styling.
        """
        # Get tooltip configuration or use defaults
        if config:
            tooltip_config = config.get('ui', {}).get('positional_heatmap', {}).get('tooltip', {})
        else:
            tooltip_config = {}
        
        # Extract configuration values with defaults
        max_width = tooltip_config.get('max_width', 400)
        font_family = tooltip_config.get('font_family', 'Helvetica Neue')
        font_size = tooltip_config.get('font_size', 11)
        line_height = tooltip_config.get('line_height', 1.5)
        padding = tooltip_config.get('padding', 10)
        spacing = tooltip_config.get('spacing', 4)
        section_spacing = tooltip_config.get('section_spacing', 6)
        bg_color = tooltip_config.get('background_color', [45, 45, 50])
        border_color = tooltip_config.get('border_color', [60, 60, 65])
        border_width = tooltip_config.get('border_width', 1)
        border_radius = tooltip_config.get('border_radius', 5)
        text_color = tooltip_config.get('text_color', [220, 220, 220])
        header_font_size = tooltip_config.get('header_font_size', 12)
        header_color = tooltip_config.get('header_color', [240, 240, 240])
        positive_color = tooltip_config.get('positive_color', [100, 255, 100])
        negative_color = tooltip_config.get('negative_color', [255, 200, 100])
        bullet_indent = tooltip_config.get('bullet_indent', 15)
        calculation_indent = tooltip_config.get('calculation_indent', 12)
        calc_bg = tooltip_config.get('calculation_background', [35, 35, 40])
        calc_padding = tooltip_config.get('calculation_padding', 6)
        
        # Escape HTML special characters
        def escape_html(text: str) -> str:
            """Escape HTML special characters."""
            return (text.replace('&', '&amp;')
                       .replace('<', '&lt;')
                       .replace('>', '&gt;'))
        
        # Build HTML content with enhanced styling
        html_lines = []
        
        # Container with background, border, and padding
        container_style = (
            f"max-width: {max_width}px; "
            f"word-wrap: break-word; "
            f"white-space: normal; "
            f"font-family: '{font_family}'; "
            f"font-size: {font_size}pt; "
            f"line-height: {line_height}; "
            f"padding: {padding}px; "
            f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]}); "
            f"border: {border_width}px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]}); "
            f"border-radius: {border_radius}px; "
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
        )
        html_lines.append(f'<div style="{container_style}">')
        
        for i, line in enumerate(lines):
            if not line:
                # Empty line - add spacing
                html_lines.append(f'<div style="height: {spacing}px; background: transparent;"></div>')
            elif line.startswith('✓ ') or line.startswith('⚠ ') or line.startswith('  • '):
                # Items with symbols (checkmark, warning, or bullet) - use table for alignment
                if line.startswith('✓ '):
                    symbol = '✓'
                    symbol_color = f'rgb({positive_color[0]}, {positive_color[1]}, {positive_color[2]})'
                    escaped_text = escape_html(line[2:])  # Remove '✓ ' prefix
                elif line.startswith('⚠ '):
                    symbol = '⚠'
                    symbol_color = f'rgb({negative_color[0]}, {negative_color[1]}, {negative_color[2]})'
                    escaped_text = escape_html(line[2:])  # Remove '⚠ ' prefix
                else:  # line.startswith('  • ')
                    symbol = '•'
                    symbol_color = f'rgb({text_color[0]}, {text_color[1]}, {text_color[2]})'
                    escaped_text = escape_html(line[4:])  # Remove '  • ' prefix
                
                # Use table for proper alignment
                html_lines.append(
                    f'<table style="width: 100%; border-collapse: collapse; margin-bottom: {spacing}px; background: transparent;">'
                    f'<tr>'
                    f'<td style="width: 20px; text-align: center; vertical-align: top; padding: 0; background: transparent;">'
                    f'<span style="color: {symbol_color};">{symbol}</span>'
                    f'</td>'
                    f'<td style="text-align: left; vertical-align: top; padding: 0; padding-left: 4px; background: transparent;">'
                    f'<span style="color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});">{escaped_text}</span>'
                    f'</td>'
                    f'</tr>'
                    f'</table>'
                )
            elif line.startswith('  '):
                # Indented line (calculation details or bullet points)
                escaped_text = escape_html(line[2:])  # Remove '  ' prefix
                # Use consistent styling for all indented lines (no separate background)
                html_lines.append(
                    f'<div style="margin-left: {calculation_indent}px; '
                    f'font-family: monospace; '
                    f'margin-bottom: {spacing}px; background: transparent;">{escaped_text}</div>'
                )
            elif ':' in line and not line.startswith('Overall:'):
                # Section header (contains colon but not "Overall:")
                escaped_text = escape_html(line)
                html_lines.append(
                    f'<div style="font-weight: bold; '
                    f'font-size: {header_font_size}pt; '
                    f'color: rgb({header_color[0]}, {header_color[1]}, {header_color[2]}); '
                    f'margin-top: {section_spacing}px; '
                    f'margin-bottom: {spacing}px; background: transparent;">{escaped_text}</div>'
                )
            else:
                # Regular line with spacing
                escaped_text = escape_html(line)
                html_lines.append(f'<div style="margin-bottom: {spacing}px; background: transparent;">{escaped_text}</div>')
        
        html_lines.append('</div>')
        
        return ''.join(html_lines)

