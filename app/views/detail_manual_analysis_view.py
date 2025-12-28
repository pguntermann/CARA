"""Manual Analysis view for detail panel."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QEvent, QPropertyAnimation, QEasingCurve, QTimer
from PyQt6.QtGui import QPalette, QColor, QFont, QFontMetrics
from typing import Dict, Any, Optional

from app.models.game_model import GameModel
from app.models.engine_model import EngineModel
from app.models.manual_analysis_model import ManualAnalysisModel
from app.controllers.manual_analysis_controller import ManualAnalysisController


class DetailManualAnalysisView(QWidget):
    """Manual Analysis view displaying engine analysis for current position."""
    
    def __init__(self, config: Dict[str, Any], 
                 game_model: Optional[GameModel] = None,
                 engine_model: Optional[EngineModel] = None) -> None:
        """Initialize the manual analysis view.
        
        Args:
            config: Configuration dictionary.
            game_model: Optional GameModel to observe for position changes.
            engine_model: Optional EngineModel to observe for engine assignment changes.
        """
        super().__init__()
        self.config = config
        self._game_model: Optional[GameModel] = None
        self._engine_model: Optional[EngineModel] = None
        self._analysis_model: Optional[ManualAnalysisModel] = None
        self._analysis_controller: Optional[ManualAnalysisController] = None
        self._board_model = None
        self._is_analyzing = False
        self._multipv_count = 2
        
        # Track which line is being hovered (multipv -> HoverablePvLabel)
        self._hovered_labels: Dict[int, 'HoverablePvLabel'] = {}
        
        # Debounce timer for analysis updates (to improve performance during rapid navigation)
        self._analysis_update_timer = QTimer()
        self._analysis_update_timer.setSingleShot(True)
        self._analysis_update_timer.timeout.connect(self._on_analysis_changed_debounced)
        self._pending_analysis_update = False
        
        self._load_config()
        self._setup_ui()
        
        # Connect button signals
        self.start_stop_button.toggled.connect(self._on_start_stop_toggled)
        self.add_line_button.clicked.connect(self._on_add_line_clicked)
        self.remove_line_button.clicked.connect(self._on_remove_line_clicked)
        
        # Connect to models if provided
        if game_model:
            self.set_game_model(game_model)
        
        if engine_model:
            self.set_engine_model(engine_model)
    
    def eventFilter(self, obj, event) -> bool:
        """Event filter to detect resize events on control bar frame."""
        if hasattr(self, 'control_bar_frame') and obj == self.control_bar_frame:
            if event.type() == QEvent.Type.Resize:
                # Update exploration row visibility when control bar is resized
                self._update_exploration_row_visibility()
            elif event.type() == QEvent.Type.Show:
                # Also check when frame is shown (for initial visibility)
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(50, self._update_exploration_row_visibility)
        return super().eventFilter(obj, event)
    
    def showEvent(self, event) -> None:
        """Handle show event to check visibility when widget is shown."""
        super().showEvent(event)
        # Check visibility after widget is shown
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(50, self._update_exploration_row_visibility)
    
    def _load_config(self) -> None:
        """Load configuration values from config dictionary."""
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        manual_analysis_config = panel_config.get('manual_analysis', {})
        
        # Load multipv1 indicator config
        multipv1_indicator_config = manual_analysis_config.get('multipv1_indicator', {})
        self.multipv1_indicator_width = multipv1_indicator_config.get('width', 4)
        self.multipv1_indicator_enabled = multipv1_indicator_config.get('enabled', True)
        
        # Load multipv2 indicator config
        multipv2_indicator_config = manual_analysis_config.get('multipv2_indicator', {})
        self.multipv2_indicator_width = multipv2_indicator_config.get('width', 4)
        self.multipv2_indicator_enabled = multipv2_indicator_config.get('enabled', True)
        
        # Load multipv3 indicator config
        multipv3_indicator_config = manual_analysis_config.get('multipv3_indicator', {})
        self.multipv3_indicator_width = multipv3_indicator_config.get('width', 4)
        self.multipv3_indicator_enabled = multipv3_indicator_config.get('enabled', True)
        
        # Load arrow colors from board config (to match arrow colors)
        main_panel_config = ui_config.get('panels', {}).get('main', {})
        board_config = main_panel_config.get('board', {})
        bestnextmove_arrow_config = board_config.get('bestnextmove_arrow', {})
        self.bestnextmove_arrow_color = bestnextmove_arrow_config.get('color', [0, 0, 255])
        pv2_arrow_config = board_config.get('pv2_arrow', {})
        self.pv2_arrow_color = pv2_arrow_config.get('color', [100, 150, 255])
        pv3_arrow_config = board_config.get('pv3_arrow', {})
        self.pv3_arrow_color = pv3_arrow_config.get('color', [150, 150, 150])
        
        # Load statistics config
        statistics_config = manual_analysis_config.get('statistics', {})
        self.statistics_enabled = statistics_config.get('enabled', True)
        self.statistics_position = statistics_config.get('position', 'top')
        self.statistics_show_nps = statistics_config.get('show_nps', True)
        self.statistics_show_hash = statistics_config.get('show_hash', True)
        self.statistics_show_time = statistics_config.get('show_time', True)
        self.statistics_show_nodes = statistics_config.get('show_nodes', False)
        from app.utils.font_utils import scale_font_size
        self.statistics_font_size = scale_font_size(statistics_config.get('font_size', 9))
        self.statistics_color = statistics_config.get('color', [180, 180, 180])
        self.statistics_format = statistics_config.get('format', 'compact')
        self.statistics_separator = statistics_config.get('separator', ' | ')
        self.statistics_background_color = statistics_config.get('background_color', [45, 45, 50])
        self.statistics_padding = statistics_config.get('padding', [8, 4, 8, 4])
        
        # Load evaluation difference config
        evaluation_difference_config = manual_analysis_config.get('evaluation_difference', {})
        self.evaluation_difference_enabled = evaluation_difference_config.get('enabled', True)
        self.evaluation_difference_show_delta = evaluation_difference_config.get('show_delta', True)
        self.evaluation_difference_delta_format = evaluation_difference_config.get('delta_format', '({delta:+.2f})')
        self.evaluation_difference_positive_color = evaluation_difference_config.get('positive_color', [100, 255, 100])
        self.evaluation_difference_negative_color = evaluation_difference_config.get('negative_color', [255, 100, 100])
        
        # Load trajectory highlight config
        trajectory_highlight_config = manual_analysis_config.get('trajectory_highlight', {})
        self.trajectory_highlight_enabled = trajectory_highlight_config.get('enabled', True)
        self.trajectory_highlight_font_weight = trajectory_highlight_config.get('font_weight', 'bold')
        self.trajectory_highlight_bg_alpha = trajectory_highlight_config.get('background_alpha', 0.3)
        
        # Load trajectory colors from board config (to match trajectory line colors)
        main_panel_config = ui_config.get('panels', {}).get('main', {})
        board_config = main_panel_config.get('board', {})
        positional_plans_config = board_config.get('positional_plans', {})
        
        # Trajectory 1 colors (most moved piece)
        trajectory_1_config = positional_plans_config.get('trajectory', {})
        self.trajectory_1_color = trajectory_1_config.get('color_end', [0, 100, 255])  # Use darker end color for highlighting
        
        # Trajectory 2 colors (second most moved piece)
        trajectory_2_config = positional_plans_config.get('trajectory_2', {})
        self.trajectory_2_color = trajectory_2_config.get('color_end', [0, 200, 100])
        
        # Trajectory 3 colors (third most moved piece)
        trajectory_3_config = positional_plans_config.get('trajectory_3', {})
        self.trajectory_3_color = trajectory_3_config.get('color_end', [255, 150, 0])
    
    def _setup_ui(self) -> None:
        """Setup the manual analysis UI."""
        layout = QVBoxLayout(self)
        ui_config = self.config.get('ui', {})
        margins = ui_config.get('margins', {}).get('detail_panel', [0, 0, 0, 0])
        layout.setContentsMargins(margins[0], margins[1], margins[2], margins[3])
        
        # Get layout spacing from config
        panel_config = ui_config.get('panels', {}).get('detail', {})
        manual_analysis_config = panel_config.get('manual_analysis', {})
        layout_config = manual_analysis_config.get('layout', {})
        layout_spacing = layout_config.get('spacing', 0)
        layout.setSpacing(layout_spacing)
        
        # Control bar (top)
        self.control_bar = self._create_control_bar()
        layout.addWidget(self.control_bar)
        
        # Statistics bar (if enabled and position is top)
        self.statistics_bar = None
        if self.statistics_enabled and self.statistics_position == 'top':
            self.statistics_bar = self._create_statistics_bar()
            layout.addWidget(self.statistics_bar)
        
        # Analysis lines display area (scrollable) - directly under control bar
        self.analysis_area = self._create_analysis_area()
        layout.addWidget(self.analysis_area, 1)  # Takes remaining space
        
        # Statistics bar (if enabled and position is bottom)
        if self.statistics_enabled and self.statistics_position == 'bottom':
            if self.statistics_bar is None:
                self.statistics_bar = self._create_statistics_bar()
            layout.addWidget(self.statistics_bar)
        
        # Info bar (showing position and engine info) - at the bottom
        self.info_bar = self._create_info_bar()
        layout.addWidget(self.info_bar)
        
        # Apply styling
        self._apply_styling()
    
    def _create_control_bar(self) -> QFrame:
        """Create the control bar with buttons.
        
        Returns:
            QFrame containing control buttons in a two-row layout.
        """
        frame = QFrame()
        # Main layout is vertical (two rows)
        main_layout = QVBoxLayout(frame)
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        manual_analysis_config = panel_config.get('manual_analysis', {})
        control_config = manual_analysis_config.get('control_bar', {})
        
        margins = control_config.get('margins', [8, 8, 8, 8])
        spacing = control_config.get('spacing', 8)
        main_layout.setContentsMargins(margins[0], margins[1], margins[2], margins[3])
        main_layout.setSpacing(spacing)
        
        # Row 1: Start Analysis and Lines controls
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(spacing)
        
        # Start/Stop Analysis button
        self.start_stop_button = QPushButton("Start Analysis")
        self.start_stop_button.setCheckable(True)
        self.start_stop_button.setChecked(False)
        self.start_stop_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        # Button styling will be applied in _apply_styling()
        row1_layout.addWidget(self.start_stop_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        # Get button group spacing from config
        button_group_spacing = control_config.get('button_group_spacing', 16)
        row1_layout.addSpacing(button_group_spacing)
        
        # Multipv controls
        self.lines_label = QLabel("Lines:")
        row1_layout.addWidget(self.lines_label)
        
        # Get multipv button width from config (will be set after config is loaded)
        # We'll set it in _apply_styling() after config is available
        self.remove_line_button = QPushButton("-")
        self.remove_line_button.setEnabled(False)  # Disabled when only 1 line
        self.remove_line_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row1_layout.addWidget(self.remove_line_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        self.multipv_label = QLabel("2")
        # Width will be set from config in _apply_styling()
        self.multipv_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row1_layout.addWidget(self.multipv_label)
        
        self.add_line_button = QPushButton("+")
        self.add_line_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row1_layout.addWidget(self.add_line_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        row1_layout.addStretch()  # Push buttons to the left
        
        main_layout.addLayout(row1_layout)
        
        # Row 2: Exploration controls (in a widget so we can hide/show it)
        self.exploration_row_widget = QWidget()
        row2_layout = QHBoxLayout(self.exploration_row_widget)
        row2_layout.setSpacing(spacing)
        row2_layout.setContentsMargins(0, 0, 0, 0)  # No margins, parent frame handles them
        
        # Load initial state from user settings
        from app.services.user_settings_service import UserSettingsService
        settings_service = UserSettingsService.get_instance()
        user_settings = settings_service.get_settings()
        manual_analysis_settings = user_settings.get('manual_analysis', {})
        board_visibility = user_settings.get('board_visibility', {})
        
        # Explore controls
        self.explore_label = QLabel("Explore:")
        row2_layout.addWidget(self.explore_label)
        
        # Explore PV1 button
        self.explore_pv1_button = QPushButton("PV1")
        self.explore_pv1_button.setCheckable(True)
        self.explore_pv1_button.setChecked(False)
        self.explore_pv1_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.explore_pv1_button.toggled.connect(lambda checked: self._on_explore_pv1_toggled(checked))
        row2_layout.addWidget(self.explore_pv1_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        # Explore PV2 button
        self.explore_pv2_button = QPushButton("PV2")
        self.explore_pv2_button.setCheckable(True)
        self.explore_pv2_button.setChecked(False)
        self.explore_pv2_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.explore_pv2_button.toggled.connect(lambda checked: self._on_explore_pv2_toggled(checked))
        row2_layout.addWidget(self.explore_pv2_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        # Explore PV3 button
        self.explore_pv3_button = QPushButton("PV3")
        self.explore_pv3_button.setCheckable(True)
        self.explore_pv3_button.setChecked(False)
        self.explore_pv3_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.explore_pv3_button.toggled.connect(lambda checked: self._on_explore_pv3_toggled(checked))
        row2_layout.addWidget(self.explore_pv3_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        # Explore Off button
        self.explore_off_button = QPushButton("Off")
        self.explore_off_button.setCheckable(True)
        self.explore_off_button.setChecked(True)  # Default to Off
        self.explore_off_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.explore_off_button.toggled.connect(lambda checked: self._on_explore_off_toggled(checked))
        row2_layout.addWidget(self.explore_off_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        row2_layout.addSpacing(button_group_spacing)
        
        # Pieces controls
        self.pieces_label = QLabel("Pieces:")
        row2_layout.addWidget(self.pieces_label)
        
        max_pieces = manual_analysis_settings.get('max_pieces_to_explore', 1)
        
        # Pieces 1 button
        self.pieces_1_button = QPushButton("1")
        self.pieces_1_button.setCheckable(True)
        self.pieces_1_button.setChecked(max_pieces == 1)
        self.pieces_1_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.pieces_1_button.toggled.connect(lambda checked: self._on_pieces_toggled(1, checked))
        row2_layout.addWidget(self.pieces_1_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        # Pieces 2 button
        self.pieces_2_button = QPushButton("2")
        self.pieces_2_button.setCheckable(True)
        self.pieces_2_button.setChecked(max_pieces == 2)
        self.pieces_2_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.pieces_2_button.toggled.connect(lambda checked: self._on_pieces_toggled(2, checked))
        row2_layout.addWidget(self.pieces_2_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        # Pieces 3 button
        self.pieces_3_button = QPushButton("3")
        self.pieces_3_button.setCheckable(True)
        self.pieces_3_button.setChecked(max_pieces == 3)
        self.pieces_3_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.pieces_3_button.toggled.connect(lambda checked: self._on_pieces_toggled(3, checked))
        row2_layout.addWidget(self.pieces_3_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        row2_layout.addSpacing(button_group_spacing)
        
        # Depth controls
        self.depth_label = QLabel("Depth:")
        row2_layout.addWidget(self.depth_label)
        
        max_depth = manual_analysis_settings.get('max_exploration_depth', 2)
        
        # Depth 2 button
        self.depth_2_button = QPushButton("2")
        self.depth_2_button.setCheckable(True)
        self.depth_2_button.setChecked(max_depth == 2)
        self.depth_2_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.depth_2_button.toggled.connect(lambda checked: self._on_depth_toggled(2, checked))
        row2_layout.addWidget(self.depth_2_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        # Depth 3 button
        self.depth_3_button = QPushButton("3")
        self.depth_3_button.setCheckable(True)
        self.depth_3_button.setChecked(max_depth == 3)
        self.depth_3_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.depth_3_button.toggled.connect(lambda checked: self._on_depth_toggled(3, checked))
        row2_layout.addWidget(self.depth_3_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        # Depth 4 button
        self.depth_4_button = QPushButton("4")
        self.depth_4_button.setCheckable(True)
        self.depth_4_button.setChecked(max_depth == 4)
        self.depth_4_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.depth_4_button.toggled.connect(lambda checked: self._on_depth_toggled(4, checked))
        row2_layout.addWidget(self.depth_4_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        
        row2_layout.addStretch()  # Push buttons to the left
        
        main_layout.addWidget(self.exploration_row_widget)
        
        # Store reference to frame for resize event handling
        self.control_bar_frame = frame
        
        # Install event filter to detect resize events
        frame.installEventFilter(self)
        
        # Initialize animation for fade effect
        # Use maximumHeight animation for smooth show/hide
        self._fade_animation = QPropertyAnimation(self.exploration_row_widget, b"maximumHeight")
        self._fade_animation.setDuration(200)  # 200ms animation
        self._fade_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # Set initial state - hidden by default until we check
        self.exploration_row_widget.setMaximumHeight(0)
        self.exploration_row_widget.setVisible(False)
        # Store if we're currently hiding (to prevent multiple connections)
        self._is_hiding = False
        
        # Initial visibility check (will be called after layout is complete)
        # Use multiple delays to ensure proper sizing
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._update_exploration_row_visibility)
        QTimer.singleShot(100, self._update_exploration_row_visibility)  # Also check after 100ms
        
        return frame
    
    def _update_exploration_row_visibility(self) -> None:
        """Update visibility of exploration row based on available width."""
        if not hasattr(self, 'exploration_row_widget') or not hasattr(self, 'control_bar_frame'):
            return
        
        # Get current width of control bar frame
        frame_width = self.control_bar_frame.width()
        
        # If frame hasn't been laid out yet (width is 0), skip check
        if frame_width == 0:
            return
        
        # Calculate minimum width needed for row 2
        # Get the size hint of the exploration row widget to determine minimum width needed
        # Add some buffer (20px) to account for margins and ensure buttons don't squeeze
        min_width_needed = self.exploration_row_widget.sizeHint().width() + 20
        
        # Alternative: Use a fixed minimum if size hint is not reliable yet
        # Estimate: "Explore:" (~60px) + 4 buttons (~120px) + "Pieces:" (~60px) + 3 buttons (~90px) + "Depth:" (~60px) + 3 buttons (~90px) + spacing (~50px)
        # Total: ~520px minimum, but add some buffer for margins and padding
        FALLBACK_MIN_WIDTH = 550
        
        # Use the larger of size hint or fallback, but ensure we have a reasonable minimum
        min_width = max(min_width_needed, FALLBACK_MIN_WIDTH) if min_width_needed > 0 else FALLBACK_MIN_WIDTH
        
        # Show row 2 only if we have enough width
        should_show = frame_width >= min_width
        
        # Get current state - check both visibility and if widget is actually shown
        # Also check if animation is running (if so, don't interrupt)
        from PyQt6.QtCore import QAbstractAnimation
        animation_running = self._fade_animation.state() == QAbstractAnimation.State.Running
        is_visible = self.exploration_row_widget.isVisible() and self.exploration_row_widget.height() > 0
        
        # Only update if state changed and animation is not running
        if should_show != is_visible and not animation_running:
            # Animate the transition
            if should_show:
                # Show: animate from 0 to natural height
                self.exploration_row_widget.setVisible(True)
                natural_height = self.exploration_row_widget.sizeHint().height()
                if natural_height == 0:
                    # If size hint not ready, use a reasonable default
                    natural_height = 40
                
                # Disconnect any hide finished handler
                try:
                    self._fade_animation.finished.disconnect(self._on_fade_hide_finished)
                except TypeError:
                    pass
                self._is_hiding = False
                
                self._fade_animation.setStartValue(0)
                self._fade_animation.setEndValue(natural_height)
                # After animation completes, reset maximumHeight to allow natural sizing
                def on_show_finished():
                    try:
                        self._fade_animation.finished.disconnect(on_show_finished)
                    except TypeError:
                        pass
                    # Reset to allow natural height
                    self.exploration_row_widget.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX equivalent
                
                self._fade_animation.finished.connect(on_show_finished)
                self._fade_animation.start()
            else:
                # Hide: animate from current height to 0
                current_actual_height = self.exploration_row_widget.height()
                if current_actual_height > 0:
                    self._fade_animation.setStartValue(current_actual_height)
                else:
                    natural_height = self.exploration_row_widget.sizeHint().height()
                    if natural_height == 0:
                        natural_height = 40
                    self._fade_animation.setStartValue(natural_height)
                
                self._fade_animation.setEndValue(0)
                
                # Disconnect previous connection if any, then connect
                try:
                    self._fade_animation.finished.disconnect(self._on_fade_hide_finished)
                except TypeError:
                    pass
                
                if not self._is_hiding:
                    self._fade_animation.finished.connect(self._on_fade_hide_finished)
                    self._is_hiding = True
                
                self._fade_animation.start()
    
    def _on_fade_hide_finished(self) -> None:
        """Handle fade animation finished when hiding."""
        # Disconnect the signal to avoid multiple connections
        try:
            self._fade_animation.finished.disconnect(self._on_fade_hide_finished)
        except TypeError:
            pass
        
        self._is_hiding = False
        
        # Hide widget after animation completes
        if hasattr(self, 'exploration_row_widget'):
            self.exploration_row_widget.setVisible(False)
    
    def _create_info_bar(self) -> QFrame:
        """Create the info bar showing position and engine information.
        
        Returns:
            QFrame containing info labels.
        """
        frame = QFrame()
        layout = QHBoxLayout(frame)
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        manual_analysis_config = panel_config.get('manual_analysis', {})
        info_config = manual_analysis_config.get('info_bar', {})
        
        margins = info_config.get('margins', [8, 4, 8, 4])
        spacing = info_config.get('spacing', 16)
        layout.setContentsMargins(margins[0], margins[1], margins[2], margins[3])
        layout.setSpacing(spacing)
        
        # Position info
        self.position_label = QLabel("Position: Starting Position (White to move)")
        layout.addWidget(self.position_label)
        
        layout.addStretch()
        
        # Engine info
        self.engine_label = QLabel("Engine: None")
        layout.addWidget(self.engine_label)
        
        return frame
    
    def _create_statistics_bar(self) -> QFrame:
        """Create the statistics bar showing global engine statistics.
        
        Returns:
            QFrame containing statistics labels.
        """
        frame = QFrame()
        layout = QHBoxLayout(frame)
        
        # Get padding from config
        padding = self.statistics_padding
        layout.setContentsMargins(padding[0], padding[1], padding[2], padding[3])
        layout.setSpacing(8)
        
        # Statistics label (will be updated when analysis changes)
        self.statistics_label = QLabel("")
        self.statistics_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        # Get styling from config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        tabs_config = panel_config.get('tabs', {})
        font_family = tabs_config.get('font_family', 'Helvetica Neue')
        
        # Apply styling
        bg_color = self.statistics_background_color
        text_color = self.statistics_color
        font_size = self.statistics_font_size
        
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});
                border: none;
            }}
        """)
        
        self.statistics_label.setStyleSheet(f"""
            QLabel {{
                color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});
                font-family: "{font_family}";
                font-size: {font_size}pt;
                border: none;
                background-color: transparent;
            }}
        """)
        # Set palette to prevent macOS override
        stats_palette = self.statistics_label.palette()
        stats_palette.setColor(self.statistics_label.foregroundRole(), QColor(text_color[0], text_color[1], text_color[2]))
        self.statistics_label.setPalette(stats_palette)
        self.statistics_label.update()
        
        layout.addWidget(self.statistics_label)
        layout.addStretch()
        
        # Initially hide the statistics bar (will be shown when analysis starts)
        frame.setVisible(False)
        
        return frame
    
    def _create_analysis_area(self) -> QScrollArea:
        """Create the scrollable analysis lines display area.
        
        Returns:
            QScrollArea containing analysis lines widget.
        """
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        
        # Container widget for analysis lines
        container = QWidget()
        container_layout = QVBoxLayout(container)
        
        # Get container margins and spacing from config
        # Note: We need to get config here since this is called before _apply_styling()
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        manual_analysis_config = panel_config.get('manual_analysis', {})
        analysis_area_config = manual_analysis_config.get('analysis_area', {})
        container_margins = analysis_area_config.get('container_margins', [0, 0, 0, 0])
        container_spacing = analysis_area_config.get('container_spacing', 0)
        line_spacing = analysis_area_config.get('line_spacing', 8)
        line_area_padding = analysis_area_config.get('line_area_padding', [8, 8, 8, 0])
        container_layout.setContentsMargins(line_area_padding[0], line_area_padding[1], line_area_padding[2], line_area_padding[3])
        container_layout.setSpacing(line_spacing)
        
        # Placeholder label (will be replaced with actual analysis lines later)
        self.empty_label = QLabel("Start analysis to see engine evaluations")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        container_layout.addWidget(self.empty_label)
        
        # Don't add stretch - we want lines at the top
        # container_layout.addStretch()
        
        scroll_area.setWidget(container)
        self.analysis_container = container
        self.analysis_container_layout = container_layout
        
        return scroll_area
    
    def _apply_styling(self) -> None:
        """Apply styling to UI elements based on configuration."""
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        manual_analysis_config = panel_config.get('manual_analysis', {})
        tabs_config = panel_config.get('tabs', {})
        
        # Get colors from config
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        colors_config = tabs_config.get('colors', {})
        normal = colors_config.get('normal', {})
        norm_text = normal.get('text', [200, 200, 200])
        norm_bg = normal.get('background', [45, 45, 50])
        norm_border = normal.get('border', [60, 60, 65])
        
        hover = colors_config.get('hover', {})
        hover_bg = hover.get('background', [55, 55, 60])
        hover_text = hover.get('text', [230, 230, 230])
        
        active = colors_config.get('active', {})
        active_bg = active.get('background', [70, 90, 130])
        active_text = active.get('text', [240, 240, 240])
        
        # Get font settings
        from app.utils.font_utils import resolve_font_family, scale_font_size
        font_family = resolve_font_family(tabs_config.get('font_family', 'Helvetica Neue'))
        font_size = scale_font_size(tabs_config.get('font_size', 10))
        
        # Label config (needed for disabled_color_multiplier in button stylesheet)
        label_config = manual_analysis_config.get('labels', {})
        label_font_size = scale_font_size(label_config.get('font_size', tabs_config.get('font_size', 10)))
        disabled_color_multiplier = label_config.get('disabled_color_multiplier', 0.5)
        empty_label_color_multiplier = label_config.get('empty_label_color_multiplier', 0.7)
        
        # Button styling
        button_config = manual_analysis_config.get('buttons', {})
        button_height = button_config.get('height', 28)
        button_padding = button_config.get('padding', [6, 4])
        button_border_radius = button_config.get('border_radius', 4)
        
        # Multipv button width
        multipv_config = manual_analysis_config.get('multipv_buttons', {})
        multipv_button_width = multipv_config.get('width', 30)
        
        # Set minimum width for multipv label
        self.multipv_label.setMinimumWidth(multipv_button_width)
        
        # Apply button styling using StyleManager
        from app.views.style import StyleManager
        
        # Get button config values for offsets
        buttons_config = ui_config.get('buttons', {})
        button_bg_offset = buttons_config.get('background_offset', 20)
        button_hover_offset = buttons_config.get('hover_background_offset', 30)
        button_pressed_offset = buttons_config.get('pressed_background_offset', 10)
        
        # Calculate offsets: use pane_bg as base to match StyleManager's offset model
        bg_offset = max(0, norm_bg[0] - pane_bg[0])
        hover_offset = max(0, hover_bg[0] - pane_bg[0])
        
        # Convert padding from [horizontal, vertical] to single value (use horizontal for consistency)
        button_padding_value = button_padding[0] if isinstance(button_padding, list) else button_padding
        
        # Apply base styling using StyleManager
        bg_color_list = [pane_bg[0], pane_bg[1], pane_bg[2]]
        border_color_list = [norm_border[0], norm_border[1], norm_border[2]]
        text_color_list = [norm_text[0], norm_text[1], norm_text[2]]
        
        # Collect all buttons
        all_buttons = [self.start_stop_button, self.add_line_button, self.remove_line_button]
        icon_buttons = [self.add_line_button, self.remove_line_button]  # Buttons with single character icons
        text_buttons = []  # Buttons with text labels
        
        # Add exploration buttons if they exist
        if hasattr(self, 'explore_pv1_button'):
            explore_buttons = [self.explore_pv1_button, self.explore_pv2_button, 
                               self.explore_pv3_button, self.explore_off_button]
            all_buttons.extend(explore_buttons)
            text_buttons.extend(explore_buttons)
        if hasattr(self, 'pieces_1_button'):
            pieces_buttons = [self.pieces_1_button, self.pieces_2_button, self.pieces_3_button]
            all_buttons.extend(pieces_buttons)
            text_buttons.extend(pieces_buttons)
        if hasattr(self, 'depth_2_button'):
            depth_buttons = [self.depth_2_button, self.depth_3_button, self.depth_4_button]
            all_buttons.extend(depth_buttons)
            text_buttons.extend(depth_buttons)
        
        # Apply base styling to all buttons
        StyleManager.style_buttons(
            all_buttons,
            self.config,
            bg_color_list,
            border_color_list,
            text_color=text_color_list,
            font_family=font_family,
            font_size=font_size,
            border_radius=button_border_radius,
            padding=button_padding_value,
            background_offset=bg_offset,
            hover_background_offset=hover_offset,
            pressed_background_offset=button_pressed_offset,
            min_height=button_height
        )
        
        # Set fixed heights for alignment
        for button in all_buttons:
            button.setFixedHeight(button_height)
        
        # Set fixed widths for icon buttons (+, -)
        for button in icon_buttons:
            button.setFixedWidth(multipv_button_width)
        
        # Calculate and set appropriate widths for text buttons based on their content
        button_font = QFont(font_family, int(font_size))
        font_metrics = QFontMetrics(button_font)
        
        # Calculate width needed for each text button and use the maximum
        max_text_width = 0
        for button in text_buttons:
            text = button.text()
            text_width = font_metrics.horizontalAdvance(text)
            # Add padding (horizontal padding * 2) + some extra for borders
            total_width = text_width + (button_padding_value * 2) + 10  # 10px for borders
            max_text_width = max(max_text_width, total_width)
        
        # Use the calculated width or multipv_button_width, whichever is larger
        text_button_width = max(max_text_width, multipv_button_width)
        
        # Set fixed widths for text buttons
        for button in text_buttons:
            button.setFixedWidth(int(text_button_width))
        
        # Add checked state styling for toggle buttons (StyleManager doesn't support checked state yet)
        # Also add disabled state styling
        checked_disabled_style = f"""
            QPushButton:checked {{
                background-color: rgb({active_bg[0]}, {active_bg[1]}, {active_bg[2]});
                color: rgb({active_text[0]}, {active_text[1]}, {active_text[2]});
            }}
            QPushButton:disabled {{
                background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
                color: rgb({int(norm_text[0] * disabled_color_multiplier)}, {int(norm_text[1] * disabled_color_multiplier)}, {int(norm_text[2] * disabled_color_multiplier)});
                border-color: rgb({int(norm_border[0] * disabled_color_multiplier)}, {int(norm_border[1] * disabled_color_multiplier)}, {int(norm_border[2] * disabled_color_multiplier)});
            }}
            QPushButton:hover {{
                color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
            }}
        """
        # Append checked/disabled state to existing stylesheet for all buttons
        for button in all_buttons:
            current_style = button.styleSheet()
            button.setStyleSheet(current_style + checked_disabled_style)
        
        # Label styling
        
        label_stylesheet = f"""
            QLabel {{
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                font-family: "{font_family}";
                font-size: {label_font_size}pt;
            }}
        """
        
        # Style all labels with palette to prevent macOS override
        labels_to_style = []
        if hasattr(self, 'position_label'):
            labels_to_style.append(self.position_label)
        if hasattr(self, 'engine_label'):
            labels_to_style.append(self.engine_label)
        if hasattr(self, 'multipv_label'):
            labels_to_style.append(self.multipv_label)
        if hasattr(self, 'lines_label'):
            labels_to_style.append(self.lines_label)
        if hasattr(self, 'explore_label'):
            labels_to_style.append(self.explore_label)
        if hasattr(self, 'pieces_label'):
            labels_to_style.append(self.pieces_label)
        if hasattr(self, 'depth_label'):
            labels_to_style.append(self.depth_label)
        
        for label in labels_to_style:
            label.setStyleSheet(label_stylesheet)
            label_palette = label.palette()
            label_palette.setColor(label.foregroundRole(), QColor(norm_text[0], norm_text[1], norm_text[2]))
            label.setPalette(label_palette)
            label.update()
        
        # Control bar and info bar styling
        # Use control_bar background_color if available, otherwise fall back to pane_bg
        control_bar_config = manual_analysis_config.get('control_bar', {})
        control_bar_bg = control_bar_config.get('background_color', pane_bg)
        control_bar_stylesheet = f"""
            QFrame {{
                background-color: rgb({control_bar_bg[0]}, {control_bar_bg[1]}, {control_bar_bg[2]});
                border-bottom: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
            }}
        """
        
        # Apply to control and info bars
        self.control_bar.setStyleSheet(control_bar_stylesheet)
        self.info_bar.setStyleSheet(control_bar_stylesheet)
        
        # Scroll area styling using StyleManager
        # Note: This view uses different colors (norm_bg, norm_border) and no border
        from app.views.style import StyleManager
        StyleManager.style_scroll_area(
            self.analysis_area,
            self.config,
            norm_bg,
            norm_border,
            0  # No border radius since border is none
        )
        
        # Empty label styling
        analysis_area_config = manual_analysis_config.get('analysis_area', {})
        empty_label_padding = analysis_area_config.get('empty_label_padding', 20)
        self.empty_label.setStyleSheet(f"""
            QLabel {{
                color: rgb({int(norm_text[0] * empty_label_color_multiplier)}, {int(norm_text[1] * empty_label_color_multiplier)}, {int(norm_text[2] * empty_label_color_multiplier)});
                font-family: "{font_family}";
                font-size: {label_font_size}pt;
                padding: {empty_label_padding}px;
            }}
        """)
    
    def set_game_model(self, model: GameModel) -> None:
        """Set the game model to observe for position changes.
        
        Args:
            model: The GameModel instance to observe.
        """
        if self._game_model:
            # Disconnect from old model
            self._game_model.active_move_changed.disconnect(self._on_active_move_changed)
            self._game_model.active_game_changed.disconnect(self._on_active_game_changed)
        
        self._game_model = model
        
        # Connect to model signals
        model.active_move_changed.connect(self._on_active_move_changed)
        model.active_game_changed.connect(self._on_active_game_changed)
        
        # Initialize with current state
        self._on_active_move_changed(model.get_active_move_ply())
    
    def _on_active_move_changed(self, ply_index: int) -> None:
        """Handle active move change from model.
        
        Args:
            ply_index: Ply index of the active move (0 = starting position).
        """
        if ply_index == 0:
            position_text = "Position: Starting Position (White to move)"
        else:
            # Calculate move number and side to move
            move_number = (ply_index // 2) + 1
            side_to_move = "White" if (ply_index % 2 == 0) else "Black"
            position_text = f"Position: Move {move_number} ({side_to_move} to move)"
        
        self.position_label.setText(position_text)
    
    def _on_active_game_changed(self, game) -> None:
        """Handle active game change from model.
        
        Args:
            game: GameData instance or None.
        """
        # Reset position display when game changes
        if game is None:
            self.position_label.setText("Position: No game loaded")
        else:
            # Update position based on current ply
            if self._game_model:
                self._on_active_move_changed(self._game_model.get_active_move_ply())
    
    def set_engine_model(self, model: EngineModel) -> None:
        """Set the engine model to observe for engine assignment changes.
        
        Args:
            model: The EngineModel instance to observe.
        """
        if self._engine_model:
            # Disconnect from old model
            try:
                self._engine_model.assignment_changed.disconnect(self._on_assignment_changed)
            except TypeError:
                # Signal was not connected, ignore
                pass
        
        self._engine_model = model
        
        # Connect to model signals
        if model:
            model.assignment_changed.connect(self._on_assignment_changed)
            
            # Initialize with current assignment
            self._on_assignment_changed()
    
    def _on_assignment_changed(self) -> None:
        """Handle engine assignment change from model."""
        if not self._engine_model:
            self.engine_label.setText("Engine: None")
            return
        
        # Get manual analysis engine assignment
        engine_id = self._engine_model.get_assignment(EngineModel.TASK_MANUAL_ANALYSIS)
        
        if engine_id is None:
            self.engine_label.setText("Engine: None")
        else:
            engine = self._engine_model.get_engine(engine_id)
            if engine:
                # Format: "Engine: Stockfish 15.1" or "Engine: Stockfish" if no version
                if engine.version:
                    engine_text = f"Engine: {engine.name} {engine.version}"
                else:
                    engine_text = f"Engine: {engine.name}"
                self.engine_label.setText(engine_text)
            else:
                self.engine_label.setText("Engine: None")
    
    def set_analysis_controller(self, controller: ManualAnalysisController) -> None:
        """Set the manual analysis controller.
        
        Args:
            controller: The ManualAnalysisController instance.
        """
        # Disconnect from old board model if exists
        if self._analysis_controller:
            old_board_model = self._analysis_controller.get_board_model()
            if old_board_model:
                try:
                    old_board_model.bestnextmove_arrow_visibility_changed.disconnect(self._on_pv1_arrow_visibility_changed)
                    old_board_model.pv2_arrow_visibility_changed.disconnect(self._on_pv2_arrow_visibility_changed)
                    old_board_model.pv3_arrow_visibility_changed.disconnect(self._on_pv3_arrow_visibility_changed)
                    old_board_model.positional_plan_changed.disconnect(self._on_positional_plan_changed)
                    old_board_model.active_pv_plan_changed.disconnect(self._on_active_pv_plan_changed)
                except TypeError:
                    pass
        
        self._analysis_controller = controller
        
        # Connect to analysis model
        if controller:
            analysis_model = controller.get_analysis_model()
            self.set_analysis_model(analysis_model)
            
            # Connect to board model for arrow visibility changes and trajectory updates
            board_model = controller.get_board_model()
            if board_model:
                self._board_model = board_model
                board_model.bestnextmove_arrow_visibility_changed.connect(self._on_pv1_arrow_visibility_changed)
                board_model.pv2_arrow_visibility_changed.connect(self._on_pv2_arrow_visibility_changed)
                board_model.pv3_arrow_visibility_changed.connect(self._on_pv3_arrow_visibility_changed)
                board_model.positional_plan_changed.connect(self._on_positional_plan_changed)
                board_model.active_pv_plan_changed.connect(self._on_active_pv_plan_changed)
                
                # Initialize explore buttons with current state
                if hasattr(self, 'explore_pv1_button'):
                    active_pv_plan = board_model.active_pv_plan
                    self.explore_pv1_button.setChecked(active_pv_plan == 1)
                    self.explore_pv2_button.setChecked(active_pv_plan == 2)
                    self.explore_pv3_button.setChecked(active_pv_plan == 3)
                    self.explore_off_button.setChecked(active_pv_plan == 0)
    
    def set_analysis_model(self, model: ManualAnalysisModel) -> None:
        """Set the analysis model to observe for analysis changes.
        
        Args:
            model: The ManualAnalysisModel instance to observe.
        """
        if self._analysis_model:
            # Disconnect from old model
            try:
                self._analysis_model.analysis_changed.disconnect(self._on_analysis_changed)
                self._analysis_model.lines_changed.disconnect(self._on_lines_changed)
                self._analysis_model.is_analyzing_changed.disconnect(self._on_is_analyzing_changed)
            except TypeError:
                # Signal was not connected, ignore
                pass
        
        self._analysis_model = model
        
        # Connect to model signals
        if model:
            # Connect analysis_changed signal (will be debounced)
            model.analysis_changed.connect(self._on_analysis_changed)
            model.lines_changed.connect(self._on_lines_changed)
            model.is_analyzing_changed.connect(self._on_is_analyzing_changed)
            
            # Connect to board model for arrow visibility changes
            if self._analysis_controller:
                board_model = self._analysis_controller.get_board_model()
                if board_model:
                    board_model.bestnextmove_arrow_visibility_changed.connect(self._on_pv1_arrow_visibility_changed)
                    board_model.pv2_arrow_visibility_changed.connect(self._on_pv2_arrow_visibility_changed)
                    board_model.pv3_arrow_visibility_changed.connect(self._on_pv3_arrow_visibility_changed)
            
            # Initialize with current state (immediate update)
            self._on_is_analyzing_changed(model.is_analyzing)
            self._on_lines_changed()
            self._on_analysis_changed(immediate=True)
    
    def _on_start_stop_toggled(self, checked: bool) -> None:
        """Handle start/stop button toggle.
        
        Args:
            checked: True if button is checked (start), False if unchecked (stop).
        """
        if not self._analysis_controller:
            return
        
        if checked:
            # Start analysis (FEN will be retrieved from board controller)
            success = self._analysis_controller.start_analysis()
            if not success:
                # Failed to start - uncheck button
                self.start_stop_button.setChecked(False)
                self.start_stop_button.setText("Start Analysis")
        else:
            # Stop analysis
            self._analysis_controller.stop_analysis()
    
    def _on_add_line_clicked(self) -> None:
        """Handle add line button click."""
        if not self._analysis_controller or not self._analysis_model:
            return
        
        # Increase multipv (model will handle the rest)
        current_multipv = self._analysis_model.multipv
        new_multipv = current_multipv + 1
        self._analysis_controller.set_multipv(new_multipv)
        # UI will update via _on_lines_changed signal
    
    def _on_remove_line_clicked(self) -> None:
        """Handle remove line button click."""
        if not self._analysis_controller or not self._analysis_model:
            return
        
        # Decrease multipv (minimum 1, model will handle the rest)
        if self._analysis_model.multipv > 1:
            new_multipv = self._analysis_model.multipv - 1
            self._analysis_controller.set_multipv(new_multipv)
            # UI will update via _on_lines_changed signal
    
    def _on_explore_pv1_toggled(self, checked: bool) -> None:
        """Handle explore PV1 button toggle.
        
        Args:
            checked: True if button is checked, False otherwise.
        """
        if not self._analysis_controller:
            return
        
        if checked:
            # Uncheck other explore buttons (mutually exclusive)
            self.explore_pv2_button.setChecked(False)
            self.explore_pv3_button.setChecked(False)
            self.explore_off_button.setChecked(False)
            
            # Set PV1 exploration
            self._analysis_controller.set_explore_pv_plan(1)
        else:
            # If unchecked, switch to Off
            self.explore_off_button.setChecked(True)
            self._analysis_controller.set_explore_pv_plan(0)
    
    def _on_explore_pv2_toggled(self, checked: bool) -> None:
        """Handle explore PV2 button toggle.
        
        Args:
            checked: True if button is checked, False otherwise.
        """
        if not self._analysis_controller:
            return
        
        if checked:
            # Uncheck other explore buttons (mutually exclusive)
            self.explore_pv1_button.setChecked(False)
            self.explore_pv3_button.setChecked(False)
            self.explore_off_button.setChecked(False)
            
            # Set PV2 exploration
            self._analysis_controller.set_explore_pv_plan(2)
        else:
            # If unchecked, switch to Off
            self.explore_off_button.setChecked(True)
            self._analysis_controller.set_explore_pv_plan(0)
    
    def _on_explore_pv3_toggled(self, checked: bool) -> None:
        """Handle explore PV3 button toggle.
        
        Args:
            checked: True if button is checked, False otherwise.
        """
        if not self._analysis_controller:
            return
        
        if checked:
            # Uncheck other explore buttons (mutually exclusive)
            self.explore_pv1_button.setChecked(False)
            self.explore_pv2_button.setChecked(False)
            self.explore_off_button.setChecked(False)
            
            # Set PV3 exploration
            self._analysis_controller.set_explore_pv_plan(3)
        else:
            # If unchecked, switch to Off
            self.explore_off_button.setChecked(True)
            self._analysis_controller.set_explore_pv_plan(0)
    
    def _on_explore_off_toggled(self, checked: bool) -> None:
        """Handle explore Off button toggle.
        
        Args:
            checked: True if button is checked, False otherwise.
        """
        if not self._analysis_controller:
            return
        
        if checked:
            # Uncheck other explore buttons (mutually exclusive)
            self.explore_pv1_button.setChecked(False)
            self.explore_pv2_button.setChecked(False)
            self.explore_pv3_button.setChecked(False)
            
            # Disable exploration
            self._analysis_controller.set_explore_pv_plan(0)
    
    def _on_pieces_toggled(self, max_pieces: int, checked: bool) -> None:
        """Handle pieces button toggle.
        
        Args:
            max_pieces: Number of pieces to explore (1-3).
            checked: True if button is checked, False otherwise.
        """
        if not self._analysis_controller:
            return
        
        if checked:
            # Uncheck other pieces buttons (mutually exclusive)
            if max_pieces == 1:
                self.pieces_2_button.setChecked(False)
                self.pieces_3_button.setChecked(False)
            elif max_pieces == 2:
                self.pieces_1_button.setChecked(False)
                self.pieces_3_button.setChecked(False)
            else:  # max_pieces == 3
                self.pieces_1_button.setChecked(False)
                self.pieces_2_button.setChecked(False)
            
            # Update controller
            self._analysis_controller.set_max_pieces_to_explore(max_pieces)
            
            # Save to user settings
            from app.services.user_settings_service import UserSettingsService
            settings_service = UserSettingsService.get_instance()
            settings_service.update_manual_analysis({'max_pieces_to_explore': max_pieces})
            settings_service.save()
    
    def _on_depth_toggled(self, max_depth: int, checked: bool) -> None:
        """Handle depth button toggle.
        
        Args:
            max_depth: Maximum number of moves to show in trajectory (2-4).
            checked: True if button is checked, False otherwise.
        """
        if not self._analysis_controller:
            return
        
        if checked:
            # Uncheck other depth buttons (mutually exclusive)
            if max_depth == 2:
                self.depth_3_button.setChecked(False)
                self.depth_4_button.setChecked(False)
            elif max_depth == 3:
                self.depth_2_button.setChecked(False)
                self.depth_4_button.setChecked(False)
            else:  # max_depth == 4
                self.depth_2_button.setChecked(False)
                self.depth_3_button.setChecked(False)
            
            # Update controller
            self._analysis_controller.set_max_exploration_depth(max_depth)
            
            # Save to user settings
            from app.services.user_settings_service import UserSettingsService
            settings_service = UserSettingsService.get_instance()
            settings_service.update_manual_analysis({'max_exploration_depth': max_depth})
            settings_service.save()
    
    def _on_is_analyzing_changed(self, is_analyzing: bool) -> None:
        """Handle analysis state change from model.
        
        Args:
            is_analyzing: True if analyzing, False otherwise.
        """
        self._is_analyzing = is_analyzing
        
        # Update button text and state
        if is_analyzing:
            self.start_stop_button.setText("Stop Analysis")
            self.start_stop_button.setChecked(True)
        else:
            self.start_stop_button.setText("Start Analysis")
            self.start_stop_button.setChecked(False)
            # Hide empty label when analysis stops
            self.empty_label.setVisible(False)
            # Hide statistics bar when analysis stops
            if self.statistics_bar:
                self.statistics_bar.setVisible(False)
    
    def _on_lines_changed(self) -> None:
        """Handle lines count change from model."""
        if not self._analysis_model:
            return
        
        # Update multipv count and label
        self._multipv_count = self._analysis_model.multipv
        self.multipv_label.setText(str(self._multipv_count))
        
        # Enable/disable remove button
        if self._multipv_count > 1:
            self.remove_line_button.setEnabled(True)
        else:
            self.remove_line_button.setEnabled(False)
    
    def _on_pv1_arrow_visibility_changed(self, visible: bool) -> None:
        """Handle best next move arrow visibility change from board model.
        
        Args:
            visible: True if arrow is visible, False otherwise.
        """
        # Refresh analysis lines to update indicator styling (immediate update for user action)
        self._on_analysis_changed(immediate=True)
    
    def _on_pv2_arrow_visibility_changed(self, visible: bool) -> None:
        """Handle PV2 arrow visibility change from board model.
        
        Args:
            visible: True if arrow is visible, False otherwise.
        """
        # Refresh analysis lines to update indicator styling (immediate update for user action)
        self._on_analysis_changed(immediate=True)
    
    def _on_pv3_arrow_visibility_changed(self, visible: bool) -> None:
        """Handle PV3 arrow visibility change from board model.
        
        Args:
            visible: True if arrow is visible, False otherwise.
        """
        # Refresh analysis lines to update indicator styling (immediate update for user action)
        self._on_analysis_changed(immediate=True)
    
    def _on_positional_plan_changed(self, plan) -> None:
        """Handle positional plan change from board model.
        
        Args:
            plan: PieceTrajectory or None.
        """
        # Refresh analysis lines to update trajectory highlighting (immediate update for user action)
        self._on_analysis_changed(immediate=True)
    
    def _on_active_pv_plan_changed(self, pv_number: int) -> None:
        """Handle active PV plan change from board model.
        
        Args:
            pv_number: 0 for none, 1-3 for PV1-PV3.
        """
        # Sync explore buttons with current state
        if hasattr(self, 'explore_pv1_button'):
            self.explore_pv1_button.setChecked(pv_number == 1)
            self.explore_pv2_button.setChecked(pv_number == 2)
            self.explore_pv3_button.setChecked(pv_number == 3)
            self.explore_off_button.setChecked(pv_number == 0)
        
        # Refresh analysis lines to update trajectory highlighting (immediate update for user action)
        self._on_analysis_changed(immediate=True)
    
    def _on_analysis_changed(self, immediate: bool = False) -> None:
        """Handle analysis data change from model (debounced).
        
        Args:
            immediate: If True, update immediately without debouncing (for explicit user actions).
        """
        if not self._analysis_model:
            return
        
        if immediate:
            # Update immediately (e.g., when user clicks buttons)
            self._analysis_update_timer.stop()
            self._pending_analysis_update = False
            self._on_analysis_changed_debounced()
        else:
            # Debounce the update to improve performance during rapid navigation
            # Get debounce delay from config
            manual_analysis_config = self.config.get('ui', {}).get('panels', {}).get('detail', {}).get('manual_analysis', {})
            update_interval = manual_analysis_config.get('update_interval_ms', 100)
            
            # Mark that we have a pending update
            self._pending_analysis_update = True
            
            # Restart the timer (this will delay the actual update)
            self._analysis_update_timer.start(update_interval)
    
    def _on_analysis_changed_debounced(self) -> None:
        """Actually perform the analysis update after debounce delay."""
        if not self._analysis_model:
            return
        
        # Update statistics bar
        self._update_statistics_bar()
        
        # Get all analysis lines
        lines = self._analysis_model.lines
        
        # Store existing widgets by multipv to preserve hovered ones
        # Also track their positions to maintain order
        # Only preserve if miniature preview is enabled
        existing_widgets = {}  # multipv -> widget
        widget_positions = {}  # multipv -> position index
        enable_miniature_preview = True
        if self._analysis_model:
            enable_miniature_preview = self._analysis_model.enable_miniature_preview
        
        if enable_miniature_preview:
            for i in range(self.analysis_container_layout.count()):
                item = self.analysis_container_layout.itemAt(i)
                if item:
                    widget = item.widget()
                    if widget and widget != self.empty_label:
                        # Check all labels in this widget to see if any are hovered
                        hovered_multipv = None
                        for child in widget.findChildren(QLabel):
                            # Check if this is a hoverable label
                            if hasattr(child, '_multipv') and hasattr(child, '_is_hovered'):
                                # This is a hoverable label - check if it's being hovered
                                if child._is_hovered:
                                    # Found a hovered label - preserve this widget
                                    hovered_multipv = child._multipv
                                    break
                        
                        if hovered_multipv is not None:
                            existing_widgets[hovered_multipv] = widget
                            widget_positions[hovered_multipv] = i
        
        # Clear existing analysis lines from container (except hovered ones)
        # Remove all widgets and layout items except the empty label (if present)
        items_to_remove = []
        for i in range(self.analysis_container_layout.count()):
            item = self.analysis_container_layout.itemAt(i)
            if item:
                widget = item.widget()
                if widget and widget != self.empty_label:
                    # Check if this widget should be preserved (is being hovered)
                    should_preserve = False
                    for multipv, preserved_widget in existing_widgets.items():
                        if widget == preserved_widget:
                            should_preserve = True
                            break
                    
                    if not should_preserve:
                        items_to_remove.append(i)
                elif item.spacerItem():
                    items_to_remove.append(i)
        
        # Remove items in reverse order to maintain indices
        for i in reversed(items_to_remove):
            item = self.analysis_container_layout.takeAt(i)
            if item:
                widget = item.widget()
                if widget and widget != self.empty_label:
                    widget.setParent(None)
        
        # Hide empty label if we have lines
        if lines:
            self.empty_label.setVisible(False)
            
            # Create or update widgets for each analysis line
            # Process lines in order to maintain PV1, PV2, PV3 order
            for line_idx, line in enumerate(lines):
                if line.multipv in existing_widgets:
                    # Widget exists and is being hovered - don't recreate it
                    # The frozen PV state will keep the mini-board showing correctly
                    # Just ensure it's still in the layout at the correct position
                    preserved_widget = existing_widgets[line.multipv]
                    current_position = widget_positions.get(line.multipv, -1)
                    
                    # Check if widget is at the correct position
                    item_at_position = self.analysis_container_layout.itemAt(line_idx)
                    if item_at_position and item_at_position.widget() != preserved_widget:
                        # Widget is not at correct position - move it
                        # Remove from current position
                        for i in range(self.analysis_container_layout.count()):
                            item = self.analysis_container_layout.itemAt(i)
                            if item and item.widget() == preserved_widget:
                                self.analysis_container_layout.removeWidget(preserved_widget)
                                break
                        # Insert at correct position
                        self.analysis_container_layout.insertWidget(line_idx, preserved_widget, 0, Qt.AlignmentFlag.AlignTop)
                else:
                    # Create new widget
                    line_widget = self._create_analysis_line_widget(line)
                    # Insert at correct position to maintain order
                    self.analysis_container_layout.insertWidget(line_idx, line_widget, 0, Qt.AlignmentFlag.AlignTop)
            
            # Add stretch at the end if not already present
            last_item = self.analysis_container_layout.itemAt(self.analysis_container_layout.count() - 1)
            if not last_item or not last_item.spacerItem():
                self.analysis_container_layout.addStretch()
        else:
            # Hide empty label when no lines (don't show placeholder text)
            self.empty_label.setVisible(False)
            # Clear hovered labels when no lines
            self._hovered_labels.clear()
    
    def _create_analysis_line_widget(self, line) -> QWidget:
        """Create a widget for displaying an analysis line.
        
        Args:
            line: AnalysisLine instance.
            
        Returns:
            QWidget displaying the analysis line.
        """
        widget = QFrame()
        # Set size policy to prevent vertical stretching
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)
        
        # Get styling from config
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        manual_analysis_config = panel_config.get('manual_analysis', {})
        tabs_config = panel_config.get('tabs', {})
        
        # Get colors from config
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        colors_config = tabs_config.get('colors', {})
        normal = colors_config.get('normal', {})
        norm_text = normal.get('text', [200, 200, 200])
        norm_border = normal.get('border', [60, 60, 65])
        
        # Get font settings
        from app.utils.font_utils import resolve_font_family, scale_font_size
        font_family = resolve_font_family(tabs_config.get('font_family', 'Helvetica Neue'))
        font_size = scale_font_size(tabs_config.get('font_size', 10))
        label_config = manual_analysis_config.get('labels', {})
        label_font_size = scale_font_size(label_config.get('font_size', tabs_config.get('font_size', 10)))
        
        # Format evaluation
        if line.is_mate:
            if line.mate_moves > 0:
                eval_str = f"M{line.mate_moves}"  # White mates
            else:
                eval_str = f"M{abs(line.mate_moves)}"  # Black mates
        else:
            # Convert centipawns to pawns and format
            pawns = line.centipawns / 100.0
            if pawns > 0:
                eval_str = f"+{pawns:.2f}"
            else:
                eval_str = f"{pawns:.2f}"
        
        # Get line highlight styling from config
        line_highlight_config = label_config.get('line_highlight_style', {})
        line_highlight_color = line_highlight_config.get('color', [255, 255, 255])
        line_highlight_font_weight = line_highlight_config.get('font_weight', 'bold')
        
        # Calculate evaluation difference from best line (if enabled)
        eval_delta_str = ""
        if self.evaluation_difference_enabled and self.evaluation_difference_show_delta:
            best_line = None
            if self._analysis_model:
                best_line = self._analysis_model.get_best_line()
            
            if best_line and best_line.multipv != line.multipv:
                # Calculate difference (line evaluation - best line evaluation)
                if not line.is_mate and not best_line.is_mate:
                    # Both are regular evaluations
                    line_pawns = line.centipawns / 100.0
                    best_pawns = best_line.centipawns / 100.0
                    delta = line_pawns - best_pawns
                    
                    # Format delta
                    delta_formatted = self.evaluation_difference_delta_format.format(delta=delta)
                    
                    # Color-code delta (positive = green, negative = red)
                    if delta > 0:
                        delta_color = self.evaluation_difference_positive_color
                    else:
                        delta_color = self.evaluation_difference_negative_color
                    
                    eval_delta_str = f' <span style="color: rgb({delta_color[0]}, {delta_color[1]}, {delta_color[2]});">{delta_formatted}</span>'
        
        # Create formatted line text with HTML for bold parts
        # Bold: "Line X: +-Value" and first move of PV
        line_header = f"Line {line.multipv}: {eval_str}"
        depth_part = f" @ depth {line.depth}"
        
        # Format line text with bold header and evaluation delta
        line_text_html = f'<span style="font-weight: {line_highlight_font_weight}; color: rgb({line_highlight_color[0]}, {line_highlight_color[1]}, {line_highlight_color[2]});">{line_header}</span>{eval_delta_str}<span style="color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});">{depth_part}</span>'
        
        # Add PV with bold first move, truncated to fit available width
        if line.pv:
            pv_moves = line.pv.strip().split()
            if pv_moves:
                # Create font for measuring text width
                font = QFont(font_family, int(label_font_size))
                font_metrics = QFontMetrics(font)
                
                # Calculate width of header part (without PV)
                # Extract plain text from eval_delta_str for measurement (it contains HTML)
                eval_delta_plain = ""
                if eval_delta_str:
                    # Extract the delta value from HTML (format: (value))
                    import re
                    match = re.search(r'\(([+-]?[\d.]+)\)', eval_delta_str)
                    if match:
                        eval_delta_plain = " " + match.group(0)
                header_text = f"Line {line.multipv}: {eval_str}{eval_delta_plain} @ depth {line.depth} | PV: "
                header_width = font_metrics.horizontalAdvance(header_text)
                
                # Get available width from the scroll area viewport (actual available space)
                available_width = 800  # Fallback default
                if hasattr(self, 'analysis_area') and self.analysis_area:
                    viewport = self.analysis_area.viewport()
                    if viewport:
                        viewport_width = viewport.width()
                        if viewport_width > 0:
                            # Account for widget padding and margins
                            widget_margins = layout.contentsMargins()
                            # Also account for container layout margins
                            container_margins = self.analysis_container_layout.contentsMargins() if hasattr(self, 'analysis_container_layout') else (0, 0, 0, 0)
                            # Get scrollbar width from global styles config
                            styles_config = self.config.get('ui', {}).get('styles', {})
                            scrollbar_config = styles_config.get('scrollbar', {})
                            scrollbar_width = scrollbar_config.get('width', 6)
                            # Be conservative: account for scrollbar and add extra buffer to prevent horizontal scrolling
                            # Add buffer equivalent to about one move width (estimate ~40-50px for a typical move)
                            move_buffer = font_metrics.horizontalAdvance("Nf3 ")  # Estimate one move width
                            available_width = viewport_width - widget_margins.left() - widget_margins.right() - container_margins.left() - container_margins.right() - scrollbar_width - move_buffer
                
                # Calculate available width for PV moves
                pv_available_width = max(100, available_width - header_width)
                
                # Build PV string by adding moves until we exceed available width
                first_move = pv_moves[0]
                displayed_moves = [first_move]
                displayed_text = first_move
                displayed_width = font_metrics.horizontalAdvance(displayed_text)
                
                # Add remaining moves one by one
                # Estimate one move width for conservative truncation (to prevent scrollbars)
                estimated_move_width = font_metrics.horizontalAdvance("QQQQ#")  # Estimate one move width
                ellipsis_width = font_metrics.horizontalAdvance("...")
                
                for move in pv_moves[1:]:
                    test_text = displayed_text + " " + move
                    test_width = font_metrics.horizontalAdvance(test_text)
                    
                    # Check if adding this move would exceed available width
                    # Be conservative: subtract one move width buffer to prevent scrollbars
                    if test_width + ellipsis_width + estimated_move_width <= pv_available_width:
                        displayed_text = test_text
                        displayed_width = test_width
                        displayed_moves.append(move)
                    else:
                        # Can't fit this move, will truncate with "..."
                        break
                
                # Check if we need to add ellipsis
                needs_ellipsis = len(displayed_moves) < len(pv_moves)
                
                # Check if this line has trajectory highlighting enabled
                # Map trajectory index to move indices for all active trajectories
                trajectory_move_mapping = {}  # Maps trajectory_index -> set of move indices
                if (self.trajectory_highlight_enabled and 
                    self._board_model and 
                    self._board_model.active_pv_plan == line.multipv and
                    self._board_model.positional_plans):
                    trajectories = self._board_model.positional_plans
                    # Verify which moves actually correspond to each trajectory piece
                    import chess
                    try:
                        board = chess.Board(self._board_model.get_fen())
                        piece_type_map = {
                            'p': chess.PAWN, 'r': chess.ROOK, 'n': chess.KNIGHT,
                            'b': chess.BISHOP, 'q': chess.QUEEN, 'k': chess.KING
                        }
                        
                        # Process each trajectory
                        for trajectory_index, trajectory in enumerate(trajectories):
                            chess_piece_type = piece_type_map.get(trajectory.piece_type)
                            chess_color = chess.WHITE if trajectory.piece_color else chess.BLACK
                            
                            # Parse all PV moves to verify which ones are for this trajectory piece
                            # The trajectory is always for the side that is to move
                            # PV always starts with the side that is to move, so that side's moves are at even indices (0, 2, 4...)
                            verified_indices = set()
                            board_start = chess.Board(self._board_model.get_fen())
                            
                            for ply_idx in trajectory.ply_indices:
                                if ply_idx < len(pv_moves):
                                    # The trajectory is for the side that is to move, which always has even indices
                                    # So we only need to verify moves at even indices
                                    if ply_idx % 2 != 0:
                                        # This is an odd index, so it's for the opposite side - skip it
                                        continue
                                    
                                    # Reconstruct board state up to this move
                                    temp_board = chess.Board(self._board_model.get_fen())
                                    for i in range(ply_idx):
                                        if i < len(pv_moves):
                                            try:
                                                move_str = pv_moves[i]
                                                move = temp_board.parse_san(move_str)
                                                temp_board.push(move)
                                            except:
                                                break
                                    
                                    # Check the move at this index
                                    if ply_idx < len(pv_moves):
                                        try:
                                            move_str = pv_moves[ply_idx]
                                            move = temp_board.parse_san(move_str)
                                            # Check if this move is for the trajectory piece
                                            piece_at_from = temp_board.piece_at(move.from_square)
                                            if (piece_at_from and 
                                                piece_at_from.piece_type == chess_piece_type and
                                                piece_at_from.color == chess_color):
                                                verified_indices.add(ply_idx)
                                        except:
                                            pass
                            
                            # Use verified indices, or fall back to original if verification failed
                            if verified_indices:
                                trajectory_move_mapping[trajectory_index] = verified_indices
                            else:
                                # Fallback: use original ply_indices
                                trajectory_move_mapping[trajectory_index] = set(trajectory.ply_indices)
                    except:
                        # If verification fails, use original ply_indices for all trajectories
                        for trajectory_index, trajectory in enumerate(trajectories):
                            trajectory_move_mapping[trajectory_index] = set(trajectory.ply_indices)
                
                # Helper function to format a move with trajectory highlighting if needed
                # move_index_in_displayed is the index in displayed_moves (0, 1, 2...)
                # move_index_in_full_pv is the actual index in the full pv_moves array
                def format_move(move_text: str, move_index_in_displayed: int, move_index_in_full_pv: int) -> str:
                    # Check which trajectory (if any) this move belongs to
                    trajectory_index = None
                    for traj_idx, move_indices in trajectory_move_mapping.items():
                        if move_index_in_full_pv in move_indices:
                            trajectory_index = traj_idx
                            break
                    
                    if trajectory_index is not None:
                        # Highlight this move as part of a trajectory, using the trajectory's color
                        if trajectory_index == 0:
                            highlight_color = self.trajectory_1_color
                        elif trajectory_index == 1:
                            highlight_color = self.trajectory_2_color
                        else:  # trajectory_index == 2
                            highlight_color = self.trajectory_3_color
                        
                        # Use the trajectory color for both text and background (with transparency)
                        highlight_r, highlight_g, highlight_b = highlight_color
                        bg_r, bg_g, bg_b = highlight_color
                        return f'<span style="font-weight: {self.trajectory_highlight_font_weight}; color: rgb({highlight_r}, {highlight_g}, {highlight_b}); background-color: rgba({bg_r}, {bg_g}, {bg_b}, {self.trajectory_highlight_bg_alpha}); padding: 1px 2px; border-radius: 2px;">{move_text}</span>'
                    else:
                        # Normal formatting (first move gets line highlight, others get normal)
                        if move_index_in_displayed == 0:
                            return f'<span style="font-weight: {line_highlight_font_weight}; color: rgb({line_highlight_color[0]}, {line_highlight_color[1]}, {line_highlight_color[2]});">{move_text}</span>'
                        else:
                            return f'<span style="color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});">{move_text}</span>'
                
                # Build HTML for PV part with trajectory highlighting
                if len(displayed_moves) == 1:
                    # Only first move (index 0 in both displayed and full PV)
                    first_move_html = format_move(first_move, 0, 0)
                    if needs_ellipsis:
                        pv_part = f' | PV: {first_move_html} <span style="color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});">...</span>'
                    else:
                        pv_part = f' | PV: {first_move_html}'
                else:
                    # Multiple moves - format each move individually
                    # Map displayed_moves indices to full pv_moves indices
                    move_htmls = []
                    for displayed_idx, move in enumerate(displayed_moves):
                        # displayed_idx is the index in displayed_moves
                        # The actual index in full pv_moves is the same (since displayed_moves is a prefix of pv_moves)
                        full_pv_idx = displayed_idx
                        move_htmls.append(format_move(move, displayed_idx, full_pv_idx))
                    moves_html = " ".join(move_htmls)
                    if needs_ellipsis:
                        pv_part = f' | PV: {moves_html} <span style="color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});">...</span>'
                    else:
                        pv_part = f' | PV: {moves_html}'
                
                line_text_html += pv_part
            else:
                line_text_html += f' | PV: <span style="color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});">{line.pv}</span>'
        
        # Check if PV hover is enabled and we should use HoverablePvLabel
        manual_analysis_config = self.config.get('ui', {}).get('panels', {}).get('detail', {}).get('manual_analysis', {})
        pv_hover_config = manual_analysis_config.get('pv_hover', {})
        pv_hover_enabled = pv_hover_config.get('enabled', True)
        
        # Get PV moves if available
        pv_moves = []
        if line.pv:
            pv_moves = line.pv.strip().split()
        
        # Get current analysis position (FEN)
        current_fen = None
        board_controller = None
        if self._analysis_controller:
            board_model = self._analysis_controller.get_board_model()
            if board_model:
                current_fen = board_model.get_fen()
            board_controller = self._analysis_controller.get_board_controller()
        
        # Create line widget with separate labels for each move if hover is enabled
        if (pv_moves and pv_hover_enabled and board_controller and current_fen):
            # Use separate labels for each move
            from app.views.hoverable_pv_label import HoverablePvLabel
            
            # Create horizontal layout for PV section
            pv_layout = QHBoxLayout()
            pv_layout.setContentsMargins(0, 0, 0, 0)
            pv_layout.setSpacing(0)
            pv_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)  # Ensure left alignment
            
            # Create shared stylesheet for labels (to reduce overhead)
            shared_stylesheet = f"""
                QLabel {{
                    color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                    font-family: "{font_family}";
                    font-size: {int(label_font_size)}pt;
                    border: none;
                    background-color: transparent;
                }}
            """
            
            # Add " | PV: " prefix
            prefix_label = QLabel(" | PV: ")
            prefix_label.setStyleSheet(shared_stylesheet)
            prefix_palette = prefix_label.palette()
            prefix_palette.setColor(prefix_label.foregroundRole(), QColor(norm_text[0], norm_text[1], norm_text[2]))
            prefix_label.setPalette(prefix_palette)
            prefix_label.update()
            pv_layout.addWidget(prefix_label)
            
            # Calculate available width for PV moves (same logic as non-hoverable version)
            # Create font for measuring text width
            font = QFont(font_family, int(label_font_size))
            font_metrics = QFontMetrics(font)
            
            # Calculate width of header part (without PV)
            eval_delta_plain = ""
            if eval_delta_str:
                import re
                match = re.search(r'\(([+-]?[\d.]+)\)', eval_delta_str)
                if match:
                    eval_delta_plain = " " + match.group(0)
            header_text = f"Line {line.multipv}: {eval_str}{eval_delta_plain} @ depth {line.depth} | PV: "
            header_width = font_metrics.horizontalAdvance(header_text)
            
            # Get available width from the scroll area viewport
            available_width = 800  # Fallback default
            if hasattr(self, 'analysis_area') and self.analysis_area:
                viewport = self.analysis_area.viewport()
                if viewport:
                    viewport_width = viewport.width()
                    if viewport_width > 0:
                        widget_margins = layout.contentsMargins()
                        container_margins = self.analysis_container_layout.contentsMargins() if hasattr(self, 'analysis_container_layout') else (0, 0, 0, 0)
                        # Get scrollbar width from global styles config
                        styles_config = self.config.get('ui', {}).get('styles', {})
                        scrollbar_config = styles_config.get('scrollbar', {})
                        scrollbar_width = scrollbar_config.get('width', 6)
                        move_buffer = font_metrics.horizontalAdvance("Nf3 ")  # Estimate one move width
                        available_width = viewport_width - widget_margins.left() - widget_margins.right() - container_margins.left() - container_margins.right() - scrollbar_width - move_buffer
            
            # Calculate available width for PV moves
            pv_available_width = max(100, available_width - header_width)
            
            # Build displayed_moves by adding moves until we exceed available width
            first_move = pv_moves[0]
            displayed_moves = [first_move]
            displayed_text = first_move
            displayed_width = font_metrics.horizontalAdvance(displayed_text)
            
            # Add remaining moves one by one
            # Estimate one move width for conservative truncation (to prevent scrollbars)
            estimated_move_width = font_metrics.horizontalAdvance("QQQQ#")  # Estimate one move width
            ellipsis_width = font_metrics.horizontalAdvance("...")
            
            for move in pv_moves[1:]:
                # Account for space between moves
                test_text = displayed_text + " " + move
                test_width = font_metrics.horizontalAdvance(test_text)
                
                # Check if adding this move would exceed available width
                # Be conservative: subtract one move width buffer to prevent scrollbars
                if test_width + ellipsis_width + estimated_move_width <= pv_available_width:
                    displayed_text = test_text
                    displayed_width = test_width
                    displayed_moves.append(move)
                else:
                    # Can't fit this move, will truncate with "..."
                    break
            
            # Check if we need to add ellipsis
            needs_ellipsis = len(displayed_moves) < len(pv_moves)
            
            # Create a hoverable label for each move
            for move_idx, move_text in enumerate(displayed_moves):
                # Format move with trajectory highlighting if available
                if trajectory_move_mapping:
                    full_pv_idx = move_idx
                    formatted_move = format_move(move_text, move_idx, full_pv_idx)
                else:
                    # No trajectory highlighting, use simple formatting
                    if move_idx == 0:
                        formatted_move = f'<span style="font-weight: {line_highlight_font_weight}; color: rgb({line_highlight_color[0]}, {line_highlight_color[1]}, {line_highlight_color[2]});">{move_text}</span>'
                    else:
                        formatted_move = f'<span style="color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});">{move_text}</span>'
                
                # Create hoverable label
                move_label = HoverablePvLabel(
                    move_text=move_text,
                    move_index=move_idx,
                    pv_moves=pv_moves,
                    current_fen=current_fen,
                    board_controller=board_controller,
                    config=self.config,
                    multipv=line.multipv,
                    analysis_model=self._analysis_model
                )
                move_label.setTextFormat(Qt.TextFormat.RichText)
                move_label.setWordWrap(False)
                move_label.setText(formatted_move)
                move_label.setStyleSheet(shared_stylesheet)
                move_palette = move_label.palette()
                move_palette.setColor(move_label.foregroundRole(), QColor(norm_text[0], norm_text[1], norm_text[2]))
                move_label.setPalette(move_palette)
                move_label.update()
                pv_layout.addWidget(move_label)
                
                # Add space after move (except last)
                if move_idx < len(displayed_moves) - 1 or needs_ellipsis:
                    space_label = QLabel(" ")
                    space_label.setStyleSheet(shared_stylesheet)
                    space_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)  # Don't process mouse events for spaces
                    pv_layout.addWidget(space_label)
            
            # Add ellipsis if needed
            if needs_ellipsis:
                ellipsis_label = QLabel(f'<span style="color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});">...</span>')
                ellipsis_label.setTextFormat(Qt.TextFormat.RichText)
                ellipsis_label.setStyleSheet(shared_stylesheet)
                ellipsis_palette = ellipsis_label.palette()
                ellipsis_palette.setColor(ellipsis_label.foregroundRole(), QColor(norm_text[0], norm_text[1], norm_text[2]))
                ellipsis_label.setPalette(ellipsis_palette)
                ellipsis_label.update()
                pv_layout.addWidget(ellipsis_label)
            
            # Create container widget for PV section
            pv_widget = QWidget()
            pv_widget.setLayout(pv_layout)
            
            # Create main line label (without PV part - extract everything before " | PV: ")
            pv_prefix = " | PV: "
            pv_start = line_text_html.find(pv_prefix)
            if pv_start != -1:
                line_text_without_pv = line_text_html[:pv_start]
            else:
                line_text_without_pv = line_text_html
            
            line_label = QLabel(line_text_without_pv)
            line_label.setWordWrap(False)
            line_label.setTextFormat(Qt.TextFormat.RichText)
            line_label.setStyleSheet(f"""
                QLabel {{
                    color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                    font-family: "{font_family}";
                    font-size: {int(label_font_size)}pt;
                    border: none;
                    background-color: transparent;
                }}
            """)
            line_palette = line_label.palette()
            line_palette.setColor(line_label.foregroundRole(), QColor(norm_text[0], norm_text[1], norm_text[2]))
            line_label.setPalette(line_palette)
            line_label.update()
            
            # Create horizontal layout for entire line
            line_layout = QHBoxLayout()
            line_layout.setContentsMargins(0, 0, 0, 0)
            line_layout.setSpacing(0)
            line_layout.addWidget(line_label)
            line_layout.addWidget(pv_widget)
            line_layout.addStretch()  # Add stretch to push everything to the left
            
            line_widget = QWidget()
            line_widget.setLayout(line_layout)
            layout.addWidget(line_widget)
        else:
            # Fallback to standard QLabel if hover not available
            line_label = QLabel(line_text_html)
            line_label.setWordWrap(False)
            line_label.setTextFormat(Qt.TextFormat.RichText)
            line_label.setStyleSheet(f"""
                QLabel {{
                    color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                    font-family: "{font_family}";
                    font-size: {int(label_font_size)}pt;
                    border: none;
                    background-color: transparent;
                }}
            """)
            line_palette = line_label.palette()
            line_palette.setColor(line_label.foregroundRole(), QColor(norm_text[0], norm_text[1], norm_text[2]))
            line_label.setPalette(line_palette)
            line_label.update()
            layout.addWidget(line_label)
        
        # Check if this line should show an indicator based on multipv and arrow visibility
        show_indicator = False
        indicator_width = 0
        indicator_color = [0, 0, 0]
        
        if self._analysis_controller:
            board_model = self._analysis_controller.get_board_model()
            if board_model:
                if (line.multipv == 1 and 
                    self.multipv1_indicator_enabled and 
                    board_model.show_bestnextmove_arrow):
                    show_indicator = True
                    indicator_width = self.multipv1_indicator_width
                    indicator_color = self.bestnextmove_arrow_color
                elif (line.multipv == 2 and 
                      self.multipv2_indicator_enabled and 
                      board_model.show_pv2_arrow):
                    show_indicator = True
                    indicator_width = self.multipv2_indicator_width
                    indicator_color = self.pv2_arrow_color
                elif (line.multipv == 3 and 
                      self.multipv3_indicator_enabled and 
                      board_model.show_pv3_arrow):
                    show_indicator = True
                    indicator_width = self.multipv3_indicator_width
                    indicator_color = self.pv3_arrow_color
        
        # Apply frame styling
        if show_indicator:
            # Apply colored left border for multipv line when arrow is visible
            widget.setStyleSheet(f"""
                QFrame {{
                    background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
                    border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
                    border-left: {indicator_width}px solid rgb({indicator_color[0]}, {indicator_color[1]}, {indicator_color[2]});
                    border-radius: 4px;
                }}
            """)
        else:
            # Standard styling with outer border
            widget.setStyleSheet(f"""
                QFrame {{
                    background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
                    border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
                    border-radius: 4px;
                }}
            """)
        
        return widget
    
    def _update_statistics_bar(self) -> None:
        """Update the statistics bar with current engine statistics."""
        if not self.statistics_bar or not self.statistics_enabled:
            return
        
        if not self._analysis_model:
            self.statistics_bar.setVisible(False)
            return
        
        # Get lines to extract statistics (NPS and hash are the same for all lines)
        lines = self._analysis_model.lines
        if not lines:
            self.statistics_bar.setVisible(False)
            return
        
        # Get statistics from first line (they're the same for all lines)
        first_line = lines[0]
        nps = first_line.nps
        hashfull = first_line.hashfull
        
        # Build statistics text
        stats_parts = []
        
        if self.statistics_show_nps and nps >= 0:
            # Format NPS (e.g., "2.5M" or "2500K" or "2500000")
            if nps >= 1_000_000:
                nps_str = f"{nps / 1_000_000:.1f}M"
            elif nps >= 1_000:
                nps_str = f"{nps / 1_000:.1f}K"
            else:
                nps_str = str(nps)
            stats_parts.append(f"NPS: {nps_str}")
        
        if self.statistics_show_hash and hashfull >= 0:
            # Format hash usage as percentage (hashfull is 0-1000, so divide by 10)
            hash_percent = hashfull / 10.0
            stats_parts.append(f"Hash: {hash_percent:.1f}%")
        
        if self.statistics_show_time:
            # Get elapsed time from model
            elapsed_time = self._analysis_model.get_elapsed_time()
            if elapsed_time > 0:
                # Format time (e.g., "5.2s" or "1m 5.2s")
                if elapsed_time < 60:
                    time_str = f"{elapsed_time:.1f}s"
                else:
                    minutes = int(elapsed_time // 60)
                    seconds = elapsed_time % 60
                    time_str = f"{minutes}m {seconds:.1f}s"
                stats_parts.append(f"Time: {time_str}")
        
        if self.statistics_show_nodes and nps >= 0 and self._analysis_model.get_elapsed_time() > 0:
            # Calculate total nodes (NPS * time)
            total_nodes = int(nps * self._analysis_model.get_elapsed_time())
            if total_nodes >= 1_000_000:
                nodes_str = f"{total_nodes / 1_000_000:.1f}M"
            elif total_nodes >= 1_000:
                nodes_str = f"{total_nodes / 1_000:.1f}K"
            else:
                nodes_str = str(total_nodes)
            stats_parts.append(f"Nodes: {nodes_str}")
        
        # Update label text
        if stats_parts:
            stats_text = self.statistics_separator.join(stats_parts)
            self.statistics_label.setText(stats_text)
            self.statistics_bar.setVisible(True)
        else:
            self.statistics_bar.setVisible(False)
