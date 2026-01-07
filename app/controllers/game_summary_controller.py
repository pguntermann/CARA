"""Controller for orchestrating game summary calculations."""

from __future__ import annotations

from dataclasses import asdict
import html
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtSignal

from app.models.game_model import GameModel
from app.models.moveslist_model import MovesListModel, MoveData
from app.services.game_summary_service import GameSummaryService, GameSummary, GameHighlight


class GameSummaryController(QObject):
    """Controller responsible for producing and exposing game summary data."""

    summary_updated = pyqtSignal(object, list)  # GameSummary, List[MoveData]
    summary_unavailable = pyqtSignal(str)  # Reason key (e.g., "not_analyzed", "no_moves")

    def __init__(
        self,
        config: Dict[str, Any],
        game_model: GameModel,
        moveslist_model: Optional[MovesListModel] = None,
        classification_model: Optional[Any] = None,
    ) -> None:
        super().__init__()
        self.config = config
        self._game_model = game_model
        self._moveslist_model = moveslist_model
        self.summary_service = GameSummaryService(config, classification_model)

        self.current_summary: Optional[GameSummary] = None
        self._latest_moves: List[MoveData] = []
        self._last_unavailable_reason: str = "not_analyzed"

        if self._game_model:
            self._game_model.is_game_analyzed_changed.connect(self._on_analysis_status_changed)
            self._game_model.active_game_changed.connect(self._on_active_game_changed)

    def set_moveslist_model(self, moveslist_model: MovesListModel) -> None:
        """Inject the moves list model used for summary calculations."""
        self._moveslist_model = moveslist_model
        if self._game_model and self._game_model.is_game_analyzed:
            self.refresh_summary()

    def refresh_summary(self) -> None:
        """Recalculate the game summary if prerequisites are satisfied."""
        if not self._game_model or not self._game_model.is_game_analyzed:
            self._emit_unavailable("not_analyzed")
            return

        if not self._moveslist_model:
            self._emit_unavailable("moves_model_missing")
            return

        moves = self._moveslist_model.get_all_moves()
        if not moves:
            self._emit_unavailable("no_moves")
            return

        try:
            # Get game result from active game if available
            game_result = None
            if self._game_model and self._game_model.active_game:
                game_result = self._game_model.active_game.result
            summary = self.summary_service.calculate_summary(moves, len(moves), game_result=game_result)
        except Exception as e:
            # Avoid crashing the UI; surface a generic error state
            # Log the exception to console for debugging
            import sys
            import traceback
            print(f"Error calculating game summary: {e}", file=sys.stderr)
            print(f"Traceback: {traceback.format_exc()}", file=sys.stderr)
            self._emit_unavailable("error")
            return

        self.current_summary = summary
        self._latest_moves = moves
        self.summary_updated.emit(summary, moves)

    def get_current_summary(self) -> Optional[GameSummary]:
        """Return the most recently calculated summary, if any."""
        return self.current_summary

    def get_latest_moves(self) -> List[MoveData]:
        """Return the move list used for the latest summary."""
        return self._latest_moves

    def get_last_unavailable_reason(self) -> str:
        """Return the most recent reason for summary unavailability."""
        return self._last_unavailable_reason

    def get_highlights_html(self) -> str:
        """Build the highlights section as HTML for debugging/export."""
        if not self.current_summary or not self.current_summary.highlights:
            return ""

        opening, middlegame, endgame = self.partition_highlights_by_phase(
            self.current_summary.highlights,
            self.current_summary.opening_end,
            self.current_summary.middlegame_end,
        )

        sections: List[str] = []

        def build_section(title: str, items: List[GameHighlight]) -> None:
            if not items:
                return
            rows = [
                f'<div class="gh-section-title">{html.escape(title)}</div>',
                '<ul class="gh-section-list">',
            ]
            for highlight in items:
                move_label = html.escape(highlight.move_notation) if highlight.move_notation else ""
                description = html.escape(highlight.description) if highlight.description else ""
                rows.append(f'<li><span class="gh-move">{move_label}</span> {description}</li>')
            rows.append("</ul>")
            sections.append("\n".join(rows))

        build_section("Opening Highlights", opening)
        build_section("Middlegame Highlights", middlegame)
        build_section("Endgame Highlights", endgame)

        if not sections:
            return ""

        container = [
            '<div class="game-highlights">',
            '<div class="gh-header">Game Highlights</div>',
            "\n".join(sections),
            "</div>",
        ]
        return "\n".join(container).strip()

    def get_highlights_json(self) -> List[Dict[str, Any]]:
        """Return game highlights as a JSON-serializable structure."""
        if not self.current_summary or not self.current_summary.highlights:
            return []

        opening_end = self.current_summary.opening_end or 0
        middlegame_end = self.current_summary.middlegame_end or 0

        serialized: List[Dict[str, Any]] = []
        for highlight in self.current_summary.highlights:
            data = asdict(highlight)
            data["phase"] = self._determine_highlight_phase(highlight.move_number, opening_end, middlegame_end)
            serialized.append(data)
        return serialized

    def partition_highlights_by_phase(
        self,
        highlights: Optional[List[GameHighlight]] = None,
        opening_end: Optional[int] = None,
        middlegame_end: Optional[int] = None,
    ) -> Tuple[List[GameHighlight], List[GameHighlight], List[GameHighlight]]:
        """Partition highlights into opening, middlegame, and endgame lists."""
        summary = self.current_summary
        if highlights is None and summary:
            highlights = summary.highlights
        if highlights is None:
            return [], [], []

        opening_end_val = opening_end if opening_end is not None else (summary.opening_end if summary else 0)
        middlegame_end_val = (
            middlegame_end if middlegame_end is not None else (summary.middlegame_end if summary else 0)
        )

        opening_highlights: List[GameHighlight] = []
        middlegame_highlights: List[GameHighlight] = []
        endgame_highlights: List[GameHighlight] = []

        for highlight in highlights:
            phase = self._determine_highlight_phase(highlight.move_number, opening_end_val, middlegame_end_val)
            if phase == "opening":
                opening_highlights.append(highlight)
            elif phase == "middlegame":
                middlegame_highlights.append(highlight)
            else:
                endgame_highlights.append(highlight)

        return opening_highlights, middlegame_highlights, endgame_highlights

    def _on_analysis_status_changed(self, is_analyzed: bool) -> None:
        """Respond to analysis completion toggles."""
        if not is_analyzed:
            self._emit_unavailable("not_analyzed")
        else:
            self.refresh_summary()

    def _on_active_game_changed(self, _game) -> None:
        """Re-evaluate summary when the active game switches."""
        # Re-check the current analyzed flag to determine availability
        if self._game_model:
            self._on_analysis_status_changed(self._game_model.is_game_analyzed)

    def _emit_unavailable(self, reason: str) -> None:
        """Emit a summary-unavailable event with the provided reason."""
        self.current_summary = None
        self._latest_moves = []
        self._last_unavailable_reason = reason
        self.summary_unavailable.emit(reason)

    @staticmethod
    def _determine_highlight_phase(move_number: int, opening_end: int, middlegame_end: int) -> str:
        """Determine which phase a move belongs to."""
        if opening_end and move_number <= opening_end:
            return "opening"
        if middlegame_end and move_number < middlegame_end:
            return "middlegame"
        return "endgame"

