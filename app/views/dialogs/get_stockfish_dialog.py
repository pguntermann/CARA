"""Get Stockfish wizard — download and register an official Stockfish build."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor, QShowEvent
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.controllers.engine_controller import EngineController
from app.controllers.get_stockfish_controller import GetStockfishController
from app.services.stockfish_download_service import (
    ResolvedStockfishAsset,
    format_bytes,
)
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.themed_icon import SVG_MENU_FOLDER_OPEN, themed_icon_from_svg
from app.views.style import StyleManager


class GetStockfishDialog(QDialog):
    """Multi-step wizard to download Stockfish and add it to CARA."""

    CONFIG_KEY = "get_stockfish"
    PAGE_WELCOME = 0
    PAGE_BINARY = 1
    PAGE_FOLDER = 2
    PAGE_DOWNLOAD = 3
    PAGE_VALIDATE = 4
    PAGE_DONE = 5
    PAGE_COUNT = 6

    def __init__(
        self,
        config: Dict[str, Any],
        engine_controller: EngineController,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.controller = GetStockfishController(
            engine_controller, config, self
        )
        self._binary_radios: List[QRadioButton] = []
        self._binary_group = QButtonGroup(self)
        self._executable_path: Optional[Path] = None
        self._fetching = False
        self._lookup_failed = False
        self._downloading = False
        self._validating = False
        self._validation_failed = False

        self._load_config()
        self.setWindowTitle(self.copy_window_title)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, False)
        self._setup_ui()
        self._apply_styling()
        self._apply_configured_dialog_size()
        self._connect_signals()
        self._show_page(self.PAGE_WELCOME)

    def _copy(self, key: str, default: str = "") -> str:
        value = self._copy_config.get(key, default)
        return str(value) if value is not None else default

    def _fmt(self, key: str, default: str = "", **kwargs: Any) -> str:
        template = self._copy(key, default)
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError, IndexError):
            return template

    def _load_config(self) -> None:
        dialog_config = (
            self.config.get("ui", {}).get("dialogs", {}).get(self.CONFIG_KEY, {})
        )
        self.dialog_width = int(dialog_config.get("width", 560))
        self.dialog_height = int(dialog_config.get("height", 480))
        self.bottom_button_top_padding = int(
            dialog_config.get("bottom_button_top_padding", 25)
        )
        self.dialog_bg = dialog_config.get("background_color", [40, 40, 45])
        self.dialog_border = dialog_config.get("border_color", [60, 60, 65])
        self.dialog_text = dialog_config.get("text_color", [240, 240, 240])

        self.official_download_page_url = str(
            dialog_config.get("official_download_page_url")
            or self.controller.official_download_page_url
            or ""
        )

        layout_config = dialog_config.get("layout", {})
        self.layout_spacing = int(layout_config.get("spacing", 12))
        self.layout_margins = layout_config.get("margins", [24, 22, 24, 20])

        labels_config = dialog_config.get("labels", {})
        self.label_font_family = resolve_font_family(
            labels_config.get("font_family", "Helvetica Neue")
        )
        self.label_font_size = scale_font_size(labels_config.get("font_size", 11))
        self.label_text_color = labels_config.get("text_color", [200, 200, 200])
        self.title_font_size = scale_font_size(
            labels_config.get("title_font_size", 15)
        )
        self.title_text_color = labels_config.get(
            "title_text_color", self.dialog_text
        )
        self.hint_font_size = scale_font_size(
            labels_config.get("hint_font_size", 10)
        )
        self.hint_text_color = labels_config.get("hint_text_color", [150, 150, 150])

        inputs_config = dialog_config.get("inputs", {})
        self.input_font_family = resolve_font_family(
            inputs_config.get("font_family", "Helvetica Neue")
        )
        self.input_font_size = scale_font_size(inputs_config.get("font_size", 11))
        self.input_bg = inputs_config.get("background_color", [30, 30, 35])
        self.input_border = inputs_config.get("border_color", [60, 60, 65])
        self.input_text = inputs_config.get("text_color", [240, 240, 240])
        self.input_focus_border = inputs_config.get(
            "focus_border_color", [70, 90, 130]
        )
        self.input_border_radius = int(inputs_config.get("border_radius", 3))
        self.input_padding = inputs_config.get("padding", [8, 6])
        self.input_min_height = int(inputs_config.get("minimum_height", 30))
        self.browse_button_icon_svg = str(
            inputs_config.get("browse_button_icon_svg") or SVG_MENU_FOLDER_OPEN
        )

        buttons_config = dialog_config.get("buttons", {})
        self.button_width = int(buttons_config.get("width", 110))
        self.button_height = int(buttons_config.get("height", 30))
        self.button_spacing = int(buttons_config.get("spacing", 10))
        self.button_border = buttons_config.get(
            "border_color", self.dialog_border
        )

        progress_config = dialog_config.get("progress", {})
        self.progress_chunk = progress_config.get("chunk_color", [70, 110, 160])
        self.progress_height = int(progress_config.get("height", 18))

        self._copy_config = dialog_config.get("copy", {}) or {}
        self.copy_window_title = self._copy("window_title", "Get Stockfish")
        self.copy_welcome_title = self._copy(
            "welcome_title", "Get Stockfish for CARA"
        )
        self.copy_welcome_body = self._copy("welcome_body")
        self.copy_official_note = self._fmt(
            "official_note",
            url=self.official_download_page_url,
        )
        self.copy_binary_title = self._copy(
            "binary_title", "Choose a Stockfish build"
        )
        self.copy_binary_hint = self._copy("binary_hint")
        self.copy_folder_title = self._copy(
            "folder_title", "Choose install folder"
        )
        self.copy_folder_body = self._copy("folder_body")
        self.copy_download_title = self._copy(
            "download_title", "Downloading Stockfish"
        )
        self.copy_done_title = self._copy("done_title", "Stockfish is ready")
        self.copy_button_back = self._copy("button_back", "Back")
        self.copy_button_cancel = self._copy("button_cancel", "Cancel")
        self.copy_button_cancel_download = self._copy(
            "button_cancel_download", "Cancel download"
        )
        self.copy_button_next = self._copy("button_next", "Next")
        self.copy_button_download = self._copy("button_download", "Download")
        self.copy_button_retry = self._copy("button_retry", "Retry validation")
        self.copy_button_retry_lookup = self._copy("button_retry_lookup", "Retry")
        self.copy_button_finish = self._copy("button_finish", "Finish")
        self.copy_button_browse = self._copy("button_browse", "Browse…")
        self.copy_folder_browse_title = self._copy(
            "folder_browse_title", "Select Stockfish install folder"
        )
        self.copy_looking_up_release = self._copy("looking_up_release")
        self.copy_download_preparing = self._copy("download_preparing")
        self.copy_validate_title = self._copy(
            "validate_title", "Validating Stockfish"
        )
        self.copy_recommended_suffix = self._copy(
            "recommended_suffix", "  —  Recommended"
        )
        self.binary_option_spacing = int(
            dialog_config.get("binary_option_spacing", 10)
        )

    def _setup_ui(self) -> None:
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(
            self.backgroundRole(),
            QColor(self.dialog_bg[0], self.dialog_bg[1], self.dialog_bg[2]),
        )
        self.setPalette(palette)

        root = QVBoxLayout(self)
        root.setSpacing(self.layout_spacing)
        m = self.layout_margins
        root.setContentsMargins(int(m[0]), int(m[1]), int(m[2]), int(m[3]))

        self.step_label = QLabel()
        root.addWidget(self.step_label)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_welcome_page())
        self.stack.addWidget(self._build_binary_page())
        self.stack.addWidget(self._build_folder_page())
        self.stack.addWidget(self._build_download_page())
        self.stack.addWidget(self._build_validate_page())
        self.stack.addWidget(self._build_done_page())
        root.addWidget(self.stack, 1)

        root.addSpacing(self.bottom_button_top_padding)

        buttons = QHBoxLayout()
        buttons.setSpacing(self.button_spacing)
        self.back_button = QPushButton(self.copy_button_back)
        self.back_button.clicked.connect(self._on_back)
        buttons.addWidget(self.back_button)
        buttons.addStretch(1)
        self.cancel_button = QPushButton(self.copy_button_cancel)
        self.cancel_button.clicked.connect(self._on_cancel)
        buttons.addWidget(self.cancel_button)
        self.next_button = QPushButton(self.copy_button_next)
        self.next_button.clicked.connect(self._on_next)
        buttons.addWidget(self.next_button)
        root.addLayout(buttons)

    def _build_welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.layout_spacing)

        self.welcome_title = QLabel(self.copy_welcome_title)
        self.welcome_title.setWordWrap(True)
        layout.addWidget(self.welcome_title)

        self.welcome_body = QLabel(self.copy_welcome_body)
        self.welcome_body.setWordWrap(True)
        layout.addWidget(self.welcome_body)

        self.welcome_platform = QLabel()
        self.welcome_platform.setWordWrap(True)
        layout.addWidget(self.welcome_platform)

        self.welcome_note = QLabel(self.copy_official_note)
        self.welcome_note.setWordWrap(True)
        layout.addWidget(self.welcome_note)
        layout.addStretch(1)
        return page

    def _build_binary_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.layout_spacing)

        self.binary_title = QLabel(self.copy_binary_title)
        self.binary_title.setWordWrap(True)
        layout.addWidget(self.binary_title)

        self.binary_status = QLabel(self.copy_looking_up_release)
        self.binary_status.setWordWrap(True)
        self.binary_status.setTextFormat(Qt.TextFormat.RichText)
        self.binary_status.setOpenExternalLinks(True)
        self.binary_status.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        layout.addWidget(self.binary_status)

        self.binary_release = QLabel()
        self.binary_release.setWordWrap(True)
        layout.addWidget(self.binary_release)

        self.binary_scroll = QScrollArea()
        self.binary_scroll.setWidgetResizable(True)
        self.binary_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.binary_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        # Do not set a QScrollArea stylesheet that targets QWidget — that forces
        # stylesheet painting on radios and breaks native indicators.
        self.binary_list_host = QWidget()
        self.binary_list_layout = QVBoxLayout(self.binary_list_host)
        self.binary_list_layout.setContentsMargins(0, 0, 8, 0)
        self.binary_list_layout.setSpacing(self.binary_option_spacing)
        self.binary_list_layout.addStretch(1)
        self.binary_scroll.setWidget(self.binary_list_host)
        layout.addWidget(self.binary_scroll, 1)

        self.binary_hint = QLabel(self.copy_binary_hint)
        self.binary_hint.setWordWrap(True)
        layout.addWidget(self.binary_hint)
        return page

    def _build_folder_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.layout_spacing)

        self.folder_title = QLabel(self.copy_folder_title)
        self.folder_title.setWordWrap(True)
        layout.addWidget(self.folder_title)

        self.folder_body = QLabel(self.copy_folder_body)
        self.folder_body.setWordWrap(True)
        layout.addWidget(self.folder_body)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.setContentsMargins(0, 0, 0, 0)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.folder_edit = QLineEdit()
        self.folder_edit.setText(str(self.controller.install_directory))
        self.folder_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        row.addWidget(self.folder_edit, 1, Qt.AlignmentFlag.AlignVCenter)
        # Icon-only browse control — same pattern as Add Engine dialog.
        self.browse_button = QPushButton()
        self.browse_button.setToolTip(self.copy_button_browse)
        self.browse_button.setAccessibleName(self.copy_button_browse)
        self.browse_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.browse_button.clicked.connect(self._browse_folder)
        row.addWidget(self.browse_button, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(row)

        self.folder_hint = QLabel()
        self.folder_hint.setWordWrap(True)
        layout.addWidget(self.folder_hint)
        layout.addStretch(1)
        return page

    def _build_download_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.layout_spacing)

        self.download_title = QLabel(self.copy_download_title)
        self.download_title.setWordWrap(True)
        layout.addWidget(self.download_title)

        self.download_detail = QLabel()
        self.download_detail.setWordWrap(True)
        layout.addWidget(self.download_detail)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(self.progress_height)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        self.download_status = QLabel(self.copy_download_preparing)
        self.download_status.setWordWrap(True)
        layout.addWidget(self.download_status)
        layout.addStretch(1)
        return page

    def _build_validate_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.layout_spacing)

        self.validate_title = QLabel(self.copy_validate_title)
        self.validate_title.setWordWrap(True)
        layout.addWidget(self.validate_title)

        self.validate_status = QLabel()
        self.validate_status.setWordWrap(True)
        layout.addWidget(self.validate_status)

        self.validate_path = QLabel()
        self.validate_path.setWordWrap(True)
        layout.addWidget(self.validate_path)

        self.validate_hint = QLabel()
        self.validate_hint.setWordWrap(True)
        layout.addWidget(self.validate_hint)
        layout.addStretch(1)
        return page

    def _build_done_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.layout_spacing)

        self.done_title = QLabel(self.copy_done_title)
        self.done_title.setWordWrap(True)
        layout.addWidget(self.done_title)

        self.done_body = QLabel()
        self.done_body.setWordWrap(True)
        layout.addWidget(self.done_body)
        layout.addStretch(1)
        return page

    def _apply_styling(self) -> None:
        title_style = (
            f"QLabel {{"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.title_font_size}pt;"
            f"font-weight: bold;"
            f"color: rgb({self.title_text_color[0]}, {self.title_text_color[1]}, {self.title_text_color[2]});"
            f"background-color: transparent;"
            f"}}"
        )
        body_style = (
            f"QLabel {{"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.label_font_size}pt;"
            f"color: rgb({self.label_text_color[0]}, {self.label_text_color[1]}, {self.label_text_color[2]});"
            f"background-color: transparent;"
            f"}}"
        )
        hint_style = (
            f"QLabel {{"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.hint_font_size}pt;"
            f"color: rgb({self.hint_text_color[0]}, {self.hint_text_color[1]}, {self.hint_text_color[2]});"
            f"background-color: transparent;"
            f"}}"
        )
        for label in (
            self.welcome_title,
            self.binary_title,
            self.folder_title,
            self.download_title,
            self.validate_title,
            self.done_title,
        ):
            label.setStyleSheet(title_style)
        for label in (
            self.welcome_body,
            self.welcome_platform,
            self.binary_status,
            self.binary_release,
            self.folder_body,
            self.download_detail,
            self.download_status,
            self.validate_status,
            self.validate_path,
            self.done_body,
            self.step_label,
        ):
            label.setStyleSheet(body_style)
        for label in (
            self.welcome_note,
            self.binary_hint,
            self.folder_hint,
            self.validate_hint,
        ):
            label.setStyleSheet(hint_style)

        StyleManager.style_line_edits(
            [self.folder_edit],
            self.config,
            text_color=self.input_text,
            font_family=self.input_font_family,
            font_size=self.input_font_size,
            bg_color=self.input_bg,
            border_color=self.input_border,
            focus_border_color=self.input_focus_border,
            border_radius=self.input_border_radius,
            padding=self.input_padding,
        )
        StyleManager.style_buttons(
            [
                self.back_button,
                self.cancel_button,
                self.next_button,
            ],
            self.config,
            self.dialog_bg,
            self.button_border,
            min_width=self.button_width,
            min_height=self.button_height,
        )
        for button in (
            self.back_button,
            self.cancel_button,
            self.next_button,
        ):
            button.setFixedHeight(self.button_height)

        # Match Browse to the folder field (Add Engine style: themed folder icon).
        input_v_pad = (
            int(self.input_padding[1])
            if isinstance(self.input_padding, (list, tuple))
            and len(self.input_padding) >= 2
            else 6
        )
        StyleManager.style_buttons(
            [self.browse_button],
            self.config,
            self.dialog_bg,
            self.input_border,
            text_color=self.input_text,
            font_family=self.input_font_family,
            font_size=self.input_font_size,
            border_radius=self.input_border_radius,
            padding=input_v_pad,
        )
        browse_tint = (
            int(self.input_text[0]),
            int(self.input_text[1]),
            int(self.input_text[2]),
        )
        self.browse_button.setIcon(
            themed_icon_from_svg(self.browse_button_icon_svg, browse_tint)
        )
        self.browse_button.setText("")
        self.browse_button.setIconSize(QSize(20, 20))
        self._align_folder_row_heights()

        self._style_binary_scroll_area()

        self.progress_bar.setStyleSheet(
            f"QProgressBar {{"
            f"background-color: rgb({self.input_bg[0]}, {self.input_bg[1]}, {self.input_bg[2]});"
            f"border: 1px solid rgb({self.input_border[0]}, {self.input_border[1]}, {self.input_border[2]});"
            f"border-radius: {self.input_border_radius}px;"
            f"text-align: center;"
            f"color: rgb({self.input_text[0]}, {self.input_text[1]}, {self.input_text[2]});"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.hint_font_size}pt;"
            f"}}"
            f"QProgressBar::chunk {{"
            f"background-color: rgb({self.progress_chunk[0]}, {self.progress_chunk[1]}, {self.progress_chunk[2]});"
            f"border-radius: {max(0, self.input_border_radius - 1)}px;"
            f"}}"
        )

    def _apply_configured_dialog_size(self) -> None:
        self.setFixedSize(self.dialog_width, self.dialog_height)

    def _fill_widget_background(self, widget: QWidget, rgb) -> None:
        widget.setAutoFillBackground(True)
        palette = widget.palette()
        palette.setColor(
            widget.backgroundRole(),
            QColor(int(rgb[0]), int(rgb[1]), int(rgb[2])),
        )
        widget.setPalette(palette)

    def _align_folder_row_heights(self) -> None:
        """Square icon Browse button matching the folder field height (Add Engine)."""
        self.folder_edit.updateGeometry()
        self.browse_button.updateGeometry()
        height = max(
            int(self.input_min_height),
            int(self.folder_edit.sizeHint().height()),
            int(self.browse_button.sizeHint().height()),
        )
        icon_px = max(16, min(24, height - 8))
        self.browse_button.setIconSize(QSize(icon_px, icon_px))

        for widget in (self.folder_edit, self.browse_button):
            widget.setFixedHeight(height)
            widget.setMinimumHeight(height)
            widget.setMaximumHeight(height)
        self.browse_button.setContentsMargins(0, 0, 0, 0)
        self.browse_button.setFixedWidth(height)
        self.browse_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )

        sheet = self.browse_button.styleSheet()
        sheet = re.sub(r"(min-height|max-height|height|min-width|max-width|width):\s*\d+px;?", "", sheet)
        if "margin:" not in sheet:
            sheet = sheet.replace("QPushButton {", "QPushButton {\nmargin: 0px;")
        else:
            sheet = re.sub(r"margin:\s*[^;]+;", "margin: 0px;", sheet)
        self.browse_button.setStyleSheet(sheet)

    def _style_binary_scroll_area(self) -> None:
        """Theme scroll chrome without stylesheet rules that retarget child QWidgets.

        ``StyleManager.style_scroll_area`` injects ``QScrollArea QWidget {…}``, which
        forces radios into the stylesheet engine and breaks native indicators.
        """
        from app.views.style.scrollbar import generate_scrollbar_stylesheet

        self.binary_scroll.setStyleSheet("")
        viewport = self.binary_scroll.viewport()
        if viewport is not None:
            self._fill_widget_background(viewport, self.dialog_bg)
        self._fill_widget_background(self.binary_list_host, self.dialog_bg)

        scrollbar = self.binary_scroll.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setStyleSheet(
                generate_scrollbar_stylesheet(
                    self.config, self.dialog_bg, self.dialog_border
                )
            )

    def _connect_signals(self) -> None:
        self.controller.options_ready.connect(self._on_options_ready)
        self.controller.options_failed.connect(self._on_options_failed)
        self.controller.download_progress.connect(self._on_download_progress)
        self.controller.download_finished.connect(self._on_download_finished)
        self.controller.download_failed.connect(self._on_download_failed)
        self.controller.validation_finished.connect(self._on_validation_finished)
        self.controller.validation_failed.connect(self._on_validation_failed)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        info = self.controller.platform_info
        self.welcome_platform.setText(
            self._fmt("detected_system", system=info.display_name)
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        self.controller.cleanup()
        super().closeEvent(event)

    def _show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.step_label.setText(
            self._fmt(
                "step_label",
                current=index + 1,
                total=self.PAGE_COUNT,
            )
        )
        self.back_button.setEnabled(
            index > 0 and not self._downloading and not self._validating
        )
        self.cancel_button.setEnabled(not self._validating)

        if index == self.PAGE_WELCOME:
            self.next_button.setText(self.copy_button_next)
            self.next_button.setEnabled(True)
        elif index == self.PAGE_BINARY:
            if self._lookup_failed:
                self.next_button.setText(self.copy_button_retry_lookup)
                self.next_button.setEnabled(not self._fetching)
            else:
                self.next_button.setText(self.copy_button_next)
                self.next_button.setEnabled(
                    bool(self.controller.options) and not self._fetching
                )
            if (
                not self.controller.options
                and not self._fetching
                and not self._lookup_failed
            ):
                self._start_fetch()
        elif index == self.PAGE_FOLDER:
            self._refresh_folder_hint()
            self.next_button.setText(self.copy_button_download)
            self.next_button.setEnabled(True)
        elif index == self.PAGE_DOWNLOAD:
            self.next_button.setText(self.copy_button_next)
            self.next_button.setEnabled(False)
            self.back_button.setEnabled(False)
        elif index == self.PAGE_VALIDATE:
            if self._validation_failed:
                self.next_button.setText(self.copy_button_retry)
                self.next_button.setEnabled(True)
                self.back_button.setEnabled(True)
            else:
                self.next_button.setText(self.copy_button_next)
                self.next_button.setEnabled(False)
                self.back_button.setEnabled(False)
        elif index == self.PAGE_DONE:
            self.next_button.setText(self.copy_button_finish)
            self.next_button.setEnabled(True)
            self.back_button.setEnabled(False)
            self.cancel_button.setEnabled(False)

    def _start_fetch(self) -> None:
        self._fetching = True
        self._lookup_failed = False
        self.binary_status.setTextFormat(Qt.TextFormat.PlainText)
        self.binary_status.setText(self.copy_looking_up_release)
        self.binary_release.setText("")
        self.binary_hint.setVisible(True)
        self.next_button.setText(self.copy_button_next)
        self.next_button.setEnabled(False)
        self.controller.start_fetch_options()

    def _on_options_ready(
        self,
        info,
        tag: str,
        name: str,
        options: List[ResolvedStockfishAsset],
    ) -> None:
        self._fetching = False
        self._lookup_failed = False
        self.binary_status.setTextFormat(Qt.TextFormat.PlainText)
        self.binary_status.setText(
            self._fmt("detected_system", system=info.display_name)
        )
        self.binary_release.setText(
            self._fmt("latest_release", name=name or tag)
        )
        self.binary_hint.setVisible(True)
        self._rebuild_binary_list(options)
        if self.stack.currentIndex() == self.PAGE_BINARY:
            self.next_button.setText(self.copy_button_next)
            self.next_button.setEnabled(True)

    def _manual_download_link_html(self) -> str:
        url = self.official_download_page_url
        return f'<a href="{url}">{url}</a>'

    def _on_options_failed(self, kind: str, detail: str = "") -> None:
        self._fetching = False
        self._lookup_failed = True
        self.binary_release.setText("")
        self.binary_hint.setVisible(False)
        # Clear any previous option radios so the page does not look half-populated.
        self._rebuild_binary_list([])

        url_html = self._manual_download_link_html()
        if kind == "offline":
            body = self._fmt("lookup_failed_offline", url=url_html)
        elif kind == "timeout":
            body = self._fmt("lookup_failed_timeout", url=url_html)
        elif kind == "http":
            body = self._fmt(
                "lookup_failed_http",
                status=detail or "?",
                url=url_html,
            )
        else:
            body = self._fmt(
                "lookup_failed_generic",
                error=detail or "Unexpected error.",
                url=url_html,
            )

        # Preserve newlines in RichText.
        body_html = body.replace("\n", "<br>")
        self.binary_status.setTextFormat(Qt.TextFormat.RichText)
        self.binary_status.setOpenExternalLinks(True)
        self.binary_status.setText(body_html)

        if self.stack.currentIndex() == self.PAGE_BINARY:
            self.next_button.setText(self.copy_button_retry_lookup)
            self.next_button.setEnabled(True)

    def _rebuild_binary_list(self, options: List[ResolvedStockfishAsset]) -> None:
        while self.binary_list_layout.count():
            item = self.binary_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._binary_radios.clear()
        for button in list(self._binary_group.buttons()):
            self._binary_group.removeButton(button)

        recommended_id = self.controller.recommended_option_id()
        for asset in options:
            radio = QRadioButton()
            title = asset.option.label
            if asset.option.recommended or asset.option.id == recommended_id:
                title = f"{title}{self.copy_recommended_suffix}"
            radio.setText(title)
            radio.setProperty("option_id", asset.option.id)
            radio.setToolTip(
                f"{asset.option.description}\n"
                f"File: {asset.filename} ({format_bytes(asset.size_bytes)})"
            )
            desc = QLabel(asset.option.description)
            desc.setWordWrap(True)
            desc.setStyleSheet(
                f"QLabel {{"
                f"font-family: {self.label_font_family};"
                f"font-size: {self.hint_font_size}pt;"
                f"color: rgb({self.hint_text_color[0]}, {self.hint_text_color[1]}, {self.hint_text_color[2]});"
                f"background-color: transparent;"
                f"margin-left: 22px;"
                f"}}"
            )
            block = QWidget()
            block.setAutoFillBackground(False)
            block_layout = QVBoxLayout(block)
            block_layout.setContentsMargins(0, 0, 0, 0)
            block_layout.setSpacing(2)
            block_layout.addWidget(radio)
            block_layout.addWidget(desc)
            self.binary_list_layout.addWidget(block)
            self._binary_group.addButton(radio)
            self._binary_radios.append(radio)
            if asset.option.id == recommended_id:
                radio.setChecked(True)

        StyleManager.style_radio_buttons(
            self._binary_radios,
            self.config,
            text_color=self.label_text_color,
            font_family=self.label_font_family,
            font_size=self.label_font_size,
        )
        self.binary_list_layout.addStretch(1)
        self._style_binary_scroll_area()

    def _selected_option_id(self) -> Optional[str]:
        for radio in self._binary_radios:
            if radio.isChecked():
                return str(radio.property("option_id") or "")
        return None

    def _browse_folder(self) -> None:
        start = self.folder_edit.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self, self.copy_folder_browse_title, start
        )
        if chosen:
            self.folder_edit.setText(chosen)
            self._refresh_folder_hint()

    def _refresh_folder_hint(self) -> None:
        asset = self.controller.selected_asset
        if asset is None:
            self.folder_hint.setText("")
            return
        self.folder_hint.setText(
            self._fmt(
                "selected_build",
                label=asset.option.label,
                size=format_bytes(asset.size_bytes),
            )
        )

    def _on_back(self) -> None:
        index = self.stack.currentIndex()
        if index <= 0 or self._downloading or self._validating:
            return
        if index == self.PAGE_VALIDATE:
            # Skip the transient download page when going back after failure.
            self._validation_failed = False
            self._show_page(self.PAGE_FOLDER)
            return
        self._show_page(index - 1)

    def _on_cancel(self) -> None:
        if self._downloading:
            self.controller.cancel_download()
            self.download_status.setText(self._copy("download_cancelling"))
            return
        if self._validating:
            return
        self.controller.cleanup()
        self.reject()

    def _on_next(self) -> None:
        index = self.stack.currentIndex()
        if index == self.PAGE_WELCOME:
            self._show_page(self.PAGE_BINARY)
            return
        if index == self.PAGE_BINARY:
            if self._lookup_failed:
                self._start_fetch()
                return
            option_id = self._selected_option_id()
            if not option_id:
                return
            self.controller.set_selected_option_id(option_id)
            self._show_page(self.PAGE_FOLDER)
            return
        if index == self.PAGE_FOLDER:
            folder = self.folder_edit.text().strip()
            if not folder:
                self.folder_hint.setText(self._copy("folder_missing"))
                return
            path = Path(folder)
            try:
                path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self.folder_hint.setText(
                    self._fmt("folder_invalid", error=exc)
                )
                return
            self.controller.set_install_directory(path)
            self._start_download()
            return
        if index == self.PAGE_VALIDATE:
            if self._validation_failed and self._executable_path is not None:
                self._start_validation(self._executable_path)
            return
        if index == self.PAGE_DONE:
            self.controller.cleanup()
            self.accept()

    def _start_download(self) -> None:
        asset = self.controller.selected_asset
        if asset is None:
            return
        self._downloading = True
        self._show_page(self.PAGE_DOWNLOAD)
        self.progress_bar.setValue(0)
        self.download_detail.setText(
            self._fmt(
                "download_detail",
                filename=asset.filename,
                release=self.controller.release_label,
            )
        )
        self.download_status.setText(self._copy("download_starting"))
        self.cancel_button.setText(self.copy_button_cancel_download)
        self.controller.start_download()

    def _on_download_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(int(downloaded * 100 / total))
            self.download_status.setText(
                self._fmt(
                    "download_progress",
                    downloaded=format_bytes(downloaded),
                    total=format_bytes(total),
                )
            )
        else:
            self.progress_bar.setRange(0, 0)
            self.download_status.setText(
                self._fmt(
                    "download_progress_unknown",
                    downloaded=format_bytes(downloaded),
                )
            )

    def _on_download_finished(self, executable: object) -> None:
        self._downloading = False
        self.cancel_button.setText(self.copy_button_cancel)
        path = Path(str(executable))
        self._executable_path = path
        self.download_status.setText(self._copy("download_complete"))
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self._start_validation(path)

    def _on_download_failed(self, message: str) -> None:
        self._downloading = False
        self.cancel_button.setText(self.copy_button_cancel)
        self.progress_bar.setRange(0, 100)
        self.download_status.setText(
            self._fmt("download_failed", error=message)
        )
        self.back_button.setEnabled(True)
        self.next_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

    def _start_validation(self, path: Path) -> None:
        self._validating = True
        self._validation_failed = False
        self.validate_status.setText(self._copy("validate_checking"))
        self.validate_path.setText(self._fmt("validate_path", path=path))
        self.validate_hint.setText("")
        self._show_page(self.PAGE_VALIDATE)
        self.controller.start_validation(path)

    def _on_validation_finished(self, message: str) -> None:
        self._validating = False
        self._validation_failed = False
        path = self._executable_path or Path("")
        self.done_body.setText(
            self._fmt("done_body", message=message, path=path)
        )
        self._show_page(self.PAGE_DONE)

    def _on_validation_failed(self, message: str) -> None:
        self._validating = False
        self._validation_failed = True
        self.validate_status.setText(
            self._fmt("validate_failed", error=message)
        )
        self.validate_hint.setText(
            self._fmt(
                "validate_failed_hint",
                url=self.official_download_page_url,
            )
        )
        self.next_button.setText(self.copy_button_retry)
        self.next_button.setEnabled(True)
        self.back_button.setEnabled(True)
        self.cancel_button.setEnabled(True)
