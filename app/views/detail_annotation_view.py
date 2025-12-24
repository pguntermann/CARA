"""Annotation view for detail panel."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QToolButton,
    QButtonGroup, QColorDialog, QScrollArea, QLabel, QSizePolicy, QFrame, QSplitter, QSlider
)
from PyQt6.QtCore import Qt, QSize, QEvent, QPropertyAnimation, QEasingCurve, QTimer, QAbstractAnimation
import chess
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap, QPalette, QPen, QMouseEvent
from typing import Dict, Any, Optional

from app.models.game_model import GameModel
from app.views.chessboard_widget import ChessBoardWidget
from app.controllers.annotation_controller import AnnotationController
from app.models.annotation_model import AnnotationType


class DetailAnnotationView(QWidget):
    """Annotation view for drawing on the chessboard."""
    
    def __init__(self, config: Dict[str, Any], game_model: Optional[GameModel] = None,
                 annotation_controller: Optional[AnnotationController] = None,
                 board_widget: Optional[ChessBoardWidget] = None) -> None:
        """Initialize the annotation view.
        
        Args:
            config: Configuration dictionary.
            game_model: Optional GameModel to observe.
            annotation_controller: Optional AnnotationController for annotation operations.
            board_widget: Optional ChessboardWidget to add annotation layer to.
        """
        super().__init__()
        self.config = config
        self._game_model: Optional[GameModel] = None
        self._annotation_controller: Optional[AnnotationController] = annotation_controller
        self._board_widget = board_widget
        
        # Tool state
        self._current_tool = "arrow"  # arrow, square, circle, text
        self._arrow_style = "straight"  # straight, curved, bezier
        
        # Custom color palette (per game)
        self._custom_colors: list[QColor] = []
        
        # Annotation drawing state
        self._annotation_start_square: Optional[str] = None
        self._annotation_preview_square: Optional[str] = None  # Current square during arrow drag
        
        # Load config values
        self._load_config()
        
        self._setup_ui()
        
        # Connect to game model if provided
        if game_model:
            self.set_game_model(game_model)
        
        # Connect board widget if provided
        if board_widget and annotation_controller:
            self.set_board_widget(board_widget)
    
    def _load_config(self) -> None:
        """Load configuration values from config dictionary."""
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        annotations_config = panel_config.get('annotations', {})
        
        # Layout config
        layout_config = annotations_config.get('layout', {})
        self.layout_spacing = layout_config.get('spacing', 8)
        self.controls_padding = layout_config.get('controls_padding', 5)
        self.controls_spacing = layout_config.get('controls_spacing', 8)
        self.action_buttons_spacing = layout_config.get('action_buttons_spacing', 3)
        self.toolbar_spacing = layout_config.get('toolbar_spacing', 8)
        self.toolbar_row_spacing = layout_config.get('toolbar_row_spacing', 3)
        self.color_palette_spacing = layout_config.get('color_palette_spacing', 8)
        self.color_row_spacing = layout_config.get('color_row_spacing', 3)
        self.annotations_section_spacing = layout_config.get('annotations_section_spacing', 5)
        self.annotations_header_spacing = layout_config.get('annotations_header_spacing', 5)
        self.annotations_list_spacing = layout_config.get('annotations_list_spacing', 3)
        self.annotations_list_margins = layout_config.get('annotations_list_margins', [5, 5, 5, 5])
        
        # Tool buttons config
        tool_buttons_config = annotations_config.get('tool_buttons', {})
        self.tool_button_min_width = tool_buttons_config.get('minimum_width', 50)
        self.compact_mode_threshold = tool_buttons_config.get('compact_mode_threshold', 400)
        self.tool_button_height = tool_buttons_config.get('height', 32)
        
        # Color swatches config
        color_swatches_config = annotations_config.get('color_swatches', {})
        self.color_swatch_size = color_swatches_config.get('size', 34)
        selected_border_color = color_swatches_config.get('selected_border_color', [120, 150, 200])
        self.selected_border_color = QColor(selected_border_color[0], selected_border_color[1], selected_border_color[2])
        self.selected_border_width = color_swatches_config.get('selected_border_width', 2)
        unselected_border_color = color_swatches_config.get('unselected_border_color', [180, 180, 180])
        self.unselected_border_color = QColor(unselected_border_color[0], unselected_border_color[1], unselected_border_color[2])
        self.unselected_border_width = color_swatches_config.get('unselected_border_width', 1)
        
        # Preset colors - check user settings first, then config defaults
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings = settings_service.get_settings()
        annotations_prefs = settings.get('annotations', {})
        
        preset_colors_list = annotations_prefs.get('preset_colors', None)
        if preset_colors_list is None:
            # Use config defaults
            preset_colors_list = annotations_config.get('preset_colors', [[255, 0, 0], [0, 255, 0], [0, 0, 255], [255, 255, 0], [255, 0, 255], [0, 255, 255], [255, 165, 0], [255, 192, 203], [128, 0, 128], [255, 255, 255]])
        
        self.preset_colors = [QColor(color[0], color[1], color[2]) for color in preset_colors_list]
        
        # Default color
        default_color_list = annotations_config.get('default_color', [255, 0, 0])
        self._current_color = QColor(default_color_list[0], default_color_list[1], default_color_list[2])
        
        # Size slider config
        size_slider_config = annotations_config.get('size_slider', {})
        self.size_slider_min = size_slider_config.get('minimum', 50)
        self.size_slider_max = size_slider_config.get('maximum', 200)
        self.size_slider_default = size_slider_config.get('default', 100)
        self.size_slider_tick_interval = size_slider_config.get('tick_interval', 25)
        # Current size (as percentage, 100 = 1.0 = default size)
        self._current_size = self.size_slider_default / 100.0  # Convert to multiplier (1.0 = 100%)
        # Current shadow state
        self._current_shadow = False  # Default to no shadow
        
        # Annotations list config
        annotations_list_config = annotations_config.get('annotations_list', {})
        self.annotations_list_min_height = annotations_list_config.get('minimum_height', 100)
        wrapping_config = annotations_list_config.get('wrapping', {})
        self.color_buffer = wrapping_config.get('color_buffer', 0)
        self.tool_buffer = wrapping_config.get('tool_buffer', 10)
        self.tool_verification_buffer = wrapping_config.get('tool_verification_buffer', 6)
        
        # Splitter config
        splitter_config = annotations_config.get('splitter', {})
        self.splitter_controls_height = splitter_config.get('controls_height', 200)
        self.splitter_annotations_height = splitter_config.get('annotations_height', 300)
        self.splitter_controls_stretch = splitter_config.get('controls_stretch_factor', 0)
        self.splitter_annotations_stretch = splitter_config.get('annotations_stretch_factor', 1)
    
    def _setup_ui(self) -> None:
        """Setup the annotation view UI."""
        layout = QVBoxLayout(self)
        ui_config = self.config.get('ui', {})
        # Get margins - follow same pattern as other detail views
        margins = ui_config.get('margins', {}).get('detail_panel', [0, 0, 0, 0])
        if not isinstance(margins, list):
            margins = [0, 0, 0, 0]
        layout.setContentsMargins(0, 0, 0, 0)  # No margins on main layout, container will handle padding
        layout.setSpacing(self.layout_spacing)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # Top-align all content
        
        # Get panel config
        panel_config = ui_config.get('panels', {}).get('detail', {}).get('tabs', {})
        pane_bg = panel_config.get('pane_background', [40, 40, 45])
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        self.setPalette(palette)
        
        # Container for all controls (action buttons, toolbar, color palette)
        controls_container = QFrame()
        controls_layout = QVBoxLayout(controls_container)
        # Use padding from config, but ensure minimum based on margins
        padding = max(margins[0], self.controls_padding)
        controls_layout.setContentsMargins(padding, padding, padding, padding)
        # Set spacing to match top padding for consistent spacing
        controls_layout.setSpacing(padding)
        # Ensure container respects its layout margins
        controls_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        # Calculate minimum height to prevent truncation:
        # - Action buttons: tool_button_height
        # - Spacing after action buttons: controls_spacing
        # - Tool buttons: tool_button_height (can wrap to multiple rows, but minimum is 1 row)
        # - Spacing after toolbar: controls_spacing
        # - Color swatches: 2 rows (color_swatch_size + spacing + color_swatch_size) to prevent truncation
        # - Spacing after color palette: controls_spacing
        # - Size slider: ~30px (approximate height for QSlider with label)
        # - Padding: top + bottom
        # Add extra buffer to ensure nothing gets cut off
        size_slider_height = 35  # Approximate height for slider with label
        min_height = (self.tool_button_height +           # Action buttons
                     padding +                              # Spacing (matches top padding)
                     self.tool_button_height +              # Tool buttons (1 row minimum)
                     padding +                              # Spacing (matches top padding)
                     self.color_swatch_size +               # Color swatches row 1
                     self.color_row_spacing +               # Spacing between color rows
                     self.color_swatch_size +               # Color swatches row 2
                     padding +                              # Spacing (matches top padding)
                     size_slider_height +                   # Size slider
                     padding * 2 +                          # Top and bottom padding
                     30)                                    # Extra buffer to prevent truncation
        controls_container.setMinimumHeight(min_height)
        
        # Action buttons (at top)
        action_layout = QHBoxLayout()
        action_layout.setSpacing(self.action_buttons_spacing)
        
        self.save_btn = QPushButton("Save Annotations")
        self.save_btn.setFixedHeight(self.tool_button_height)  # Match tool button height
        action_layout.addWidget(self.save_btn)
        
        self.clear_all_btn = QPushButton("Clear All")
        self.clear_all_btn.setFixedHeight(self.tool_button_height)  # Match tool button height
        action_layout.addWidget(self.clear_all_btn)
        
        # No stretch - keep buttons left-aligned
        
        controls_layout.addLayout(action_layout)
        
        # Toolbar frame (for responsive layout)
        toolbar_frame = QFrame()
        toolbar_frame_layout = QVBoxLayout(toolbar_frame)
        toolbar_frame_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_frame_layout.setSpacing(self.toolbar_spacing)
        
        # Tool buttons container (responsive - can wrap to multiple rows)
        self.tool_buttons_container = QWidget()
        self.tool_buttons_layout = QVBoxLayout(self.tool_buttons_container)
        self.tool_buttons_layout.setContentsMargins(0, 0, 0, 0)
        self.tool_buttons_layout.setSpacing(self.toolbar_row_spacing)
        
        # Tool button row 1
        self.tool_row1_widget = QWidget()
        self.tool_row1_layout = QHBoxLayout(self.tool_row1_widget)
        self.tool_row1_layout.setContentsMargins(0, 0, 0, 0)
        self.tool_row1_layout.setSpacing(self.toolbar_row_spacing)
        self.tool_buttons_layout.addWidget(self.tool_row1_widget)
        
        # Tool button row 2
        self.tool_row2_widget = QWidget()
        self.tool_row2_layout = QHBoxLayout(self.tool_row2_widget)
        self.tool_row2_layout.setContentsMargins(0, 0, 0, 0)
        self.tool_row2_layout.setSpacing(self.toolbar_row_spacing)
        self.tool_buttons_layout.addWidget(self.tool_row2_widget)
        
        # Tool button row 3
        self.tool_row3_widget = QWidget()
        self.tool_row3_layout = QHBoxLayout(self.tool_row3_widget)
        self.tool_row3_layout.setContentsMargins(0, 0, 0, 0)
        self.tool_row3_layout.setSpacing(self.toolbar_row_spacing)
        self.tool_buttons_layout.addWidget(self.tool_row3_widget)
        
        # Tool buttons group
        self.tool_group = QButtonGroup(self)
        
        # Arrow tool
        self.arrow_btn = QToolButton()
        self.arrow_btn.setText("Arrow")
        self.arrow_btn.setCheckable(True)
        self.arrow_btn.setChecked(True)
        self.arrow_btn.setToolTip("Draw arrow")
        self.arrow_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.arrow_btn.setMinimumWidth(self.tool_button_min_width)
        self.arrow_btn.setFixedHeight(self.tool_button_height)  # Fixed height from config, width scales
        self.tool_group.addButton(self.arrow_btn, 0)
        
        # Square tool
        self.square_btn = QToolButton()
        self.square_btn.setText("Square")
        self.square_btn.setCheckable(True)
        self.square_btn.setToolTip("Highlight square")
        self.square_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.square_btn.setMinimumWidth(self.tool_button_min_width)
        self.square_btn.setFixedHeight(self.tool_button_height)  # Fixed height from config, width scales
        self.tool_group.addButton(self.square_btn, 1)
        
        # Circle tool
        self.circle_btn = QToolButton()
        self.circle_btn.setText("Circle")
        self.circle_btn.setCheckable(True)
        self.circle_btn.setToolTip("Circle square")
        self.circle_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.circle_btn.setMinimumWidth(self.tool_button_min_width)
        self.circle_btn.setFixedHeight(self.tool_button_height)  # Fixed height from config, width scales
        self.tool_group.addButton(self.circle_btn, 2)
        
        # Text tool
        self.text_btn = QToolButton()
        self.text_btn.setText("Text")
        self.text_btn.setCheckable(True)
        self.text_btn.setToolTip("Add text annotation")
        self.text_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.text_btn.setMinimumWidth(self.tool_button_min_width)
        self.text_btn.setFixedHeight(self.tool_button_height)  # Fixed height from config, width scales
        self.tool_group.addButton(self.text_btn, 3)
        
        # Store tool buttons list
        self.tool_buttons = [self.arrow_btn, self.square_btn, self.circle_btn, self.text_btn]
        
        # Initially add all to row 1, will be redistributed based on width
        for btn in self.tool_buttons:
            self.tool_row1_layout.addWidget(btn)
        
        toolbar_frame_layout.addWidget(self.tool_buttons_container)
        
        controls_layout.addWidget(toolbar_frame)
        
        # Store reference for resize event handling
        self.toolbar_frame = toolbar_frame
        toolbar_frame.installEventFilter(self)
        self.tool_buttons_container.installEventFilter(self)
        
        # Color palette section (responsive, wraps to second row when narrow)
        color_frame = QFrame()
        color_frame_layout = QVBoxLayout(color_frame)
        color_frame_layout.setContentsMargins(0, 0, 0, 0)
        color_frame_layout.setSpacing(self.color_palette_spacing)
        
        # Color rows container (can have 1 or 2 rows depending on width)
        self.color_rows_container = QWidget()
        self.color_rows_layout = QVBoxLayout(self.color_rows_container)
        self.color_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.color_rows_layout.setSpacing(self.color_row_spacing)
        
        # Color row 1: First part of preset colors
        self.color_row1_widget = QWidget()
        self.color_row1_layout = QHBoxLayout(self.color_row1_widget)
        self.color_row1_layout.setContentsMargins(0, 0, 0, 0)
        self.color_row1_layout.setSpacing(self.color_row_spacing)
        self.color_rows_layout.addWidget(self.color_row1_widget)
        
        # Color row 2: Second part of preset colors (shown when narrow)
        self.color_row2_widget = QWidget()
        self.color_row2_layout = QHBoxLayout(self.color_row2_widget)
        self.color_row2_layout.setContentsMargins(0, 0, 0, 0)
        self.color_row2_layout.setSpacing(self.color_row_spacing)
        self.color_rows_layout.addWidget(self.color_row2_widget)
        
        self.color_buttons = []
        for i, color in enumerate(self.preset_colors):
            btn = QPushButton()
            btn.setFixedSize(self.color_swatch_size, self.color_swatch_size)  # Fixed size to prevent truncation
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)  # Fixed size policy
            btn.setToolTip(f"RGB({color.red()}, {color.green()}, {color.blue()})")
            btn.setProperty("color_index", i)  # Store index for click handling
            self._set_button_color(btn, color)
            self.color_buttons.append(btn)
            # Connect click to set current color
            btn.clicked.connect(lambda checked, idx=i, col=color: self._on_color_selected(idx, col))
            # Initially add all to row 1, will be redistributed based on width
            self.color_row1_layout.addWidget(btn)
        
        # Highlight the initially selected color (find index of default color)
        default_color_index = 0
        found_color = False
        for i, color in enumerate(self.preset_colors):
            if color == self._current_color:
                default_color_index = i
                found_color = True
                break
        # If default color not found in preset_colors, use the first preset color
        if not found_color and self.preset_colors:
            default_color_index = 0
            self._current_color = self.preset_colors[0]
        self._update_color_selection(default_color_index)
        
        color_frame_layout.addWidget(self.color_rows_container)
        
        # Store reference for resize handling
        self.color_frame = color_frame
        color_frame.installEventFilter(self)
        
        controls_layout.addWidget(color_frame)
        
        # Size slider
        size_slider_container = QFrame()
        size_slider_layout = QHBoxLayout(size_slider_container)
        size_slider_layout.setContentsMargins(0, 0, 0, 0)
        size_slider_layout.setSpacing(8)
        
        size_label = QLabel("Size:")
        size_slider_layout.addWidget(size_label)
        
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setMinimum(self.size_slider_min)
        self.size_slider.setMaximum(self.size_slider_max)
        self.size_slider.setValue(self.size_slider_default)
        self.size_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.size_slider.setTickInterval(self.size_slider_tick_interval)
        # Make slider snap to tick intervals
        self.size_slider.setSingleStep(self.size_slider_tick_interval)
        self.size_slider.setPageStep(self.size_slider_tick_interval)
        self.size_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        size_slider_layout.addWidget(self.size_slider)
        
        self.size_value_label = QLabel(f"{self.size_slider_default}%")
        self.size_value_label.setMinimumWidth(40)
        self.size_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        size_slider_layout.addWidget(self.size_value_label)
        
        # Shadow toggle button (next to size slider)
        self.shadow_button = QPushButton("Shadow: OFF")
        self.shadow_button.setCheckable(True)  # Make it a toggle button
        self.shadow_button.setChecked(False)  # Default to no shadow
        self.shadow_button.setFixedHeight(self.tool_button_height)  # Match tool button height
        self.shadow_button.setMinimumWidth(100)  # Reasonable width for the button text
        self.shadow_button.clicked.connect(self._on_shadow_toggled)
        size_slider_layout.addWidget(self.shadow_button)
        
        # Connect slider to update size
        # Connect sliderReleased to snap to nearest tick when dragging ends
        self.size_slider.sliderReleased.connect(self._on_size_slider_released)
        # Connect valueChanged for updates (also handles keyboard/click changes)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        
        controls_layout.addWidget(size_slider_container)
        
        # Create vertical splitter to allow resizing between controls and annotations list
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Add controls container to splitter (top section)
        self.splitter.addWidget(controls_container)
        
        # Annotations section (simplified design - always visible compact list)
        annotations_section = QFrame()
        annotations_layout = QVBoxLayout(annotations_section)
        annotations_layout.setContentsMargins(padding, padding, padding, padding)
        annotations_layout.setSpacing(self.annotations_section_spacing)
        
        # Header with count
        annotations_header = QHBoxLayout()
        annotations_header.setSpacing(self.annotations_header_spacing)
        
        self.annotation_count_label = QLabel("Annotations:")
        annotations_header.addWidget(self.annotation_count_label)
        
        self.annotation_count_value = QLabel("0")
        annotations_header.addWidget(self.annotation_count_value)
        
        annotations_header.addStretch()
        
        annotations_layout.addLayout(annotations_header)
        
        # Scrollable annotation list (resizable, no max height restriction)
        self.annotation_scroll = QScrollArea()
        self.annotation_scroll.setWidgetResizable(True)
        self.annotation_scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.annotation_scroll.setMinimumHeight(self.annotations_list_min_height)
        self.annotation_scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        self.annotation_list_widget = QWidget()
        self.annotation_list_layout = QVBoxLayout(self.annotation_list_widget)
        list_margins = self.annotations_list_margins
        self.annotation_list_layout.setContentsMargins(list_margins[0], list_margins[1], list_margins[2], list_margins[3])
        self.annotation_list_layout.setSpacing(self.annotations_list_spacing)
        
        self.annotation_scroll.setWidget(self.annotation_list_widget)
        annotations_layout.addWidget(self.annotation_scroll)
        
        # Add annotations section to splitter (bottom section)
        self.splitter.addWidget(annotations_section)
        
        # Set splitter sizes and stretch factors from config
        self.splitter.setSizes([self.splitter_controls_height, self.splitter_annotations_height])
        self.splitter.setStretchFactor(0, self.splitter_controls_stretch)
        self.splitter.setStretchFactor(1, self.splitter_annotations_stretch)
        self.splitter.setCollapsible(0, False)  # Don't allow controls to collapse
        self.splitter.setCollapsible(1, False)  # Don't allow annotations to collapse
        
        # Fix cursor on splitter handle for macOS compatibility
        # Vertical splitter needs horizontal resize cursor
        for i in range(self.splitter.count() - 1):
            handle = self.splitter.handle(i)
            if handle:
                handle.setCursor(Qt.CursorShape.SizeVerCursor)
        
        # Add splitter to main layout
        layout.addWidget(self.splitter)
        
        # Disabled state placeholder (shown when no active game)
        self.disabled_placeholder = QLabel("No active game. Load a game to add annotations.")
        self.disabled_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.disabled_placeholder.setWordWrap(True)
        self.disabled_placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.disabled_placeholder.setStyleSheet("""
            QLabel {
                color: rgb(150, 150, 150);
                font-size: 14px;
                padding: 20px;
            }
        """)
        self.disabled_placeholder.hide()  # Initially hidden
        layout.addWidget(self.disabled_placeholder)
        
        # Apply styling
        self._apply_styling()
        
        # Connect signals
        self.tool_group.buttonClicked.connect(self._on_tool_changed)
        self.save_btn.clicked.connect(self._on_save_clicked)
        self.clear_all_btn.clicked.connect(self._on_clear_all_clicked)
        
        # Connect annotation model signals if controller is available
        if self._annotation_controller:
            annotation_model = self._annotation_controller.get_annotation_model()
            annotation_model.annotations_changed.connect(self._on_annotations_changed)
            annotation_model.annotation_added.connect(self._on_annotation_added)
            annotation_model.annotation_removed.connect(self._on_annotation_removed)
            annotation_model.annotations_cleared.connect(self._on_annotations_cleared)
            # Initial population of annotation list
            if self._game_model:
                QTimer.singleShot(0, self._populate_annotation_list)
        
        # Initial visibility checks with delays
        QTimer.singleShot(0, self._update_color_wrapping)
        QTimer.singleShot(0, self._update_toolbar_wrapping)
        QTimer.singleShot(0, self._update_toolbar_compact_mode)
        QTimer.singleShot(100, self._update_color_wrapping)
        QTimer.singleShot(100, self._update_toolbar_wrapping)
        QTimer.singleShot(100, self._update_toolbar_compact_mode)
        
        # Initialize disabled state (will be updated when game model is set)
        self._update_disabled_state(False)
    
    def _set_button_color(self, button: QPushButton, color: QColor, is_selected: bool = False) -> None:
        """Set button background color with round shape.
        
        Args:
            button: The button to style.
            color: The color to display.
            is_selected: Whether this is the currently selected color.
        """
        # Use minimum height for icon size to keep it circular
        icon_size = button.minimumHeight() if button.minimumHeight() > 0 else self.color_swatch_size
        # Create circular pixmap
        pixmap = QPixmap(icon_size, icon_size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color.red(), color.green(), color.blue()))
        # Use thicker, more visible border for selected color
        if is_selected:
            # Draw outer ring with selected border color
            painter.setPen(QPen(self.selected_border_color, self.selected_border_width))
            painter.setBrush(Qt.BrushStyle.NoBrush)  # No fill for outer ring
            painter.drawEllipse(1, 1, icon_size - 2, icon_size - 2)
            # Draw inner colored circle with border
            painter.setBrush(QColor(color.red(), color.green(), color.blue()))
            painter.setPen(QPen(self.selected_border_color, self.selected_border_width))
            border_width = self.selected_border_width + 1
            painter.drawEllipse(border_width, border_width, icon_size - (border_width * 2), icon_size - (border_width * 2))
        else:
            painter.setPen(QPen(self.unselected_border_color, self.unselected_border_width))
            border_width = self.unselected_border_width
            painter.drawEllipse(border_width, border_width, icon_size - (border_width * 2), icon_size - (border_width * 2))
        painter.end()
        button.setIcon(QIcon(pixmap))
        button.setIconSize(QSize(icon_size, icon_size))
        # Center the icon horizontally when button stretches
        button.setStyleSheet("border: none; background: transparent; text-align: center;")
    
    def _apply_styling(self) -> None:
        """Apply styling from config."""
        ui_config = self.config.get('ui', {})
        tabs_config = ui_config.get('panels', {}).get('detail', {}).get('tabs', {})
        colors_config = tabs_config.get('colors', {})
        normal = colors_config.get('normal', {})
        norm_text = normal.get('text', [200, 200, 200])
        norm_bg = normal.get('background', [50, 50, 55])
        norm_border = normal.get('border', [60, 60, 65])
        hover = colors_config.get('hover', {})
        hover_bg = hover.get('background', [60, 60, 65])
        hover_text = hover.get('text', [240, 240, 240])
        active = colors_config.get('active', {})
        active_bg = active.get('background', [70, 90, 130])
        active_text = active.get('text', [240, 240, 240])
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        
        # Get button config from manual analysis (for consistency)
        panel_config = ui_config.get('panels', {}).get('detail', {})
        manual_analysis_config = panel_config.get('manual_analysis', {})
        button_config = manual_analysis_config.get('buttons', {})
        button_border_radius = button_config.get('border_radius', 4)
        button_padding = button_config.get('padding', [6, 4])
        button_height = button_config.get('height', 28)
        
        # Style tool buttons (with rounded corners)
        tool_style = f"""
            QToolButton {{
                background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
                border-radius: {button_border_radius}px;
                padding: {button_padding[0]}px {button_padding[1]}px;
                min-height: {button_height}px;
                min-width: 60px;
            }}
            QToolButton:checked {{
                background-color: rgb({active_bg[0]}, {active_bg[1]}, {active_bg[2]});
                color: rgb({active_text[0]}, {active_text[1]}, {active_text[2]});
                border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
            }}
            QToolButton:hover {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
                color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
            }}
            QToolButton:focus {{
                outline: none;
            }}
        """
        
        for btn in [self.arrow_btn, self.square_btn, self.circle_btn, self.text_btn]:
            btn.setStyleSheet(tool_style)
        
        # Style regular buttons (with rounded corners, matching manual analysis)
        # Get pressed background offset from config
        buttons_config = ui_config.get('buttons', {})
        button_pressed_offset = buttons_config.get('pressed_background_offset', 10)
        
        button_style = f"""
            QPushButton {{
                background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
                border-radius: {button_border_radius}px;
                padding: {button_padding[0]}px {button_padding[1]}px;
                min-height: {button_height}px;
            }}
            QPushButton:hover {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
                color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
            }}
            QPushButton:pressed {{
                background-color: rgb({min(255, norm_bg[0] + button_pressed_offset)}, {min(255, norm_bg[1] + button_pressed_offset)}, {min(255, norm_bg[2] + button_pressed_offset)});
            }}
            QPushButton:focus {{
                outline: none;
            }}
        """
        
        self.save_btn.setStyleSheet(button_style)
        self.clear_all_btn.setStyleSheet(button_style)
        
        # Style shadow button with checked state (toggle button)
        shadow_button_style = f"""
            QPushButton {{
                background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
                border-radius: {button_border_radius}px;
                padding: {button_padding[0]}px {button_padding[1]}px;
                min-height: {button_height}px;
            }}
            QPushButton:checked {{
                background-color: rgb({active_bg[0]}, {active_bg[1]}, {active_bg[2]});
                color: rgb({active_text[0]}, {active_text[1]}, {active_text[2]});
                border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
            }}
            QPushButton:hover {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
                color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
            }}
            QPushButton:pressed {{
                background-color: rgb({min(255, norm_bg[0] + button_pressed_offset)}, {min(255, norm_bg[1] + button_pressed_offset)}, {min(255, norm_bg[2] + button_pressed_offset)});
            }}
            QPushButton:focus {{
                outline: none;
            }}
        """
        
        if hasattr(self, 'shadow_button'):
            self.shadow_button.setStyleSheet(shadow_button_style)
        
        # Style labels
        label_style = f"color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});"
        for label in [self.annotation_count_label, self.annotation_count_value]:
            label.setStyleSheet(label_style)
    
    def eventFilter(self, obj, event) -> bool:
        """Event filter to handle resize events on UI elements and mouse events on chessboard."""
        # Handle resize events for UI layout updates
        if hasattr(self, 'toolbar_frame') and obj == self.toolbar_frame:
            if event.type() == QEvent.Type.Resize:
                # Update toolbar wrapping and compact mode when frame is resized
                QTimer.singleShot(50, self._update_toolbar_wrapping)
                QTimer.singleShot(50, self._update_toolbar_compact_mode)
            elif event.type() == QEvent.Type.Show:
                # Also check when frame is shown
                QTimer.singleShot(50, self._update_toolbar_wrapping)
                QTimer.singleShot(50, self._update_toolbar_compact_mode)
        elif hasattr(self, 'color_frame') and obj == self.color_frame:
            if event.type() == QEvent.Type.Resize:
                # Update color wrapping when frame is resized
                QTimer.singleShot(50, self._update_color_wrapping)
        elif hasattr(self, 'tool_buttons_container') and obj == self.tool_buttons_container:
            if event.type() == QEvent.Type.Resize:
                # Update tool button wrapping when container is resized
                QTimer.singleShot(50, self._update_toolbar_wrapping)
        # Handle mouse events on chessboard for annotation drawing
        # Only process if annotation view is visible (tab is active)
        elif (self._board_widget is not None and obj == self._board_widget):
            # Check if board widget is editing text - if so, don't interfere
            if hasattr(self._board_widget, '_editing_text_id') and self._board_widget._editing_text_id:
                # Board widget is handling text editing, don't interfere
                pass
            elif (event.type() == QEvent.Type.MouseButtonPress and self.isVisible()):
                if (isinstance(event, QMouseEvent) and 
                    event.button() == Qt.MouseButton.LeftButton and 
                    self._annotation_controller is not None):
                    # Check if clicking on existing text annotation - if so, let board widget handle it
                    if (hasattr(self._board_widget, '_hovered_text_id') and 
                        self._board_widget._hovered_text_id):
                        # Hovering over text, let board widget handle the click
                        pass
                    else:
                        # Get square from mouse position
                        square = self._board_widget._get_square_from_mouse_pos(event.pos())
                        if square is not None:
                            square_name = chess.square_name(square)
                            # For text tool, check if text already exists at this position
                            if self._current_tool == "text":
                                if self._game_model and self._annotation_controller:
                                    ply_index = self._game_model.get_active_move_ply()
                                    annotation_model = self._annotation_controller.get_annotation_model()
                                    annotations = annotation_model.get_annotations(ply_index)
                                    # Check if there's any text annotation on this square
                                    has_text = False
                                    for annotation in annotations:
                                        if (annotation.annotation_type == AnnotationType.TEXT and 
                                            annotation.square == square_name):
                                            has_text = True
                                            break
                                    # If text exists, don't handle click - let board widget handle it
                                    if has_text:
                                        pass  # Let board widget handle it
                                    else:
                                        self._handle_annotation_click(square_name)
                            else:
                                self._handle_annotation_click(square_name)
                        # Don't return True - let the board widget handle the event normally too
                        # This allows other board interactions to continue working
            elif (event.type() == QEvent.Type.MouseMove and self.isVisible()):
                # Handle mouse move for arrow preview
                if (isinstance(event, QMouseEvent) and 
                    self._current_tool == "arrow" and
                    self._annotation_start_square is not None):
                    # Get square from mouse position
                    square = self._board_widget._get_square_from_mouse_pos(event.pos())
                    if square is not None:
                        square_name = chess.square_name(square)
                        if square_name != self._annotation_preview_square:
                            self._annotation_preview_square = square_name
                            # Update board to show preview
                            if self._board_widget:
                                self._board_widget.set_arrow_preview(
                                    self._annotation_start_square,
                                    self._annotation_preview_square,
                                    [self._current_color.red(), self._current_color.green(), self._current_color.blue()],
                                    self._current_size
                                )
                                self._board_widget.update()  # Force redraw
                    else:
                        # Mouse outside board, clear preview
                        if self._annotation_preview_square is not None:
                            self._annotation_preview_square = None
                            if self._board_widget:
                                self._board_widget.set_arrow_preview(None, None, None, 1.0)
                                self._board_widget.update()
            elif (event.type() == QEvent.Type.MouseButtonRelease and self.isVisible()):
                if (isinstance(event, QMouseEvent) and 
                    event.button() == Qt.MouseButton.LeftButton and 
                    self._annotation_controller is not None and
                    self._current_tool == "arrow" and
                    self._annotation_start_square is not None):
                    # Get square from mouse position
                    square = self._board_widget._get_square_from_mouse_pos(event.pos())
                    if square is not None:
                        square_name = chess.square_name(square)
                        self._handle_annotation_release(square_name)
                    else:
                        self._annotation_start_square = None
        
        return super().eventFilter(obj, event)
    
    def showEvent(self, event) -> None:
        """Handle show event to check visibility when widget is shown."""
        super().showEvent(event)
        QTimer.singleShot(50, self._update_color_wrapping)
        QTimer.singleShot(50, self._update_toolbar_wrapping)
        QTimer.singleShot(50, self._update_toolbar_compact_mode)
    
    def _update_color_wrapping(self) -> None:
        """Update color button wrapping to second row based on available width."""
        if not hasattr(self, 'color_frame') or not hasattr(self, 'color_buttons'):
            return
        
        # Use the color_rows_container width instead of frame width for more accurate calculation
        container_width = self.color_rows_container.width()
        if container_width == 0:
            # Fallback to frame width if container width not available
            container_width = self.color_frame.width()
        if container_width == 0:
            return
        
        # Get actual button minimum size and spacing from config
        button_min_width = self.color_swatch_size
        spacing = self.color_row_spacing
        
        # Get margins from the color rows container
        margins = self.color_rows_layout.contentsMargins()
        horizontal_margins = margins.left() + margins.right()
        
        # Calculate available width (account for margins and buffer)
        available_width = container_width - horizontal_margins - self.color_buffer
        
        # Calculate how many buttons can fit in one row based on minimum width
        # Buttons can expand, so we check if we have enough space for minimum widths
        total_buttons = len(self.color_buttons)
        min_width_needed = (button_min_width * total_buttons) + (spacing * (total_buttons - 1))
        
        # If we can fit all buttons at minimum width, use single row
        # Otherwise, split between two rows
        use_two_rows = available_width < min_width_needed
        
        if use_two_rows:
            # Calculate how many buttons fit in first row based on minimum width
            # Try to fit as many as possible
            buttons_per_row = 0
            width_used = 0
            for i in range(total_buttons):
                button_width = button_min_width if i == 0 else (button_min_width + spacing)
                if width_used + button_width <= available_width:
                    buttons_per_row += 1
                    width_used += button_width
                else:
                    break
            
            # Ensure at least one button per row
            if buttons_per_row == 0:
                buttons_per_row = 1
            if buttons_per_row >= total_buttons:
                buttons_per_row = total_buttons - 1
        else:
            buttons_per_row = total_buttons
        
        if use_two_rows:
            # Split buttons: put as many as possible in first row, rest in second row
            buttons_row1 = buttons_per_row
            buttons_row2 = total_buttons - buttons_row1
            # Ensure at least one button per row
            if buttons_row1 == 0:
                buttons_row1 = 1
                buttons_row2 = total_buttons - 1
            if buttons_row2 == 0:
                buttons_row1 = total_buttons
                buttons_row2 = 0
        else:
            buttons_row1 = total_buttons
            buttons_row2 = 0
        
        # Remove all buttons from layouts
        for btn in self.color_buttons:
            self.color_row1_layout.removeWidget(btn)
            self.color_row2_layout.removeWidget(btn)
        
        # Add buttons to appropriate rows (they will expand evenly to fill space)
        for i, btn in enumerate(self.color_buttons):
            if i < buttons_row1:
                self.color_row1_layout.addWidget(btn)
            else:
                self.color_row2_layout.addWidget(btn)
        
        # Show/hide row 2 based on whether it has buttons
        should_show_row2 = buttons_row2 > 0
        is_row2_visible = self.color_row2_widget.isVisible()
        
        if should_show_row2 != is_row2_visible:
            self.color_row2_widget.setVisible(should_show_row2)
    
    def _on_color_selected(self, index: int, color: QColor) -> None:
        """Handle color selection from preset palette.
        
        Args:
            index: Index of the selected color in preset_colors.
            color: The selected color (ignored, we use preset_colors[index] instead).
        """
        # Always use the current color from preset_colors to handle reloaded colors
        if index < len(self.preset_colors):
            self._current_color = self.preset_colors[index]
        else:
            self._current_color = color  # Fallback to passed color if index is invalid
        self._update_color_selection(index)
    
    def _update_color_selection(self, selected_index: int) -> None:
        """Update the visual selection of color buttons.
        
        Args:
            selected_index: Index of the currently selected color.
        """
        for i, btn in enumerate(self.color_buttons):
            color = self.preset_colors[i]
            is_selected = (i == selected_index)
            self._set_button_color(btn, color, is_selected)
    
    def _get_current_color_index(self) -> int:
        """Get the index of the currently selected color.
        
        Returns:
            Index of current color in preset_colors, or 0 if not found.
        """
        for i, color in enumerate(self.preset_colors):
            if color == self._current_color:
                return i
        return 0
    
    def reload_colors(self) -> None:
        """Reload colors from user settings and update UI and existing annotations."""
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        settings = settings_service.get_settings()
        annotations_prefs = settings.get('annotations', {})
        
        # Get config defaults
        annotations_config = self.config.get('ui', {}).get('panels', {}).get('detail', {}).get('annotations', {})
        default_preset_colors = annotations_config.get('preset_colors', [[255, 100, 100], [100, 220, 100], [150, 200, 255], [255, 200, 100], [200, 100, 255], [100, 220, 255], [255, 150, 200], [150, 150, 255], [200, 200, 100], [240, 240, 240]])
        
        preset_colors_list = annotations_prefs.get('preset_colors', None)
        if preset_colors_list is None:
            preset_colors_list = default_preset_colors
        
        # Store current index before updating colors
        current_index = self._get_current_color_index()
        
        # Update preset colors
        self.preset_colors = [QColor(color[0], color[1], color[2]) for color in preset_colors_list]
        
        # Update current color to match the color at the current index
        if current_index < len(self.preset_colors):
            self._current_color = self.preset_colors[current_index]
        
        # Update color buttons
        for i, color_btn in enumerate(self.color_buttons):
            if i < len(self.preset_colors):
                self._set_button_color(color_btn, self.preset_colors[i], i == current_index)
        
        # Update existing annotations: update colors based on color_index
        if self._annotation_controller:
            annotation_model = self._annotation_controller.get_annotation_model()
            all_annotations = annotation_model.get_all_annotations()
            updated_plies = set()
            
            # Update annotations for all plies
            for ply_index, annotations in all_annotations.items():
                annotations_updated = False
                
                for annotation in annotations:
                    # Update color from palette using color_index
                    if annotation.color_index is not None and annotation.color_index < len(self.preset_colors):
                        new_color = self.preset_colors[annotation.color_index]
                        annotation.color = [new_color.red(), new_color.green(), new_color.blue()]
                        annotations_updated = True
                
                # Emit signal to update views for this ply if annotations were updated
                if annotations_updated:
                    updated_plies.add(ply_index)
                    annotation_model.annotations_changed.emit(ply_index)
    
    def _update_toolbar_wrapping(self) -> None:
        """Update tool button wrapping to multiple rows based on available width."""
        if not hasattr(self, 'toolbar_frame') or not hasattr(self, 'tool_buttons'):
            return
        
        frame_width = self.toolbar_frame.width()
        if frame_width == 0:
            return
        
        # Use the tool_buttons_container width for more accurate calculation
        container_width = self.tool_buttons_container.width()
        if container_width == 0:
            container_width = frame_width
        if container_width == 0:
            return
        
        # Get actual button minimum size and spacing from config
        button_min_width = self.tool_button_min_width
        spacing = self.toolbar_row_spacing
        
        # Get margins from the tool buttons container
        margins = self.tool_buttons_layout.contentsMargins()
        horizontal_margins = margins.left() + margins.right()
        
        # Calculate available width (account for margins and buffer from config)
        available_width = container_width - horizontal_margins - self.tool_buffer
        
        # Calculate how many buttons can fit in one row based on minimum width
        total_buttons = len(self.tool_buttons)
        min_width_needed = (button_min_width * total_buttons) + (spacing * (total_buttons - 1))
        
        # If we can fit all buttons at minimum width, use single row
        # Otherwise, calculate how many fit per row
        use_multiple_rows = available_width < min_width_needed
        
        if use_multiple_rows:
            # Calculate how many buttons fit per row (be very conservative)
            if available_width < button_min_width:
                buttons_per_row = 1
            else:
                # Calculate: (available_width + spacing) / (button_min_width + spacing)
                # Use floor division and be very conservative - reduce by 1 to be safe
                buttons_per_row = (available_width + spacing) // (button_min_width + spacing)
                buttons_per_row = max(1, min(buttons_per_row, total_buttons))
                
                # Be extra conservative: reduce by 1 to ensure no overlap
                if buttons_per_row > 1:
                    buttons_per_row -= 1
                
                # Verify the calculation: ensure buttons actually fit with extra margin
                # Add verification buffer from config
                required_width = buttons_per_row * button_min_width + (buttons_per_row - 1) * spacing + self.tool_verification_buffer
                if required_width > available_width and buttons_per_row > 1:
                    buttons_per_row -= 1  # Reduce by one if it doesn't fit
                
                # Double-check: if still doesn't fit, reduce again
                required_width = buttons_per_row * button_min_width + (buttons_per_row - 1) * spacing + self.tool_verification_buffer
                if required_width > available_width and buttons_per_row > 1:
                    buttons_per_row -= 1
            
            # Distribute buttons across rows (up to 3 rows)
            # Try to distribute evenly, but prioritize first row
            buttons_row1 = min(buttons_per_row, total_buttons)
            remaining = total_buttons - buttons_row1
            
            if remaining > 0:
                buttons_row2 = min(buttons_per_row, remaining)
                buttons_row3 = remaining - buttons_row2 if remaining > buttons_row2 else 0
            else:
                buttons_row2 = 0
                buttons_row3 = 0
        else:
            # All buttons fit in one row
            buttons_row1 = total_buttons
            buttons_row2 = 0
            buttons_row3 = 0
        
        # Remove all items (buttons and stretches) from layouts
        while self.tool_row1_layout.count() > 0:
            item = self.tool_row1_layout.takeAt(0)
            if item.widget():
                self.tool_row1_layout.removeWidget(item.widget())
        while self.tool_row2_layout.count() > 0:
            item = self.tool_row2_layout.takeAt(0)
            if item.widget():
                self.tool_row2_layout.removeWidget(item.widget())
        while self.tool_row3_layout.count() > 0:
            item = self.tool_row3_layout.takeAt(0)
            if item.widget():
                self.tool_row3_layout.removeWidget(item.widget())
        
        # Add buttons to appropriate rows (they will expand to fill space)
        for i, btn in enumerate(self.tool_buttons):
            if i < buttons_row1:
                self.tool_row1_layout.addWidget(btn)
            elif i < buttons_row1 + buttons_row2:
                self.tool_row2_layout.addWidget(btn)
            else:
                self.tool_row3_layout.addWidget(btn)
        
        # Don't add stretches - let buttons expand to fill available space
        
        # Show/hide rows based on whether they have buttons
        self.tool_row2_widget.setVisible(buttons_row2 > 0)
        self.tool_row3_widget.setVisible(buttons_row3 > 0)
    
    def _update_toolbar_compact_mode(self) -> None:
        """Update toolbar to use compact mode when width is narrow."""
        if not hasattr(self, 'toolbar_frame'):
            return
        
        frame_width = self.toolbar_frame.width()
        if frame_width == 0:
            return
        
        # Use compact mode based on threshold from config
        use_compact = frame_width < self.compact_mode_threshold
        
        # Update button text (buttons will stretch automatically due to size policy)
        tool_buttons = [self.arrow_btn, self.square_btn, self.circle_btn, self.text_btn]
        
        # Use button identity instead of text/tooltip to avoid confusion
        if use_compact:
            # Compact mode: shorter text
            self.arrow_btn.setText("Arr")
            self.square_btn.setText("Sqr")
            self.circle_btn.setText("Cir")
            self.text_btn.setText("Txt")
        else:
            # Normal mode: full text
            self.arrow_btn.setText("Arrow")
            self.square_btn.setText("Square")
            self.circle_btn.setText("Circle")
            self.text_btn.setText("Text")
    
    def _animate_show_row(self, widget: QWidget, animation: QPropertyAnimation) -> None:
        """Animate showing a row widget."""
        widget.setVisible(True)
        natural_height = widget.sizeHint().height()
        if natural_height == 0:
            natural_height = 35
        
        animation.setStartValue(0)
        animation.setEndValue(natural_height)
        
        def on_finished():
            try:
                animation.finished.disconnect(on_finished)
            except TypeError:
                pass
            widget.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX
        
        animation.finished.connect(on_finished)
        animation.start()
    
    def _animate_hide_row(self, widget: QWidget, animation: QPropertyAnimation) -> None:
        """Animate hiding a row widget."""
        current_height = widget.height()
        if current_height > 0:
            animation.setStartValue(current_height)
        else:
            natural_height = widget.sizeHint().height()
            if natural_height == 0:
                natural_height = 35
            animation.setStartValue(natural_height)
        
        animation.setEndValue(0)
        
        def on_finished():
            try:
                animation.finished.disconnect(on_finished)
            except TypeError:
                pass
            widget.setVisible(False)
        
        animation.finished.connect(on_finished)
        animation.start()
    
    def _on_tool_changed(self, button: QToolButton) -> None:
        """Handle tool selection change."""
        tool_map = {
            0: "arrow",
            1: "square",
            2: "circle",
            3: "text"
        }
        self._current_tool = tool_map.get(self.tool_group.id(button), "arrow")
        # Reset annotation start square and preview when tool changes
        self._annotation_start_square = None
        self._annotation_preview_square = None
        if self._board_widget:
            self._board_widget.set_arrow_preview(None, None, None, 1.0)
            self._board_widget.update()
    
    def _on_save_clicked(self) -> None:
        """Handle save annotations button click."""
        if self._annotation_controller:
            success = self._annotation_controller.save_annotations()
            if success:
                # Could show a status message here
                pass
    
    def _on_clear_all_clicked(self) -> None:
        """Handle clear all annotations button click."""
        if self._annotation_controller:
            self._annotation_controller.clear_current_annotations()
    
    def _on_annotations_changed(self, ply_index: int) -> None:
        """Handle annotations changed signal.
        
        Args:
            ply_index: Ply index that changed.
        """
        self._update_annotation_count_display()
        # Update list if this is the current ply
        if self._game_model and ply_index == self._game_model.get_active_move_ply():
            self._populate_annotation_list()
    
    def _on_annotation_added(self, ply_index: int, annotation_id: str) -> None:
        """Handle annotation added signal.
        
        Args:
            ply_index: Ply index.
            annotation_id: ID of added annotation.
        """
        self._update_annotation_count_display()
        # Update list if this is the current ply
        if self._game_model and ply_index == self._game_model.get_active_move_ply():
            self._populate_annotation_list()
    
    def _on_annotation_removed(self, ply_index: int, annotation_id: str) -> None:
        """Handle annotation removed signal.
        
        Args:
            ply_index: Ply index.
            annotation_id: ID of removed annotation.
        """
        self._update_annotation_count_display()
        # Update list if this is the current ply
        if self._game_model and ply_index == self._game_model.get_active_move_ply():
            self._populate_annotation_list()
    
    def _on_annotations_cleared(self, ply_index: int) -> None:
        """Handle annotations cleared signal.
        
        Args:
            ply_index: Ply index.
        """
        self._update_annotation_count_display()
        # Update list if this is the current ply
        if self._game_model and ply_index == self._game_model.get_active_move_ply():
            self._populate_annotation_list()
    
    def _update_annotation_count_display(self) -> None:
        """Update the annotation count display."""
        if not self._annotation_controller or not self._game_model:
            self.annotation_count_value.setText("0")
            return
        
        ply_index = self._game_model.get_active_move_ply()
        annotation_model = self._annotation_controller.get_annotation_model()
        annotations = annotation_model.get_annotations(ply_index)
        count = len(annotations)
        self.annotation_count_value.setText(str(count))
    
    def _populate_annotation_list(self) -> None:
        """Populate the annotation list with current annotations."""
        # Clear existing items
        while self.annotation_list_layout.count():
            item = self.annotation_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not self._annotation_controller or not self._game_model:
            return
        
        ply_index = self._game_model.get_active_move_ply()
        annotation_model = self._annotation_controller.get_annotation_model()
        annotations = annotation_model.get_annotations(ply_index)
        
        if not annotations:
            # Show empty state message
            empty_label = QLabel("No annotations for this move")
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_label.setStyleSheet("color: rgb(150, 150, 150); padding: 10px;")
            self.annotation_list_layout.addWidget(empty_label)
            self.annotation_list_layout.addStretch()
            return
        
        # Create list items for each annotation
        for annotation in annotations:
            item_widget = self._create_annotation_list_item(annotation, ply_index)
            self.annotation_list_layout.addWidget(item_widget)
        
        # Add stretch at the end
        self.annotation_list_layout.addStretch()
    
    def _create_annotation_list_item(self, annotation, ply_index: int) -> QWidget:
        """Create a list item widget for an annotation.
        
        Args:
            annotation: Annotation instance.
            ply_index: Current ply index.
            
        Returns:
            QWidget representing the annotation list item.
        """
        from app.models.annotation_model import AnnotationType
        
        item_frame = QFrame()
        item_layout = QHBoxLayout(item_frame)
        item_layout.setContentsMargins(5, 5, 5, 5)
        item_layout.setSpacing(8)
        
        # Color indicator
        color_indicator = QLabel()
        color_indicator.setFixedSize(16, 16)
        color = QColor(annotation.color[0], annotation.color[1], annotation.color[2])
        pixmap = QPixmap(16, 16)
        pixmap.fill(color)
        color_indicator.setPixmap(pixmap)
        item_layout.addWidget(color_indicator)
        
        # Annotation description
        desc_text = self._format_annotation_description(annotation)
        desc_label = QLabel(desc_text)
        desc_label.setWordWrap(True)
        desc_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        item_layout.addWidget(desc_label)
        
        # Delete button
        delete_btn = QPushButton("×")
        delete_btn.setFixedSize(24, 24)
        delete_btn.setToolTip("Delete annotation")
        delete_btn.clicked.connect(lambda checked, ann_id=annotation.annotation_id: 
                                   self._on_delete_annotation(ann_id, ply_index))
        item_layout.addWidget(delete_btn)
        
        return item_frame
    
    def _format_annotation_description(self, annotation) -> str:
        """Format annotation description for list display.
        
        Args:
            annotation: Annotation instance.
            
        Returns:
            Formatted description string.
        """
        from app.models.annotation_model import AnnotationType
        
        type_name = annotation.annotation_type.value.capitalize()
        
        if annotation.annotation_type == AnnotationType.ARROW:
            if annotation.from_square and annotation.to_square:
                return f"{type_name}: {annotation.from_square} → {annotation.to_square}"
            return f"{type_name}"
        elif annotation.annotation_type == AnnotationType.SQUARE:
            if annotation.square:
                return f"{type_name}: {annotation.square}"
            return f"{type_name}"
        elif annotation.annotation_type == AnnotationType.CIRCLE:
            if annotation.square:
                return f"{type_name}: {annotation.square}"
            return f"{type_name}"
        elif annotation.annotation_type == AnnotationType.TEXT:
            text_preview = annotation.text[:20] + "..." if annotation.text and len(annotation.text) > 20 else (annotation.text or "")
            square_info = f" on {annotation.square}" if annotation.square else ""
            return f"{type_name}: \"{text_preview}\"{square_info}"
        
        return type_name
    
    def _on_delete_annotation(self, annotation_id: str, ply_index: int) -> None:
        """Handle delete annotation button click.
        
        Args:
            annotation_id: ID of annotation to delete.
            ply_index: Ply index of the annotation.
        """
        if not self._annotation_controller:
            return
        
        annotation_model = self._annotation_controller.get_annotation_model()
        annotation_model.remove_annotation(ply_index, annotation_id)
    
    def set_game_model(self, game_model: GameModel) -> None:
        """Set the game model to observe.
        
        Args:
            game_model: GameModel instance to observe.
        """
        if self._game_model:
            # Disconnect from old model
            self._game_model.active_move_changed.disconnect(self._on_active_move_changed)
            self._game_model.active_game_changed.disconnect(self._on_active_game_changed)
        
        self._game_model = game_model
        
        if game_model:
            # Connect to active move changes to update annotation count
            game_model.active_move_changed.connect(self._on_active_move_changed)
            # Connect to active game changes to update disabled state
            game_model.active_game_changed.connect(self._on_active_game_changed)
            self._update_annotation_count_display()
            
            # If board widget is already set, update it with the game model
            if self._board_widget:
                self._board_widget.set_game_model(game_model)
            
            # Update disabled state based on current active game
            self._update_disabled_state(game_model.active_game is not None)
        else:
            # No game model - disable view
            self._update_disabled_state(False)
    
    def _on_active_move_changed(self, ply_index: int) -> None:
        """Handle active move change.
        
        Args:
            ply_index: New active ply index.
        """
        # Reset annotation start square when move changes
        self._annotation_start_square = None
        self._annotation_preview_square = None
        # Clear arrow preview
        if self._board_widget:
            self._board_widget.set_arrow_preview(None, None, None, 1.0)
            self._board_widget.update()
        # Update annotation count for new move
        self._update_annotation_count_display()
        # Update annotation list for new move
        self._populate_annotation_list()
    
    def _on_active_game_changed(self, game) -> None:
        """Handle active game change.
        
        Args:
            game: New active game (GameData or None).
        """
        # Update disabled state based on whether there's an active game
        self._update_disabled_state(game is not None)
    
    def _update_disabled_state(self, enabled: bool) -> None:
        """Update the disabled state of the annotation view.
        
        Args:
            enabled: True to enable the view, False to disable it.
        """
        # Enable/disable all interactive elements
        self.save_btn.setEnabled(enabled)
        self.clear_all_btn.setEnabled(enabled)
        
        # Enable/disable tool buttons
        for btn in self.tool_buttons:
            btn.setEnabled(enabled)
        
        # Enable/disable color buttons
        for btn in self.color_buttons:
            btn.setEnabled(enabled)
        
        # Enable/disable size slider
        if hasattr(self, 'size_slider'):
            self.size_slider.setEnabled(enabled)
        
        # Enable/disable shadow button
        if hasattr(self, 'shadow_button'):
            self.shadow_button.setEnabled(enabled)
        
        # Show/hide splitter and disabled placeholder
        if enabled:
            self.disabled_placeholder.hide()
            self.splitter.show()
        else:
            self.splitter.hide()
            self.disabled_placeholder.show()
            # Clear annotation list when disabled
            self._populate_annotation_list()
            self._update_annotation_count_display()
    
    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """Handle splitter movement - restore configured sizes to prevent resizing.
        
        Args:
            pos: New position of the splitter handle.
            index: Index of the splitter handle that moved.
        """
        # Immediately restore the configured sizes to prevent any resizing
        self.splitter.setSizes([self.splitter_controls_height, self.splitter_annotations_height])
    
    def _on_size_slider_released(self) -> None:
        """Handle size slider released - snap to nearest tick interval."""
        current_value = self.size_slider.value()
        # Snap to nearest tick interval
        snapped_value = round(current_value / self.size_slider_tick_interval) * self.size_slider_tick_interval
        # Clamp to min/max
        snapped_value = max(self.size_slider_min, min(self.size_slider_max, snapped_value))
        
        # If value changed, update slider (this will trigger valueChanged)
        if snapped_value != current_value:
            self.size_slider.setValue(snapped_value)
    
    def _on_size_changed(self, value: int) -> None:
        """Handle size slider value change.
        
        Args:
            value: Slider value (percentage, e.g., 100 = 100%).
        """
        self._current_size = value / 100.0  # Convert to multiplier (1.0 = 100%)
        self.size_value_label.setText(f"{value}%")
    
    def _on_shadow_toggled(self, checked: bool) -> None:
        """Handle shadow toggle button state change.
        
        Args:
            checked: True if button is checked (shadow enabled), False otherwise.
        """
        self._current_shadow = checked
        # Update button text to reflect state
        self.shadow_button.setText("Shadow: ON" if checked else "Shadow: OFF")
    
    def set_board_widget(self, board_widget: ChessBoardWidget) -> None:
        """Set the chessboard widget to add annotation layer to.
        
        Args:
            board_widget: ChessBoardWidget instance.
        """
        self._board_widget = board_widget
        
        if board_widget and self._annotation_controller:
            # Notify controller about board widget
            self._annotation_controller.set_board_widget(board_widget)
            
            # Connect annotation model to board widget
            annotation_model = self._annotation_controller.get_annotation_model()
            board_widget.set_annotation_model(annotation_model)
            board_widget.set_annotation_controller(self._annotation_controller)
            
            # Set game model on board widget for getting current ply
            if self._game_model:
                board_widget.set_game_model(self._game_model)
            
            # Install event filter to handle mouse events for annotation drawing
            board_widget.installEventFilter(self)
    
    
    def _handle_annotation_click(self, square_name: str) -> None:
        """Handle annotation drawing click on chessboard.
        
        Args:
            square_name: Square name (e.g., "e4").
        """
        if not self._annotation_controller:
            return
        
        # Automatically enable annotation layer if it's currently off
        annotation_model = self._annotation_controller.get_annotation_model()
        if annotation_model and not annotation_model.show_annotations:
            annotation_model.set_show_annotations(True)
        
        # Get current color and color_index
        color = [self._current_color.red(), self._current_color.green(), self._current_color.blue()]
        color_index = self._get_current_color_index()
        
        if self._current_tool == "arrow":
            # For arrows, we start on press and complete on release
            if self._annotation_start_square is None:
                # First click - store starting square
                self._annotation_start_square = square_name
        elif self._current_tool == "square":
            self._annotation_controller.add_square(square_name, color, color_index, self._current_size, self._current_shadow)
        elif self._current_tool == "circle":
            self._annotation_controller.add_circle(square_name, color, color_index, self._current_size, self._current_shadow)
        elif self._current_tool == "text":
            # Check if there's already text at this square
            # If there is, don't open dialog (let board widget handle editing via double-click)
            # If there isn't, open dialog to add new text
            if self._game_model and self._annotation_controller:
                ply_index = self._game_model.get_active_move_ply()
                annotation_model = self._annotation_controller.get_annotation_model()
                annotations = annotation_model.get_annotations(ply_index)
                
                # Check if there's any text annotation on this square
                has_text = False
                for annotation in annotations:
                    if (annotation.annotation_type == AnnotationType.TEXT and 
                        annotation.square == square_name):
                        has_text = True
                        break
                
                # Only open dialog if there's no existing text at this square
                if not has_text:
                    self._open_text_dialog(square_name, color, color_index)
    
    def _handle_annotation_release(self, square_name: str) -> None:
        """Handle annotation drawing mouse release on chessboard (for arrows).
        
        Args:
            square_name: Square name (e.g., "e4").
        """
        if not self._annotation_controller:
            self._annotation_start_square = None
            return
        
        if self._current_tool == "arrow" and self._annotation_start_square is not None:
            # Complete the arrow
            if self._annotation_start_square != square_name:
                # Get current color and color_index
                color = [self._current_color.red(), self._current_color.green(), self._current_color.blue()]
                color_index = self._get_current_color_index()
                self._annotation_controller.add_arrow(self._annotation_start_square, square_name, color, color_index, self._current_size, self._current_shadow)
            # Clear preview
            self._annotation_start_square = None
            self._annotation_preview_square = None
            if self._board_widget:
                self._board_widget.set_arrow_preview(None, None, None, 1.0)
                self._board_widget.update()
        else:
            self._annotation_start_square = None
            self._annotation_preview_square = None
    
    def _open_text_dialog(self, square_name: str, color: list[int], color_index: int) -> None:
        """Open dialog for text annotation input.
        
        Args:
            square_name: Square name where text will be placed.
            color: RGB color [r, g, b].
            color_index: Index into color palette.
        """
        from app.views.input_dialog import InputDialog
        
        text, ok = InputDialog.get_text(
            self.config,
            "Add Text Annotation",
            "Enter text:",
            "",
            self
        )
        
        if ok and text:
            # Add text with default position and size - user can adjust interactively on board
            # text_size is stored as ratio of square_size (e.g., 0.15 = 15% of square_size)
            # Default to 0.15 (15% of square_size) for reasonable text size
            # Size multiplier is stored separately and applied during drawing
            default_text_size_ratio = 0.15
            self._annotation_controller.add_text(
                square_name, text, color, color_index,
                0.5, 0.5,  # Center of square
                default_text_size_ratio, 0.0,  # Default size ratio and rotation
                self._current_size,  # Size multiplier
                self._current_shadow  # Shadow
            )

