"""Deduplication criteria dialog for selecting how duplicate games are identified."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QComboBox,
    QSizePolicy,
    QToolButton,
    QWidget,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QPalette, QShowEvent, QResizeEvent
from typing import Dict, Any, Optional, Tuple, List
from enum import Enum

from app.utils.external_open import open_user_manual
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.themed_icon import SVG_MENU_INFO, themed_icon_from_svg


class DeduplicationMode(Enum):
    """Deduplication matching modes."""
    EXACT_PGN = "exact_pgn"
    MOVES_ONLY = "moves_only"
    NORMALIZED_PGN = "normalized_pgn"
    HEADER_BASED = "header_based"


class DeduplicationCriteriaDialog(QDialog):
    """Dialog for selecting deduplication criteria."""

    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        """Initialize the deduplication criteria dialog.

        Args:
            config: Configuration dictionary.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.selected_mode: Optional[DeduplicationMode] = None
        self.selected_headers: List[str] = []

        self._load_config()

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self._setup_ui()
        self._apply_styling()
        self._set_defaults()
        self._on_mode_changed()
        self.setWindowTitle("Deduplication Criteria")

    def _load_config(self) -> None:
        """Load configuration values from config.json."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get(
            "deduplication_criteria", {}
        )

        self.dialog_width = dialog_config.get("width", 480)
        self.bottom_button_top_padding = dialog_config.get("bottom_button_top_padding", 25)

        self.bg_color = dialog_config.get("background_color", [40, 40, 45])
        self.border_color = dialog_config.get("border_color", [60, 60, 65])
        self.text_color = dialog_config.get("text_color", [200, 200, 200])
        self.font_size = scale_font_size(dialog_config.get("font_size", 11))

        layout_config = dialog_config.get("layout", {})
        self.layout_spacing = layout_config.get("spacing", 10)
        self.layout_margins = layout_config.get("margins", [25, 25, 25, 25])
        self.section_spacing = layout_config.get("section_spacing", 15)

        buttons_config = dialog_config.get("buttons", {})
        self.button_width = buttons_config.get("width", 120)
        self.button_height = buttons_config.get("height", 30)
        self.button_spacing = buttons_config.get("spacing", 10)

        labels_config = dialog_config.get("labels", {})
        self.label_font_family = resolve_font_family(
            labels_config.get("font_family", "Helvetica Neue")
        )
        self.label_font_size = scale_font_size(labels_config.get("font_size", 11))
        self.label_text_color = labels_config.get("text_color", [200, 200, 200])

        description_config = dialog_config.get("description", {})
        self.description_font_family = resolve_font_family(
            description_config.get("font_family", "Helvetica Neue")
        )
        self.description_font_size = scale_font_size(
            description_config.get("font_size", 10)
        )
        self.description_text_color = description_config.get(
            "text_color", [180, 180, 180]
        )
        self.description_margin_top = description_config.get("margin_top", 8)

        inputs_config = dialog_config.get("inputs", {})
        self.input_font_family = resolve_font_family(
            inputs_config.get("font_family", "Cascadia Mono")
        )
        self.input_font_size = scale_font_size(inputs_config.get("font_size", 11))
        self.input_text_color = inputs_config.get("text_color", [240, 240, 240])
        self.input_bg_color = inputs_config.get("background_color", [30, 30, 35])
        self.input_border_color = inputs_config.get("border_color", [60, 60, 65])
        self.input_border_radius = inputs_config.get("border_radius", 3)
        self.input_padding = inputs_config.get("padding", [8, 6])

        checkbox_config = dialog_config.get("checkboxes", {})
        self.checkbox_spacing = checkbox_config.get("spacing", 5)
        self.checkbox_text_color = checkbox_config.get(
            "text_color", self.label_text_color or self.text_color
        )
        self.checkbox_font_size = scale_font_size(checkbox_config.get("font_size", 11))
        self.header_checkbox_columns = int(
            checkbox_config.get("columns", 2)
        )

        modes_config = dialog_config.get("modes", {})
        self.mode_options = modes_config.get(
            "options",
            [
                {"value": "exact_pgn", "label": "Exact PGN Match"},
                {"value": "moves_only", "label": "Moves Only"},
                {"value": "normalized_pgn", "label": "Normalized PGN Match"},
                {"value": "header_based", "label": "Header Based Match"},
            ],
        )
        self.mode_descriptions = modes_config.get(
            "descriptions",
            {
                "exact_pgn": (
                    "Match games with identical PGN strings (headers + moves). "
                    "This is the most strict matching mode."
                ),
                "moves_only": (
                    "Match games with identical moves, ignoring header information. "
                    "Useful when the same game appears with different metadata."
                ),
                "normalized_pgn": (
                    "Match games after removing comments, variations, annotations, "
                    "and extra whitespace. Useful when PGN formatting differs."
                ),
                "header_based": (
                    "Match games based on selected header fields. Useful when you want "
                    "to identify games by specific metadata rather than moves."
                ),
            },
        )

        self.default_mode = dialog_config.get("default_mode", "exact_pgn")
        self.header_fields = dialog_config.get(
            "header_fields",
            ["White", "Black", "Date", "Result", "Event", "Site", "Round"],
        )
        self.default_headers = dialog_config.get(
            "default_headers", ["White", "Black", "Date", "Result"]
        )

        help_config = dialog_config.get("help", {})
        self.help_enabled = bool(help_config.get("enabled", True))
        self.help_manual_anchor = str(
            help_config.get("manual_anchor", "deduplicate-games")
        )
        self.help_tooltip = str(help_config.get("tooltip", "Open user manual"))
        self.help_button_size = int(help_config.get("button_size", 22))
        self.help_column_spacing = int(help_config.get("column_spacing", 8))
        self.help_top_offset = int(help_config.get("top_offset", 0))

    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(
            self.backgroundRole(),
            QColor(self.bg_color[0], self.bg_color[1], self.bg_color[2]),
        )
        self.setPalette(palette)

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(
            self.layout_margins[0],
            self.layout_margins[1],
            self.layout_margins[2],
            self.layout_margins[3],
        )

        # Header: section label + optional help
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(self.help_column_spacing)
        header_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.mode_label = QLabel("Matching mode")
        self.mode_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        header_row.addWidget(self.mode_label, 1, Qt.AlignmentFlag.AlignVCenter)
        if self.help_enabled:
            header_row.addWidget(
                self._build_help_button(), 0, Qt.AlignmentFlag.AlignVCenter
            )
        layout.addLayout(header_row)
        layout.addSpacing(max(6, self.layout_spacing // 2))

        self.mode_combo = QComboBox()
        for option in self.mode_options:
            self.mode_combo.addItem(option["label"], option["value"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        layout.addWidget(self.mode_combo)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self.description_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.description_label)

        # Header-field options (shown only for header-based mode)
        self.customization_panel = QWidget()
        customization_layout = QVBoxLayout(self.customization_panel)
        customization_layout.setContentsMargins(0, self.section_spacing, 0, 0)
        customization_layout.setSpacing(self.checkbox_spacing)

        self.header_fields_label = QLabel("Select header fields to match:")
        customization_layout.addWidget(self.header_fields_label)

        checkbox_grid = QGridLayout()
        checkbox_grid.setContentsMargins(0, 0, 0, 0)
        checkbox_grid.setHorizontalSpacing(max(16, self.layout_spacing * 2))
        checkbox_grid.setVerticalSpacing(self.checkbox_spacing)
        columns = max(1, self.header_checkbox_columns)

        self.header_checkboxes: Dict[str, QCheckBox] = {}
        for index, header_field in enumerate(self.header_fields):
            checkbox = QCheckBox(header_field)
            self.header_checkboxes[header_field] = checkbox
            checkbox_grid.addWidget(checkbox, index // columns, index % columns)

        customization_layout.addLayout(checkbox_grid)
        self.customization_panel.setVisible(False)
        self.customization_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self.customization_panel, 0)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(self.button_spacing)
        button_layout.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)

        self.ok_button = QPushButton("OK")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self._on_ok_clicked)
        button_layout.addWidget(self.ok_button)

        layout.addSpacing(self.bottom_button_top_padding)
        layout.addLayout(button_layout)

    def _build_help_button(self) -> QToolButton:
        """Themed manual help button for the dialog header."""
        btn_size = max(16, self.help_button_size)
        icon_size = max(12, btn_size - 6)
        tint = tuple(int(c) for c in self.label_text_color[:3])
        self.help_button = QToolButton()
        self.help_button.setToolTip(self.help_tooltip)
        self.help_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_button.setAutoRaise(True)
        self.help_button.setFixedSize(btn_size, btn_size)
        self.help_button.setIconSize(QSize(icon_size, icon_size))
        self.help_button.setAccessibleName(self.help_tooltip)
        self.help_button.setIcon(themed_icon_from_svg(SVG_MENU_INFO, tint))
        self.help_button.setStyleSheet(
            "QToolButton { background: transparent; border: none; padding: 0px; }"
        )
        self.help_button.clicked.connect(self._on_help_clicked)
        return self.help_button

    def _on_help_clicked(self) -> None:
        open_user_manual(
            anchor=self.help_manual_anchor,
            context="deduplication_criteria.help",
        )

    def _apply_configured_dialog_size(self) -> None:
        """Width from config; height from layout size hint (content-driven)."""
        w = int(self.dialog_width)
        self.setFixedWidth(w)
        lay = self.layout()
        if lay is None:
            return
        h = lay.sizeHint().height()
        if h > 0:
            self.setFixedHeight(h)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._apply_configured_dialog_size()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_configured_dialog_size()

    def _apply_styling(self) -> None:
        """Apply styling from config.json to all UI elements."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get(
            "deduplication_criteria", {}
        )
        inputs_config = dialog_config.get("inputs", {})

        from app.views.style import StyleManager

        buttons = list(self.findChildren(QPushButton))
        if buttons:
            StyleManager.style_buttons(
                buttons,
                self.config,
                list(self.bg_color),
                list(self.border_color),
                min_width=self.button_width,
                min_height=self.button_height,
            )

        label_style = (
            f"QLabel {{"
            f'font-family: "{self.label_font_family}";'
            f"font-size: {self.label_font_size}pt;"
            f"color: rgb({self.label_text_color[0]}, {self.label_text_color[1]}, {self.label_text_color[2]});"
            f"background-color: transparent;"
            f"}}"
        )
        for label in self.findChildren(QLabel):
            label.setStyleSheet(label_style)
            label_palette = label.palette()
            label_palette.setColor(
                label.foregroundRole(),
                QColor(
                    self.label_text_color[0],
                    self.label_text_color[1],
                    self.label_text_color[2],
                ),
            )
            label.setPalette(label_palette)

        description_style = (
            f"QLabel {{"
            f'font-family: "{self.description_font_family}";'
            f"font-size: {self.description_font_size}pt;"
            f"color: rgb({self.description_text_color[0]}, {self.description_text_color[1]}, {self.description_text_color[2]});"
            f"margin-top: {self.description_margin_top}px;"
            f"background-color: transparent;"
            f"}}"
        )
        self.description_label.setStyleSheet(description_style)
        description_palette = self.description_label.palette()
        description_palette.setColor(
            self.description_label.foregroundRole(),
            QColor(
                self.description_text_color[0],
                self.description_text_color[1],
                self.description_text_color[2],
            ),
        )
        self.description_label.setPalette(description_palette)

        selection_bg = inputs_config.get("selection_background_color", [70, 90, 130])
        selection_text = inputs_config.get("selection_text_color", [240, 240, 240])
        focus_border_color = inputs_config.get("focus_border_color", [0, 120, 212])

        StyleManager.style_comboboxes(
            [self.mode_combo],
            self.config,
            self.input_text_color,
            self.input_font_family,
            self.input_font_size,
            self.input_bg_color,
            self.input_border_color,
            focus_border_color,
            selection_bg,
            selection_text,
            border_width=1,
            border_radius=self.input_border_radius,
            padding=self.input_padding,
        )

        from app.utils.path_resolver import get_app_resource_path

        checkmark_path = get_app_resource_path("app/resources/icons/checkmark.svg")
        StyleManager.style_checkboxes(
            list(self.findChildren(QCheckBox)),
            self.config,
            self.checkbox_text_color,
            self.label_font_family,
            self.checkbox_font_size,
            self.input_bg_color,
            self.input_border_color,
            checkmark_path,
        )

    def _set_defaults(self) -> None:
        """Set default values."""
        default_index = 0
        for idx, option in enumerate(self.mode_options):
            if option["value"] == self.default_mode:
                default_index = idx
                break
        self.mode_combo.setCurrentIndex(default_index)

        for header_field in self.default_headers:
            if header_field in self.header_checkboxes:
                self.header_checkboxes[header_field].setChecked(True)

    def _on_mode_changed(self) -> None:
        """Handle mode combo box change.

        Updates description text and shows/hides customization area.
        """
        current_value = self.mode_combo.currentData()
        if not current_value:
            return

        self.description_label.setText(
            self.mode_descriptions.get(current_value, "")
        )

        show_headers = current_value == "header_based"
        self.customization_panel.setVisible(show_headers)
        self.customization_panel.updateGeometry()
        self._apply_configured_dialog_size()

    def _on_ok_clicked(self) -> None:
        """Handle OK button click."""
        current_value = self.mode_combo.currentData()
        if not current_value:
            return

        mode_map = {
            "exact_pgn": DeduplicationMode.EXACT_PGN,
            "moves_only": DeduplicationMode.MOVES_ONLY,
            "normalized_pgn": DeduplicationMode.NORMALIZED_PGN,
            "header_based": DeduplicationMode.HEADER_BASED,
        }

        self.selected_mode = mode_map.get(current_value)
        if not self.selected_mode:
            return

        if self.selected_mode == DeduplicationMode.HEADER_BASED:
            self.selected_headers = [
                field
                for field, checkbox in self.header_checkboxes.items()
                if checkbox.isChecked()
            ]
            if not self.selected_headers:
                from app.views.dialogs.message_dialog import MessageDialog

                MessageDialog.show_warning(
                    self.config,
                    "Invalid Selection",
                    "Please select at least one header field for header-based matching.",
                    self,
                )
                return

        self.accept()

    def get_criteria(self) -> Tuple[DeduplicationMode, List[str]]:
        """Get the selected deduplication criteria.

        Returns:
            Tuple of (mode, headers) where headers is only used for HEADER_BASED mode.
        """
        return (self.selected_mode, self.selected_headers)
