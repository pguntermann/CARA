"""Shared regular-expression editor.

Callers supply the pattern, the replacement, and the case flag they already
store. The dialog edits the pattern. Matches are marked in the sample text.
The replacement is returned unchanged.
"""

from __future__ import annotations

from html import escape
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QShowEvent,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QScrollArea,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from app.controllers.regex_editor_controller import (
    RegexBlock,
    RegexBlockGroup,
    RegexEditorController,
    RegexEditorValues,
    RegexExample,
    RegexExplanation,
)
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.utils.themed_icon import themed_icon_from_svg
from app.views.style import StyleManager
from app.views.style.scrollbar import generate_scrollbar_stylesheet
from app.views.widgets.regex_syntax import RegexSyntaxHighlighter, regex_token_colors


class _BlockMenuHover(QObject):
    """Keeps each custom row in step with the menu's highlighted action."""

    def __init__(self, menu: QMenu) -> None:
        super().__init__(menu)
        menu.hovered.connect(self._on_hovered)
        menu.installEventFilter(self)

    def _on_hovered(self, action) -> None:
        self._apply(action)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Leave:
            self._apply(None)
        return False

    def _apply(self, action) -> None:
        menu = self.parent()
        if not isinstance(menu, QMenu):
            return
        for item in menu.actions():
            widget = item.defaultWidget() if isinstance(item, QWidgetAction) else None
            if isinstance(widget, _BlockMenuRow):
                widget.set_hovered(item is action)


class _BlockMenuRow(QWidget):
    """One building-block row: colored syntax, then the name."""

    def __init__(
        self,
        action: QWidgetAction,
        *,
        code_html: str,
        name: str,
        code_width: int,
        code_font: str,
        code_size: int,
        name_font: str,
        name_size: int,
        text_color: tuple,
        hover_text_color: tuple,
        hover_background: tuple,
        padding: List[int],
        gap: int,
    ) -> None:
        super().__init__()
        self._action = action
        self._text_color = text_color
        self._hover_text_color = hover_text_color
        self._hover_background = hover_background
        self._name_font = name_font
        self._name_size = name_size
        self._hovered = False
        self.setObjectName("regexBlockRow")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoFillBackground(False)
        self.setMouseTracking(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(int(padding[3]), int(padding[0]), int(padding[1]), int(padding[2]))
        layout.setSpacing(gap)
        self._code = QLabel()
        self._code.setObjectName("regexBlockCode")
        self._code.setTextFormat(Qt.TextFormat.RichText)
        self._code.setText(code_html)
        self._code.setMinimumWidth(code_width)
        self._code.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._code.setStyleSheet(
            f"font-family: {_css_font(code_font)}; font-size: {code_size}pt; background: transparent;"
        )
        self._name = QLabel(name)
        self._name.setObjectName("regexBlockName")
        self._name.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._code)
        layout.addWidget(self._name)
        layout.addStretch(1)
        self._apply_name_color()

    def is_hovered(self) -> bool:
        return self._hovered

    def set_hovered(self, hover: bool) -> None:
        if hover == self._hovered:
            return
        self._hovered = hover
        self._apply_name_color()
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        menu = self._menu()
        if menu is not None:
            menu.setActiveAction(self._action)
        self.set_hovered(True)
        super().enterEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._action.trigger()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if not self._hovered:
            return
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(*self._hover_background))

    def _menu(self) -> Optional[QMenu]:
        parent = self.parent()
        while parent is not None and not isinstance(parent, QMenu):
            parent = parent.parent()
        return parent if isinstance(parent, QMenu) else None

    def _apply_name_color(self) -> None:
        name_color = self._hover_text_color if self._hovered else self._text_color
        self._name.setStyleSheet(
            f"font-family: {_css_font(self._name_font)}; font-size: {self._name_size}pt;"
            f" color: {_css_rgb(name_color)}; background: transparent;"
        )


