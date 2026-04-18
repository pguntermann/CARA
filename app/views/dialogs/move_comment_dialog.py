"""Dialog to edit main-line move comments (white / black) for one row."""

from typing import Dict, Any, Tuple

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QSizePolicy,
    QWidget,
)
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QPalette, QColor, QFont

from app.views.style import StyleManager
from app.views.style.line_edit import generate_line_edit_stylesheet


class MoveCommentDialog(QDialog):
    """Edit comments attached to the main-line half-moves for one full-move row."""

    def __init__(
        self,
        config: Dict[str, Any],
        move_number: int,
        white_san: str,
        black_san: str,
        white_initial: str,
        black_initial: str,
        has_black_half: bool,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._has_black_half = has_black_half

        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("move_comment", {})
        width = dialog_config.get("width", 500)
        height = dialog_config.get("height", 400)
        self._fixed_size = QSize(width, height)
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._load_config()
        self._setup_ui(
            move_number,
            white_san,
            black_san,
            white_initial,
            black_initial,
        )
        self._apply_styling()
        self.setWindowTitle("Move comments")

    def _load_config(self) -> None:
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("move_comment", {})

        bg_color = dialog_config.get("background_color", [40, 40, 45])
        self._bg_color = QColor(bg_color[0], bg_color[1], bg_color[2])

        text_color = dialog_config.get("text_color", [200, 200, 200])
        self._dialog_text_color = QColor(text_color[0], text_color[1], text_color[2])

        layout_config = dialog_config.get("layout", {})
        self._layout_margins = layout_config.get("margins", [20, 20, 20, 20])
        self._layout_spacing = layout_config.get("spacing", 12)

        spacing_config = dialog_config.get("spacing", {})
        self._section_spacing = spacing_config.get("section", 15)
        self._form_spacing = spacing_config.get("form", 8)
        self._before_buttons_spacing = spacing_config.get("before_buttons", 20)

        buttons_config = dialog_config.get("buttons", {})
        self._button_width = buttons_config.get("width", 120)
        self._button_height = buttons_config.get("height", 30)
        self._button_spacing = buttons_config.get("spacing", 10)

        labels_config = dialog_config.get("labels", {})
        from app.utils.font_utils import resolve_font_family, scale_font_size

        self._label_font_family = resolve_font_family(
            labels_config.get("font_family", "Helvetica Neue")
        )
        self._label_font_size = int(scale_font_size(labels_config.get("font_size", 11)))
        self._label_text_color = QColor(*labels_config.get("text_color", [200, 200, 200]))

        inputs_config = dialog_config.get("inputs", {})
        self._input_font_family = resolve_font_family(
            inputs_config.get("font_family", "Cascadia Mono")
        )
        self._input_font_size = scale_font_size(inputs_config.get("font_size", 11))
        self._input_text_rgb = inputs_config.get("text_color", [240, 240, 240])
        self._input_bg_rgb = inputs_config.get("background_color", [30, 30, 35])
        self._input_border_rgb = inputs_config.get("border_color", [60, 60, 65])
        self._input_border_radius = inputs_config.get("border_radius", 3)
        self._input_padding = inputs_config.get("padding", [8, 6])
        styles_le = self.config.get("ui", {}).get("styles", {}).get("line_edit", {})
        self._input_focus_border_rgb = inputs_config.get(
            "focus_border_color", styles_le.get("focus_border_color", [0, 120, 212])
        )
        self._input_border_width = styles_le.get("border_width", 1)
        self._input_hover_border_offset = styles_le.get("hover_border_offset", 20)
        self._input_disabled_brightness_factor = float(
            styles_le.get("disabled_brightness_factor", 0.5) or 0.5
        )
        self._input_disabled_brightness_factor = max(
            0.1, min(1.0, self._input_disabled_brightness_factor)
        )

        text_edits_config = dialog_config.get("text_edits", {})
        self._text_edit_min_h = text_edits_config.get("minimum_height", 80)
        self._text_side_inset = text_edits_config.get("side_inset", 10)

        self._dialog_bg_rgb = dialog_config.get("background_color", [40, 40, 45])
        self._dialog_border_rgb = dialog_config.get("border_color", [60, 60, 65])

    @staticmethod
    def _format_move_header(
        move_number: int, white_san: str, black_san: str, has_black_half: bool
    ) -> str:
        w = (white_san or "").strip()
        if not w:
            w = "…"
        if not has_black_half:
            return f"Move {move_number}: {w}"
        b = (black_san or "").strip()
        if not b:
            b = "…"
        return f"Move {move_number}: {w} {b}"

    def _setup_ui(
        self,
        move_number: int,
        white_san: str,
        black_san: str,
        white_initial: str,
        black_initial: str,
    ) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(
            self._layout_margins[0],
            self._layout_margins[1],
            self._layout_margins[2],
            self._layout_margins[3],
        )

        header = QLabel(
            self._format_move_header(
                move_number, white_san, black_san, self._has_black_half
            )
        )
        header.setFont(QFont(self._label_font_family, self._label_font_size))
        header.setWordWrap(True)
        header.setStyleSheet(
            f"color: rgb({self._label_text_color.red()}, {self._label_text_color.green()}, "
            f"{self._label_text_color.blue()});"
        )
        main_layout.addWidget(header)
        main_layout.addSpacing(self._section_spacing)

        # Inset left/right so text fields do not sit flush with the dialog chrome
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(
            self._text_side_inset,
            0,
            self._text_side_inset,
            0,
        )
        body_layout.setSpacing(0)

        white_block = QVBoxLayout()
        white_block.setSpacing(self._form_spacing)
        wl = QLabel("White")
        wl.setFont(QFont(self._label_font_family, self._label_font_size))
        wl.setStyleSheet(
            f"color: rgb({self._label_text_color.red()}, {self._label_text_color.green()}, "
            f"{self._label_text_color.blue()});"
        )
        white_block.addWidget(wl)
        self._white_edit = QTextEdit()
        self._white_edit.setAcceptRichText(False)
        self._white_edit.setPlainText(white_initial)
        self._white_edit.setMinimumHeight(self._text_edit_min_h)
        self._white_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        white_block.addWidget(self._white_edit)
        body_layout.addLayout(white_block)
        body_layout.addSpacing(self._section_spacing)

        black_block = QVBoxLayout()
        black_block.setSpacing(self._form_spacing)
        bl = QLabel("Black")
        bl.setFont(QFont(self._label_font_family, self._label_font_size))
        bl.setStyleSheet(
            f"color: rgb({self._label_text_color.red()}, {self._label_text_color.green()}, "
            f"{self._label_text_color.blue()});"
        )
        black_block.addWidget(bl)
        self._black_edit = QTextEdit()
        self._black_edit.setAcceptRichText(False)
        self._black_edit.setPlainText(black_initial)
        self._black_edit.setMinimumHeight(self._text_edit_min_h)
        self._black_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self._black_edit.setEnabled(self._has_black_half)
        black_block.addWidget(self._black_edit)
        body_layout.addLayout(black_block)

        main_layout.addWidget(body)
        main_layout.addStretch(1)
        main_layout.addSpacing(self._before_buttons_spacing)

        self._ok_button = QPushButton("OK")
        self._ok_button.setDefault(True)
        self._ok_button.setAutoDefault(True)
        self._ok_button.clicked.connect(self.accept)
        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setAutoDefault(False)
        self._cancel_button.clicked.connect(self.reject)

        # Same horizontal inset as the text edits so OK/Cancel line up with their right edge
        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(
            self._text_side_inset,
            0,
            self._text_side_inset,
            0,
        )
        footer_layout.setSpacing(0)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self._cancel_button)
        footer_layout.addSpacing(self._button_spacing)
        footer_layout.addWidget(self._ok_button)
        main_layout.addWidget(footer)

    def _apply_styling(self) -> None:
        palette = self.palette()
        palette.setColor(self.backgroundRole(), self._bg_color)
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("move_comment", {})
        bg_rgb = dialog_config.get("background_color", [40, 40, 45])
        border_rgb = dialog_config.get("border_color", [60, 60, 65])

        StyleManager.style_buttons(
            [self._ok_button, self._cancel_button],
            self.config,
            bg_rgb,
            border_rgb,
            min_width=self._button_width,
            min_height=self._button_height,
        )

        text_edit_style = generate_line_edit_stylesheet(
            self.config,
            self._input_text_rgb,
            self._input_font_family,
            self._input_font_size,
            self._input_bg_rgb,
            self._input_border_rgb,
            self._input_focus_border_rgb,
            border_width=self._input_border_width,
            border_radius=self._input_border_radius,
            padding=self._input_padding,
            hover_border_offset=self._input_hover_border_offset,
            disabled_brightness_factor=self._input_disabled_brightness_factor,
        ).replace("QLineEdit", "QTextEdit")

        for te in (self._white_edit, self._black_edit):
            te.setStyleSheet(text_edit_style)
            StyleManager.style_text_edit_scrollbar(
                te,
                self.config,
                self._input_bg_rgb,
                self._input_border_rgb,
                text_edit_style,
            )

    def get_comments(self) -> Tuple[str, str]:
        """Return plain-text white and black comments as edited."""
        white = self._white_edit.toPlainText()
        black = self._black_edit.toPlainText() if self._has_black_half else ""
        return (white, black)
