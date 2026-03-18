"""Notes view for detail panel: plain-text game notes with move linking."""

from typing import Dict, Any, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QMenu, QApplication,
)
from PyQt6.QtGui import (
    QFont, QKeySequence, QShortcut, QMouseEvent, QContextMenuEvent, QAction,
)
from PyQt6.QtCore import Qt, QTimer

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
        self._link_debounce_timer = QTimer(self)
        self._link_debounce_timer.setSingleShot(True)
        self._link_debounce_timer.timeout.connect(self._reapply_move_links)
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

        self._notes_edit.textChanged.connect(self._on_notes_text_changed)

        layout.addWidget(self._notes_edit)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = self._notes_edit.createStandardContextMenu()
        menu.exec(event.globalPos())

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
        self._link_debounce_timer.stop()
        self._link_debounce_timer.start(400)

    def _reapply_move_links(self) -> None:
        """Re-build HTML with links from current plain text and restore cursor."""
        if self._updating_links or not self._notes_controller:
            return
        edit = self._notes_edit
        plain = edit.toPlainText()
        cursor = edit.textCursor()
        saved_pos = cursor.position()
        self._updating_links = True
        if not plain:
            edit.setPlainText("")
        else:
            html_content = self._plain_to_html_with_links(plain)
            edit.setHtml(html_content)
        # Restore cursor position (plain text length unchanged by link injection)
        new_cursor = edit.textCursor()
        max_pos = edit.document().characterCount() - 1
        new_cursor.setPosition(min(saved_pos, max(0, max_pos)))
        edit.setTextCursor(new_cursor)
        QTimer.singleShot(0, self._clear_updating_links)

    def _clear_updating_links(self) -> None:
        self._updating_links = False

    def _set_content_with_links(self, plain: str) -> None:
        """Set editor content as HTML with move notation links, or empty so placeholder shows."""
        self._link_debounce_timer.stop()
        self._updating_links = True
        if not plain:
            self._notes_edit.setPlainText("")
        else:
            html_content = self._plain_to_html_with_links(plain)
            self._notes_edit.setHtml(html_content)
        QTimer.singleShot(0, self._clear_updating_links)

    def _plain_to_html_with_links(self, plain: str) -> str:
        """Convert plain text to HTML with move links."""
        if not plain:
            return ""
        if not self._notes_controller:
            # Fallback: show raw text (no links) if controller isn't wired yet.
            return plain.replace("\n", "<br>")

        link_style = "color: rgb(100,150,255); text-decoration: underline; font-weight: bold;"
        bold_style = "font-weight: bold;"
        return self._notes_controller.render_notes_html(plain, link_style=link_style, bold_style=bold_style)

    def _on_move_link_clicked(self, notation: str) -> bool:
        if not self._notes_controller or not notation:
            return False
        return self._notes_controller.navigate_from_move_link(notation)

    def get_plain_text(self) -> str:
        return self._notes_edit.toPlainText()

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
