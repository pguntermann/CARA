"""Dialog for adding a PGN header tag (metadata).

Styled via ``ui.dialogs.add_tag_dialog`` in the style config.
"""

from __future__ import annotations

from typing import Any, Dict, Tuple

from PyQt6.QtCore import Qt, QRegularExpression
from PyQt6.QtGui import QColor, QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.pgn_header_utils import is_valid_pgn_header_tag_name, pgn_header_tag_name_input_pattern
from app.views.style import StyleManager


class AddPgnHeaderDialog(QDialog):
    """Dialog for adding a new PGN header tag."""

    CONFIG_KEY = "add_tag_dialog"

    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.tag_name = ""
        self.tag_value = ""

        self._load_config()
        self._setup_ui()
        self._apply_styling()
        self.setWindowTitle("Add PGN header tag")

    def _load_config(self) -> None:
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get(self.CONFIG_KEY, {})
        self.dialog_width = dialog_config.get("width", 440)
        self.dialog_height = dialog_config.get("height", 220)
        self.dialog_min_width = dialog_config.get("minimum_width", 380)
        self.dialog_min_height = dialog_config.get("minimum_height", 180)
        self.dialog_bg_color = dialog_config.get("background_color", [40, 40, 45])
        self.dialog_border_color = dialog_config.get("border_color", [60, 60, 65])

        layout_config = dialog_config.get("layout", {})
        self.layout_margins = layout_config.get("margins", [25, 25, 25, 25])
        self.button_row_spacing = layout_config.get("button_row_spacing", 20)
        self.form_horizontal_spacing = layout_config.get("form_horizontal_spacing", 14)
        self.form_vertical_spacing = layout_config.get("form_vertical_spacing", 12)

        groups_config = dialog_config.get("groups", {})
        self.group_title = groups_config.get("title", "PGN header tag")
        self.group_content_margins = groups_config.get("content_margins", [10, 20, 10, 15])

        labels_config = dialog_config.get("labels", {})
        self.label_font_family = labels_config.get("font_family", "Helvetica Neue")
        self.label_font_size = scale_font_size(labels_config.get("font_size", 11))
        self.label_text_color = labels_config.get("text_color", [200, 200, 200])
        self.label_minimum_width = labels_config.get("minimum_width", 130)

        inputs_config = dialog_config.get("inputs", {})
        input_font_family_raw = inputs_config.get("font_family", "Cascadia Mono")
        self.input_font_family = resolve_font_family(input_font_family_raw)
        self.input_font_size = inputs_config.get("font_size", 11)
        self.input_bg_color = inputs_config.get("background_color", [30, 30, 35])
        self.input_border_color = inputs_config.get("border_color", [60, 60, 65])
        self.input_border_radius = inputs_config.get("border_radius", 3)
        self.input_padding = inputs_config.get("padding", [8, 6])
        self.input_min_width = inputs_config.get("minimum_width", 200)
        self.input_min_height = inputs_config.get("minimum_height", 30)
        self.input_focus_border_color = inputs_config.get("focus_border_color", [0, 120, 212])

        buttons_config = dialog_config.get("buttons", {})
        self.button_width = buttons_config.get("width", 120)
        self.button_height = buttons_config.get("height", 30)
        self.button_bg_offset = buttons_config.get("background_offset", 20)
        self.button_hover_bg_offset = buttons_config.get("hover_background_offset", 30)
        self.button_pressed_bg_offset = buttons_config.get("pressed_background_offset", 10)
        self.button_border_color = buttons_config.get("border_color", [60, 60, 65])
        self.button_spacing = buttons_config.get("spacing", 10)

    def _setup_ui(self) -> None:
        self.setMinimumSize(self.dialog_min_width, self.dialog_min_height)
        self.resize(self.dialog_width, self.dialog_height)

        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(
            self.backgroundRole(),
            QColor(self.dialog_bg_color[0], self.dialog_bg_color[1], self.dialog_bg_color[2]),
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

        tag_group = QGroupBox(self.group_title)
        form_layout = QFormLayout()
        form_layout.setSpacing(self.form_vertical_spacing)
        form_layout.setHorizontalSpacing(self.form_horizontal_spacing)
        form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        tag_name_label = QLabel("Tag name:")
        tag_name_label.setMinimumWidth(self.label_minimum_width)
        self.tag_name_input = QLineEdit()
        self.tag_name_input.setValidator(
            QRegularExpressionValidator(
                QRegularExpression(pgn_header_tag_name_input_pattern()),
                self.tag_name_input,
            )
        )
        self.tag_name_input.setPlaceholderText("e.g. MyCustomTag")
        self.tag_name_input.setMinimumWidth(self.input_min_width)
        self.tag_name_input.setMinimumHeight(self.input_min_height)
        self.tag_name_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form_layout.addRow(tag_name_label, self.tag_name_input)

        tag_value_label = QLabel("Value:")
        tag_value_label.setMinimumWidth(self.label_minimum_width)
        self.tag_value_input = QLineEdit()
        self.tag_value_input.setMinimumWidth(self.input_min_width)
        self.tag_value_input.setMinimumHeight(self.input_min_height)
        self.tag_value_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        form_layout.addRow(tag_value_label, self.tag_value_input)

        tag_group.setLayout(form_layout)
        layout.addWidget(tag_group)

        layout.addStretch(1)
        layout.addSpacing(self.button_row_spacing)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(self.button_spacing)
        button_layout.addStretch()
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        ok_button = QPushButton("OK")
        ok_button.setDefault(True)
        ok_button.clicked.connect(self._on_ok_clicked)
        button_layout.addWidget(ok_button)
        layout.addLayout(button_layout)

        self._cancel_button = cancel_button
        self._ok_button = ok_button

        self.tag_name_input.setFocus()

    def _apply_styling(self) -> None:
        label_style = f"""
            QLabel {{
                font-family: '{self.label_font_family}';
                font-size: {self.label_font_size}pt;
                color: rgb({self.label_text_color[0]}, {self.label_text_color[1]}, {self.label_text_color[2]});
            }}
        """

        scaled_font_size = scale_font_size(self.input_font_size)
        input_padding = (
            self.input_padding if isinstance(self.input_padding, list) and len(self.input_padding) == 2 else [8, 6]
        )

        line_edits = list(self.findChildren(QLineEdit))
        if line_edits:
            StyleManager.style_line_edits(
                line_edits,
                self.config,
                font_family=self.input_font_family,
                font_size=scaled_font_size,
                bg_color=self.input_bg_color,
                border_color=self.input_border_color,
                focus_border_color=self.input_focus_border_color,
                border_radius=self.input_border_radius,
                padding=input_padding,
            )

        for label in self.findChildren(QLabel):
            label.setStyleSheet(label_style)

        groups_cfg = (
            self.config.get("ui", {}).get("dialogs", {}).get(self.CONFIG_KEY, {}).get("groups", {}) or {}
        )
        bc = (
            self.dialog_border_color
            if isinstance(self.dialog_border_color, list) and len(self.dialog_border_color) >= 3
            else [60, 60, 65]
        )
        bc = [int(bc[0]), int(bc[1]), int(bc[2])]
        bg_rgb = [int(self.dialog_bg_color[0]), int(self.dialog_bg_color[1]), int(self.dialog_bg_color[2])]
        title_ff = groups_cfg.get("title_font_family")
        title_ff = resolve_font_family(title_ff) if title_ff else None
        title_fs = scale_font_size(groups_cfg["title_font_size"]) if "title_font_size" in groups_cfg else None
        title_color = groups_cfg.get("title_color")
        if isinstance(title_color, dict) and "$ref" in title_color:
            title_color = None
        elif isinstance(title_color, list) and len(title_color) >= 3:
            title_color = [int(title_color[0]), int(title_color[1]), int(title_color[2])]
        else:
            title_color = None
        group_boxes = [g for g in self.findChildren(QGroupBox)]
        if group_boxes:
            StyleManager.style_group_boxes(
                group_boxes,
                self.config,
                border_color=bc,
                bg_color=bg_rgb,
                border_radius=groups_cfg.get("border_radius"),
                border_width=groups_cfg.get("border_width"),
                margin_top=groups_cfg.get("margin_top"),
                padding_top=groups_cfg.get("padding_top"),
                title_font_family=title_ff,
                title_font_size=title_fs,
                title_color=title_color,
                content_margins=list(self.group_content_margins),
            )

        main_buttons = [self._ok_button, self._cancel_button]
        bg_color_list = [self.dialog_bg_color[0], self.dialog_bg_color[1], self.dialog_bg_color[2]]
        border_color_list = [self.button_border_color[0], self.button_border_color[1], self.button_border_color[2]]
        StyleManager.style_buttons(
            main_buttons,
            self.config,
            bg_color_list,
            border_color_list,
            background_offset=self.button_bg_offset,
            hover_background_offset=self.button_hover_bg_offset,
            pressed_background_offset=self.button_pressed_bg_offset,
            min_width=self.button_width,
            min_height=self.button_height,
        )

    def _on_ok_clicked(self) -> None:
        tag_name = self.tag_name_input.text().strip()
        tag_value = self.tag_value_input.text().strip()

        if not tag_name:
            from app.views.dialogs.message_dialog import MessageDialog

            MessageDialog.show_warning(self.config, "Invalid input", "PGN header tag name cannot be empty.", self)
            return

        if not is_valid_pgn_header_tag_name(tag_name):
            from app.views.dialogs.message_dialog import MessageDialog

            MessageDialog.show_warning(
                self.config,
                "Invalid tag name",
                "PGN header tag names must be one word: start with a letter, then only letters, "
                "digits, or underscores. Spaces and other characters are not allowed.",
                self,
            )
            return

        self.tag_name = tag_name
        self.tag_value = tag_value
        self.accept()

    def get_tag_info(self) -> Tuple[str, str]:
        """Return the tag name and value entered in the dialog."""
        return (self.tag_name, self.tag_value)
