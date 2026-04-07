"""Debug-only controller actions.

This controller hosts development and diagnostics actions that would otherwise
inflate MainWindow and mix orchestration logic into the view layer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from PyQt6.QtWidgets import QApplication


class DebugController:
    """Controller for debug-only helper actions."""

    def __init__(self, config: Dict[str, Any], app_controller: Any) -> None:
        self.config = config
        self._app_controller = app_controller

    def _set_status(self, message: str) -> None:
        try:
            self._app_controller.set_status(message)
        except Exception:
            # Debug helper: never crash app on diagnostics.
            pass

    @staticmethod
    def _copy_to_clipboard(text: str) -> None:
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def copy_pgn_view_debug_to_clipboard(self, pgn_view: Any) -> None:
        """Copy PGN HTML and visibility settings from a PGN view to clipboard."""
        if not pgn_view or not hasattr(pgn_view, "get_debug_info"):
            self._set_status("DEBUG: PGN view not available")
            return

        try:
            html, settings = pgn_view.get_debug_info()
        except Exception as exc:
            self._set_status(f"DEBUG: Failed to collect PGN debug info: {exc}")
            return

        try:
            debug_text = f"""=== PGN VIEW DEBUG INFO ===

Visibility Settings:
- Show Metadata: {settings['show_metadata']}
- Show Comments: {settings['show_comments']}
- Show Variations: {settings['show_variations']}
- Show Annotations: {settings['show_annotations']}
- Show Results: {settings['show_results']}

=== HTML OUTPUT ===

{html}

=== END DEBUG INFO ===
"""
        except Exception as exc:
            self._set_status(f"DEBUG: Failed to format PGN debug info: {exc}")
            return

        self._copy_to_clipboard(debug_text)
        self._set_status("DEBUG: PGN HTML and settings copied to clipboard")

    def copy_game_highlights_html_to_clipboard(self) -> None:
        """Copy game highlights HTML from the summary controller to clipboard."""
        try:
            summary_controller = self._app_controller.get_game_summary_controller()
            highlights_html = summary_controller.get_highlights_html() if summary_controller else ""
        except Exception as exc:
            self._set_status(f"DEBUG: Error reading game highlights HTML: {exc}")
            return

        if not highlights_html:
            self._set_status("DEBUG: No game highlights available to copy")
            return

        self._copy_to_clipboard(highlights_html)
        self._set_status("DEBUG: Game highlights HTML copied to clipboard")

    def copy_game_highlights_json_to_clipboard(self) -> None:
        """Copy game highlights JSON data from the summary controller to clipboard."""
        try:
            summary_controller = self._app_controller.get_game_summary_controller()
            highlights_data = summary_controller.get_highlights_json() if summary_controller else []
        except Exception as exc:
            self._set_status(f"DEBUG: Error reading game highlights JSON: {exc}")
            return

        if not highlights_data:
            self._set_status("DEBUG: No game highlights available to copy")
            return

        self._copy_to_clipboard(json.dumps(highlights_data, indent=2, ensure_ascii=False))
        self._set_status("DEBUG: Game highlights JSON copied to clipboard")

    def create_highlight_rule_test_data_file(self, filename: str) -> None:
        """Write the active game's analysis JSON into tests/highlight_rules/games/<filename>."""
        from app.services.analysis_data_storage_service import AnalysisDataStorageService

        filename = (filename or "").strip()
        if not filename:
            return
        if not filename.lower().endswith(".json"):
            filename += ".json"

        try:
            game_model = self._app_controller.get_game_controller().get_game_model()
            active_game = game_model.active_game
        except Exception as exc:
            self._set_status(f"DEBUG: Error reading active game: {exc}")
            return

        if not active_game:
            self._set_status("DEBUG: No active game")
            return

        if not AnalysisDataStorageService.has_analysis_data(active_game):
            self._set_status("DEBUG: Game does not have CARAAnalysisData tag")
            return

        raw_json = AnalysisDataStorageService.get_raw_analysis_data(active_game)
        if raw_json is None:
            self._set_status("DEBUG: Failed to deserialize CARAAnalysisData tag")
            return

        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            self._set_status("DEBUG: Analysis data is not valid JSON")
            return

        repo_root = Path(__file__).resolve().parents[2]
        games_dir = repo_root / "tests" / "highlight_rules" / "games"
        games_dir.mkdir(parents=True, exist_ok=True)
        target_path = games_dir / filename

        if target_path.exists():
            self._set_status(f"DEBUG: File already exists: {target_path.name}")
            return

        try:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            self._set_status(f"DEBUG: Error creating highlight test data: {exc}")
            return

        self._set_status(f"DEBUG: Highlight test data saved to {target_path.name}")

    def copy_deserialized_analysis_tag_to_clipboard(self) -> None:
        """Copy deserialized and decompressed CARAAnalysisData tag to clipboard."""
        from app.services.analysis_data_storage_service import AnalysisDataStorageService

        try:
            game_model = self._app_controller.get_game_controller().get_game_model()
            active_game = game_model.active_game
        except Exception as exc:
            self._set_status(f"DEBUG: Error reading active game: {exc}")
            return

        if not active_game:
            self._set_status("DEBUG: No active game")
            return

        if not AnalysisDataStorageService.has_analysis_data(active_game):
            self._set_status("DEBUG: Game does not have CARAAnalysisData tag")
            return

        json_str = AnalysisDataStorageService.get_raw_analysis_data(active_game)
        if json_str is None:
            self._set_status("DEBUG: Failed to deserialize CARAAnalysisData tag")
            return

        try:
            self._copy_to_clipboard(json_str)
        except Exception as exc:
            self._set_status(f"DEBUG: Error copying analysis data: {exc}")
            return

        self._set_status("DEBUG: Deserialized CARAAnalysisData copied to clipboard")

    def copy_deserialized_annotation_tag_to_clipboard(self) -> None:
        """Copy deserialized and decompressed CARAAnnotations tag to clipboard."""
        from app.services.annotation_storage_service import AnnotationStorageService

        try:
            game_model = self._app_controller.get_game_controller().get_game_model()
            active_game = game_model.active_game
        except Exception as exc:
            self._set_status(f"DEBUG: Error reading active game: {exc}")
            return

        if not active_game:
            self._set_status("DEBUG: No active game")
            return

        if not AnnotationStorageService.has_annotations(active_game):
            self._set_status("DEBUG: Game does not have CARAAnnotations tag")
            return

        json_str = AnnotationStorageService.get_raw_annotations_data(active_game)
        if json_str is None:
            self._set_status("DEBUG: Failed to deserialize CARAAnnotations tag")
            return

        try:
            self._copy_to_clipboard(json_str)
        except Exception as exc:
            self._set_status(f"DEBUG: Error copying annotation data: {exc}")
            return

        self._set_status("DEBUG: Deserialized CARAAnnotations copied to clipboard")

