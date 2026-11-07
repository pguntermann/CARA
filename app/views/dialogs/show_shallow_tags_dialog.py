"""Dialog that shows rows flagged as shallow or vague-lesson from the current corpus.

Save/Cancel model: edits are buffered in the row widgets until the user clicks
Save.  Save writes ``is_shallow=True`` / ``is_vague=True`` on every shown row
(per key membership), clears stale flags on entries classified-clean this run
(scoped to ``classified_keys`` only — entries the classifier didn't touch this
run are never modified), then calls ``controller.save_games(affected_games)``
to write game.pgn and mark each affected database unsaved.  Cancel and the
window close button discard all edits.

The Ignore checkbox (via ``_TagRowWidget(show_ignore_checkbox=True)``) lets
the user dismiss rows from future runs.  The row stays visible for the rest of
this session; it disappears on the next open.
"""

from __future__ import annotations

import html
from io import StringIO
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

import chess.pgn

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from datetime import datetime, timezone

from app.services.chess_log_storage_service import ChessLogStorageService
from app.utils.chess_log_best_move import resolve_best_move_for_path
from app.utils.help_icon import make_help_icon
from app.utils.pgn_variation_path import decode_path
from app.views.dialogs._tag_row_helpers import (
    game_header_text as _game_header_text,
    node_info as _node_info_fn,
    ply_for_path as _ply_for_path_fn,
)
from app.views.dialogs.message_dialog import MessageDialog
from app.views.dialogs.show_tags_dialog import _TagRowWidget, _PRESET_ORDER, _normalize_entries
from app.views.style.style_manager import StyleManager


