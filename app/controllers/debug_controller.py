"""Debug-only controller actions.

This controller hosts development and diagnostics actions that would otherwise
inflate MainWindow and mix orchestration logic into the view layer.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtWidgets import QApplication


# Rules that appear in fewer than this fraction of scanned games are "rare".
_RARE_GAME_FRACTION = 0.01


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
- Show PGN header tags: {settings['show_metadata']}
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

    def scan_highlight_rule_frequency(self, parent: Any = None) -> Optional[str]:
        """Scan analyzed games in the active DB for highlight rule frequency.

        Recomputes summary highlights per game (same pipeline as the UI), counts
        ``rule_type`` hits (with ply locations), copies a text report to the
        clipboard, and shows a clickable frequency table.

        Returns:
            The full report text, or None if the scan could not start.
        """
        from collections import defaultdict

        from app.services.analysis_data_storage_service import AnalysisDataStorageService
        from app.services.game_highlight_rules_service import GameHighlightRulesService
        from app.services.game_highlights.rule_catalog import list_builtin_rules
        from app.services.game_summary_service import GameSummaryService
        from app.services.progress_service import ProgressService
        from app.views.dialogs.highlight_rule_frequency_dialog import (
            HighlightFrequencyRow,
            HighlightRuleFrequencyDialog,
        )

        try:
            database_controller = self._app_controller.get_database_controller()
            database = database_controller.get_active_database()
        except Exception as exc:
            self._set_status(f"DEBUG: Error reading active database: {exc}")
            return None

        if database is None:
            self._set_status("DEBUG: No active database")
            self._show_info(parent, "Highlight Rule Frequency", "No active database.")
            return None

        db_label = self._active_database_label(database_controller, database)
        source_name = Path(db_label).stem if db_label.endswith(".pgn") else db_label
        all_games = list(database.get_all_games())
        analyzed_games = [g for g in all_games if getattr(g, "analyzed", False)]
        if not analyzed_games:
            msg = (
                f"Database: {db_label}\n"
                f"Games: {len(all_games)}\n"
                "No analyzed games found (missing CARAAnalysisData)."
            )
            self._set_status("DEBUG: No analyzed games in active database")
            self._show_info(parent, "Highlight Rule Frequency", msg)
            return msg

        rules_service = GameHighlightRulesService.get_instance()
        catalog = list(list_builtin_rules())
        rule_meta = {meta.id: meta for meta in catalog}
        enabled_ids = {
            row.rule_id
            for row in rules_service.list_effective_rules()
            if row.enabled
        }

        hit_counts: Counter[str] = Counter()
        game_counts: Counter[str] = Counter()
        hit_locations: Dict[str, List[Any]] = defaultdict(list)
        scanned = 0
        skipped = 0
        total_highlights = 0

        progress = ProgressService.get_instance()
        summary_service = GameSummaryService(self.config)
        total = len(analyzed_games)

        try:
            progress.show_progress()
            progress.set_indeterminate(False)
            progress.set_progress(0)
            progress.set_status(
                f"Scanning highlight rules in {total} analyzed game(s)..."
            )
            QApplication.processEvents()

            for index, game in enumerate(analyzed_games):
                try:
                    moves = AnalysisDataStorageService.load_analysis_data(game)
                    if not moves:
                        skipped += 1
                    else:
                        summary = summary_service.calculate_summary(
                            moves, len(moves), game.result or ""
                        )
                        if summary is None:
                            skipped += 1
                        else:
                            scanned += 1
                            seen_in_game: set[str] = set()
                            for highlight in summary.highlights or []:
                                rule_type = (highlight.rule_type or "").strip()
                                if not rule_type:
                                    rule_type = "(missing_rule_type)"
                                hit_counts[rule_type] += 1
                                total_highlights += 1
                                seen_in_game.add(rule_type)
                                hit_locations[rule_type].append(
                                    (game, self._ref_ply_for_highlight(highlight))
                                )
                            for rule_type in seen_in_game:
                                game_counts[rule_type] += 1
                except Exception:
                    skipped += 1

                should_update = (
                    (index + 1) <= 10
                    or (index + 1) % 10 == 0
                    or (index + 1) == total
                )
                if should_update:
                    percent = int(((index + 1) / total) * 100)
                    progress.report_progress(
                        f"Scanning game {index + 1}/{total}...",
                        percent,
                    )
                    QApplication.processEvents()
        finally:
            progress.hide_progress()

        report = self._format_highlight_frequency_report(
            db_label=db_label,
            total_games=len(all_games),
            analyzed_games=len(analyzed_games),
            scanned=scanned,
            skipped=skipped,
            total_highlights=total_highlights,
            hit_counts=hit_counts,
            game_counts=game_counts,
            rule_meta=rule_meta,
            enabled_ids=enabled_ids,
        )
        self._copy_to_clipboard(report)
        self._set_status(
            f"DEBUG: Highlight rule frequency scanned ({scanned} games); "
            "report copied to clipboard"
        )

        table_rows = self._build_frequency_table_rows(
            scanned=scanned,
            hit_counts=hit_counts,
            game_counts=game_counts,
            hit_locations=hit_locations,
            rule_meta=rule_meta,
            enabled_ids=enabled_ids,
        )
        try:
            dialog = HighlightRuleFrequencyDialog(
                self.config,
                db_label=db_label,
                scanned=scanned,
                skipped=skipped,
                total_highlights=total_highlights,
                rows=table_rows,
                source_name=source_name,
                on_open_hits=lambda rule_id, src, hits: self._open_highlight_hits_in_search_results(
                    parent, rule_id, src, hits
                ),
                parent=parent,
            )
            dialog.exec()
        except Exception as exc:
            self._set_status(f"DEBUG: Frequency table failed ({exc}); report is on clipboard")
            self._show_info(
                parent,
                "Highlight Rule Frequency",
                "Scan finished; full report copied to clipboard.\n"
                f"(Could not open table dialog: {exc})",
            )
        return report

    @staticmethod
    def _ref_ply_for_highlight(highlight: Any) -> int:
        """Convert highlight move number/side to a board ply index."""
        move_number = int(getattr(highlight, "move_number", 0) or 0)
        if move_number <= 0:
            return 0
        if bool(getattr(highlight, "is_white", True)):
            return move_number * 2 - 1
        return move_number * 2

    def _build_frequency_table_rows(
        self,
        *,
        scanned: int,
        hit_counts: Counter[str],
        game_counts: Counter[str],
        hit_locations: Dict[str, List[Any]],
        rule_meta: Dict[str, Any],
        enabled_ids: set[str],
    ) -> List[Any]:
        from app.views.dialogs.highlight_rule_frequency_dialog import HighlightFrequencyRow

        catalog_ids = list(rule_meta.keys())
        unknown_ids = sorted(
            rid for rid in set(hit_counts) | set(game_counts) if rid not in rule_meta
        )
        all_ids = sorted(
            set(catalog_ids) | set(unknown_ids),
            key=lambda rid: (
                game_counts.get(rid, 0),
                hit_counts.get(rid, 0),
                rid,
            ),
        )
        rows: List[HighlightFrequencyRow] = []
        for rid in all_ids:
            meta = rule_meta.get(rid)
            display = meta.display_name if meta is not None else rid
            games_hit = game_counts.get(rid, 0)
            pct = (100.0 * games_hit / scanned) if scanned > 0 else 0.0
            locations = tuple(hit_locations.get(rid, []))
            rows.append(
                HighlightFrequencyRow(
                    rule_id=rid,
                    display_name=display,
                    enabled=rid in enabled_ids,
                    games_hit=games_hit,
                    games_pct=pct,
                    hits=hit_counts.get(rid, 0),
                    hit_locations=locations,
                )
            )
        return rows

    def _open_highlight_hits_in_search_results(
        self,
        parent: Any,
        rule_id: str,
        source_name: str,
        hits: List[Any],
    ) -> None:
        """Close overview already done by dialog; open Search Results at hit plies."""
        if not hits:
            self._set_status(f"DEBUG: No hits to open for {rule_id}")
            return
        if parent is None or not hasattr(parent, "database_panel"):
            self._set_status("DEBUG: Database panel not available for Search Results")
            return

        try:
            search_controller = self._app_controller.get_search_controller()
            items = [(game, source_name, int(ref_ply)) for game, ref_ply in hits]
            model = search_controller.create_search_results_model(items)
            tab_index = parent.database_panel.add_search_results_tab(model)
            parent.database_panel.tab_widget.setCurrentIndex(tab_index)
            if hasattr(parent, "_on_database_tab_changed"):
                parent._on_database_tab_changed(tab_index)
            self._set_status(
                f"DEBUG: Opened {len(items)} {rule_id} hit(s) in Search Results"
            )
        except Exception as exc:
            self._set_status(f"DEBUG: Failed to open Search Results: {exc}")

    def _active_database_label(self, database_controller: Any, database: Any) -> str:
        """Human-readable label for the active database."""
        try:
            identifier = database_controller.panel_model.find_database_by_model(database)
        except Exception:
            identifier = None
        if not identifier:
            return "active database"
        if identifier == "clipboard":
            return "Clipboard"
        return Path(identifier).name

    def _format_highlight_frequency_report(
        self,
        *,
        db_label: str,
        total_games: int,
        analyzed_games: int,
        scanned: int,
        skipped: int,
        total_highlights: int,
        hit_counts: Counter[str],
        game_counts: Counter[str],
        rule_meta: Dict[str, Any],
        enabled_ids: set[str],
    ) -> str:
        """Build the full clipboard report."""

        def is_rare(games_hit: int) -> bool:
            if scanned <= 0 or games_hit <= 0:
                return False
            return (games_hit / scanned) <= _RARE_GAME_FRACTION

        catalog_ids = list(rule_meta.keys())
        unknown_ids = sorted(
            rid for rid in set(hit_counts) | set(game_counts) if rid not in rule_meta
        )

        never_enabled = sorted(
            rid for rid in catalog_ids if rid in enabled_ids and game_counts.get(rid, 0) == 0
        )
        never_disabled = sorted(
            rid
            for rid in catalog_ids
            if rid not in enabled_ids and game_counts.get(rid, 0) == 0
        )
        rare_enabled = sorted(
            (
                rid
                for rid in catalog_ids
                if rid in enabled_ids and is_rare(game_counts.get(rid, 0))
            ),
            key=lambda rid: (game_counts.get(rid, 0), hit_counts.get(rid, 0), rid),
        )

        lines: List[str] = [
            "=== HIGHLIGHT RULE FREQUENCY (ACTIVE DATABASE) ===",
            f"Database: {db_label}",
            f"Games in DB: {total_games}",
            f"Analyzed games: {analyzed_games}",
            f"Scanned successfully: {scanned}",
            f"Skipped (no/invalid analysis): {skipped}",
            f"Total highlight instances: {total_highlights}",
            f"Rare threshold: ≤ {_RARE_GAME_FRACTION:.0%} of scanned games",
            "",
            "Counts are after summary filtering (phase limits, dedupe, exclusivity).",
            "",
        ]

        lines.append("--- Never hit (enabled rules) ---")
        if never_enabled:
            for rid in never_enabled:
                lines.append(f"  {self._rule_label(rid, rule_meta)}")
        else:
            lines.append("  (none)")
        lines.append("")

        lines.append("--- Rarely hit (enabled rules) ---")
        if rare_enabled:
            for rid in rare_enabled:
                lines.append(
                    f"  {self._rule_label(rid, rule_meta)}  "
                    f"games={game_counts.get(rid, 0)}  hits={hit_counts.get(rid, 0)}  "
                    f"({self._pct(game_counts.get(rid, 0), scanned)} of scanned games)"
                )
        else:
            lines.append("  (none)")
        lines.append("")

        if never_disabled:
            lines.append("--- Never hit (disabled rules; expected) ---")
            for rid in never_disabled:
                lines.append(f"  {self._rule_label(rid, rule_meta)}")
            lines.append("")

        lines.append("--- All rules by games hit (ascending) ---")
        all_ids = sorted(
            set(catalog_ids) | set(unknown_ids),
            key=lambda rid: (
                game_counts.get(rid, 0),
                hit_counts.get(rid, 0),
                rid,
            ),
        )
        for rid in all_ids:
            status = "enabled" if rid in enabled_ids else "disabled"
            if rid not in rule_meta:
                status = "unknown"
            lines.append(
                f"  {self._rule_label(rid, rule_meta)}  "
                f"[{status}]  games={game_counts.get(rid, 0)}  "
                f"hits={hit_counts.get(rid, 0)}  "
                f"({self._pct(game_counts.get(rid, 0), scanned)} of scanned games)"
            )
        lines.append("")
        lines.append("=== END REPORT (also copied to clipboard) ===")
        return "\n".join(lines)

    @staticmethod
    def _rule_label(rule_id: str, rule_meta: Dict[str, Any]) -> str:
        meta = rule_meta.get(rule_id)
        if meta is None:
            return rule_id
        return f"{meta.display_name} ({rule_id})"

    @staticmethod
    def _pct(part: int, whole: int) -> str:
        if whole <= 0:
            return "n/a"
        return f"{100.0 * part / whole:.2f}%"

    def _show_info(self, parent: Any, title: str, message: str) -> None:
        try:
            from app.views.dialogs.message_dialog import MessageDialog

            # MessageDialog renders as rich text; preserve line breaks.
            html = message.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html = html.replace("\n", "<br>")
            MessageDialog.show_information(self.config, title, html, parent)
        except Exception:
            pass

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
