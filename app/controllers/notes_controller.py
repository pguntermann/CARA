"""Controller for Notes feature (storage, rendering, navigation)."""

from __future__ import annotations

import html
from typing import Any, Dict, Optional, List

from app.controllers.game_controller import GameController
from app.services.notes_storage_service import NotesStorageService
from app.services.notes_formatter_service import NotesFormatterService


class NotesController:
    """Controller for storing/loading notes and rendering move links.

    This controller is responsible for Notes-specific orchestration:
    - loading/saving/clearing notes from/to the active game's PGN tags
    - rendering notes text to HTML with move links
    - handling navigation when a move link is clicked
    """

    def __init__(self, config: Dict[str, Any], game_controller: GameController) -> None:
        self.config = config
        self._game_controller = game_controller

    def get_notes_for_current_game(self) -> str:
        """Get notes for the active game, loading from CARANotes tag if not cached."""
        game = self._game_controller.get_game_model().active_game
        if game is None:
            return ""
        if getattr(game, "notes", None) is not None:
            return game.notes
        return NotesStorageService.load_notes(game)

    def save_notes_to_current_game(self, notes_text: str) -> bool:
        """Save notes into the active game's PGN tag (in memory)."""
        game = self._game_controller.get_game_model().active_game
        if game is None:
            return False
        ok = NotesStorageService.store_notes(game, notes_text, self.config)
        if ok:
            self._game_controller.get_game_model().refresh_active_game()
        return ok

    def clear_notes_for_current_game(self) -> bool:
        """Clear notes for the active game (removes CARANotes tag in memory)."""
        game = self._game_controller.get_game_model().active_game
        if game is None:
            return False
        ok = NotesStorageService.clear_notes(game)
        if ok:
            self._game_controller.get_game_model().refresh_active_game()
        return ok

    def render_notes_html(self, plain: str, link_style: str, bold_style: str) -> str:
        """Render notes as HTML with move links (and bold-only tokens)."""
        notation_to_ply = self._game_controller.get_move_notation_to_ply_map()
        return NotesFormatterService.plain_to_html_with_move_links(
            plain=plain,
            notation_to_ply=notation_to_ply,
            link_style=link_style,
            bold_style=bold_style,
        )

    def get_notes_format_spans(self, plain: str) -> List[NotesFormatterService.FormatSpan]:
        """Return formatting spans for in-place Notes rendering."""
        notation_to_ply = self._game_controller.get_move_notation_to_ply_map()
        return NotesFormatterService.get_notes_format_spans(plain, notation_to_ply)

    def selection_intersects_heading_line(self, plain: str, start: int, end: int) -> bool:
        """Return True if selection intersects a markdown heading line."""
        return NotesFormatterService.selection_intersects_heading_line(plain, start, end)

    def apply_notes_toolbar_action(
        self,
        kind: str,
        plain: str,
        start: int,
        end: int,
    ) -> tuple[str, int, int]:
        """Apply a toolbar formatting action to the selected plain-text range."""
        return NotesFormatterService.apply_toolbar_action(kind=kind, plain=plain, start=start, end=end)

    def navigate_from_move_link(self, notation: str) -> bool:
        """Navigate to the move referenced by a clicked link (notation from href)."""
        if not notation:
            return False
        notation = html.unescape(notation).strip().rstrip(".,;:!?)")
        notation_to_ply = self._game_controller.get_move_notation_to_ply_map()
        ply = notation_to_ply.get(notation)
        if ply is None and " " in notation:
            ply = notation_to_ply.get(notation.replace(" ", "", 1))
        if ply is None:
            return False
        return self._game_controller.navigate_to_ply(ply)

