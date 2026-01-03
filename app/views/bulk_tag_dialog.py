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
        
        # Buttons
        buttons_config = dialog_config.get("buttons", {})
        self.button_width = buttons_config.get("width", 120)
        self.button_height = buttons_config.get("height", 30)
        self.button_spacing = buttons_config.get("spacing", 10)
        
        # Inputs
        inputs_config = dialog_config.get("inputs", {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
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
        # Set spacing to 0 to disable automatic spacing - we'll use explicit spacing instead
        main_layout.setSpacing(0)
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
        buttons_layout.setSpacing(self.button_spacing)
        buttons_layout.addStretch()
        
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._on_apply_clicked)
        buttons_layout.addWidget(self.apply_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_button)
        
        # Add spacing before buttons
        main_layout.addSpacing(self.section_spacing)
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
        from app.utils.font_utils import scale_font_size
        font_size = scale_font_size(self.config.get("ui", {}).get("dialogs", {}).get("bulk_tag", {}).get("font_size", 11))
        
        button_width = buttons_config.get("width", 120)
        button_height = buttons_config.get("height", 30)
        button_border_radius = buttons_config.get("border_radius", 3)
        button_padding = buttons_config.get("padding", 5)
        button_bg_offset = buttons_config.get("background_offset", 20)
        button_hover_offset = buttons_config.get("hover_background_offset", 30)
        button_pressed_offset = buttons_config.get("pressed_background_offset", 10)
        
        # Apply button styling using StyleManager (uses unified config)
        from app.views.style import StyleManager
        StyleManager.style_buttons(
            [self.apply_button, self.cancel_button],
            self.config,
            bg_color,
            border_color,
            min_width=button_width,
            min_height=button_height
        )
        
        # Get selection colors from config (use defaults if not available)
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_tag", {})
        inputs_config = dialog_config.get("inputs", {})
        selection_bg = inputs_config.get('selection_background_color', [70, 90, 130])
        selection_text = inputs_config.get('selection_text_color', [240, 240, 240])
        
        # Apply unified line edit styling using StyleManager
        from app.views.style import StyleManager
        
        # Get padding from config (preserve existing format for alignment)
        # self.input_padding is already in [horizontal, vertical] format from _load_config
        input_padding = self.input_padding if isinstance(self.input_padding, list) and len(self.input_padding) == 2 else [8, 6]
        
        # Use dialog-specific background color and font to match combobox styling
        bg_color = [self.input_bg_color.red(), self.input_bg_color.green(), self.input_bg_color.blue()]
        
        StyleManager.style_line_edits(
            [self.fixed_value_input],
            self.config,
            font_family=self.input_font_family,  # Match original dialog font
            font_size=self.input_font_size,  # Match original dialog font size
            bg_color=bg_color,  # Match combobox background color
            padding=input_padding  # Preserve existing padding for alignment
        )
        
        # Apply combobox styling using StyleManager
        
        # Get focus border color for combobox
        focus_border_color = inputs_config.get('focus_border_color', [0, 120, 212])
        
        # Convert QColor to [R, G, B] lists
        text_color = [self.input_text_color.red(), self.input_text_color.green(), self.input_text_color.blue()]
        bg_color = [self.input_bg_color.red(), self.input_bg_color.green(), self.input_bg_color.blue()]
        border_color = [self.input_border_color.red(), self.input_border_color.green(), self.input_border_color.blue()]
        
        # Style comboboxes separately - tag_combo is editable, source_tag_combo is not
        # Tag combobox (editable)
        StyleManager.style_comboboxes(
            [self.tag_combo],
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
            editable=True
        )
        # Source tag combobox (not editable)
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
        
        # Apply group box styling
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_tag", {})
        groups_config = dialog_config.get("groups", {})
        bg_color = dialog_config.get("background_color", [40, 40, 45])
        border_color = dialog_config.get("border_color", [60, 60, 65])
        
        group_bg_color = groups_config.get("background_color")  # None = use unified default
        group_border_color = groups_config.get("border_color", border_color) if "border_color" in groups_config else border_color
        group_border_radius = groups_config.get("border_radius", 5)
        from app.utils.font_utils import resolve_font_family, scale_font_size
        group_title_font_family = resolve_font_family(groups_config.get("title_font_family", "Helvetica Neue"))
        group_title_font_size = scale_font_size(groups_config.get("title_font_size", 11))
        group_title_color = groups_config.get("title_color", [240, 240, 240])
        group_content_margins = groups_config.get("content_margins", [10, 15, 10, 10])
        group_margin_top = groups_config.get("margin_top", 10)
        group_padding_top = groups_config.get("padding_top", 5)
        
        group_border_width = groups_config.get("border_width", 1)
        group_title_left = groups_config.get("title_left", 10)
        group_title_padding = groups_config.get("title_padding", [0, 5])
        
        group_boxes = list(self.findChildren(QGroupBox))
        if group_boxes:
            StyleManager.style_group_boxes(
                group_boxes,
                self.config,
                border_color=group_border_color,
                border_width=group_border_width,
                border_radius=group_border_radius,
                bg_color=group_bg_color,
                margin_top=group_margin_top,
                padding_top=group_padding_top,
                title_font_family=group_title_font_family,
                title_font_size=group_title_font_size,
                title_color=group_title_color,
                title_left=group_title_left,
                title_padding=group_title_padding,
                content_margins=group_content_margins
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
        
        # Apply radio button styling using StyleManager (uses unified config)
        from app.views.style import StyleManager
        radio_buttons = list(self.findChildren(QRadioButton))
        if radio_buttons:
            StyleManager.style_radio_buttons(radio_buttons, self.config)
        
        # Apply checkbox styling to ensure consistent font size and style
        self._apply_checkbox_styling()
    
    def _apply_checkbox_styling(self) -> None:
        """Apply checkbox styling to all checkboxes."""
        from app.views.style import StyleManager
        from pathlib import Path
        
        input_border_color = self.input_border_color
        input_bg_color = self.input_bg_color
        
        # Get checkmark icon path
        project_root = Path(__file__).parent.parent.parent
        checkmark_path = project_root / "app" / "resources" / "icons" / "checkmark.svg"
        
        # Convert QColor to [R, G, B] lists
        text_color = [self.label_text_color.red(), self.label_text_color.green(), self.label_text_color.blue()]
        input_bg = [input_bg_color.red(), input_bg_color.green(), input_bg_color.blue()]
        input_border = [input_border_color.red(), input_border_color.green(), input_border_color.blue()]
        
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
        raw_tag_name = self.tag_combo.currentText().strip()
        if not raw_tag_name:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "Error", "Please enter a tag name", self)
            return
        
        # Sanitize tag name using controller method
        tag_name = self.controller.sanitize_tag_name(raw_tag_name)
        if not tag_name:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "Error", "Tag name contains only invalid characters", self)
            return
        
        # If the tag name was modified, update the combobox to show the sanitized version
        if tag_name != raw_tag_name:
            # Update the combobox to show the sanitized tag name
            self.tag_combo.setCurrentText(tag_name)
        
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
                    raw_source_tag = self.source_tag_combo.currentText().strip()
                    if not raw_source_tag:
                        from app.views.message_dialog import MessageDialog
                        MessageDialog.show_warning(self.config, "Error", "Please enter a source tag name", self)
                        self._set_controls_enabled(True)
                        self._operation_in_progress = False
                        return
                    
                    # Sanitize source tag name using controller method
                    source_tag = self.controller.sanitize_tag_name(raw_source_tag)
                    if not source_tag:
                        from app.views.message_dialog import MessageDialog
                        MessageDialog.show_warning(self.config, "Error", "Source tag name contains only invalid characters", self)
                        self._set_controls_enabled(True)
                        self._operation_in_progress = False
                        return
                    
                    # Update combobox if tag name was modified
                    if source_tag != raw_source_tag:
                        self.source_tag_combo.setCurrentText(source_tag)
                    
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
        
        # Import scale_font_size at the beginning of the method
        from app.utils.font_utils import scale_font_size
        
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
        button_font_size = scale_font_size(buttons_config.get('font_size', 10))
        text_color = buttons_config.get('text_color', [200, 200, 200])
        border_color = buttons_config.get('border_color', [60, 60, 65])
        
        # Apply button styling using StyleManager (uses unified config)
        from app.views.style import StyleManager
        ok_button = QPushButton("OK")
        StyleManager.style_buttons(
            [ok_button],
            self.config,
            bg_color,
            border_color,
            min_width=button_width,
            min_height=button_height
        )
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



