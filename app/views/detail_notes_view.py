"""Notes view for detail panel: plain-text game notes with move linking."""

from typing import Dict, Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QMenu, QApplication,
    QPushButton, QFrame, QGraphicsOpacityEffect,
)
from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QKeySequence,
    QShortcut,
    QMouseEvent,
    QContextMenuEvent,
    QAction,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve

from app.utils.font_utils import resolve_font_family, scale_font_size
from app.views.style.style_manager import StyleManager

if __name__ != "__main__":
    from app.models.game_model import GameModel
    from app.controllers.notes_controller import NotesController


class NotesTextEdit(QTextEdit):
    """QTextEdit that handles move-link clicks for navigation."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._link_click_handler = None

    def set_link_click_handler(self, handler) -> None:
        self._link_click_handler = handler

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._link_click_handler:
            pos = event.position().toPoint()
            cursor = self.cursorForPosition(pos)
            fmt = cursor.charFormat()
            href = fmt.anchorHref()
            if href and href.startswith("move:"):
                notation = href.split("move:", 1)[1]
                if notation and self._link_click_handler(notation):
                    event.accept()
                    return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Standard editor menu, then Notes menubar actions; styled like other context menus."""
        menu = self.createStandardContextMenu()
        parent_view = self.parent()
        cfg = getattr(parent_view, "config", None) if parent_view else None
        if isinstance(cfg, dict):
            from app.views.style.context_menu import apply_dark_standard_textedit_context_menu_icons

            StyleManager.style_context_menu(menu, cfg)
            apply_dark_standard_textedit_context_menu_icons(menu, cfg)

        from PyQt6.QtWidgets import QApplication

        from app.views.menus.notes_context_menu import append_notes_menu_items_to_context_menu

        mw = QApplication.activeWindow()
        if mw is not None and isinstance(cfg, dict):
            menu.addSeparator()
            append_notes_menu_items_to_context_menu(menu, mw)

        from app.views.style.context_menu import try_wire_context_menu_shared_action_icons

        try_wire_context_menu_shared_action_icons(menu)
        menu.exec(event.globalPos())


