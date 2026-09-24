"""Dialog to edit main-line move comments (white / black) for one row."""

from typing import Dict, Any, Optional, Tuple

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QSizePolicy,
    QWidget,
    QToolButton,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPalette, QColor, QFont, QShowEvent

from app.utils.external_open import open_user_manual
from app.utils.themed_icon import themed_icon_from_svg, SVG_MENU_INFO
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
        *,
        single_move_label: str = "",
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._has_black_half = has_black_half
        self._single_move_label = (single_move_label or "").strip()

        self._load_config()
        self._setup_ui(
            move_number,
            white_san,
            black_san,
            white_initial,
            black_initial,
        )
        self._apply_styling()
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self._apply_configured_dialog_size()
        self.setWindowTitle("Move comments")

    def _load_config(self) -> None:
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("move_comment", {})

        self._dialog_width = dialog_config.get("width", 500)
        spacing_config = dialog_config.get("spacing", {})
        self._bottom_button_top_padding = dialog_config.get(
            "bottom_button_top_padding", spacing_config.get("before_buttons", 25)
        )
        self._dialog_minimum_width = dialog_config.get("minimum_width")
        # Dual White+Black layout; single-field mode uses minimum_height_single (or content sizeHint).
        self._dialog_minimum_height = dialog_config.get(
            "minimum_height", dialog_config.get("height", 370)
        )
        self._dialog_minimum_height_single = dialog_config.get("minimum_height_single")

        bg_color = dialog_config.get("background_color", [40, 40, 45])
        self._bg_color = QColor(bg_color[0], bg_color[1], bg_color[2])

        text_color = dialog_config.get("text_color", [200, 200, 200])
        self._dialog_text_color = QColor(text_color[0], text_color[1], text_color[2])

        layout_config = dialog_config.get("layout", {})
        self._layout_margins = layout_config.get("margins", [20, 20, 20, 20])
        self._layout_spacing = layout_config.get("spacing", 12)

        self._section_spacing = spacing_config.get("section", 15)
        self._form_spacing = spacing_config.get("form", 8)

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
        self._text_edit_min_h = text_edits_config.get("minimum_height", 96)
        self._text_side_inset = text_edits_config.get("side_inset", 10)

        self._dialog_bg_rgb = dialog_config.get("background_color", [40, 40, 45])
        self._dialog_border_rgb = dialog_config.get("border_color", [60, 60, 65])

        help_config = dialog_config.get("help", {}) if isinstance(dialog_config.get("help", {}), dict) else {}
        self.help_enabled = bool(help_config.get("enabled", True))
        self.help_manual_anchor = str(help_config.get("manual_anchor", "editing-move-comments"))
        self.help_tooltip = str(help_config.get("tooltip", "Open user manual"))
        self.help_button_size = int(help_config.get("button_size", 22))
        self.help_column_spacing = int(help_config.get("column_spacing", 8))
        self.help_top_offset = int(help_config.get("top_offset", 0))

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
            self._single_move_label
            if self._single_move_label
            else self._format_move_header(
                move_number, white_san, black_san, self._has_black_half
            )
        )
        header.setFont(QFont(self._label_font_family, self._label_font_size))
        header.setWordWrap(True)
        header.setStyleSheet(
            f"color: rgb({self._label_text_color.red()}, {self._label_text_color.green()}, "
            f"{self._label_text_color.blue()});"
        )

        # Shared left/right inset for move label, text fields, and buttons.
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(
            self._text_side_inset,
            0,
            self._text_side_inset,
            0,
        )
        body_layout.setSpacing(0)

        if self.help_enabled:
            header_row = QHBoxLayout()
            header_row.setContentsMargins(0, 0, 0, 0)
            header_row.setSpacing(self.help_column_spacing)
            header_row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            header_row.addWidget(header, 1, Qt.AlignmentFlag.AlignVCenter)
            header_row.addWidget(
                self._build_help_button(), 0, Qt.AlignmentFlag.AlignVCenter
            )
            body_layout.addLayout(header_row)
        else:
            body_layout.addWidget(header)
        body_layout.addSpacing(self._section_spacing)

        white_block = QVBoxLayout()
        white_block.setSpacing(self._form_spacing)
        wl = QLabel("Comment" if self._single_move_label else "White")
        wl.setFont(QFont(self._label_font_family, self._label_font_size))
        wl.setStyleSheet(
            f"color: rgb({self._label_text_color.red()}, {self._label_text_color.green()}, "
            f"{self._label_text_color.blue()});"
        )
        white_block.addWidget(wl)
        self._white_edit = QTextEdit()
        self._white_edit.setAcceptRichText(False)
        self._white_edit.setPlainText(white_initial)
        self._white_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        white_block.addWidget(self._white_edit)
        body_layout.addLayout(white_block)

        self._black_container = QWidget()
        black_block = QVBoxLayout(self._black_container)
        black_block.setSpacing(self._form_spacing)
        black_block.setContentsMargins(0, 0, 0, 0)
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
        self._black_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self._black_edit.setEnabled(self._has_black_half)
        black_block.addWidget(self._black_edit)
        # Single-field mode: omit Black from the layout so it cannot stretch the dialog.
        if not self._single_move_label:
            body_layout.addSpacing(self._section_spacing)
            body_layout.addWidget(self._black_container)

        main_layout.addWidget(body, 0, Qt.AlignmentFlag.AlignTop)
        main_layout.addSpacing(self._bottom_button_top_padding)

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

    def _build_help_button(self) -> QToolButton:
        """Themed manual help button for the move header row."""
        btn_size = max(16, self.help_button_size)
        icon_size = max(12, btn_size - 6)
        tint = (
            self._label_text_color.red(),
            self._label_text_color.green(),
            self._label_text_color.blue(),
        )
        self.help_button = QToolButton()
        self.help_button.setToolTip(self.help_tooltip)
        self.help_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_button.setAutoRaise(True)
        self.help_button.setFixedSize(btn_size, btn_size)
        self.help_button.setIconSize(QSize(icon_size, icon_size))
        self.help_button.setAccessibleName(self.help_tooltip)
        self.help_button.setIcon(themed_icon_from_svg(SVG_MENU_INFO, tint))
        self.help_button.setStyleSheet(
            f"QToolButton {{"
            f"background: transparent; border: none; padding: 0px;"
            f"margin-top: {self.help_top_offset}px;"
            f"}}"
        )
        self.help_button.clicked.connect(self._on_help_clicked)
        return self.help_button

    def _on_help_clicked(self) -> None:
        open_user_manual(
            anchor=self.help_manual_anchor,
            context="move_comment.help",
        )

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
        # QTextEdit ignores a small minimumHeight for layout: its sizeHint stays large unless height is fixed.
        for te in (self._white_edit, self._black_edit):
            te.setFixedHeight(self._text_edit_min_h)

    def _apply_configured_dialog_size(self) -> None:
        """Width from config; height from layout (floored by optional minimum_height)."""
        w = int(self._dialog_width)
        if self._dialog_minimum_width is not None:
            w = max(w, int(self._dialog_minimum_width))
        self.setFixedWidth(w)
        lay = self.layout()
        if lay is None:
            return
        h = lay.sizeHint().height()
        if h <= 0:
            return
        min_h = (
            self._dialog_minimum_height_single
            if self._single_move_label
            else self._dialog_minimum_height
        )
        if min_h is not None:
            h = max(h, int(min_h))
        self.setFixedHeight(h)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._apply_configured_dialog_size()

    def get_comments(self) -> Tuple[str, str]:
        """Return plain-text white and black comments as edited."""
        white = self._white_edit.toPlainText()
        black = self._black_edit.toPlainText() if self._has_black_half else ""
        return (white, black)

    def get_comment(self) -> str:
        """Return the single-field comment (same as White's field)."""
        return self._white_edit.toPlainText()

    @staticmethod
    def edit_single_move(
        config: Dict[str, Any],
        move_number: int,
        san: str,
        is_white: bool,
        initial: str,
        parent=None,
    ) -> Optional[str]:
        """Show a one-half-move comment editor. ``None`` if the user cancels."""
        label = f"{move_number}.{san}" if is_white else f"{move_number}...{san}"
        dialog = MoveCommentDialog(
            config,
            move_number,
            san,
            "",
            initial,
            "",
            False,
            parent,
            single_move_label=label,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.get_comment()
