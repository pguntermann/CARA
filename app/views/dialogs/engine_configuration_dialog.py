"""Engine configuration dialog for setting engine parameters per task."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QLabel,
    QLineEdit,
    QCheckBox,
    QComboBox,
    QPushButton,
    QScrollArea,
    QGroupBox,
    QFormLayout,
    QSizePolicy,
    QApplication,
    QFrame,
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QFont, QFontMetrics, QIntValidator, QShowEvent, QMoveEvent, QWheelEvent
from pathlib import Path
from html import escape
from typing import Optional, Dict, Any, List
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.path_display_utils import truncate_path_for_display
from app.utils.themed_icon import (
    SVG_MENU_COPY,
    SVG_MENU_PASTE_CLIPBOARD,
    themed_icon_from_svg,
)
from app.controllers.engine_configuration_controller import EngineConfigurationController


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events to prevent accidental value changes."""
    
    def wheelEvent(self, event: QWheelEvent) -> None:
        """Override wheel event to ignore it completely."""
        event.ignore()


class EngineConfigurationDialog(QDialog):
    """Dialog for configuring engine parameters per task."""
    
    def __init__(self, config: Dict[str, Any], engine_id: str, engine_controller, parent=None) -> None:
        """Initialize the engine configuration dialog.
        
        Args:
            config: Configuration dictionary.
            engine_id: ID of the engine to configure.
            engine_controller: EngineController instance.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.engine_id = engine_id
        self.engine_controller = engine_controller
        
        # Get engine data
        engine_model = engine_controller.get_engine_model()
        engine = engine_model.get_engine(engine_id)
        if not engine:
            from app.views.dialogs.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Engine Not Found",
                f"Engine with ID '{engine_id}' not found.",
                self
            )
            self.reject()
            return
        
        self.engine = engine
        self.engine_path = Path(engine.path)
        
        # Initialize controller
        self.controller = EngineConfigurationController(config, self.engine_path, engine_controller)
        self.engine_options = self.controller.get_engine_options()
        # Task constants (from controller)
        self.TASK_EVALUATION = EngineConfigurationController.TASK_EVALUATION
        self.TASK_GAME_ANALYSIS = EngineConfigurationController.TASK_GAME_ANALYSIS
        self.TASK_MANUAL_ANALYSIS = EngineConfigurationController.TASK_MANUAL_ANALYSIS
        self.TASK_BRILLIANCY_DETECTION = EngineConfigurationController.TASK_BRILLIANCY_DETECTION
        
        # Store widgets for each task: {task: {param_name: widget}}
        self.task_widgets: Dict[str, Dict[str, Any]] = {
            self.TASK_EVALUATION: {},
            self.TASK_GAME_ANALYSIS: {},
            self.TASK_MANUAL_ANALYSIS: {},
            self.TASK_BRILLIANCY_DETECTION: {},
        }
        # Tab index order matches task order
        self._task_order = [self.TASK_EVALUATION, self.TASK_GAME_ANALYSIS, self.TASK_MANUAL_ANALYSIS, self.TASK_BRILLIANCY_DETECTION]
        # Paste buttons (one per task tab); enabled only when clipboard has content
        self._paste_buttons: List[QPushButton] = []
        # Copy/Paste toolbar buttons (icon-only; styled separately from main actions)
        self._copy_paste_icon_buttons: List[QPushButton] = []
        
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_configuration', {})
        self.dialog_width = int(dialog_config.get('width', 600))
        self.bottom_button_top_padding = int(dialog_config.get('bottom_button_top_padding', 50))
        self.dialog_minimum_width = dialog_config.get('minimum_width')
        self.dialog_minimum_height = dialog_config.get('minimum_height')
        
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        
        self._setup_ui()
        self._apply_styling()
        self._apply_configured_dialog_size()
        self.setWindowTitle(f"Engine Configuration - {engine.name}")
    
    def _apply_configured_dialog_size(self) -> None:
        """Width from config; height from layout size hint (floored by optional minimum_height)."""
        w = int(self.dialog_width)
        if self.dialog_minimum_width is not None:
            w = max(w, int(self.dialog_minimum_width))
        self.setFixedWidth(w)
        lay = self.layout()
        if lay is None:
            return
        h = lay.sizeHint().height()
        if h <= 0:
            return
        if self.dialog_minimum_height is not None:
            h = max(h, int(self.dialog_minimum_height))
        self.setFixedHeight(h)
    
    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._apply_configured_dialog_size()
        QTimer.singleShot(0, self._update_path_label_truncation)
    
    def moveEvent(self, event: QMoveEvent) -> None:
        """Override move event."""
        super().moveEvent(event)

    def _update_path_label_truncation(self) -> None:
        """Re-truncate path using label's actual width and font (DPI-aware)."""
        path_label = self._engine_path_label
        font = self._engine_path_font
        w = path_label.width()
        if w > 0:
            path_max_width_px = max(80, w - 8)
        else:
            dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_configuration', {})
            layout_margins = dialog_config.get('layout', {}).get('margins', [10, 10, 10, 10])
            path_max_width_px = max(
                80,
                int(getattr(self, 'dialog_width', dialog_config.get('width', 600)))
                - layout_margins[0]
                - layout_margins[2]
                - getattr(self, '_engine_path_lead_spacer', 0)
                - 8,
            )
        path_display = truncate_path_for_display(
            self.engine_path, max_width_px=path_max_width_px, font=font
        )
        path_label.setText(path_display)
        path_label.setToolTip(str(self.engine_path))

    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        # Get layout spacing and margins from config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_configuration', {})
        layout_config = dialog_config.get('layout', {})
        layout_spacing = layout_config.get('spacing', 10)
        layout_margins = layout_config.get('margins', [10, 10, 10, 10])
        spacing_after_header = layout_config.get('spacing_after_header', 8)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(layout_spacing)
        # Prevent layout from resizing the dialog
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetNoConstraint)
        layout.setContentsMargins(layout_margins[0], layout_margins[1], layout_margins[2], layout_margins[3])
        
        # Engine info header (same pattern as BulkReplaceDialog database name/path: no boxed frame).
        # Font metrics match BulkReplaceDialog labels (dialogs.*.labels), with header.* as fallback.
        labels_config = dialog_config.get('labels', {})
        header_config = dialog_config.get('header', {})
        title_font_family = resolve_font_family(
            labels_config.get('font_family') or header_config.get('font_family', 'Helvetica Neue')
        )
        # Same sizing as BulkReplaceDialog database path: int(scale_font_size(labels.font_size)) - 2
        _label_fs_raw = labels_config.get('font_size', header_config.get('font_size', 11))
        label_font_size = int(scale_font_size(_label_fs_raw))
        title_font_size = label_font_size
        # Same delta as BulkReplaceDialog path (label_font_size - 2); explicit QSS enforces pt size on Windows.
        path_font_size = max(8, label_font_size - 2)
        self._engine_label_font_size = label_font_size
        self._engine_title_font_family_resolved = title_font_family
        title_font = QFont(title_font_family, title_font_size)
        path_font = QFont(title_font_family, path_font_size)
        path_font_metrics = QFontMetrics(path_font)
        path_line_height = path_font_metrics.lineSpacing()

        self._engine_header_widget = QWidget()
        header_layout = QVBoxLayout(self._engine_header_widget)
        header_layout.setContentsMargins(0, 0, 0, spacing_after_header)
        header_layout.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        self._engine_label_prefix = QLabel("Engine:")
        self._engine_label_prefix.setFont(title_font)
        self._engine_name_label = QLabel(f"<b>{escape(self.engine.name)}</b>")
        self._engine_name_label.setFont(title_font)
        self._engine_name_label.setWordWrap(False)
        title_row.addWidget(self._engine_label_prefix)
        title_row.addWidget(self._engine_name_label)
        title_row.addStretch()

        header_layout.addLayout(title_row)

        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.setSpacing(0)
        label_fm = QFontMetrics(self._engine_label_prefix.font())
        spacer_w = label_fm.horizontalAdvance("Engine:") + 8
        self._engine_path_lead_spacer = spacer_w
        path_spacer = QWidget()
        path_spacer.setFixedWidth(spacer_w)
        path_row.addWidget(path_spacer)

        initial_path_max = max(
            80,
            int(self.dialog_width)
            - layout_margins[0]
            - layout_margins[2]
            - spacer_w
            - 8,
        )
        path_display = truncate_path_for_display(
            self.engine_path, max_width_px=initial_path_max, font=path_font
        )
        self._engine_path_label = QLabel(path_display)
        self._engine_path_label.setWordWrap(False)
        self._engine_path_label.setToolTip(str(self.engine_path))
        # Match BulkReplaceDialog db path: setFont drives point size; stylesheet is color-only (see _apply_engine_info_path_style).
        self._engine_path_label.setFont(path_font)
        self._engine_path_font = path_font
        self._apply_engine_info_path_style(dialog_config)
        self._engine_path_label.setFixedHeight(path_line_height)
        path_row.addWidget(self._engine_path_label)
        path_row.addStretch()

        path_row_widget = QWidget()
        path_row_widget.setLayout(path_row)
        path_row_widget.setFixedHeight(path_line_height)
        header_layout.addWidget(path_row_widget)

        layout.addWidget(self._engine_header_widget)
        
        # Tab widget for tasks (scroll areas use config-fixed heights; dialog height follows layout)
        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(False)  # Disable document mode for better control
        self.tab_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        
        # Create tabs for each task
        self._create_task_tab(self.TASK_EVALUATION, "Evaluation")
        self._create_task_tab(self.TASK_GAME_ANALYSIS, "Game Analysis")
        self._create_task_tab(self.TASK_MANUAL_ANALYSIS, "Manual Analysis")
        self._create_task_tab(self.TASK_BRILLIANCY_DETECTION, "Brilliancy Detection")
        
        layout.addWidget(self.tab_widget)
        
        layout.addSpacing(self.bottom_button_top_padding)
        
        # Buttons: Reset (bottom-left), then stretch, Cancel and Save (bottom-right)
        buttons_config = dialog_config.get('buttons', {})
        button_layout = QHBoxLayout()
        button_layout.setSpacing(buttons_config.get('spacing', 10))
        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.setToolTip("Reset all engine settings to defaults")
        self.reset_button.clicked.connect(self._on_reset_clicked)
        button_layout.addWidget(self.reset_button)
        button_layout.addStretch()
        
        self.ok_button = QPushButton("Save Changes")
        self.ok_button.clicked.connect(self._on_ok_clicked)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)
        
        layout.addLayout(button_layout)
    
    def _create_task_tab(self, task: str, task_label: str) -> None:
        """Create a tab for a specific task.
        
        Args:
            task: Task identifier.
            task_label: Display label for the task.
        """
        tab = QWidget()
        # Set background color immediately when tab is created
        # This ensures the first tab has the correct background from the start
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_configuration', {})
        tabs_config = dialog_config.get('tabs', {})
        tabs_layout_config = dialog_config.get('tabs_layout', {})
        groups_config = dialog_config.get('groups', {})
        group_margin_top = groups_config.get('margin_top', 8)
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        from PyQt6.QtGui import QPalette, QColor
        tab.setAutoFillBackground(True)
        tab_palette = tab.palette()
        tab_palette.setColor(tab.backgroundRole(), QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        tab_palette.setColor(QPalette.ColorRole.Window, QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        tab_palette.setColor(QPalette.ColorRole.Base, QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        tab.setPalette(tab_palette)
        
        tab_layout = QVBoxLayout(tab)
        tab_layout_spacing = tabs_layout_config.get('spacing', 15)
        tab_layout_margins = tabs_layout_config.get('margins', [15, 10, 15, 10])
        tab_layout.setSpacing(tab_layout_spacing)
        # Add padding around the tab content to prevent group boxes from touching borders
        # Left, Top, Right, Bottom margins
        tab_layout.setContentsMargins(tab_layout_margins[0], tab_layout_margins[1], tab_layout_margins[2], tab_layout_margins[3])
        
        # Add a small spacer at the top to create space between tab bar and first group
        top_spacer = tabs_layout_config.get('top_spacer', 5)
        tab_layout.addSpacing(top_spacer)
        
        # Add spacing between group boxes (accounting for group box margin_top)
        # The group box has margin_top, so we subtract it from explicit spacing to avoid double spacing
        spacing_between_groups = max(0, tab_layout_spacing - group_margin_top)
        if spacing_between_groups > 0:
            tab_layout.addSpacing(spacing_between_groups)
        
        # Common parameters section
        common_group = QGroupBox("Common Parameters")
        # Compact 3-column layout (label above field) to reduce vertical height
        # on low-resolution screens.
        common_layout = QHBoxLayout()
        common_layout_spacing = tabs_layout_config.get('common_layout_spacing', 10)
        common_layout.setSpacing(common_layout_spacing)
        common_layout.setContentsMargins(0, 0, 0, 0)
        
        # Get saved parameters for this task (with fallback to recommended defaults)
        recommended_defaults = self.controller.get_recommended_defaults(task)
        
        # Load saved parameters from engine_parameters.json
        saved_params = self.controller.get_task_parameters(task)
        
        # Use saved values if available, otherwise use recommended defaults
        threads_value = saved_params.get("threads", recommended_defaults.get("threads", 1))
        depth_value = saved_params.get("depth", recommended_defaults.get("depth", 0))
        movetime_value = saved_params.get("movetime", recommended_defaults.get("movetime", 0))
        
        # Threads
        threads_label = QLabel("Threads:")
        threads_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        threads_edit = QLineEdit()
        threads_edit.setText(str(threads_value))
        threads_edit.setValidator(QIntValidator(1, 512))
        threads_edit.setToolTip("Number of threads for engine analysis (1-512)")
        threads_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        threads_col = QVBoxLayout()
        threads_col.setSpacing(4)
        threads_col.setContentsMargins(0, 0, 0, 0)
        threads_col.addWidget(threads_label, 0, Qt.AlignmentFlag.AlignLeft)
        threads_col.addWidget(threads_edit, 0)
        self.task_widgets[task]["threads"] = threads_edit
        
        # Depth
        depth_label = QLabel("Max Depth:")
        depth_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        depth_edit = QLineEdit()
        depth_edit.setText(str(depth_value))
        depth_edit.setValidator(QIntValidator(0, 100))
        depth_edit.setToolTip("Maximum search depth")
        depth_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        depth_col = QVBoxLayout()
        depth_col.setSpacing(4)
        depth_col.setContentsMargins(0, 0, 0, 0)
        depth_col.addWidget(depth_label, 0, Qt.AlignmentFlag.AlignLeft)
        depth_col.addWidget(depth_edit, 0)
        self.task_widgets[task]["depth"] = depth_edit
        
        # Movetime (in milliseconds)
        movetime_label = QLabel("Move Time:")
        movetime_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        movetime_edit = QLineEdit()
        movetime_edit.setText(str(movetime_value))
        movetime_edit.setValidator(QIntValidator(0, 3600000))  # 1 hour max
        movetime_edit.setToolTip("Maximum time per move (ply) in milliseconds")
        movetime_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        movetime_col = QVBoxLayout()
        movetime_col.setSpacing(4)
        movetime_col.setContentsMargins(0, 0, 0, 0)
        movetime_col.addWidget(movetime_label, 0, Qt.AlignmentFlag.AlignLeft)
        movetime_col.addWidget(movetime_edit, 0)
        self.task_widgets[task]["movetime"] = movetime_edit
        
        # Disable depth and movetime inputs based on task requirements
        # Evaluation: both depth and movetime are ignored (infinite analysis)
        # Manual Analysis: both depth and movetime are ignored (continuous analysis)
        # Game Analysis: depth is ignored, movetime is used
        # Brilliancy Detection: depth is ignored (shallow depths from config), movetime is used
        if task == self.TASK_EVALUATION or task == self.TASK_MANUAL_ANALYSIS:
            # Disable both depth and movetime for Evaluation and Manual Analysis
            depth_edit.setEnabled(False)
            depth_edit.setToolTip("Depth is not used for this task type (infinite/continuous analysis)")
            depth_label.setEnabled(False)
            movetime_edit.setEnabled(False)
            movetime_edit.setToolTip("Move time is not used for this task type (infinite/continuous analysis)")
            movetime_label.setEnabled(False)
        elif task == self.TASK_GAME_ANALYSIS or task == self.TASK_BRILLIANCY_DETECTION:
            # Disable depth only (movetime is used for Game Analysis and Brilliancy Detection)
            depth_edit.setEnabled(False)
            depth_edit.setToolTip("Depth is not used for this task type (move time / shallow depths from config)")
            depth_label.setEnabled(False)
            movetime_edit.setEnabled(True)
            movetime_edit.setToolTip("Maximum time per move (ply) in milliseconds")
            movetime_label.setEnabled(True)
        
        # Wrap columns into widgets so the outer layout can size them evenly.
        threads_widget = QWidget()
        threads_widget.setLayout(threads_col)
        depth_widget = QWidget()
        depth_widget.setLayout(depth_col)
        movetime_widget = QWidget()
        movetime_widget.setLayout(movetime_col)
        
        common_layout.addWidget(threads_widget, 1)
        common_layout.addWidget(depth_widget, 1)
        common_layout.addWidget(movetime_widget, 1)
        
        common_group.setLayout(common_layout)
        tab_layout.addWidget(common_group)
        
        # Add spacing between group boxes (accounting for group box margin_top)
        # The group box has margin_top, so we subtract it from explicit spacing to avoid double spacing
        spacing_between_groups = max(0, tab_layout_spacing - group_margin_top)
        if spacing_between_groups > 0:
            tab_layout.addSpacing(spacing_between_groups)
        
        # Engine-specific parameters section
        if self.engine_options:
            engine_params_group = QGroupBox("Engine-Specific Parameters")
            engine_params_group_layout = QVBoxLayout()
            engine_params_group_layout.setContentsMargins(0, 0, 0, 0)
            engine_params_group_layout.setSpacing(0)
            copy_paste_top = tabs_layout_config.get('spacing_before_copy_paste', 12)
            try:
                copy_paste_top = int(copy_paste_top)
            except (TypeError, ValueError):
                copy_paste_top = 12
            if copy_paste_top > 0:
                engine_params_group_layout.addSpacing(copy_paste_top)
            # Copy / Paste row at top of engine-specific section
            copy_paste_layout = QHBoxLayout()
            copy_layout_spacing = tabs_layout_config.get('copy_layout_spacing', 10)
            copy_paste_layout.setSpacing(copy_layout_spacing)
            copy_btn = QPushButton()
            copy_btn.setToolTip("Copy engine-specific parameters from this task to paste into another task")
            copy_btn.setAccessibleName("Copy")
            copy_btn.clicked.connect(lambda checked, t=task: self._copy_engine_params(t))
            copy_paste_layout.addWidget(copy_btn)
            paste_btn = QPushButton()
            paste_btn.setToolTip("Paste engine-specific parameters copied from another task")
            paste_btn.setAccessibleName("Paste")
            paste_btn.clicked.connect(lambda checked, t=task: self._paste_engine_params(t))
            paste_btn.setEnabled(False)
            self._paste_buttons.append(paste_btn)
            self._copy_paste_icon_buttons.extend([copy_btn, paste_btn])
            copy_paste_layout.addWidget(paste_btn)
            copy_paste_layout.addStretch()
            engine_params_group_layout.addLayout(copy_paste_layout)
            copy_to_scroll_gap = tabs_layout_config.get('copy_paste_to_scroll_spacing', 10)
            try:
                copy_to_scroll_gap = int(copy_to_scroll_gap)
            except (TypeError, ValueError):
                copy_to_scroll_gap = 10
            if copy_to_scroll_gap > 0:
                engine_params_group_layout.addSpacing(copy_to_scroll_gap)

            # Create scroll area for engine parameters (fixed height from config; see main layout stretch)
            scroll_area_config = dialog_config.get('scroll_area', {})
            raw_scroll_h = scroll_area_config.get('height')
            if raw_scroll_h is None:
                raw_scroll_h = scroll_area_config.get('min_height', 200)
            try:
                scroll_fixed_h = max(80, int(raw_scroll_h))
            except (TypeError, ValueError):
                scroll_fixed_h = 200
            scroll_bg = scroll_area_config.get('background_color', [45, 45, 50])
            
            scroll = QScrollArea()
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setFixedHeight(scroll_fixed_h)
            scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            
            # Apply scrollbar styling using StyleManager
            from app.views.style import StyleManager
            scroll_border = scroll_area_config.get('border_color', [60, 60, 65])
            StyleManager.style_scroll_area(
                scroll,
                self.config,
                scroll_bg,
                scroll_border,
                0,  # No border radius
                include_scroll_area_border=False,
            )
            
            scroll_widget = QWidget()
            scroll_layout = QFormLayout(scroll_widget)
            scroll_layout_spacing = tabs_layout_config.get('scroll_layout_spacing', 10)
            scroll_layout.setSpacing(scroll_layout_spacing)
            # Set field growth policy to make fields expand
            scroll_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            # Labels vertically centered with fields (checkbox rows use min-height matching combos)
            scroll_layout.setLabelAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            scroll_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            scroll_layout_margins = tabs_layout_config.get('scroll_layout_margins', [0, 0, 0, 0])
            scroll_layout.setContentsMargins(
                scroll_layout_margins[0],
                scroll_layout_margins[1],
                scroll_layout_margins[2],
                scroll_layout_margins[3],
            )
            
            # Add widgets for each engine option
            for option in self.engine_options:
                option_name = option.get("name", "")
                option_type = option.get("type", "")
                option_default = option.get("default")
                option_min = option.get("min")
                option_max = option.get("max")
                option_var = option.get("var", [])
                
                if not option_name or not option_type:
                    continue
                
                # Skip button type options - they don't need configuration
                if option_type == "button":
                    continue
                
                # Skip "Threads" - it's already in the common parameters section
                if option_name == "Threads":
                    continue
                
                # Get saved value for this option (if available)
                saved_value = saved_params.get(option_name, option_default)
                
                # Create appropriate widget based on option type
                widget = self._create_option_widget(option_type, saved_value, option_min, option_max, option_var)
                if widget:
                    scroll_layout.addRow(f"{option_name}:", widget)
                    # Store value widget (inner QCheckBox when wrapped) for state read/write
                    stored = getattr(widget, "_engine_option_checkbox", widget)
                    self.task_widgets[task][f"engine_option_{option_name}"] = stored
            
            scroll_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            scroll.setWidget(scroll_widget)
            
            engine_params_group_layout.addWidget(scroll)
            scroll_bottom_spacing = tabs_layout_config.get('scroll_bottom_spacing', 12)
            try:
                scroll_bottom_spacing = int(scroll_bottom_spacing)
            except (TypeError, ValueError):
                scroll_bottom_spacing = 12
            if scroll_bottom_spacing > 0:
                engine_params_group_layout.addSpacing(scroll_bottom_spacing)
            engine_params_group.setLayout(engine_params_group_layout)
            engine_params_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            tab_layout.addWidget(engine_params_group)
        else:
            # No engine options available
            no_options_label = QLabel("No engine-specific parameters available.\nEngine options will be loaded after validation.")
            no_options_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tab_layout.addWidget(no_options_label)
            # Store reference for styling
            if not hasattr(self, '_no_options_labels'):
                self._no_options_labels = []
            self._no_options_labels.append(no_options_label)
        
        # Add tab to tab widget
        self.tab_widget.addTab(tab, task_label)
    
    def _create_option_widget(self, option_type: str, default: Any, min_val: Optional[int], 
                              max_val: Optional[int], var_values: List[str]) -> Optional[Any]:
        """Create a widget for an engine option based on its type.
        
        Args:
            option_type: Type of option (spin, check, combo, string, button).
            default: Default value.
            min_val: Minimum value (for spin).
            max_val: Maximum value (for spin).
            var_values: List of possible values (for combo).
            
        Returns:
            Widget for the option, or None if type is not supported.
        """
        if option_type == "spin":
            line_edit = QLineEdit()
            line_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            # Set up validator with min/max values
            if min_val is not None and max_val is not None:
                line_edit.setValidator(QIntValidator(min_val, max_val))
            elif min_val is not None:
                line_edit.setValidator(QIntValidator(min_val, 2147483647))  # Max int
            elif max_val is not None:
                line_edit.setValidator(QIntValidator(-2147483648, max_val))  # Min int
            if default is not None:
                line_edit.setText(str(int(default)))
            return line_edit
        
        elif option_type == "check":
            check = QCheckBox()
            if default is not None:
                check.setChecked(bool(default))
            # Full-width row + min height so checkboxes align with line edits / combos in QFormLayout
            dialog_cfg = self.config.get("ui", {}).get("dialogs", {}).get("engine_configuration", {})
            fl = dialog_cfg.get("form_layout", {})
            row_min = fl.get("checkbox_row_min_height")
            if row_min is None:
                sp_style = self.config.get("ui", {}).get("styles", {}).get("spinbox", {})
                row_min = sp_style.get("minimum_height", 28)
            wrap = QWidget()
            row = QHBoxLayout(wrap)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            row.addWidget(check, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            row.addStretch(1)
            wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            wrap.setMinimumHeight(int(row_min))
            setattr(wrap, "_engine_option_checkbox", check)
            return wrap
        
        elif option_type == "combo":
            combo = NoWheelComboBox()
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if var_values:
                combo.addItems(var_values)
                if default is not None and str(default) in var_values:
                    combo.setCurrentText(str(default))
            return combo
        
        elif option_type == "string":
            line_edit = QLineEdit()
            line_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if default is not None:
                line_edit.setText(str(default))
            return line_edit
        
        elif option_type == "button":
            # Button options don't have values, they trigger actions
            # For now, we'll skip them or show a label
            label = QLabel("(Button option - no configuration needed)")
            return label
        
        return None
    
    def _get_raw_widget_state(self, task: str) -> Dict[str, Any]:
        """Read current widget values for a task (no parsing). Returns raw strings/bools for controller."""
        raw = {}
        if "threads" in self.task_widgets[task]:
            raw["threads"] = self.task_widgets[task]["threads"].text()
        if "depth" in self.task_widgets[task]:
            raw["depth"] = self.task_widgets[task]["depth"].text()
        if "movetime" in self.task_widgets[task]:
            raw["movetime"] = self.task_widgets[task]["movetime"].text()
        for key, widget in self.task_widgets[task].items():
            if not key.startswith("engine_option_"):
                continue
            option_name = key.replace("engine_option_", "", 1)
            if isinstance(widget, QLineEdit):
                raw[option_name] = widget.text()
            elif isinstance(widget, QCheckBox):
                raw[option_name] = widget.isChecked()
            elif isinstance(widget, QComboBox):
                raw[option_name] = widget.currentText()
        return raw

    def _apply_params_to_task_widgets(self, task: str, params: Dict[str, Any]) -> None:
        """Apply a parameter dict to the task's widgets (common + engine options)."""
        if "threads" in self.task_widgets[task] and "threads" in params:
            self.task_widgets[task]["threads"].setText(str(params["threads"]))
        if "depth" in self.task_widgets[task] and "depth" in params:
            self.task_widgets[task]["depth"].setText(str(params["depth"]))
        if "movetime" in self.task_widgets[task] and "movetime" in params:
            self.task_widgets[task]["movetime"].setText(str(params["movetime"]))
        for option_name, value in params.items():
            if option_name in ("threads", "depth", "movetime"):
                continue
            key = f"engine_option_{option_name}"
            if key not in self.task_widgets[task]:
                continue
            widget = self.task_widgets[task][key]
            if isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                if str(value) in [widget.itemText(i) for i in range(widget.count())]:
                    widget.setCurrentText(str(value))
                elif widget.count() > 0:
                    widget.setCurrentIndex(0)

    def _apply_engine_params_to_task_widgets(self, task: str, params: Dict[str, Any]) -> None:
        """Apply only engine-specific parameters to the task's widgets."""
        for option_name, value in params.items():
            key = f"engine_option_{option_name}"
            if key not in self.task_widgets[task]:
                continue
            widget = self.task_widgets[task][key]
            if isinstance(widget, QLineEdit):
                widget.setText(str(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QComboBox):
                if str(value) in [widget.itemText(i) for i in range(widget.count())]:
                    widget.setCurrentText(str(value))

    def _update_paste_buttons_enabled(self, enabled: bool) -> None:
        """Enable or disable all Paste buttons."""
        for btn in self._paste_buttons:
            btn.setEnabled(enabled)

    def _copy_engine_params(self, task: str) -> None:
        """Copy engine-specific parameters from the current task into the controller clipboard."""
        raw = self._get_raw_widget_state(task)
        engine_names = self.controller.get_engine_param_names()
        clip = {k: raw[k] for k in engine_names if k in raw}
        self.controller.set_engine_params_clipboard(clip)
        self.controller.notify_copy_engine_params()
        self._update_paste_buttons_enabled(True)

    def _paste_engine_params(self, task: str) -> None:
        """Paste engine-specific parameters from the controller clipboard into the current task."""
        clipboard = self.controller.get_engine_params_clipboard()
        if not clipboard:
            from app.views.dialogs.message_dialog import MessageDialog
            MessageDialog.show_info(
                self.config,
                "Nothing to Paste",
                "Copy engine-specific parameters from another task first.",
                self
            )
            return
        self._apply_engine_params_to_task_widgets(task, clipboard)
        self.controller.notify_paste_engine_params()

    def _on_reset_clicked(self) -> None:
        """Reset all parameters to defaults for all three tasks (controller handles logic)."""
        success, refreshed_options, status_message = self.controller.reset_to_defaults(self.TASK_EVALUATION)
        QApplication.processEvents()
        err_dialog = self.controller.get_reset_error_dialog(success, status_message)
        if err_dialog:
            from app.views.dialogs.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, err_dialog[0], err_dialog[1], self)
            if not refreshed_options:
                return
        if refreshed_options:
            self.engine_options = refreshed_options
        for task in self._task_order:
            params = self.controller.get_defaults_for_task(task)
            self._apply_params_to_task_widgets(task, params)
        QApplication.processEvents()
        self.controller.set_status("All parameters reset to defaults.")

    def _on_ok_clicked(self) -> None:
        """Handle OK button click: collect raw state, parse via controller, validate, save."""
        task_params = {}
        for task in self._task_order:
            raw = self._get_raw_widget_state(task)
            task_params[task] = self.controller.parse_task_parameters_from_ui(raw, task)
        all_validation_results = self.controller.validate_parameters(task_params)
        if self.controller.should_show_validation_dialog(all_validation_results):
            if not self._show_validation_dialog(all_validation_results):
                return
        success, status_message = self.controller.save_parameters(task_params, self.engine.name)
        QApplication.processEvents()
        if success:
            self.accept()
        else:
            from app.views.dialogs.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "Save Error", status_message, self)
    
    def _show_validation_dialog(self, validation_results: Dict[str, Any]) -> bool:
        """Show validation dialog with issues and get user confirmation.
        
        Args:
            validation_results: Dictionary mapping task names to ValidationResult objects.
            
        Returns:
            True if user confirmed to save despite issues, False if user cancelled.
        """
        ValidationSeverity = self.controller.get_validation_severity_enum()
        
        # Get validation dialog config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_configuration', {})
        validation_config = dialog_config.get('validation_dialog', {})
        validation_layout_config = validation_config.get('layout', {})
        validation_title_config = validation_config.get('title', {})
        validation_desc_config = validation_config.get('description', {})
        validation_task_header_config = validation_config.get('task_header', {})
        validation_scroll_config = validation_config.get('scroll_area', {})
        
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Parameter Validation")
        dialog_width = validation_config.get('width', 600)
        dialog_height = validation_config.get('height', 400)
        # Make dialog non-resizable by setting fixed size
        dialog.setFixedSize(dialog_width, dialog_height)
        
        # Set dialog background color
        tabs_config = dialog_config.get('tabs', {})
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        from PyQt6.QtGui import QPalette, QColor
        dialog.setAutoFillBackground(True)
        dialog_palette = dialog.palette()
        dialog_palette.setColor(dialog.backgroundRole(), QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        dialog.setPalette(dialog_palette)
        
        layout = QVBoxLayout(dialog)
        layout_spacing = validation_layout_config.get('spacing', 15)
        layout_margins = validation_layout_config.get('margins', [15, 15, 15, 15])
        layout.setSpacing(layout_spacing)
        layout.setContentsMargins(layout_margins[0], layout_margins[1], layout_margins[2], layout_margins[3])
        
        # Title
        title_font_size = scale_font_size(validation_title_config.get('font_size', 14))
        title_padding = validation_title_config.get('padding', 5)
        title_text_color = validation_title_config.get('text_color', [240, 240, 240])
        title_label = QLabel("<b>Parameter Validation Issues</b>")
        title_label.setStyleSheet(
            f"font-size: {title_font_size}pt; "
            f"padding: {title_padding}px; "
            f"color: rgb({title_text_color[0]}, {title_text_color[1]}, {title_text_color[2]});"
            f"background-color: transparent;"
        )
        # Set palette to prevent macOS override
        title_label_palette = title_label.palette()
        title_label_palette.setColor(title_label.foregroundRole(), QColor(title_text_color[0], title_text_color[1], title_text_color[2]))
        title_label.setPalette(title_label_palette)
        title_label.update()
        layout.addWidget(title_label)
        
        # Description
        desc_font_size = scale_font_size(validation_desc_config.get('font_size', 11))
        desc_padding = validation_desc_config.get('padding', 5)
        desc_text_color = validation_desc_config.get('text_color', [200, 200, 200])
        desc_label = QLabel(
            "The following issues were found with your parameter settings. "
            "You can choose to save anyway or cancel to fix the issues."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(
            f"font-size: {desc_font_size}pt; "
            f"padding: {desc_padding}px; "
            f"color: rgb({desc_text_color[0]}, {desc_text_color[1]}, {desc_text_color[2]});"
        )
        layout.addWidget(desc_label)
        
        # Scroll area for issues
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll_min_height = validation_scroll_config.get('min_height', 250)
        # Fix white background - use scroll_area background_color from main dialog config
        scroll_area_config = dialog_config.get('scroll_area', {})
        scroll_bg = scroll_area_config.get('background_color', [45, 45, 50])
        # Get border color from dialog config (use a default if not available)
        scroll_border = scroll_area_config.get('border_color', [60, 60, 65])
        
        # Apply scrollbar styling using StyleManager
        from app.views.style import StyleManager
        StyleManager.style_scroll_area(
            scroll,
            self.config,
            scroll_bg,
            scroll_border,
            0,  # No border radius for validation dialog
            include_scroll_area_border=False,
        )
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(10)
        
        # Task names for display
        task_names = {
            self.TASK_EVALUATION: "Evaluation",
            self.TASK_GAME_ANALYSIS: "Game Analysis",
            self.TASK_MANUAL_ANALYSIS: "Manual Analysis",
            self.TASK_BRILLIANCY_DETECTION: "Brilliancy Detection",
        }
        
        # Add issues for each task
        for task, result in validation_results.items():
            if not result.issues:
                continue
            
            # Task header
            task_header_font_size = scale_font_size(validation_task_header_config.get('font_size', 12))
            task_header_padding = validation_task_header_config.get('padding', 5)
            task_header_text_color = validation_task_header_config.get('text_color', [220, 220, 220])
            task_label = QLabel(f"<b>{task_names[task]}</b>")
            task_label.setStyleSheet(
                f"font-size: {task_header_font_size}pt; "
                f"padding: {task_header_padding}px; "
                f"color: rgb({task_header_text_color[0]}, {task_header_text_color[1]}, {task_header_text_color[2]});"
            )
            scroll_layout.addWidget(task_label)
            
            # Group issues by severity
            errors = [issue for issue in result.issues if issue.severity == ValidationSeverity.ERROR]
            warnings = [issue for issue in result.issues if issue.severity == ValidationSeverity.WARNING]
            infos = [issue for issue in result.issues if issue.severity == ValidationSeverity.INFO]
            
            # Show errors
            for issue in errors:
                issue_widget = self._create_issue_widget(issue, "error")
                scroll_layout.addWidget(issue_widget)
            
            # Show warnings
            for issue in warnings:
                issue_widget = self._create_issue_widget(issue, "warning")
                scroll_layout.addWidget(issue_widget)
            
            # Show info
            for issue in infos:
                issue_widget = self._create_issue_widget(issue, "info")
                scroll_layout.addWidget(issue_widget)
            
            # Add spacing after task
            scroll_layout.addSpacing(10)
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        # Set minimum height for scroll area
        scroll.setMinimumHeight(scroll_min_height)
        # Add scroll area with stretch factor so buttons don't intersect
        layout.addWidget(scroll, stretch=1)
        
        # Buttons (use same styling as main dialog)
        buttons_config = dialog_config.get('buttons', {})
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        
        # Get colors for button styling (match other dialogs: base on dialog bg/border)
        tabs_config = dialog_config.get('tabs', {})
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        bg_color = dialog_config.get('background_color', pane_bg)
        border_color = dialog_config.get('border_color', buttons_config.get('border_color', [60, 60, 65]))
        bg_color_list = [bg_color[0], bg_color[1], bg_color[2]]
        border_color_list = [border_color[0], border_color[1], border_color[2]]
        
        # Apply button styling using StyleManager (uses unified config)
        from app.views.style import StyleManager
        
        button_layout = QHBoxLayout()
        button_spacing = buttons_config.get('spacing', 10)
        button_layout.setSpacing(button_spacing)
        button_layout.addStretch()
        
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(dialog.reject)
        button_layout.addWidget(cancel_button)
        
        save_button = QPushButton("Save Anyway")
        save_button.clicked.connect(dialog.accept)
        button_layout.addWidget(save_button)
        
        # Style both buttons using StyleManager
        StyleManager.style_buttons(
            [cancel_button, save_button],
            self.config,
            bg_color_list,
            border_color_list,
            min_width=button_width,
            min_height=button_height
        )
        
        layout.addLayout(button_layout)
        
        # Show dialog and return result
        return dialog.exec() == QDialog.DialogCode.Accepted
    
    def _create_issue_widget(self, issue, severity: str) -> QWidget:
        """Create a widget to display a validation issue.
        
        Args:
            issue: ValidationIssue object.
            severity: Severity level ("error", "warning", "info").
            
        Returns:
            QWidget displaying the issue.
        """
        # Get validation dialog config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_configuration', {})
        validation_config = dialog_config.get('validation_dialog', {})
        issue_widget_config = validation_config.get('issue_widget', {})
        severity_labels_config = validation_config.get('severity_labels', {})
        issue_message_config = validation_config.get('issue_message', {})
        
        widget = QWidget()
        layout = QHBoxLayout(widget)
        issue_margins = issue_widget_config.get('margins', [10, 5, 10, 5])
        issue_spacing = issue_widget_config.get('spacing', 10)
        layout.setContentsMargins(issue_margins[0], issue_margins[1], issue_margins[2], issue_margins[3])
        layout.setSpacing(issue_spacing)
        
        # Severity icon/color
        severity_colors_config = severity_labels_config.get('colors', {})
        severity_colors = {
            "error": severity_colors_config.get('error', [255, 100, 100]),
            "warning": severity_colors_config.get('warning', [255, 200, 100]),
            "info": severity_colors_config.get('info', [150, 200, 255])
        }
        severity_labels_text = {
            "error": "ERROR",
            "warning": "WARNING",
            "info": "INFO"
        }
        
        severity_width = severity_labels_config.get('width', 80)
        severity_font_size = scale_font_size(severity_labels_config.get('font_size', 10))
        severity_padding = severity_labels_config.get('padding', [2, 8])
        severity_border_radius = severity_labels_config.get('border_radius', 3)
        
        severity_label = QLabel(severity_labels_text[severity])
        severity_color = severity_colors[severity]
        severity_label.setStyleSheet(
            f"background-color: rgb({severity_color[0]}, {severity_color[1]}, {severity_color[2]}); "
            f"color: rgb(0, 0, 0); "
            f"padding: {severity_padding[0]}px {severity_padding[1]}px; "
            f"border-radius: {severity_border_radius}px; "
            f"font-weight: bold; "
            f"font-size: {severity_font_size}pt;"
        )
        severity_label.setFixedWidth(severity_width)
        severity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(severity_label)
        
        # Issue message
        message_font_size = scale_font_size(issue_message_config.get('font_size', 11))
        message_padding = issue_message_config.get('padding', 2)
        message_text_color = issue_message_config.get('text_color', [200, 200, 200])
        message_label = QLabel(issue.message)
        message_label.setWordWrap(True)
        message_label.setStyleSheet(
            f"font-size: {message_font_size}pt; "
            f"padding: {message_padding}px; "
            f"color: rgb({message_text_color[0]}, {message_text_color[1]}, {message_text_color[2]});"
        )
        layout.addWidget(message_label, stretch=1)
        
        return widget

    def _apply_engine_info_path_style(self, dialog_config: Dict[str, Any]) -> None:
        """Path line: same pattern as BulkReplaceDialog — setFont in _setup_ui; stylesheet color only.

        Setting font-size/family in QSS can fight setFont on Windows/DPI and make the path look tiny.
        """
        header_config = dialog_config.get('header', {})
        header_text = header_config.get('text_color', [51, 51, 51])
        path_opacity = float(header_config.get('path_opacity', 0.7))
        tr, tg, tb = header_text[0], header_text[1], header_text[2]
        bg_rgb = dialog_config.get('background_color', [255, 255, 255])
        br, bgr, bb = bg_rgb[0], bg_rgb[1], bg_rgb[2]
        t = path_opacity
        pr = int(tr * t + br * (1.0 - t))
        pg = int(tg * t + bgr * (1.0 - t))
        pb = int(tb * t + bb * (1.0 - t))
        self._engine_path_label.setStyleSheet(
            f'color: rgb({pr}, {pg}, {pb});'
        )

    def _apply_styling(self) -> None:
        """Apply styling to UI elements based on configuration."""
        ui_config = self.config.get('ui', {})
        dialog_config = ui_config.get('dialogs', {}).get('engine_configuration', {})
        
        # Header: first row uses palette only (stylesheets would reset font). Path uses _apply_engine_info_path_style.
        header_config = dialog_config.get('header', {})
        header_text = header_config.get('text_color', [51, 51, 51])
        tr, tg, tb = header_text[0], header_text[1], header_text[2]
        from PyQt6.QtGui import QPalette, QColor

        title_color = QColor(tr, tg, tb)
        for w in (self._engine_label_prefix, self._engine_name_label):
            pal = w.palette()
            pal.setColor(QPalette.ColorRole.WindowText, title_color)
            w.setPalette(pal)

        self._apply_engine_info_path_style(dialog_config)
        
        # Tab widget styling (aligned with DetailPanel._apply_tab_styling)
        tabs_config = dialog_config.get('tabs', {})
        tab_font_family = resolve_font_family(tabs_config.get('font_family', 'Helvetica Neue'))
        tab_font_size = scale_font_size(tabs_config.get('font_size', 10))
        tab_font_weight = tabs_config.get('font_weight', None)
        selected_tab_font_weight = tabs_config.get('selected_font_weight', 500)
        tab_height = tabs_config.get('tab_height', 24)
        pane_bg = tabs_config.get('pane_background', [255, 255, 255])
        colors_config = tabs_config.get('colors', {})
        
        normal = colors_config.get('normal', {})
        norm_bg = normal.get('background', [245, 245, 245])
        norm_text = normal.get('text', [51, 51, 51])
        norm_border = normal.get('border', [204, 204, 204])
        
        hover = colors_config.get('hover', {})
        hover_bg = hover.get('background', [235, 235, 235])
        hover_text = hover.get('text', [51, 51, 51])
        hover_border = hover.get('border', [180, 180, 180])
        
        active = colors_config.get('active', {})
        active_bg = active.get('background', [70, 90, 130])
        active_text = active.get('text', [255, 255, 255])
        active_border = active.get('border', [100, 120, 160])
        
        tab_weight_css = (
            f"font-weight: {int(tab_font_weight)};"
            if tab_font_weight is not None
            else ""
        )
        
        # Scroll button color
        scroll_button_color = tabs_config.get('scroll_button_color', [30, 30, 30])
        
        # Horizontal rule under the tab row (grounds tabs when pane has no full border)
        sep_cfg = tabs_config.get('pane_separator') or {}
        sep_width = sep_cfg.get('width', 1)
        sep_color = sep_cfg.get('color')
        if sep_color is None:
            sep_color = norm_border
        if sep_width and sep_width > 0:
            pane_top_rule = (
                f"border-top: {int(sep_width)}px solid "
                f"rgb({sep_color[0]}, {sep_color[1]}, {sep_color[2]});"
            )
        else:
            pane_top_rule = ""
        
        tab_stylesheet = f"""
            QTabWidget {{
                background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
            }}
            QTabWidget::pane {{
                border: none;
                {pane_top_rule}
                background-color: rgb({pane_bg[0]}, {pane_bg[1]}, {pane_bg[2]});
            }}
            QTabWidget::tab-bar {{
                alignment: left;
            }}
            QTabBar::tab {{
                background-color: rgb({norm_bg[0]}, {norm_bg[1]}, {norm_bg[2]});
                color: rgb({norm_text[0]}, {norm_text[1]}, {norm_text[2]});
                border: 1px solid rgb({norm_border[0]}, {norm_border[1]}, {norm_border[2]});
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                padding: 6px 12px;
                min-width: 80px;
                height: {tab_height}px;
                font-family: "{tab_font_family}";
                font-size: {tab_font_size}pt;
                {tab_weight_css}
                margin-right: 2px;
            }}
            QTabBar::tab:hover {{
                background-color: rgb({hover_bg[0]}, {hover_bg[1]}, {hover_bg[2]});
                color: rgb({hover_text[0]}, {hover_text[1]}, {hover_text[2]});
                border-color: rgb({hover_border[0]}, {hover_border[1]}, {hover_border[2]});
            }}
            QTabBar::tab:selected {{
                background-color: rgb({active_bg[0]}, {active_bg[1]}, {active_bg[2]});
                color: rgb({active_text[0]}, {active_text[1]}, {active_text[2]});
                border-color: rgb({active_border[0]}, {active_border[1]}, {active_border[2]});
                font-weight: {int(selected_tab_font_weight)};
            }}
            QTabBar::tab:focus {{
                outline: none;
            }}
            QTabBar::tab:!selected {{
                margin-top: 2px;
            }}
            QTabBar::tab:first:selected {{
                margin-left: 0px;
            }}
            QTabBar::tab:last:selected {{
                margin-right: 0px;
            }}
            QTabBar QToolButton {{
                background-color: rgb({scroll_button_color[0]}, {scroll_button_color[1]}, {scroll_button_color[2]});
                border: none;
            }}
            
            QTabBar QToolButton:hover {{
                background-color: rgb({scroll_button_color[0]}, {scroll_button_color[1]}, {scroll_button_color[2]});
            }}
            
            QTabBar QToolButton:pressed {{
                background-color: rgb({scroll_button_color[0]}, {scroll_button_color[1]}, {scroll_button_color[2]});
            }}
        """
        self.tab_widget.setStyleSheet(tab_stylesheet)
        
        # Group boxes, tab chrome, inputs (after main dialog buttons exist — not during _setup_ui)
        self._configure_tab_bar()
        
        buttons_config = dialog_config.get('buttons', {})
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        tabs_cfg = dialog_config.get('tabs', {})
        pane_bg_btn = tabs_cfg.get('pane_background', [40, 40, 45])
        bg_color = dialog_config.get('background_color', pane_bg_btn)
        border_color = dialog_config.get('border_color', buttons_config.get('border_color', [60, 60, 65]))
        bg_color_list = [bg_color[0], bg_color[1], bg_color[2]]
        border_color_list = [border_color[0], border_color[1], border_color[2]]
        from app.views.style import StyleManager
        
        # Main actions: full-width text buttons. Copy/Paste: icon-only (same SVGs as Edit menu).
        main_action_buttons = [self.reset_button, self.cancel_button, self.ok_button]
        StyleManager.style_buttons(
            main_action_buttons,
            self.config,
            bg_color_list,
            border_color_list,
            min_width=button_width,
            min_height=button_height,
        )
        if self._copy_paste_icon_buttons:
            StyleManager.style_buttons(
                self._copy_paste_icon_buttons,
                self.config,
                bg_color_list,
                border_color_list,
                min_width=None,
                min_height=button_height,
            )
            labels_tc = dialog_config.get('labels', {}).get('text_color', [200, 200, 200])
            if not isinstance(labels_tc, (list, tuple)) or len(labels_tc) < 3:
                labels_tc = [200, 200, 200]
            tint = (int(labels_tc[0]), int(labels_tc[1]), int(labels_tc[2]))
            icon_px = max(16, min(22, button_height - 8))
            for i, btn in enumerate(self._copy_paste_icon_buttons):
                svg_path = SVG_MENU_COPY if i % 2 == 0 else SVG_MENU_PASTE_CLIPBOARD
                btn.setIcon(themed_icon_from_svg(svg_path, tint))
                btn.setText('')
                btn.setIconSize(QSize(icon_px, icon_px))
                btn.setFixedSize(button_height, button_height)
    
    def _configure_tab_bar(self) -> None:
        """Configure QTabBar for macOS compatibility (left-aligned, content-sized tabs)."""
        from PyQt6.QtGui import QPalette, QColor
        
        tab_bar = self.tab_widget.tabBar()
        tab_bar.setExpanding(False)  # Allow tabs to size to content instead of filling space
        tab_bar.setElideMode(Qt.TextElideMode.ElideNone)  # Prevent text truncation
        tab_bar.setUsesScrollButtons(True)  # Enable scroll buttons when tabs don't fit
        tab_bar.setDrawBase(False)  # Don't draw base line
        
        # Get pane background color from config
        ui_config = self.config.get('ui', {})
        dialog_config = ui_config.get('dialogs', {}).get('engine_configuration', {})
        tabs_config = dialog_config.get('tabs', {})
        pane_bg = tabs_config.get('pane_background', [255, 255, 255])
        
        # Set background color directly on tab widgets (QWidget) to ensure dark background
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            # Use setAutoFillBackground and palette to ensure background is applied
            tab.setAutoFillBackground(True)
            palette = tab.palette()
            palette.setColor(tab.backgroundRole(), QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
            palette.setColor(QPalette.ColorRole.Window, QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
            palette.setColor(QPalette.ColorRole.Base, QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
            tab.setPalette(palette)
            
            # Also set background on the tab's layout if it exists
            # Note: Don't override margins here - they're set in _create_task_tab for proper padding
            if tab.layout():
                pass  # Margins are already set in _create_task_tab
        
        # Also ensure the tab widget's pane has the correct background
        self.tab_widget.setAutoFillBackground(True)
        tab_widget_palette = self.tab_widget.palette()
        tab_widget_palette.setColor(self.tab_widget.backgroundRole(), QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        tab_widget_palette.setColor(QPalette.ColorRole.Window, QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        tab_widget_palette.setColor(QPalette.ColorRole.Base, QColor(pane_bg[0], pane_bg[1], pane_bg[2]))
        self.tab_widget.setPalette(tab_widget_palette)
        
        # Group box styling
        groups_config = dialog_config.get('groups', {})
        group_bg = groups_config.get('background_color')  # None = use unified default
        group_border = groups_config.get('border_color', [60, 60, 65])
        group_border_width = groups_config.get('border_width', 1)
        group_border_radius = groups_config.get('border_radius', 5)
        group_title_font_family_raw = groups_config.get('title_font_family')
        from app.utils.font_utils import resolve_font_family
        group_title_font_family = resolve_font_family(group_title_font_family_raw)
        group_title_font_size = scale_font_size(groups_config.get('title_font_size', 11))
        group_title_font_weight = groups_config.get('title_font_weight', 'bold')
        group_title_color = groups_config.get('title_color')
        group_spacing = groups_config.get('spacing', 10)
        group_margin_top = groups_config.get('margin_top', 8)
        group_padding_top = groups_config.get('padding_top', 12)
        group_content_margins = groups_config.get('content_margins', [10, 20, 10, 15])
        group_title_left = groups_config.get('title_left', 10)  # Standard left offset
        # Convert from fixed "0 4px" to array format [0, 4] (Pattern 1)
        group_title_padding = [0, 4]
        
        # Collect all group boxes from all tabs
        group_boxes = []
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            group_boxes.extend(tab.findChildren(QGroupBox))
        
        if group_boxes:
            from app.views.style import StyleManager
            StyleManager.style_group_boxes(
                group_boxes,
                self.config,
                border_color=group_border,
                border_width=group_border_width,
                border_radius=group_border_radius,
                bg_color=group_bg,
                margin_top=group_margin_top,
                padding_top=group_padding_top,
                title_font_family=group_title_font_family,
                title_font_size=group_title_font_size,
                title_font_weight=group_title_font_weight,
                title_color=group_title_color,
                title_left=group_title_left,
                title_padding=group_title_padding,
                content_margins=group_content_margins
            )
            # Reduce top spacing for specific groups that need denser content placement.
            left, right, bottom = group_content_margins[0], group_content_margins[2], group_content_margins[3]
            common_params_content_top = groups_config.get('common_params_content_margin_top', 6)
            engine_params_content_top = groups_config.get('engine_params_content_margin_top', 2)
            for group_box in group_boxes:
                layout = group_box.layout()
                if not layout:
                    continue
                if group_box.title() == "Common Parameters":
                    layout.setContentsMargins(left, common_params_content_top, right, bottom)
                elif group_box.title() == "Engine-Specific Parameters":
                    layout.setContentsMargins(left, engine_params_content_top, right, bottom)
            # Force layout recalculation by accessing layout properties
            # This ensures margins are properly applied and spacing is consistent across tabs
            for group_box in group_boxes:
                layout = group_box.layout()
                if layout:
                    # Access margins to force layout calculation (similar to debug code)
                    _ = layout.getContentsMargins()
                    # Access size hints to force geometry calculation
                    _ = group_box.sizeHint()
                    _ = group_box.size()
        
        # Labels styling
        labels_config = dialog_config.get('labels', {})
        label_font_family = labels_config.get('font_family', 'Helvetica Neue')
        label_font_size = scale_font_size(labels_config.get('font_size', 10))
        form_label_font_size = scale_font_size(labels_config.get('form_label_font_size', labels_config.get('font_size', 10)))
        label_text_color = labels_config.get('text_color', [200, 200, 200])
        label_disabled_color = labels_config.get('disabled_color', [128, 128, 128])
        label_empty_color = labels_config.get('empty_label_color', [128, 128, 128])
        label_empty_font_style = labels_config.get('empty_label_font_style', 'italic')
        label_empty_padding = labels_config.get('empty_label_padding', [20, 20, 20, 20])
        
        # Apply label styling - need to apply to all labels including form labels
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            for label in tab.findChildren(QLabel):
                # Skip if it's a no_options_label (will be styled separately)
                if hasattr(self, '_no_options_labels') and label in self._no_options_labels:
                    continue
                
                # Check if this is a form label (in a QFormLayout)
                is_form_label = label.parent() and isinstance(label.parent().layout(), QFormLayout)
                # Use form_label_font_size for form labels to match input widget font size
                font_size = form_label_font_size if is_form_label else label_font_size
                
                # Apply light text color for labels on dark backgrounds
                label.setStyleSheet(
                    f"font-family: {label_font_family}; "
                    f"font-size: {font_size}pt; "
                    f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
                )
        
        # Style empty options labels if they exist
        if hasattr(self, '_no_options_labels'):
            empty_label_style = (
                f"color: rgb({label_empty_color[0]}, {label_empty_color[1]}, {label_empty_color[2]}); "
                f"padding: {label_empty_padding[0]}px {label_empty_padding[1]}px {label_empty_padding[2]}px {label_empty_padding[3]}px; "
                f"font-style: {label_empty_font_style};"
            )
            for no_options_label in self._no_options_labels:
                no_options_label.setStyleSheet(empty_label_style)
        
        # Form layout spacing
        form_layout_config = dialog_config.get('form_layout', {})
        form_spacing = form_layout_config.get('spacing', 10)
        label_min_width = form_layout_config.get('label_minimum_width', 100)
        
        # Apply form layout spacing
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            for form_layout in tab.findChildren(QFormLayout):
                form_layout.setSpacing(form_spacing)
            # Set label minimum width
            for label in tab.findChildren(QLabel):
                if label.parent() and isinstance(label.parent().layout(), QFormLayout):
                    label.setMinimumWidth(label_min_width)
        
        # Input widgets: QLineEdit / QComboBox use ui.styles via StyleManager (same as Import Games et al.).
        # Checkboxes still need explicit colors (StyleManager.style_checkboxes has no unified-defaults path).
        input_config = dialog_config.get('input_widgets', {})
        input_bg = input_config.get('background_color', [45, 45, 50])
        input_border = input_config.get('border_color', [60, 60, 65])
        app_root = Path(__file__).resolve().parents[2]
        checkmark_path = app_root / "resources" / "icons" / "checkmark.svg"
        checkbox_font_family = resolve_font_family(label_font_family)
        
        from app.views.style import StyleManager
        
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            
            combo_inner_line_edits = set()
            for cb in tab.findChildren(QComboBox):
                inner = cb.lineEdit()
                if inner is not None:
                    combo_inner_line_edits.add(inner)
            line_edits = [
                le for le in tab.findChildren(QLineEdit) if le not in combo_inner_line_edits
            ]
            if line_edits:
                StyleManager.style_line_edits(line_edits, self.config)
            
            comboboxes = tab.findChildren(QComboBox)
            if comboboxes:
                StyleManager.style_comboboxes(comboboxes, self.config, editable=True)
            
            checkboxes = tab.findChildren(QCheckBox)
            if checkboxes:
                StyleManager.style_checkboxes(
                    checkboxes,
                    self.config,
                    label_text_color,
                    checkbox_font_family,
                    label_font_size,
                    input_bg,
                    input_border,
                    checkmark_path,
                )
        
        # Window chrome: same as BulkReplaceDialog (dialogs.*.background_color), not tab pane color
        tabs_config = dialog_config.get('tabs', {})
        pane_bg = tabs_config.get('pane_background', [40, 40, 45])
        dialog_chrome_bg = dialog_config.get('background_color', pane_bg)
        from PyQt6.QtGui import QPalette, QColor
        palette = self.palette()
        palette.setColor(
            self.backgroundRole(),
            QColor(dialog_chrome_bg[0], dialog_chrome_bg[1], dialog_chrome_bg[2]),
        )
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        
        # Also set stylesheet to ensure background color covers the entire window including frame
        dialog_stylesheet = f"""
            QDialog {{
                background-color: rgb({dialog_chrome_bg[0]}, {dialog_chrome_bg[1]}, {dialog_chrome_bg[2]});
            }}
        """
        # Append to existing stylesheet if any, otherwise set it
        current_stylesheet = self.styleSheet()
        if current_stylesheet:
            self.setStyleSheet(current_stylesheet + "\n" + dialog_stylesheet)
        else:
            self.setStyleSheet(dialog_stylesheet)

