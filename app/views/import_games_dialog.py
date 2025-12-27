"""Dialog for importing games from online platforms (Lichess, Chess.com)."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QSizePolicy,
    QWidget,
    QDateEdit,
    QSpinBox,
    QCheckBox,
)
from PyQt6.QtCore import Qt, QSize, QDate
from PyQt6.QtGui import QPalette, QColor, QFont
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from app.models.database_model import DatabaseModel




class ImportGamesDialog(QDialog):
    """Dialog for importing games from online platforms."""
    
    def __init__(
        self,
        config: Dict[str, Any],
        database_controller,
        active_database: Optional[DatabaseModel],
        parent=None
    ) -> None:
        """Initialize the import games dialog.
        
        Args:
            config: Configuration dictionary.
            database_controller: DatabaseController instance.
            active_database: Optional active DatabaseModel instance.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.database_controller = database_controller
        self.active_database = active_database
        
        self._load_config()
        self._setup_ui()
        self._apply_styling()
        self.setWindowTitle("Import Games from Online")
    
    def _load_config(self) -> None:
        """Load configuration values from config.json."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("import_games", {})
        
        # Dialog dimensions
        self.dialog_width = dialog_config.get("width", 550)
        self.dialog_height = dialog_config.get("height", 600)
        
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
        self.form_spacing = spacing_config.get("form", 10)
        
        # Buttons
        buttons_config = dialog_config.get("buttons", {})
        self.button_width = buttons_config.get("width", 120)
        self.button_height = buttons_config.get("height", 30)
        self.button_spacing = buttons_config.get("spacing", 10)
        
        # Labels
        labels_config = dialog_config.get("labels", {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
        self.label_font_family = resolve_font_family(labels_config.get("font_family", "Helvetica Neue"))
        self.label_font_size = scale_font_size(labels_config.get("font_size", 11))
        self.label_text_color = QColor(*labels_config.get("text_color", [200, 200, 200]))
        self.label_minimum_width = labels_config.get("minimum_width", 120)
        
        # Inputs
        inputs_config = dialog_config.get("inputs", {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
        input_font_family_raw = inputs_config.get("font_family", "Cascadia Mono")
        self.input_font_family = resolve_font_family(input_font_family_raw)
        self.input_font_size = scale_font_size(inputs_config.get("font_size", 11))
        self.input_text_color = QColor(*inputs_config.get("text_color", [240, 240, 240]))
        self.input_bg_color = QColor(*inputs_config.get("background_color", [30, 30, 35]))
        self.input_border_color = QColor(*inputs_config.get("border_color", [60, 60, 65]))
        self.input_focus_border_color = QColor(*inputs_config.get("focus_border_color", [70, 90, 130]))
        self.input_border_radius = inputs_config.get("border_radius", 3)
        self.input_padding = inputs_config.get("padding", [8, 6])
        self.input_minimum_width = inputs_config.get("minimum_width", 200)
        self.input_minimum_height = inputs_config.get("minimum_height", 30)
        
        # Groups
        groups_config = dialog_config.get("groups", {})
        self.group_content_margins = groups_config.get("content_margins", [10, 20, 10, 15])
        
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
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        # Set fixed size
        self.setFixedSize(self.dialog_width, self.dialog_height)
        
        # Set background color
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), self.bg_color)
        self.setPalette(palette)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(self.layout_spacing)
        main_layout.setContentsMargins(
            self.layout_margins[0],
            self.layout_margins[1],
            self.layout_margins[2],
            self.layout_margins[3]
        )
        
        # Destination group (moved to top for consistency)
        destination_group = QGroupBox("Destination")
        destination_layout = QHBoxLayout()
        destination_layout.setSpacing(self.section_spacing)
        destination_layout.setContentsMargins(
            self.group_content_margins[0],
            self.group_content_margins[1],
            self.group_content_margins[2],
            self.group_content_margins[3]
        )
        
        self.destination_button_group = QButtonGroup(self)
        self.clipboard_radio = QRadioButton("Clipboard Database")
        self.active_radio = QRadioButton("Active Database")
        self.destination_button_group.addButton(self.clipboard_radio, 0)
        self.destination_button_group.addButton(self.active_radio, 1)
        
        # Set default based on availability
        if self.active_database:
            self.active_radio.setChecked(True)
        else:
            self.clipboard_radio.setChecked(True)
            self.active_radio.setEnabled(False)
        
        destination_layout.addWidget(self.clipboard_radio)
        destination_layout.addWidget(self.active_radio)
        destination_layout.addStretch()
        destination_group.setLayout(destination_layout)
        main_layout.addWidget(destination_group)
        
        # Platform selection group
        platform_group = QGroupBox("Platform")
        platform_layout = QFormLayout()
        platform_layout.setSpacing(self.form_spacing)
        # Set field growth policy to make fields expand
        platform_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        # Set alignment for macOS compatibility (left-align labels and form)
        platform_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        platform_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        platform_layout.setContentsMargins(
            self.group_content_margins[0],
            self.group_content_margins[1],
            self.group_content_margins[2],
            self.group_content_margins[3]
        )
        
        self.platform_combo = QComboBox()
        self.platform_combo.addItems(["Lichess", "Chess.com"])
        self.platform_combo.currentTextChanged.connect(self._on_platform_changed)
        self.platform_combo.setMinimumWidth(self.input_minimum_width)
        self.platform_combo.setMinimumHeight(self.input_minimum_height)
        self.platform_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        platform_label = QLabel("Platform:")
        platform_label.setMinimumWidth(self.label_minimum_width)
        platform_layout.addRow(platform_label, self.platform_combo)
        
        self.username_input = QLineEdit()
        self.username_input.setMinimumWidth(self.input_minimum_width)
        self.username_input.setMinimumHeight(self.input_minimum_height)
        self.username_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        username_label = QLabel("Username:")
        username_label.setMinimumWidth(self.label_minimum_width)
        platform_layout.addRow(username_label, self.username_input)
        
        platform_group.setLayout(platform_layout)
        main_layout.addWidget(platform_group)
        
        # Filters group
        filters_group = QGroupBox("Filters")
        filters_layout = QFormLayout()
        filters_layout.setSpacing(self.form_spacing)
        # Set field growth policy to make fields expand
        filters_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        # Set alignment for macOS compatibility (left-align labels and form)
        filters_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        filters_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        filters_layout.setContentsMargins(
            self.group_content_margins[0],
            self.group_content_margins[1],
            self.group_content_margins[2],
            self.group_content_margins[3]
        )
        
        # Max games limit
        self.limit_checkbox = QCheckBox("Limit number of games")
        self.limit_checkbox.setChecked(False)
        self.limit_checkbox.toggled.connect(self._on_limit_toggled)
        filters_layout.addRow("", self.limit_checkbox)
        
        self.max_games_spin = QSpinBox()
        self.max_games_spin.setMinimum(1)
        self.max_games_spin.setMaximum(999999)
        self.max_games_spin.setValue(1000)
        self.max_games_spin.setEnabled(False)
        self.max_games_spin.setMinimumWidth(self.input_minimum_width)
        self.max_games_spin.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.max_games_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        max_games_label = QLabel("Maximum games:")
        max_games_label.setMinimumWidth(self.label_minimum_width)
        filters_layout.addRow(max_games_label, self.max_games_spin)
        
        # Date range
        self.date_range_checkbox = QCheckBox("Filter by date range")
        self.date_range_checkbox.setChecked(False)
        self.date_range_checkbox.toggled.connect(self._on_date_range_toggled)
        filters_layout.addRow("", self.date_range_checkbox)
        
        # Since date
        self.since_date_edit = QDateEdit()
        self.since_date_edit.setCalendarPopup(True)
        self.since_date_edit.setDate(QDate.currentDate().addYears(-1))
        self.since_date_edit.setEnabled(False)
        self.since_date_edit.setMinimumWidth(self.input_minimum_width)
        self.since_date_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        since_date_label = QLabel("From date:")
        since_date_label.setMinimumWidth(self.label_minimum_width)
        filters_layout.addRow(since_date_label, self.since_date_edit)
        
        # Until date
        self.until_date_edit = QDateEdit()
        self.until_date_edit.setCalendarPopup(True)
        self.until_date_edit.setDate(QDate.currentDate())
        self.until_date_edit.setEnabled(False)
        self.until_date_edit.setMinimumWidth(self.input_minimum_width)
        self.until_date_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        until_date_label = QLabel("To date:")
        until_date_label.setMinimumWidth(self.label_minimum_width)
        filters_layout.addRow(until_date_label, self.until_date_edit)
        
        # Game type (Lichess only)
        self.game_type_label = QLabel("Game type:")
        self.game_type_label.setMinimumWidth(self.label_minimum_width)
        self.game_type_combo = QComboBox()
        self.game_type_combo.addItems(["All", "Blitz", "Rapid", "Classical", "Bullet", "Correspondence"])
        self.game_type_combo.setCurrentText("All")
        self.game_type_combo.setMinimumWidth(self.input_minimum_width)
        self.game_type_combo.setMinimumHeight(self.input_minimum_height)
        self.game_type_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        filters_layout.addRow(self.game_type_label, self.game_type_combo)
        
        filters_group.setLayout(filters_layout)
        main_layout.addWidget(filters_group)
        
        main_layout.addStretch()
        
        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(self._on_import_clicked)
        self.import_button.setDefault(True)
        buttons_layout.addWidget(self.import_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(buttons_layout)
    
    def _on_platform_changed(self, platform: str) -> None:
        """Handle platform selection change."""
        # Game type filter is only available for Lichess
        is_lichess = platform == "Lichess"
        self.game_type_label.setEnabled(is_lichess)
        self.game_type_combo.setEnabled(is_lichess)
    
    def _on_limit_toggled(self, checked: bool) -> None:
        """Handle limit checkbox toggle."""
        self.max_games_spin.setEnabled(checked)
    
    def _on_date_range_toggled(self, checked: bool) -> None:
        """Handle date range checkbox toggle."""
        self.since_date_edit.setEnabled(checked)
        self.until_date_edit.setEnabled(checked)
    
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
    
    def _apply_styling(self) -> None:
        """Apply styling from config.json."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("import_games", {})
        bg_color = dialog_config.get("background_color", [40, 40, 45])
        border_color = dialog_config.get("border_color", [60, 60, 65])
        text_color = dialog_config.get("text_color", [200, 200, 200])
        from app.utils.font_utils import scale_font_size
        font_size = scale_font_size(dialog_config.get("font_size", 11))
        
        # Apply button styling using StyleManager (uses unified config)
        buttons_config = dialog_config.get("buttons", {})
        button_width = buttons_config.get("width", 120)
        button_height = buttons_config.get("height", 30)
        border_color = dialog_config.get("border_color", [60, 60, 65])
        bg_color_list = [bg_color[0], bg_color[1], bg_color[2]]
        border_color_list = [border_color[0], border_color[1], border_color[2]]
        
        from app.views.style import StyleManager
        all_buttons = self.findChildren(QPushButton)
        StyleManager.style_buttons(
            all_buttons,
            self.config,
            bg_color_list,
            border_color_list,
            min_width=button_width,
            min_height=button_height
        )
        
        # Get selection colors from config (use defaults if not available)
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
        
        # Apply styling to QLineEdit widgets
        StyleManager.style_line_edits(
            [self.username_input],
            self.config,
            font_family=self.input_font_family,  # Match original dialog font
            font_size=self.input_font_size,  # Match original dialog font size
            bg_color=bg_color,  # Match combobox background color
            padding=input_padding  # Preserve existing padding for alignment
        )
        
        # Separate styling for QSpinBox and QDateEdit
        spinbox_dateedit_style = (
            f"QSpinBox, QDateEdit {{"
            f"background-color: rgb({self.input_bg_color.red()}, {self.input_bg_color.green()}, {self.input_bg_color.blue()});"
            f"border: 1px solid rgb({self.input_border_color.red()}, {self.input_border_color.green()}, {self.input_border_color.blue()});"
            f"border-radius: {self.input_border_radius}px;"
            f"padding: {self.input_padding[1]}px {self.input_padding[0]}px;"
            f"color: rgb({self.input_text_color.red()}, {self.input_text_color.green()}, {self.input_text_color.blue()});"
            f"font-family: {self.input_font_family};"
            f"font-size: {self.input_font_size}pt;"
            f"}}"
            f"QSpinBox:disabled, QDateEdit:disabled {{"
            f"background-color: rgb({self.input_bg_color.red() // 2}, {self.input_bg_color.green() // 2}, {self.input_bg_color.blue() // 2});"
            f"color: rgb({self.input_text_color.red() // 2}, {self.input_text_color.green() // 2}, {self.input_text_color.blue() // 2});"
            f"}}"
            f"QSpinBox::up-button, QSpinBox::down-button {{"
            f"width: 0px;"
            f"}}"
        )
        
        self.max_games_spin.setStyleSheet(spinbox_dateedit_style)
        self.since_date_edit.setStyleSheet(spinbox_dateedit_style)
        self.until_date_edit.setStyleSheet(spinbox_dateedit_style)
        
        # Apply combobox styling using StyleManager
        from app.views.style import StyleManager
        comboboxes = [self.platform_combo, self.game_type_combo]
        text_color = [self.input_text_color.red(), self.input_text_color.green(), self.input_text_color.blue()]
        bg_color = [self.input_bg_color.red(), self.input_bg_color.green(), self.input_bg_color.blue()]
        border_color = [self.input_border_color.red(), self.input_border_color.green(), self.input_border_color.blue()]
        focus_border_color = [self.input_focus_border_color.red(), self.input_focus_border_color.green(), self.input_focus_border_color.blue()]
        
        StyleManager.style_comboboxes(
            comboboxes,
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
        
        # Apply checkbox styling
        self._apply_checkbox_styling()
        
        # Label styling
        label_style = (
            f"QLabel {{"
            f"color: rgb({self.label_text_color.red()}, {self.label_text_color.green()}, {self.label_text_color.blue()});"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.label_font_size}pt;"
            f"}}"
        )
        
        for label in self.findChildren(QLabel):
            label.setStyleSheet(label_style)
        
        # Group box styling
        groups_config = dialog_config.get("groups", {})
        group_bg_color = groups_config.get("background_color", bg_color) if "background_color" in groups_config else bg_color
        group_border_color = groups_config.get("border_color", border_color) if "border_color" in groups_config else border_color
        group_border_radius = groups_config.get("border_radius", 5)
        group_title_font_family = groups_config.get("title_font_family", "Helvetica Neue")
        group_title_font_size = scale_font_size(groups_config.get("title_font_size", 11))
        group_title_color = groups_config.get("title_color", [240, 240, 240])
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
                    self.group_content_margins[0],
                    self.group_content_margins[1],
                    self.group_content_margins[2],
                    self.group_content_margins[3]
                )
        
        # Note: Checkbox styling is already applied by _apply_checkbox_styling() above
        
        # Apply radio button styling using StyleManager (uses unified config)
        from app.views.style import StyleManager
        radio_buttons = list(self.findChildren(QRadioButton))
        if radio_buttons:
            StyleManager.style_radio_buttons(radio_buttons, self.config)
    
    def _on_import_clicked(self) -> None:
        """Handle import button click."""
        # Validate username
        username = self.username_input.text().strip()
        if not username:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Invalid Input",
                "Please enter a username",
                self
            )
            return
        
        # Get platform
        platform = self.platform_combo.currentText()
        platform_key = "lichess" if platform == "Lichess" else "chesscom"
        
        # Get filters
        max_games = None
        if self.limit_checkbox.isChecked():
            max_games = self.max_games_spin.value()
        
        since_date = None
        until_date = None
        if self.date_range_checkbox.isChecked():
            since_qdate = self.since_date_edit.date()
            until_qdate = self.until_date_edit.date()
            since_date = datetime(since_qdate.year(), since_qdate.month(), since_qdate.day())
            until_date = datetime(until_qdate.year(), until_qdate.month(), until_qdate.day())
            # Add one day to until_date to include the entire day
            until_date = until_date + timedelta(days=1)
        
        perf_type = None
        if platform_key == "lichess":
            game_type = self.game_type_combo.currentText()
            if game_type != "All":
                perf_type = game_type.lower()
        
        # Get destination database
        if self.clipboard_radio.isChecked():
            destination_model = self.database_controller.get_database_model()
        else:
            destination_model = self.active_database
            if not destination_model:
                from app.views.message_dialog import MessageDialog
                MessageDialog.show_warning(
                    self.config,
                    "No Active Database",
                    "No active database selected. Please select Clipboard Database or open a database first.",
                    self
                )
                return
        
        # Disable dialog during import
        self.setEnabled(False)
        
        # Perform import
        success, message, first_game_index = self.database_controller.import_online_games(
            platform=platform_key,
            username=username,
            model=destination_model,
            max_games=max_games,
            since_date=since_date,
            until_date=until_date,
            perf_type=perf_type
        )
        
        # Re-enable dialog
        self.setEnabled(True)
        
        if success:
            # Show success message
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_information(
                self.config,
                "Import Successful",
                message,
                self
            )
            self.accept()
        else:
            # Show error message
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Import Failed",
                message,
                self
            )

