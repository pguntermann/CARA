"""Chess board widget displaying an 8x8 grid with coordinates."""

from PyQt6.QtWidgets import QWidget, QGridLayout, QLabel, QToolTip
from app.utils.rule_explanation_formatter import RuleExplanationFormatter
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPolygon, QPolygonF, QMouseEvent, QFontMetrics, QPainterPath
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import Qt, QRect, QRectF, QPointF, QTimer, QPoint
from pathlib import Path
import sys
import chess
from typing import Dict, Any, Optional, List

from app.models.board_model import BoardModel
from app.models.evaluation_model import EvaluationModel
from app.models.annotation_model import AnnotationModel, Annotation, AnnotationType
from app.views.material_widget import MaterialWidget
from app.views.evaluation_bar_widget import EvaluationBarWidget
from app.services.logging_service import LoggingService


class ChessBoardWidget(QWidget):
    """Chess board widget displaying a configurable 8x8 board."""
    
    def __init__(self, config: Dict[str, Any], board_model: Optional[BoardModel] = None,
                 evaluation_model: Optional[EvaluationModel] = None) -> None:
        """Initialize the chess board widget.
        
        Args:
            config: Configuration dictionary.
            board_model: Optional BoardModel to observe.
                        If provided, widget will automatically update when model changes.
            evaluation_model: Optional EvaluationModel to observe.
        """
        super().__init__()
        self.config = config
        self._board_model: Optional[BoardModel] = None
        self._evaluation_model: Optional[EvaluationModel] = evaluation_model
        self._load_config()
        self._setup_board()
        
        # Enable mouse tracking for hover tooltips
        self.setMouseTracking(True)
        
        # Create evaluation bar widget (attached to left side of board)
        self.evaluation_bar = EvaluationBarWidget(self.config, self._evaluation_model)
        self.evaluation_bar.setParent(self)
        self.evaluation_bar.setVisible(False)
        
        # Create material widget (attached to upper right of board)
        # Note: board_model will be set later in set_model()
        self.material_widget = MaterialWidget(self.config, None)
        self.material_widget.setParent(self)
        self.material_widget.setVisible(False)
        
        # Create positional heat-map overlay (will be set later via set_positional_heatmap_model)
        self.positional_heatmap_overlay = None
        self.positional_heatmap_controller = None  # Will be set later for hover tooltips
        
        # Annotation model reference (set by annotation controller)
        self._annotation_model: Optional[AnnotationModel] = None
        self._annotation_controller = None  # Set by annotation controller for mouse events
        self._game_model = None  # Game model reference for getting current ply
        
        # Arrow preview state (for drag preview)
        self._arrow_preview_from: Optional[str] = None
        self._arrow_preview_to: Optional[str] = None
        self._arrow_preview_color: Optional[list[int]] = None
        self._arrow_preview_size: float = 1.0
        
        # Text annotation editing state
        self._hovered_text_id: Optional[str] = None  # ID of text annotation being hovered
        self._editing_text_id: Optional[str] = None  # ID of text annotation being edited
        self._edit_mode: Optional[str] = None  # "move", "resize", "rotate"
        self._edit_start_pos: Optional[QPoint] = None  # Mouse position when edit started
        self._edit_start_params: Optional[Dict[str, float]] = None  # Initial annotation params when edit started
        self._single_click_timer: Optional[QTimer] = None  # Timer to delay single-click handling
        self._pending_click_pos: Optional[QPoint] = None  # Position of pending single-click
        self._pending_click_annotation_id: Optional[str] = None  # Annotation ID of pending click
        
        # Connect to model if provided
        # Set model after setup so it can load position from model
        if board_model:
            self.set_model(board_model)
        else:
            # If no model provided, use fallback starting position
            self._initialize_starting_position()
        
        # Initialize turn indicator state
        self._is_white_turn = True
        self.show_turn_indicator = True  # Default visibility state
        self.show_playedmove_arrow = True  # Default visibility state
        self.show_bestnextmove_arrow = True  # Default visibility state
        self.show_pv2_arrow = True  # Default visibility state
        self.show_pv3_arrow = True  # Default visibility state
        self.show_bestalternativemove_arrow = True  # Default visibility state
        self._last_move: Optional[chess.Move] = None  # Track last move for arrow drawing
        self._best_next_move: Optional[chess.Move] = None  # Track best next move for arrow drawing
        self._pv2_move: Optional[chess.Move] = None  # Track PV2 move for arrow drawing
        self._pv3_move: Optional[chess.Move] = None  # Track PV3 move for arrow drawing
        self._best_alternative_move: Optional[chess.Move] = None  # Track best alternative move for arrow drawing
    
    def _load_config(self) -> None:
        """Load configuration for the chessboard."""
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('main', {})
        board_config = panel_config.get('board', {})
        
        # Padding
        self.padding = board_config.get('padding', [20, 20, 20, 20])
        
        # Border
        border_config = board_config.get('border', {})
        self.border_size = border_config.get('size', 2)
        self.border_color = border_config.get('color', [60, 60, 65])
        
        # Square colors
        squares_config = board_config.get('squares', {})
        self.light_square_color = squares_config.get('light_color', [240, 217, 181])
        self.dark_square_color = squares_config.get('dark_color', [181, 136, 99])
        
        # Coordinates
        coords_config = board_config.get('coordinates', {})
        self.show_coordinates = coords_config.get('show', True)
        self.coord_border_width = coords_config.get('border_width', 25)
        from app.utils.font_utils import resolve_font_family, scale_font_size
        self.coord_font_family = resolve_font_family(coords_config.get('font_family', 'Helvetica Neue'))
        self.coord_font_size = int(scale_font_size(coords_config.get('font_size', 10)))
        self.coord_color = coords_config.get('color', [200, 200, 200])
        self.coord_font_style = coords_config.get('font_style', 'normal')
        
        # Pieces
        pieces_config = board_config.get('pieces', {})
        self.svg_path = pieces_config.get('svg_path', 'resources/chesspieces/default')
        
        # Turn indicator
        indicator_config = board_config.get('turn_indicator', {})
        self.indicator_size = indicator_config.get('size', 16)
        self.indicator_padding = indicator_config.get('padding', [0, 0, 10, 10])
        self.indicator_white_color = indicator_config.get('white_color', [250, 250, 250])
        self.indicator_black_color = indicator_config.get('black_color', [40, 40, 40])
        
        # Played move arrow
        playedmove_arrow_config = board_config.get('playedmove_arrow', {})
        self.playedmove_arrow_color = playedmove_arrow_config.get('color', [255, 255, 0])
        
        # Best next move arrow
        bestnextmove_arrow_config = board_config.get('bestnextmove_arrow', {})
        self.bestnextmove_arrow_color = bestnextmove_arrow_config.get('color', [0, 0, 255])
        
        # PV2 arrow
        pv2_arrow_config = board_config.get('pv2_arrow', {})
        self.pv2_arrow_color = pv2_arrow_config.get('color', [100, 150, 255])
        
        # PV3 arrow
        pv3_arrow_config = board_config.get('pv3_arrow', {})
        self.pv3_arrow_color = pv3_arrow_config.get('color', [150, 150, 150])
        
        # Best alternative move arrow
        bestalternativemove_arrow_config = board_config.get('bestalternativemove_arrow', {})
        self.bestalternativemove_arrow_color = bestalternativemove_arrow_config.get('color', [200, 0, 100])
        
        # Evaluation bar padding
        eval_bar_config = board_config.get('evaluation_bar', {})
        self.eval_bar_padding_left = eval_bar_config.get('padding_left', 40)
        
        # Positional plans - load configs for up to 3 trajectories
        positional_plans_config = board_config.get('positional_plans', {})
        # Check user settings first, then fall back to config default
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        user_settings = settings_service.get_settings()
        board_visibility = user_settings.get('board_visibility', {})
        use_straight_lines = board_visibility.get('use_straight_lines')
        if use_straight_lines is None:
            # Fallback to config default
            use_straight_lines = positional_plans_config.get('use_straight_lines', False)
        self.trajectory_use_straight_lines = use_straight_lines
        
        # Trajectory 1 (most moved piece)
        trajectory_config = positional_plans_config.get('trajectory', {})
        self.trajectory_line_width_start = trajectory_config.get('line_width_start', 2)
        self.trajectory_line_width_end = trajectory_config.get('line_width_end', 6)
        self.trajectory_opacity_start = trajectory_config.get('opacity_start', 0.4)
        self.trajectory_opacity_end = trajectory_config.get('opacity_end', 1.0)
        self.trajectory_color_start = trajectory_config.get('color_start', [100, 150, 255])
        self.trajectory_color_end = trajectory_config.get('color_end', [0, 100, 255])
        self.trajectory_curve_factor = trajectory_config.get('curve_factor', 0.3)
        
        # Trajectory 2 (second most moved piece)
        trajectory_2_config = positional_plans_config.get('trajectory_2', {})
        self.trajectory_2_line_width_start = trajectory_2_config.get('line_width_start', 2)
        self.trajectory_2_line_width_end = trajectory_2_config.get('line_width_end', 6)
        self.trajectory_2_opacity_start = trajectory_2_config.get('opacity_start', 0.4)
        self.trajectory_2_opacity_end = trajectory_2_config.get('opacity_end', 1.0)
        self.trajectory_2_color_start = trajectory_2_config.get('color_start', [150, 100, 255])
        self.trajectory_2_color_end = trajectory_2_config.get('color_end', [100, 0, 255])
        self.trajectory_2_curve_factor = trajectory_2_config.get('curve_factor', 0.3)
        
        # Trajectory 3 (third most moved piece)
        trajectory_3_config = positional_plans_config.get('trajectory_3', {})
        self.trajectory_3_line_width_start = trajectory_3_config.get('line_width_start', 2)
        self.trajectory_3_line_width_end = trajectory_3_config.get('line_width_end', 6)
        self.trajectory_3_opacity_start = trajectory_3_config.get('opacity_start', 0.4)
        self.trajectory_3_opacity_end = trajectory_3_config.get('opacity_end', 1.0)
        self.trajectory_3_color_start = trajectory_3_config.get('color_start', [255, 150, 100])
        self.trajectory_3_color_end = trajectory_3_config.get('color_end', [255, 100, 0])
        self.trajectory_3_curve_factor = trajectory_3_config.get('curve_factor', 0.3)
        
        # Markers for trajectory 1
        numbered_markers_config = positional_plans_config.get('numbered_markers', {})
        self.markers_enabled = numbered_markers_config.get('enabled', True)
        self.marker_font_size = int(scale_font_size(numbered_markers_config.get('font_size', 10)))
        self.marker_font_family = resolve_font_family(numbered_markers_config.get('font_family', 'Helvetica Neue'))
        self.marker_font_weight = numbered_markers_config.get('font_weight', 'bold')
        self.marker_background_color = numbered_markers_config.get('background_color', [0, 100, 255])
        self.marker_background_radius = numbered_markers_config.get('background_radius', 8)
        self.marker_size = numbered_markers_config.get('size', 16)
        
        # Markers for trajectory 2
        numbered_markers_2_config = positional_plans_config.get('numbered_markers_2', {})
        self.marker_2_background_color = numbered_markers_2_config.get('background_color', [0, 200, 100])
        
        # Markers for trajectory 3
        numbered_markers_3_config = positional_plans_config.get('numbered_markers_3', {})
        self.marker_3_background_color = numbered_markers_3_config.get('background_color', [255, 150, 0])
    
    def _get_text_annotation_font(self, absolute_text_size: int) -> QFont:
        """Get font for text annotations, using user preferences if available.
        
        Args:
            absolute_text_size: Absolute text size in pixels (calculated from text_size_ratio and size_multiplier).
        
        Returns:
            QFont configured with user preferences or defaults.
        """
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings = settings_service.get_settings()
        annotations_prefs = settings.get('annotations', {})
        
        # Get font family from user settings or config defaults
        font_family = annotations_prefs.get('text_font_family', None)
        if font_family is None:
            # Get from config
            annotations_config = self.config.get('ui', {}).get('panels', {}).get('detail', {}).get('annotations', {})
            font_family = annotations_config.get('text_font_family', 'Arial')
        
        # Always use the calculated absolute_text_size to maintain proper scaling with size multiplier
        # The user's font size preference is not used here because it would break the scaling
        # Instead, the user can adjust the size slider in the annotation view to change text size
        # Convert pixels to points (approximate: 1 point ≈ 0.75 pixels at 96 DPI, or use 1:1 for simplicity)
        # QFont size is in points, but we'll use pixels directly as QFont can handle it
        font_size = absolute_text_size
        
        return QFont(font_family, font_size)
    
    def _setup_board(self) -> None:
        """Setup the board structure."""
        # Board size (8x8 squares)
        self.square_count = 8
        
        # Calculate board dimensions (will be set in paintEvent)
        self.board_size = 0
        self.square_size = 0
        
        # Cache for calculated dimensions to avoid recalculating on every paintEvent
        self._cached_dimensions = None
        self._cached_widget_size = None
        self._cached_eval_bar_visible = None
        self._cached_material_widget_visible = None
        self._cached_coordinates_visible = None
        
        # Load piece SVGs
        self._load_pieces()
        
        # Board state will be initialized when model is set or in fallback case
    
    def _calculate_board_dimensions(self) -> dict:
        """Calculate board dimensions and positions.
        
        Returns:
            Dictionary with calculated dimensions:
            - board_size: Size of the board in pixels
            - square_size: Size of each square in pixels
            - start_x: X position where board squares start
            - start_y: Y position where board squares start
            - coord_border_start: X position where coordinate border starts
            - board_border_start: X position where board border starts
            - board_group_start_x: X position where board group (with coordinates) starts
            - total_board_width: Total width including coordinates and borders
            - total_board_height: Total height including borders
        """
        # Get widget dimensions
        width = self.width()
        height = self.height()
        widget_size = (width, height)
        
        # Check if evaluation bar and material widget are visible
        eval_bar_visible = self.evaluation_bar and self.evaluation_bar.isVisible()
        material_widget_visible = self.material_widget and self.material_widget.isVisible()
        coordinates_visible = self.show_coordinates
        
        # Check if cache is valid
        if (self._cached_dimensions is not None and
            self._cached_widget_size == widget_size and
            self._cached_eval_bar_visible == eval_bar_visible and
            self._cached_material_widget_visible == material_widget_visible and
            self._cached_coordinates_visible == coordinates_visible):
            return self._cached_dimensions
        
        # Calculate coordinate border width
        coord_border_width = self.coord_border_width if coordinates_visible else 0
        
        # Calculate board size with padding
        padding_left = self.padding[0]
        padding_top = self.padding[1]
        padding_right = self.padding[2]
        padding_bottom = self.padding[3]
        
        # Account for evaluation bar width when visible
        eval_bar_width = 0
        if eval_bar_visible:
            eval_bar_width = self.evaluation_bar.width + self.eval_bar_padding_left
        
        # Account for material widget width when visible
        material_widget_width = 0
        if material_widget_visible:
            material_widget_width = self.material_widget.width()
            # Get material widget padding from config
            board_config = self.config.get("ui", {}).get("panels", {}).get("main", {}).get("board", {})
            material_config = board_config.get("material_widget", {})
            material_padding = material_config.get("padding", [10, 10, 15, 10])  # [top, right, bottom, left]
            # Add left padding (space between board and widget) to material widget width
            material_widget_width += material_padding[3]  # left padding
        
        # Available space after padding, evaluation bar, and material widget
        available_width_no_coord = width - padding_left - padding_right - eval_bar_width - material_widget_width
        available_height_no_coord = height - padding_top - padding_bottom
        
        # Board is square, use the smaller dimension (accounting for coordinate border)
        available_width = available_width_no_coord - coord_border_width
        available_height = available_height_no_coord - coord_border_width
        
        board_size = min(available_width, available_height)
        square_size = board_size // self.square_count
        
        # Adjust board size to fit exact squares
        board_size = square_size * self.square_count
        
        # Calculate starting position
        # Center the board (with coordinate border) horizontally in the available space
        # Total width needed: coordinate border + board border + board squares
        total_board_width = coord_border_width + self.border_size * 2 + board_size
        total_board_height = self.border_size * 2 + board_size
        
        # Center horizontally (accounting for evaluation bar on the left)
        board_group_start_x = padding_left + eval_bar_width + (available_width_no_coord - total_board_width) // 2
        
        # Coordinate border starts at the left edge of the centered group
        coord_border_start = board_group_start_x
        
        # Board border starts right after coordinate border
        board_border_start = coord_border_start + coord_border_width
        # Board squares start after board border
        start_x = board_border_start + self.border_size
        
        # Center vertically
        start_y = padding_top + (available_height_no_coord - total_board_height) // 2
        
        # Cache the results
        self._cached_dimensions = {
            'board_size': board_size,
            'square_size': square_size,
            'start_x': start_x,
            'start_y': start_y,
            'coord_border_start': coord_border_start,
            'board_border_start': board_border_start,
            'board_group_start_x': board_group_start_x,
            'total_board_width': total_board_width,
            'total_board_height': total_board_height,
            'eval_bar_width': eval_bar_width,
            'material_widget_width': material_widget_width,
            'available_width_no_coord': available_width_no_coord,
            'available_height_no_coord': available_height_no_coord
        }
        self._cached_widget_size = widget_size
        self._cached_eval_bar_visible = eval_bar_visible
        self._cached_material_widget_visible = material_widget_visible
        self._cached_coordinates_visible = coordinates_visible
        
        return self._cached_dimensions
    
    def _invalidate_cache(self) -> None:
        """Invalidate cached dimensions to force recalculation."""
        self._cached_dimensions = None
        self._cached_widget_size = None
        self._cached_eval_bar_visible = None
        self._cached_material_widget_visible = None
        self._cached_coordinates_visible = None
    
    def paintEvent(self, event) -> None:
        """Paint the chess board."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Get calculated dimensions (cached if possible)
        dims = self._calculate_board_dimensions()
        
        # Use cached dimensions
        self.board_size = dims['board_size']
        self.square_size = dims['square_size']
        start_x = dims['start_x']
        start_y = dims['start_y']
        coord_border_start = dims['coord_border_start']
        board_border_start = dims['board_border_start']
        coord_border_width = self.coord_border_width if self.show_coordinates else 0
        
        # Draw border
        if self.border_size > 0:
            border_rect = QRect(
                board_border_start,
                start_y - self.border_size,
                self.board_size + self.border_size * 2,
                self.board_size + self.border_size * 2
            )
            border_color = QColor(self.border_color[0], self.border_color[1], self.border_color[2])
            painter.fillRect(border_rect, QBrush(border_color))
        
        # Draw squares
        light_color = QColor(self.light_square_color[0], self.light_square_color[1], self.light_square_color[2])
        dark_color = QColor(self.dark_square_color[0], self.dark_square_color[1], self.dark_square_color[2])
        
        for row in range(self.square_count):
            for col in range(self.square_count):
                # Chess boards start from bottom-left (a1), so row 0 is bottom
                # In our coordinate system, row 0 is top, so we invert
                is_light = (row + col) % 2 == 0
                
                square_color = light_color if is_light else dark_color
                
                square_x = start_x + col * self.square_size
                square_y = start_y + row * self.square_size
                
                square_rect = QRect(square_x, square_y, self.square_size, self.square_size)
                painter.fillRect(square_rect, QBrush(square_color))
        
        # Draw coordinates in border area if enabled
        if self.show_coordinates:
            self._draw_coordinates(painter, start_x, start_y, coord_border_start)
        
        # Draw pieces
        self._draw_pieces(painter, start_x, start_y)
        
        # Draw turn indicator (attached to bottom right of board) if visible
        if self.show_turn_indicator:
            self._draw_turn_indicator(painter, start_x, start_y)
        
        # Check if we should hide other arrows during plan exploration
        # Only hide if both: a plan is active AND the toggle is enabled
        should_hide_other_arrows = (self._board_model and 
                                    self._board_model.active_pv_plan > 0 and
                                    self._board_model.hide_other_arrows_during_plan_exploration)
        
        # Draw played move arrow if visible and last move exists
        # Hide if plan exploration is active and hide_other_arrows is enabled
        if (self.show_playedmove_arrow and self._last_move is not None and
            not should_hide_other_arrows):
            self._draw_arrow(painter, self._last_move, self.playedmove_arrow_color, start_x, start_y)
        
        # Draw best next move arrow (PV1) if visible and best next move exists
        # Hide if plan exploration is active and hide_other_arrows is enabled
        if (self.show_bestnextmove_arrow and self._best_next_move is not None and
            not should_hide_other_arrows):
            self._draw_arrow(painter, self._best_next_move, self.bestnextmove_arrow_color, start_x, start_y)
        
        # Draw PV2 arrow if visible and PV2 move exists
        # Hide if plan exploration is active and hide_other_arrows is enabled
        if (self.show_pv2_arrow and self._pv2_move is not None and
            not should_hide_other_arrows):
            self._draw_arrow(painter, self._pv2_move, self.pv2_arrow_color, start_x, start_y)
        
        # Draw PV3 arrow if visible and PV3 move exists
        # Hide if plan exploration is active and hide_other_arrows is enabled
        if (self.show_pv3_arrow and self._pv3_move is not None and
            not should_hide_other_arrows):
            self._draw_arrow(painter, self._pv3_move, self.pv3_arrow_color, start_x, start_y)
        
        # Draw best alternative move arrow if visible and best alternative move exists
        # Hide if plan exploration is active and hide_other_arrows is enabled
        if (self.show_bestalternativemove_arrow and self._best_alternative_move is not None and
            not should_hide_other_arrows):
            self._draw_arrow(painter, self._best_alternative_move, self.bestalternativemove_arrow_color, start_x, start_y)
        
        # Draw positional plan trajectories if active
        if self._board_model and self._board_model.positional_plans:
            for idx, trajectory in enumerate(self._board_model.positional_plans):
                self._draw_trajectory(painter, trajectory, start_x, start_y, idx)
        
        # Draw annotations if annotation model is set
        if self._annotation_model:
            self._draw_annotations(painter, start_x, start_y)
    
    def _draw_arrow(self, painter: QPainter, move: chess.Move, color: List[int], board_start_x: int, board_start_y: int) -> None:
        """Draw an arrow for a chess move.
        
        Args:
            painter: QPainter instance for drawing.
            move: Chess move to draw arrow for.
            color: RGB color list [r, g, b] for the arrow.
            board_start_x: X coordinate of the board's top-left corner.
            board_start_y: Y coordinate of the board's top-left corner.
        """
        if move is None:
            return
        
        # Get move squares
        from_square = move.from_square
        to_square = move.to_square
        
        # Check if board is flipped
        is_flipped = False
        if self._board_model:
            is_flipped = self._board_model.is_flipped
        
        # Convert square indices to file and rank
        from_file = chess.square_file(from_square)
        from_rank = chess.square_rank(from_square)
        to_file = chess.square_file(to_square)
        to_rank = chess.square_rank(to_square)
        
        # Adjust for flipped board
        if is_flipped:
            from_file = 7 - from_file
            from_rank = 7 - from_rank
            to_file = 7 - to_file
            to_rank = 7 - to_rank
        
        # CRITICAL: In python-chess, ranks are 0-based from bottom (0=rank1, 7=rank8)
        # But in our drawing system, row 0 is at the top (rank 8), row 7 is at the bottom (rank 1)
        # So we need to convert: visual_row = 7 - rank
        from_visual_rank = 7 - from_rank
        to_visual_rank = 7 - to_rank
        
        # Calculate square centers
        from_x = board_start_x + from_file * self.square_size + self.square_size // 2
        from_y = board_start_y + from_visual_rank * self.square_size + self.square_size // 2
        to_x = board_start_x + to_file * self.square_size + self.square_size // 2
        to_y = board_start_y + to_visual_rank * self.square_size + self.square_size // 2
        
        # Set up pen for arrow
        arrow_color = QColor(color[0], color[1], color[2])
        pen = QPen(arrow_color)
        pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(QBrush(arrow_color))
        
        # Draw arrow line from source to destination
        # Shorten the line to leave space for arrowhead
        arrowhead_size = self.square_size * 0.15
        dx = to_x - from_x
        dy = to_y - from_y
        length = (dx * dx + dy * dy) ** 0.5
        if length > 0:
            # Normalize direction
            unit_x = dx / length
            unit_y = dy / length
            
            # Shorten line to make room for arrowhead
            shortened_to_x = to_x - unit_x * arrowhead_size
            shortened_to_y = to_y - unit_y * arrowhead_size
            
            # Draw line (convert to int for drawLine)
            painter.drawLine(int(from_x), int(from_y), int(shortened_to_x), int(shortened_to_y))
            
            # Draw arrowhead (triangle pointing to destination)
            arrowhead_points = QPolygonF([
                QPointF(to_x, to_y),
                QPointF(
                    shortened_to_x - unit_y * arrowhead_size * 0.5,
                    shortened_to_y + unit_x * arrowhead_size * 0.5
                ),
                QPointF(
                    shortened_to_x + unit_y * arrowhead_size * 0.5,
                    shortened_to_y - unit_x * arrowhead_size * 0.5
                )
            ])
            painter.drawPolygon(arrowhead_points)
    def _draw_trajectory(self, painter: QPainter, trajectory, board_start_x: int, board_start_y: int, trajectory_index: int = 0) -> None:
        """Draw a piece trajectory showing its path through multiple moves.
        
        Args:
            painter: QPainter instance for drawing.
            trajectory: PieceTrajectory object containing squares and move numbers.
            board_start_x: X coordinate of the board's top-left corner.
            board_start_y: Y coordinate of the board's top-left corner.
            trajectory_index: Index of the trajectory (0=first/most moved, 1=second, 2=third).
        """
        if trajectory is None or not trajectory.squares or len(trajectory.squares) < 2:
            return
        
        # Reset painter state to ensure clean drawing (prevents color bleeding from previous arrows)
        # The played move arrow sets brush to yellow, so we need to explicitly reset it
        painter.setPen(QPen(Qt.PenStyle.NoPen))  # Reset pen
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))  # Reset brush
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        
        # Check if board is flipped
        is_flipped = False
        if self._board_model:
            is_flipped = self._board_model.is_flipped
        
        # Find the piece's current square on the board (where it starts from)
        # First try to use the starting_square from the trajectory if available
        # But verify it actually has the correct piece in the current board state
        current_square = None
        if hasattr(trajectory, 'starting_square') and trajectory.starting_square is not None:
            # Verify the starting_square actually has the correct piece
            if self._board_model:
                board = self._board_model.board
                piece_type_map = {
                    'p': chess.PAWN, 'r': chess.ROOK, 'n': chess.KNIGHT,
                    'b': chess.BISHOP, 'q': chess.QUEEN, 'k': chess.KING
                }
                chess_piece_type = piece_type_map.get(trajectory.piece_type)
                chess_color = chess.WHITE if trajectory.piece_color else chess.BLACK
                
                if chess_piece_type:
                    piece_at_start = board.piece_at(trajectory.starting_square)
                    # Verify the piece at starting_square matches the trajectory
                    if (piece_at_start and 
                        piece_at_start.piece_type == chess_piece_type and 
                        piece_at_start.color == chess_color):
                        current_square = trajectory.starting_square
        
        # Fallback: find which square has a piece matching the trajectory's piece type and color
        if current_square is None and self._board_model:
            board = self._board_model.board
            piece_type_map = {
                'p': chess.PAWN, 'r': chess.ROOK, 'n': chess.KNIGHT,
                'b': chess.BISHOP, 'q': chess.QUEEN, 'k': chess.KING
            }
            chess_piece_type = piece_type_map.get(trajectory.piece_type)
            chess_color = chess.WHITE if trajectory.piece_color else chess.BLACK
            
            if chess_piece_type:
                # Find all pieces of this type and color
                pieces = list(board.pieces(chess_piece_type, chess_color))
                # If there's only one, use it; otherwise try to match by following the trajectory
                if len(pieces) == 1:
                    current_square = pieces[0]
                elif len(pieces) > 1 and trajectory.squares:
                    # Multiple pieces of same type - find which one can follow the entire trajectory
                    # Test each piece by trying to follow the path
                    best_match = None
                    best_match_score = 0
                    
                    for piece_square in pieces:
                        # Try to follow the trajectory path from this piece
                        test_board = board.copy()
                        test_square = piece_square
                        match_score = 0
                        
                        # Check if this piece can reach each square in the trajectory in sequence
                        for dest_square in trajectory.squares:
                            try:
                                # Try to create a move from current test_square to destination
                                test_move = chess.Move(test_square, dest_square)
                                if test_move in test_board.legal_moves:
                                    # This move is legal - update test_square and continue
                                    test_board.push(test_move)
                                    test_square = dest_square
                                    match_score += 1
                                else:
                                    # Can't reach this destination - this piece doesn't match
                                    break
                            except:
                                # Invalid move - this piece doesn't match
                                break
                        
                        # If we matched more moves than previous best, this is a better match
                        if match_score > best_match_score:
                            best_match = piece_square
                            best_match_score = match_score
                    
                    # Use the best match if we found one that can follow at least the first move
                    if best_match is not None and best_match_score > 0:
                        current_square = best_match
                    elif trajectory.squares:
                        # Fallback: just find any piece that can reach the first destination
                        first_dest = trajectory.squares[0]
                        for piece_square in pieces:
                            try:
                                test_move = chess.Move(piece_square, first_dest)
                                if test_move in board.legal_moves:
                                    current_square = piece_square
                                    break
                            except:
                                continue
        
        # Convert squares to pixel coordinates
        # Note: trajectory.squares now only contains squares the piece moves TO
        # (starting square is excluded)
        points = []
        
        # Add the piece's current square as the starting point if we found it
        if current_square is not None:
            file = chess.square_file(current_square)
            rank = chess.square_rank(current_square)
            if is_flipped:
                file = 7 - file
                rank = 7 - rank
            visual_rank = 7 - rank
            x = board_start_x + file * self.square_size + self.square_size // 2
            y = board_start_y + visual_rank * self.square_size + self.square_size // 2
            points.append((x, y))
        
        # Add all destination squares
        for square in trajectory.squares:
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            
            # Adjust for flipped board
            if is_flipped:
                file = 7 - file
                rank = 7 - rank
            
            # Convert rank (0=rank1, 7=rank8) to visual row (0=top, 7=bottom)
            visual_rank = 7 - rank
            
            # Calculate square center
            x = board_start_x + file * self.square_size + self.square_size // 2
            y = board_start_y + visual_rank * self.square_size + self.square_size // 2
            points.append((x, y))
        
        if len(points) < 2:
            return
        
        # Select trajectory colors and settings based on index
        if trajectory_index == 0:
            color_full = self.trajectory_color_end  # Full/dark color
            color_faded = self.trajectory_color_start  # Faded/light color
            line_width_start = self.trajectory_line_width_start
            line_width_end = self.trajectory_line_width_end
            curve_factor = self.trajectory_curve_factor
        elif trajectory_index == 1:
            color_full = self.trajectory_2_color_end
            color_faded = self.trajectory_2_color_start
            line_width_start = self.trajectory_2_line_width_start
            line_width_end = self.trajectory_2_line_width_end
            curve_factor = self.trajectory_2_curve_factor
        else:  # trajectory_index == 2
            color_full = self.trajectory_3_color_end
            color_faded = self.trajectory_3_color_start
            line_width_start = self.trajectory_3_line_width_start
            line_width_end = self.trajectory_3_line_width_end
            curve_factor = self.trajectory_3_curve_factor
        
        num_segments = len(points) - 1
        MAX_EXPLORATION_DEPTH = 4  # Maximum number of moves that can be explored
        
        if self.trajectory_use_straight_lines:
            # Draw straight lines (original implementation)
            for i in range(num_segments):
                from_point = points[i]
                to_point = points[i + 1]
                
                # Calculate fade factor
                if i == 0:
                    fade_factor = 0.0
                else:
                    fade_factor = i / (MAX_EXPLORATION_DEPTH - 1)
                    fade_factor = min(1.0, fade_factor)
                
                # Interpolate color and width
                r = int(color_full[0] + (color_faded[0] - color_full[0]) * fade_factor)
                g = int(color_full[1] + (color_faded[1] - color_full[1]) * fade_factor)
                b = int(color_full[2] + (color_faded[2] - color_full[2]) * fade_factor)
                r = max(0, min(255, r))
                g = max(0, min(255, g))
                b = max(0, min(255, b))
                line_width = line_width_end + (line_width_start - line_width_end) * fade_factor
                
                color = QColor(r, g, b)
                color.setAlphaF(1.0)
                pen = QPen(color)
                pen.setWidthF(line_width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                
                painter.drawLine(int(from_point[0]), int(from_point[1]), 
                               int(to_point[0]), int(to_point[1]))
        else:
            # Improved bezier curve rendering with smooth continuity
            # Calculate tangent directions at each point for smooth transitions
            tangents = []
            for i in range(len(points)):
                if i == 0:
                    # First point: tangent is direction to next point
                    if len(points) > 1:
                        dx = points[1][0] - points[0][0]
                        dy = points[1][1] - points[0][1]
                        length = (dx * dx + dy * dy) ** 0.5
                        if length > 0:
                            tangents.append((dx / length, dy / length))
                        else:
                            tangents.append((1.0, 0.0))
                    else:
                        tangents.append((1.0, 0.0))
                elif i == len(points) - 1:
                    # Last point: tangent is direction from previous point
                    dx = points[i][0] - points[i-1][0]
                    dy = points[i][1] - points[i-1][1]
                    length = (dx * dx + dy * dy) ** 0.5
                    if length > 0:
                        tangents.append((dx / length, dy / length))
                    else:
                        tangents.append((1.0, 0.0))
                else:
                    # Middle point: average direction from previous to next
                    dx1 = points[i][0] - points[i-1][0]
                    dy1 = points[i][1] - points[i-1][1]
                    dx2 = points[i+1][0] - points[i][0]
                    dy2 = points[i+1][1] - points[i][1]
                    length1 = (dx1 * dx1 + dy1 * dy1) ** 0.5
                    length2 = (dx2 * dx2 + dy2 * dy2) ** 0.5
                    
                    if length1 > 0 and length2 > 0:
                        # Average the two directions
                        tx = (dx1 / length1 + dx2 / length2) / 2
                        ty = (dy1 / length1 + dy2 / length2) / 2
                        length = (tx * tx + ty * ty) ** 0.5
                        if length > 0:
                            tangents.append((tx / length, ty / length))
                        else:
                            tangents.append((1.0, 0.0))
                    elif length1 > 0:
                        tangents.append((dx1 / length1, dy1 / length1))
                    elif length2 > 0:
                        tangents.append((dx2 / length2, dy2 / length2))
                    else:
                        tangents.append((1.0, 0.0))
            
            # Draw each segment with cubic bezier curves
            for i in range(num_segments):
                p0 = points[i]
                p1 = points[i + 1]
                t0 = tangents[i]
                t1 = tangents[i + 1]
                
                # Calculate fade factor
                if i == 0:
                    fade_factor = 0.0
                else:
                    fade_factor = i / (MAX_EXPLORATION_DEPTH - 1)
                    fade_factor = min(1.0, fade_factor)
                
                # Interpolate color and width
                r = int(color_full[0] + (color_faded[0] - color_full[0]) * fade_factor)
                g = int(color_full[1] + (color_faded[1] - color_full[1]) * fade_factor)
                b = int(color_full[2] + (color_faded[2] - color_full[2]) * fade_factor)
                r = max(0, min(255, r))
                g = max(0, min(255, g))
                b = max(0, min(255, b))
                line_width = line_width_end + (line_width_start - line_width_end) * fade_factor
                
                color = QColor(r, g, b)
                color.setAlphaF(1.0)
                pen = QPen(color)
                pen.setWidthF(line_width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                painter.setPen(pen)
                
                # Calculate segment length and turn angle for adaptive curve strength
                dx = p1[0] - p0[0]
                dy = p1[1] - p0[1]
                segment_length = (dx * dx + dy * dy) ** 0.5
                
                # Calculate turn angle (angle between current and next segment)
                turn_angle = 0.0
                if i < num_segments - 1:
                    # Angle between current segment and next segment
                    next_dx = points[i + 2][0] - p1[0]
                    next_dy = points[i + 2][1] - p1[1]
                    next_length = (next_dx * next_dx + next_dy * next_dy) ** 0.5
                    if segment_length > 0 and next_length > 0:
                        # Dot product to get angle
                        dot = (dx * next_dx + dy * next_dy) / (segment_length * next_length)
                        dot = max(-1.0, min(1.0, dot))  # Clamp for acos
                        turn_angle = abs(1.0 - dot)  # 0 = straight, 1 = 90 degrees
                
                # Adaptive curve strength based on:
                # - Base curve_factor
                # - Segment length (longer = stronger curve)
                # - Turn angle (sharper turns = stronger curve)
                # - Position in path (fade_factor for visual consistency)
                length_factor = min(1.0, segment_length / (self.square_size * 2))  # Normalize to ~2 squares
                adaptive_curve = curve_factor * (0.5 + 0.5 * length_factor) * (1.0 + turn_angle * 0.5)
                
                # Calculate control point distances (proportional to segment length)
                # Use a fraction of segment length for control point distance
                # Shorter distance for tighter control, longer for smoother curves
                base_control_distance = segment_length * 0.33  # One-third of segment length
                control_distance = base_control_distance * (0.5 + adaptive_curve * 0.5)
                
                # Calculate perpendicular direction for consistent curve direction
                # Always curve in the same relative direction (right side of movement)
                perp_x = -dy / segment_length if segment_length > 0 else 0.0
                perp_y = dx / segment_length if segment_length > 0 else 0.0
                
                # Perpendicular offset magnitude based on adaptive curve strength
                perp_offset = self.square_size * adaptive_curve * 0.4
                
                # First control point: along tangent from p0, with perpendicular offset
                c1_x = p0[0] + t0[0] * control_distance
                c1_y = p0[1] + t0[1] * control_distance
                c1_x += perp_x * perp_offset
                c1_y += perp_y * perp_offset
                
                # Second control point: along tangent toward p1 (reversed), with perpendicular offset
                # For C1 continuity, this should align with the next segment's first control point
                # at the connection point, but since we draw segments separately, we position it
                # along the tangent to create smooth visual flow
                c2_x = p1[0] - t1[0] * control_distance
                c2_y = p1[1] - t1[1] * control_distance
                c2_x += perp_x * perp_offset
                c2_y += perp_y * perp_offset
                
                # Draw cubic bezier curve
                path = QPainterPath()
                path.moveTo(p0[0], p0[1])
                path.cubicTo(c1_x, c1_y, c2_x, c2_y, p1[0], p1[1])
                painter.drawPath(path)
        
        # Draw numbered markers on squares
        if self.markers_enabled:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            font = QFont(self.marker_font_family, self.marker_font_size)
            if self.marker_font_weight == 'bold':
                font.setBold(True)
            painter.setFont(font)
            
            # Draw marker for starting square (if we found it)
            if current_square is not None:
                file = chess.square_file(current_square)
                rank = chess.square_rank(current_square)
                if is_flipped:
                    file = 7 - file
                    rank = 7 - rank
                visual_rank = 7 - rank
                center_x = board_start_x + file * self.square_size + self.square_size // 2
                center_y = board_start_y + visual_rank * self.square_size + self.square_size // 2
                
                # Draw marker background circle for starting position
                marker_radius = self.marker_size // 2
                
                # Starting marker should always be full color (fade_factor = 0.0)
                # Select trajectory colors based on index
                if trajectory_index == 0:
                    color_full = self.trajectory_color_end
                elif trajectory_index == 1:
                    color_full = self.trajectory_2_color_end
                else:  # trajectory_index == 2
                    color_full = self.trajectory_3_color_end
                
                # Use full color (no fading for starting marker)
                r = int(color_full[0])
                g = int(color_full[1])
                b = int(color_full[2])
                
                # Create color with full opacity
                bg_color = QColor(r, g, b)
                bg_color.setAlphaF(1.0)
                
                painter.setBrush(QBrush(bg_color))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(center_x - marker_radius, center_y - marker_radius, 
                                   self.marker_size, self.marker_size)
                
                # No text on starting marker - just the circle
            
            # Draw markers for each square in the trajectory
            # trajectory.squares already excludes the starting position
            if len(trajectory.squares) > 0:
                num_markers = len(trajectory.squares)
                for i, square in enumerate(trajectory.squares):
                    file = chess.square_file(square)
                    rank = chess.square_rank(square)
                    
                    # Adjust for flipped board
                    if is_flipped:
                        file = 7 - file
                        rank = 7 - rank
                    
                    # Convert rank to visual row
                    visual_rank = 7 - rank
                    
                    # Calculate square center
                    center_x = board_start_x + file * self.square_size + self.square_size // 2
                    center_y = board_start_y + visual_rank * self.square_size + self.square_size // 2
                    
                    # Scale down markers: start large, get smaller
                    # Starting marker (move 0) is always full size (drawn separately above)
                    # Numbered markers scale from slightly smaller than full (move 1) to smallest (last move)
                    # Calculate progress (0.0 to 1.0) for scaling
                    if num_markers == 1:
                        # Only one numbered marker: make it slightly smaller than starting marker
                        progress = 0.5  # Halfway between start and end
                    else:
                        progress = i / (num_markers - 1)
                    # Reverse progress so first numbered marker is largest
                    reversed_progress = 1.0 - progress
                    # Scale from 85% (first numbered marker) to 50% (last numbered marker)
                    marker_size_start = self.marker_size * 0.85
                    marker_size_end = self.marker_size * 0.5
                    # Interpolate: when reversed_progress=1.0 (first), use start; when 0.0 (last), use end
                    marker_size = marker_size_start * reversed_progress + marker_size_end * (1.0 - reversed_progress)
                    
                    marker_radius = marker_size // 2
                    
                    # Use same color as preceding line segment (the line that ends at this marker)
                    # Marker i is at the end of segment i, so it should use segment i's color
                    # Calculate fade_factor exactly as the line segment does
                    num_segments = num_markers  # Same as len(trajectory.squares)
                    
                    # Calculate fade_factor for segment i (matching line segment calculation)
                    # Use fixed maximum depth (4) so fading is consistent
                    MAX_EXPLORATION_DEPTH = 4  # Maximum number of moves that can be explored
                    
                    if i == 0:
                        fade_factor = 0.0  # Segment 0 always full color
                    else:
                        # Calculate fade_factor based on fixed maximum depth
                        fade_factor = i / (MAX_EXPLORATION_DEPTH - 1)
                        # Cap at 1.0 in case we somehow have more segments than max depth
                        fade_factor = min(1.0, fade_factor)
                    
                    # Select trajectory colors based on index (same as line segments)
                    if trajectory_index == 0:
                        color_full = self.trajectory_color_end
                        color_faded = self.trajectory_color_start
                    elif trajectory_index == 1:
                        color_full = self.trajectory_2_color_end
                        color_faded = self.trajectory_2_color_start
                    else:  # trajectory_index == 2
                        color_full = self.trajectory_3_color_end
                        color_faded = self.trajectory_3_color_start
                    
                    # Interpolate color: fade from color_full to color_faded (same as line segment)
                    r = int(color_full[0] + (color_faded[0] - color_full[0]) * fade_factor)
                    g = int(color_full[1] + (color_faded[1] - color_full[1]) * fade_factor)
                    b = int(color_full[2] + (color_faded[2] - color_full[2]) * fade_factor)
                    
                    # Clamp color values to valid range [0, 255]
                    r = max(0, min(255, r))
                    g = max(0, min(255, g))
                    b = max(0, min(255, b))
                    
                    # Create color with full opacity (no transparency, no shine-through)
                    bg_color = QColor(r, g, b)
                    bg_color.setAlphaF(1.0)
                    
                    # Draw marker background with full opacity (matches line color exactly)
                    painter.setBrush(QBrush(bg_color))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawEllipse(int(center_x - marker_radius), int(center_y - marker_radius),
                                       int(marker_size), int(marker_size))
    
    def _draw_coordinates(self, painter: QPainter, board_start_x: int, board_start_y: int, coord_border_start: int) -> None:
        """Draw coordinate labels in the border area.
        
        Args:
            painter: QPainter instance.
            board_start_x: X position where the board starts.
            board_start_y: Y position where the board starts.
            coord_border_start: X position where the coordinate border starts (from centered calculation).
        """
        # Setup font
        font = QFont(self.coord_font_family, self.coord_font_size)
        if self.coord_font_style == 'bold':
            font.setBold(True)
        elif self.coord_font_style == 'italic':
            font.setItalic(True)
        painter.setFont(font)
        
        # Setup color
        text_color = QColor(self.coord_color[0], self.coord_color[1], self.coord_color[2])
        painter.setPen(text_color)
        
        # Calculate positions
        coord_padding = 3
        
        # Check if board is flipped
        is_flipped = False
        if self._board_model:
            is_flipped = self._board_model.is_flipped
        
        # Draw file letters (a-h) in bottom border
        # Position letters right at the top edge of the coordinate border area
        file_top = board_start_y + self.board_size + self.border_size + coord_padding
        file_bottom = board_start_y + self.board_size + self.border_size + self.coord_border_width - coord_padding
        
        for col in range(self.square_count):
            if is_flipped:
                # Flip file letters: a->h, b->g, c->f, d->e, e->d, f->c, g->b, h->a
                file_letter = chr(ord('h') - col)
            else:
                file_letter = chr(ord('a') + col)
            file_x = board_start_x + col * self.square_size
            
            # Center letter in square
            text_rect = QRect(
                file_x,
                file_top,
                self.square_size,
                file_bottom - file_top
            )
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter, file_letter)
        
        # Draw rank numbers (1-8) in left border
        # Position numbers at the right edge of the coordinate border (closest to board)
        # Use the calculated coord_border_start to ensure coordinates are attached to the centered board
        # Add spacing similar to file letters (coord_padding from board border)
        coord_border_left = coord_border_start
        # Calculate right edge of coordinate border (where board border starts)
        coord_border_right = board_start_x - self.border_size
        
        for row in range(self.square_count):
            if is_flipped:
                # Flip rank numbers: 1->8, 2->7, 3->6, 4->5, 5->4, 6->3, 7->2, 8->1
                rank_number = str(1 + row)  # row 0 -> rank 1, row 7 -> rank 8
            else:
                rank_number = str(self.square_count - row)  # row 0 -> rank 8, row 7 -> rank 1
            rank_y = board_start_y + row * self.square_size
            
            # Center number vertically in square, align right with padding from board border
            # Leave coord_padding space from the board border (similar to file letters)
            text_rect = QRect(
                coord_border_left,
                rank_y,
                coord_border_right - coord_padding - coord_border_left,
                self.square_size
            )
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, rank_number)
    
    def _load_pieces(self) -> None:
        """Load chess piece SVG files from the configured path."""
        # Resolve path relative to project root
        project_root = Path(__file__).parent.parent.parent
        pieces_dir = project_root / self.svg_path
        
        if not pieces_dir.exists():
            logging_service = LoggingService.get_instance()
            logging_service.warning(f"Chess pieces directory not found: {pieces_dir}")
            self.piece_renderers = {}
            return
        
        # Piece type mapping: (color, piece_type) -> filename
        # color: 'w' (white) or 'b' (black)
        # piece_type: 'p' (pawn), 'r' (rook), 'n' (knight), 'b' (bishop), 'q' (queen), 'k' (king)
        piece_types = ['p', 'r', 'n', 'b', 'q', 'k']
        colors = ['w', 'b']
        
        self.piece_renderers = {}
        
        for color in colors:
            for piece_type in piece_types:
                filename = f"{color}{piece_type}.svg"
                file_path = pieces_dir / filename
                
                if file_path.exists():
                    renderer = QSvgRenderer(str(file_path))
                    if renderer.isValid():
                        self.piece_renderers[(color, piece_type)] = renderer
                    else:
                        logging_service = LoggingService.get_instance()
                        logging_service.warning(f"Invalid SVG file: {file_path}")
                else:
                    logging_service = LoggingService.get_instance()
                    logging_service.warning(f"Piece file not found: {file_path}")
    
    def _initialize_starting_position(self) -> None:
        """Initialize the board state with standard starting position.
        
        Board representation:
        - self.board[row][col] = (color, piece_type) or None
        - row 0 = rank 8 (top, black pieces)
        - row 7 = rank 1 (bottom, white pieces)
        """
        self.board = [[None for _ in range(self.square_count)] for _ in range(self.square_count)]
        self._load_standard_starting_position()
    
    def _load_position_from_model(self) -> None:
        """Load board position from BoardModel."""
        if not self._board_model:
            return
        
        # Clear the board first to remove old pieces
        if not hasattr(self, 'board') or self.board is None:
            self.board = [[None for _ in range(self.square_count)] for _ in range(self.square_count)]
        else:
            # Clear all squares
            for row in range(self.square_count):
                for col in range(self.square_count):
                    self.board[row][col] = None
        
        # Get flip state
        is_flipped = self._board_model.is_flipped
        
        pieces = self._board_model.get_all_pieces()
        for (file, rank), (color, piece_type) in pieces.items():
            # Convert rank from python-chess (0=rank1, 7=rank8) to our system (0=rank8, 7=rank1)
            # python-chess rank: 0=rank1, 7=rank8 (bottom to top)
            # Our system: row 0=rank8, row 7=rank1 (top to bottom)
            
            if is_flipped:
                # When flipped visually, mirror both file and rank for display
                # FEN position stays the same, but we display it rotated
                mirrored_file = 7 - file
                mirrored_rank = 7 - rank
                row = 7 - mirrored_rank  # Convert to our row system (rank 0 -> row 7)
                col = mirrored_file
            else:
                row = 7 - rank
                col = file
            
            self.board[row][col] = (color, piece_type)
    
    def _load_standard_starting_position(self) -> None:
        """Load standard chess starting position (fallback)."""
        # Rank 8 (row 0): Black pieces
        self.board[0][0] = ('b', 'r')  # a8
        self.board[0][1] = ('b', 'n')  # b8
        self.board[0][2] = ('b', 'b')  # c8
        self.board[0][3] = ('b', 'q')  # d8
        self.board[0][4] = ('b', 'k')  # e8
        self.board[0][5] = ('b', 'b')  # f8
        self.board[0][6] = ('b', 'n')  # g8
        self.board[0][7] = ('b', 'r')  # h8
        
        # Rank 7 (row 1): Black pawns
        for col in range(self.square_count):
            self.board[1][col] = ('b', 'p')
        
        # Rank 2 (row 6): White pawns
        for col in range(self.square_count):
            self.board[6][col] = ('w', 'p')
        
        # Rank 1 (row 7): White pieces
        self.board[7][0] = ('w', 'r')  # a1
        self.board[7][1] = ('w', 'n')  # b1
        self.board[7][2] = ('w', 'b')  # c1
        self.board[7][3] = ('w', 'q')  # d1
        self.board[7][4] = ('w', 'k')  # e1
        self.board[7][5] = ('w', 'b')  # f1
        self.board[7][6] = ('w', 'n')  # g1
        self.board[7][7] = ('w', 'r')  # h1
    
    def set_model(self, model: BoardModel) -> None:
        """Set the board model to observe.
        
        Args:
            model: The BoardModel instance to observe.
        """
        if self._board_model:
            # Disconnect from old model
            try:
                self._board_model.position_changed.disconnect(self._on_position_changed)
                if hasattr(self._board_model, 'flip_state_changed'):
                    self._board_model.flip_state_changed.disconnect(self._on_flip_state_changed)
                if hasattr(self._board_model, 'hide_other_arrows_during_plan_exploration_changed'):
                    self._board_model.hide_other_arrows_during_plan_exploration_changed.disconnect(self._on_hide_other_arrows_during_plan_exploration_changed)
            except TypeError:
                # Signal was not connected, ignore
                pass
        
        self._board_model = model
        
        # Initialize board array if not already done
        if not hasattr(self, 'board') or self.board is None:
            self.board = [[None for _ in range(self.square_count)] for _ in range(self.square_count)]
        
        # Connect to model signals
        model.position_changed.connect(self._on_position_changed)
        model.flip_state_changed.connect(self._on_flip_state_changed)
        model.coordinates_visibility_changed.connect(self._on_coordinates_visibility_changed)
        model.turn_indicator_visibility_changed.connect(self._on_turn_indicator_visibility_changed)
        model.playedmove_arrow_visibility_changed.connect(self._on_playedmove_arrow_visibility_changed)
        model.bestnextmove_arrow_visibility_changed.connect(self._on_bestnextmove_arrow_visibility_changed)
        model.pv2_arrow_visibility_changed.connect(self._on_pv2_arrow_visibility_changed)
        model.pv3_arrow_visibility_changed.connect(self._on_pv3_arrow_visibility_changed)
        model.bestalternativemove_arrow_visibility_changed.connect(self._on_bestalternativemove_arrow_visibility_changed)
        model.last_move_changed.connect(self._on_last_move_changed)
        model.best_next_move_changed.connect(self._on_best_next_move_changed)
        model.pv2_move_changed.connect(self._on_pv2_move_changed)
        model.pv3_move_changed.connect(self._on_pv3_move_changed)
        model.best_alternative_move_changed.connect(self._on_best_alternative_move_changed)
        model.positional_plan_changed.connect(self._on_positional_plan_changed)
        model.active_pv_plan_changed.connect(self._on_active_pv_plan_changed)
        model.hide_other_arrows_during_plan_exploration_changed.connect(self._on_hide_other_arrows_during_plan_exploration_changed)
        model.material_widget_visibility_changed.connect(self._on_material_widget_visibility_changed)
        if hasattr(model, 'turn_changed'):
            model.turn_changed.connect(self._on_turn_changed)
        
        # Initialize view with current model state
        self._load_position_from_model()
        self._update_turn_state()
        self._update_coordinates_visibility(model.show_coordinates)
        self._update_turn_indicator_visibility(model.show_turn_indicator)
        self._update_playedmove_arrow_visibility(model.show_playedmove_arrow)
        self._update_bestnextmove_arrow_visibility(model.show_bestnextmove_arrow)
        self._update_pv2_arrow_visibility(model.show_pv2_arrow)
        self._update_pv3_arrow_visibility(model.show_pv3_arrow)
        self._update_bestalternativemove_arrow_visibility(model.show_bestalternativemove_arrow)
        self._update_last_move(model.last_move)
        self._update_best_next_move(model.best_next_move)
        self._update_pv2_move(model.pv2_move)
        self._update_pv3_move(model.pv3_move)
        self._update_best_alternative_move(model.best_alternative_move)
        
        # Update evaluation bar visibility if model has it
        if hasattr(model, 'show_evaluation_bar'):
            self.set_evaluation_bar_visible(model.show_evaluation_bar)
        if hasattr(model, 'is_flipped'):
            self.set_evaluation_bar_flipped(model.is_flipped)
        
        # Update material widget visibility if model has it
        if hasattr(model, 'show_material_widget'):
            self.set_material_widget_visible(model.show_material_widget)
        if hasattr(model, 'is_flipped'):
            self.set_material_widget_flipped(model.is_flipped)
        
        # Connect material widget to board model
        self.material_widget.set_board_model(model)
        
        self.update()  # Trigger repaint
    
    def _on_position_changed(self) -> None:
        """Handle position change from model."""
        self._load_position_from_model()
        self.update()  # Trigger repaint
    
    def _on_flip_state_changed(self, is_flipped: bool) -> None:
        """Handle flip state change from model.
        
        Args:
            is_flipped: True if board is flipped, False otherwise.
        """
        # Reload piece positions with new flip state
        self._load_position_from_model()
        # Trigger repaint to update both pieces and coordinates
        self.update()
    
    def _on_coordinates_visibility_changed(self, show: bool) -> None:
        """Handle coordinates visibility change from model.
        
        Args:
            show: True if coordinates should be visible, False otherwise.
        """
        self._update_coordinates_visibility(show)
        self.update()  # Trigger repaint
    
    def _update_coordinates_visibility(self, show: bool) -> None:
        """Update coordinates visibility state.
        
        Args:
            show: True if coordinates should be visible, False otherwise.
        """
        self.show_coordinates = show
        # Invalidate cache when coordinates visibility changes to force recalculation
        self._invalidate_cache()
        # Force recalculation by calling _calculate_board_dimensions()
        # This ensures the board size is recalculated immediately
        self._calculate_board_dimensions()
        # Trigger repaint to update the board with new dimensions
        self.update()
    
    def _on_turn_indicator_visibility_changed(self, show: bool) -> None:
        """Handle turn indicator visibility change from model.
        
        Args:
            show: True if turn indicator should be visible, False otherwise.
        """
        self._update_turn_indicator_visibility(show)
        self.update()  # Trigger repaint
    
    def _update_turn_indicator_visibility(self, show: bool) -> None:
        """Update turn indicator visibility state.
        
        Args:
            show: True if turn indicator should be visible, False otherwise.
        """
        self.show_turn_indicator = show
    
    def _on_playedmove_arrow_visibility_changed(self, visible: bool) -> None:
        """Handle played move arrow visibility change from board model.
        
        Args:
            visible: True if played move arrow should be visible, False otherwise.
        """
        self._update_playedmove_arrow_visibility(visible)
    
    def _update_playedmove_arrow_visibility(self, visible: bool) -> None:
        """Update played move arrow visibility state.
        
        Args:
            visible: True if played move arrow should be visible, False otherwise.
        """
        self.show_playedmove_arrow = visible
        self.update()  # Trigger repaint
    
    def _on_last_move_changed(self, move: Optional[chess.Move]) -> None:
        """Handle last move change from board model.
        
        Args:
            move: The last Move object, or None if no move.
        """
        self._update_last_move(move)
    
    def _update_last_move(self, move: Optional[chess.Move]) -> None:
        """Update last move state.
        
        Args:
            move: The last Move object, or None if no move.
        """
        self._last_move = move
        self.update()  # Trigger repaint
    
    def _on_bestnextmove_arrow_visibility_changed(self, visible: bool) -> None:
        """Handle best next move arrow visibility change from board model.
        
        Args:
            visible: True if best next move arrow should be visible, False otherwise.
        """
        self._update_bestnextmove_arrow_visibility(visible)
        self.update()  # Trigger repaint
    
    def _update_bestnextmove_arrow_visibility(self, visible: bool) -> None:
        """Update best next move arrow visibility state.
        
        Args:
            visible: True if best next move arrow should be visible, False otherwise.
        """
        self.show_bestnextmove_arrow = visible
        self.update()  # Trigger repaint
    
    def _on_best_next_move_changed(self, move: Optional[chess.Move]) -> None:
        """Handle best next move change from board model.
        
        Args:
            move: The best next Move object, or None if no move.
        """
        self._update_best_next_move(move)
        self.update()  # Trigger repaint
    
    def _update_best_next_move(self, move: Optional[chess.Move]) -> None:
        """Update best next move state.
        
        Args:
            move: The best next move, or None if no move.
        """
        self._best_next_move = move
        self.update()  # Trigger repaint
    
    def _on_pv2_arrow_visibility_changed(self, visible: bool) -> None:
        """Handle PV2 arrow visibility change from board model.
        
        Args:
            visible: True if PV2 arrow should be visible, False otherwise.
        """
        self._update_pv2_arrow_visibility(visible)
        self.update()  # Trigger repaint
    
    def _update_pv2_arrow_visibility(self, visible: bool) -> None:
        """Update PV2 arrow visibility state.
        
        Args:
            visible: True if PV2 arrow should be visible, False otherwise.
        """
        self.show_pv2_arrow = visible
        self.update()  # Trigger repaint
    
    def _on_pv3_arrow_visibility_changed(self, visible: bool) -> None:
        """Handle PV3 arrow visibility change from board model.
        
        Args:
            visible: True if PV3 arrow should be visible, False otherwise.
        """
        self._update_pv3_arrow_visibility(visible)
        self.update()  # Trigger repaint
    
    def _update_pv3_arrow_visibility(self, visible: bool) -> None:
        """Update PV3 arrow visibility state.
        
        Args:
            visible: True if PV3 arrow should be visible, False otherwise.
        """
        self.show_pv3_arrow = visible
        self.update()  # Trigger repaint
    
    def _on_pv2_move_changed(self, move: Optional[chess.Move]) -> None:
        """Handle PV2 move change from board model.
        
        Args:
            move: The PV2 Move object, or None if no move.
        """
        self._update_pv2_move(move)
        self.update()  # Trigger repaint
    
    def _update_pv2_move(self, move: Optional[chess.Move]) -> None:
        """Update PV2 move state.
        
        Args:
            move: The PV2 move, or None if no move.
        """
        self._pv2_move = move
        self.update()  # Trigger repaint
    
    def _on_pv3_move_changed(self, move: Optional[chess.Move]) -> None:
        """Handle PV3 move change from board model.
        
        Args:
            move: The PV3 Move object, or None if no move.
        """
        self._update_pv3_move(move)
        self.update()  # Trigger repaint
    
    def _update_pv3_move(self, move: Optional[chess.Move]) -> None:
        """Update PV3 move state.
        
        Args:
            move: The PV3 move, or None if no move.
        """
        self._pv3_move = move
        self.update()  # Trigger repaint
    
    def _on_bestalternativemove_arrow_visibility_changed(self, visible: bool) -> None:
        """Handle best alternative move arrow visibility change from board model.
        
        Args:
            visible: True if best alternative move arrow should be visible, False otherwise.
        """
        self._update_bestalternativemove_arrow_visibility(visible)
        self.update()  # Trigger repaint
    
    def _update_bestalternativemove_arrow_visibility(self, visible: bool) -> None:
        """Update best alternative move arrow visibility state.
        
        Args:
            visible: True if best alternative move arrow should be visible, False otherwise.
        """
        self.show_bestalternativemove_arrow = visible
        self.update()  # Trigger repaint
    
    def _on_best_alternative_move_changed(self, move: Optional[chess.Move]) -> None:
        """Handle best alternative move change from board model.
        
        Args:
            move: The best alternative Move object, or None if no move.
        """
        self._update_best_alternative_move(move)
        self.update()  # Trigger repaint
    
    def _update_best_alternative_move(self, move: Optional[chess.Move]) -> None:
        """Update best alternative move state.
        
        Args:
            move: The best alternative move, or None if no move.
        """
        self._best_alternative_move = move
        self.update()  # Trigger repaint
    
    def _on_positional_plan_changed(self, plan) -> None:
        """Handle positional plan change from board model.
        
        Args:
            plan: PieceTrajectory object, or None if no plan.
        """
        # Plan is stored in model, we just need to repaint
        self.update()  # Trigger repaint
    
    def _on_active_pv_plan_changed(self, pv_number: int) -> None:
        """Handle active PV plan change from board model.
        
        Args:
            pv_number: 0 if no plan active, 1-3 for PV1-PV3.
        """
        # Active PV plan is stored in model, we just need to repaint
        self.update()  # Trigger repaint
    
    def _on_hide_other_arrows_during_plan_exploration_changed(self, hide: bool) -> None:
        """Handle hide other arrows during plan exploration setting change.
        
        Args:
            hide: True if other arrows should be hidden, False otherwise.
        """
        self.update()
    
    def _on_turn_changed(self, is_white_turn: bool) -> None:
        """Handle turn change from model.
        
        Args:
            is_white_turn: True if White's turn, False if Black's turn.
        """
        self._update_turn_state()
        self.update()
    
    def _update_turn_state(self) -> None:
        """Update turn state from model."""
        if self._board_model:
            self._is_white_turn = self._board_model.is_white_turn()
        else:
            self._is_white_turn = True
    
    def set_positional_heatmap_model(self, model, controller=None) -> None:
        """Set the positional heat-map model.
        
        Args:
            model: PositionalHeatmapModel instance.
            controller: Optional PositionalHeatmapController instance for hover tooltips.
        """
        from app.views.positional_heatmap_overlay import PositionalHeatmapOverlay
        
        if model is None:
            # Remove overlay if model is None
            if self.positional_heatmap_overlay:
                self.positional_heatmap_overlay.setParent(None)
                self.positional_heatmap_overlay = None
            self.positional_heatmap_controller = None
            return
        
        # Store controller for hover tooltips
        self.positional_heatmap_controller = controller
        
        # Create overlay if it doesn't exist
        if self.positional_heatmap_overlay is None:
            self.positional_heatmap_overlay = PositionalHeatmapOverlay(
                self.config, model, self
            )
            self.positional_heatmap_overlay.setGeometry(self.rect())
        
        # Update overlay when board is resized or repainted
        self.update()
    
    def set_evaluation_model(self, model: Optional[EvaluationModel]) -> None:
        """Set the evaluation model for the evaluation bar.
        
        Args:
            model: EvaluationModel instance or None.
        """
        self._evaluation_model = model
        if self.evaluation_bar:
            self.evaluation_bar.set_evaluation_model(model)
    
    def set_evaluation_bar_visible(self, visible: bool) -> None:
        """Set evaluation bar visibility.
        
        Args:
            visible: True if evaluation bar should be visible, False otherwise.
        """
        if self.evaluation_bar:
            self.evaluation_bar.setVisible(visible)
            # Invalidate cache when visibility changes to force recalculation
            self._invalidate_cache()
            # Force recalculation by calling _calculate_board_dimensions()
            # This ensures the board size is recalculated immediately
            self._calculate_board_dimensions()
            # Trigger repaint to update the board with new dimensions
            self.update()
            if visible:
                self._update_evaluation_bar_position()
            # Update material widget position if it's visible, since board dimensions changed
            if self.material_widget and self.material_widget.isVisible():
                self._update_material_widget_position()
    
    def set_evaluation_bar_flipped(self, is_flipped: bool) -> None:
        """Set evaluation bar flip state.
        
        Args:
            is_flipped: True if board is flipped, False otherwise.
        """
        if self.evaluation_bar:
            self.evaluation_bar.set_flipped(is_flipped)
    
    def _on_material_widget_visibility_changed(self, show: bool) -> None:
        """Handle material widget visibility change from model.
        
        Args:
            show: True if material widget should be visible, False otherwise.
        """
        self.set_material_widget_visible(show)
    
    def set_material_widget_visible(self, visible: bool) -> None:
        """Set material widget visibility.
        
        Args:
            visible: True if material widget should be visible, False otherwise.
        """
        if self.material_widget:
            self.material_widget.setVisible(visible)
            # Invalidate cache when visibility changes to force recalculation
            self._invalidate_cache()
            # Force recalculation by calling _calculate_board_dimensions()
            # This ensures the board size is recalculated immediately
            self._calculate_board_dimensions()
            # Trigger repaint to update the board with new dimensions
            self.update()
            if visible:
                self._update_material_widget_position()
            # Update evaluation bar position if it's visible, since board dimensions changed
            if self.evaluation_bar and self.evaluation_bar.isVisible():
                self._update_evaluation_bar_position()
    
    def set_material_widget_flipped(self, is_flipped: bool) -> None:
        """Set material widget flip state.
        
        Args:
            is_flipped: True if board is flipped, False otherwise.
        """
        if self.material_widget:
            self.material_widget.set_flipped(is_flipped)
    
    def _draw_pieces(self, painter: QPainter, board_start_x: int, board_start_y: int) -> None:
        """Draw chess pieces on the board.
        
        Args:
            painter: QPainter instance.
            board_start_x: X position where the board squares start.
            board_start_y: Y position where the board squares start.
        """
        # Piece padding (margin from square edges)
        piece_padding = 0.1  # 10% padding on each side
        
        for row in range(self.square_count):
            for col in range(self.square_count):
                piece = self.board[row][col]
                if piece is None:
                    continue
                
                color, piece_type = piece
                renderer = self.piece_renderers.get((color, piece_type))
                if renderer is None:
                    continue
                
                # Calculate square position
                square_x = board_start_x + col * self.square_size
                square_y = board_start_y + row * self.square_size
                
                # Calculate piece size with padding
                piece_size = self.square_size * (1 - piece_padding * 2)
                
                # Calculate piece position (centered in square)
                piece_x = square_x + self.square_size * piece_padding
                piece_y = square_y + self.square_size * piece_padding
                
                # Draw piece (QSvgRenderer.render requires QRectF)
                piece_rect = QRectF(piece_x, piece_y, piece_size, piece_size)
                renderer.render(painter, piece_rect)
    
    def showEvent(self, event) -> None:
        """Handle widget show event to position child widgets.
        
        Args:
            event: Show event.
        """
        super().showEvent(event)
        # Update positions when widget is first shown
        # Use QTimer to ensure widget has final size
        QTimer.singleShot(0, self._update_evaluation_bar_position)
        QTimer.singleShot(0, self._update_material_widget_position)
    
    def resizeEvent(self, event) -> None:
        """Handle widget resize event to reposition evaluation bar.
        
        Args:
            event: Resize event.
        """
        super().resizeEvent(event)
        # Invalidate cache when widget is resized
        self._invalidate_cache()
        self._update_evaluation_bar_position()
        self._update_material_widget_position()
        
        # Update overlay size
        if self.positional_heatmap_overlay:
            self.positional_heatmap_overlay.setGeometry(self.rect())
    
    def _update_evaluation_bar_position(self) -> None:
        """Update evaluation bar position to attach to left side of board."""
        if not self.evaluation_bar or not self.evaluation_bar.isVisible():
            return
        
        # Get calculated dimensions (uses cache if available)
        dims = self._calculate_board_dimensions()
        
        start_x = dims['start_x']
        start_y = dims['start_y']
        board_size = dims['board_size']
        
        # Position evaluation bar to the left of the board
        # It should be attached to the left edge of the board area with padding
        eval_bar_width = self.evaluation_bar.width  # width is an attribute, not a method
        eval_bar_x = start_x - eval_bar_width - self.eval_bar_padding_left
        eval_bar_y = start_y
        eval_bar_height = board_size
        
        # Set position and size
        self.evaluation_bar.setGeometry(
            int(eval_bar_x),
            int(eval_bar_y),
            eval_bar_width,
            int(eval_bar_height)
        )
    
    def _update_material_widget_position(self) -> None:
        """Update material widget position to attach to upper right of board."""
        if not self.material_widget or not self.material_widget.isVisible():
            return
        
        # Get calculated dimensions (uses cache if available)
        dims = self._calculate_board_dimensions()
        
        start_x = dims['start_x']
        start_y = dims['start_y']
        board_size = dims['board_size']
        
        # Calculate top of board visual area (including border) for alignment
        # The border is drawn at start_y - self.border_size, so that's the top of the board visual area
        board_top_y = start_y - self.border_size
        
        # Get material widget config
        board_config = self.config.get("ui", {}).get("panels", {}).get("main", {}).get("board", {})
        material_config = board_config.get("material_widget", {})
        material_padding = material_config.get("padding", [10, 10, 15, 10])  # [top, right, bottom, left]
        
        # Position material widget to the upper right of the board
        # Get widget size from QWidget methods (not attributes)
        material_widget_width = self.material_widget.width()
        material_widget_height = self.material_widget.height()
        # Position to the right of the board with padding
        # The board size calculation already accounts for material widget width, so position it correctly
        material_widget_x = start_x + board_size + material_padding[3]  # left padding from board edge
        # Align with board top (including border) - no additional top padding for perfect alignment
        material_widget_y = board_top_y
        
        # Set position and size
        self.material_widget.setGeometry(
            int(material_widget_x),
            int(material_widget_y),
            material_widget_width,
            material_widget_height
        )
    
    def _draw_turn_indicator(self, painter: QPainter, board_start_x: int, board_start_y: int) -> None:
        """Draw turn indicator attached to bottom right of board.
        
        Args:
            painter: QPainter instance.
            board_start_x: X position where the board squares start.
            board_start_y: Y position where the board squares start.
        """
        # Position indicator to the right of the board, aligned with bottom
        # Calculate indicator position: right of board + left padding
        # Padding: [top, right, bottom, left]
        indicator_x = board_start_x + self.board_size + self.border_size + self.indicator_padding[3]  # left padding
        indicator_y = board_start_y + self.board_size - self.indicator_size - self.indicator_padding[2]  # bottom padding
        
        # Choose color based on turn
        if self._is_white_turn:
            color = QColor(self.indicator_white_color[0], self.indicator_white_color[1], self.indicator_white_color[2])
        else:
            color = QColor(self.indicator_black_color[0], self.indicator_black_color[1], self.indicator_black_color[2])
        
        # Draw circle
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawEllipse(int(indicator_x), int(indicator_y), self.indicator_size, self.indicator_size)
    
    def _get_square_from_mouse_pos(self, pos: QPoint) -> Optional[chess.Square]:
        """Get the chess square from mouse position.
        
        Args:
            pos: Mouse position in widget coordinates.
        
        Returns:
            Chess square index if position is over a square, None otherwise.
        """
        if not self._cached_dimensions:
            return None
        
        dims = self._cached_dimensions
        square_size = dims['square_size']
        board_start_x = dims['start_x']
        board_start_y = dims['start_y']
        
        # Check if mouse is within board bounds
        if pos.x() < board_start_x or pos.y() < board_start_y:
            return None
        
        # Calculate which square the mouse is over
        col = (pos.x() - board_start_x) // square_size
        row = (pos.y() - board_start_y) // square_size
        
        if col < 0 or col >= 8 or row < 0 or row >= 8:
            return None
        
        # Convert to chess square (accounting for board flip)
        # Match the inverse transformation used in _load_position_from_model
        if hasattr(self, '_board_model') and self._board_model and self._board_model.is_flipped:
            # When flipped: col = 7 - file, row = rank
            # So: file = 7 - col, rank = row
            file = 7 - col
            rank = row
        else:
            file = col
            rank = 7 - row  # Invert rank (chess rank 0 = row 7)
        
        return chess.square(file, rank)
    
    def _format_evaluation_tooltip(self, piece_info: Dict, board: chess.Board, square: chess.Square) -> str:
        """Format evaluation information as natural language tooltip.
        
        Args:
            piece_info: Dictionary with piece evaluation info from get_detailed_evaluation.
            board: Current chess position.
            square: Square of the piece.
        
        Returns:
            Formatted tooltip text (HTML).
        """
        return RuleExplanationFormatter.format_evaluation_tooltip(piece_info, board, square, self.config)
    
    def set_arrow_preview(self, from_square: Optional[str], to_square: Optional[str], 
                         color: Optional[list[int]], size: float = 1.0) -> None:
        """Set arrow preview for drag operation.
        
        Args:
            from_square: Starting square (e.g., "e2") or None to clear preview.
            to_square: Ending square (e.g., "e4") or None to clear preview.
            color: RGB color [r, g, b] or None to clear preview.
            size: Size multiplier (default 1.0).
        """
        self._arrow_preview_from = from_square
        self._arrow_preview_to = to_square
        self._arrow_preview_color = color
        self._arrow_preview_size = size
    
    def set_annotation_model(self, annotation_model: Optional[AnnotationModel]) -> None:
        """Set the annotation model for drawing annotations.
        
        Args:
            annotation_model: AnnotationModel instance or None.
        """
        if self._annotation_model:
            # Disconnect from old model
            self._annotation_model.annotations_changed.disconnect(self.update)
        
        self._annotation_model = annotation_model
        
        if annotation_model:
            # Connect to model signals to update when annotations change
            annotation_model.annotations_changed.connect(self.update)
            annotation_model.annotation_added.connect(self.update)
            annotation_model.annotation_removed.connect(self.update)
            annotation_model.annotations_cleared.connect(self.update)
            annotation_model.annotations_visibility_changed.connect(self.update)
            # Force update to ensure current visibility state is reflected
            self.update()
    
    def set_game_model(self, game_model) -> None:
        """Set the game model for getting current ply.
        
        Args:
            game_model: GameModel instance.
        """
        self._game_model = game_model
    
    def _draw_annotations(self, painter: QPainter, board_start_x: int, board_start_y: int) -> None:
        """Draw annotations on the board.
        
        Args:
            painter: QPainter instance for drawing.
            board_start_x: X coordinate of the board's top-left corner.
            board_start_y: Y coordinate of the board's top-left corner.
        """
        if not self._annotation_model:
            return
        
        # Check if annotations are visible
        if not self._annotation_model.show_annotations:
            return  # Annotations are hidden, don't draw them
        
        # Get current ply from game model
        if not self._game_model:
            return
        
        ply_index = self._game_model.get_active_move_ply()
        annotations = self._annotation_model.get_annotations(ply_index)
        
        for annotation in annotations:
            color = QColor(annotation.color[0], annotation.color[1], annotation.color[2])
            
            # Get size multiplier (default to 1.0 if not set)
            size_multiplier = annotation.size if annotation.size is not None else 1.0
            # Get shadow setting (default to False if not set)
            has_shadow = annotation.shadow if annotation.shadow is not None else False
            
            if annotation.annotation_type == AnnotationType.ARROW:
                if annotation.from_square and annotation.to_square:
                    self._draw_annotation_arrow(painter, annotation.from_square, annotation.to_square,
                                               color, board_start_x, board_start_y, size_multiplier, has_shadow)
            elif annotation.annotation_type == AnnotationType.SQUARE:
                if annotation.square:
                    self._draw_annotation_square(painter, annotation.square, color,
                                                 board_start_x, board_start_y, size_multiplier)
            elif annotation.annotation_type == AnnotationType.CIRCLE:
                if annotation.square:
                    self._draw_annotation_circle(painter, annotation.square, color,
                                                board_start_x, board_start_y, size_multiplier, has_shadow)
            elif annotation.annotation_type == AnnotationType.TEXT:
                if annotation.square and annotation.text:
                    is_hovered = annotation.annotation_id == self._hovered_text_id
                    # text_size is stored as ratio of square_size (e.g., 0.15 = 15% of square_size)
                    # Default to 0.15 if not set (for backward compatibility with old absolute sizes)
                    default_text_size_ratio = 0.15  # 15% of square_size as default
                    text_size_ratio = annotation.text_size if annotation.text_size is not None else default_text_size_ratio
                    # If old absolute size (>= 1.0), convert to ratio (assuming square_size was ~80px)
                    if text_size_ratio >= 1.0:
                        text_size_ratio = text_size_ratio / 80.0  # Convert old absolute to ratio
                    # Apply size multiplier to text size
                    text_size_ratio = text_size_ratio * size_multiplier
                    self._draw_annotation_text(painter, annotation.square, annotation.text, color,
                                              annotation.text_x or 0.5, annotation.text_y or 0.5,
                                              text_size_ratio, annotation.text_rotation or 0.0,
                                              board_start_x, board_start_y, is_hovered, has_shadow)
        
        # Draw arrow preview if active (drawn after annotations so it appears on top)
        if self._arrow_preview_from and self._arrow_preview_to and self._arrow_preview_color:
            preview_color = QColor(self._arrow_preview_color[0], self._arrow_preview_color[1], self._arrow_preview_color[2])
            self._draw_annotation_arrow(painter, self._arrow_preview_from, self._arrow_preview_to,
                                       preview_color, board_start_x, board_start_y, self._arrow_preview_size, False)
    
    def _draw_annotation_arrow(self, painter: QPainter, from_square: str, to_square: str,
                               color: QColor, board_start_x: int, board_start_y: int,
                               size_multiplier: float = 1.0, shadow: bool = False) -> None:
        """Draw an annotation arrow.
        
        Args:
            painter: QPainter instance.
            from_square: Starting square (e.g., "e2").
            to_square: Ending square (e.g., "e4").
            color: Arrow color.
            board_start_x: Board start X.
            board_start_y: Board start Y.
            size_multiplier: Size multiplier (default 1.0).
            shadow: Whether to add black shadow for readability (default False).
        """
        try:
            from_sq = chess.parse_square(from_square)
            to_sq = chess.parse_square(to_square)
            
            # Get square centers
            from_x, from_y = self._get_square_center(from_sq, board_start_x, board_start_y)
            to_x, to_y = self._get_square_center(to_sq, board_start_x, board_start_y)
            
            # Draw arrow using existing arrow drawing logic
            # Apply size multiplier to both line width and arrowhead size
            line_width = max(1, int(2 * size_multiplier))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            
            # Calculate arrowhead size (apply size multiplier)
            arrowhead_size = self.square_size * 0.15 * size_multiplier
            dx = to_x - from_x
            dy = to_y - from_y
            length = (dx * dx + dy * dy) ** 0.5
            if length > 0:
                unit_x = dx / length
                unit_y = dy / length
                shortened_to_x = to_x - unit_x * arrowhead_size
                shortened_to_y = to_y - unit_y * arrowhead_size
                
                # Draw shadow if enabled (offset by 2px)
                if shadow:
                    shadow_offset = 2
                    shadow_color = QColor(0, 0, 0, 200)  # Black with some transparency
                    painter.setPen(QPen(shadow_color, line_width + 2))
                    painter.setBrush(QBrush(shadow_color))
                    painter.drawLine(int(from_x + shadow_offset), int(from_y + shadow_offset),
                                   int(shortened_to_x + shadow_offset), int(shortened_to_y + shadow_offset))
                    # Shadow arrowhead
                    shadow_arrowhead_points = QPolygonF([
                        QPointF(to_x + shadow_offset, to_y + shadow_offset),
                        QPointF(shortened_to_x + shadow_offset - unit_y * arrowhead_size * 0.5,
                               shortened_to_y + shadow_offset + unit_x * arrowhead_size * 0.5),
                        QPointF(shortened_to_x + shadow_offset + unit_y * arrowhead_size * 0.5,
                               shortened_to_y + shadow_offset - unit_x * arrowhead_size * 0.5)
                    ])
                    painter.drawPolygon(shadow_arrowhead_points)
                
                # Draw arrow line (with sized line width)
                painter.setPen(QPen(color, line_width))
                painter.setBrush(QBrush(color))
                painter.drawLine(int(from_x), int(from_y), int(shortened_to_x), int(shortened_to_y))
                
                # Draw arrowhead (with sized arrowhead)
                arrowhead_points = QPolygonF([
                    QPointF(to_x, to_y),
                    QPointF(shortened_to_x - unit_y * arrowhead_size * 0.5,
                           shortened_to_y + unit_x * arrowhead_size * 0.5),
                    QPointF(shortened_to_x + unit_y * arrowhead_size * 0.5,
                           shortened_to_y - unit_x * arrowhead_size * 0.5)
                ])
                painter.drawPolygon(arrowhead_points)
        except (ValueError, AttributeError):
            pass
    
    def _draw_annotation_square(self, painter: QPainter, square: str, color: QColor,
                                board_start_x: int, board_start_y: int,
                                size_multiplier: float = 1.0) -> None:
        """Draw an annotation square highlight.
        
        Args:
            painter: QPainter instance.
            square: Square name (e.g., "e4").
            color: Square color.
            board_start_x: Board start X.
            board_start_y: Board start Y.
            size_multiplier: Size multiplier (ignored for squares - always fills entire square).
        """
        try:
            sq = chess.parse_square(square)
            center_x, center_y = self._get_square_center(sq, board_start_x, board_start_y)
            
            # Draw semi-transparent overlay - always fills entire square (size multiplier ignored)
            overlay_color = QColor(color)
            overlay_color.setAlpha(128)  # 50% opacity
            # Square always fills the entire square, regardless of size multiplier
            size = self.square_size
            x = center_x - size / 2
            y = center_y - size / 2
            painter.fillRect(int(x), int(y), int(size), int(size),
                           QBrush(overlay_color))
        except (ValueError, AttributeError):
            pass
    
    def _draw_annotation_circle(self, painter: QPainter, square: str, color: QColor,
                               board_start_x: int, board_start_y: int,
                               size_multiplier: float = 1.0, shadow: bool = False) -> None:
        """Draw an annotation circle.
        
        Args:
            painter: QPainter instance.
            square: Square name (e.g., "e4").
            color: Circle color.
            board_start_x: Board start X.
            board_start_y: Board start Y.
            size_multiplier: Size multiplier (default 1.0) - only affects line width, not radius.
            shadow: Whether to add black shadow for readability (default False).
        """
        try:
            sq = chess.parse_square(square)
            x, y = self._get_square_center(sq, board_start_x, board_start_y)
            
            # Draw circle - radius stays constant (0.4 * square_size) to remain inside square
            # Only line width is affected by size multiplier
            radius = self.square_size * 0.4
            line_width = max(1, int(3 * size_multiplier))
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            
            # Draw shadow if enabled (offset by 2px)
            if shadow:
                shadow_offset = 2
                shadow_color = QColor(0, 0, 0, 200)  # Black with some transparency
                painter.setPen(QPen(shadow_color, line_width + 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(int(x - radius + shadow_offset), int(y - radius + shadow_offset),
                                  int(radius * 2), int(radius * 2))
            
            # Draw circle
            painter.setPen(QPen(color, line_width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(int(x - radius), int(y - radius), int(radius * 2), int(radius * 2))
        except (ValueError, AttributeError):
            pass
    
    def _draw_annotation_text(self, painter: QPainter, square: str, text: str, color: QColor,
                             text_x: float, text_y: float, text_size: float, text_rotation: float,
                             board_start_x: int, board_start_y: int, show_handles: bool = False,
                             shadow: bool = False) -> None:
        """Draw an annotation text.
        
        Args:
            painter: QPainter instance.
            square: Square name (e.g., "e4").
            text: Text content.
            color: Text color.
            text_x: X position relative to square (0-1).
            text_y: Y position relative to square (0-1).
            text_size: Text size in points.
            text_rotation: Text rotation in degrees.
            board_start_x: Board start X.
            board_start_y: Board start Y.
            show_handles: Whether to show resize/rotate handles.
            shadow: Whether to add black shadow for readability (default False).
        """
        try:
            sq = chess.parse_square(square)
            square_x, square_y = self._get_square_top_left(sq, board_start_x, board_start_y)
            
            # Account for board flip - flip text position relative to square
            is_flipped = False
            if self._board_model:
                is_flipped = self._board_model.is_flipped
            
            if is_flipped:
                # Flip text position relative to square to maintain visual position
                adjusted_text_x = 1.0 - text_x
                adjusted_text_y = 1.0 - text_y
            else:
                adjusted_text_x = text_x
                adjusted_text_y = text_y
            
            # Calculate text position (absolute on board, can be outside square)
            text_pos_x = square_x + adjusted_text_x * self.square_size
            text_pos_y = square_y + adjusted_text_y * self.square_size
            
            # Set font and color
            # text_size is stored as ratio of square_size (e.g., 0.15 = 15% of square_size)
            # Convert to absolute pixels for drawing
            absolute_text_size = max(8, int(text_size * self.square_size))  # Minimum 8px
            font = self._get_text_annotation_font(absolute_text_size)
            painter.setFont(font)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            
            # Get text metrics for centering
            metrics = QFontMetrics(font)
            text_rect = metrics.boundingRect(text)
            
            # Draw shadow if enabled (offset by 2px)
            if shadow:
                shadow_color = QColor(0, 0, 0, 200)  # Black with some transparency
                shadow_offset = 2
                painter.setPen(QPen(shadow_color))
                if text_rotation != 0:
                    painter.save()
                    painter.translate(text_pos_x + shadow_offset, text_pos_y + shadow_offset)
                    painter.rotate(text_rotation)
                    painter.drawText(-text_rect.width() // 2, text_rect.height() // 2, text)
                    painter.restore()
                else:
                    painter.drawText(int(text_pos_x - text_rect.width() // 2 + shadow_offset), 
                                   int(text_pos_y + text_rect.height() // 2 + shadow_offset), text)
            
            # Draw text
            painter.setPen(QPen(color))
            if text_rotation != 0:
                painter.save()
                painter.translate(text_pos_x, text_pos_y)
                painter.rotate(text_rotation)
                # Draw text centered at origin (0, 0) after translation
                painter.drawText(-text_rect.width() // 2, text_rect.height() // 2, text)
                painter.restore()
            else:
                # Draw text centered at position
                painter.drawText(int(text_pos_x - text_rect.width() // 2), 
                               int(text_pos_y + text_rect.height() // 2), text)
            
            # Draw handles if hovered
            if show_handles:
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                
                # Get text metrics for handle positioning (already calculated above)
                # text_rect is already available from above
                
                # Account for rotation in handle positions
                import math
                # Scale handle size with text size (minimum 6px, scales with text)
                # Use a percentage of text size, but ensure minimum visibility
                handle_size = max(6, int(absolute_text_size * 0.15))  # 15% of text size, min 6px
                text_half_width = text_rect.width() / 2
                text_half_height = text_rect.height() / 2
                
                # Position handles closer to text edge (60% instead of 80% for resize, 70% instead of 90% for rotate)
                # This keeps handles near the text even when text is very large
                resize_offset_factor = 0.6  # Position at 60% of text dimensions
                rotate_offset_factor = 0.7  # Position at 70% of text height
                
                if text_rotation != 0:
                    rad = math.radians(text_rotation)
                    cos_r = math.cos(rad)
                    sin_r = math.sin(rad)
                    # Resize handle: bottom-right corner in local space (inside text bounds)
                    # Position closer to text edge
                    resize_local_x = text_half_width * resize_offset_factor
                    resize_local_y = -text_half_height * resize_offset_factor
                    # Rotate to world space
                    resize_x = text_pos_x + resize_local_x * cos_r - resize_local_y * sin_r
                    resize_y = text_pos_y + resize_local_x * sin_r + resize_local_y * cos_r
                    
                    # Rotate handle: top center in local space (inside text bounds)
                    # Position closer to text edge
                    rotate_local_x = 0
                    rotate_local_y = -text_half_height * rotate_offset_factor
                    # Rotate to world space
                    rotate_x = text_pos_x + rotate_local_x * cos_r - rotate_local_y * sin_r
                    rotate_y = text_pos_y + rotate_local_x * sin_r + rotate_local_y * cos_r
                else:
                    # No rotation - handles are at fixed positions relative to text center
                    # Position handles closer to text edge
                    resize_x = text_pos_x + text_half_width * resize_offset_factor
                    resize_y = text_pos_y - text_half_height * resize_offset_factor
                    # Rotate handle at top edge but closer to text
                    rotate_x = text_pos_x
                    rotate_y = text_pos_y - text_half_height * rotate_offset_factor
                
                # Draw resize handle (blue)
                painter.setPen(QPen(QColor(255, 255, 255), 2))
                painter.setBrush(QBrush(QColor(100, 150, 255)))
                painter.drawEllipse(int(resize_x - handle_size), int(resize_y - handle_size),
                                   handle_size * 2, handle_size * 2)
                
                # Draw rotate handle (orange)
                painter.setBrush(QBrush(QColor(255, 150, 100)))
                painter.drawEllipse(int(rotate_x - handle_size), int(rotate_y - handle_size),
                                   handle_size * 2, handle_size * 2)
                
                painter.restore()
        except (ValueError, AttributeError):
            pass
    
    def _get_square_center(self, square: chess.Square, board_start_x: int, board_start_y: int) -> tuple[float, float]:
        """Get the center coordinates of a square.
        
        Args:
            square: Chess square index.
            board_start_x: Board start X.
            board_start_y: Board start Y.
            
        Returns:
            Tuple of (x, y) center coordinates.
        """
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        
        # Account for board flip
        is_flipped = False
        if self._board_model:
            is_flipped = self._board_model.is_flipped
        
        if is_flipped:
            col = 7 - file
            row = rank
        else:
            col = file
            row = 7 - rank
        
        x = board_start_x + col * self.square_size + self.square_size / 2
        y = board_start_y + row * self.square_size + self.square_size / 2
        
        return (x, y)
    
    def _get_square_top_left(self, square: chess.Square, board_start_x: int, board_start_y: int) -> tuple[float, float]:
        """Get the top-left coordinates of a square.
        
        Args:
            square: Chess square index.
            board_start_x: Board start X.
            board_start_y: Board start Y.
            
        Returns:
            Tuple of (x, y) top-left coordinates.
        """
        file = chess.square_file(square)
        rank = chess.square_rank(square)
        
        # Account for board flip
        is_flipped = False
        if self._board_model:
            is_flipped = self._board_model.is_flipped
        
        if is_flipped:
            col = 7 - file
            row = rank
        else:
            col = file
            row = 7 - rank
        
        x = board_start_x + col * self.square_size
        y = board_start_y + row * self.square_size
        
        return (x, y)
    
    def set_annotation_controller(self, annotation_controller) -> None:
        """Set the annotation controller for handling mouse events.
        
        Args:
            annotation_controller: AnnotationController instance.
        """
        self._annotation_controller = annotation_controller
    
    
    def _hit_test_text_annotation(self, pos: QPoint, annotation: Annotation, 
                                   board_start_x: int, board_start_y: int) -> Optional[str]:
        """Test if mouse position hits a text annotation or its handles.
        
        Args:
            pos: Mouse position.
            annotation: Text annotation to test.
            board_start_x: Board start X.
            board_start_y: Board start Y.
            
        Returns:
            "text" if hitting text body, "resize" if hitting resize handle,
            "rotate" if hitting rotate handle, None if not hitting.
        """
        if annotation.annotation_type != AnnotationType.TEXT or not annotation.square:
            return None
        
        try:
            sq = chess.parse_square(annotation.square)
            square_x, square_y = self._get_square_top_left(sq, board_start_x, board_start_y)
            
            # Account for board flip - flip text position relative to square
            is_flipped = False
            if self._board_model:
                is_flipped = self._board_model.is_flipped
            
            if is_flipped:
                # Flip text position relative to square to maintain visual position
                adjusted_text_x = 1.0 - (annotation.text_x or 0.5)
                adjusted_text_y = 1.0 - (annotation.text_y or 0.5)
            else:
                adjusted_text_x = annotation.text_x or 0.5
                adjusted_text_y = annotation.text_y or 0.5
            
            # Calculate text position
            text_x = square_x + adjusted_text_x * self.square_size
            text_y = square_y + adjusted_text_y * self.square_size
            
            # Get text metrics
            # text_size is stored as ratio of square_size (e.g., 0.15 = 15% of square_size)
            # Convert to absolute pixels for hit testing
            # IMPORTANT: Apply size multiplier to match how text is drawn
            default_text_size_ratio = 0.15  # 15% of square_size as default
            text_size_ratio = annotation.text_size if annotation.text_size is not None else default_text_size_ratio
            size_multiplier = annotation.size if annotation.size is not None else 1.0
            # Apply size multiplier to match drawing code
            text_size_ratio = text_size_ratio * size_multiplier
            absolute_text_size = max(8, int(text_size_ratio * self.square_size))  # Minimum 8px
            font = self._get_text_annotation_font(absolute_text_size)
            metrics = QFontMetrics(font)
            text = annotation.text or ""
            text_rect = metrics.boundingRect(text)
            
            # Text is centered at text_x, text_y
            # Text bounding box in local coordinates (before rotation)
            text_half_width = text_rect.width() / 2
            text_half_height = text_rect.height() / 2
            
            # Account for rotation in hit testing
            rotation = annotation.text_rotation or 0.0
            padding = 5
            # Scale handle size with text size (minimum 12px, scales with text)
            # Use a percentage of text size, but ensure minimum hit area for easier clicking
            # Make hit area larger than visual handle for better usability
            handle_size = max(12, int(absolute_text_size * 0.25))  # 25% of text size, min 12px (larger than visual for easier clicking)
            
            # Position handles closer to text edge (matching drawing code)
            resize_offset_factor = 0.6  # Position at 60% of text dimensions
            rotate_offset_factor = 0.7  # Position at 70% of text height
            
            if rotation != 0:
                import math
                # For rotated text, transform mouse position to text's local coordinate system
                rad = math.radians(rotation)
                cos_r = math.cos(rad)
                sin_r = math.sin(rad)
                # Transform mouse position to text's local coordinate system (rotate back)
                dx = pos.x() - text_x
                dy = pos.y() - text_y
                local_x = dx * cos_r + dy * sin_r
                local_y = -dx * sin_r + dy * cos_r
                
                # Check handles first (before text body) so they have priority
                # Resize handle (bottom-right in local space, inside text bounds)
                resize_local_x = text_half_width * resize_offset_factor
                resize_local_y = -text_half_height * resize_offset_factor
                if (abs(local_x - resize_local_x) <= handle_size and
                    abs(local_y - resize_local_y) <= handle_size):
                    return "resize"
                
                # Rotate handle (top in local space, inside text bounds)
                rotate_local_x = 0
                rotate_local_y = -text_half_height * rotate_offset_factor
                if (abs(local_x - rotate_local_x) <= handle_size and
                    abs(local_y - rotate_local_y) <= handle_size):
                    return "rotate"
                
                # Check if mouse is over text body (in local coordinates)
                if (-text_half_width - padding <= local_x <= text_half_width + padding and
                    -text_half_height - padding <= local_y <= text_half_height + padding):
                    return "text"
            else:
                # No rotation - simple hit test
                if (-text_half_width - padding <= pos.x() - text_x <= text_half_width + padding and
                    -text_half_height - padding <= pos.y() - text_y <= text_half_height + padding):
                    # Check handles first (before text body) so they have priority
                    # Check for resize handle (bottom-right corner, inside text bounds)
                    resize_handle_x = text_x + text_half_width * resize_offset_factor
                    resize_handle_y = text_y - text_half_height * resize_offset_factor
                    if (abs(pos.x() - resize_handle_x) <= handle_size and
                        abs(pos.y() - resize_handle_y) <= handle_size):
                        return "resize"
                    
                    # Check for rotate handle (top of text, inside text bounds)
                    rotate_handle_x = text_x
                    rotate_handle_y = text_y - text_half_height * rotate_offset_factor
                    if (abs(pos.x() - rotate_handle_x) <= handle_size and
                        abs(pos.y() - rotate_handle_y) <= handle_size):
                        return "rotate"
                    
                    return "text"
        except (ValueError, AttributeError):
            pass
        
        return None
    
    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move events for hover tooltips and text annotation editing.
        
        Args:
            event: Mouse event.
        """
        # Handle text annotation editing if active
        if self._editing_text_id and self._edit_mode and self._edit_start_pos and self._annotation_controller:
            self._handle_text_edit_drag(event.pos())
            self.update()  # Force redraw
            # Don't return - continue to check hover for other annotations
        
        # Call parent to ensure normal mouse handling still works
        super().mouseMoveEvent(event)
        
        # Check for text annotation hover (only if not currently editing)
        if not self._editing_text_id and self._annotation_model and self._game_model:
            if not self._cached_dimensions:
                self._calculate_board_dimensions()
            
            start_x, start_y = self._cached_dimensions['start_x'], self._cached_dimensions['start_y']
            ply_index = self._game_model.get_active_move_ply()
            annotations = self._annotation_model.get_annotations(ply_index)
            
            new_hovered_id = None
            for annotation in annotations:
                if annotation.annotation_type == AnnotationType.TEXT:
                    hit = self._hit_test_text_annotation(event.pos(), annotation, start_x, start_y)
                    if hit:
                        new_hovered_id = annotation.annotation_id
                        break
            
            if new_hovered_id != self._hovered_text_id:
                self._hovered_text_id = new_hovered_id
                self.update()  # Redraw to show/hide handles
        
        # Only show tooltip if heatmap is enabled and visible
        if (self.positional_heatmap_controller is None or 
            not self.positional_heatmap_controller.get_model().is_visible):
            QToolTip.hideText()
            return
        
        # Ensure cached dimensions are available
        if not self._cached_dimensions:
            self._calculate_board_dimensions()
        
        # Get square from mouse position
        square = self._get_square_from_mouse_pos(event.pos())
        if square is None:
            QToolTip.hideText()
            return
        
        # Check if there's a piece on this square
        if self._board_model is None or self._board_model.board.piece_at(square) is None:
            QToolTip.hideText()
            return
        
        # Get detailed evaluation
        board = self._board_model.board
        piece = board.piece_at(square)
        perspective = piece.color
        
        try:
            detailed = self.positional_heatmap_controller.analyzer.get_detailed_evaluation(board, perspective)
            piece_info = detailed.get('pieces', {}).get(square)
            
            if piece_info:
                tooltip_text = self._format_evaluation_tooltip(piece_info, board, square)
                # Convert widget position to global screen position
                global_pos = self.mapToGlobal(event.pos())
                # Use a very large timeout so tooltip stays visible until mouse moves away
                QToolTip.showText(global_pos, tooltip_text, self, QRect(), 999999)
            else:
                QToolTip.hideText()
        except Exception as e:
            # Log error for debugging
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error showing tooltip: {e}", exc_info=e)
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press events for text annotation editing.
        
        Args:
            event: Mouse event.
        """
        # Cancel any pending single-click timer
        if self._single_click_timer:
            self._single_click_timer.stop()
            self._single_click_timer = None
            self._pending_click_pos = None
            self._pending_click_annotation_id = None
        
        # Check for text annotation editing
        if (event.button() == Qt.MouseButton.LeftButton and 
            self._hovered_text_id and self._annotation_model and self._game_model and
            self._annotation_controller):
            
            if not self._cached_dimensions:
                self._calculate_board_dimensions()
            
            start_x, start_y = self._cached_dimensions['start_x'], self._cached_dimensions['start_y']
            ply_index = self._game_model.get_active_move_ply()
            annotations = self._annotation_model.get_annotations(ply_index)
            
            for annotation in annotations:
                if (annotation.annotation_id == self._hovered_text_id and 
                    annotation.annotation_type == AnnotationType.TEXT):
                    # Determine edit mode
                    hit = self._hit_test_text_annotation(event.pos(), annotation, start_x, start_y)
                    if hit:  # If hitting text or handle
                        # Store pending click info for delayed handling
                        self._pending_click_pos = event.pos()
                        self._pending_click_annotation_id = annotation.annotation_id
                        
                        # Start timer to delay single-click handling (wait for possible double-click)
                        self._single_click_timer = QTimer()
                        self._single_click_timer.setSingleShot(True)
                        self._single_click_timer.timeout.connect(self._handle_single_click)
                        self._single_click_timer.start(250)  # Qt's default double-click interval
                        return
        
        # Call parent for normal handling
        super().mousePressEvent(event)
    
    def _handle_single_click(self) -> None:
        """Handle single-click on text annotation (after timer delay)."""
        if not (self._pending_click_pos and self._pending_click_annotation_id and 
                self._annotation_model and self._game_model and self._annotation_controller):
            return
        
        if not self._cached_dimensions:
            self._calculate_board_dimensions()
        
        start_x, start_y = self._cached_dimensions['start_x'], self._cached_dimensions['start_y']
        ply_index = self._game_model.get_active_move_ply()
        annotations = self._annotation_model.get_annotations(ply_index)
        
        for annotation in annotations:
            if (annotation.annotation_id == self._pending_click_annotation_id and 
                annotation.annotation_type == AnnotationType.TEXT):
                # Determine edit mode
                hit = self._hit_test_text_annotation(self._pending_click_pos, annotation, start_x, start_y)
                if hit == "resize":
                    self._edit_mode = "resize"
                elif hit == "rotate":
                    self._edit_mode = "rotate"
                elif hit == "text":
                    self._edit_mode = "move"
                else:
                    # Not a valid hit, clear state
                    self._pending_click_pos = None
                    self._pending_click_annotation_id = None
                    return
                
                self._editing_text_id = annotation.annotation_id
                self._edit_start_pos = self._pending_click_pos
                # text_size is stored as ratio of square_size
                default_text_size_ratio = 0.15  # 15% of square_size as default
                text_size_ratio = annotation.text_size if annotation.text_size is not None else default_text_size_ratio
                # If old absolute size (>= 1.0), convert to ratio (assuming square_size was ~80px)
                if text_size_ratio >= 1.0:
                    text_size_ratio = text_size_ratio / 80.0  # Convert old absolute to ratio
                self._edit_start_params = {
                    'text_x': annotation.text_x or 0.5,
                    'text_y': annotation.text_y or 0.5,
                    'text_size': text_size_ratio,
                    'text_rotation': annotation.text_rotation or 0.0
                }
                
                # Clear pending state
                self._pending_click_pos = None
                self._pending_click_annotation_id = None
                return
    
    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release events to end text annotation editing.
        
        Args:
            event: Mouse event.
        """
        # End text editing if active
        if (event.button() == Qt.MouseButton.LeftButton and self._editing_text_id):
            # End editing
            self._editing_text_id = None
            self._edit_mode = None
            self._edit_start_pos = None
            self._edit_start_params = None
            self._hovered_text_id = None  # Clear hover state
            self.update()
            return  # Don't process further
        
        # Call parent for normal handling
        super().mouseReleaseEvent(event)
    
    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle double-click to edit text annotation content.
        
        Args:
            event: Mouse event.
        """
        # Cancel any pending single-click timer
        if self._single_click_timer:
            self._single_click_timer.stop()
            self._single_click_timer = None
            self._pending_click_pos = None
            self._pending_click_annotation_id = None
        
        # Only handle double-click if we're not currently editing (moving/resizing/rotating)
        if (event.button() == Qt.MouseButton.LeftButton and 
            not self._editing_text_id and
            self._hovered_text_id and self._annotation_model and self._game_model and
            self._annotation_controller):
            
            if not self._cached_dimensions:
                self._calculate_board_dimensions()
            
            start_x, start_y = self._cached_dimensions['start_x'], self._cached_dimensions['start_y']
            ply_index = self._game_model.get_active_move_ply()
            annotations = self._annotation_model.get_annotations(ply_index)
            
            for annotation in annotations:
                if (annotation.annotation_id == self._hovered_text_id and 
                    annotation.annotation_type == AnnotationType.TEXT):
                    # Verify we're actually hitting the text (not a handle)
                    hit = self._hit_test_text_annotation(event.pos(), annotation, start_x, start_y)
                    if hit == "text":  # Only open dialog if clicking on text body, not handles
                        # Open text input dialog to edit text content
                        from app.views.input_dialog import InputDialog
                        text, ok = InputDialog.get_text(
                            self.config,
                            "Edit Text Annotation",
                            "Enter text:",
                            annotation.text or "",
                            self
                        )
                        
                        if ok and text and text != annotation.text:
                            # Update text content via controller
                            self._annotation_controller.update_text_annotation(
                                annotation.annotation_id,
                                text=text
                            )
                        return
        
        # Call parent for normal handling
        super().mouseDoubleClickEvent(event)
    
    def _handle_text_edit_drag(self, current_pos: QPoint) -> None:
        """Handle dragging during text annotation editing.
        
        Args:
            current_pos: Current mouse position.
        """
        if not (self._editing_text_id and self._edit_mode and self._edit_start_pos and 
                self._edit_start_params and self._annotation_model and self._game_model):
            return
        
        if not self._cached_dimensions:
            self._calculate_board_dimensions()
        
        start_x, start_y = self._cached_dimensions['start_x'], self._cached_dimensions['start_y']
        ply_index = self._game_model.get_active_move_ply()
        annotations = self._annotation_model.get_annotations(ply_index)
        
        for annotation in annotations:
            if (annotation.annotation_id == self._editing_text_id and 
                annotation.annotation_type == AnnotationType.TEXT and annotation.square):
                
                sq = chess.parse_square(annotation.square)
                square_x, square_y = self._get_square_top_left(sq, start_x, start_y)
                
                # Account for board flip when calculating positions
                is_flipped = False
                if self._board_model:
                    is_flipped = self._board_model.is_flipped
                
                # Get stored text position (in logical coordinates)
                stored_text_x = self._edit_start_params['text_x']
                stored_text_y = self._edit_start_params['text_y']
                
                # Convert to visual coordinates for calculations
                if is_flipped:
                    visual_text_x = 1.0 - stored_text_x
                    visual_text_y = 1.0 - stored_text_y
                else:
                    visual_text_x = stored_text_x
                    visual_text_y = stored_text_y
                
                if self._edit_mode == "move":
                    # Move text - calculate absolute position on board
                    delta_x = current_pos.x() - self._edit_start_pos.x()
                    delta_y = current_pos.y() - self._edit_start_pos.y()
                    
                    # Get original absolute position (using visual coordinates)
                    original_abs_x = square_x + visual_text_x * self.square_size
                    original_abs_y = square_y + visual_text_y * self.square_size
                    
                    # Calculate new absolute position
                    new_abs_x = original_abs_x + delta_x
                    new_abs_y = original_abs_y + delta_y
                    
                    # Convert back to relative position (can be outside the square)
                    new_visual_text_x = (new_abs_x - square_x) / self.square_size
                    new_visual_text_y = (new_abs_y - square_y) / self.square_size
                    
                    # Convert back to logical coordinates for storage
                    if is_flipped:
                        new_text_x = 1.0 - new_visual_text_x
                        new_text_y = 1.0 - new_visual_text_y
                    else:
                        new_text_x = new_visual_text_x
                        new_text_y = new_visual_text_y
                    
                    # Allow movement anywhere on the board (no clamping)
                    self._annotation_controller.update_text_annotation(
                        annotation.annotation_id,
                        text_x=new_text_x,
                        text_y=new_text_y
                    )
                
                elif self._edit_mode == "resize":
                    # Resize text
                    import math
                    start_text_x = square_x + visual_text_x * self.square_size
                    start_text_y = square_y + visual_text_y * self.square_size
                    
                    # Get text metrics to calculate handle position
                    # IMPORTANT: Apply size multiplier to match how text is drawn
                    default_text_size_ratio = 0.15
                    text_size_ratio = self._edit_start_params['text_size']
                    size_multiplier = annotation.size if annotation.size is not None else 1.0
                    # Apply size multiplier to match drawing code
                    text_size_ratio = text_size_ratio * size_multiplier
                    absolute_text_size = max(8, int(text_size_ratio * self.square_size))
                    font = self._get_text_annotation_font(absolute_text_size)
                    metrics = QFontMetrics(font)
                    text = annotation.text or ""
                    text_rect = metrics.boundingRect(text)
                    text_half_width = text_rect.width() / 2
                    text_half_height = text_rect.height() / 2
                    
                    # Calculate resize handle position (at 60% of text dimensions from center)
                    resize_offset_factor = 0.6
                    resize_handle_offset_x = text_half_width * resize_offset_factor
                    resize_handle_offset_y = -text_half_height * resize_offset_factor
                    
                    # Handle rotation if present
                    rotation = self._edit_start_params.get('text_rotation', 0.0)
                    if rotation != 0:
                        rad = math.radians(rotation)
                        cos_r = math.cos(rad)
                        sin_r = math.sin(rad)
                        # Rotate handle offset to world space
                        handle_world_x = resize_handle_offset_x * cos_r - resize_handle_offset_y * sin_r
                        handle_world_y = resize_handle_offset_x * sin_r + resize_handle_offset_y * cos_r
                    else:
                        handle_world_x = resize_handle_offset_x
                        handle_world_y = resize_handle_offset_y
                    
                    # Calculate resize handle position in world coordinates
                    start_handle_x = start_text_x + handle_world_x
                    start_handle_y = start_text_y + handle_world_y
                    
                    # Calculate distance from resize handle position to mouse
                    # Use handle position as reference for more intuitive scaling
                    start_dist = math.sqrt(
                        (self._edit_start_pos.x() - start_handle_x) ** 2 +
                        (self._edit_start_pos.y() - start_handle_y) ** 2
                    )
                    current_dist = math.sqrt(
                        (current_pos.x() - start_handle_x) ** 2 +
                        (current_pos.y() - start_handle_y) ** 2
                    )
                    
                    # Scale size proportionally
                    # text_size is stored as ratio of square_size
                    # Add minimum distance to start_dist to prevent sudden jumps and ensure smooth scaling
                    # Don't clamp current_dist to allow scaling down from maximum
                    min_dist = max(15.0, text_half_width * 0.3)  # At least 30% of text half-width or 15px
                    start_dist = max(start_dist, min_dist)
                    # Allow current_dist to be smaller than min_dist to enable scaling down
                    current_dist = max(current_dist, 1.0)  # Only prevent division by zero, allow smaller values
                    
                    scale = current_dist / start_dist if start_dist > 0 else 1.0
                    start_size_ratio = self._edit_start_params['text_size']
                    new_size_ratio = start_size_ratio * scale
                    # Clamp to reasonable range (0.05 to 0.5 of square_size)
                    new_size_ratio = max(0.05, min(0.5, new_size_ratio))
                    
                    self._annotation_controller.update_text_annotation(
                        annotation.annotation_id,
                        text_size=new_size_ratio
                    )
                
                elif self._edit_mode == "rotate":
                    # Rotate text
                    import math
                    text_x = square_x + self._edit_start_params['text_x'] * self.square_size
                    text_y = square_y + self._edit_start_params['text_y'] * self.square_size
                    
                    # Calculate angle from text center to mouse
                    start_angle = math.degrees(math.atan2(
                        self._edit_start_pos.y() - text_y,
                        self._edit_start_pos.x() - text_x
                    ))
                    current_angle = math.degrees(math.atan2(
                        current_pos.y() - text_y,
                        current_pos.x() - text_x
                    ))
                    
                    delta_angle = current_angle - start_angle
                    new_rotation = (self._edit_start_params['text_rotation'] + delta_angle) % 360
                    
                    self._annotation_controller.update_text_annotation(
                        annotation.annotation_id,
                        text_rotation=new_rotation
                    )
                
                break
    
    def leaveEvent(self, event) -> None:
        """Handle mouse leave events to hide tooltip.
        
        Args:
            event: Leave event.
        """
        QToolTip.hideText()
        super().leaveEvent(event)

