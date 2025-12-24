"""Bulk tag dialog for adding and removing tags from database games."""

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
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPalette, QColor, QFont, QShowEvent
from typing import Optional, Dict, Any, List

from app.controllers.bulk_tag_controller import BulkTagController
from app.models.database_model import DatabaseModel


class BulkTagDialog(QDialog):
    """Dialog for bulk tag operations on databases."""
    
    # Standard PGN tags
    STANDARD_TAGS = [
        "White", "Black", "Result", "Date", "Event", "Site", "Round",
        "ECO", "WhiteElo", "BlackElo", "TimeControl", "WhiteTitle",
        "BlackTitle", "WhiteFideId", "BlackFideId", "WhiteTeam", "BlackTeam",
        "PlyCount", "EventDate", "Termination", "Annotator", "UTCTime"
    ]
    
    def __init__(self, config: Dict[str, Any], bulk_tag_controller: BulkTagController,
                 database: Optional[DatabaseModel], parent=None) -> None:
        """Initialize the bulk tag dialog.
        
        Args:
            config: Configuration dictionary.
            bulk_tag_controller: BulkTagController instance.
            database: Optional DatabaseModel instance (active database).
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.controller = bulk_tag_controller
        self.database = database
        
        # Store fixed size
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_tag', {})
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
        self.setWindowTitle("Bulk Add/Remove Tags")
    
    def _load_config(self) -> None:
        """Load configuration values from config.json."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_tag", {})
        
        # Dialog dimensions
        self.dialog_width = dialog_config.get("width", 600)
        self.dialog_height = dialog_config.get("height", 680)
        
        # Background color
        bg_color = dialog_config.get("background_color", [40, 40, 45])
        self.bg_color = QColor(bg_color[0], bg_color[1], bg_color[2])
        
        # Text color
        text_color = dialog_config.get("text_color", [200, 200, 200])
        self.text_color = QColor(text_color[0], text_color[1], text_color[2])
        
        # Font
        font_size = dialog_config.get("font_size", 11)
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
        self.input_font_size = inputs_config.get("font_size", 11)
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
        
        # Radio buttons
        radio_buttons_config = dialog_config.get("radio_buttons", {})
        self.radio_button_first_minimum_width = radio_buttons_config.get("first_button_minimum_width", 100)
    
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
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_tag", {})
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
        # Ensure consistent sizing for proper alignment
        self.all_games_radio.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.selected_games_radio.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # Set minimum width for first radio button to align second buttons across sections
        self.all_games_radio.setMinimumWidth(self.radio_button_first_minimum_width)
        games_layout.addWidget(self.all_games_radio, alignment=Qt.AlignmentFlag.AlignVCenter)
        games_layout.addWidget(self.selected_games_radio, alignment=Qt.AlignmentFlag.AlignVCenter)
        games_layout.addStretch()
        games_group.setLayout(games_layout)
        main_layout.addWidget(games_group)
        
        main_layout.addSpacing(self.section_spacing)
        
        # Operation Selection group
        operation_group = QGroupBox("Operation")
        operation_layout = QHBoxLayout()
        operation_layout.setSpacing(self.section_spacing)
        operation_content_margins = groups_config.get("content_margins", [10, 20, 10, 15])
        operation_layout.setContentsMargins(
            operation_content_margins[0],
            operation_content_margins[1],
            operation_content_margins[2],
            operation_content_margins[3]
        )
        self.operation_button_group = QButtonGroup(self)
        self.add_tag_radio = QRadioButton("Add Tag")
        self.remove_tag_radio = QRadioButton("Remove Tag")
        self.operation_button_group.addButton(self.add_tag_radio, 0)
        self.operation_button_group.addButton(self.remove_tag_radio, 1)
        self.add_tag_radio.setChecked(True)
        self.add_tag_radio.toggled.connect(self._on_operation_changed)
        self.remove_tag_radio.toggled.connect(self._on_operation_changed)
        # Ensure consistent sizing for proper alignment
        self.add_tag_radio.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.remove_tag_radio.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        # Set same minimum width for first radio button to align second buttons across sections
        self.add_tag_radio.setMinimumWidth(self.radio_button_first_minimum_width)
        operation_layout.addWidget(self.add_tag_radio, alignment=Qt.AlignmentFlag.AlignVCenter)
        operation_layout.addWidget(self.remove_tag_radio, alignment=Qt.AlignmentFlag.AlignVCenter)
        operation_layout.addStretch()
        operation_group.setLayout(operation_layout)
        main_layout.addWidget(operation_group)
        
        main_layout.addSpacing(self.section_spacing)
        
        # Tag Operation group
        tag_group = QGroupBox("Tag Operation")
        tag_layout = QFormLayout()
        tag_layout.setSpacing(self.form_spacing)
        # Set field growth policy to make fields expand
        tag_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        # Set alignment for macOS compatibility (left-align labels and form)
        tag_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        tag_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        tag_content_margins = groups_config.get("content_margins", [10, 20, 10, 15])
        tag_layout.setContentsMargins(
            tag_content_margins[0],
            tag_content_margins[1],
            tag_content_margins[2],
            tag_content_margins[3]
        )
        
        # Set fixed label width
        label_min_width = self.label_minimum_width
        
        # Tag selection
        self.tag_combo = QComboBox()
        self.tag_combo.setEditable(True)
        self.tag_combo.addItems(self.STANDARD_TAGS)
        self.tag_combo.setCurrentText("EventDate")
        self.tag_combo.setMinimumWidth(self.input_minimum_width)
        self.tag_combo.setMinimumHeight(self.input_minimum_height)
        self.tag_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tag_label = QLabel("Tag:")
        self.tag_label.setFont(QFont(self.label_font_family, self.label_font_size))
        self.tag_label.setMinimumWidth(label_min_width)
        tag_layout.addRow(self.tag_label, self.tag_combo)
        
        # Spacer before value source options
        spacer_widget = QWidget()
        spacer_widget.setFixedHeight(self.form_spacing)
        tag_layout.addRow("", spacer_widget)
        
        # Value source selection (for Add Tag mode)
        self.value_source_button_group = QButtonGroup(self)
        self.fixed_value_radio = QRadioButton("Fixed value")
        self.copy_from_tag_radio = QRadioButton("Copy from tag")
        self.value_source_button_group.addButton(self.fixed_value_radio, 0)
        self.value_source_button_group.addButton(self.copy_from_tag_radio, 1)
        self.fixed_value_radio.setChecked(True)
        self.fixed_value_radio.toggled.connect(self._on_value_source_changed)
        self.copy_from_tag_radio.toggled.connect(self._on_value_source_changed)
        # Ensure consistent sizing for proper alignment
        self.fixed_value_radio.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.copy_from_tag_radio.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        
        value_source_layout = QHBoxLayout()
        value_source_layout.setSpacing(self.section_spacing)
        value_source_layout.addWidget(self.fixed_value_radio, alignment=Qt.AlignmentFlag.AlignVCenter)
        value_source_layout.addWidget(self.copy_from_tag_radio, alignment=Qt.AlignmentFlag.AlignVCenter)
        value_source_layout.addStretch()
        self.value_source_label = QLabel("Value source:")
        self.value_source_label.setFont(QFont(self.label_font_family, self.label_font_size))
        self.value_source_label.setMinimumWidth(label_min_width)
        tag_layout.addRow(self.value_source_label, value_source_layout)
        
        # Fixed value input (for Add Tag mode)
        self.fixed_value_input = QLineEdit()
        self.fixed_value_input.setMinimumWidth(self.input_minimum_width)
        self.fixed_value_input.setMinimumHeight(self.input_minimum_height)
        self.fixed_value_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.fixed_value_label = QLabel("Value:")
        self.fixed_value_label.setFont(QFont(self.label_font_family, self.label_font_size))
        self.fixed_value_label.setMinimumWidth(label_min_width)
        tag_layout.addRow(self.fixed_value_label, self.fixed_value_input)
        
        # Source tag selection (for Add Tag mode with copy from tag)
        self.source_tag_combo = QComboBox()
        self.source_tag_combo.setEditable(True)
        self.source_tag_combo.addItems(self.STANDARD_TAGS)
        self.source_tag_combo.setCurrentText("Date")
        self.source_tag_combo.setMinimumWidth(self.input_minimum_width)
        self.source_tag_combo.setMinimumHeight(self.input_minimum_height)
        self.source_tag_combo.setVisible(False)
        self.source_tag_label = QLabel("Source tag:")
        self.source_tag_label.setFont(QFont(self.label_font_family, self.label_font_size))
        self.source_tag_label.setMinimumWidth(label_min_width)
        self.source_tag_label.setVisible(False)
        tag_layout.addRow(self.source_tag_label, self.source_tag_combo)
        
        tag_group.setLayout(tag_layout)
        main_layout.addWidget(tag_group)
        
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
        
        # Initialize UI state
        self._on_operation_changed()
    
    def _apply_styling(self) -> None:
        """Apply styling from config.json."""
        # Background color
        palette = self.palette()
        palette.setColor(self.backgroundRole(), self.bg_color)
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        
        # Apply button styling
        buttons_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_tag", {}).get("buttons", {})
        bg_color = self.config.get("ui", {}).get("dialogs", {}).get("bulk_tag", {}).get("background_color", [40, 40, 45])
        border_color = self.config.get("ui", {}).get("dialogs", {}).get("bulk_tag", {}).get("border_color", [60, 60, 65])
        text_color = self.config.get("ui", {}).get("dialogs", {}).get("bulk_tag", {}).get("text_color", [200, 200, 200])
        font_size = self.config.get("ui", {}).get("dialogs", {}).get("bulk_tag", {}).get("font_size", 11)
        
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
        
        # Apply input styling
        input_style = (
            f"QLineEdit, QComboBox {{"
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
            f"QComboBox:disabled {{"
            f"background-color: rgb({self.input_bg_color.red() // 2}, {self.input_bg_color.green() // 2}, {self.input_bg_color.blue() // 2});"
            f"color: rgb({self.input_text_color.red() // 2}, {self.input_text_color.green() // 2}, {self.input_text_color.blue() // 2});"
            f"}}"
        )
        
        self.fixed_value_input.setStyleSheet(input_style)
        self.tag_combo.setStyleSheet(input_style)
        self.source_tag_combo.setStyleSheet(input_style)
        
        # Apply group box styling
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_tag", {})
        groups_config = dialog_config.get("groups", {})
        bg_color = dialog_config.get("background_color", [40, 40, 45])
        border_color = dialog_config.get("border_color", [60, 60, 65])
        
        group_bg_color = groups_config.get("background_color", bg_color) if "background_color" in groups_config else bg_color
        group_border_color = groups_config.get("border_color", border_color) if "border_color" in groups_config else border_color
        group_border_radius = groups_config.get("border_radius", 5)
        group_title_font_family = groups_config.get("title_font_family", "Helvetica Neue")
        group_title_font_size = groups_config.get("title_font_size", 11)
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
        
        # Apply label styling
        label_style = (
            f"QLabel {{"
            f"color: rgb({self.label_text_color.red()}, {self.label_text_color.green()}, {self.label_text_color.blue()});"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.label_font_size}pt;"
            f"}}"
        )
        
        for label in self.findChildren(QLabel):
            # Skip group box titles (they're styled via QGroupBox::title)
            if isinstance(label.parent(), QGroupBox):
                continue
            label.setStyleSheet(label_style)
        
        # Apply checkbox styling to ensure consistent font size and style
        self._apply_checkbox_styling()
    
    def _apply_checkbox_styling(self) -> None:
        """Apply checkbox styling to all checkboxes."""
        from pathlib import Path
        
        input_border_color = self.input_border_color
        input_bg_color = self.input_bg_color
        
        # Get checkmark icon path
        project_root = Path(__file__).parent.parent.parent
        checkmark_path = project_root / "app" / "resources" / "icons" / "checkmark.svg"
        checkmark_url = str(checkmark_path).replace("\\", "/") if checkmark_path.exists() else ""
        
        checkbox_style = (
            f"QCheckBox {{"
            f"color: rgb({self.label_text_color.red()}, {self.label_text_color.green()}, {self.label_text_color.blue()});"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.label_font_size}pt;"
            f"spacing: {self.checkbox_spacing}px;"
            f"}}"
            f"QCheckBox::indicator {{"
            f"width: {self.checkbox_indicator_width}px;"
            f"height: {self.checkbox_indicator_height}px;"
            f"border: 1px solid rgb({input_border_color.red()}, {input_border_color.green()}, {input_border_color.blue()});"
            f"border-radius: {self.checkbox_indicator_border_radius}px;"
            f"background-color: rgb({input_bg_color.red()}, {input_bg_color.green()}, {input_bg_color.blue()});"
            f"}}"
            f"QCheckBox::indicator:hover {{"
            f"border: 1px solid rgb({min(255, input_border_color.red() + self.checkbox_hover_border_offset)}, {min(255, input_border_color.green() + self.checkbox_hover_border_offset)}, {min(255, input_border_color.blue() + self.checkbox_hover_border_offset)});"
            f"}}"
            f"QCheckBox::indicator:checked {{"
            f"background-color: rgb({self.checkbox_checked_bg_color.red()}, {self.checkbox_checked_bg_color.green()}, {self.checkbox_checked_bg_color.blue()});"
            f"border: 1px solid rgb({self.checkbox_checked_border_color.red()}, {self.checkbox_checked_border_color.green()}, {self.checkbox_checked_border_color.blue()});"
            f"image: url({checkmark_url});"
            f"}}"
        )
        
        for checkbox in self.findChildren(QCheckBox):
            checkbox.setStyleSheet(checkbox_style)
    
    def showEvent(self, event: QShowEvent) -> None:
        """Override showEvent to ensure styling is applied when dialog is shown."""
        super().showEvent(event)
        self._apply_checkbox_styling()
        # Update tag combobox if in remove mode
        if self.remove_tag_radio.isChecked():
            self._update_tag_combo_for_remove()
    
    def _on_operation_changed(self) -> None:
        """Handle operation selection change."""
        is_add_mode = self.add_tag_radio.isChecked()
        
        # Show/hide value source options based on operation
        self.value_source_label.setVisible(is_add_mode)
        self.fixed_value_radio.setVisible(is_add_mode)
        self.copy_from_tag_radio.setVisible(is_add_mode)
        self.fixed_value_input.setVisible(is_add_mode and self.fixed_value_radio.isChecked())
        self.fixed_value_label.setVisible(is_add_mode and self.fixed_value_radio.isChecked())
        self.source_tag_combo.setVisible(is_add_mode and self.copy_from_tag_radio.isChecked())
        self.source_tag_label.setVisible(is_add_mode and self.copy_from_tag_radio.isChecked())
        
        # Update tag label
        self.tag_label.setText("Tag:" if is_add_mode else "Tag to remove:")
        
        # Update tag combobox based on operation mode
        if is_add_mode:
            # Add mode: use standard tags
            self.tag_combo.clear()
            self.tag_combo.addItems(self.STANDARD_TAGS)
            self.tag_combo.setCurrentText("EventDate")
        else:
            # Remove mode: use tags that exist in the database
            self._update_tag_combo_for_remove()
    
    def _update_tag_combo_for_remove(self) -> None:
        """Update tag combobox with tags that exist in the database."""
        if not self.database:
            return
        
        # Extract all tags from database games
        existing_tags = self._extract_tags_from_database()
        
        # Sort tags: standard tags first (in order), then non-standard tags alphabetically
        standard_tags_set = set(self.STANDARD_TAGS)
        standard_tags_list = [tag for tag in self.STANDARD_TAGS if tag in existing_tags]
        non_standard_tags = sorted([tag for tag in existing_tags if tag not in standard_tags_set])
        
        # Combine: standard tags first, then non-standard tags
        all_tags = standard_tags_list + non_standard_tags
        
        # Update combobox
        self.tag_combo.clear()
        if all_tags:
            self.tag_combo.addItems(all_tags)
            self.tag_combo.setCurrentText(all_tags[0])
        else:
            # No tags found, keep editable for manual entry
            self.tag_combo.setCurrentText("")
    
    def _extract_tags_from_database(self) -> set:
        """Extract all tags that exist in the database games.
        
        Returns:
            Set of tag names that exist in at least one game.
        """
        if not self.database:
            return set()
        
        tags = set()
        games = self.database.get_all_games()
        
        for game in games:
            try:
                import chess.pgn
                from io import StringIO
                
                # Parse PGN to get headers
                pgn_io = StringIO(game.pgn)
                chess_game = chess.pgn.read_game(pgn_io)
                
                if chess_game:
                    # Add all tag names from headers
                    tags.update(chess_game.headers.keys())
            except Exception:
                # Skip games that fail to parse
                continue
        
        return tags
    
    def _on_value_source_changed(self) -> None:
        """Handle value source selection change."""
        is_copy_mode = self.copy_from_tag_radio.isChecked()
        is_fixed_mode = self.fixed_value_radio.isChecked()
        
        # Show/hide source tag selection
        self.source_tag_combo.setVisible(is_copy_mode)
        self.source_tag_label.setVisible(is_copy_mode)
        
        # Show/hide fixed value input
        self.fixed_value_input.setVisible(is_fixed_mode)
        self.fixed_value_label.setVisible(is_fixed_mode)
        
        # Enable/disable fixed value input
        self.fixed_value_input.setEnabled(is_fixed_mode)
    
    def _on_apply_clicked(self) -> None:
        """Handle apply button click."""
        if not self.database:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "Error", "No database selected", self)
            return
        
        if self._operation_in_progress:
            return
        
        # Get tag name
        tag_name = self.tag_combo.currentText().strip()
        if not tag_name:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "Error", "Please enter a tag name", self)
            return
        
        # Get game indices
        game_indices = None
        if self.selected_games_radio.isChecked():
            game_indices = self.controller.get_selected_game_indices()
            if not game_indices:
                from app.views.message_dialog import MessageDialog
                MessageDialog.show_warning(self.config, "Error", "No games selected", self)
                return
        
        # Disable controls during operation
        self._set_controls_enabled(False)
        self._operation_in_progress = True
        
        try:
            if self.add_tag_radio.isChecked():
                # Add tag operation
                tag_value = None
                source_tag = None
                
                if self.fixed_value_radio.isChecked():
                    # Fixed value (empty string if input is empty)
                    tag_value = self.fixed_value_input.text()
                    # If empty, tag_value will be empty string (not None)
                    # This will result in adding tag with empty value
                elif self.copy_from_tag_radio.isChecked():
                    # Copy from tag
                    source_tag = self.source_tag_combo.currentText().strip()
                    if not source_tag:
                        from app.views.message_dialog import MessageDialog
                        MessageDialog.show_warning(self.config, "Error", "Please enter a source tag name", self)
                        self._set_controls_enabled(True)
                        self._operation_in_progress = False
                        return
                    
                    if source_tag == tag_name:
                        from app.views.message_dialog import MessageDialog
                        MessageDialog.show_warning(self.config, "Error", "Source and target tags must be different", self)
                        self._set_controls_enabled(True)
                        self._operation_in_progress = False
                        return
                # If neither is checked (shouldn't happen), tag_value and source_tag both None = empty value
                
                result = self.controller.add_tag(
                    self.database,
                    tag_name,
                    tag_value,
                    source_tag,
                    game_indices
                )
            else:
                # Remove tag operation
                result = self.controller.remove_tag(
                    self.database,
                    tag_name,
                    game_indices
                )
            
            if not result.success:
                from app.views.message_dialog import MessageDialog
                MessageDialog.show_warning(self.config, "Error", result.error_message or "Operation failed", self)
                self._set_controls_enabled(True)
                self._operation_in_progress = False
                return
            
            # Show success message
            self._show_success_dialog(
                "Bulk Tag Complete",
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
        self.tag_combo.setEnabled(enabled)
        self.add_tag_radio.setEnabled(enabled)
        self.remove_tag_radio.setEnabled(enabled)
        self.fixed_value_radio.setEnabled(enabled)
        self.copy_from_tag_radio.setEnabled(enabled)
        self.fixed_value_input.setEnabled(enabled and self.fixed_value_radio.isChecked() and not self.copy_from_tag_radio.isChecked())
        self.source_tag_combo.setEnabled(enabled)
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
        title_font_size = scale_font_size(title_config.get('font_size', 14))
        title_padding = title_config.get('padding', 5)
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setStyleSheet(f"font-size: {title_font_size}pt; padding: {title_padding}px;")
        layout.addWidget(title_label)
        
        # Message
        from app.utils.font_utils import scale_font_size
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