class RegexEditorDialog(QDialog):
    """Test and build a regular expression, then return it on OK."""

    def __init__(
        self,
        config: Dict[str, Any],
        *,
        pattern: str,
        replacement: str,
        case_sensitive: bool,
        sample: str = "",
        show_replace: bool = True,
        settings: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._app_config = config
        dialogs = config.get("ui", {}).get("dialogs", {})
        section = dialogs.get("regex_editor", {})
        self._cfg = section if isinstance(section, dict) else {}
        self.controller = RegexEditorController(
            config,
            case_sensitive=case_sensitive,
            show_replace=show_replace,
            replacement=replacement,
            settings=settings,
        )
        self._replacement = replacement
        self.result: Optional[RegexEditorValues] = None
        self._pattern_focus_pending = True
        self._build(pattern, sample)

    def _build(self, pattern: str, sample: str) -> None:
        cfg = self._cfg
        self.setWindowTitle(str(cfg.get("title", "Edit regular expression")))
        self.setMinimumWidth(int(cfg.get("minimum_width", cfg.get("width", 680))))

        bg = _rgb(cfg.get("background_color"), (40, 40, 45))
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(*bg))
        self.setPalette(palette)

        layout_cfg = cfg.get("layout", {})
        margins = layout_cfg.get("margins", [24, 20, 24, 20])
        spacing = int(layout_cfg.get("spacing", 8))
        root = QVBoxLayout(self)
        root.setSpacing(spacing)
        root.setContentsMargins(int(margins[0]), int(margins[1]), int(margins[2]), int(margins[3]))

        pattern_row = QHBoxLayout()
        pattern_row.setSpacing(int(layout_cfg.get("spacing", 8)))
        self._blocks_button = self._build_library_button(
            str(cfg.get("blocks_label", "Building blocks")),
            "blocks_icon_svg",
            "app/resources/icons/regex.svg",
        )
        self._blocks_button.clicked.connect(self._on_blocks)
        pattern_row.addWidget(self._blocks_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self._examples_button = self._build_library_button(
            str(cfg.get("examples_button", "Example regular expressions")),
            "examples_icon_svg",
            "app/resources/icons/menu_book.svg",
        )
        self._examples_button.clicked.connect(self._on_examples)
        pattern_row.addWidget(self._examples_button, 0, Qt.AlignmentFlag.AlignVCenter)
        pattern_row.addStretch(1)
        separator, margin = self._library_separator()
        pattern_row.addSpacing(max(0, int(margin[0])))
        pattern_row.addWidget(separator, 0, Qt.AlignmentFlag.AlignVCenter)
        pattern_row.addSpacing(max(0, int(margin[2])))
        self._save_button = self._build_library_button(
            str(cfg.get("save_button", "Save this regular expression")),
            "save_icon_svg",
            "app/resources/icons/save_database.svg",
        )
        self._save_button.clicked.connect(self._on_save)
        self._load_button = self._build_library_button(
            str(cfg.get("load_button", "Load or remove a saved regular expression")),
            "load_icon_svg",
            "app/resources/icons/folder_open.svg",
        )
        self._load_button.clicked.connect(self._on_load)
        pattern_row.addWidget(self._save_button, 0, Qt.AlignmentFlag.AlignVCenter)
        pattern_row.addWidget(self._load_button, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(pattern_row)

        self.pattern_edit = self._make_editor(cfg.get("pattern", {}), placeholder=str(cfg.get("pattern_placeholder", "")))
        self._highlighter = RegexSyntaxHighlighter(
            self.pattern_edit.document(),
            self._syntax_colors(),
            self.controller.classify,
        )
        root.addWidget(self.pattern_edit)

        root.addWidget(self._label(str(cfg.get("explain_label", "Explanation"))))
        self._explain_scroll, self._explain_layout = self._build_explanation_panel()
        self._explained_pattern: Optional[str] = None
        root.addWidget(self._explain_scroll, 1)

        root.addWidget(self._label(str(cfg.get("sample_label", "Sample text"))))
        self.sample_edit = self._make_editor(
            cfg.get("sample", {}),
            placeholder=str(cfg.get("sample_placeholder", "")),
        )
        root.addWidget(self.sample_edit)

        root.addSpacing(int(cfg.get("bottom_button_top_padding", 12)))
        root.addLayout(self._build_buttons())

        self.pattern_edit.textChanged.connect(self._refresh)
        self.sample_edit.textChanged.connect(self._refresh)
        pattern, cursor = self.controller.starting_pattern(pattern)
        self.pattern_edit.setPlainText(pattern)
        if cursor is not None:
            placed = self.pattern_edit.textCursor()
            placed.setPosition(min(cursor, len(pattern)))
            self.pattern_edit.setTextCursor(placed)
        self.sample_edit.setPlainText(sample)
        self._refresh()
        self._pattern_focus_pending = True
        self._fit_to_contents()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # The native window has to exist before either editor joins Text Services.
        self.winId()
        if self._pattern_focus_pending and self.isActiveWindow():
            QTimer.singleShot(0, self._focus_pattern_field)

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if (
            event.type() == QEvent.Type.ActivationChange
            and self._pattern_focus_pending
            and self.isActiveWindow()
        ):
            QTimer.singleShot(0, self._focus_pattern_field)

    def _focus_pattern_field(self) -> None:
        if not self._pattern_focus_pending or not self.isVisible() or not self.isActiveWindow():
            return
        self._pattern_focus_pending = False
        for editor in (self.pattern_edit, self.sample_edit):
            editor.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, True)
            editor.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.pattern_edit.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

    def _fit_to_contents(self) -> None:
        """Open at the stacked height of the fields, and refuse to go shorter.

        The pattern and the sample stay at their configured heights. Extra
        window height goes to the explanation.
        """
        lay = self.layout()
        hint_h = lay.minimumSize().height() if lay is not None else self.minimumSizeHint().height()
        width = max(self.minimumWidth(), int(self._cfg.get("width", 720)))
        height = max(int(self._cfg.get("minimum_height", 0)), hint_h)
        self.setMinimumHeight(height)
        self.resize(width, height)

    def _on_blocks(self) -> None:
        menu = self._blocks_menu()
        menu.exec(self._blocks_button.mapToGlobal(self._blocks_button.rect().bottomLeft()))

    def _on_examples(self) -> None:
        menu = self._examples_menu()
        menu.exec(self._examples_button.mapToGlobal(self._examples_button.rect().bottomLeft()))

    def _examples_menu(self) -> QMenu:
        menu = QMenu(self._examples_button)
        StyleManager.style_context_menu(menu, self._app_config)
        current_group = None
        target = menu
        for example in self.controller.examples():
            if example.group != current_group:
                current_group = example.group
                if example.group:
                    target = menu.addMenu(example.group)
                    StyleManager.style_context_menu(target, self._app_config)
                else:
                    target = menu
            action = target.addAction(example.label)
            if example.tooltip:
                action.setToolTip(example.tooltip)
            action.triggered.connect(lambda _checked=False, item=example: self._apply_example(item))
        return menu

    def _apply_example(self, example: RegexExample) -> None:
        from app.views.dialogs.confirmation_dialog import ConfirmationDialog

        if self.controller.replaces_current_pattern(self.pattern_edit.toPlainText()):
            if not ConfirmationDialog.show_confirmation(
                self._app_config,
                str(self._cfg.get("examples_title", "Use example")),
                _named(str(self._cfg.get("examples_replace_message", "")), example.label),
                self,
            ):
                return
        self.pattern_edit.setPlainText(example.pattern)
        if example.sample:
            self.sample_edit.setPlainText(example.sample)
        placed = self.pattern_edit.textCursor()
        if example.select_text and example.select_text in example.pattern:
            start = example.pattern.index(example.select_text)
            placed.setPosition(start)
            placed.setPosition(start + len(example.select_text), QTextCursor.MoveMode.KeepAnchor)
        else:
            placed.setPosition(len(example.pattern))
        self.pattern_edit.setTextCursor(placed)
        self.pattern_edit.setFocus()

    def _library_separator(self) -> tuple:
        style = self._cfg.get("library_buttons", {})
        if not isinstance(style, dict):
            style = {}
        buttons_cfg = self._cfg.get("buttons", {})
        width = max(1, int(style.get("separator_width", 1)))
        margin = style.get("separator_margin", [6, 4, 6, 4])
        if not isinstance(margin, list) or len(margin) < 4:
            margin = [6, 4, 6, 4]
        size = int(style.get("size", buttons_cfg.get("height", 30)))
        sep = QFrame()
        sep.setObjectName("regexLibrarySeparator")
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedWidth(width)
        sep.setFixedHeight(max(8, size - int(margin[1]) - int(margin[3])))
        border = _rgb(buttons_cfg.get("border_color", self._cfg.get("border_color")), (60, 60, 65))
        sep.setStyleSheet(
            "QFrame#regexLibrarySeparator {"
            f" background-color: {_css_rgb(border)}; border: 0px; padding: 0px; margin: 0px;"
            "}"
        )
        return sep, margin

    def _build_library_button(self, tooltip: str, icon_key: str, fallback_svg: str) -> QPushButton:
        """Square icon button, matching the bulk-operations plan toolbar."""
        style = self._cfg.get("library_buttons", {})
        if not isinstance(style, dict):
            style = {}
        buttons_cfg = self._cfg.get("buttons", {})
        size = int(style.get("size", buttons_cfg.get("height", 30)))
        icon_px = int(style.get("icon_px", 18))
        tint = style.get("icon_tint", [200, 200, 200])
        if not isinstance(tint, (list, tuple)) or len(tint) < 3:
            tint = [200, 200, 200]
        icon_svg = str(style.get(icon_key) or fallback_svg)
        button = QPushButton()
        button.setAutoDefault(False)
        button.setDefault(False)
        button.setText("")
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIcon(themed_icon_from_svg(icon_svg, tint))
        button.setIconSize(QSize(icon_px, icon_px))
        bg = _rgb(self._cfg.get("background_color"), (40, 40, 45))
        border = _rgb(buttons_cfg.get("border_color", self._cfg.get("border_color")), (60, 60, 65))
        StyleManager.style_buttons(
            [button],
            self._app_config,
            [bg[0], bg[1], bg[2]],
            [border[0], border[1], border[2]],
            min_width=None,
            min_height=size,
        )
        button.setFixedSize(size, size)
        return button

    def _blocks_menu(self) -> QMenu:
        menu = QMenu(self)
        self._fill_block_menu(menu, self.controller.block_groups())
        return menu

    def _fill_block_menu(self, menu: QMenu, groups: List[RegexBlockGroup]) -> None:
        StyleManager.style_context_menu(menu, self._app_config)
        for group in groups:
            if group.groups or group.blocks:
                category = menu.addMenu(group.label)
                self._fill_block_category(category, group)

    def _fill_block_category(self, menu: QMenu, group: RegexBlockGroup) -> None:
        StyleManager.style_context_menu(menu, self._app_config)
        _BlockMenuHover(menu)
        code_font, code_size = self._block_code_font()
        metrics = QFontMetrics(QFont(code_font, code_size))
        code_width = max((metrics.horizontalAdvance(block.insert) for block in group.blocks), default=0)
        for block in group.blocks:
            action = QWidgetAction(menu)
            action.setText(block.label)
            if block.tooltip:
                action.setToolTip(block.tooltip)
            action.triggered.connect(lambda _checked=False, item=block: self._insert_block(item))
            row = _BlockMenuRow(
                action,
                code_html=self._colored_snippet(block.insert),
                name=block.label,
                code_width=code_width,
                code_font=code_font,
                code_size=code_size,
                name_font=self._menu_font_family(),
                name_size=self._menu_font_size(),
                text_color=self._menu_color("text_color", (200, 200, 200)),
                hover_text_color=self._menu_color("hover_text_color", (230, 230, 230)),
                hover_background=self._menu_color("hover_background_color", (55, 55, 60)),
                padding=self._menu_padding(),
                gap=self._block_code_gap(),
            )
            action.setDefaultWidget(row)
            menu.addAction(action)
        for child in group.groups:
            nested = menu.addMenu(child.label)
            self._fill_block_category(nested, child)

    def _colored_snippet(self, snippet: str) -> str:
        colors = self._syntax_colors()
        parts: List[str] = []
        for start, end, kind in self.controller.classify(snippet):
            token = escape(snippet[start:end]).replace(" ", "&nbsp;")
            color = colors.get(kind)
            if color is None:
                parts.append(token)
            else:
                parts.append(
                    f'<span style="color: rgb({color.red()}, {color.green()}, {color.blue()});">{token}</span>'
                )
        return "".join(parts)

    def _block_code_font(self) -> tuple:
        style = self._cfg.get("explain_style", {})
        if not isinstance(style, dict):
            style = {}
        family = resolve_font_family(str(style.get("token_font_family", "monospace")))
        size = scale_font_size(style.get("token_font_size", 12))
        return family, int(size)

    def _block_code_gap(self) -> int:
        menu = self._cfg.get("blocks_menu", {})
        if not isinstance(menu, dict):
            return 14
        return max(0, int(menu.get("code_gap", 14)))

    def _menu_style(self) -> Dict[str, Any]:
        styles = self._app_config.get("ui", {}).get("styles", {})
        menu = styles.get("context_menu", {}) if isinstance(styles, dict) else {}
        return menu if isinstance(menu, dict) else {}

    def _menu_font_family(self) -> str:
        return resolve_font_family(str(self._menu_style().get("font_family", "")))

    def _menu_font_size(self) -> int:
        return int(scale_font_size(self._menu_style().get("font_size", 11)))

    def _menu_color(self, key: str, fallback: tuple) -> tuple:
        return _rgb(self._menu_style().get(key), fallback)

    def _menu_padding(self) -> List[int]:
        padding = self._menu_style().get("item_padding", [4, 20, 4, 14])
        if not isinstance(padding, list) or len(padding) < 4:
            return [4, 20, 4, 14]
        return [int(padding[0]), int(padding[1]), int(padding[2]), int(padding[3])]

    def _build_buttons(self) -> QHBoxLayout:
        cfg = self._cfg
        buttons_cfg = cfg.get("buttons", {})
        row = QHBoxLayout()
        row.setSpacing(int(buttons_cfg.get("spacing", 10)))
        row.addStretch(1)
        cancel = QPushButton(str(cfg.get("cancel_button", "Cancel")))
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        self._ok_button = QPushButton(str(cfg.get("ok_button", "OK")))
        self._ok_button.setDefault(True)
        self._ok_button.clicked.connect(self._on_ok)
        row.addWidget(cancel)
        row.addWidget(self._ok_button)
        bg = _rgb(cfg.get("background_color"), (40, 40, 45))
        border = _rgb(buttons_cfg.get("border_color", cfg.get("border_color")), (60, 60, 65))
        StyleManager.style_buttons(
            [cancel, self._ok_button],
            self._app_config,
            [bg[0], bg[1], bg[2]],
            [border[0], border[1], border[2]],
            min_width=int(buttons_cfg.get("width", 120)),
            min_height=int(buttons_cfg.get("height", 30)),
        )
        return row

    def _on_save(self) -> None:
        from app.views.dialogs.confirmation_dialog import ConfirmationDialog
        from app.views.dialogs.input_dialog import InputDialog
        from app.views.dialogs.message_dialog import MessageDialog

        pattern = self.pattern_edit.toPlainText()
        if not self.controller.pattern_can_be_saved(pattern):
            return
        cfg = self._cfg
        name, accepted = InputDialog.get_text(
            self._app_config,
            str(cfg.get("save_title", "Save regular expression")),
            str(cfg.get("save_prompt", "Name:")),
            "",
            self,
        )
        if not accepted:
            return
        name = self.controller.normalize_name(name)
        if not name:
            MessageDialog.show_warning(
                self._app_config,
                str(cfg.get("save_title", "Save regular expression")),
                str(cfg.get("save_name_required", "Enter a name.")),
                self,
            )
            return
        if self.controller.library_has(name):
            if not ConfirmationDialog.show_confirmation(
                self._app_config,
                str(cfg.get("overwrite_title", "Overwrite regular expression")),
                _named(str(cfg.get("overwrite_message", "")), name),
                self,
            ):
                return
        self.controller.store_pattern(name, pattern)

    def _on_load(self) -> None:
        menu = self._library_menu()
        menu.exec(self._load_button.mapToGlobal(self._load_button.rect().bottomLeft()))

    def _library_menu(self) -> QMenu:
        menu = QMenu(self._load_button)
        StyleManager.style_context_menu(menu, self._app_config)
        names = self.controller.saved_names()
        if not names:
            empty = menu.addAction(str(self._cfg.get("load_empty", "No saved regular expressions")))
            empty.setEnabled(False)
            return menu
        for name in names:
            action = menu.addAction(name)
            action.triggered.connect(lambda _checked=False, item=name: self._load_named(item))
        menu.addSeparator()
        remove_menu = menu.addMenu(str(self._cfg.get("remove_menu", "Remove…")))
        StyleManager.style_context_menu(remove_menu, self._app_config)
        for name in names:
            action = remove_menu.addAction(name)
            action.triggered.connect(lambda _checked=False, item=name: self._remove_named(item))
        return menu

    def _load_named(self, name: str) -> None:
        from app.views.dialogs.confirmation_dialog import ConfirmationDialog
        from app.views.dialogs.message_dialog import MessageDialog

        pattern = self.controller.saved_pattern(name)
        if pattern is None:
            MessageDialog.show_warning(
                self._app_config,
                str(self._cfg.get("load_title", "Load regular expression")),
                _named(str(self._cfg.get("load_missing", "")), name),
                self,
            )
            return
        if self.controller.replaces_current_pattern(self.pattern_edit.toPlainText()):
            if not ConfirmationDialog.show_confirmation(
                self._app_config,
                str(self._cfg.get("load_title", "Load regular expression")),
                _named(str(self._cfg.get("load_replace_message", "")), name),
                self,
            ):
                return
        self.pattern_edit.setPlainText(pattern)
        placed = self.pattern_edit.textCursor()
        placed.setPosition(len(pattern))
        self.pattern_edit.setTextCursor(placed)
        self.pattern_edit.setFocus()

    def _remove_named(self, name: str) -> None:
        from app.views.dialogs.confirmation_dialog import ConfirmationDialog

        if not ConfirmationDialog.show_confirmation(
            self._app_config,
            str(self._cfg.get("remove_title", "Remove regular expression")),
            _named(str(self._cfg.get("remove_message", "")), name),
            self,
        ):
            return
        self.controller.remove_pattern(name)

    def _insert_block(self, block: RegexBlock) -> None:
        cursor = self.pattern_edit.textCursor()
        updated, sel_start, sel_end = self.controller.insert_block(
            self.pattern_edit.toPlainText(),
            cursor.selectionStart(),
            cursor.selectionEnd(),
            block,
        )
        self.pattern_edit.setPlainText(updated)
        placed = self.pattern_edit.textCursor()
        placed.setPosition(sel_start)
        placed.setPosition(sel_end, QTextCursor.MoveMode.KeepAnchor)
        self.pattern_edit.setTextCursor(placed)
        self.pattern_edit.setFocus()

    def _refresh(self) -> None:
        pattern = self.pattern_edit.toPlainText()
        sample = self.sample_edit.toPlainText()
        preview = self.controller.preview(pattern, self._replacement, sample)
        self._ok_button.setEnabled(preview.valid)
        self._save_button.setEnabled(preview.valid)
        self._apply_match_highlights(preview.spans)
        if pattern != self._explained_pattern:
            self._explained_pattern = pattern
            self._render_explanation(self.controller.explain(pattern))

    def _build_explanation_panel(self) -> tuple:
        style = self._cfg.get("explain_style", {})
        if not isinstance(style, dict):
            style = {}
        panel_height = int(style.get("min_height", 160))
        bg = _rgb(style.get("background_color"), (32, 32, 36))
        border = _rgb(style.get("border_color"), (70, 70, 78))
        radius = int(style.get("border_radius", 4))
        width = int(style.get("border_width", 1))
        # Border lives on a frame. A stylesheet on the scroll area itself stops
        # Qt from clipping the explanation, which then paints over the fields below.
        frame = QFrame()
        frame.setObjectName("regexExplainPanel")
        frame.setMinimumHeight(panel_height)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        frame.setStyleSheet(
            "QFrame#regexExplainPanel {"
            f" background-color: {_css_rgb(bg)};"
            f" border: {width}px solid {_css_rgb(border)};"
            f" border-radius: {radius}px;"
            "}"
        )
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("regexExplainScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # The frame owns the border. Scrollbar rules are still required here:
        # without an explicit width, the native groove is wider than the themed
        # bar and the bar sits inset from the section edge. A border or radius
        # on this scroll area stops Qt from clipping the explanation.
        scroll.setStyleSheet(
            "QScrollArea#regexExplainScroll { border: none; background: transparent; padding: 0px; }"
            + generate_scrollbar_stylesheet(
                self._app_config,
                [bg[0], bg[1], bg[2]],
                [border[0], border[1], border[2]],
                widget_selector="QScrollArea#regexExplainScroll QScrollBar",
            )
        )
        StyleManager.install_grab_friendly_scrollbars(scroll, self._app_config)
        viewport = scroll.viewport()
        viewport.setAutoFillBackground(True)
        viewport_palette = viewport.palette()
        viewport_palette.setColor(viewport.backgroundRole(), QColor(*bg))
        viewport.setPalette(viewport_palette)
        host = QWidget()
        host.setStyleSheet(f"background-color: {_css_rgb(bg)};")
        host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(host)
        pad = int(style.get("padding", 8))
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(int(style.get("spacing", 4)))
        scroll.setWidget(host)
        frame_layout.addWidget(scroll, 1)
        return frame, layout

    def _render_explanation(self, nodes: List[RegexExplanation]) -> None:
        while self._explain_layout.count():
            item = self._explain_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not nodes:
            note = QLabel(str(self._cfg.get("explain_placeholder", "")))
            note.setWordWrap(True)
            self._style_status(note, error=False)
            self._explain_layout.addWidget(note)
        else:
            for node in nodes:
                self._explain_layout.addWidget(self._explanation_node(node))
        self._explain_layout.addStretch(1)

    def _explanation_node(self, node: RegexExplanation) -> QFrame:
        style = self._cfg.get("explain_style", {})
        kinds = style.get("kinds", {}) if isinstance(style, dict) else {}
        kind_style = kinds.get(node.kind, kinds.get("literal", {}))
        if not isinstance(kind_style, dict):
            kind_style = {}
        frame = QFrame()
        frame.setObjectName("regexExplainNode")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        bg = _rgb(kind_style.get("background_color"), (40, 40, 44))
        border = _rgb(kind_style.get("border_color"), (90, 90, 98))
        radius = int(style.get("border_radius", 4)) if isinstance(style, dict) else 4
        width = int(style.get("border_width", 1)) if isinstance(style, dict) else 1
        frame.setStyleSheet(
            "QFrame#regexExplainNode {"
            f" background-color: {_css_rgb(bg)};"
            f" border: {width}px solid {_css_rgb(border)};"
            f" border-radius: {radius}px;"
            "}"
        )
        layout = QVBoxLayout(frame)
        pad = int(style.get("padding", 8)) if isinstance(style, dict) else 8
        spacing = int(style.get("spacing", 4)) if isinstance(style, dict) else 4
        layout.setContentsMargins(pad, pad, pad, pad)
        layout.setSpacing(spacing)
        layout.addLayout(self._explanation_row(node.token, node.text, kind_style))
        if node.children:
            child_host = QWidget()
            child_host.setStyleSheet("background: transparent; border: none;")
            child_layout = QVBoxLayout(child_host)
            indent = int(style.get("indent", 12)) if isinstance(style, dict) else 12
            child_layout.setContentsMargins(indent, 0, 0, 0)
            child_layout.setSpacing(spacing)
            for child in node.children:
                child_layout.addWidget(self._explanation_node(child))
            layout.addWidget(child_host)
        if node.closing_token:
            layout.addLayout(self._explanation_row(node.closing_token, "", kind_style))
        return frame

    def _explanation_row(self, token: str, text: str, kind_style: Dict[str, Any]) -> QHBoxLayout:
        style = self._cfg.get("explain_style", {})
        if not isinstance(style, dict):
            style = {}
        labels = self._cfg.get("labels", {})
        token_family = resolve_font_family(str(style.get("token_font_family", "monospace")))
        text_family = resolve_font_family(
            str(style.get("text_font_family", labels.get("font_family", "")))
        )
        token_size = scale_font_size(style.get("token_font_size", 12))
        text_size = scale_font_size(style.get("text_font_size", 11))
        token_color = _rgb(kind_style.get("token_color"), (230, 230, 230))
        text_color = _rgb(kind_style.get("text_color"), (210, 210, 210))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        token_label = QLabel(token)
        token_label.setStyleSheet(
            f"font-family: {_css_font(token_family)}; font-size: {token_size}pt; font-weight: 700;"
            f" color: {_css_rgb(token_color)}; background: transparent; border: none;"
        )
        token_label.setMinimumWidth(int(style.get("token_min_width", 28)))
        token_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        row.addWidget(token_label, 0, Qt.AlignmentFlag.AlignTop)
        if text:
            text_label = QLabel(text)
            text_label.setWordWrap(True)
            text_label.setMinimumWidth(0)
            text_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            text_label.setStyleSheet(
                f"font-family: {_css_font(text_family)}; font-size: {text_size}pt;"
                f" color: {_css_rgb(text_color)}; background: transparent; border: none;"
            )
            row.addWidget(text_label, 1)
        else:
            row.addStretch(1)
        return row

    def _apply_match_highlights(self, spans) -> None:
        sample_cfg = self._cfg.get("sample", {})
        bg = QColor(*_rgb(sample_cfg.get("match_background_color"), (48, 96, 68)))
        fg = QColor(*_rgb(sample_cfg.get("match_text_color"), (232, 244, 232)))
        selections = []
        document = self.sample_edit.document()
        for start, end in spans:
            selection = QTextEdit.ExtraSelection()
            cursor = QTextCursor(document)
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            fmt = QTextCharFormat()
            fmt.setBackground(bg)
            fmt.setForeground(fg)
            selection.cursor = cursor
            selection.format = fmt
            selections.append(selection)
        self.sample_edit.setExtraSelections(selections)

    def _on_ok(self) -> None:
        values = self.controller.accepted_values(
            self.pattern_edit.toPlainText(),
            self._replacement,
            self.sample_edit.toPlainText(),
        )
        if values is None:
            return
        self.result = values
        self.accept()

    def _syntax_colors(self) -> Dict[str, QColor]:
        """Foreground colors for the pattern, taken from the explanation token colors."""
        return regex_token_colors(self._app_config)

    def _label(self, text: str) -> QLabel:
        labels = self._cfg.get("labels", {})
        color = _rgb(labels.get("text_color", self._cfg.get("text_color")), (200, 200, 200))
        size = scale_font_size(labels.get("font_size", 11))
        family = resolve_font_family(str(labels.get("font_family", self._cfg.get("font_family", ""))))
        label = QLabel(text)
        label.setStyleSheet(
            f"font-family: {_css_font(family)}; font-size: {size}pt;"
            f" color: {_css_rgb(color)}; background: transparent;"
        )
        return label

    def _style_status(self, label: QLabel, *, error: bool) -> None:
        status = self._cfg.get("status", {})
        labels = self._cfg.get("labels", {})
        color = _rgb(
            status.get("error_color") if error else status.get("note_color"),
            (210, 90, 90) if error else (160, 160, 160),
        )
        size = scale_font_size(status.get("font_size", labels.get("font_size", 11)))
        family = resolve_font_family(str(labels.get("font_family", "")))
        label.setStyleSheet(
            f"font-family: {_css_font(family)}; font-size: {size}pt;"
            f" color: {_css_rgb(color)}; background: transparent;"
        )

    def _make_editor(
        self,
        field_cfg: Dict[str, Any],
        *,
        placeholder: str = "",
        min_height: Optional[int] = None,
        read_only: bool = False,
        expand: bool = False,
    ) -> QPlainTextEdit:
        editor = QPlainTextEdit()
        editor.setPlaceholderText(placeholder)
        editor.setReadOnly(read_only)
        height = int(min_height if min_height is not None else field_cfg.get("min_height", 48))
        if expand:
            editor.setMinimumHeight(height)
            editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            editor.setFixedHeight(height)
            editor.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        editor.document().setDocumentMargin(2)
        editor.setStyleSheet(self._editor_stylesheet(field_cfg))
        # A plain-text editor registers with macOS Text Services as soon as it
        # is shown. That registration fails (TSMSendMessageToUIServer) until
        # the dialog window is key, so keep input methods off until then.
        editor.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        editor.setAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled, False)
        return editor

    def _editor_stylesheet(self, field_cfg: Dict[str, Any]) -> str:
        family = resolve_font_family(
            str(field_cfg.get("font_family", self._cfg.get("pattern", {}).get("font_family", "monospace")))
        )
        size = scale_font_size(field_cfg.get("font_size", self._cfg.get("pattern", {}).get("font_size", 12)))
        bg = _rgb(field_cfg.get("background_color"), (30, 30, 35))
        fg = _rgb(field_cfg.get("text_color"), (230, 230, 230))
        border = _rgb(field_cfg.get("border_color", self._cfg.get("border_color")), (70, 70, 75))
        focus = _rgb(field_cfg.get("focus_border_color", border), border)
        radius = int(field_cfg.get("border_radius", 3))
        width = int(self._cfg.get("border_width", 1))
        pad = field_cfg.get("padding", [8, 6])
        pad_h = int(pad[0]) if isinstance(pad, list) and pad else 8
        pad_v = int(pad[1]) if isinstance(pad, list) and len(pad) > 1 else 6
        sel_bg = _rgb(field_cfg.get("selection_background_color"), (70, 90, 130))
        sel_fg = _rgb(field_cfg.get("selection_text_color"), (240, 240, 240))
        return (
            "QPlainTextEdit {"
            f" font-family: {_css_font(family)}; font-size: {size}pt;"
            f" background-color: {_css_rgb(bg)}; color: {_css_rgb(fg)};"
            f" border: {width}px solid {_css_rgb(border)}; border-radius: {radius}px;"
            f" padding: {pad_v}px {pad_h}px;"
            f" selection-background-color: {_css_rgb(sel_bg)}; selection-color: {_css_rgb(sel_fg)};"
            "}"
            f"QPlainTextEdit:focus {{ border: {width}px solid {_css_rgb(focus)}; }}"
        )


def edit_regex(
    config: Dict[str, Any],
    *,
    pattern: str,
    replacement: str = "",
    case_sensitive: bool = False,
    sample: str = "",
    show_replace: bool = True,
    parent: Optional[QWidget] = None,
) -> Optional[RegexEditorValues]:
    """Open the editor. Returns ``None`` when the user cancels."""
    dialog = RegexEditorDialog(
        config,
        pattern=pattern,
        replacement=replacement,
        case_sensitive=case_sensitive,
        sample=sample,
        show_replace=show_replace,
        parent=parent,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted or dialog.result is None:
        return None
    return dialog.result


def _named(template: str, name: str) -> str:
    safe = name.replace("{", "{{").replace("}", "}}")
    return template.format(name=safe)


def _rgb(value: Any, fallback):
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (int(value[0]), int(value[1]), int(value[2]))
    return fallback


def _css_rgb(color: tuple) -> str:
    return f"rgb({color[0]}, {color[1]}, {color[2]})"


def _css_font(family: str) -> str:
    if not family:
        return "sans-serif"
    if any(ch in family for ch in " \"'"):
        return f"'{family}'"
    return family
