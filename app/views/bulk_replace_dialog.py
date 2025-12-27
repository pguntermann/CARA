"""Bulk replace dialog for database operations."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QPushButton,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QSizePolicy,
    QWidget,
    QScrollArea,
    QGridLayout,
    QFrame,
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QPalette, QColor, QFont, QShowEvent
from typing import Optional, Dict, Any, List

from app.controllers.bulk_replace_controller import BulkReplaceController
from app.models.database_model import DatabaseModel


class BulkReplaceDialog(QDialog):
    """Dialog for bulk replacement operations on databases."""
    
    # Standard PGN tags - ordered by importance/commonality
    STANDARD_TAGS = [
        "White", "Black", "Result", "Date", "Event", "Site", "Round",
        "ECO", "WhiteElo", "BlackElo", "TimeControl", "WhiteTitle",
        "BlackTitle", "WhiteFideId", "BlackFideId", "WhiteTeam", "BlackTeam",
        "PlyCount", "EventDate", "Termination", "Annotator", "UTCTime"
    ]
    
    # Important/common tags that should appear first (even if less frequent)
    IMPORTANT_TAGS = ["White", "Black", "Result", "Date", "Event", "Site", "Round", "ECO"]
    
    def __init__(self, config: Dict[str, Any], bulk_replace_controller: BulkReplaceController,
                 database: Optional[DatabaseModel], parent=None) -> None:
        """Initialize the bulk replace dialog.
        
        Args:
            config: Configuration dictionary.
            bulk_replace_controller: BulkReplaceController instance.
            database: Optional DatabaseModel instance (active database).
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.controller = bulk_replace_controller
        self.database = database
        
        # Store fixed size
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_replace', {})
        width = dialog_config.get('width', 600)
        height = dialog_config.get('height', 680)
        self._fixed_size = QSize(width, height)
        
        # Set fixed size
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        # Track operation state
        self._operation_in_progress = False
        
        self._load_config()
        self._setup_ui()
        self._apply_styling()
        self.setWindowTitle("Bulk Replace")
    
    def _load_config(self) -> None:
        """Load configuration values from config.json."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_replace", {})
        
        # Dialog dimensions
        self.dialog_width = dialog_config.get("width", 600)
        self.dialog_height = dialog_config.get("height", 900)
        
        # Background color
        bg_color = dialog_config.get("background_color", [40, 40, 45])
        self.bg_color = QColor(bg_color[0], bg_color[1], bg_color[2])
        
        # Text color
        text_color = dialog_config.get("text_color", [200, 200, 200])
        self.text_color = QColor(text_color[0], text_color[1], text_color[2])
        
        # Font
        from app.utils.font_utils import scale_font_size
        font_size = scale_font_size(dialog_config.get("font_size", 11))
        self.font_family = dialog_config.get("font_family", "Helvetica Neue")
        self.font_size = font_size
        
        # Layout
        layout_config = dialog_config.get("layout", {})
        self.layout_margins = layout_config.get("margins", [25, 25, 25, 25])
        self.layout_spacing = layout_config.get("spacing", 15)
        
        # Spacing
        spacing_config = dialog_config.get("spacing", {})
        self.section_spacing = spacing_config.get("section", 15)
        self.form_spacing = spacing_config.get("form", 15)
        self.options_spacing = spacing_config.get("options", 15)
        self.result_spacing = spacing_config.get("result", 8)
        
        # Buttons
        buttons_config = dialog_config.get("buttons", {})
        self.button_width = buttons_config.get("width", 120)
        self.button_height = buttons_config.get("height", 30)
        self.button_spacing = buttons_config.get("spacing", 10)
        
        # Inputs
        inputs_config = dialog_config.get("inputs", {})
        from app.utils.font_utils import resolve_font_family
        input_font_family_raw = inputs_config.get("font_family", "Cascadia Mono")
        self.input_font_family = resolve_font_family(input_font_family_raw)
        self.input_font_size = scale_font_size(inputs_config.get("font_size", 11))
        self.input_text_color = QColor(*inputs_config.get("text_color", [240, 240, 240]))
        self.input_bg_color = QColor(*inputs_config.get("background_color", [30, 30, 35]))
        self.input_border_color = QColor(*inputs_config.get("border_color", [60, 60, 65]))
        self.input_border_radius = inputs_config.get("border_radius", 3)
        self.input_padding = inputs_config.get("padding", [8, 6])
        self.input_minimum_width = inputs_config.get("minimum_width", 200)
        self.input_minimum_height = inputs_config.get("minimum_height", 30)
        
        # Labels
        labels_config = dialog_config.get("labels", {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
        self.label_font_family = resolve_font_family(labels_config.get("font_family", "Helvetica Neue"))
        self.label_font_size = int(scale_font_size(labels_config.get("font_size", 11)))
        self.label_text_color = QColor(*labels_config.get("text_color", [200, 200, 200]))
        self.label_note_font_size = int(scale_font_size(labels_config.get("note_font_size", 10)))
        self.label_minimum_width = labels_config.get("minimum_width", 90)
        
        # Checkboxes
        checkboxes_config = dialog_config.get("checkboxes", {})
        self.checkbox_spacing = checkboxes_config.get("spacing", 5)
        indicator_config = checkboxes_config.get("indicator", {})
        self.checkbox_indicator_width = indicator_config.get("width", 16)
        self.checkbox_indicator_height = indicator_config.get("height", 16)
        self.checkbox_indicator_border_radius = indicator_config.get("border_radius", 3)
        checked_config = checkboxes_config.get("checked", {})
        self.checkbox_checked_bg_color = QColor(*checked_config.get("background_color", [70, 90, 130]))
        self.checkbox_checked_border_color = QColor(*checked_config.get("border_color", [100, 120, 160]))
        self.checkbox_hover_border_offset = checkboxes_config.get("hover_border_offset", 20)
        
        # Tags list
        tags_list_config = dialog_config.get("tags_list", {})
        self.tags_list_height = tags_list_config.get("height", 180)
        self.tags_list_columns = tags_list_config.get("columns", 2)
        self.tags_list_spacing = tags_list_config.get("spacing", 8)
        self.tags_list_row_spacing = tags_list_config.get("row_spacing", 4)
        self.tags_list_margins = tags_list_config.get("margins", [10, 6, 8, 10])
        
        # Quick select buttons
        quick_select_config = dialog_config.get("quick_select_buttons", {})
        self.quick_select_enabled = quick_select_config.get("enabled", True)
        self.quick_select_spacing = quick_select_config.get("spacing", 8)
        self.quick_select_width = quick_select_config.get("width", 100)
        self.quick_select_height = quick_select_config.get("height", 24)
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(self.layout_spacing)
        main_layout.setContentsMargins(
            self.layout_margins[0],
            self.layout_margins[1],
            self.layout_margins[2],
            self.layout_margins[3]
        )
        
        # Target Database section - label and name on same line, path below
        db_container = QWidget()
        db_container_layout = QVBoxLayout(db_container)
        db_container_layout.setContentsMargins(0, 0, 0, 0)
        db_container_layout.setSpacing(2)
        
        # Horizontal layout for label and name
        db_header_layout = QHBoxLayout()
        db_header_layout.setContentsMargins(0, 0, 0, 0)
        db_header_layout.setSpacing(8)
        
        db_label = QLabel("Target Database:")
        db_label.setFont(QFont(self.label_font_family, self.label_font_size))
        db_header_layout.addWidget(db_label)
        
        # Get database name and path
        db_name = "Clipboard"
        db_path = None
        if self.database:
            # Get database info from panel model
            panel_model = self.controller.database_controller.get_panel_model()
            identifier = panel_model.find_database_by_model(self.database)
            if identifier and identifier != "clipboard":
                from pathlib import Path
                db_path = identifier
                db_name = Path(identifier).stem
            else:
                db_name = "Clipboard"
        
        self.db_name_label = QLabel(f"<b>{db_name}</b>")
        self.db_name_label.setFont(QFont(self.label_font_family, self.label_font_size))
        db_header_layout.addWidget(self.db_name_label)
        db_header_layout.addStretch()
        
        db_container_layout.addLayout(db_header_layout)
        
        # Path label (smaller font, below name, aligned with database name)
        if db_path:
            # Create a horizontal layout to align path with database name
            path_layout = QHBoxLayout()
            path_layout.setContentsMargins(0, 0, 0, 0)
            path_layout.setSpacing(0)
            
            # Add spacer to match the width of "Target Database:" label + spacing
            # Calculate approximate width: label text width + spacing (8px)
            label_font_metrics = db_label.fontMetrics()
            label_width = label_font_metrics.horizontalAdvance("Target Database:")
            spacer_width = label_width + 8  # label width + spacing
            
            spacer = QWidget()
            spacer.setFixedWidth(spacer_width)
            path_layout.addWidget(spacer)
            
            self.db_path_label = QLabel(db_path)
            # Use smaller font size
            path_font_size = max(8, self.label_font_size - 2)
            self.db_path_label.setFont(QFont(self.label_font_family, path_font_size))
            # Make path text lighter/more subtle
            path_text_color = self.text_color
            self.db_path_label.setStyleSheet(
                f"color: rgb({path_text_color.red()}, {path_text_color.green()}, {path_text_color.blue()});"
                f"opacity: 0.7;"
            )
            path_layout.addWidget(self.db_path_label)
            path_layout.addStretch()
            
            # Add path layout to container
            path_widget = QWidget()
            path_widget.setLayout(path_layout)
            db_container_layout.addWidget(path_widget)
        else:
            self.db_path_label = None
        
        main_layout.addWidget(db_container)
        
        main_layout.addSpacing(self.section_spacing)
        
        # Target Games group
        games_group = QGroupBox("Target Games")
        games_layout = QHBoxLayout()
        games_layout.setSpacing(self.section_spacing)
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_replace", {})
        groups_config = dialog_config.get("groups", {})
        games_content_margins = groups_config.get("content_margins", [10, 20, 10, 15])
        games_layout.setContentsMargins(
            games_content_margins[0],
            games_content_margins[1],
            games_content_margins[2],
            games_content_margins[3]
        )
        self.games_button_group = QButtonGroup(self)
        self.all_games_radio = QRadioButton("All games")
        self.selected_games_radio = QRadioButton("Selected games")
        self.games_button_group.addButton(self.all_games_radio, 0)
        self.games_button_group.addButton(self.selected_games_radio, 1)
        self.all_games_radio.setChecked(True)
        games_layout.addWidget(self.all_games_radio)
        games_layout.addWidget(self.selected_games_radio)
        games_layout.addStretch()
        games_group.setLayout(games_layout)
        main_layout.addWidget(games_group)
        
        main_layout.addSpacing(self.section_spacing)
        
        # Metadata Tag Replacement group
        replace_group = QGroupBox("Metadata Tag Replacement")
        replace_layout = QFormLayout()
        replace_layout.setSpacing(self.form_spacing)
        replace_layout.setVerticalSpacing(self.form_spacing)  # Ensure vertical spacing between rows
        replace_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)  # Prevent row wrapping
        # Set field growth policy to make fields expand
        replace_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        # Set alignment for macOS compatibility (left-align labels and form)
        replace_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        replace_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        replace_content_margins = groups_config.get("content_margins", [10, 20, 10, 15])
        replace_layout.setContentsMargins(
            replace_content_margins[0],
            replace_content_margins[1],
            replace_content_margins[2],
            replace_content_margins[3]
        )
        
        # Set fixed label width to prevent layout shifting when "Source tag:" appears
        # Calculate width based on longest label text ("Source tag:" or "Target tags:")
        label_min_width = self.label_minimum_width
        
        # Tags selection (multiple tags with checkboxes)
        self.tag_label = QLabel("Tags:")
        self.tag_label.setFont(QFont(self.label_font_family, self.label_font_size))
        self.tag_label.setMinimumWidth(label_min_width)
        
        # Create container widget for tags section (buttons above scroll area)
        tags_container = QWidget()
        tags_container_layout = QVBoxLayout(tags_container)
        tags_container_layout.setContentsMargins(0, 0, 0, 0)
        tags_container_layout.setSpacing(0)
        # Ensure container has proper size policy and minimum height
        tags_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        # Calculate minimum height for container: buttons (if enabled) + spacing + scroll area height
        # Add extra padding to ensure scroll area and scrollbar are fully visible
        container_min_height = self.tags_list_height + 8  # Add 8px extra for scrollbar clearance
        if self.quick_select_enabled:
            container_min_height += self.quick_select_height + 10  # button height + spacing
        tags_container.setMinimumHeight(container_min_height)
        
        # Quick selection buttons (ABOVE scroll area)
        if self.quick_select_enabled:
            quick_select_layout = QHBoxLayout()
            quick_select_layout.setSpacing(self.quick_select_spacing)
            quick_select_layout.setContentsMargins(0, 0, 0, 0)
            quick_select_layout.addStretch()
            
            self.select_all_button = QPushButton("Select All")
            self.select_all_button.setFixedSize(self.quick_select_width, self.quick_select_height)
            self.select_all_button.clicked.connect(self._on_select_all_clicked)
            quick_select_layout.addWidget(self.select_all_button)
            
            self.deselect_all_button = QPushButton("Deselect All")
            self.deselect_all_button.setFixedSize(self.quick_select_width, self.quick_select_height)
            self.deselect_all_button.clicked.connect(self._on_deselect_all_clicked)
            quick_select_layout.addWidget(self.deselect_all_button)
            
            tags_container_layout.addLayout(quick_select_layout)
            
            # Add explicit spacing between buttons and scroll area
            tags_container_layout.addSpacing(10)
        
        # Create scrollable area for tag checkboxes
        tags_scroll_area = QScrollArea()
        # Remove default frame to prevent white bar on macOS
        tags_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        # Set fixed height - this is the visible height of the scroll area
        # Account for scrollbar width plus frame/border (2px) to prevent clipping
        # Get scrollbar width from global styles config
        styles_config = self.config.get('ui', {}).get('styles', {})
        scrollbar_config = styles_config.get('scrollbar', {})
        scrollbar_width = scrollbar_config.get('width', 6)
        scrollbar_clearance = scrollbar_width + 2  # Scrollbar + frame buffer
        scroll_area_height = self.tags_list_height - scrollbar_clearance
        tags_scroll_area.setFixedHeight(scroll_area_height)
        tags_scroll_area.setMinimumHeight(scroll_area_height)
        tags_scroll_area.setMaximumHeight(scroll_area_height)
        tags_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tags_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        tags_scroll_area.setWidgetResizable(False)  # Manual sizing to prevent clipping
        tags_scroll_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)  # Fixed height, expand width
        # Ensure viewport margins are zero
        tags_scroll_area.setViewportMargins(0, 0, 0, 0)
        
        # Create widget and grid layout for checkboxes
        tags_widget = QWidget()
        # Set background color to match scroll area to prevent white bar
        tags_widget.setAutoFillBackground(True)
        tags_palette = tags_widget.palette()
        tags_palette.setColor(tags_widget.backgroundRole(), self.input_bg_color)
        tags_widget.setPalette(tags_palette)
        tags_grid = QGridLayout(tags_widget)
        tags_grid.setSpacing(self.tags_list_spacing)
        # Use configurable margins for proper padding: [left, top, right, bottom]
        tags_grid.setContentsMargins(
            self.tags_list_margins[0],  # left
            self.tags_list_margins[1],  # top
            self.tags_list_margins[2],  # right
            self.tags_list_margins[3]   # bottom
        )
        
        # Get available tags from database, ordered by commonality
        available_tags = self._get_available_tags()
        
        # Create checkboxes for available tags
        self.tag_checkboxes: Dict[str, QCheckBox] = {}
        row = 0
        col = 0
        for tag in available_tags:
            checkbox = QCheckBox(tag)
            checkbox.setFont(QFont(self.label_font_family, self.label_font_size))
            # Default: White and Black are checked
            if tag in ["White", "Black"]:
                checkbox.setChecked(True)
            self.tag_checkboxes[tag] = checkbox
            tags_grid.addWidget(checkbox, row, col)
            col += 1
            if col >= self.tags_list_columns:
                col = 0
                row += 1
        
        # Set widget size policy - expand horizontally, minimum vertically
        tags_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        
        # Set the widget in the scroll area
        tags_scroll_area.setWidget(tags_widget)
        
        # Store references for size update after layout
        self._tags_widget = tags_widget
        self._tags_scroll_area = tags_scroll_area
        
        tags_container_layout.addWidget(tags_scroll_area)
        self.tags_scroll_area = tags_scroll_area
        
        # Add tags label and container to form layout
        replace_layout.addRow(self.tag_label, tags_container)
        
        # Copy from another tag checkbox - ensure it's positioned below the tags container
        # The tags_container already has bottom margin for spacing
        self.copy_from_tag_check = QCheckBox("Copy from another tag")
        self.copy_from_tag_check.setFont(QFont(self.label_font_family, self.label_font_size))
        self.copy_from_tag_check.toggled.connect(self._on_copy_mode_toggled)
        # Add to form layout with empty label to maintain alignment
        copy_checkbox_widget = QWidget()
        copy_checkbox_layout = QHBoxLayout(copy_checkbox_widget)
        copy_checkbox_layout.setContentsMargins(0, 0, 0, 0)
        copy_checkbox_layout.addWidget(self.copy_from_tag_check)
        copy_checkbox_layout.addStretch()
        replace_layout.addRow("", copy_checkbox_widget)
        
        # Source tag selection (shown when copy mode is enabled)
        self.source_tag_combo = QComboBox()
        # Populate with available tags (will be updated when dialog is shown)
        self.source_tag_combo.setMinimumWidth(self.input_minimum_width)
        self.source_tag_combo.setMinimumHeight(self.input_minimum_height)
        self.source_tag_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.source_tag_combo.setVisible(False)
        source_tag_label = QLabel("Source tag:")
        source_tag_label.setFont(QFont(self.label_font_family, self.label_font_size))
        source_tag_label.setMinimumWidth(label_min_width)
        source_tag_label.setVisible(False)
        replace_layout.addRow(source_tag_label, self.source_tag_combo)
        self.source_tag_label = source_tag_label
        
        # Find
        self.find_input = QLineEdit()
        self.find_input.setMinimumWidth(self.input_minimum_width)
        self.find_input.setMinimumHeight(self.input_minimum_height)
        self.find_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.find_label = QLabel("Find:")
        self.find_label.setFont(QFont(self.label_font_family, self.label_font_size))
        self.find_label.setMinimumWidth(label_min_width)
        replace_layout.addRow(self.find_label, self.find_input)
        
        # Replace
        self.replace_input = QLineEdit()
        self.replace_input.setMinimumWidth(self.input_minimum_width)
        self.replace_input.setMinimumHeight(self.input_minimum_height)
        self.replace_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.replace_label = QLabel("Replace:")
        self.replace_label.setFont(QFont(self.label_font_family, self.label_font_size))
        self.replace_label.setMinimumWidth(label_min_width)
        replace_layout.addRow(self.replace_label, self.replace_input)
        
        # Spacer before Options (to match spacing before "Copy from another tag")
        spacer_widget_options = QWidget()
        spacer_widget_options.setFixedHeight(self.form_spacing)
        replace_layout.addRow("", spacer_widget_options)
        
        # Options
        options_layout = QHBoxLayout()
        options_layout.setSpacing(self.options_spacing)
        self.case_sensitive_check = QCheckBox("Case sensitive")
        self.case_sensitive_check.setFont(QFont(self.label_font_family, self.label_font_size))
        self.regex_check = QCheckBox("Use regex")
        self.regex_check.setFont(QFont(self.label_font_family, self.label_font_size))
        self.overwrite_all_check = QCheckBox("Overwrite all values")
        self.overwrite_all_check.setFont(QFont(self.label_font_family, self.label_font_size))
        self.overwrite_all_check.toggled.connect(self._on_overwrite_all_toggled)
        options_layout.addWidget(self.case_sensitive_check)
        options_layout.addWidget(self.regex_check)
        options_layout.addWidget(self.overwrite_all_check)
        options_layout.addStretch()
        self.options_label = QLabel("Options:")
        self.options_label.setFont(QFont(self.label_font_family, self.label_font_size))
        self.options_label.setMinimumWidth(label_min_width)
        replace_layout.addRow(self.options_label, options_layout)
        self.options_layout = options_layout
        
        replace_group.setLayout(replace_layout)
        main_layout.addWidget(replace_group)
        
        main_layout.addSpacing(self.section_spacing)
        
        # Smart Update group
        smart_update_group = QGroupBox("Smart Update")
        smart_update_layout = QVBoxLayout()
        smart_update_layout.setSpacing(self.result_spacing)
        smart_update_content_margins = groups_config.get("content_margins", [10, 20, 10, 15])
        smart_update_layout.setContentsMargins(
            smart_update_content_margins[0],
            smart_update_content_margins[1],
            smart_update_content_margins[2],
            smart_update_content_margins[3]
        )
        self.update_result_check = QCheckBox("Update Result based on last move evaluation")
        self.update_result_check.setChecked(False)
        smart_update_layout.addWidget(self.update_result_check)
        self.update_eco_check = QCheckBox("Update ECO code with played opening ECO")
        self.update_eco_check.setChecked(False)
        smart_update_layout.addWidget(self.update_eco_check)
        smart_update_group.setLayout(smart_update_layout)
        main_layout.addWidget(smart_update_group)
        
        main_layout.addStretch()
        
        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._on_apply_clicked)
        buttons_layout.addWidget(self.apply_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(buttons_layout)
    
    def _apply_styling(self) -> None:
        """Apply styling from config.json."""
        # Background color
        palette = self.palette()
        palette.setColor(self.backgroundRole(), self.bg_color)
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        
        # Apply button styling
        buttons_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_replace", {}).get("buttons", {})
        bg_color = self.config.get("ui", {}).get("dialogs", {}).get("bulk_replace", {}).get("background_color", [40, 40, 45])
        border_color = self.config.get("ui", {}).get("dialogs", {}).get("bulk_replace", {}).get("border_color", [60, 60, 65])
        text_color = self.config.get("ui", {}).get("dialogs", {}).get("bulk_replace", {}).get("text_color", [200, 200, 200])
        from app.utils.font_utils import scale_font_size
        font_size = scale_font_size(self.config.get("ui", {}).get("dialogs", {}).get("bulk_replace", {}).get("font_size", 11))
        
        button_width = buttons_config.get("width", 120)
        button_height = buttons_config.get("height", 30)
        button_border_radius = buttons_config.get("border_radius", 3)
        button_padding = buttons_config.get("padding", 5)
        button_bg_offset = buttons_config.get("background_offset", 20)
        button_hover_offset = buttons_config.get("hover_background_offset", 30)
        button_pressed_offset = buttons_config.get("pressed_background_offset", 10)
        
        button_style = (
            f"QPushButton {{"
            f"min-width: {button_width}px;"
            f"min-height: {button_height}px;"
            f"background-color: rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
            f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
            f"border-radius: {button_border_radius}px;"
            f"padding: {button_padding}px;"
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"font-size: {font_size}pt;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({bg_color[0] + button_hover_offset}, {bg_color[1] + button_hover_offset}, {bg_color[2] + button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({bg_color[0] + button_pressed_offset}, {bg_color[1] + button_pressed_offset}, {bg_color[2] + button_pressed_offset});"
            f"}}"
            f"QPushButton:disabled {{"
            f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
            f"color: rgb({text_color[0] // 2}, {text_color[1] // 2}, {text_color[2] // 2});"
            f"}}"
        )
        
        self.apply_button.setStyleSheet(button_style)
        self.cancel_button.setStyleSheet(button_style)
        
        # Apply styling to quick select buttons if they exist
        if self.quick_select_enabled and hasattr(self, 'select_all_button'):
            quick_select_style = (
                f"QPushButton {{"
                f"min-width: {self.quick_select_width}px;"
                f"min-height: {self.quick_select_height}px;"
                f"background-color: rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
                f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
                f"border-radius: {button_border_radius}px;"
                f"padding: {button_padding}px;"
                f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
                f"font-size: {font_size}pt;"
                f"}}"
                f"QPushButton:hover {{"
                f"background-color: rgb({bg_color[0] + button_hover_offset}, {bg_color[1] + button_hover_offset}, {bg_color[2] + button_hover_offset});"
                f"}}"
                f"QPushButton:pressed {{"
                f"background-color: rgb({bg_color[0] + button_pressed_offset}, {bg_color[1] + button_pressed_offset}, {bg_color[2] + button_pressed_offset});"
                f"}}"
            )
            self.select_all_button.setStyleSheet(quick_select_style)
            self.deselect_all_button.setStyleSheet(quick_select_style)
        
        # Get selection colors from config (use defaults if not available)
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_replace", {})
        inputs_config = dialog_config.get("inputs", {})
        selection_bg = inputs_config.get('selection_background_color', [70, 90, 130])
        selection_text = inputs_config.get('selection_text_color', [240, 240, 240])
        
        # Apply input styling for QLineEdit only
        input_style = (
            f"QLineEdit {{"
            f"background-color: rgb({self.input_bg_color.red()}, {self.input_bg_color.green()}, {self.input_bg_color.blue()});"
            f"border: 1px solid rgb({self.input_border_color.red()}, {self.input_border_color.green()}, {self.input_border_color.blue()});"
            f"border-radius: {self.input_border_radius}px;"
            f"padding: {self.input_padding[1]}px {self.input_padding[0]}px;"
            f"color: rgb({self.input_text_color.red()}, {self.input_text_color.green()}, {self.input_text_color.blue()});"
            f"font-family: {self.input_font_family};"
            f"font-size: {self.input_font_size}pt;"
            f"}}"
            f"QLineEdit:disabled {{"
            f"background-color: rgb({self.input_bg_color.red() // 2}, {self.input_bg_color.green() // 2}, {self.input_bg_color.blue() // 2});"
            f"color: rgb({self.input_text_color.red() // 2}, {self.input_text_color.green() // 2}, {self.input_text_color.blue() // 2});"
            f"}}"
        )
        
        self.find_input.setStyleSheet(input_style)
        self.replace_input.setStyleSheet(input_style)
        
        # Apply combobox styling using StyleManager
        from app.views.style import StyleManager
        
        # Get focus border color for combobox
        focus_border_color = inputs_config.get('focus_border_color', [0, 120, 212])
        
        # Convert QColor to [R, G, B] lists
        text_color = [self.input_text_color.red(), self.input_text_color.green(), self.input_text_color.blue()]
        bg_color = [self.input_bg_color.red(), self.input_bg_color.green(), self.input_bg_color.blue()]
        border_color = [self.input_border_color.red(), self.input_border_color.green(), self.input_border_color.blue()]
        
        # Apply styling to combobox
        StyleManager.style_comboboxes(
            [self.source_tag_combo],
            self.config,
            text_color,
            self.input_font_family,
            self.input_font_size,
            bg_color,
            border_color,
            focus_border_color,
            selection_bg,
            selection_text,
            border_width=1,
            border_radius=self.input_border_radius,
            padding=self.input_padding,
            editable=False
        )
        
        # Apply scroll area styling using StyleManager
        if hasattr(self, 'tags_scroll_area'):
            from app.views.style import StyleManager
            # Convert QColor to [R, G, B] list
            input_bg = [self.input_bg_color.red(), self.input_bg_color.green(), self.input_bg_color.blue()]
            input_border = [self.input_border_color.red(), self.input_border_color.green(), self.input_border_color.blue()]
            StyleManager.style_scroll_area(
                self.tags_scroll_area,
                self.config,
                input_bg,
                input_border,
                self.input_border_radius
            )
        
        # Apply group box styling
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_replace", {})
        groups_config = dialog_config.get("groups", {})
        bg_color = dialog_config.get("background_color", [40, 40, 45])
        border_color = dialog_config.get("border_color", [60, 60, 65])
        
        group_bg_color = groups_config.get("background_color", bg_color) if "background_color" in groups_config else bg_color
        group_border_color = groups_config.get("border_color", border_color) if "border_color" in groups_config else border_color
        group_border_radius = groups_config.get("border_radius", 5)
        from app.utils.font_utils import resolve_font_family, scale_font_size
        group_title_font_family = resolve_font_family(groups_config.get("title_font_family", "Helvetica Neue"))
        group_title_font_size = scale_font_size(groups_config.get("title_font_size", 11))
        group_title_color = groups_config.get("title_color", [240, 240, 240])
        group_content_margins = groups_config.get("content_margins", [10, 15, 10, 10])
        group_margin_top = groups_config.get("margin_top", 10)
        group_padding_top = groups_config.get("padding_top", 5)
        
        group_title_left = groups_config.get("title_left", 10)
        group_title_padding = groups_config.get("title_padding", [0, 5])
        
        group_style = (
            f"QGroupBox {{"
            f"background-color: rgb({group_bg_color[0]}, {group_bg_color[1]}, {group_bg_color[2]});"
            f"border: 1px solid rgb({group_border_color[0]}, {group_border_color[1]}, {group_border_color[2]});"
            f"border-radius: {group_border_radius}px;"
            f"margin-top: {group_margin_top}px;"
            f"padding-top: {group_padding_top}px;"
            f"}}"
            f"QGroupBox::title {{"
            f"subcontrol-origin: margin;"
            f"subcontrol-position: top left;"
            f"left: {group_title_left}px;"
            f"padding: {group_title_padding[0]} {group_title_padding[1]}px;"
            f"font-family: {group_title_font_family};"
            f"font-size: {group_title_font_size}pt;"
            f"color: rgb({group_title_color[0]}, {group_title_color[1]}, {group_title_color[2]});"
            f"}}"
        )
        
        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(group_style)
            layout = group.layout()
            if layout:
                layout.setContentsMargins(
                    group_content_margins[0],
                    group_content_margins[1],
                    group_content_margins[2],
                    group_content_margins[3]
                )
        
        # Apply label styling - apply to ALL labels to prevent macOS theme override
        label_style = (
            f"QLabel {{"
            f"color: rgb({self.label_text_color.red()}, {self.label_text_color.green()}, {self.label_text_color.blue()});"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.label_font_size}pt;"
            f"background-color: transparent;"
            f"}}"
        )
        
        # Apply stylesheet and palette to all labels to ensure macOS doesn't override
        # Group box titles are styled via QGroupBox::title, not QLabel, so we can style all QLabels
        for label in self.findChildren(QLabel):
            # Apply stylesheet
            label.setStyleSheet(label_style)
            # Also set palette to ensure color is applied (macOS sometimes ignores stylesheet)
            label_palette = label.palette()
            label_palette.setColor(label.foregroundRole(), self.label_text_color)
            label.setPalette(label_palette)
            # Force update to ensure styling is applied
            label.update()
        
        # Apply radio button styling to match import games dialog (simple styling, no custom indicator)
        radio_button_style = (
            f"QRadioButton {{"
            f"color: rgb({self.label_text_color.red()}, {self.label_text_color.green()}, {self.label_text_color.blue()});"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.label_font_size}pt;"
            f"spacing: 5px;"
            f"}}"
        )
        
        for radio_button in self.findChildren(QRadioButton):
            radio_button.setStyleSheet(radio_button_style)
        
        # Apply checkbox styling to ensure consistent font size and style
        self._apply_checkbox_styling()
    
    def _apply_checkbox_styling(self) -> None:
        """Apply checkbox styling to all checkboxes."""
        from pathlib import Path
        
        # Apply checkbox styling using StyleManager
        from app.views.style import StyleManager
        from pathlib import Path
        
        # Get checkmark icon path
        project_root = Path(__file__).parent.parent.parent
        checkmark_path = project_root / "app" / "resources" / "icons" / "checkmark.svg"
        
        # Convert QColor to [R, G, B] lists
        text_color = [self.label_text_color.red(), self.label_text_color.green(), self.label_text_color.blue()]
        input_bg = [self.input_bg_color.red(), self.input_bg_color.green(), self.input_bg_color.blue()]
        input_border = [self.input_border_color.red(), self.input_border_color.green(), self.input_border_color.blue()]
        
        # Get all checkboxes and apply styling
        checkboxes = self.findChildren(QCheckBox)
        StyleManager.style_checkboxes(
            checkboxes,
            self.config,
            text_color,
            self.label_font_family,
            self.label_font_size,
            input_bg,
            input_border,
            checkmark_path
        )
    
    
    def _get_available_tags(self) -> List[str]:
        """Get available tags from database, ordered by commonality.
        
        Delegates to DatabaseController to extract tags from the database.
        
        Returns:
            List of tag names ordered by importance and frequency.
        """
        if not self.database:
            # If no database, return empty list
            return []
        
        # Delegate to database controller
        return self.controller.database_controller.get_available_tags(self.database)
    
    def showEvent(self, event: QShowEvent) -> None:
        """Override showEvent to ensure checkbox styling is applied when dialog is shown."""
        super().showEvent(event)
        
        # Update source tag combo with available tags
        available_tags = self._get_available_tags()
        self.source_tag_combo.clear()
        if available_tags:
            self.source_tag_combo.addItems(available_tags)
            # Set default to first available tag if Date is not available
            if "Date" in available_tags:
                self.source_tag_combo.setCurrentText("Date")
            else:
                self.source_tag_combo.setCurrentIndex(0)
        
        # Reapply checkbox styling to fix any truncation issues
        self._apply_checkbox_styling()
        
        # Update tags widget size after dialog is shown to ensure proper scrolling
        if hasattr(self, '_tags_widget') and hasattr(self, '_tags_scroll_area'):
            QTimer.singleShot(0, self._update_tags_widget_size)
    
    def _update_tags_widget_size(self) -> None:
        """Update the tags widget size to match viewport width and content height."""
        if not hasattr(self, '_tags_widget') or not hasattr(self, '_tags_scroll_area'):
            return
        
        # Force layout update
        self._tags_widget.updateGeometry()
        
        # Get viewport width
        viewport_width = self._tags_scroll_area.viewport().width()
        if viewport_width <= 0:
            # Try again after a short delay if viewport not ready
            QTimer.singleShot(50, self._update_tags_widget_size)
            return
        
        # Get content height from size hint
        content_height = self._tags_widget.sizeHint().height()
        
        # Set widget size: width matches viewport, height matches content
        self._tags_widget.setFixedSize(viewport_width, content_height)
    
    def _on_copy_mode_toggled(self, checked: bool) -> None:
        """Handle copy mode checkbox toggle."""
        # Show/hide source tag dropdown
        self.source_tag_combo.setVisible(checked)
        self.source_tag_label.setVisible(checked)
        
        # Hide/show Find/Replace fields and options
        self.find_input.setVisible(not checked)
        self.find_label.setVisible(not checked)
        self.replace_input.setVisible(not checked)
        self.replace_label.setVisible(not checked)
        self.options_label.setVisible(not checked)
        self.case_sensitive_check.setVisible(not checked)
        self.regex_check.setVisible(not checked)
        self.overwrite_all_check.setVisible(not checked)
        
        # Update label for tags
        self.tag_label.setText("Target tags:" if checked else "Tags:")
    
    def _on_select_all_clicked(self) -> None:
        """Handle Select All button click."""
        for checkbox in self.tag_checkboxes.values():
            checkbox.setChecked(True)
    
    def _on_deselect_all_clicked(self) -> None:
        """Handle Deselect All button click."""
        for checkbox in self.tag_checkboxes.values():
            checkbox.setChecked(False)
    
    def _get_selected_tags(self) -> List[str]:
        """Get list of selected tag names.
        
        Returns:
            List of selected tag names.
        """
        selected = []
        for tag, checkbox in self.tag_checkboxes.items():
            if checkbox.isChecked():
                selected.append(tag)
        return selected
    
    def _on_overwrite_all_toggled(self, checked: bool) -> None:
        """Handle overwrite all checkbox toggle."""
        # Disable Find field when overwrite all is checked
        self.find_input.setEnabled(not checked)
        self.case_sensitive_check.setEnabled(not checked)
        self.regex_check.setEnabled(not checked)
    
    def _on_apply_clicked(self) -> None:
        """Handle apply button click."""
        if not self.database:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "Error", "No database selected", self)
            return
        
        if self._operation_in_progress:
            return
        
        # Check if at least one operation is selected
        is_copy_mode = self.copy_from_tag_check.isChecked()
        overwrite_all = self.overwrite_all_check.isChecked()
        has_find_text = bool(self.find_input.text().strip())
        has_replace_text = bool(self.replace_input.text().strip())
        # Replace operation is valid if:
        # - Copy mode is enabled, OR
        # - Overwrite all is checked (replace text is optional but recommended), OR
        # - Both find and replace text are provided
        has_replace = is_copy_mode or overwrite_all or (has_find_text and has_replace_text)
        has_result_update = self.update_result_check.isChecked()
        has_eco_update = self.update_eco_check.isChecked()
        
        if not has_replace and not has_result_update and not has_eco_update:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "Error", "Please select at least one operation", self)
            return
        
        # Disable controls during operation
        self._set_controls_enabled(False)
        self._operation_in_progress = True
        
        # Get game indices
        game_indices = None
        if self.selected_games_radio.isChecked():
            game_indices = self.controller.get_selected_game_indices()
            if not game_indices:
                from app.views.message_dialog import MessageDialog
                MessageDialog.show_warning(self.config, "Error", "No games selected", self)
                self._set_controls_enabled(True)
                self._operation_in_progress = False
                return
        
        # Perform operations
        try:
            # Initialize result variable (will be set by first operation)
            result = None
            
            # Metadata replacement or copy
            if has_replace:
                # Get selected tags
                selected_tags = self._get_selected_tags()
                if not selected_tags:
                    from app.views.message_dialog import MessageDialog
                    MessageDialog.show_warning(self.config, "Error", "Please select at least one tag", self)
                    self._set_controls_enabled(True)
                    self._operation_in_progress = False
                    return
                
                if is_copy_mode:
                    # Copy from another tag
                    source_tag = self.source_tag_combo.currentText().strip()
                    if not source_tag:
                        from app.views.message_dialog import MessageDialog
                        MessageDialog.show_warning(self.config, "Error", "Please enter a source tag name", self)
                        self._set_controls_enabled(True)
                        self._operation_in_progress = False
                        return
                    
                    # Check if source tag is in selected tags
                    if source_tag in selected_tags:
                        from app.views.message_dialog import MessageDialog
                        MessageDialog.show_warning(self.config, "Error", "Source tag cannot be in the target tags list", self)
                        self._set_controls_enabled(True)
                        self._operation_in_progress = False
                        return
                    
                    # Process each selected tag
                    total_games_processed = 0
                    total_games_updated = 0
                    total_games_failed = 0
                    total_games_skipped = 0
                    
                    for target_tag in selected_tags:
                        result = self.controller.copy_metadata_tag(
                            self.database,
                            target_tag,
                            source_tag,
                            game_indices
                        )
                        
                        if not result.success:
                            from app.views.message_dialog import MessageDialog
                            MessageDialog.show_warning(self.config, "Error", f"Failed to copy to {target_tag}: {result.error_message or 'Operation failed'}", self)
                            self._set_controls_enabled(True)
                            self._operation_in_progress = False
                            return
                        
                        # Aggregate results
                        total_games_processed = max(total_games_processed, result.games_processed)
                        total_games_updated += result.games_updated
                        total_games_failed += result.games_failed
                        total_games_skipped += result.games_skipped
                    
                    # Create aggregated result
                    from app.services.bulk_replace_service import BulkReplaceResult
                    result = BulkReplaceResult(
                        success=True,
                        games_processed=total_games_processed,
                        games_updated=total_games_updated,
                        games_failed=total_games_failed,
                        games_skipped=total_games_skipped
                    )
                else:
                    # Text replacement
                    find_text = self.find_input.text()
                    replace_text = self.replace_input.text()
                    case_sensitive = self.case_sensitive_check.isChecked()
                    use_regex = self.regex_check.isChecked()
                    overwrite_all = self.overwrite_all_check.isChecked()
                    
                    # Process each selected tag
                    total_games_processed = 0
                    total_games_updated = 0
                    total_games_failed = 0
                    total_games_skipped = 0
                    
                    for target_tag in selected_tags:
                        tag_result = self.controller.replace_metadata_tag(
                            self.database,
                            target_tag,
                            find_text,
                            replace_text,
                            case_sensitive,
                            use_regex,
                            overwrite_all,
                            game_indices
                        )
                        
                        if not tag_result.success:
                            from app.views.message_dialog import MessageDialog
                            MessageDialog.show_warning(self.config, "Error", f"Failed to replace in {target_tag}: {tag_result.error_message or 'Operation failed'}", self)
                            self._set_controls_enabled(True)
                            self._operation_in_progress = False
                            return
                        
                        # Aggregate results
                        total_games_processed = max(total_games_processed, tag_result.games_processed)
                        total_games_updated += tag_result.games_updated
                        total_games_failed += tag_result.games_failed
                        total_games_skipped += tag_result.games_skipped
                    
                    # Create aggregated result
                    from app.services.bulk_replace_service import BulkReplaceResult
                    result = BulkReplaceResult(
                        success=True,
                        games_processed=total_games_processed,
                        games_updated=total_games_updated,
                        games_failed=total_games_failed,
                        games_skipped=total_games_skipped
                    )
            
            # Result update
            if has_result_update:
                result = self.controller.update_result_tags(
                    self.database,
                    game_indices
                )
                
                if not result.success:
                    from app.views.message_dialog import MessageDialog
                    MessageDialog.show_warning(self.config, "Error", result.error_message or "Operation failed", self)
                    self._set_controls_enabled(True)
                    self._operation_in_progress = False
                    return
            
            # ECO update
            if has_eco_update:
                eco_result = self.controller.update_eco_tags(
                    self.database,
                    game_indices
                )
                
                if not eco_result.success:
                    from app.views.message_dialog import MessageDialog
                    MessageDialog.show_warning(self.config, "Error", eco_result.error_message or "Operation failed", self)
                    self._set_controls_enabled(True)
                    self._operation_in_progress = False
                    return
                
                # If we had a previous result (from replace or result update), aggregate
                # Otherwise use ECO result
                if has_replace or has_result_update:
                    # Aggregate results
                    from app.services.bulk_replace_service import BulkReplaceResult
                    result = BulkReplaceResult(
                        success=True,
                        games_processed=max(result.games_processed, eco_result.games_processed),
                        games_updated=result.games_updated + eco_result.games_updated,
                        games_failed=result.games_failed + eco_result.games_failed,
                        games_skipped=result.games_skipped + eco_result.games_skipped
                    )
                else:
                    result = eco_result
            
            # Show success message using styled dialog
            self._show_success_dialog(
                "Bulk Replace Complete",
                f"Operation completed:\n\n"
                f"Games processed: {result.games_processed}\n"
                f"Games updated: {result.games_updated}\n"
                f"Games failed: {result.games_failed}\n"
                f"Games skipped: {result.games_skipped}"
            )
            
            self.accept()
            
        except Exception as e:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_critical(self.config, "Error", f"An error occurred: {str(e)}", self)
            self._set_controls_enabled(True)
            self._operation_in_progress = False
    
    def _set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable all controls."""
        # Enable/disable tag checkboxes
        for checkbox in self.tag_checkboxes.values():
            checkbox.setEnabled(enabled)
        
        # Enable/disable quick select buttons
        if self.quick_select_enabled and hasattr(self, 'select_all_button'):
            self.select_all_button.setEnabled(enabled)
            self.deselect_all_button.setEnabled(enabled)
        
        self.copy_from_tag_check.setEnabled(enabled)
        self.source_tag_combo.setEnabled(enabled)
        is_copy_mode = self.copy_from_tag_check.isChecked()
        is_overwrite_all = self.overwrite_all_check.isChecked()
        self.find_input.setEnabled(enabled and not is_copy_mode and not is_overwrite_all)
        self.replace_input.setEnabled(enabled and not is_copy_mode)
        self.case_sensitive_check.setEnabled(enabled and not is_copy_mode and not is_overwrite_all)
        self.regex_check.setEnabled(enabled and not is_copy_mode and not is_overwrite_all)
        self.overwrite_all_check.setEnabled(enabled and not is_copy_mode)
        self.update_result_check.setEnabled(enabled)
        self.all_games_radio.setEnabled(enabled)
        self.selected_games_radio.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)
        self.cancel_button.setEnabled(enabled)
    
    def sizeHint(self) -> QSize:
        """Return the fixed size as the size hint."""
        return self._fixed_size
    
    def _show_success_dialog(self, title: str, message: str) -> None:
        """Show a styled success dialog.
        
        Args:
            title: Dialog title.
            message: Success message.
        """
        from PyQt6.QtGui import QPalette, QColor
        
        # Get confirmation dialog config (reuse for success dialog)
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('confirmation_dialog', {})
        layout_config = dialog_config.get('layout', {})
        title_config = dialog_config.get('title', {})
        message_config = dialog_config.get('message', {})
        buttons_config = dialog_config.get('buttons', {})
        
        # Create dialog
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog_width = dialog_config.get('width', 400)
        
        # Set dialog background color
        bg_color = dialog_config.get('background_color', [40, 40, 45])
        dialog.setAutoFillBackground(True)
        dialog_palette = dialog.palette()
        dialog_palette.setColor(dialog.backgroundRole(), QColor(bg_color[0], bg_color[1], bg_color[2]))
        dialog.setPalette(dialog_palette)
        
        layout = QVBoxLayout(dialog)
        layout_spacing = layout_config.get('spacing', 15)
        layout_margins = layout_config.get('margins', [15, 15, 15, 15])
        layout.setSpacing(layout_spacing)
        layout.setContentsMargins(layout_margins[0], layout_margins[1], layout_margins[2], layout_margins[3])
        
        # Title
        from app.utils.font_utils import scale_font_size
        title_font_size = scale_font_size(title_config.get('font_size', 14))
        title_padding = title_config.get('padding', 5)
        # Get title text color from config, fallback to dialog text_color or default
        title_text_color = title_config.get('text_color', dialog_config.get('text_color', [240, 240, 240]))
        title_label = QLabel(f"<b>{title}</b>")
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
        
        # Message
        message_font_size = scale_font_size(message_config.get('font_size', 11))
        message_padding = message_config.get('padding', 5)
        message_text_color = message_config.get('text_color', [200, 200, 200])
        message_label = QLabel(message)
        message_label.setWordWrap(True)
        # Set minimum width to ensure proper word wrapping calculation
        message_label.setMinimumWidth(dialog_width - layout_margins[0] - layout_margins[2] - (message_padding * 2))
        message_label.setStyleSheet(
            f"font-size: {message_font_size}pt; "
            f"padding: {message_padding}px; "
            f"color: rgb({message_text_color[0]}, {message_text_color[1]}, {message_text_color[2]});"
        )
        layout.addWidget(message_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_spacing = buttons_config.get('spacing', 10)
        button_layout.setSpacing(button_spacing)
        button_layout.addStretch()
        
        # Get button styling from config
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        button_border_radius = buttons_config.get('border_radius', 3)
        button_padding = buttons_config.get('padding', 5)
        button_bg_offset = buttons_config.get('background_offset', 20)
        button_hover_offset = buttons_config.get('hover_background_offset', 30)
        button_pressed_offset = buttons_config.get('pressed_background_offset', 10)
        from app.utils.font_utils import scale_font_size
        button_font_size = scale_font_size(buttons_config.get('font_size', 10))
        text_color = buttons_config.get('text_color', [200, 200, 200])
        border_color = buttons_config.get('border_color', [60, 60, 65])
        
        button_style = (
            f"QPushButton {{"
            f"min-width: {button_width}px;"
            f"min-height: {button_height}px;"
            f"background-color: rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
            f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
            f"border-radius: {button_border_radius}px;"
            f"padding: {button_padding}px;"
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"font-size: {button_font_size}pt;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({bg_color[0] + button_hover_offset}, {bg_color[1] + button_hover_offset}, {bg_color[2] + button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({bg_color[0] + button_pressed_offset}, {bg_color[1] + button_pressed_offset}, {bg_color[2] + button_pressed_offset});"
            f"}}"
        )
        
        ok_button = QPushButton("OK")
        ok_button.setStyleSheet(button_style)
        ok_button.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
        
        # Let Qt calculate the natural size after layout is set up
        # This accounts for DPI scaling automatically
        dialog.setMinimumWidth(dialog_width)
        dialog.adjustSize()
        
        # Ensure minimum height from config
        min_height = dialog_config.get('height', 150)
        if dialog.height() < min_height:
            dialog.setMinimumHeight(min_height)
            dialog.resize(dialog.width(), min_height)
        
        # Show dialog
        dialog.exec()

