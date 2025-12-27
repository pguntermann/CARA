"""Game Summary view for detail panel."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QGridLayout, QSizePolicy, QSplitter
)
from PyQt6.QtCore import Qt, QRect, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics, QMouseEvent
from typing import Dict, Any, Optional, List, Tuple, TYPE_CHECKING
import math

from app.models.game_model import GameModel
from app.models.moveslist_model import MoveData
from app.services.game_summary_service import GameSummary, GameHighlight
from app.controllers.game_controller import GameController
from app.utils.font_utils import resolve_font_family, scale_font_size

if TYPE_CHECKING:
    from app.controllers.game_summary_controller import GameSummaryController


class ClickableMoveLabel(QLabel):
    """A clickable QLabel that navigates to a specific move when clicked."""
    
    def __init__(self, text: str, move_number: int, is_white: bool, 
                 game_controller: Optional[GameController] = None) -> None:
        """Initialize the clickable move label.
        
        Args:
            text: Label text to display.
            move_number: Move number (1-indexed).
            is_white: True if this is a white move, False if black.
            game_controller: Optional GameController for navigation.
        """
        super().__init__(text)
        self.move_number = move_number
        self.is_white = is_white
        self.game_controller = game_controller
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse click to navigate to the move.
        
        Args:
            event: Mouse event.
        """
        if event.button() == Qt.MouseButton.LeftButton and self.game_controller:
            try:
                # Calculate ply_index from move_number and is_white
                # For move_number N:
                #   White move: ply_index = N * 2 - 1 (after white's move)
                #   Black move: ply_index = N * 2 (after black's move)
                if self.is_white:
                    ply_index = self.move_number * 2 - 1
                else:
                    ply_index = self.move_number * 2
                
                # Navigate to this ply - defensive check for valid ply_index
                if ply_index >= 0:
                    self.game_controller.navigate_to_ply(ply_index)
            except (AttributeError, RuntimeError):
                # Game controller or widget deleted, ignore
                pass
        
        super().mousePressEvent(event)


