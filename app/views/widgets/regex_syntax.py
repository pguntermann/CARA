"""Regex token colors shared by the editor and the bulk Find field."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from PyQt6.QtCore import QEvent, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFontMetrics,
    QKeyEvent,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import QFrame, QPlainTextEdit, QSizePolicy, QToolButton, QVBoxLayout, QWidget


class RegexSyntaxHighlighter(QSyntaxHighlighter):
    """Paints token spans from the regex editor classifier."""

    def __init__(self, document, colors: Dict[str, QColor], classify: Callable[[str], List[Tuple[int, int, str]]]) -> None:
        super().__init__(document)
        self._classify = classify
        self._formats: Dict[str, QTextCharFormat] = {}
        for kind, color in colors.items():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self._formats[kind] = fmt

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for start, end, kind in self._classify(text):
            fmt = self._formats.get(kind)
            if fmt is not None and end > start:
                self.setFormat(start, end - start, fmt)


def regex_token_colors(config: Dict[str, Any]) -> Dict[str, QColor]:
    """Foreground colors for a pattern, taken from the explanation token colors."""
    section = config.get("ui", {}).get("dialogs", {}).get("regex_editor", {})
    if not isinstance(section, dict):
        return {}
    kinds = section.get("explain_style", {}).get("kinds", {})
    if not isinstance(kinds, dict):
        return {}
    colors: Dict[str, QColor] = {}
    for kind, style in kinds.items():
        if not isinstance(style, dict):
            continue
        rgb = style.get("token_color")
        if isinstance(rgb, (list, tuple)) and len(rgb) >= 3:
            colors[str(kind)] = QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))
    return colors


class RegexPatternLine(QWidget):
    """Single-line pattern field. Token colors turn on with the regex option."""

    textEdited = pyqtSignal(str)
    returnPressed = pyqtSignal()

    def __init__(
        self,
        colors: Dict[str, QColor],
        classify: Callable[[str], List[Tuple[int, int, str]]],
        parent: QWidget | None = None,
        *,
        object_name: str = "bulkFindPattern",
    ) -> None:
        super().__init__(parent)
        self._pad_h = 8
        self._border = 1
        self._highlighting = False
        self._setting = False
        self._action = None
        self._icon_px = 16
        # Chrome (border/background) is painted on this wrapper. A frameless
        # QPlainTextEdit often drops QSS borders, which made Find look unstyled
        # on light/scholar panels that share the field background color.
        self.setObjectName(f"{object_name}Wrap")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("focused", False)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._edit = QPlainTextEdit(self)
        self._edit.setObjectName(object_name)
        self._edit.setFrameShape(QFrame.Shape.NoFrame)
        self._edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._edit.setTabChangesFocus(True)
        self._edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._edit.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._edit.document().setDocumentMargin(0)
        self._edit.installEventFilter(self)
        self._edit.textChanged.connect(self._on_text_changed)
        self._highlighter = RegexSyntaxHighlighter(None, colors, classify)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._edit)
        self._button = QToolButton(self)
        self._button.setObjectName("bulkFindRegexButton")
        self._button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._button.setAutoRaise(True)
        self._button.setStyleSheet(
            "QToolButton#bulkFindRegexButton { border: none; background: transparent; padding: 0px; }"
        )
        self._button.hide()
        self._button.clicked.connect(self._trigger_action)
        self.setFocusProxy(self._edit)

    def set_editor_action(self, action, icon_px: int = 16) -> None:
        self._action = action
        self._icon_px = max(1, int(icon_px))
        action.changed.connect(self._sync_action)
        self._sync_action()

    def token_color_at(self, index: int) -> QColor | None:
        """Syntax color at a character, when highlighting is on."""
        layout = self._edit.document().firstBlock().layout()
        if layout is None:
            return None
        for item in layout.formats():
            if item.start <= index < item.start + item.length:
                return item.format.foreground().color()
        return None

    def set_line_style(self, stylesheet: str, font) -> None:
        """Apply line-edit QSS: box on the wrapper, text surface on the editor."""
        self._edit.setFont(font)
        edit_id = self._edit.objectName()
        wrap_id = self.objectName()
        edit_sel = f"QPlainTextEdit#{edit_id}"
        wrap_sel = f"QWidget#{wrap_id}"
        chrome = stylesheet.replace(edit_sel, wrap_sel).replace(
            f"{wrap_sel}:focus", f'{wrap_sel}[focused="true"]'
        )
        # Keep typography/colors on the editor; suppress its own box so the
        # wrapper border is the only chrome (avoids double borders).
        edit_sheet = (
            f"{stylesheet}"
            f"{edit_sel} {{"
            f"background-color: transparent;"
            f"border: none;"
            f"padding: 0px;"
            f"margin: 0px;"
            f"}}"
        )
        self.setStyleSheet(chrome)
        self._edit.setStyleSheet(edit_sheet)

    def set_line_metrics(self, *, pad_h: int, border_width: int) -> None:
        self._pad_h = max(0, int(pad_h))
        self._border = max(0, int(border_width))
        self._place_chrome()

    def set_highlighting(self, enabled: bool) -> None:
        if enabled == self._highlighting:
            return
        self._highlighting = enabled
        self._setting = True
        try:
            if enabled:
                self._highlighter.setDocument(self._edit.document())
                self._highlighter.rehighlight()
            else:
                self._highlighter.setDocument(None)
                cursor = QTextCursor(self._edit.document())
                cursor.select(QTextCursor.SelectionType.Document)
                cursor.setCharFormat(QTextCharFormat())
        finally:
            self._setting = False

    def text(self) -> str:
        return self._edit.toPlainText()

    def setText(self, text: str) -> None:  # noqa: N802
        self._setting = True
        try:
            self._edit.setPlainText(text.replace("\n", ""))
        finally:
            self._setting = False

    def setPlaceholderText(self, text: str) -> None:  # noqa: N802
        self._edit.setPlaceholderText(text)

    def setSelection(self, start: int, length: int) -> None:  # noqa: N802
        cursor = self._edit.textCursor()
        cursor.setPosition(max(0, start))
        cursor.setPosition(max(0, start) + max(0, length), QTextCursor.MoveMode.KeepAnchor)
        self._edit.setTextCursor(cursor)

    def clear(self) -> None:
        self.setText("")

    def textCursor(self) -> QTextCursor:  # noqa: N802
        return self._edit.textCursor()

    def sizeHint(self) -> QSize:  # noqa: N802
        metrics = QFontMetrics(self._edit.font())
        return QSize(160, max(24, metrics.height() + 10))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(80, self.sizeHint().height())

    def setFocus(self, reason: Qt.FocusReason = Qt.FocusReason.OtherFocusReason) -> None:  # noqa: N802
        self._edit.setFocus(reason)

    def clearFocus(self) -> None:  # noqa: N802
        self._edit.clearFocus()
        super().clearFocus()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._edit:
            etype = event.type()
            if etype == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
                if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self.returnPressed.emit()
                    return True
            if etype == QEvent.Type.FocusIn:
                self._set_focused(True)
            elif etype == QEvent.Type.FocusOut:
                self._set_focused(False)
        return super().eventFilter(obj, event)

    def _set_focused(self, focused: bool) -> None:
        if bool(self.property("focused")) == focused:
            return
        self.setProperty("focused", focused)
        style = self.style()
        if style is not None:
            style.unpolish(self)
            style.polish(self)
        self.update()


    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._place_chrome()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._place_chrome()

    def _trigger_action(self) -> None:
        if self._action is not None:
            self._action.trigger()

    def _sync_action(self) -> None:
        action = self._action
        if action is None:
            return
        self._button.setIcon(action.icon())
        self._button.setIconSize(QSize(self._icon_px, self._icon_px))
        self._button.setToolTip(action.toolTip())
        self._button.setVisible(action.isVisible())
        self._button.setFixedSize(self._icon_px + 8, self._icon_px + 8)
        self._place_chrome()

    def _place_chrome(self) -> None:
        metrics = QFontMetrics(self._edit.font())
        inner = max(0, self._edit.height() - (self._border * 2))
        extra = max(0, inner - metrics.height())
        top = extra // 2
        bottom = extra - top
        right = self._pad_h
        if not self._button.isHidden():
            self._button.raise_()
            x = self.width() - self._button.width() - 3
            y = max(0, (self.height() - self._button.height()) // 2)
            self._button.move(x, y)
            right = self._button.width() + 6
        self._edit.setViewportMargins(self._pad_h, top, right, bottom)

    def _on_text_changed(self) -> None:
        if self._setting:
            return
        text = self._edit.toPlainText()
        if "\n" in text:
            self.setText(text.replace("\n", ""))
            text = self.text()
        self.textEdited.emit(text)
