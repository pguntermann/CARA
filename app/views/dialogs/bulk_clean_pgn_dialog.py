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
from PyQt6.QtCore import Qt, QSize, QSignalBlocker
from PyQt6.QtGui import QPalette, QColor, QFont, QShowEvent, QResizeEvent
from typing import Optional, Dict, Any

from app.controllers.bulk_clean_pgn_controller import BulkCleanPgnController
from app.models.database_model import DatabaseModel
from app.utils.bulk_operation_summary import format_bulk_operation_summary_html
from app.utils.path_display_utils import truncate_path_for_display, truncate_text_middle
from app.utils.themed_icon import themed_icon_from_svg


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
        
        # Track operation state
        self._operation_in_progress = False
        self._controls_enabled = True
        
        self._load_config()
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self._setup_ui()
        self._apply_styling()
        self._apply_configured_dialog_size()
        self.setWindowTitle("Bulk Clean PGN")
    
    def _load_config(self) -> None:
        """Load configuration values from config.json."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_clean_pgn", {})
        
        self.dialog_width = dialog_config.get("width", 500)
        self.dialog_minimum_width = dialog_config.get("minimum_width")
        self.dialog_minimum_height = dialog_config.get("minimum_height")
        self.bottom_button_top_padding = dialog_config.get("bottom_button_top_padding", 50)
        
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

        # Icon-only quick-select buttons (SVG paths + tint + px + tooltips)
        self.quick_select_select_svg = quick_select_config.get("select_all_button_icon_svg")
        self.quick_select_select_tint_rgb = quick_select_config.get("select_all_button_icon_tint_rgb")
        self.quick_select_select_icon_px = int(quick_select_config.get("select_all_button_icon_px", 18))
        self.quick_select_select_tooltip = quick_select_config.get("select_all_button_tooltip", "Select all")

        self.quick_select_deselect_svg = quick_select_config.get("deselect_all_button_icon_svg")
        self.quick_select_deselect_tint_rgb = quick_select_config.get("deselect_all_button_icon_tint_rgb")
        self.quick_select_deselect_icon_px = int(quick_select_config.get("deselect_all_button_icon_px", 18))
        self.quick_select_deselect_tooltip = quick_select_config.get("deselect_all_button_tooltip", "Deselect all")
    
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
        
        self._target_db_label = QLabel("Target Database:")
        self._target_db_label.setFont(QFont(self.label_font_family, self.label_font_size))
        db_header_layout.addWidget(self._target_db_label)
        db_label = self._target_db_label
        
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
        self.db_name_label.setWordWrap(False)
        if db_path:
            self.db_name_label.setToolTip(db_name)
        db_header_layout.addWidget(self.db_name_label)
        db_header_layout.addStretch()
        
        db_container_layout.addLayout(db_header_layout)
        
        # Path label (smaller font, below name, aligned with database name)
        if db_path:
            self._db_path_full = db_path
            self._db_name_full = db_name
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
            
            path_font_size = max(8, self.label_font_size - 2)
            path_font = QFont(self.label_font_family, path_font_size)
            path_max_width_px = max(
                80,
                self.dialog_width - self.layout_margins[0] - self.layout_margins[2] - spacer_width - 8,
            )
            path_display = truncate_path_for_display(db_path, path_max_width_px, path_font)
            self.db_path_label = QLabel(path_display)
            self.db_path_label.setToolTip(db_path)
            self.db_path_label.setFont(path_font)
            self.db_path_label.setWordWrap(False)
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
            self._db_path_full = None
            self._db_name_full = None
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
            quick_select_left_margin = max(0, options_content_margins[0] - 2)
            quick_select_layout.setContentsMargins(
                quick_select_left_margin,
                0,
                options_content_margins[2],
                0
            )
            # Keep the icon buttons aligned with the checkbox column below.
            quick_select_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            
            self.select_all_button = QPushButton()
            self.select_all_button.setFixedSize(self.button_height, self.button_height)
            self.select_all_button.setText("")
            self.select_all_button.setAccessibleName("Select All")
            self.select_all_button.clicked.connect(self._on_select_all_clicked)
            quick_select_layout.addWidget(
                self.select_all_button,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            )
            
            self.deselect_all_button = QPushButton()
            self.deselect_all_button.setFixedSize(self.button_height, self.button_height)
            self.deselect_all_button.setText("")
            self.deselect_all_button.setAccessibleName("Deselect All")
            self.deselect_all_button.clicked.connect(self._on_deselect_all_clicked)
            quick_select_layout.addWidget(
                self.deselect_all_button,
                alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            )
            
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
        options_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        # Create checkboxes for each cleaning option
        self.remove_comments_check = QCheckBox("Remove Comments")
        self.remove_variations_check = QCheckBox("Remove Variations")
        self.remove_non_standard_tags_check = QCheckBox("Remove Non-Standard Tags")
        self.remove_annotations_check = QCheckBox("Remove Annotations")

        # Track for quick-select enabled/disabled state
        self._clean_checkboxes = [
            self.remove_comments_check,
            self.remove_variations_check,
            self.remove_non_standard_tags_check,
            self.remove_annotations_check,
        ]
        for cb in self._clean_checkboxes:
            cb.stateChanged.connect(self._on_clean_checkbox_state_changed)
        
        # Arrange checkboxes in 2 columns: 3 in first column, 1 in second column
        options_layout.addWidget(
            self.remove_comments_check,
            0,
            0,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        options_layout.addWidget(
            self.remove_variations_check,
            1,
            0,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        options_layout.addWidget(
            self.remove_non_standard_tags_check,
            2,
            0,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        options_layout.addWidget(
            self.remove_annotations_check,
            0,
            1,
            alignment=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
        )
        
        options_container_layout.addLayout(options_layout)
        options_group.setLayout(QVBoxLayout())
        options_group.layout().setContentsMargins(0, 0, 0, 0)
        options_group.layout().addWidget(options_container)
        main_layout.addWidget(options_group)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(self.button_spacing)
        buttons_layout.addStretch()
        
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._on_apply_clicked)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
        buttons_layout.addWidget(self.cancel_button)
        buttons_layout.addWidget(self.apply_button)
        
        main_layout.addSpacing(self.bottom_button_top_padding)
        main_layout.addLayout(buttons_layout)
    
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
        
        group_bg_color = groups_config.get("background_color")  # None = use unified default
        group_border_color = groups_config.get("border_color", border_color) if "border_color" in groups_config else border_color
        group_border_radius = groups_config.get("border_radius", 5)
        from app.utils.font_utils import resolve_font_family, scale_font_size
        group_title_font_family = resolve_font_family(groups_config.get("title_font_family"))
        group_title_font_size = scale_font_size(groups_config.get("title_font_size", 11))
        group_title_color = groups_config.get("title_color")
        group_content_margins = groups_config.get("content_margins", [10, 20, 10, 15])
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
        
        # Apply checkbox styling
        self._apply_checkbox_styling()
        
        # Apply quick select button styling
        if self.quick_select_enabled and hasattr(self, 'select_all_button'):
            self._apply_quick_select_button_styling()
            self._update_quick_select_buttons_enabled()
    
    def showEvent(self, event: QShowEvent) -> None:
        """Override showEvent to run path truncation with actual label size (DPI-aware)."""
        super().showEvent(event)
        self._apply_configured_dialog_size()
        self._update_path_label_truncation()
        self._apply_configured_dialog_size()
        self._enforce_quick_select_square()
    
    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_path_label_truncation()
        self._enforce_quick_select_square()

    def _enforce_quick_select_square(self) -> None:
        """Keep quick-select icon buttons square after Qt layout passes."""
        if not self.quick_select_enabled:
            return
        if not hasattr(self, "select_all_button") or not hasattr(self, "deselect_all_button"):
            return
        size = self.button_height
        for btn in (self.select_all_button, self.deselect_all_button):
            btn.setFixedSize(size, size)
            btn.setMinimumSize(size, size)
            btn.setMaximumSize(size, size)
    
    def _update_path_label_truncation(self) -> None:
        """Re-truncate path and name using actual width and font (DPI-aware)."""
        if hasattr(self, 'db_name_label') and self.db_name_label.parent() and getattr(self, '_db_name_full', None) and hasattr(self, '_target_db_label'):
            container = self.db_name_label.parent()
            name_w = max(40, container.width() - self._target_db_label.width() - 8)
            self.db_name_label.setMaximumWidth(name_w)
            self.db_name_label.setWordWrap(False)
            name_font = QFont(self.db_name_label.font())
            name_font.setBold(True)
            name_display = truncate_text_middle(self._db_name_full, name_w, name_font)
            self.db_name_label.setText(f"<b>{name_display}</b>")
            self.db_name_label.setToolTip(self._db_name_full)
        if not getattr(self, '_db_path_full', None) or not getattr(self, 'db_path_label', None):
            return
        label = self.db_path_label
        w = max(80, label.width())
        path_display = truncate_path_for_display(self._db_path_full, w, label.font())
        label.setText(path_display)
    
    def _apply_checkbox_styling(self) -> None:
        """Apply checkbox styling to all checkboxes."""
        from app.views.style import StyleManager
        from pathlib import Path
        
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("bulk_clean_pgn", {})
        inputs_config = dialog_config.get("inputs", {})
        input_border_color = inputs_config.get("border_color", [60, 60, 65])
        input_bg_color = inputs_config.get("background_color", [30, 30, 35])
        
        # Get checkmark icon path
        app_root = Path(__file__).resolve().parents[2]
        checkmark_path = app_root / "resources" / "icons" / "checkmark.svg"
        
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

        icon_button_size = self.button_height
        StyleManager.style_buttons(
            quick_select_buttons,
            self.config,
            bg_color_list,
            border_color_list,
            min_width=None,
            min_height=icon_button_size,
        )

        # Icon-only behavior: set SVG icons with style-config tint.
        # This mirrors BulkReplaceDialog and EngineConfigurationDialog patterns.
        select_tint = (
            int(self.quick_select_select_tint_rgb[0]),
            int(self.quick_select_select_tint_rgb[1]),
            int(self.quick_select_select_tint_rgb[2]),
        )
        deselect_tint = (
            int(self.quick_select_deselect_tint_rgb[0]),
            int(self.quick_select_deselect_tint_rgb[1]),
            int(self.quick_select_deselect_tint_rgb[2]),
        )

        # Keep rendered icon sizes aligned with themed_icon_from_svg pixmap sizes (16/20/22/24/32).
        # This avoids Qt scaling artifacts on some themes.
        icon_px = max(16, min(22, icon_button_size - 8))

        self.select_all_button.setIcon(themed_icon_from_svg(self.quick_select_select_svg, select_tint))
        self.select_all_button.setText("")
        self.select_all_button.setToolTip(self.quick_select_select_tooltip)
        self.select_all_button.setIconSize(QSize(icon_px, icon_px))
        self.select_all_button.setFixedSize(icon_button_size, icon_button_size)

        self.deselect_all_button.setIcon(themed_icon_from_svg(self.quick_select_deselect_svg, deselect_tint))
        self.deselect_all_button.setText("")
        self.deselect_all_button.setToolTip(self.quick_select_deselect_tooltip)
        self.deselect_all_button.setIconSize(QSize(icon_px, icon_px))
        self.deselect_all_button.setFixedSize(icon_button_size, icon_button_size)
    
    def _on_apply_clicked(self) -> None:
        """Handle apply button click."""
        if self._operation_in_progress:
            return
        
        if not self.database:
            from app.views.dialogs.message_dialog import MessageDialog
            MessageDialog.show_warning(self.config, "No Database", "No database is currently active.", self)
            return
        
        # Check if at least one option is selected
        remove_comments = self.remove_comments_check.isChecked()
        remove_variations = self.remove_variations_check.isChecked()
        remove_non_standard_tags = self.remove_non_standard_tags_check.isChecked()
        remove_annotations = self.remove_annotations_check.isChecked()
        
        if not any([remove_comments, remove_variations, remove_non_standard_tags, 
                   remove_annotations]):
            from app.views.dialogs.message_dialog import MessageDialog
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
            game_indices
        )
        
        # Re-enable controls
        self._operation_in_progress = False
        self._set_controls_enabled(True)
        
        if not result.success:
            from app.views.dialogs.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Error",
                f"Failed to clean PGN: {result.error_message or 'Operation failed'}",
                self
            )
            return
        
        # Show success message (dialog stays open, user closes it manually)
        from app.views.dialogs.message_dialog import MessageDialog
        MessageDialog.show_information(
            self.config,
            "Bulk Clean PGN Complete",
            format_bulk_operation_summary_html(result),
            self
        )
        
        # Dialog stays open - user closes it manually
    
    def _on_select_all_clicked(self) -> None:
        """Handle Select All button click."""
        for cb in self._clean_checkboxes:
            with QSignalBlocker(cb):
                cb.setChecked(True)
        self._update_quick_select_buttons_enabled()
    
    def _on_deselect_all_clicked(self) -> None:
        """Handle Deselect All button click."""
        for cb in self._clean_checkboxes:
            with QSignalBlocker(cb):
                cb.setChecked(False)
        self._update_quick_select_buttons_enabled()
    
    def _on_cancel_clicked(self) -> None:
        """Handle Cancel button click."""
        self.reject()
    
    def _set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable dialog controls.
        
        Args:
            enabled: If True, enable controls; if False, disable them.
        """
        self.remove_comments_check.setEnabled(enabled)
        self.remove_variations_check.setEnabled(enabled)
        self.remove_non_standard_tags_check.setEnabled(enabled)
        self.remove_annotations_check.setEnabled(enabled)
        self.apply_button.setEnabled(enabled)
        self.cancel_button.setEnabled(enabled)
        self._controls_enabled = enabled
        self._update_quick_select_buttons_enabled()

    def _on_clean_checkbox_state_changed(self, _state: int) -> None:
        """Update quick-select buttons when checkbox selection changes."""
        self._update_quick_select_buttons_enabled()

    def _update_quick_select_buttons_enabled(self) -> None:
        """Enable/disable quick-select icon buttons based on checkbox selection."""
        if not getattr(self, "quick_select_enabled", False):
            return
        if not hasattr(self, "select_all_button") or not hasattr(self, "deselect_all_button"):
            return
        if not hasattr(self, "_clean_checkboxes"):
            return

        any_checked = any(cb.isChecked() for cb in self._clean_checkboxes)
        all_checked = all(cb.isChecked() for cb in self._clean_checkboxes)

        # If controls are disabled (e.g. operation in progress), force both off.
        controls_enabled = getattr(self, "_controls_enabled", True)

        # Requirement:
        # - If all checked => Select All disabled
        # - If none checked => Deselect All disabled
        self.select_all_button.setEnabled(controls_enabled and (not all_checked))
        self.deselect_all_button.setEnabled(controls_enabled and any_checked)