class DetailNotesView(QWidget):
    """Detail view: scrollable notes with monospace font and move linking."""

    def __init__(
        self,
        config: Dict[str, Any],
        game_model: Optional["GameModel"] = None,
        notes_controller: Optional["NotesController"] = None,
    ) -> None:
        super().__init__()
        self.config = config
        self._game_model = game_model
        self._notes_controller = notes_controller
        self._current_plain: str = ""
        self._updating_links = False
        self._format_toolbar_buttons: Dict[str, QPushButton] = {}
        self._link_debounce_timer = QTimer(self)
        self._link_debounce_timer.setSingleShot(True)
        self._link_debounce_timer.timeout.connect(self._reapply_move_links)
        self._toolbar_widget: Optional[QWidget] = None
        self._toolbar_required_width: int = 0
        self._toolbar_collapsed: bool = False
        self._toolbar_opacity_effect: Optional[QGraphicsOpacityEffect] = None
        self._toolbar_opacity_animation: Optional[QPropertyAnimation] = None
        self._setup_ui()
        if game_model:
            game_model.active_game_changed.connect(self._on_active_game_changed)
        if notes_controller:
            self._notes_edit.set_link_click_handler(self._on_move_link_clicked)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        ui_config = self.config.get("ui", {})
        panel_config = ui_config.get("panels", {}).get("detail", {})
        notes_config = panel_config.get("notes", {})
        pgn_config = panel_config.get("pgn_notation", {})

        font_family = resolve_font_family(notes_config.get("font_family", pgn_config.get("font_family", "Courier New")))
        font_size = int(scale_font_size(notes_config.get("font_size", pgn_config.get("font_size", 11))))
        self._notes_edit = NotesTextEdit(self)
        self._notes_edit.setFont(QFont(font_family, font_size))
        self._notes_edit.setAcceptRichText(True)

        tabs_config = panel_config.get("tabs", {})
        pane_bg = tabs_config.get("pane_background", [30, 30, 35])
        notes_text_color = notes_config.get("text_color", [220, 220, 220])
        self._blockquote_text_color = notes_config.get("blockquote_text_color", [210, 190, 130])
        self._hidden_marker_font_point_size = notes_config.get(
            "hidden_marker_font_point_size", 0.5
        )
        self._toolbar_separator_color = notes_config.get(
            "toolbar_separator_color", [60, 60, 65]
        )
        self._inline_code_background_color = notes_config.get(
            "inline_code_background_color", [90, 110, 160]
        )
        self._inline_code_background_alpha = notes_config.get(
            "inline_code_background_alpha", 170
        )
        self._inline_code_text_color = notes_config.get(
            "inline_code_text_color", [255, 255, 255]
        )
        self._move_link_text_color = notes_config.get(
            "move_link_text_color", [100, 150, 255]
        )
        bg_rgb = f"rgb({pane_bg[0]},{pane_bg[1]},{pane_bg[2]})"
        text_rgb = f"rgb({notes_text_color[0]},{notes_text_color[1]},{notes_text_color[2]})"
        style = f"QTextEdit {{ background-color: {bg_rgb}; color: {text_rgb}; border: none; padding: 6px; }}"
        StyleManager.style_text_edit_scrollbar(self._notes_edit, self.config, pane_bg, [60, 60, 65], style)
        self._notes_edit.setPlaceholderText(notes_config.get("placeholder_text", "Add notes about this game..."))

        copy_shortcut = QShortcut(QKeySequence("Ctrl+C"), self._notes_edit)
        copy_shortcut.activated.connect(self._notes_edit.copy)
        meta_c = QShortcut(QKeySequence("Meta+C"), self._notes_edit)
        meta_c.activated.connect(self._notes_edit.copy)
        paste_shortcut = QShortcut(QKeySequence("Ctrl+V"), self._notes_edit)
        paste_shortcut.activated.connect(self._notes_edit.paste)
        meta_v = QShortcut(QKeySequence("Meta+V"), self._notes_edit)
        meta_v.activated.connect(self._notes_edit.paste)

        self._setup_format_toolbar(layout, pane_bg, notes_text_color, font_family, font_size)

        self._notes_edit.textChanged.connect(self._on_notes_text_changed)
        self._notes_edit.cursorPositionChanged.connect(self._sync_format_toolbar_enabled_state)

        layout.addWidget(self._notes_edit, 1)

        # Ensure initial state is correct when the view gets focus.
        self._sync_format_toolbar_enabled_state()

    def _setup_format_toolbar(
        self,
        layout: QVBoxLayout,
        pane_bg: list,
        notes_text_color: list,
        font_family: str,
        font_size: float,
    ) -> None:
        """Create the small markdown toolbar above the notes editor."""
        toolbar = QWidget(self)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(6, 4, 6, 4)
        toolbar_layout.setSpacing(4)

        bg_rgb = f"rgb({pane_bg[0]},{pane_bg[1]},{pane_bg[2]})"
        # Keep it visually subtle: same background + thin bottom border.
        toolbar.setStyleSheet(
            f"QWidget {{ background-color: {bg_rgb}; border-bottom: 1px solid rgb(60, 60, 65); }}"
        )

        # Order is intentionally: headings first, then bold/italic.
        buttons: list[QPushButton] = []

        btn_h1 = QPushButton("H1", toolbar)
        btn_h2 = QPushButton("H2", toolbar)
        btn_h3 = QPushButton("H3", toolbar)
        btn_b = QPushButton("B", toolbar)
        btn_i = QPushButton("I", toolbar)
        btn_code = QPushButton("`", toolbar)
        btn_strike = QPushButton("S", toolbar)
        btn_quote = QPushButton(">", toolbar)

        buttons.extend([btn_h1, btn_h2, btn_h3, btn_b, btn_i, btn_code, btn_strike, btn_quote])
        self._format_toolbar_buttons = {
            "h1": btn_h1,
            "h2": btn_h2,
            "h3": btn_h3,
            "bold": btn_b,
            "italic": btn_i,
            "inline_code": btn_code,
            "strike": btn_strike,
            "blockquote": btn_quote,
        }

        # Make all buttons equal width (prevents the single-letter buttons
        # from being visually narrower).
        toolbar_font = QFont(font_family, int(font_size))
        metrics = QFontMetrics(toolbar_font)
        widest = max(
            ["H1", "H2", "H3", "B", "I", "`", "S", ">"],
            key=lambda t: metrics.horizontalAdvance(t),
        )
        fixed_w = metrics.horizontalAdvance(widest) + 22
        for btn in self._format_toolbar_buttons.values():
            btn.setFixedWidth(fixed_w)

        for key, btn in self._format_toolbar_buttons.items():
            btn.setToolTip(
                {
                    "h1": "Insert H1 heading for the selected line(s)",
                    "h2": "Insert H2 heading for the selected line(s)",
                    "h3": "Insert H3 heading for the selected line(s)",
                    "bold": "Wrap selection in bold Markdown",
                    "italic": "Wrap selection in italic Markdown",
                    "inline_code": "Wrap selection in inline code (`...`)",
                    "strike": "Wrap selection in strikethrough (~~...~~)",
                    "blockquote": "Insert/replace blockquote prefix (> ) for the selected line(s)",
                }[key]
            )
            btn.clicked.connect(lambda _, k=key: self._on_format_button_clicked(k))
            # Buttons are added to the toolbar_layout in grouped order below.

        def _add_separator() -> None:
            separator = QFrame(toolbar)
            separator.setFrameShape(QFrame.Shape.VLine)
            separator.setFrameShadow(QFrame.Shadow.Plain)
            separator.setLineWidth(1)
            # Use the same tone as the toolbar border for consistency.
            c = self._toolbar_separator_color
            # QFrame VLine may render an extra border/outline by default.
            # Force a single solid line by removing borders and using a fixed width.
            separator.setFixedWidth(1)
            separator.setContentsMargins(0, 0, 0, 0)
            separator.setStyleSheet(
                "QFrame { "
                f"background-color: rgb({int(c[0])}, {int(c[1])}, {int(c[2])}); "
                "border: 0px; padding: 0px; margin: 0px;"
                "}"
            )
            toolbar_layout.addWidget(separator)

        StyleManager.style_buttons(
            buttons,
            self.config,
            bg_color=pane_bg,
            border_color=[60, 60, 65],
            text_color=notes_text_color,
            font_family=font_family,
            font_size=font_size,
            min_height=24,
        )

        # Make markdown-format buttons self-descriptive via font styling.
        # (This affects only the button label, not the markdown inserted.)
        btn_b_font = QFont(font_family, int(font_size))
        btn_b_font.setBold(True)
        btn_b.setFont(btn_b_font)

        btn_i_font = QFont(font_family, int(font_size))
        btn_i_font.setItalic(True)
        btn_i.setFont(btn_i_font)

        btn_strike_font = QFont(font_family, int(font_size))
        btn_strike_font.setStrikeOut(True)
        btn_strike.setFont(btn_strike_font)

        # Add grouped buttons + visual separators.
        group_headings = [btn_h1, btn_h2, btn_h3]
        group_bold_italic = [btn_b, btn_i]
        group_symbols = [btn_code, btn_strike, btn_quote]

        for idx, btn in enumerate(group_headings):
            toolbar_layout.addWidget(btn)
        _add_separator()
        for btn in group_bold_italic:
            toolbar_layout.addWidget(btn)
        _add_separator()
        for btn in group_symbols:
            toolbar_layout.addWidget(btn)

        # Keep toolbar compact.
        toolbar_layout.addStretch(0)

        # Start disabled until we have an active selection.
        for btn in buttons:
            btn.setEnabled(False)

        self._toolbar_widget = toolbar

        # Cache required width so we can fade out when there's not enough space.
        self._toolbar_required_width = toolbar.sizeHint().width()

        # Setup fade animation for toolbar.
        self._toolbar_opacity_effect = QGraphicsOpacityEffect(toolbar)
        self._toolbar_opacity_effect.setOpacity(1.0)
        toolbar.setGraphicsEffect(self._toolbar_opacity_effect)
        self._toolbar_opacity_animation = QPropertyAnimation(
            self._toolbar_opacity_effect, b"opacity", self
        )
        self._toolbar_opacity_animation.setDuration(180)
        self._toolbar_opacity_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._toolbar_opacity_animation.finished.connect(
            self._on_toolbar_opacity_animation_finished
        )

        layout.addWidget(toolbar, 0)

    def _sync_format_toolbar_enabled_state(self) -> None:
        """Enable toolbar buttons only when the editor has a non-empty selection.

        Bold/italic are disabled for selections that are inside heading lines,
        to avoid inserting markdown markers that conflict with heading syntax.
        """
        if not hasattr(self, "_notes_edit") or self._notes_edit is None:
            return
        has_selection = self._notes_edit.textCursor().hasSelection()
        plain = self._current_plain if self._current_plain is not None else self._notes_edit.toPlainText()
        cursor = self._notes_edit.textCursor()
        selection_start = cursor.selectionStart() if has_selection else -1
        selection_end = cursor.selectionEnd() if has_selection else -1
        selection_in_heading = (
            has_selection
            and selection_start >= 0
            and selection_end >= 0
            and self._notes_controller
            and self._notes_controller.selection_intersects_heading_line(plain, selection_start, selection_end)
        )
        for btn in self._format_toolbar_buttons.values():
            # Headings always allowed when selection exists.
            if btn in (self._format_toolbar_buttons.get("bold"), self._format_toolbar_buttons.get("italic")):
                btn.setEnabled(has_selection and not selection_in_heading)
            else:
                btn.setEnabled(has_selection)

        # If the toolbar is currently collapsed due to width, keep it hidden.
        if self._toolbar_widget and self._toolbar_collapsed:
            self._toolbar_widget.setVisible(False)

    def _on_format_button_clicked(self, kind: str) -> None:
        """Wrap current selection with Markdown syntax."""
        if not self._notes_edit or not self._notes_controller:
            return
        cursor = self._notes_edit.textCursor()
        if not cursor.hasSelection():
            return

        plain = self._current_plain if self._current_plain is not None else self._notes_edit.toPlainText()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        if end < start:
            start, end = end, start

        if start < 0 or end < 0 or start == end:
            return

        self._link_debounce_timer.stop()
        self._updating_links = True
        try:
            new_plain, new_start, new_end = self._notes_controller.apply_notes_toolbar_action(
                kind=kind,
                plain=plain,
                start=start,
                end=end,
            )
            # If nothing changed (e.g. bold/italic inside heading), do nothing.
            if new_plain == plain and new_start == start and new_end == end:
                return

            self._current_plain = new_plain
            self._notes_edit.setPlainText(new_plain)
            self._apply_in_place_formatting(self._notes_edit, new_plain)
            self._set_cursor_selection_bounds(new_start, new_end)
        finally:
            QTimer.singleShot(0, self._clear_updating_links)

    def _set_cursor_selection_bounds(self, start: int, end: int) -> None:
        """Set QTextCursor selection bounds with safe clamping."""
        max_pos = self._notes_edit.document().characterCount() - 1
        start = max(0, min(start, max_pos))
        end = max(0, min(end, max_pos))

        new_cursor = self._notes_edit.textCursor()
        new_cursor.setPosition(start)
        new_cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        self._notes_edit.setTextCursor(new_cursor)

    def _on_active_game_changed(self, game) -> None:
        """Handle active game change: clear when game is None, otherwise load notes (same pattern as metadata/moves list)."""
        if game is None:
            self._current_plain = ""
            self._set_content_with_links("")
            return
        if not self._notes_controller:
            return
        plain = self._notes_controller.get_notes_for_current_game()
        self._current_plain = plain
        self._set_content_with_links(plain)

    def _on_notes_text_changed(self) -> None:
        """Debounce and re-apply move links when user types."""
        if self._updating_links:
            return
        # Source-of-truth for re-rendering/saving is the unformatted plain text we had
        # right after the user's edit, before we call setHtml() (which can slightly
        # change how QTextEdit reconstructs its plain text).
        self._current_plain = self._notes_edit.toPlainText()
        self._link_debounce_timer.stop()
        self._link_debounce_timer.start(400)

    def _reapply_move_links(self) -> None:
        """Apply in-place formatting (move links + supported markdown)."""
        if self._updating_links or not self._notes_controller:
            return
        edit = self._notes_edit
        plain = self._current_plain if self._current_plain is not None else edit.toPlainText()

        cursor = edit.textCursor()
        saved_pos = cursor.position()

        self._updating_links = True
        try:
            self._apply_in_place_formatting(edit, plain)
            # Restore cursor position
            new_cursor = edit.textCursor()
            max_pos = edit.document().characterCount() - 1
            new_cursor.setPosition(min(saved_pos, max(0, max_pos)))
            edit.setTextCursor(new_cursor)
        finally:
            QTimer.singleShot(0, self._clear_updating_links)

    def _clear_updating_links(self) -> None:
        self._updating_links = False

    def _set_content_with_links(self, plain: str) -> None:
        """Set editor content as plain text and apply in-place formatting."""
        self._link_debounce_timer.stop()
        self._updating_links = True
        self._notes_edit.setPlainText(plain or "")
        self._apply_in_place_formatting(self._notes_edit, plain or "")
        QTimer.singleShot(0, self._clear_updating_links)

    def _apply_in_place_formatting(self, edit: QTextEdit, plain: str) -> None:
        """Apply formatting spans to the QTextEdit document."""
        if edit is None or not self._notes_controller:
            return

        spans = self._notes_controller.get_notes_format_spans(plain)
        doc = edit.document()

        # Reset all character formatting first to avoid stale formatting.
        reset_cursor = QTextCursor(doc)
        reset_cursor.movePosition(QTextCursor.MoveOperation.Start)
        reset_cursor.movePosition(
            QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor
        )
        reset_cursor.setCharFormat(QTextCharFormat())

        # Apply spans in deterministic precedence order.
        kind_order = {
            # Always apply hidden marker formatting last so it can't be
            # overridden by other markdown styles that may overlap.
            "hidden": 99,
            "italic": 1,
            "blockquote": 1,
            "bold": 2,
            "bold_italic": 3,
            "inline_code": 3,
            # Apply strike after bold/bold+italic so strikeout doesn't get cleared
            # by later spans that don't set strike-out.
            "strike": 4,
            "move_bold": 5,
            "move_link": 6,
        }
        spans_sorted = sorted(spans, key=lambda s: kind_order.get(s.kind, 99))

        for span in spans_sorted:
            if span.end <= span.start:
                continue
            if span.start < 0:
                continue
            if span.end > doc.characterCount() - 1:
                continue

            fmt = QTextCharFormat()

            if span.kind == "hidden":
                fmt.setForeground(QColor(0, 0, 0, 0))
                # Shrink marker glyphs aggressively to minimize "invisible spacing".
                # Use a small but valid point size to avoid Qt warnings/clamping to 0.
                fmt.setFontPointSize(float(getattr(self, "_hidden_marker_font_point_size", 0.5)))
            elif span.kind == "italic":
                fmt.setFontItalic(True)
            elif span.kind == "bold":
                fmt.setFontWeight(QFont.Weight.Bold)
                if span.font_point_size is not None:
                    fmt.setFontPointSize(span.font_point_size)
            elif span.kind == "bold_italic":
                fmt.setFontWeight(QFont.Weight.Bold)
                fmt.setFontItalic(True)
            elif span.kind == "inline_code":
                # Inline code: more pronounced (configurable).
                bg = getattr(self, "_inline_code_background_color", [90, 110, 160])
                a = getattr(self, "_inline_code_background_alpha", 170)
                fg = getattr(self, "_inline_code_text_color", [255, 255, 255])
                fmt.setBackground(QColor(int(bg[0]), int(bg[1]), int(bg[2]), int(a)))
                fmt.setForeground(QColor(int(fg[0]), int(fg[1]), int(fg[2])))
            elif span.kind == "strike":
                fmt.setFontStrikeOut(True)
            elif span.kind == "blockquote":
                # Blockquote: slightly muted color to distinguish the quoted line(s).
                c = getattr(self, "_blockquote_text_color", [210, 190, 130])
                fmt.setForeground(QColor(int(c[0]), int(c[1]), int(c[2])))
            elif span.kind == "move_bold":
                fmt.setFontWeight(QFont.Weight.Bold)
            elif span.kind == "move_link":
                fmt.setFontWeight(QFont.Weight.Bold)
                c = getattr(self, "_move_link_text_color", [100, 150, 255])
                fmt.setForeground(QColor(int(c[0]), int(c[1]), int(c[2])))
                fmt.setFontUnderline(True)
                if span.anchor_href:
                    fmt.setAnchorHref(span.anchor_href)
            else:
                continue

            cursor = QTextCursor(doc)
            cursor.setPosition(span.start)
            cursor.setPosition(span.end, QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(fmt)

    def _on_move_link_clicked(self, notation: str) -> bool:
        if not self._notes_controller or not notation:
            return False
        return self._notes_controller.navigate_from_move_link(notation)

    def resizeEvent(self, event) -> None:
        """Fade toolbar when the panel becomes too narrow to fit the buttons."""
        super().resizeEvent(event)
        self._update_toolbar_fit_visibility()

    def _on_toolbar_opacity_animation_finished(self) -> None:
        """Hide toolbar only if we are in the collapsed state."""
        if self._toolbar_widget and self._toolbar_collapsed:
            self._toolbar_widget.setVisible(False)

    def _update_toolbar_fit_visibility(self) -> None:
        if not self._toolbar_widget or self._toolbar_required_width <= 0:
            return

        available_width = self.width()
        should_collapse = available_width < self._toolbar_required_width

        if should_collapse and not self._toolbar_collapsed:
            self._toolbar_collapsed = True
            if self._toolbar_opacity_effect and self._toolbar_opacity_animation:
                self._toolbar_widget.setVisible(True)
                self._toolbar_opacity_animation.stop()
                self._toolbar_opacity_animation.setStartValue(
                    self._toolbar_opacity_effect.opacity()
                )
                self._toolbar_opacity_animation.setEndValue(0.0)
                self._toolbar_opacity_animation.start()
            else:
                self._toolbar_widget.setVisible(False)

        elif not should_collapse and self._toolbar_collapsed:
            self._toolbar_collapsed = False
            if self._toolbar_opacity_effect and self._toolbar_opacity_animation:
                self._toolbar_widget.setVisible(True)
                self._toolbar_opacity_animation.stop()
                self._toolbar_opacity_animation.setStartValue(0.0)
                self._toolbar_opacity_animation.setEndValue(1.0)
                self._toolbar_opacity_animation.start()
            else:
                self._toolbar_widget.setVisible(True)

    def get_plain_text(self) -> str:
        return self._current_plain

    def set_notes_text(self, plain: str) -> None:
        """Set notes content (e.g. after Clear). Updates both cache and display with links."""
        self._current_plain = plain
        self._set_content_with_links(plain)

    def set_game_model(self, model: Optional["GameModel"]) -> None:
        if self._game_model:
            self._game_model.active_game_changed.disconnect(self._on_active_game_changed)
        self._game_model = model
        if model:
            model.active_game_changed.connect(self._on_active_game_changed)
            self._on_active_game_changed(model.active_game)

    def set_notes_controller(self, controller: Optional["NotesController"]) -> None:
        self._notes_controller = controller
        if self._notes_edit and controller:
            self._notes_edit.set_link_click_handler(self._on_move_link_clicked)
