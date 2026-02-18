"""Generic dialog for displaying file content (e.g. markdown or plain text) inline."""

from pathlib import Path
from typing import Dict, Any, Literal

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTextBrowser,
    QPushButton,
)
from PyQt6.QtGui import QColor, QTextCursor, QDesktopServices

from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.markdown_to_html import markdown_to_html
from app.utils.path_resolver import get_app_root


class InlineContentDialog(QDialog):
    """Styled dialog that displays file content as markdown or plain text."""

    def __init__(
        self,
        config: Dict[str, Any],
        window_title: str,
        content_path: Path,
        content_format: Literal["markdown", "plain"] = "markdown",
        fallback_message: str = "Content not found.",
        parent=None,
    ) -> None:
        """Initialize the inline content dialog.

        Args:
            config: Configuration dictionary.
            window_title: Dialog window title.
            content_path: Path to the file to display (absolute or relative to app root).
            content_format: "markdown" to render as markdown, "plain" for plain text.
            fallback_message: Message shown when the file is missing or unreadable.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config

        dialog_config = (self.config.get("ui") or {}).get("dialogs") or {}
        dialog_config = (dialog_config.get("inline_content_dialog") or {}).copy()
        layout_config = (dialog_config.get("layout") or {}).copy()
        content_config = (dialog_config.get("content") or {}).copy()
        buttons_config = (dialog_config.get("buttons") or {}).copy()

        self.setWindowTitle(window_title)
        dialog_width = dialog_config.get("width", 700)
        dialog_height = dialog_config.get("height", 500)
        self.setMinimumSize(
            dialog_config.get("minimum_width", 500),
            dialog_config.get("minimum_height", 400),
        )
        self.resize(dialog_width, dialog_height)

        bg_color = dialog_config.get("background_color", [40, 40, 45])
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(bg_color[0], bg_color[1], bg_color[2]))
        self.setPalette(palette)

        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(layout_config.get("spacing", 15))
        margins = layout_config.get("margins", [20, 20, 20, 20])
        main_layout.setContentsMargins(margins[0], margins[1], margins[2], margins[3])

        def _num(val, default: float):
            if isinstance(val, (int, float)):
                return float(val)
            try:
                return float(val) if val is not None else default
            except (TypeError, ValueError):
                return default

        content_font_family = resolve_font_family(content_config.get("font_family") or "Helvetica Neue")
        content_font_size = scale_font_size(_num(content_config.get("font_size"), 11))
        content_color = content_config.get("text_color") or [200, 200, 200]
        link_color = content_config.get("link_color") or [100, 150, 255]
        if not isinstance(content_color, (list, tuple)) or len(content_color) < 3:
            content_color = [200, 200, 200]
        if not isinstance(link_color, (list, tuple)) or len(link_color) < 3:
            link_color = [100, 150, 255]

        text_browser = QTextBrowser(self)
        self._text_browser = text_browser
        text_browser.setReadOnly(True)
        text_browser.setOpenLinks(False)
        text_browser.setOpenExternalLinks(False)
        text_browser.anchorClicked.connect(self._on_anchor_clicked)

        content_style = (
            f"font-family: {content_font_family}; "
            f"font-size: {content_font_size}pt; "
            f"color: rgb({content_color[0]}, {content_color[1]}, {content_color[2]}); "
            f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]}); "
            f"border: none; "
            f"QTextBrowser a {{ color: rgb({link_color[0]}, {link_color[1]}, {link_color[2]}); }}"
        )
        text_browser.setStyleSheet(content_style)

        path = content_path if content_path.is_absolute() else get_app_root() / content_path
        self._content_base_path = path.parent
        if path.exists():
            try:
                raw_text = path.read_text(encoding="utf-8")
                if content_format == "markdown":
                    doc = text_browser.document()
                    doc.setDefaultStyleSheet(
                        self._markdown_document_stylesheet(bg_color=bg_color, content_config=content_config)
                    )
                    heading_styles = self._build_heading_inline_styles(content_config)
                    html_body = markdown_to_html(
                        raw_text,
                        heading_styles=heading_styles,
                        heading_level_offset=1,
                    )
                    doc.setHtml(f"<body>{html_body}</body>")
                else:
                    text_browser.setPlainText(raw_text)
            except Exception:
                import sys
                import traceback
                traceback.print_exc(file=sys.stderr)
                try:
                    from app.services.logging_service import LoggingService
                    LoggingService.get_instance().exception("Failed to load inline content")
                except Exception:
                    pass
                text_browser.setPlainText(fallback_message)
                raise
        else:
            text_browser.setPlainText(fallback_message)

        from app.views.style import StyleManager

        scroll_border_color = dialog_config.get("border_color", [60, 60, 65])
        StyleManager.style_text_edit_scrollbar(
            text_browser, self.config, bg_color, scroll_border_color, content_style
        )
        main_layout.addWidget(text_browser)

        main_layout.addSpacing(layout_config.get("button_section_top_margin", 15))
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        button_width = buttons_config.get("width", 120)
        button_height = buttons_config.get("height", 30)
        btn_border_color = buttons_config.get("border_color", [60, 60, 65])
        bg_color_list = [bg_color[0], bg_color[1], bg_color[2]]
        border_color_list = (
            list(btn_border_color) if isinstance(btn_border_color, (list, tuple)) else [60, 60, 65]
        )

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        StyleManager.style_buttons(
            [close_button],
            self.config,
            bg_color_list,
            border_color_list,
            min_width=button_width,
            min_height=button_height,
        )
        main_layout.addLayout(button_layout)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Scroll to top after layout; deferred so it runs after the dialog is shown
        QTimer.singleShot(0, self._scroll_text_to_top)

    def _scroll_text_to_top(self) -> None:
        browser = getattr(self, "_text_browser", None)
        if browser is None:
            return
        cursor = browser.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        browser.setTextCursor(cursor)
        browser.verticalScrollBar().setValue(0)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """Open the link in the system default browser/app (never navigate within the dialog)."""
        if url.isEmpty():
            return

        if url.isRelative() or not url.scheme():
            base = getattr(self, "_content_base_path", None)
            if base is not None:
                path_str = url.path().lstrip("/")
                if not path_str:
                    return
                resolved = (base / path_str).resolve()
                url = QUrl.fromLocalFile(str(resolved))
            else:
                url = QUrl.fromLocalFile(url.path())

        QDesktopServices.openUrl(url)

    def _build_heading_inline_styles(self, content_config: Dict[str, Any]) -> Dict[str, str]:
        """Build a dict of h1–h6 to inline style strings (for markdown_to_html). Uses config + DPI scaling."""
        try:
            content_font_size = scale_font_size(float(content_config.get("font_size") or 11))
        except (TypeError, ValueError):
            content_font_size = scale_font_size(11)
        headings_config = content_config.get("headings") or {}
        if not isinstance(headings_config, dict):
            headings_config = {}
        _defaults = {
            "h1": (0.75, 0.5, 1.1),
            "h2": (1, 0.4, 1.35),
            "h3": (0.85, 0.35, 1.2),
            "h4": (0.75, 0.3, 1.05),
            "h5": (0.65, 0.25, 1),
            "h6": (0.55, 0.2, 0.95),
        }
        result: Dict[str, str] = {}
        for level in range(1, 7):
            key = f"h{level}"
            h = headings_config.get(key) or {}
            if not isinstance(h, dict):
                h = {}
            def_mt, def_mb, def_fs = _defaults.get(key, (0.75, 0.5, 1.6))
            mt = h.get("margin_top_em", def_mt)
            mb = h.get("margin_bottom_em", def_mb)
            fs_em = h.get("font_size_em", def_fs)
            pt = max(1, int(round(content_font_size * fs_em)))
            result[key] = f"margin-top: {mt}em; margin-bottom: {mb}em; font-size: {pt}pt; font-weight: bold;"
        return result

    @staticmethod
    def _markdown_document_stylesheet(bg_color: list, content_config: Dict[str, Any]) -> str:
        """Build a CSS stylesheet for markdown-rendered content from config."""
        if not bg_color or not isinstance(bg_color, (list, tuple)) or len(bg_color) < 3:
            bg_color = [40, 40, 45]
        content_font_family = resolve_font_family(content_config.get("font_family") or "Helvetica Neue")
        try:
            content_font_size = scale_font_size(float(content_config.get("font_size") or 11))
        except (TypeError, ValueError):
            content_font_size = scale_font_size(11)
        content_color = content_config.get("text_color") or [200, 200, 200]
        link_color = content_config.get("link_color") or [100, 150, 255]
        if not isinstance(content_color, (list, tuple)) or len(content_color) < 3:
            content_color = [200, 200, 200]
        if not isinstance(link_color, (list, tuple)) or len(link_color) < 3:
            link_color = [100, 150, 255]
        r, g, b = content_color[0], content_color[1], content_color[2]
        lr, lg, lb = link_color[0], link_color[1], link_color[2]

        pre_block = content_config.get("pre_block") or {}
        if not isinstance(pre_block, dict):
            pre_block = {}
        bg_off = pre_block.get("background_color_offset") or [-8, -8, 5]
        if not isinstance(bg_off, (list, tuple)) or len(bg_off) < 3:
            bg_off = [-8, -8, 5]
        br, bg_val, bb = bg_color[0], bg_color[1], bg_color[2]
        pre_bg = (
            max(0, br + int(bg_off[0])),
            max(0, bg_val + int(bg_off[1])),
            min(255, bb + int(bg_off[2])),
        )
        border_off = pre_block.get("border_color_offset") or [-15, -15, 10]
        if not isinstance(border_off, (list, tuple)) or len(border_off) < 3:
            border_off = [-15, -15, 10]
        pre_border = (
            max(0, br + int(border_off[0])),
            max(0, bg_val + int(border_off[1])),
            min(255, bb + int(border_off[2])),
        )
        pre_radius = int(pre_block.get("border_radius") or 4)
        padding_em = pre_block.get("padding_em") or [0.75, 1]
        if not isinstance(padding_em, (list, tuple)) or len(padding_em) < 2:
            padding_em = [0.75, 1]
        pre_padding = f"{float(padding_em[0])}em {float(padding_em[1])}em"
        pre_margin_top = pre_block.get("margin_top_em", 0.6)
        pre_margin_bottom = pre_block.get("margin_bottom_em", 0.8)
        pre_font_family = resolve_font_family(
            pre_block.get("font_family") or "Monaco, Menlo, \"Liberation Mono\", Consolas, monospace"
        )
        try:
            pre_font_size_offset = int(pre_block.get("font_size_offset") or -1)
        except (TypeError, ValueError):
            pre_font_size_offset = -1
        pre_font_size_pt = max(9, content_font_size + pre_font_size_offset)

        paragraph_config = content_config.get("paragraph") or {}
        p_mt = float(paragraph_config.get("margin_top_em") or 0.4)
        p_mb = float(paragraph_config.get("margin_bottom_em") or 0.6)

        lists_config = content_config.get("lists") or {}
        if not isinstance(lists_config, dict):
            lists_config = {}
        ul_mt = lists_config.get("margin_top_em", 0.4)
        ul_mb = lists_config.get("margin_bottom_em", 0.6)
        ul_pl = lists_config.get("padding_left_em", 1.5)
        li_mb = lists_config.get("li_margin_bottom_em", 0.2)

        return f"""
            body {{
                font-family: {content_font_family};
                font-size: {content_font_size}pt;
                color: rgb({r}, {g}, {b});
                margin: 0;
                padding: 0;
            }}
            p {{
                margin-top: {p_mt}em;
                margin-bottom: {p_mb}em;
            }}
            ul, ol {{
                margin-top: {ul_mt}em;
                margin-bottom: {ul_mb}em;
                padding-left: {ul_pl}em;
            }}
            li {{
                margin-bottom: {li_mb}em;
            }}
            pre {{
                background-color: rgb({pre_bg[0]}, {pre_bg[1]}, {pre_bg[2]});
                border: 1px solid rgb({pre_border[0]}, {pre_border[1]}, {pre_border[2]});
                border-radius: {pre_radius}px;
                padding: {pre_padding};
                margin-top: {pre_margin_top}em;
                margin-bottom: {pre_margin_bottom}em;
                font-family: {pre_font_family};
                font-size: {pre_font_size_pt}pt;
                white-space: pre-wrap;
                color: rgb({r}, {g}, {b});
            }}
            code {{
                font-family: {pre_font_family};
                font-size: {pre_font_size_pt}pt;
            }}
            a {{ color: rgb({lr}, {lg}, {lb}); text-decoration: underline; }}
        """