def _format_check_run_date(utc_iso: str) -> str:
    """Convert a UTC ISO-8601 timestamp to a local-time display string.

    Accepts the "2026-10-30T14:23:45Z" format written by the controller.
    Returns a "%Y-%m-%d %H:%M" string in local time, or the raw string on
    parse failure.
    """
    try:
        dt_utc = datetime.strptime(utc_iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt_utc.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return utc_iso


class ShowShallowTagsDialog(QDialog):
    """Save/Cancel dialog listing rows flagged as shallow or vague-lesson.

    Args:
        config: application config dict.
        games: list of GameData objects in scope.
        controller: ChessLogController instance (not ChessLogChartsController).
        shallow_keys: set of (game, path_key, preset, cat) 4-tuples classified SHALLOW
            this run.  ``game`` is the GameData object (identity-keyed).
        vague_keys: set of (game, path_key, preset, cat) 4-tuples with a vague lesson
            this run (3x3 only).
        classified_keys: frozenset of (game, path_key, preset, cat) 4-tuples that were
            sent to the classifier AND received a parsed verdict this run.
            ``shallow_keys ∪ vague_keys ⊆ classified_keys``.  Only entries in this set
            may be modified by Save; entries outside it are never touched.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        games: List,
        controller,
        shallow_keys: Set,
        vague_keys: Set = frozenset(),
        classified_keys: FrozenSet = frozenset(),
        partial_notice: Optional[str] = None,
        source_label: str = "",
        model_label: str = "",
        check_run_info: Optional[Dict[str, str]] = None,
        window_title: str = "Check Logs",
        saved_mode: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._controller = controller
        self._shallow_keys = frozenset(shallow_keys)
        self._vague_keys = frozenset(vague_keys)
        self._classified_keys = classified_keys
        self._flagged_keys = self._shallow_keys | self._vague_keys
        self._partial_notice = partial_notice
        self._source_label = source_label
        self._model_label = model_label
        # check_run_info: {"model": "...", "date": "..."} written to each game's PGN on Save.
        # None in Saved-Logs mode (no new classification this session).
        self._check_run_info: Optional[Dict[str, str]] = check_run_info
        self._games_in_scope = list(games)
        # Saved mode = explicitly flagged by the caller (opened from Menu, not from a
        # live Check Logs run).  Only Saved mode shows the unchecked-count banner.
        # Using an explicit flag avoids treating a live run that parsed zero entries
        # (all-fail) as Saved mode.
        self._is_saved_mode: bool = saved_mode

        # Unchecked count: answers in scope that haven't been checked yet.
        # Only computed in Saved mode — in live mode the banner is never shown.
        self._unchecked_count: int = (
            self._controller.count_unchecked_answers(self._games_in_scope)
            if self._is_saved_mode else 0
        )

        self._load_config()

        # Build rows filtered to shallow_keys ∪ vague_keys.
        # Parallel lists: _rows (path_key, preset, entries), _row_games, _row_pgn_games.
        self._rows: List[Tuple[str, str, List[Dict[str, Any]]]] = []
        self._row_games: List = []
        self._row_pgn_games: List = []

        preset_rank = {p: i for i, p in enumerate(_PRESET_ORDER)}

        for game in games:
            pgn_game = self._parse_pgn(game)
            tags = controller.get_tags_for_game(game)

            game_rows: List[Tuple[int, int, str, str, List[Dict[str, Any]]]] = []
            for path_key, all_entries in tags.items():
                if not all_entries:
                    continue
                path = decode_path(path_key)
                if path is None:
                    continue

                by_preset: Dict[str, List[Dict[str, Any]]] = {}
                for entry in all_entries:
                    p = entry.get("preset", "")
                    by_preset.setdefault(p, []).append(entry)

                for preset, entries in by_preset.items():
                    if not self._moment_has_flag(game, path_key, preset):
                        continue
                    ply = _ply_for_path_fn(pgn_game, path)
                    rank = preset_rank.get(preset, len(_PRESET_ORDER))
                    game_rows.append((ply, rank, path_key, preset, entries))

            game_rows.sort(key=lambda r: (r[0], r[1]))
            for _, _, path_key, preset, entries in game_rows:
                self._rows.append((path_key, preset, entries))
                self._row_games.append(game)
                self._row_pgn_games.append(pgn_game)

        # Snapshot of the original entries for shown rows, keyed by row index.
        # Used in _on_save to skip rows that haven't changed.
        self._original_snapshot: Dict[int, List[Dict[str, Any]]] = {
            i: list(entries)
            for i, (pk, pr, entries) in enumerate(self._rows)
        }

        self._row_widgets: List[_TagRowWidget] = []
        self._rows_layout = None
        self._setup_ui()
        self.setWindowTitle(window_title)

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        dc = self._config.get("ui", {}).get("dialogs", {}).get("moment", {})
        self._bg_rgb = dc.get("background_color", [40, 40, 45])
        self._border_rgb = dc.get("border_color", [60, 60, 65])
        self._text_color_rgb = dc.get("text_color", [200, 200, 200])
        self._separator_rgb = dc.get("separator_color", [70, 70, 75])
        self._button_width = dc.get("button_width", 100)
        self._button_height = dc.get("button_height", 28)
        sh = self._config.get("ui", {}).get("dialogs", {}).get("shallow", {})
        self._btn_save_label = sh.get("button_save", "Save")
        self._btn_cancel_label = sh.get("button_cancel", "Cancel")
        banner = sh.get("unchecked_banner", {})
        self._banner_bg_rgb = banner.get("background_color", [50, 50, 55])
        self._banner_text_rgb = banner.get("text_color", [200, 200, 200])

    def get_unchecked_count(self) -> int:
        """Return the unchecked answer count computed at dialog open time."""
        return self._unchecked_count

    # ------------------------------------------------------------------
    # 4-tuple key helpers
    # ------------------------------------------------------------------

    def _moment_has_flag(self, game, pk: str, preset: str) -> bool:
        """True if any per-cat key for this moment is in flagged_keys."""
        if preset == "3x3":
            return any(
                (game, pk, "3x3", cat) in self._flagged_keys
                for cat in ("Why1", "Why2", "Why3", "Why4")
            )
        return (game, pk, preset, "") in self._flagged_keys

    def _is_shallow_key(self, game, pk: str, preset: str, cat: str) -> bool:
        if preset == "3x3":
            return (game, pk, "3x3", cat) in self._shallow_keys
        return (game, pk, preset, "") in self._shallow_keys

    def _is_vague_key(self, game, pk: str, preset: str, cat: str) -> bool:
        if preset == "3x3":
            return (game, pk, "3x3", cat) in self._vague_keys
        return (game, pk, preset, "") in self._vague_keys

    def _in_classified(self, game, pk: str, preset: str, cat: str) -> bool:
        if preset == "3x3":
            return (game, pk, "3x3", cat) in self._classified_keys
        return (game, pk, preset, "") in self._classified_keys

    def _stamp_entries(
        self, game, pk: str, preset: str, entries: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Return entries with is_shallow / is_vague stamped per 4-tuple key membership.

        For 3x3 entries whose Ignore is honoured but whose chip flag is absent from
        storage (e.g. dropped by a prior bug), the flag is inferred from cat so the
        chip always appears in the dialog.
        """
        result = []
        for e in entries:
            e_copy = dict(e)
            cat = e.get("cat", "")
            if self._is_shallow_key(game, pk, preset, cat):
                if preset != "3x3" or cat in ("Why1", "Why2", "Why3"):
                    e_copy["is_shallow"] = True
            if self._is_vague_key(game, pk, preset, cat):
                if preset != "3x3" or cat == "Why4":
                    e_copy["is_vague"] = True
            if preset == "3x3" and ChessLogStorageService.is_entry_ignore_honoured(e):
                if cat in ("Why1", "Why2", "Why3") and not e_copy.get("is_shallow"):
                    e_copy["is_shallow"] = True
                elif cat == "Why4" and not e_copy.get("is_vague"):
                    e_copy["is_vague"] = True
            result.append(e_copy)
        return result

    @staticmethod
    def _parse_pgn(game_data):
        try:
            pgn = getattr(game_data, "pgn", None)
            if not pgn:
                return None
            return chess.pgn.read_game(StringIO(pgn))
        except Exception:
            return None

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _make_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        sr, sg, sb = self._separator_rgb
        sep.setStyleSheet(f"background-color: rgb({sr},{sg},{sb}); border: none;")
        return sep

    def _make_game_header(self, game) -> QLabel:
        text = _game_header_text(game)
        label = QLabel(text)
        br, bg, bb = self._bg_rgb
        tr, tg, tb = self._text_color_rgb
        bor, bog, bob = self._border_rgb
        label.setStyleSheet(
            f"background-color: rgb({min(255, br+20)},{min(255, bg+20)},{min(255, bb+20)}); "
            f"color: rgb({tr},{tg},{tb}); "
            f"padding: 3px 8px; "
            f"border: 1px solid rgb({bor},{bog},{bob});"
        )
        return label

    def _show_help(self) -> None:
        help_text = (
            self._config.get("ui", {}).get("dialogs", {})
            .get("shallow", {}).get("help_text", "")
        )
        help_html = html.escape(help_text or "Check Logs help not configured.").replace('\n', '<br>')
        MessageDialog.show_information(self._config, "Check Logs — Help", help_html, self)

    def _setup_ui(self) -> None:
        # Read Chess Log display settings once (scale + arrow toggles).
        try:
            from app.services.user_settings_service import UserSettingsService as _USS
            from app.utils.miniature_board_scales import CHESS_LOG as _CL_SCALE_KEY
            from app.utils.miniature_board_arrows import (
                CHESS_LOG_PLAYED as _CL_PLAYED,
                CHESS_LOG_BEST_ALTERNATIVE as _CL_BEST,
            )
            _uss = _USS.get_instance()
            _board_scale = float(_uss.get_miniature_boards().get(_CL_SCALE_KEY, 1.25))
            _cl_arrows = _uss.get_miniature_board_arrows()
            _show_played = bool(_cl_arrows.get(_CL_PLAYED, True))
            _show_best = bool(_cl_arrows.get(_CL_BEST, True))
        except Exception:
            _board_scale = 1.25
            _show_played = True
            _show_best = True

        br, bg, bb = self._bg_rgb
        self.setStyleSheet(f"QDialog {{ background-color: rgb({br},{bg},{bb}); }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # Header row: title label + help icon
        tr, tg, tb = self._text_color_rgb
        hdr_row = QHBoxLayout()
        hdr_row.setSpacing(4)
        hdr_row.addStretch(1)
        help_btn = make_help_icon(
            self._config,
            tooltip="What do the chips mean?",
            text_color=self._text_color_rgb,
            on_click=self._show_help,
        )
        hdr_row.addWidget(help_btn)
        root.addLayout(hdr_row)

        if self._partial_notice:
            notice_lbl = QLabel(self._partial_notice)
            tr, tg, tb = self._text_color_rgb
            br2, bg2, bb2 = self._bg_rgb
            notice_lbl.setStyleSheet(
                f"color: rgb({tr},{tg},{tb}); "
                f"background-color: rgb({min(255,br2+15)},{min(255,bg2+10)},{min(255,bb2+5)}); "
                f"padding: 6px 8px; border-radius: 4px;"
            )
            notice_lbl.setWordWrap(True)
            root.addWidget(notice_lbl)

        if self._unchecked_count > 0:
            n = self._unchecked_count
            s = "s" if n != 1 else ""
            have = "haven't" if n != 1 else "hasn't"
            unchecked_lbl = QLabel(
                f"{n} note{s} {have} been checked yet "
                f"(new or edited since the last Check Logs). "
                f"Run Check Logs to check them."
            )
            bbr, bbg, bbb = self._banner_bg_rgb
            btr, btg, btb = self._banner_text_rgb
            unchecked_lbl.setStyleSheet(
                f"color: rgb({btr},{btg},{btb}); "
                f"background-color: rgb({bbr},{bbg},{bbb}); "
                f"padding: 6px 8px; border-radius: 4px;"
            )
            unchecked_lbl.setWordWrap(True)
            root.addWidget(unchecked_lbl)

        if not self._rows:
            tr, tg, tb = self._text_color_rgb
            lbl = QLabel("No flagged notes found.")
            lbl.setStyleSheet(f"color: rgb({tr},{tg},{tb});")
            root.addWidget(lbl)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            scroll.setFrameShape(QFrame.Shape.NoFrame)

            content = QWidget()
            self._rows_layout = QVBoxLayout(content)
            self._rows_layout.setSpacing(0)
            self._rows_layout.setContentsMargins(0, 0, 0, 0)
            self._rows_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            rows_layout = self._rows_layout

            last_game = None
            row_count = 0
            orphan_count = 0

            for i, (path_key, preset, entries) in enumerate(self._rows):
                game = self._row_games[i]
                pgn_game = self._row_pgn_games[i]

                fen, played_move, move_label, mover_is_black = _node_info_fn(pgn_game, path_key)
                if move_label == path_key:
                    orphan_count += 1
                    continue

                if game is not last_game:
                    rows_layout.addWidget(self._make_game_header(game))
                    last_game = game
                elif row_count > 0:
                    rows_layout.addWidget(self._make_separator())

                best_move = resolve_best_move_for_path(game, path_key, played_move, pgn_game)
                stamped = self._stamp_entries(game, path_key, preset, entries)
                row_widget = _TagRowWidget(
                    self._config,
                    preset,
                    stamped,
                    move_label,
                    fen or None,
                    played_move,
                    self._bg_rgb,
                    self._text_color_rgb,
                    show_ignore_checkbox=True,
                    best_move=best_move,
                    is_flipped=mover_is_black,
                    scale_factor=_board_scale,
                    show_played=_show_played,
                    show_best=_show_best,
                )
                rows_layout.addWidget(row_widget)
                self._row_widgets.append(row_widget)
                row_count += 1

            if orphan_count > 0:
                s = "s" if orphan_count != 1 else ""
                notice = QLabel(
                    f"Note: {orphan_count} tagged moment{s} could not be located "
                    f"— the game's moves may have been edited after tagging."
                )
                tr, tg, tb = self._text_color_rgb
                notice.setStyleSheet(
                    f"color: rgb({tr},{tg},{tb}); padding: 4px 0px;"
                )
                notice.setWordWrap(True)
                rows_layout.addWidget(notice)

            rows_layout.addStretch(1)
            scroll.setWidget(content)

            StyleManager.style_scroll_area(
                scroll,
                self._config,
                self._bg_rgb,
                self._border_rgb,
                border_radius=0,
                include_scroll_area_border=False,
            )

            screen = self.screen()
            max_h = int(screen.availableGeometry().height() * 0.85) if screen else 800
            scroll.setMinimumHeight(min(400, max_h))
            scroll.setMaximumHeight(max_h)
            root.addWidget(scroll)

        btn_row = QHBoxLayout()

        has_rows = bool(self._rows)

        self._copy_clipboard_btn = QPushButton("Copy to clipboard")
        self._copy_clipboard_btn.setAutoDefault(False)
        self._copy_clipboard_btn.setFixedHeight(self._button_height)
        self._copy_clipboard_btn.setEnabled(has_rows)
        self._copy_clipboard_btn.clicked.connect(self._on_copy_to_clipboard)
        btn_row.addWidget(self._copy_clipboard_btn)

        btn_row.addSpacing(6)

        self._export_pdf_btn = QPushButton("Export to PDF")
        self._export_pdf_btn.setAutoDefault(False)
        self._export_pdf_btn.setFixedHeight(self._button_height)
        self._export_pdf_btn.setEnabled(has_rows)
        self._export_pdf_btn.clicked.connect(self._on_export_pdf)
        btn_row.addWidget(self._export_pdf_btn)

        btn_row.addStretch(1)
        self._cancel_btn = QPushButton(self._btn_cancel_label)
        self._cancel_btn.setAutoDefault(False)
        self._cancel_btn.setFixedSize(self._button_width, self._button_height)
        self._cancel_btn.clicked.connect(self.reject)

        self._save_btn = QPushButton(self._btn_save_label)
        self._save_btn.setDefault(True)
        self._save_btn.setAutoDefault(True)
        self._save_btn.setFixedSize(self._button_width, self._button_height)
        self._save_btn.clicked.connect(self._on_save)

        btn_row.addWidget(self._cancel_btn)
        btn_row.addSpacing(6)
        btn_row.addWidget(self._save_btn)
        root.addLayout(btn_row)

        StyleManager.style_buttons(
            [self._copy_clipboard_btn, self._export_pdf_btn, self._cancel_btn, self._save_btn],
            self._config,
            self._bg_rgb,
            self._border_rgb,
        )

        self.setMinimumWidth(800)
        from app.views.widgets.themed_dialog_size_grip import install_themed_dialog_resize_grip
        install_themed_dialog_resize_grip(self, self._config)

    def _build_tag_groups(self):
        """Build game-grouped TagRowSnapshot lists from current widget state."""
        tag_groups = []
        current_game = None
        current_rows = []
        current_header = None
        for i, row_widget in enumerate(self._row_widgets):
            game = self._row_games[i]
            if game is not current_game:
                if current_rows:
                    tag_groups.append({"header": current_header, "rows": current_rows})
                current_game = game
                current_rows = []
                current_header = _game_header_text(game)
            current_rows.append(row_widget.snapshot())
        if current_rows:
            tag_groups.append({"header": current_header, "rows": current_rows})
        return tag_groups

    def _resolve_model_generated(self):
        """Return (model_label, generated_at) for the PDF/clipboard header.

        Live run: from check_run_info. Saved mode: from stored _check_run on games.
        """
        generated_at = ""
        model_label = self._model_label
        if self._check_run_info:
            model_label = self._check_run_info.get("model", self._model_label)
            raw_ts = self._check_run_info.get("date", "")
            generated_at = _format_check_run_date(raw_ts)
        else:
            seen_game_ids: set = set()
            seen_runs: list = []
            for game in self._row_games:
                if id(game) in seen_game_ids:
                    continue
                seen_game_ids.add(id(game))
                cr = self._controller.get_check_run_for_game(game)
                if cr and cr.get("model") and cr.get("date"):
                    seen_runs.append((cr["model"], cr["date"]))
            if not seen_runs:
                model_label = "Saved Check Logs results"
            elif len(set(seen_runs)) == 1:
                model_label = seen_runs[0][0]
                generated_at = _format_check_run_date(seen_runs[0][1])
            else:
                latest_model, latest_date = max(seen_runs, key=lambda r: r[1])
                model_label = f"{latest_model} (mixed runs)"
                generated_at = _format_check_run_date(latest_date)
        return model_label, generated_at

    def _on_copy_to_clipboard(self) -> None:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QMimeData
        from app.services.chess_log_html_service import ChessLogHTMLService
        tag_groups = self._build_tag_groups()
        model_label, generated_at = self._resolve_model_generated()
        svc = ChessLogHTMLService(self._config)
        mime = QMimeData()
        mime.setHtml(svc.check_logs_html(
            tag_groups,
            source_label=self._source_label,
            model_label=model_label,
            generated_at=generated_at,
        ))
        mime.setText(svc.check_logs_plain(
            tag_groups,
            source_label=self._source_label,
            model_label=model_label,
            generated_at=generated_at,
        ))
        QApplication.clipboard().setMimeData(mime)

    def _on_export_pdf(self) -> None:
        from pathlib import Path
        from PyQt6.QtWidgets import QFileDialog
        from app.services.chess_log_pdf_service import (
            ChessLogPDFService,
            default_chess_log_tags_pdf_filename,
        )
        suggested = default_chess_log_tags_pdf_filename(is_shallow_only=True)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export to PDF", suggested, "PDF Files (*.pdf)"
        )
        if not path:
            return
        model_label, generated_at = self._resolve_model_generated()
        ChessLogPDFService(self._config).export_tags(
            Path(path), self._build_tag_groups(),
            is_shallow_only=True,
            source_label=self._source_label,
            model_label=model_label,
            generated_at=generated_at,
        )

    def _on_save(self) -> None:
        affected: set = set()

        # a) Shown rows: stamp is_shallow / is_vague and check_hash per key membership.
        for i, (path_key, preset, _) in enumerate(self._rows):
            row_widget = self._row_widgets[i]
            game = self._row_games[i]
            user_entries = row_widget.get_current_entries()
            new_entries = self._stamp_entries(game, path_key, preset, user_entries)
            original_row = self._original_snapshot.get(i, [])
            # Clear is_shallow/is_vague for entries whose text was edited in this session.
            # _stamp_entries stamps based on key membership without checking text changes;
            # this pass applies clear_verdict_if_text_changed so edited answers lose
            # their chip (the classifier's verdict was for the old text).
            new_entries = self._clear_stale_flags_after_edit(new_entries, original_row, preset)
            # Stamp check_hash on entries that were classified this run AND whose
            # text has not been edited in this dialog session.
            new_entries = self._stamp_check_hashes_shown(
                new_entries, original_row, game, path_key, preset
            )
            original = original_row
            orig_with_flags = self._stamp_entries(game, path_key, preset, original)
            flags_missing = any(
                (
                    self._is_shallow_key(game, path_key, preset, e.get("cat", ""))
                    and not e.get("is_shallow")
                ) or (
                    self._is_vague_key(game, path_key, preset, e.get("cat", ""))
                    and not e.get("is_vague")
                )
                for e in original
            )
            # Repair: if storage has a honoured-Ignore entry that is missing its chip
            # flag (dropped by the stale-clear bug), force a save so the C1 inference
            # in _stamp_entries writes the flag back.
            inference_repair_needed = preset == "3x3" and any(
                ChessLogStorageService.is_entry_ignore_honoured(e)
                and not e.get("is_shallow") and not e.get("is_vague")
                for e in original
            )
            if _normalize_entries(new_entries) != _normalize_entries(orig_with_flags) or flags_missing or inference_repair_needed:
                self._controller.replace_entries_at_path_for_game(
                    game, path_key, preset, new_entries
                )
                affected.add(game)

        # b) Classified-but-not-shown entries: clear stale is_shallow/is_vague and
        #    stamp check_hash.  Scoped to _classified_keys — never touches unparsed,
        #    ignored, or empty-why entries.  Skips entries already handled by Phase a
        #    (those whose per-cat key is in _flagged_keys).
        for game in self._games_in_scope:
            tags = self._controller.get_tags_for_game(game)
            for path_key, entries in tags.items():
                by_preset: Dict[str, List[Dict[str, Any]]] = {}
                for e in entries:
                    by_preset.setdefault(e.get("preset", ""), []).append(e)
                for preset, preset_entries in by_preset.items():
                    if preset == "3x3":
                        # Per-entry processing for 3x3
                        new_list = []
                        changed = False
                        for e in preset_entries:
                            cat = e.get("cat", "")
                            in_cls = self._in_classified(game, path_key, preset, cat)
                            in_flag = (
                                self._is_shallow_key(game, path_key, preset, cat) or
                                self._is_vague_key(game, path_key, preset, cat)
                            )
                            # Never stale-clear an entry whose Ignore is still honoured —
                            # the user's dismiss is intentional and must not be undone.
                            ignore_honoured = ChessLogStorageService.is_entry_ignore_honoured(e)
                            if in_cls and not in_flag:
                                e_copy = dict(e)
                                # Stale flag clear
                                if not ignore_honoured and (e.get("is_shallow") or e.get("is_vague")):
                                    # Also clear ignore_shallow/ignore_text_hash: editing the text
                                    # (which caused the hash mismatch) invalidates the Ignore.
                                    # Never leave ignore_shallow=True with no chip flag.
                                    for k in ("is_shallow", "is_vague", "ignore_shallow", "ignore_text_hash"):
                                        e_copy.pop(k, None)
                                    changed = True
                                # check_hash: stamp on non-ignored entries with non-blank why.
                                # In-flag entries (shown in Phase a) are excluded so we don't
                                # re-stamp entries whose text may have been edited by the user.
                                if not ignore_honoured:
                                    why = (e_copy.get("why") or "").strip()
                                    if why:
                                        new_hash = ChessLogStorageService.compute_check_hash(why)
                                        if e_copy.get("check_hash") != new_hash:
                                            e_copy["check_hash"] = new_hash
                                            changed = True
                                new_list.append(e_copy)
                            else:
                                new_list.append(e)
                        if changed:
                            self._controller.replace_entries_at_path_for_game(
                                game, path_key, preset, new_list
                            )
                            affected.add(game)
                    else:
                        # Per-preset processing for CLAMP/CCT
                        key_4 = (game, path_key, preset, "")
                        if key_4 not in self._classified_keys:
                            continue
                        if self._moment_has_flag(game, path_key, preset):
                            continue  # shown in Phase a
                        new_list = []
                        changed = False
                        for e in preset_entries:
                            ignore_honoured = ChessLogStorageService.is_entry_ignore_honoured(e)
                            e_copy = dict(e)
                            # Stale flag clear
                            if not ignore_honoured and (e.get("is_shallow") or e.get("is_vague")):
                                for k in ("is_shallow", "is_vague"):
                                    e_copy.pop(k, None)
                                changed = True
                            # check_hash: stamp on non-ignored entries with non-blank why
                            if not ignore_honoured:
                                why = (e_copy.get("why") or "").strip()
                                if why:
                                    new_hash = ChessLogStorageService.compute_check_hash(why)
                                    if e_copy.get("check_hash") != new_hash:
                                        e_copy["check_hash"] = new_hash
                                        changed = True
                            new_list.append(e_copy)
                        if changed:
                            self._controller.replace_entries_at_path_for_game(
                                game, path_key, preset, new_list
                            )
                            affected.add(game)

        # c) Write _check_run to every game touched by this Check Logs run.
        if self._check_run_info and self._classified_keys:
            classified_games: set = {key[0] for key in self._classified_keys}
            for cg in classified_games:
                self._controller.set_check_run_for_game(cg, self._check_run_info)
                affected.add(cg)

        if affected:
            self._controller.save_games(affected)
        self.accept()

    def _stamp_check_hashes_shown(
        self,
        new_entries: List[Dict[str, Any]],
        original_entries: List[Dict[str, Any]],
        game: Any,
        path_key: str,
        preset: str,
    ) -> List[Dict[str, Any]]:
        """Stamp check_hash on shown-row entries that were classified AND text is unchanged.

        Only entries in _classified_keys receive check_hash.  Entries whose text
        was edited in this session are excluded (an edited answer is unchecked).
        Ignored entries are excluded (their honoured Ignore already counts as checked).
        """
        if not self._classified_keys:
            return new_entries

        # Build original why lookup by cat (for comparison).
        orig_by_cat: Dict[str, str] = {}
        for e in original_entries:
            cat = e.get("cat", "")
            orig_by_cat[cat] = (e.get("why") or "").strip()

        result = []
        for e in new_entries:
            cat = e.get("cat", "")
            clamp_cat = cat if preset == "3x3" else ""
            in_cls = self._in_classified(game, path_key, preset, clamp_cat)
            ignore_honoured = ChessLogStorageService.is_entry_ignore_honoured(e)
            if in_cls and not ignore_honoured:
                why = (e.get("why") or "").strip()
                if why:
                    # Only stamp when the text hasn't changed from the original
                    # (edited answers must remain unchecked after Save).
                    orig_key = cat if preset == "3x3" else next(iter(orig_by_cat), "")
                    original_why = orig_by_cat.get(orig_key, "")
                    if why == original_why:
                        e = dict(e)
                        e["check_hash"] = ChessLogStorageService.compute_check_hash(why)
            result.append(e)
        return result

    def _clear_stale_flags_after_edit(
        self,
        new_entries: List[Dict[str, Any]],
        original_entries: List[Dict[str, Any]],
        preset: str,
    ) -> List[Dict[str, Any]]:
        """Clear is_shallow/is_vague/ignore fields from entries whose why text was edited.

        _stamp_entries stamps flags based on key membership without checking for
        text changes — this post-pass re-applies clear_verdict_if_text_changed so
        that editing an answer drops its chip (the verdict was for the old text).
        check_hash is intentionally NOT cleared: a stored check_hash lets the user
        restore the exact original text and have it count as checked again without
        re-running Check Logs.
        """
        if not original_entries:
            return new_entries

        def _clear_stale(entry: Dict[str, Any], orig_why: str) -> Dict[str, Any]:
            return ChessLogStorageService.clear_verdict_if_text_changed(entry, orig_why)

        if preset == "3x3":
            orig_why_by_cat = {
                e.get("cat", ""): (e.get("why") or "").strip()
                for e in original_entries
            }
            return [
                _clear_stale(e, orig_why_by_cat.get(e.get("cat", ""), ""))
                for e in new_entries
            ]
        orig_why = (original_entries[0].get("why") or "").strip()
        return [_clear_stale(e, orig_why) for e in new_entries]
