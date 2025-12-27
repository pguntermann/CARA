"""Bulk clean PGN dialog for database operations."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QCheckBox,
    QPushButton,
    QGroupBox,
    QSizePolicy,
    QWidget,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPalette, QColor, QFont
from typing import Optional, Dict, Any

from app.controllers.bulk_clean_pgn_controller import BulkCleanPgnController
from app.models.database_model import DatabaseModel


class BulkCleanPgnDialog(QDialog):
    """Dialog for bulk PGN cleaning operations on databases."""
    
    def __init__(self, config: Dict[str, Any], bulk_clean_pgn_controller: BulkCleanPgnController,
                 database: Optional[DatabaseModel], parent=None) -> None:
        """Initialize the bulk clean PGN dialog.
        
        Args:
            config: Configuration dictionary.
            bulk_clean_pgn_controller: BulkCleanPgnController instance.
            database: Optional DatabaseModel instance (active database).
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.controller = bulk_clean_pgn_controller
        self.database = database
        
        # Store fixed size
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_clean_pgn', {})
        width = dialog_config.get('width', 500)
        height = dialog_config.get('height', 400)
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
        self.setWindowTitle("Bulk Clean PGN")
    
    def _load_config(self) -> None:
        """Load configuration values from config.json."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_clean_pgn", {})
        
        # Dialog dimensions
        self.dialog_width = dialog_config.get("width", 500)
        self.dialog_height = dialog_config.get("height", 400)
        
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
        
        # Buttons
        buttons_config = dialog_config.get("buttons", {})
        self.button_width = buttons_config.get("width", 120)
        self.button_height = buttons_config.get("height", 30)
        self.button_spacing = buttons_config.get("spacing", 10)
        
        # Labels
        labels_config = dialog_config.get("labels", {})
        self.label_font_family = labels_config.get("font_family", "Helvetica Neue")
        from app.utils.font_utils import resolve_font_family, scale_font_size
        self.label_font_size = int(scale_font_size(labels_config.get("font_size", 11)))
        self.label_text_color = QColor(*labels_config.get("text_color", [200, 200, 200]))
        
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
        
        # Cleaning Options group
        options_group = QGroupBox("Cleaning Options")
        options_container = QWidget()
        options_container_layout = QVBoxLayout(options_container)
        options_container_layout.setContentsMargins(0, 0, 0, 0)
        options_container_layout.setSpacing(0)
        
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_clean_pgn", {})
        groups_config = dialog_config.get("groups", {})
        options_content_margins = groups_config.get("content_margins", [10, 20, 10, 15])
        
        # Quick selection buttons (ABOVE checkboxes)
        if self.quick_select_enabled:
            quick_select_layout = QHBoxLayout()
            quick_select_layout.setSpacing(self.quick_select_spacing)
            quick_select_layout.setContentsMargins(
                options_content_margins[0],
                0,
                options_content_margins[2],
                0
            )
            
            self.select_all_button = QPushButton("Select All")
            self.select_all_button.setFixedSize(self.quick_select_width, self.quick_select_height)
            self.select_all_button.clicked.connect(self._on_select_all_clicked)
            quick_select_layout.addWidget(self.select_all_button)
            
            self.deselect_all_button = QPushButton("Deselect All")
            self.deselect_all_button.setFixedSize(self.quick_select_width, self.quick_select_height)
            self.deselect_all_button.clicked.connect(self._on_deselect_all_clicked)
            quick_select_layout.addWidget(self.deselect_all_button)
            
            quick_select_layout.addStretch()
            
            options_container_layout.addLayout(quick_select_layout)
            
            # Add spacing between buttons and checkboxes
            options_container_layout.addSpacing(10)
        
        # Checkboxes grid layout
        options_layout = QGridLayout()
        # Use a larger spacing value for better visual separation (checkbox_spacing is for checkbox indicator spacing)
        # Set both vertical and horizontal spacing for proper separation
        options_layout.setVerticalSpacing(10)  # Vertical spacing between rows
        options_layout.setHorizontalSpacing(15)  # Horizontal spacing between columns
        options_layout.setContentsMargins(
            options_content_margins[0],
            0,
            options_content_margins[2],
            options_content_margins[3]
        )
        
        # Create checkboxes for each cleaning option
        self.remove_comments_check = QCheckBox("Remove Comments")
        self.remove_variations_check = QCheckBox("Remove Variations")
        self.remove_non_standard_tags_check = QCheckBox("Remove Non-Standard Tags")
        self.remove_annotations_check = QCheckBox("Remove Annotations")
        self.remove_results_check = QCheckBox("Remove Results")
        
        # Arrange checkboxes in 2 columns: 3 in first column, 2 in second column
        options_layout.addWidget(self.remove_comments_check, 0, 0)
        options_layout.addWidget(self.remove_variations_check, 1, 0)
        options_layout.addWidget(self.remove_non_standard_tags_check, 2, 0)
        options_layout.addWidget(self.remove_annotations_check, 0, 1)
        options_layout.addWidget(self.remove_results_check, 1, 1)
        
        options_container_layout.addLayout(options_layout)
        options_group.setLayout(QVBoxLayout())
        options_group.layout().setContentsMargins(0, 0, 0, 0)
        options_group.layout().addWidget(options_container)
        main_layout.addWidget(options_group)
        
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
        
        # Apply button styling using StyleManager (uses unified config)
        buttons_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_clean_pgn", {}).get("buttons", {})
        bg_color = self.config.get("ui", {}).get("dialogs", {}).get("bulk_clean_pgn", {}).get("background_color", [40, 40, 45])
        border_color = self.config.get("ui", {}).get("dialogs", {}).get("bulk_clean_pgn", {}).get("border_color", [60, 60, 65])
        
        button_width = buttons_config.get("width", 120)
        button_height = buttons_config.get("height", 30)
        bg_color_list = [bg_color[0], bg_color[1], bg_color[2]]
        border_color_list = [border_color[0], border_color[1], border_color[2]]
        
        from app.views.style import StyleManager
        main_buttons = [self.apply_button, self.cancel_button]
        StyleManager.style_buttons(
            main_buttons,
            self.config,
            bg_color_list,
            border_color_list,
            min_width=button_width,
            min_height=button_height
        )
        
        # Apply group box styling
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_clean_pgn", {})
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
        
        # Apply checkbox styling
        self._apply_checkbox_styling()
        
        # Apply quick select button styling
        if self.quick_select_enabled and hasattr(self, 'select_all_button'):
            self._apply_quick_select_button_styling()
    
    def _apply_checkbox_styling(self) -> None:
        """Apply checkbox styling to all checkboxes."""
        from app.views.style import StyleManager
        from pathlib import Path
        
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_clean_pgn", {})
        inputs_config = dialog_config.get("inputs", {})
        input_border_color = inputs_config.get("border_color", [60, 60, 65])
        input_bg_color = inputs_config.get("background_color", [30, 30, 35])
        
        # Get checkmark icon path
        project_root = Path(__file__).parent.parent.parent
        checkmark_path = project_root / "app" / "resources" / "icons" / "checkmark.svg"
        
        # Convert QColor to [R, G, B] lists
        text_color = [self.label_text_color.red(), self.label_text_color.green(), self.label_text_color.blue()]
        
        # Get all checkboxes and apply styling
        checkboxes = self.findChildren(QCheckBox)
        StyleManager.style_checkboxes(
            checkboxes,
            self.config,
            text_color,
            self.label_font_family,
            self.label_font_size,
            input_bg_color,
            input_border_color,
            checkmark_path
        )
    
    def _apply_quick_select_button_styling(self) -> None:
        """Apply styling to quick select buttons."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_clean_pgn", {})
        buttons_config = dialog_config.get("buttons", {})
        bg_color = dialog_config.get("background_color", [40, 40, 45])
        border_color = dialog_config.get("border_color", [60, 60, 65])
        
        # Apply quick select button styling using StyleManager (uses unified config)
        from app.views.style import StyleManager
        bg_color_list = [bg_color[0], bg_color[1], bg_color[2]]
        border_color_list = [border_color[0], border_color[1], border_color[2]]
        quick_select_buttons = [self.select_all_button, self.deselect_all_button]
        StyleManager.style_buttons(
            quick_select_buttons,
            self.config,
            bg_color_list,
            border_color_list
        )
    
    def _on_apply_clicked(self) -> None:
        """Handle apply button click."""
        if self._operation_in_progress:
            return
        
        if not self.database:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "No Database", "No database is currently active.", self)
            return
        
        # Check if at least one option is selected
        remove_comments = self.remove_comments_check.isChecked()
        remove_variations = self.remove_variations_check.isChecked()
        remove_non_standard_tags = self.remove_non_standard_tags_check.isChecked()
        remove_annotations = self.remove_annotations_check.isChecked()
        remove_results = self.remove_results_check.isChecked()
        
        if not any([remove_comments, remove_variations, remove_non_standard_tags, 
                   remove_annotations, remove_results]):
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "No Options Selected", "Please select at least one cleaning option.", self)
            return
        
        # Get selected game indices (if any)
        game_indices = None
        # For now, process all games (can add selection support later if needed)
        
        # Disable controls during operation
        self._set_controls_enabled(False)
        self._operation_in_progress = True
        
        # Perform cleaning operation
        result = self.controller.clean_pgn(
            self.database,
            remove_comments,
            remove_variations,
            remove_non_standard_tags,
            remove_annotations,
            remove_results,
            game_indices
        )
        
        # Re-enable controls
        self._set_controls_enabled(True)
        self._operation_in_progress = False
        
        if not result.success:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Error",
                f"Failed to clean PGN: {result.error_message or 'Operation failed'}",
                self
            )
            return
        
        # Show success message
        from app.views.message_dialog import MessageDialog
        MessageDialog.show_information(
            self.config,
            "Bulk Clean PGN Complete",
            f"Processed {result.games_processed} game(s).\n"
            f"Updated {result.games_updated} game(s).\n"
            f"Failed {result.games_failed} game(s).",
            self
        )
        
        # Close dialog on success
        self.accept()
    
    def _on_select_all_clicked(self) -> None:
        """Handle Select All button click."""
        self.remove_comments_check.setChecked(True)
        self.remove_variations_check.setChecked(True)
        self.remove_non_standard_tags_check.setChecked(True)
        self.remove_annotations_check.setChecked(True)
        self.remove_results_check.setChecked(True)
    
    def _on_deselect_all_clicked(self) -> None:
        """Handle Deselect All button click."""
        self.remove_comments_check.setChecked(False)
        self.remove_variations_check.setChecked(False)
        self.remove_non_standard_tags_check.setChecked(False)
        self.remove_annotations_check.setChecked(False)
        self.remove_results_check.setChecked(False)
    
    def _set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable dialog controls.
        
        Args:
            enabled: If True, enable controls; if False, disable them.
        """
        self.remove_comments_check.setEnabled(enabled)
        self.remove_variations_check.setEnabled(enabled)
        self.remove_non_standard_tags_check.setEnabled(enabled)
        self.remove_annotations_check.setEnabled(enabled)
        self.remove_results_check.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)
        self.cancel_button.setEnabled(enabled)
        if self.quick_select_enabled and hasattr(self, 'select_all_button'):
            self.select_all_button.setEnabled(enabled)
            self.deselect_all_button.setEnabled(enabled)