class EvaluationGraphWidget(QWidget):
    """Widget for displaying evaluation graph."""
    
    def __init__(self, config: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        """Initialize the evaluation graph widget.
        
        Args:
            config: Configuration dictionary.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        
        # Get graph config
        ui_config = config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        summary_config = panel_config.get('summary', {})
        graph_config = summary_config.get('evaluation_graph', {})
        
        self.graph_height = graph_config.get('height', 200)
        self.minimum_height = graph_config.get('minimum_height', 100)
        self.background_color = QColor(*graph_config.get('background_color', [30, 30, 35]))
        self.grid_color = QColor(*graph_config.get('grid_color', [60, 60, 65]))
        self.white_line_color = QColor(*graph_config.get('white_line_color', [255, 255, 255]))
        self.black_line_color = QColor(*graph_config.get('black_line_color', [0, 0, 0]))
        self.current_move_line_color = QColor(*graph_config.get('current_move_line_color', [255, 255, 0]))
        self.current_move_line_width = graph_config.get('current_move_line_width', 2)
        self.line_width = graph_config.get('line_width', 2)
        self.text_color = QColor(*graph_config.get('text_color', [200, 200, 200]))
        self.axis_color = QColor(*graph_config.get('axis_color', [150, 150, 150]))
        self.padding = graph_config.get('padding', [40, 20, 20, 40])  # [left, top, right, bottom]
        
        self.font_family = resolve_font_family(graph_config.get('font_family', 'Helvetica Neue'))
        self.font_size = int(scale_font_size(graph_config.get('font_size', 10)))
        
        # Graph configuration values
        self.scale_cap_cp = graph_config.get('scale_cap_cp', 1000.0)
        self.normalized_mode_small_range_threshold = graph_config.get('normalized_mode_small_range_threshold', 50)
        self.zero_based_mode_small_range_threshold = graph_config.get('zero_based_mode_small_range_threshold', 100)
        self.zero_based_mode_padding = graph_config.get('zero_based_mode_padding', 50)
        self.min_grid_spacing = graph_config.get('min_grid_spacing', 30)
        self.min_grid_lines = graph_config.get('min_grid_lines', 3)
        self.show_all_labels_height_threshold = graph_config.get('show_all_labels_height_threshold', 150)
        self.min_font_size = int(scale_font_size(graph_config.get('min_font_size', 8)))
        self.font_size_calculation_divisor = graph_config.get('font_size_calculation_divisor', 20)
        self.label_skip_divisor = graph_config.get('label_skip_divisor', 3)
        self.y_axis_label_spacing = graph_config.get('y_axis_label_spacing', 5)
        self.min_label_spacing = graph_config.get('min_label_spacing', 40)
        self.min_move_labels = graph_config.get('min_move_labels', 3)
        self.x_axis_label_spacing = graph_config.get('x_axis_label_spacing', 5)
        
        # Data
        self.evaluation_data: List[Tuple[int, float]] = []  # (ply_index, evaluation_centipawns)
        self.current_ply: int = 0
        self.max_ply: int = 0
        
        # Graph mode: False = zero-based (0.00 at bottom), True = normalized (0.00 in middle)
        self.normalized_mode: bool = False
        
        # Phase transition line configuration
        self.phase_transition_line_color = QColor(*graph_config.get('phase_transition_line_color', [100, 150, 255]))
        self.phase_transition_line_width = graph_config.get('phase_transition_line_width', 2)
        phase_line_style_str = graph_config.get('phase_transition_line_style', 'dashed')
        if phase_line_style_str == 'dashed':
            self.phase_transition_line_style = Qt.PenStyle.DashLine
        elif phase_line_style_str == 'dotted':
            self.phase_transition_line_style = Qt.PenStyle.DotLine
        elif phase_line_style_str == 'dash_dot':
            self.phase_transition_line_style = Qt.PenStyle.DashDotLine
        else:
            self.phase_transition_line_style = Qt.PenStyle.SolidLine
        
        # Phase boundaries (move numbers where phases transition)
        self.opening_end: int = 0  # Move number where opening ends
        self.middlegame_end: int = 0  # Move number where middlegame ends
        
        # Critical moment line configuration
        self.critical_moment_worst_line_color = QColor(*graph_config.get('critical_moment_worst_line_color', [255, 150, 150]))
        self.critical_moment_best_line_color = QColor(*graph_config.get('critical_moment_best_line_color', [150, 255, 150]))
        self.critical_moment_line_width = graph_config.get('critical_moment_line_width', 1)
        critical_moment_line_style_str = graph_config.get('critical_moment_line_style', 'dotted')
        if critical_moment_line_style_str == 'dashed':
            self.critical_moment_line_style = Qt.PenStyle.DashLine
        elif critical_moment_line_style_str == 'dotted':
            self.critical_moment_line_style = Qt.PenStyle.DotLine
        elif critical_moment_line_style_str == 'dash_dot':
            self.critical_moment_line_style = Qt.PenStyle.DashDotLine
        else:
            self.critical_moment_line_style = Qt.PenStyle.SolidLine
        
        # Critical moments (separate lists for worst and best moves)
        self.critical_moments_worst: List[int] = []  # List of ply indices for worst moves
        self.critical_moments_best: List[int] = []  # List of ply indices for best moves
        
        # Set minimum height (will be resizable via splitter)
        self.setMinimumHeight(self.minimum_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    
    def set_normalized_mode(self, normalized: bool) -> None:
        """Set normalized mode for the evaluation graph.
        
        Args:
            normalized: True for normalized mode (0.00 in middle), False for zero-based mode (0.00 at bottom).
        """
        if self.normalized_mode != normalized:
            self.normalized_mode = normalized
            self.update()  # Redraw graph with new mode
    
    def set_evaluation_data(self, evaluation_data: List[Tuple[int, float]]) -> None:
        """Set evaluation data for the graph.
        
        Args:
            evaluation_data: List of (ply_index, evaluation_centipawns) tuples.
        """
        self.evaluation_data = evaluation_data
        if evaluation_data:
            self.max_ply = max(ply for ply, _ in evaluation_data)
        else:
            self.max_ply = 0
        self.update()
    
    def set_current_ply(self, ply: int) -> None:
        """Set current move ply index for vertical line indicator.
        
        Args:
            ply: Current ply index.
        """
        if self.current_ply != ply:
            self.current_ply = ply
            self.update()
    
    def set_phase_boundaries(self, opening_end: int, middlegame_end: int) -> None:
        """Set phase boundaries for phase transition indicators.
        
        Args:
            opening_end: Move number where opening phase ends.
            middlegame_end: Move number where middlegame phase ends.
        """
        if self.opening_end != opening_end or self.middlegame_end != middlegame_end:
            self.opening_end = opening_end
            self.middlegame_end = middlegame_end
            self.update()
    
    def set_critical_moments(self, white_top_worst: List, white_top_best: List, 
                             black_top_worst: List, black_top_best: List) -> None:
        """Set critical moments for critical moment indicators.
        
        Args:
            white_top_worst: List of CriticalMove instances for white's worst moves.
            white_top_best: List of CriticalMove instances for white's best moves.
            black_top_worst: List of CriticalMove instances for black's worst moves.
            black_top_best: List of CriticalMove instances for black's best moves.
        """
        # Collect worst and best moves separately and convert to ply indices
        worst_moments_ply: List[int] = []
        best_moments_ply: List[int] = []
        
        # Process white worst moves
        for move in white_top_worst:
            if move and hasattr(move, 'move_number') and move.move_number and move.move_number > 0:
                # White move: ply_index = move_number * 2 - 1 (after white's move)
                ply_index = move.move_number * 2 - 1
                worst_moments_ply.append(ply_index)
        
        # Process black worst moves
        for move in black_top_worst:
            if move and hasattr(move, 'move_number') and move.move_number and move.move_number > 0:
                # Black move: ply_index = move_number * 2 (after black's move)
                ply_index = move.move_number * 2
                worst_moments_ply.append(ply_index)
        
        # Process white best moves
        for move in white_top_best:
            if move and hasattr(move, 'move_number') and move.move_number and move.move_number > 0:
                # White move: ply_index = move_number * 2 - 1 (after white's move)
                ply_index = move.move_number * 2 - 1
                best_moments_ply.append(ply_index)
        
        # Process black best moves
        for move in black_top_best:
            if move and hasattr(move, 'move_number') and move.move_number and move.move_number > 0:
                # Black move: ply_index = move_number * 2 (after black's move)
                ply_index = move.move_number * 2
                best_moments_ply.append(ply_index)
        
        # Remove duplicates and sort
        self.critical_moments_worst = sorted(set(worst_moments_ply))
        self.critical_moments_best = sorted(set(best_moments_ply))
        self.update()
    
    def paintEvent(self, event) -> None:
        """Paint the evaluation graph."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        
        # Draw background
        painter.fillRect(0, 0, width, height, self.background_color)
        
        if not self.evaluation_data or self.max_ply == 0:
            # No data - draw placeholder
            painter.setPen(self.text_color)
            font = QFont(self.font_family, self.font_size)
            painter.setFont(font)
            painter.drawText(QRect(0, 0, width, height), Qt.AlignmentFlag.AlignCenter, "No evaluation data")
            return
        
        # Calculate drawing area
        left = self.padding[0]
        top = self.padding[1]
        right = width - self.padding[2]
        bottom = height - self.padding[3]
        graph_width = right - left
        graph_height = bottom - top
        
        # Find evaluation range (for scaling)
        all_evals = [eval_cp for _, eval_cp in self.evaluation_data]
        min_eval = min(all_evals)
        max_eval = max(all_evals)
        
        # Cap the scale at ±10 pawns (±1000 centipawns) for readability
        # Mate positions will still be plotted but shown at the edges
        min_eval = max(min_eval, -self.scale_cap_cp)
        max_eval = min(max_eval, self.scale_cap_cp)
        
        # Store max_abs_eval for normalized mode calculations (calculate before modifying min/max)
        max_abs_eval = max(abs(min_eval), abs(max_eval)) if min_eval != max_eval else 1.0
        
        if self.normalized_mode:
            # Normalized mode: 0.00 is in the middle, scale is symmetric
            # Find the maximum absolute value and use symmetric range
            if max_abs_eval < self.normalized_mode_small_range_threshold:
                max_abs_eval = self.normalized_mode_small_range_threshold
            min_eval = -max_abs_eval
            max_eval = max_abs_eval
        else:
            # Zero-based mode: add padding to range
            eval_range = max_eval - min_eval
            if eval_range < self.zero_based_mode_small_range_threshold:
                min_eval -= self.zero_based_mode_padding
                max_eval += self.zero_based_mode_padding
                # Re-apply cap after padding
                min_eval = max(min_eval, -self.scale_cap_cp)
                max_eval = min(max_eval, self.scale_cap_cp)
        
        eval_range = max_eval - min_eval
        
        # Recalculate max_abs_eval after range adjustments for normalized mode
        if self.normalized_mode:
            max_abs_eval = max(abs(min_eval), abs(max_eval))
        
        # Calculate adaptive grid spacing based on available height
        # Minimum spacing between grid lines (in pixels) to avoid clutter
        max_grid_lines = max(self.min_grid_lines, int(graph_height / self.min_grid_spacing))
        
        # Determine pawn range to show based on evaluation range and available space
        min_pawns = int(min_eval / 100) - 1
        max_pawns = int(max_eval / 100) + 1
        pawn_range = max_pawns - min_pawns
        
        # Calculate grid line interval (show every Nth pawn)
        if pawn_range <= max_grid_lines:
            # Enough space - show all grid lines
            grid_interval = 1
            show_all_labels = True
        else:
            # Not enough space - skip some grid lines
            grid_interval = max(1, (pawn_range + max_grid_lines - 1) // max_grid_lines)
            show_all_labels = graph_height > self.show_all_labels_height_threshold
        
        # Draw grid lines (horizontal lines at 0, ±1, ±2, etc. pawns)
        painter.setPen(QPen(self.grid_color, 1))
        
        # Always draw zero line
        if self.normalized_mode:
            # In normalized mode, zero is always in the middle
            zero_y = top + graph_height / 2
        else:
            # In zero-based mode, zero is at the calculated position
            zero_y = bottom - ((0 - min_eval) / eval_range * graph_height) if eval_range > 0 else bottom - graph_height / 2
        painter.drawLine(int(left), int(zero_y), int(right), int(zero_y))
        
        # Draw horizontal grid lines at adaptive intervals
        grid_pawns = []
        for pawns in range(min_pawns, max_pawns + 1, grid_interval):
            eval_cp = pawns * 100
            if min_eval <= eval_cp <= max_eval and pawns != 0:  # Skip zero (already drawn)
                if self.normalized_mode:
                    # In normalized mode, calculate y position from center
                    center_y = top + graph_height / 2
                    y = center_y - (eval_cp / max_abs_eval * (graph_height / 2)) if max_abs_eval > 0 else center_y
                else:
                    # In zero-based mode, calculate y position from bottom
                    y = bottom - ((eval_cp - min_eval) / eval_range * graph_height) if eval_range > 0 else bottom
                painter.drawLine(int(left), int(y), int(right), int(y))
                grid_pawns.append(pawns)
        
        # Draw axes labels
        painter.setPen(self.text_color)
        
        # Adjust font size based on height (smaller font for smaller graphs)
        adaptive_font_size = max(self.min_font_size, min(self.font_size, int(graph_height / self.font_size_calculation_divisor)))
        font = QFont(self.font_family, adaptive_font_size)
        painter.setFont(font)
        fm = QFontMetrics(font)
        
        # Y-axis labels (evaluation) - show labels for grid lines
        label_pawns = [0]  # Always show zero
        if show_all_labels:
            # Show all grid line labels
            label_pawns.extend(grid_pawns)
        else:
            # Show fewer labels (every other grid line or just key values)
            label_skip = max(1, len(grid_pawns) // self.label_skip_divisor)
            for i in range(0, len(grid_pawns), label_skip):
                label_pawns.append(grid_pawns[i])
        
        for pawns in sorted(set(label_pawns)):
            eval_cp = pawns * 100
            if min_eval <= eval_cp <= max_eval:
                if self.normalized_mode:
                    # In normalized mode, calculate y position from center
                    center_y = top + graph_height / 2
                    y = center_y - (eval_cp / max_abs_eval * (graph_height / 2)) if max_abs_eval > 0 else center_y
                else:
                    # In zero-based mode, calculate y position from bottom
                    y = bottom - ((eval_cp - min_eval) / eval_range * graph_height) if eval_range > 0 else bottom
                label = f"{pawns:+.1f}" if pawns != 0 else "0.0"
                label_width = fm.horizontalAdvance(label)
                painter.drawText(int(left - label_width - self.y_axis_label_spacing), int(y + fm.height() / 2), label)
        
        # X-axis labels (move numbers) - also adaptive
        if self.max_ply > 0:
            # Calculate how many move labels can fit based on width
            max_move_labels = max(self.min_move_labels, int(graph_width / self.min_label_spacing))
            label_interval = max(1, self.max_ply // max_move_labels)
            
            for ply in range(0, self.max_ply + 1, label_interval):
                x = left + (ply / self.max_ply * graph_width) if self.max_ply > 0 else left
                move_num = (ply + 1) // 2  # Convert ply to move number
                label = str(move_num)
                label_width = fm.horizontalAdvance(label)
                painter.drawText(int(x - label_width / 2), int(bottom + fm.height() + self.x_axis_label_spacing), label)
        
        # Draw evaluation line (single continuous line)
        if len(self.evaluation_data) > 1:
            # Sort by ply index to ensure correct order
            sorted_data = sorted(self.evaluation_data, key=lambda x: x[0])
            points: List[QPointF] = []
            
            for ply, eval_cp in sorted_data:
                x = left + (ply / self.max_ply * graph_width) if self.max_ply > 0 else left
                # Clamp evaluation to scale cap for plotting (mate positions shown at edges)
                clamped_eval = max(min_eval, min(max_eval, eval_cp))
                
                if self.normalized_mode:
                    # Normalized mode: 0.00 is in the middle
                    # Positive values go up from center, negative values go down from center
                    center_y = top + graph_height / 2
                    if eval_range > 0:
                        # Map evaluation to y position: 0 = center, +max = top, -max = bottom
                        y = center_y - (clamped_eval / max_abs_eval * (graph_height / 2)) if max_abs_eval > 0 else center_y
                    else:
                        y = center_y
                else:
                    # Zero-based mode: 0.00 is at bottom, positive values go up
                    y = bottom - ((clamped_eval - min_eval) / eval_range * graph_height) if eval_range > 0 else bottom
                
                # Clamp y to graph bounds to ensure mate positions are visible at edges
                y = max(top, min(bottom, y))
                points.append(QPointF(x, y))
            
            # Draw line connecting all points
            if len(points) > 1:
                painter.setPen(QPen(self.white_line_color, self.line_width))
                for i in range(len(points) - 1):
                    painter.drawLine(points[i], points[i + 1])
        
        # Draw critical moment indicators (vertical lines) - draw after evaluation line, before phase transition lines
        # Draw worst moves in red, best moves in green
        if self.max_ply > 0:
            # Draw worst moves (light red)
            if self.critical_moments_worst:
                painter.setPen(QPen(self.critical_moment_worst_line_color, self.critical_moment_line_width, self.critical_moment_line_style))
                for ply_index in self.critical_moments_worst:
                    if 0 <= ply_index <= self.max_ply:
                        x = left + (ply_index / self.max_ply * graph_width) if self.max_ply > 0 else left
                        painter.drawLine(int(x), int(top), int(x), int(bottom))
            
            # Draw best moves (green)
            if self.critical_moments_best:
                painter.setPen(QPen(self.critical_moment_best_line_color, self.critical_moment_line_width, self.critical_moment_line_style))
                for ply_index in self.critical_moments_best:
                    if 0 <= ply_index <= self.max_ply:
                        x = left + (ply_index / self.max_ply * graph_width) if self.max_ply > 0 else left
                        painter.drawLine(int(x), int(top), int(x), int(bottom))
        
        # Draw phase transition indicators (vertical lines) - draw after critical moment lines, before current move indicator
        # Note: Phase transition lines are drawn before current move line so current move line renders on top
        if self.max_ply > 0:
            # Draw opening-to-middlegame transition line
            if self.opening_end > 0:
                # Convert move number to ply index (opening_end is move number, need to find the ply after that move)
                # Opening ends at move N, so transition is after move N (ply = N * 2)
                opening_end_ply = self.opening_end * 2
                if opening_end_ply <= self.max_ply:
                    x = left + (opening_end_ply / self.max_ply * graph_width) if self.max_ply > 0 else left
                    painter.setPen(QPen(self.phase_transition_line_color, self.phase_transition_line_width, self.phase_transition_line_style))
                    painter.drawLine(int(x), int(top), int(x), int(bottom))
            
            # Draw middlegame-to-endgame transition line
            if self.middlegame_end > 0:
                # Convert move number to ply index (middlegame_end is move number, need to find the ply after that move)
                # Middlegame ends at move N, so transition is after move N (ply = N * 2)
                middlegame_end_ply = self.middlegame_end * 2
                if middlegame_end_ply <= self.max_ply:
                    x = left + (middlegame_end_ply / self.max_ply * graph_width) if self.max_ply > 0 else left
                    painter.setPen(QPen(self.phase_transition_line_color, self.phase_transition_line_width, self.phase_transition_line_style))
                    painter.drawLine(int(x), int(top), int(x), int(bottom))
        
        # Draw current move indicator (vertical line) - draw LAST so it always renders on top of phase transition lines
        if self.current_ply >= 0 and self.max_ply > 0:
            x = left + (self.current_ply / self.max_ply * graph_width) if self.max_ply > 0 else left
            painter.setPen(QPen(self.current_move_line_color, self.current_move_line_width))
            painter.drawLine(int(x), int(top), int(x), int(bottom))


class PieChartWidget(QWidget):
    """Widget for displaying a pie chart."""
    
    def __init__(self, config: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        """Initialize the pie chart widget.
        
        Args:
            config: Configuration dictionary.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        
        # Get colors from config
        ui_config = config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        summary_config = panel_config.get('summary', {})
        colors_config = summary_config.get('colors', {})
        pie_chart_config = summary_config.get('pie_chart', {})
        
        self.colors = {
            'book_move': QColor(*colors_config.get('book_move', [150, 150, 150])),
            'brilliant': QColor(*colors_config.get('brilliant', [255, 215, 0])),
            'best_move': QColor(*colors_config.get('best_move', [100, 255, 100])),
            'good_move': QColor(*colors_config.get('good_move', [150, 255, 150])),
            'inaccuracy': QColor(*colors_config.get('inaccuracy', [255, 255, 100])),
            'mistake': QColor(*colors_config.get('mistake', [255, 200, 100])),
            'miss': QColor(*colors_config.get('miss', [200, 100, 255])),
            'blunder': QColor(*colors_config.get('blunder', [255, 100, 100])),
        }
        
        self.text_color = QColor(*colors_config.get('text_color', [220, 220, 220]))
        self.font_family = resolve_font_family(summary_config.get('fonts', {}).get('label_font_family', 'Helvetica Neue'))
        self.font_size = int(scale_font_size(summary_config.get('fonts', {}).get('label_font_size', 11)))
        
        # Pie chart configuration
        minimum_size = pie_chart_config.get('minimum_size', [200, 200])
        self.margin = pie_chart_config.get('margin', 20)
        
        # Data
        self.data: Dict[str, int] = {}  # {category: count}
        self.total: int = 0
        
        # Set minimum size
        self.setMinimumSize(minimum_size[0], minimum_size[1])
    
    def set_data(self, data: Dict[str, int]) -> None:
        """Set pie chart data.
        
        Args:
            data: Dictionary mapping category names to counts.
        """
        self.data = data
        self.total = sum(data.values())
        self.update()
    
    def paintEvent(self, event) -> None:
        """Paint the pie chart."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        size = min(width, height) - self.margin
        x = (width - size) / 2
        y = (height - size) / 2
        rect = QRect(int(x), int(y), int(size), int(size))
        
        if self.total == 0:
            # No data - draw placeholder
            painter.setPen(self.text_color)
            font = QFont(self.font_family, self.font_size)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No data")
            return
        
        # Draw pie slices
        start_angle = 0
        for category, count in self.data.items():
            if count == 0:
                continue
            
            # Calculate angle for this slice
            angle = (count / self.total) * 360 * 16  # Qt uses 1/16th degree units
            
            # Get color for category
            color = self.colors.get(category.lower().replace(' ', '_'), self.text_color)
            
            # Draw slice
            painter.setBrush(color)
            painter.setPen(QPen(color, 1))
            painter.drawPie(rect, int(start_angle), int(angle))
            
            start_angle += angle


class DetailSummaryView(QWidget):
    """Game summary view displaying game information."""
    
    def __init__(self, config: Dict[str, Any], 
                 game_model: Optional[GameModel] = None,
                 game_controller: Optional[GameController] = None,
                 summary_controller: Optional["GameSummaryController"] = None) -> None:
        """Initialize the game summary view.
        
        Args:
            config: Configuration dictionary.
            game_model: Optional GameModel instance to observe.
            game_controller: Optional GameController for navigating to specific moves.
            summary_controller: Optional GameSummaryController for providing summary data.
        """
        super().__init__()
        self.config = config
        self._game_model: Optional[GameModel] = None
        self._game_controller: Optional[GameController] = None
        self._summary_controller: Optional["GameSummaryController"] = None
        self._latest_moves: List[MoveData] = []
        self.current_summary: Optional[GameSummary] = None
        self._last_unavailable_reason: str = "not_analyzed"
        
        # Get summary config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        summary_config = panel_config.get('summary', {})
        self.placeholder_text_not_analyzed = summary_config.get(
            'placeholder_text_not_analyzed',
            'Run Game Analysis to view Game Summary'
        )
        self.placeholder_text_to_be_implemented = summary_config.get(
            'placeholder_text_to_be_implemented',
            'to be implemented...'
        )
        
        self._setup_ui()
        self._set_disabled_placeholder_visible(True, self.placeholder_text_not_analyzed)
        
        # Connect to models if provided
        if game_model:
            self.set_game_model(game_model)
        
        if game_controller:
            self.set_game_controller(game_controller)
        
        if summary_controller:
            self.set_summary_controller(summary_controller)
    
    def _setup_ui(self) -> None:
        """Setup the game summary UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Get config for splitter
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        summary_config = panel_config.get('summary', {})
        splitter_config = summary_config.get('splitter', {})
        
        # Create vertical splitter for resizable evaluation graph
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter)
        
        # Evaluation graph (top, resizable)
        self.evaluation_graph = EvaluationGraphWidget(self.config)
        splitter.addWidget(self.evaluation_graph)
        
        # Scrollable content area (bottom, resizable)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        # Get background color for scroll area - use pane_background from tabs config or summary background
        tabs_config = panel_config.get('tabs', {})
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        # Apply scrollbar styling using StyleManager
        from app.views.style import StyleManager
        border_color = [min(255, pane_bg[0] + 20), min(255, pane_bg[1] + 20), min(255, pane_bg[2] + 20)]
        StyleManager.style_scroll_area(
            scroll_area,
            self.config,
            pane_bg,
            border_color,
            0  # No border radius
        )
        
        # Content widget
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        
        # Get layout config
        layout_config = summary_config.get('layout', {})
        margins = layout_config.get('margins', [10, 10, 10, 10])
        spacing = layout_config.get('spacing', 15)
        
        self.content_layout.setContentsMargins(margins[0], margins[1], margins[2], margins[3])
        self.content_layout.setSpacing(spacing)
        
        # Placeholder label (will be replaced with actual content when analyzed)
        self.placeholder_label = QLabel()
        self.placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.content_layout.addWidget(self.placeholder_label)
        
        scroll_area.setWidget(self.content_widget)
        splitter.addWidget(scroll_area)
        
        # Configure splitter sizes and stretch factors from config
        graph_height = splitter_config.get('graph_height', 200)
        content_height = splitter_config.get('content_height', 400)
        graph_stretch = splitter_config.get('graph_stretch_factor', 1)
        content_stretch = splitter_config.get('content_stretch_factor', 3)
        
        splitter.setSizes([graph_height, content_height])
        splitter.setStretchFactor(0, graph_stretch)
        splitter.setStretchFactor(1, content_stretch)
        
        # Fix cursor on splitter handle for macOS compatibility
        # Vertical splitter needs horizontal resize cursor
        for i in range(splitter.count() - 1):
            handle = splitter.handle(i)
            if handle:
                handle.setCursor(Qt.CursorShape.SizeVerCursor)
        
        # Apply splitter styling to prevent macOS theme override
        ui_config = self.config.get('ui', {})
        splitter_config = ui_config.get('splitter', {})
        handle_color = splitter_config.get('handle_color', [30, 30, 30])
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: rgb({handle_color[0]}, {handle_color[1]}, {handle_color[2]});
            }}
            QSplitter::handle:vertical {{
                background-color: rgb({handle_color[0]}, {handle_color[1]}, {handle_color[2]});
            }}
        """)
        
        # Store splitter reference for potential future use
        self.splitter = splitter
        
        # Disabled state placeholder (uses config values with DPI scaling)
        placeholder_config = summary_config.get('placeholder', {})
        placeholder_text_color = placeholder_config.get('text_color', [150, 150, 150])
        placeholder_font_size = int(scale_font_size(placeholder_config.get('font_size', 14)))
        placeholder_padding = placeholder_config.get('padding', 20)
        
        self.disabled_placeholder = QLabel(self.placeholder_text_not_analyzed)
        self.disabled_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.disabled_placeholder.setWordWrap(True)
        self.disabled_placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.disabled_placeholder.setStyleSheet(f"""
            QLabel {{
                color: rgb({placeholder_text_color[0]}, {placeholder_text_color[1]}, {placeholder_text_color[2]});
                font-size: {placeholder_font_size}pt;
                padding: {placeholder_padding}px;
            }}
        """)
        self.disabled_placeholder.hide()
        layout.addWidget(self.disabled_placeholder)
        
        # Default to disabled placeholder until summary data arrives
        self._set_disabled_placeholder_visible(True, self.placeholder_text_not_analyzed)
    
    def set_game_model(self, game_model: GameModel) -> None:
        """Set the game model to observe."""
        if self._game_model:
            try:
                self._game_model.active_move_changed.disconnect(self._on_active_move_changed)
            except (RuntimeError, TypeError):
                pass
        
        self._game_model = game_model
        self._game_model.active_move_changed.connect(self._on_active_move_changed)
    
    def set_game_controller(self, game_controller: GameController) -> None:
        """Set the game controller for navigating to moves.
        
        Args:
            game_controller: The GameController instance.
        """
        self._game_controller = game_controller
    
    def set_summary_controller(self, summary_controller: "GameSummaryController") -> None:
        """Attach the summary controller supplying data for this view."""
        if self._summary_controller:
            try:
                self._summary_controller.summary_updated.disconnect(self._handle_summary_updated)
                self._summary_controller.summary_unavailable.disconnect(self._handle_summary_unavailable)
            except (RuntimeError, TypeError):
                pass
        
        self._summary_controller = summary_controller
        
        if self._summary_controller:
            self._summary_controller.summary_updated.connect(self._handle_summary_updated)
            self._summary_controller.summary_unavailable.connect(self._handle_summary_unavailable)
            
            if self._summary_controller.get_current_summary():
                self._handle_summary_updated(
                    self._summary_controller.get_current_summary(),
                    self._summary_controller.get_latest_moves()
                )
            else:
                self._handle_summary_unavailable(self._summary_controller.get_last_unavailable_reason())
    
    def _on_active_move_changed(self, ply_index: int) -> None:
        """Handle active move change.
        
        Args:
            ply_index: Current ply index.
        """
        # Early return if widget is being destroyed or doesn't have required attributes
        if not hasattr(self, 'evaluation_graph') or not self.evaluation_graph:
            return
        
        # Update evaluation graph current move indicator
        try:
            self.evaluation_graph.set_current_ply(ply_index)
        except RuntimeError:
            # Widget was deleted, ignore
            pass
    
    def _handle_summary_updated(self, summary: GameSummary, moves: List[MoveData]) -> None:
        """Render the summary content when new data is available."""
        self.current_summary = summary
        self._latest_moves = moves or []
        self._last_unavailable_reason = ""
        
        self._set_disabled_placeholder_visible(False)
        try:
            if hasattr(self, 'placeholder_label') and self.placeholder_label:
                self.placeholder_label.hide()
        except RuntimeError:
            pass
        
        self._clear_content()
        self._build_summary_content(total_moves=len(self._latest_moves), moves=self._latest_moves)
        
        try:
            if hasattr(self, 'evaluation_graph') and self.evaluation_graph:
                self.evaluation_graph.set_evaluation_data(self.current_summary.evaluation_data)
                self.evaluation_graph.set_phase_boundaries(
                    self.current_summary.opening_end,
                    self.current_summary.middlegame_end
                )
                self.evaluation_graph.set_critical_moments(
                    self.current_summary.white_top_worst or [],
                    self.current_summary.white_top_best or [],
                    self.current_summary.black_top_worst or [],
                    self.current_summary.black_top_best or []
                )
                if self._game_model:
                    current_ply = self._game_model.get_active_move_ply()
                    self.evaluation_graph.set_current_ply(current_ply)
        except RuntimeError:
            pass
    
    def _handle_summary_unavailable(self, reason: str) -> None:
        """Show appropriate placeholder when summary data is unavailable."""
        self.current_summary = None
        self._latest_moves = []
        self._last_unavailable_reason = reason or "not_analyzed"
        
        self._clear_content()
        
        placeholder_text = self.placeholder_text_to_be_implemented
        if reason == "not_analyzed":
            placeholder_text = self.placeholder_text_not_analyzed
            self._set_disabled_placeholder_visible(True, placeholder_text)
        else:
            self._set_disabled_placeholder_visible(False)
            try:
                if hasattr(self, 'placeholder_label') and self.placeholder_label:
                    self.placeholder_label.setText(placeholder_text)
                    self.placeholder_label.show()
            except RuntimeError:
                pass
        
        try:
            if hasattr(self, 'evaluation_graph') and self.evaluation_graph:
                self.evaluation_graph.set_evaluation_data([])
        except RuntimeError:
            pass
    
    def _set_disabled_placeholder_visible(self, visible: bool, text: Optional[str] = None) -> None:
        """Show or hide the disabled placeholder and splitter."""
        if not hasattr(self, 'disabled_placeholder') or not self.disabled_placeholder:
            return
        
        try:
            if visible:
                if text:
                    self.disabled_placeholder.setText(text)
                self.disabled_placeholder.show()
                if hasattr(self, 'splitter') and self.splitter:
                    self.splitter.hide()
                if hasattr(self, 'placeholder_label') and self.placeholder_label:
                    self.placeholder_label.hide()
            else:
                self.disabled_placeholder.hide()
                if hasattr(self, 'splitter') and self.splitter:
                    self.splitter.show()
        except RuntimeError:
            # Widget was deleted, ignore
            pass
    
    def _clear_content(self) -> None:
        """Clear all content widgets except placeholder."""
        # Clear widgets safely to prevent accessing deleted widgets
        while self.content_layout.count() > 1:  # Keep placeholder
            item = self.content_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    # Disconnect any signals before deletion to prevent accessing deleted widget
                    try:
                        # Disconnect any signal connections from this widget
                        widget.setParent(None)
                        widget.deleteLater()
                    except RuntimeError:
                        # Widget already deleted, ignore
                        pass
                # Delete the layout item itself
                del item
    
    def _build_summary_content(self, total_moves: int = 0, moves: Optional[List[MoveData]] = None) -> None:
        """Build the summary content widgets.
        
        Args:
            total_moves: Total number of moves in the game.
        """
        if not self.current_summary:
            return
        
        moves = moves or []
        
        # Get config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        summary_config = panel_config.get('summary', {})
        colors_config = summary_config.get('colors', {})
        fonts_config = summary_config.get('fonts', {})
        layout_config = summary_config.get('layout', {})
        widgets_config = summary_config.get('widgets', {})
        
        text_color = QColor(*colors_config.get('text_color', [220, 220, 220]))
        header_text_color = QColor(*colors_config.get('header_text', [240, 240, 240]))
        background_color = QColor(*colors_config.get('background', [40, 40, 45]))
        section_bg_color = QColor(*colors_config.get('section_background', [35, 35, 40]))
        border_color = QColor(*colors_config.get('border', [60, 60, 65]))
        
        # Widget styling configuration
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)
        grid_spacing = widgets_config.get('grid_spacing', 5)
        classification_widget_spacing = widgets_config.get('classification_widget_spacing', 10)
        counts_layout_spacing = widgets_config.get('counts_layout_spacing', 3)
        row_spacing = widgets_config.get('row_spacing', 5)
        color_indicator_size = widgets_config.get('color_indicator_size', [12, 12])
        critical_moments_list_spacing = widgets_config.get('critical_moments_list_spacing', 3)
        critical_moments_section_spacing = widgets_config.get('critical_moments_section_spacing', 10)
        phase_spacing = widgets_config.get('phase_spacing', 1)
        
        header_font = QFont(fonts_config.get('header_font_family', 'Helvetica Neue'),
                           int(scale_font_size(fonts_config.get('header_font_size', 14))))
        header_font.setBold(fonts_config.get('header_font_weight', 'bold') == 'bold')
        label_font = QFont(fonts_config.get('label_font_family', 'Helvetica Neue'),
                          int(scale_font_size(fonts_config.get('label_font_size', 11))))
        value_font = QFont(fonts_config.get('value_font_family', 'Helvetica Neue'),
                          int(scale_font_size(fonts_config.get('value_font_size', 11))))
        
        section_spacing = layout_config.get('section_spacing', 20)
        player_spacing = layout_config.get('player_section_spacing', 10)
        
        # Get player names from game model and add sides
        # Defensive check: ensure we have valid game data
        if self._game_model and self._game_model.active_game:
            game = self._game_model.active_game
            # Safe access with fallbacks for None/empty values
            white_name_str = game.white if (game.white and game.white.strip()) else 'White'
            black_name_str = game.black if (game.black and game.black.strip()) else 'Black'
            white_name = f"{white_name_str} (White)"
            black_name = f"{black_name_str} (Black)"
        else:
            white_name = "White (White)"
            black_name = "Black (Black)"
        
        # Key Statistics Section
        self._add_section_header("Key Statistics", header_font, header_text_color)
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(player_spacing)
        
        # White statistics - defensive check for None stats
        if self.current_summary and self.current_summary.white_stats:
            white_stats_widget = self._create_player_stats_widget(
                white_name, self.current_summary.white_stats, 
                text_color, label_font, value_font, section_bg_color, border_color,
                is_white=True
            )
            stats_layout.addWidget(white_stats_widget)
        
        # Black statistics - defensive check for None stats
        if self.current_summary and self.current_summary.black_stats:
            black_stats_widget = self._create_player_stats_widget(
                black_name, self.current_summary.black_stats,
                text_color, label_font, value_font, section_bg_color, border_color,
                is_white=False
            )
            stats_layout.addWidget(black_stats_widget)
        
        stats_container = QWidget()
        stats_container.setLayout(stats_layout)
        self.content_layout.addWidget(stats_container)
        
        self.content_layout.addSpacing(section_spacing)
        
        # Move Classification Section
        self._add_section_header("Move Classification", header_font, header_text_color)
        classification_layout = QHBoxLayout()
        classification_layout.setSpacing(player_spacing)
        
        # White pie chart - defensive check for None stats
        if self.current_summary and self.current_summary.white_stats:
            white_pie_data = {
                'Book Move': self.current_summary.white_stats.book_moves or 0,
                'Brilliant': self.current_summary.white_stats.brilliant_moves or 0,
                'Best Move': self.current_summary.white_stats.best_moves or 0,
                'Good Move': self.current_summary.white_stats.good_moves or 0,
                'Inaccuracy': self.current_summary.white_stats.inaccuracies or 0,
                'Mistake': self.current_summary.white_stats.mistakes or 0,
                'Miss': self.current_summary.white_stats.misses or 0,
                'Blunder': self.current_summary.white_stats.blunders or 0,
            }
            white_pie_widget = self._create_classification_widget(
                white_name, white_pie_data, self.current_summary.white_stats,
                text_color, label_font, section_bg_color, border_color,
                is_white=True
            )
            classification_layout.addWidget(white_pie_widget)
        
        # Black pie chart - defensive check for None stats
        if self.current_summary and self.current_summary.black_stats:
            black_pie_data = {
                'Book Move': self.current_summary.black_stats.book_moves or 0,
                'Brilliant': self.current_summary.black_stats.brilliant_moves or 0,
                'Best Move': self.current_summary.black_stats.best_moves or 0,
                'Good Move': self.current_summary.black_stats.good_moves or 0,
                'Inaccuracy': self.current_summary.black_stats.inaccuracies or 0,
                'Mistake': self.current_summary.black_stats.mistakes or 0,
                'Miss': self.current_summary.black_stats.misses or 0,
                'Blunder': self.current_summary.black_stats.blunders or 0,
            }
            black_pie_widget = self._create_classification_widget(
                black_name, black_pie_data, self.current_summary.black_stats,
                text_color, label_font, section_bg_color, border_color,
                is_white=False
            )
            classification_layout.addWidget(black_pie_widget)
        
        classification_container = QWidget()
        classification_container.setLayout(classification_layout)
        self.content_layout.addWidget(classification_container)
        
        self.content_layout.addSpacing(section_spacing)
        
        # Phase Analysis Section
        self._add_section_header("Phase Analysis", header_font, header_text_color)
        phase_layout = QHBoxLayout()
        phase_layout.setSpacing(player_spacing)
        
        # White phase analysis - defensive check for None phase stats
        if (self.current_summary and 
            self.current_summary.white_opening and 
            self.current_summary.white_middlegame and 
            self.current_summary.white_endgame):
            white_phase_widget = self._create_phase_analysis_widget(
                white_name, 
                self.current_summary.white_opening,
                self.current_summary.white_middlegame,
                self.current_summary.white_endgame,
                text_color, label_font, value_font, section_bg_color, border_color,
                is_white=True,
                endgame_type=self.current_summary.endgame_type if self.current_summary else None,
                opening_end=self.current_summary.opening_end if self.current_summary else 0,
                middlegame_end=self.current_summary.middlegame_end if self.current_summary else 0,
                game_controller=self._game_controller,
                total_moves=total_moves,
                moves=moves
            )
            phase_layout.addWidget(white_phase_widget)
        
        # Black phase analysis - defensive check for None phase stats
        if (self.current_summary and 
            self.current_summary.black_opening and 
            self.current_summary.black_middlegame and 
            self.current_summary.black_endgame):
            black_phase_widget = self._create_phase_analysis_widget(
                black_name,
                self.current_summary.black_opening,
                self.current_summary.black_middlegame,
                self.current_summary.black_endgame,
                text_color, label_font, value_font, section_bg_color, border_color,
                is_white=False,
                endgame_type=self.current_summary.endgame_type if self.current_summary else None,
                opening_end=self.current_summary.opening_end if self.current_summary else 0,
                middlegame_end=self.current_summary.middlegame_end if self.current_summary else 0,
                game_controller=self._game_controller,
                total_moves=total_moves,
                moves=moves
            )
            phase_layout.addWidget(black_phase_widget)
        
        phase_container = QWidget()
        phase_container.setLayout(phase_layout)
        self.content_layout.addWidget(phase_container)
        
        self.content_layout.addSpacing(section_spacing)
        
        # Game Highlights Section
        if self.current_summary and self.current_summary.highlights:
            self._add_section_header("Game Highlights", header_font, header_text_color)
            highlights_widget = self._create_highlights_widget(
                self.current_summary.highlights,
                self.current_summary.opening_end,
                self.current_summary.middlegame_end,
                text_color, label_font, value_font, section_bg_color, border_color
            )
            
            # Create a container with matching left/right padding to align with 2-column sections
            # The critical moments widgets have section_margins, so we add matching padding
            highlights_container = QWidget()
            highlights_container_layout = QVBoxLayout(highlights_container)
            # Add same-size left and right padding matching the left margin of section_margins
            # This aligns the content with the visual boundaries of the 2-column sections
            padding = section_margins[3]  # Left margin from section_margins (typically same as right)
            highlights_container_layout.setContentsMargins(padding, 0, padding, 0)
            highlights_container_layout.setSpacing(0)
            
            # Ensure highlights_widget doesn't force expansion
            highlights_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            highlights_widget.setMinimumWidth(0)
            
            highlights_container_layout.addWidget(highlights_widget)
            
            self.content_layout.addWidget(highlights_container)
            self.content_layout.addSpacing(section_spacing)
        
        # Critical Moments Section
        self._add_section_header("Critical Moments", header_font, header_text_color)
        critical_layout = QHBoxLayout()
        critical_layout.setSpacing(player_spacing)
        
        # White critical moments - defensive check for None lists
        if (self.current_summary and 
            self.current_summary.white_top_worst is not None and 
            self.current_summary.white_top_best is not None):
            white_critical_widget = self._create_critical_moments_widget(
                white_name,
                self.current_summary.white_top_worst or [],
                self.current_summary.white_top_best or [],
                text_color, label_font, value_font, section_bg_color, border_color,
                is_white=True
            )
            critical_layout.addWidget(white_critical_widget)
        
        # Black critical moments - defensive check for None lists
        if (self.current_summary and 
            self.current_summary.black_top_worst is not None and 
            self.current_summary.black_top_best is not None):
            black_critical_widget = self._create_critical_moments_widget(
                black_name,
                self.current_summary.black_top_worst or [],
                self.current_summary.black_top_best or [],
                text_color, label_font, value_font, section_bg_color, border_color,
                is_white=False
            )
            critical_layout.addWidget(black_critical_widget)
        
        critical_container = QWidget()
        critical_container.setLayout(critical_layout)
        self.content_layout.addWidget(critical_container)
        
        self.content_layout.addSpacing(section_spacing)
        
        # Add stretch at end
        self.content_layout.addStretch()
    
    def _add_section_header(self, text: str, font: QFont, color: QColor) -> None:
        """Add a section header label.
        
        Args:
            text: Header text.
            font: Font to use.
            color: Text color.
        """
        header = QLabel(text)
        header.setFont(font)
        header.setStyleSheet(f"color: rgb({color.red()}, {color.green()}, {color.blue()}); border: none;")
        self.content_layout.addWidget(header)
    
    def _create_player_stats_widget(self, player_name: str, stats,
                                    text_color: QColor, label_font: QFont, value_font: QFont,
                                    bg_color: QColor, border_color: QColor,
                                    is_white: bool = True) -> QWidget:
        """Create a widget displaying player statistics.
        
        Args:
            player_name: Player name.
            stats: PlayerStatistics instance.
            text_color: Text color.
            label_font: Font for labels.
            value_font: Font for values.
            bg_color: Background color.
            border_color: Border color.
            
        Returns:
            QWidget with player statistics.
        """
        # Get widget config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        summary_config = panel_config.get('summary', {})
        widgets_config = summary_config.get('widgets', {})
        
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)
        grid_spacing = widgets_config.get('grid_spacing', 5)
        
        # Get player name label styling
        player_name_config = widgets_config.get('player_name_label', {})
        side_config = player_name_config.get('white' if is_white else 'black', {})
        player_label_bg = QColor(*side_config.get('background_color', [240, 240, 240] if is_white else [30, 30, 30]))
        player_label_text = QColor(*side_config.get('text_color', [30, 30, 30] if is_white else [240, 240, 240]))
        player_label_border_radius = side_config.get('border_radius', 3)
        player_label_padding = side_config.get('padding', [6, 4, 6, 4])
        player_label_font_weight = side_config.get('font_weight', 'bold')
        
        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color.red()}, {bg_color.green()}, {bg_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {border_radius}px;
            }}
        """)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], section_margins[3])
        layout.setSpacing(section_spacing)
        
        # Player name header with side-specific styling
        name_label = QLabel(player_name)
        name_label.setFont(label_font)
        name_label.setStyleSheet(f"""
            QLabel {{
                background-color: rgb({player_label_bg.red()}, {player_label_bg.green()}, {player_label_bg.blue()});
                color: rgb({player_label_text.red()}, {player_label_text.green()}, {player_label_text.blue()});
                font-weight: {player_label_font_weight};
                border-radius: {player_label_border_radius}px;
                padding: {player_label_padding[0]}px {player_label_padding[1]}px {player_label_padding[2]}px {player_label_padding[3]}px;
            }}
        """)
        layout.addWidget(name_label)
        
        # Statistics grid
        grid = QGridLayout()
        grid.setSpacing(grid_spacing)
        
        # ACPL - defensive check for None/invalid values
        avg_cpl = stats.average_cpl if stats.average_cpl is not None else 0.0
        self._add_stat_row(grid, 0, "Average CPL:", f"{avg_cpl:.1f}", label_font, value_font, text_color)
        # Accuracy - defensive check for None/invalid values
        accuracy = stats.accuracy if stats.accuracy is not None else 0.0
        self._add_stat_row(grid, 1, "Accuracy:", f"{accuracy:.1f}%", label_font, value_font, text_color)
        # Estimated Elo - defensive check for None/invalid values
        est_elo = stats.estimated_elo if stats.estimated_elo is not None else 0
        self._add_stat_row(grid, 2, "Est. Elo:", str(est_elo), label_font, value_font, text_color)
        # Total Moves - defensive check for None/invalid values
        total_moves = stats.total_moves if stats.total_moves is not None else 0
        self._add_stat_row(grid, 3, "Total Moves:", str(total_moves), label_font, value_font, text_color)
        # Best Move % - defensive check for None/invalid values
        best_move_pct = stats.best_move_percentage if stats.best_move_percentage is not None else 0.0
        self._add_stat_row(grid, 4, "Best Move %:", f"{best_move_pct:.1f}%", label_font, value_font, text_color)
        # Top3-Move Accuracy - defensive check for None/invalid values
        top3_move_pct = stats.top3_move_percentage if stats.top3_move_percentage is not None else 0.0
        self._add_stat_row(grid, 5, "Top3-Move Accuracy:", f"{top3_move_pct:.1f}%", label_font, value_font, text_color)
        # Blunder Rate - defensive check for None/invalid values
        blunder_rate = stats.blunder_rate if stats.blunder_rate is not None else 0.0
        self._add_stat_row(grid, 6, "Blunder Rate:", f"{blunder_rate:.1f}%", label_font, value_font, text_color)
        
        layout.addLayout(grid)
        layout.addStretch()
        
        return widget
    
    def _add_stat_row(self, grid: QGridLayout, row: int, label_text: str, value_text: str,
                     label_font: QFont, value_font: QFont, text_color: QColor) -> None:
        """Add a statistics row to a grid.
        
        Args:
            grid: QGridLayout to add to.
            row: Row index.
            label_text: Label text.
            value_text: Value text.
            label_font: Font for label.
            value_font: Font for value.
            text_color: Text color.
        """
        label = QLabel(label_text)
        label.setFont(label_font)
        label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
        grid.addWidget(label, row, 0)
        
        value = QLabel(value_text)
        value.setFont(value_font)
        value.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
        grid.addWidget(value, row, 1)
    
    def _create_classification_widget(self, player_name: str, pie_data: Dict[str, int], stats,
                                     text_color: QColor, label_font: QFont,
                                     bg_color: QColor, border_color: QColor,
                                     is_white: bool = True) -> QWidget:
        """Create a widget with pie chart and move counts.
        
        Args:
            player_name: Player name.
            pie_data: Dictionary mapping categories to counts.
            stats: PlayerStatistics instance.
            text_color: Text color.
            label_font: Font for labels.
            bg_color: Background color.
            border_color: Border color.
            
        Returns:
            QWidget with pie chart and counts.
        """
        # Get widget config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        summary_config = panel_config.get('summary', {})
        widgets_config = summary_config.get('widgets', {})
        
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        classification_widget_spacing = widgets_config.get('classification_widget_spacing', 10)
        counts_layout_spacing = widgets_config.get('counts_layout_spacing', 3)
        row_spacing = widgets_config.get('row_spacing', 5)
        color_indicator_size = widgets_config.get('color_indicator_size', [12, 12])
        
        # Get player name label styling
        player_name_config = widgets_config.get('player_name_label', {})
        side_config = player_name_config.get('white' if is_white else 'black', {})
        player_label_bg = QColor(*side_config.get('background_color', [240, 240, 240] if is_white else [30, 30, 30]))
        player_label_text = QColor(*side_config.get('text_color', [30, 30, 30] if is_white else [240, 240, 240]))
        player_label_border_radius = side_config.get('border_radius', 3)
        player_label_padding = side_config.get('padding', [6, 4, 6, 4])
        player_label_font_weight = side_config.get('font_weight', 'bold')
        
        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color.red()}, {bg_color.green()}, {bg_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {border_radius}px;
            }}
        """)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], section_margins[3])
        layout.setSpacing(classification_widget_spacing)
        
        # Player name header with side-specific styling
        name_label = QLabel(player_name)
        name_label.setFont(label_font)
        name_label.setStyleSheet(f"""
            QLabel {{
                background-color: rgb({player_label_bg.red()}, {player_label_bg.green()}, {player_label_bg.blue()});
                color: rgb({player_label_text.red()}, {player_label_text.green()}, {player_label_text.blue()});
                font-weight: {player_label_font_weight};
                border-radius: {player_label_border_radius}px;
                padding: {player_label_padding[0]}px {player_label_padding[1]}px {player_label_padding[2]}px {player_label_padding[3]}px;
            }}
        """)
        layout.addWidget(name_label)
        
        # Pie chart
        pie_chart = PieChartWidget(self.config)
        pie_chart.set_data(pie_data)
        layout.addWidget(pie_chart)
        
        # Move counts list
        counts_layout = QVBoxLayout()
        counts_layout.setSpacing(counts_layout_spacing)
        
        # Get colors from config
        colors_config = summary_config.get('colors', {})
        
        categories = [
            ('Book Move', stats.book_moves, colors_config.get('book_move', [150, 150, 150])),
            ('Brilliant', stats.brilliant_moves, colors_config.get('brilliant', [255, 215, 0])),
            ('Best Move', stats.best_moves, colors_config.get('best_move', [100, 255, 100])),
            ('Good Move', stats.good_moves, colors_config.get('good_move', [150, 255, 150])),
            ('Inaccuracy', stats.inaccuracies, colors_config.get('inaccuracy', [255, 255, 100])),
            ('Mistake', stats.mistakes, colors_config.get('mistake', [255, 200, 100])),
            ('Miss', stats.misses, colors_config.get('miss', [200, 100, 255])),
            ('Blunder', stats.blunders, colors_config.get('blunder', [255, 100, 100])),
        ]
        
        for category, count, color in categories:
            # Defensive check: ensure count is valid and > 0
            count_val = count if count is not None else 0
            if count_val > 0:
                row = QHBoxLayout()
                row.setSpacing(row_spacing)
                
                # Color indicator - defensive check for color tuple
                color_widget = QWidget()
                color_widget.setFixedSize(color_indicator_size[0], color_indicator_size[1])
                # Ensure color is a valid tuple/list with 3 elements
                color_r = color[0] if isinstance(color, (list, tuple)) and len(color) >= 1 else 150
                color_g = color[1] if isinstance(color, (list, tuple)) and len(color) >= 2 else 150
                color_b = color[2] if isinstance(color, (list, tuple)) and len(color) >= 3 else 150
                color_widget.setStyleSheet(f"""
                    QWidget {{
                        background-color: rgb({color_r}, {color_g}, {color_b});
                        border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                    }}
                """)
                row.addWidget(color_widget)
                
                # Label
                label = QLabel(f"{category}: {count_val}")
                label.setFont(label_font)
                label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
                row.addWidget(label)
                
                row.addStretch()
                counts_layout.addLayout(row)
        
        layout.addLayout(counts_layout)
        layout.addStretch()
        
        return widget
    
    def _create_phase_analysis_widget(self, player_name: str, opening, middlegame, endgame,
                                     text_color: QColor, label_font: QFont, value_font: QFont,
                                     bg_color: QColor, border_color: QColor,
                                     is_white: bool = True, endgame_type: Optional[str] = None,
                                     opening_end: int = 0, middlegame_end: int = 0,
                                     game_controller: Optional[GameController] = None,
                                     total_moves: int = 0, moves: List = None) -> QWidget:
        """Create a widget displaying phase analysis.
        
        Args:
            player_name: Player name.
            opening: PhaseStatistics for opening.
            middlegame: PhaseStatistics for middlegame.
            endgame: PhaseStatistics for endgame.
            text_color: Text color.
            label_font: Font for labels.
            value_font: Font for values.
            bg_color: Background color.
            border_color: Border color.
            
        Returns:
            QWidget with phase analysis.
        """
        # Get widget config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        summary_config = panel_config.get('summary', {})
        widgets_config = summary_config.get('widgets', {})
        
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)
        grid_spacing = widgets_config.get('grid_spacing', 5)
        phase_spacing = widgets_config.get('phase_spacing', 1)
        
        # Get player name label styling
        player_name_config = widgets_config.get('player_name_label', {})
        side_config = player_name_config.get('white' if is_white else 'black', {})
        player_label_bg = QColor(*side_config.get('background_color', [240, 240, 240] if is_white else [30, 30, 30]))
        player_label_text = QColor(*side_config.get('text_color', [30, 30, 30] if is_white else [240, 240, 240]))
        player_label_border_radius = side_config.get('border_radius', 3)
        player_label_padding = side_config.get('padding', [6, 4, 6, 4])
        player_label_font_weight = side_config.get('font_weight', 'bold')
        
        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color.red()}, {bg_color.green()}, {bg_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {border_radius}px;
            }}
        """)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], section_margins[3])
        layout.setSpacing(section_spacing)
        
        # Player name header with side-specific styling
        name_label = QLabel(player_name)
        name_label.setFont(label_font)
        name_label.setStyleSheet(f"""
            QLabel {{
                background-color: rgb({player_label_bg.red()}, {player_label_bg.green()}, {player_label_bg.blue()});
                color: rgb({player_label_text.red()}, {player_label_text.green()}, {player_label_text.blue()});
                font-weight: {player_label_font_weight};
                border-radius: {player_label_border_radius}px;
                padding: {player_label_padding[0]}px {player_label_padding[1]}px {player_label_padding[2]}px {player_label_padding[3]}px;
            }}
        """)
        layout.addWidget(name_label)
        
        # Phase statistics grid
        grid = QGridLayout()
        grid.setSpacing(grid_spacing)
        
        row = 0
        for phase_name, phase_stats in [("Opening", opening), ("Middlegame", middlegame), ("Endgame", endgame)]:
            # Calculate move range for this phase (only for Opening and Middlegame)
            # Also store the actual move number to use for navigation
            actual_move_number = 0
            if phase_name == "Opening":
                move_range = f"(.. move {opening_end})" if opening_end > 0 else ""
                actual_move_number = opening_end
            elif phase_name == "Middlegame":
                # If middlegame_end > total_moves, it means there's no endgame, so show the actual last move
                display_move = min(middlegame_end, total_moves) if total_moves > 0 else middlegame_end
                move_range = f"(.. move {display_move})" if display_move > 0 else ""
                # Store display_move for use in clickable label (use displayed move, not middlegame_end)
                actual_move_number = display_move
            else:  # Endgame - no move count
                move_range = ""
            
            # Phase header with move count
            if phase_name == "Endgame":
                # For endgame, show type on a separate line (no move count)
                if endgame_type:
                    if endgame_type == "Endgame":
                        # Catch-all: show "(undefined)"
                        phase_label_text = "Endgame\n(undefined)"
                    else:
                        # Specific type: show type name without "Endgame" suffix
                        phase_label_text = f"Endgame\n({endgame_type})"
                else:
                    phase_label_text = "Endgame"
                
                phase_label = QLabel(phase_label_text)
                phase_label.setFont(label_font)
                phase_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); font-weight: bold; border: none;")
                grid.addWidget(phase_label, row, 0, 1, 2)
                row += 1
            else:
                # Opening and Middlegame: show phase name and clickable move count
                phase_header_layout = QHBoxLayout()
                phase_header_layout.setContentsMargins(0, 0, 0, 0)
                phase_header_layout.setSpacing(0)
                
                # Phase name label
                phase_name_label = QLabel(phase_name)
                phase_name_label.setFont(label_font)
                phase_name_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); font-weight: bold; border: none;")
                phase_header_layout.addWidget(phase_name_label)
                
                # Clickable move count (if available)
                if move_range and game_controller:
                    # Use the actual_move_number (which is the displayed move number)
                    move_number = actual_move_number
                    
                    # Determine which side made the move at the phase boundary
                    # Default to Black's move (most common case - phase boundaries typically end after Black's move)
                    is_white_move = False
                    if moves and move_number > 0 and move_number <= len(moves):
                        # Check the move at this move number (1-indexed, so subtract 1 for list index)
                        move_data = moves[move_number - 1]
                        # If the game ends at this move and only white_move exists, it's White's move
                        # This happens when the game ends on White's move (e.g., checkmate by White)
                        if move_number == total_moves and move_data.white_move and not move_data.black_move:
                            is_white_move = True
                        # Otherwise, phase boundaries typically end with Black's move
                        # (since a full move = white move + black move)
                    
                    # Move count is clickable - use ClickableMoveLabel
                    move_count_label = ClickableMoveLabel(
                        f" {move_range}",  # Include space before parentheses
                        move_number,
                        is_white_move,  # Determine based on actual move data
                        game_controller
                    )
                    move_count_label.setFont(label_font)
                    move_count_label.setFrameShape(QLabel.Shape.NoFrame)
                    move_count_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); font-weight: bold; border: none; background: transparent; padding: 0px; margin: 0px; text-decoration: underline;")
                    phase_header_layout.addWidget(move_count_label)
                elif move_range:
                    # Move count not clickable (no game controller)
                    move_count_label = QLabel(f" {move_range}")
                    move_count_label.setFont(label_font)
                    move_count_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); font-weight: bold; border: none;")
                    phase_header_layout.addWidget(move_count_label)
                
                phase_header_layout.addStretch()
                
                # Container widget for the header layout
                phase_header_widget = QWidget()
                phase_header_widget.setLayout(phase_header_layout)
                phase_header_widget.setStyleSheet("border: none; background: transparent;")
                grid.addWidget(phase_header_widget, row, 0, 1, 2)
                row += 1
            
            # Accuracy - show "-" if phase has no moves, otherwise show percentage
            if phase_stats.moves == 0:
                accuracy_str = "-"
            else:
                phase_accuracy = phase_stats.accuracy if phase_stats.accuracy is not None else 0.0
                accuracy_str = f"{phase_accuracy:.1f}%"
            self._add_stat_row(grid, row, "  Accuracy:", accuracy_str, label_font, value_font, text_color)
            row += 1
            # ACPL - defensive check for None/invalid values
            phase_acpl = phase_stats.average_cpl if phase_stats.average_cpl is not None else 0.0
            self._add_stat_row(grid, row, "  ACPL:", f"{phase_acpl:.1f}", label_font, value_font, text_color)
            row += 1
            
            # Add spacing after ACPL (before next phase header) - but not after the last phase
            if phase_name != "Endgame":
                # Add an empty spacer row to create visual spacing (no border)
                spacer_label = QLabel("")
                spacer_label.setFixedHeight(8)  # Fixed 8 pixel spacing
                spacer_label.setStyleSheet("border: none;")  # Ensure spacer has no border
                grid.addWidget(spacer_label, row, 0, 1, 2)
                row += 1
        
        layout.addLayout(grid)
        layout.addStretch()
        
        return widget
    
    def _create_critical_moments_widget(self, player_name: str, top_worst: List, top_best: List,
                                        text_color: QColor, label_font: QFont, value_font: QFont,
                                        bg_color: QColor, border_color: QColor,
                                        is_white: bool = True) -> QWidget:
        """Create a widget displaying critical moments.
        
        Args:
            player_name: Player name.
            top_worst: List of CriticalMove instances (top 3 worst).
            top_best: List of CriticalMove instances (top 3 best).
            text_color: Text color.
            label_font: Font for labels.
            value_font: Font for values.
            bg_color: Background color.
            border_color: Border color.
            
        Returns:
            QWidget with critical moments.
        """
        # Get widget config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        summary_config = panel_config.get('summary', {})
        widgets_config = summary_config.get('widgets', {})
        
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)
        critical_moments_list_spacing = widgets_config.get('critical_moments_list_spacing', 3)
        critical_moments_section_spacing = widgets_config.get('critical_moments_section_spacing', 10)
        
        # Get player name label styling
        player_name_config = widgets_config.get('player_name_label', {})
        side_config = player_name_config.get('white' if is_white else 'black', {})
        player_label_bg = QColor(*side_config.get('background_color', [240, 240, 240] if is_white else [30, 30, 30]))
        player_label_text = QColor(*side_config.get('text_color', [30, 30, 30] if is_white else [240, 240, 240]))
        player_label_border_radius = side_config.get('border_radius', 3)
        player_label_padding = side_config.get('padding', [6, 4, 6, 4])
        player_label_font_weight = side_config.get('font_weight', 'bold')
        
        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color.red()}, {bg_color.green()}, {bg_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {border_radius}px;
            }}
        """)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], section_margins[3])
        layout.setSpacing(section_spacing)
        
        # Player name header with side-specific styling
        name_label = QLabel(player_name)
        name_label.setFont(label_font)
        name_label.setStyleSheet(f"""
            QLabel {{
                background-color: rgb({player_label_bg.red()}, {player_label_bg.green()}, {player_label_bg.blue()});
                color: rgb({player_label_text.red()}, {player_label_text.green()}, {player_label_text.blue()});
                font-weight: {player_label_font_weight};
                border-radius: {player_label_border_radius}px;
                padding: {player_label_padding[0]}px {player_label_padding[1]}px {player_label_padding[2]}px {player_label_padding[3]}px;
            }}
        """)
        layout.addWidget(name_label)
        
        # Top 3 Worst Moves
        worst_label = QLabel("Top 3 Worst Moves")
        worst_label.setFont(label_font)
        worst_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); font-weight: bold; border: none;")
        layout.addWidget(worst_label)
        
        worst_layout = QVBoxLayout()
        worst_layout.setSpacing(critical_moments_list_spacing)
        for i, move in enumerate(top_worst[:3], 1):
            # Defensive checks for None/missing values in CriticalMove
            if not move:
                continue
            
            # Safe access to move attributes with fallbacks
            move_notation = move.move_notation if hasattr(move, 'move_notation') and move.move_notation else "N/A"
            assessment = move.assessment if hasattr(move, 'assessment') and move.assessment else "N/A"
            cpl = move.cpl if hasattr(move, 'cpl') and move.cpl is not None else 0.0
            move_number = move.move_number if hasattr(move, 'move_number') and move.move_number is not None else 1
            best_move = move.best_move if hasattr(move, 'best_move') and move.best_move else ""
            
            # Create a container widget with horizontal layout for the move line
            move_container = QWidget()
            move_container.setStyleSheet("border: none; background: transparent;")
            move_line_layout = QHBoxLayout(move_container)
            move_line_layout.setContentsMargins(0, 0, 0, 0)
            move_line_layout.setSpacing(0)
            
            # Prefix (e.g., "1. ")
            prefix_label = QLabel(f"{i}. ")
            prefix_label.setFont(value_font)
            prefix_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
            move_line_layout.addWidget(prefix_label)
            
            # Clickable move notation (e.g., "28. Rxd7")
            move_clickable = ClickableMoveLabel(move_notation, move_number, is_white, self._game_controller)
            move_clickable.setFont(value_font)
            move_clickable.setFrameShape(QLabel.Shape.NoFrame)
            base_style = f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent; padding: 0px; margin: 0px;"
            move_clickable.setStyleSheet(base_style + " text-decoration: underline;")
            move_line_layout.addWidget(move_clickable)
            
            # Assessment part (e.g., " (Blunder, CPL: 9463)")
            assessment_text = f" ({assessment}, CPL: {cpl:.0f})"
            assessment_label = QLabel(assessment_text)
            assessment_label.setFont(value_font)
            assessment_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
            move_line_layout.addWidget(assessment_label)
            
            move_line_layout.addStretch()
            
            # Create container for the full move entry (move line + best move line if available)
            full_move_container = QWidget()
            full_move_container.setStyleSheet("border: none; background: transparent;")
            full_move_layout = QVBoxLayout(full_move_container)
            full_move_layout.setContentsMargins(0, 0, 0, 0)
            full_move_layout.setSpacing(0)
            full_move_layout.addWidget(move_container)
            
            # Best move line if available
            if best_move:
                best_move_label = QLabel(f"   Best: {best_move}")
                best_move_label.setFont(value_font)
                best_move_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
                full_move_layout.addWidget(best_move_label)
            
            worst_layout.addWidget(full_move_container)
        layout.addLayout(worst_layout)
        
        layout.addSpacing(critical_moments_section_spacing)
        
        # Top 3 Best Moves
        best_label = QLabel("Top 3 Best Moves")
        best_label.setFont(label_font)
        best_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); font-weight: bold; border: none;")
        layout.addWidget(best_label)
        
        best_layout = QVBoxLayout()
        best_layout.setSpacing(critical_moments_list_spacing)
        for i, move in enumerate(top_best[:3], 1):
            # Defensive checks for None/missing values in CriticalMove
            if not move:
                continue
            
            # Safe access to move attributes with fallbacks
            move_notation = move.move_notation if hasattr(move, 'move_notation') and move.move_notation else "N/A"
            assessment = move.assessment if hasattr(move, 'assessment') and move.assessment else "N/A"
            cpl = move.cpl if hasattr(move, 'cpl') and move.cpl is not None else 0.0
            move_number = move.move_number if hasattr(move, 'move_number') and move.move_number is not None else 1
            
            # Create a container widget with horizontal layout for the move line
            move_container = QWidget()
            move_container.setStyleSheet("border: none; background: transparent;")
            move_line_layout = QHBoxLayout(move_container)
            move_line_layout.setContentsMargins(0, 0, 0, 0)
            move_line_layout.setSpacing(0)
            
            # Prefix (e.g., "1. ")
            prefix_label = QLabel(f"{i}. ")
            prefix_label.setFont(value_font)
            prefix_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
            move_line_layout.addWidget(prefix_label)
            
            # Clickable move notation (e.g., "5. d5")
            move_clickable = ClickableMoveLabel(move_notation, move_number, is_white, self._game_controller)
            move_clickable.setFont(value_font)
            move_clickable.setFrameShape(QLabel.Shape.NoFrame)
            base_style = f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent; padding: 0px; margin: 0px;"
            move_clickable.setStyleSheet(base_style + " text-decoration: underline;")
            move_line_layout.addWidget(move_clickable)
            
            # Assessment part (e.g., " (Best Move, CPL: 0)")
            assessment_text = f" ({assessment}, CPL: {cpl:.0f})"
            assessment_label = QLabel(assessment_text)
            assessment_label.setFont(value_font)
            assessment_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
            move_line_layout.addWidget(assessment_label)
            
            move_line_layout.addStretch()
            best_layout.addWidget(move_container)
        layout.addLayout(best_layout)
        
        layout.addStretch()
        
        return widget
    
    def _create_highlights_widget(self, highlights: List, opening_end: int, middlegame_end: int,
                                 text_color: QColor, label_font: QFont, value_font: QFont,
                                 bg_color: QColor, border_color: QColor) -> QWidget:
        """Create a widget displaying game highlights.
        
        Args:
            highlights: List of GameHighlight instances.
            opening_end: Move number where opening phase ends.
            middlegame_end: Move number where middlegame phase ends.
            text_color: Text color.
            label_font: Font for labels.
            value_font: Font for values.
            bg_color: Background color.
            border_color: Border color.
            
        Returns:
            QWidget with game highlights.
        """
        # Get widget config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        summary_config = panel_config.get('summary', {})
        widgets_config = summary_config.get('widgets', {})
        
        border_radius = widgets_config.get('border_radius', 5)
        section_margins = widgets_config.get('section_margins', [10, 10, 10, 10])
        section_spacing = widgets_config.get('section_spacing', 8)
        
        widget = QWidget()
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: rgb({bg_color.red()}, {bg_color.green()}, {bg_color.blue()});
                border: 1px solid rgb({border_color.red()}, {border_color.green()}, {border_color.blue()});
                border-radius: {border_radius}px;
            }}
        """)
        
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(section_margins[0], section_margins[1], section_margins[2], section_margins[3])
        layout.setSpacing(section_spacing)
        
        # Group highlights by phase
        if self._summary_controller:
            opening_highlights, middlegame_highlights, endgame_highlights = self._summary_controller.partition_highlights_by_phase(
                highlights, opening_end, middlegame_end
            )
        else:
            opening_highlights = [h for h in highlights if h.move_number <= opening_end]
            middlegame_highlights = [h for h in highlights if opening_end < h.move_number < middlegame_end]
            endgame_highlights = [h for h in highlights if h.move_number >= middlegame_end]
        
        # Calculate minimum move column width once for consistent alignment
        font_metrics = QFontMetrics(value_font)
        sample_text = "99. O-O-O ... O-O-O"
        min_move_width = font_metrics.horizontalAdvance(sample_text) + 8  # Add some padding
        
        # Opening Phase
        if opening_highlights:
            opening_header = QLabel("Opening Phase")
            opening_header.setFont(label_font)
            opening_header.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); font-weight: bold; border: none;")
            layout.addWidget(opening_header)
            
            opening_layout = QVBoxLayout()
            opening_layout.setSpacing(5)
            for highlight in opening_highlights:
                highlight_widget = self._create_highlight_item(highlight, text_color, value_font, min_move_width)
                opening_layout.addWidget(highlight_widget)
            layout.addLayout(opening_layout)
            
            if middlegame_highlights or endgame_highlights:
                layout.addSpacing(section_spacing)
        
        # Middlegame Phase
        if middlegame_highlights:
            middlegame_header = QLabel("Middlegame Phase")
            middlegame_header.setFont(label_font)
            middlegame_header.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); font-weight: bold; border: none;")
            layout.addWidget(middlegame_header)
            
            middlegame_layout = QVBoxLayout()
            middlegame_layout.setSpacing(5)
            for highlight in middlegame_highlights:
                highlight_widget = self._create_highlight_item(highlight, text_color, value_font, min_move_width)
                middlegame_layout.addWidget(highlight_widget)
            layout.addLayout(middlegame_layout)
            
            if endgame_highlights:
                layout.addSpacing(section_spacing)
        
        # Endgame Phase
        if endgame_highlights:
            endgame_header = QLabel("Endgame Phase")
            endgame_header.setFont(label_font)
            endgame_header.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); font-weight: bold; border: none;")
            layout.addWidget(endgame_header)
            
            endgame_layout = QVBoxLayout()
            endgame_layout.setSpacing(5)
            for highlight in endgame_highlights:
                highlight_widget = self._create_highlight_item(highlight, text_color, value_font, min_move_width)
                endgame_layout.addWidget(highlight_widget)
            layout.addLayout(endgame_layout)
        
        layout.addStretch()
        
        return widget
    
    def _create_highlight_item(self, highlight, text_color: QColor, value_font: QFont, min_move_width: int) -> QWidget:
        """Create a single highlight item widget.
        
        Args:
            highlight: GameHighlight instance.
            text_color: Text color.
            value_font: Font for text.
            min_move_width: Minimum width for move column to ensure alignment.
            
        Returns:
            QWidget with highlight item.
        """
        container = QWidget()
        container.setStyleSheet("border: none; background: transparent;")
        
        layout = QGridLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(2)
        
        # Bullet point
        bullet = QLabel("•")
        bullet.setFont(value_font)
        bullet.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
        layout.addWidget(bullet, 0, 0, Qt.AlignmentFlag.AlignTop)
        
        # Move notation (clickable) contained in its own widget for consistent width
        move_container = QWidget()
        move_container.setStyleSheet("border: none; background: transparent;")
        move_layout = QHBoxLayout(move_container)
        move_layout.setContentsMargins(0, 0, 0, 0)
        move_layout.setSpacing(4)
        move_container.setMinimumWidth(min_move_width)
        move_container.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        
        # Parse move_notation to extract clickable parts
        # Format: "12. Nxc3" or "18. Rxd8 ... Rxd8" (for exchanges)
        if " ... " in highlight.move_notation:
            # Multi-move highlight (exchange sequence)
            parts = highlight.move_notation.split(" ... ")
            if len(parts) == 2:
                # First move (white)
                move_label1 = ClickableMoveLabel(
                    parts[0],  # e.g., "18. Rxd8"
                    highlight.move_number,
                    highlight.is_white,
                    self._game_controller
                )
                move_label1.setFont(value_font)
                move_label1.setFrameShape(QLabel.Shape.NoFrame)
                move_label1.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent; padding: 0px; margin: 0px; text-decoration: underline;")
                move_layout.addWidget(move_label1)
                
                # Separator
                separator = QLabel("...")
                separator.setFont(value_font)
                separator.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent;")
                move_layout.addWidget(separator)
                
                # Second move (black)
                move_label2 = ClickableMoveLabel(
                    parts[1],  # e.g., "Rxd8"
                    highlight.move_number,
                    not highlight.is_white,  # Opposite color for second move
                    self._game_controller
                )
                move_label2.setFont(value_font)
                move_label2.setFrameShape(QLabel.Shape.NoFrame)
                move_label2.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent; padding: 0px; margin: 0px; text-decoration: underline;")
                move_layout.addWidget(move_label2)
            else:
                # Fallback: treat as single move
                move_label = ClickableMoveLabel(
                    highlight.move_notation,
                    highlight.move_number,
                    highlight.is_white,
                    self._game_controller
                )
                move_label.setFont(value_font)
                move_label.setFrameShape(QLabel.Shape.NoFrame)
                move_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent; padding: 0px; margin: 0px; text-decoration: underline;")
                move_layout.addWidget(move_label)
        else:
            # Single move highlight
            move_label = ClickableMoveLabel(
                highlight.move_notation,
                highlight.move_number,
                highlight.is_white,
                self._game_controller
            )
            move_label.setFont(value_font)
            move_label.setFrameShape(QLabel.Shape.NoFrame)
            move_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none; background: transparent; padding: 0px; margin: 0px; text-decoration: underline;")
            move_layout.addWidget(move_label)
        
        layout.addWidget(move_container, 0, 1, Qt.AlignmentFlag.AlignTop)
        
        # Description text (non-clickable) with word wrap
        description_label = QLabel(highlight.description)
        description_label.setFont(value_font)
        description_label.setWordWrap(True)
        description_label.setStyleSheet(f"color: rgb({text_color.red()}, {text_color.green()}, {text_color.blue()}); border: none;")
        description_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(description_label, 0, 2, Qt.AlignmentFlag.AlignTop)
        layout.setColumnStretch(2, 1)
        
        return container

