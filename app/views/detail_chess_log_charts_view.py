"""Chess Log Charts detail-panel tab (§5.1 + §5.2).

Layout: single QScrollArea wrapping the entire pane, mirroring Player Stats.
Inside (top to bottom):
  [Data Source + Player selector rows]
  [Placeholder label OR stacked ChessLogCategoryChartWidget instances (one per preset)]
  [Narrative panel: Generate button, QTextEdit, "Also flagged" collapsible]

Placeholder text is shown at the chart area when no data is present.
The narrative panel is disabled (with an explanatory hint) when no LLM is configured.
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.controllers.chess_log_charts_controller import (
    DEFAULT_NARRATIVE_TOKEN_LIMIT,
    SOURCE_LABELS,
    ChessLogChartsController,
    CheckLogMoment,
)
from app.views.dialogs.message_dialog import MessageDialog
from app.services.ai_service import TokenUsage
from app.services.chess_log_narrative_service import sanitize_narrative_markdown
from app.services.logging_service import LoggingService
from app.services.chess_log_stats_service import ChessLogPresetSeries
from app.services.chess_log_storage_service import ChessLogStorageService
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.views.style.style_manager import StyleManager
from app.views.widgets.busy_spinner import BusySpinner
from app.views.widgets.chess_log_category_chart_widget import ChessLogCategoryChartWidget


_SOURCE_LABELS = SOURCE_LABELS


class DetailChessLogChartsView(QWidget):
    """Chess Log Charts tab view."""

    def __init__(
        self,
        config: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._controller: Optional[ChessLogChartsController] = None
        self._chart_widgets: List[ChessLogCategoryChartWidget] = []
        self._content_layout = None
        # No result copies live here: the narrative, the Check Logs result, the player
        # and the data source are all read from the controller on demand.
        # Partial-fail notice from shallow_partial signal; consumed by the next
        # shallow_ready handler to show inline in the dialog rather than a
        # separate message dialog.
        self._pending_partial_message: Optional[str] = None

        self._build_ui()
        self._apply_styling()

    # ------------------------------------------------------------------
    # Controller wiring
    # ------------------------------------------------------------------

    def set_controller(self, controller: ChessLogChartsController) -> None:
        if self._controller:
            try:
                self._controller.charts_updated.disconnect(self._on_charts_updated)
                self._controller.charts_unavailable.disconnect(self._on_charts_unavailable)
                self._controller.charts_skipped.disconnect(self._on_charts_skipped)
                self._controller.charts_loading.disconnect(self._on_charts_loading)
                self._controller.players_ready.disconnect(self._on_players_ready)
                self._controller.player_selection_cleared.disconnect(self._reset_player_selection)
                self._controller.narrative_ready.disconnect(self._on_narrative_ready)
                self._controller.narrative_failed.disconnect(self._on_narrative_failed)
                self._controller.shallow_ready.disconnect(self._on_shallow_ready)
                self._controller.shallow_failed.disconnect(self._on_shallow_failed)
                self._controller.shallow_partial.disconnect(self._on_shallow_partial)
                self._controller.ai_configured_changed.disconnect(self._on_ai_configured_changed)
                self._controller.ai_model_changed.disconnect(self._on_ai_model_changed)
                self._controller.results_invalidated.disconnect(self._clear_narrative_and_check_logs)
            except RuntimeError:
                pass

        self._controller = controller
        if not controller:
            return

        controller.charts_updated.connect(self._on_charts_updated)
        controller.charts_unavailable.connect(self._on_charts_unavailable)
        controller.charts_skipped.connect(self._on_charts_skipped)
        controller.charts_loading.connect(self._on_charts_loading)
        controller.players_ready.connect(self._on_players_ready)
        controller.player_selection_cleared.connect(self._reset_player_selection)
        controller.narrative_ready.connect(self._on_narrative_ready)
        controller.narrative_failed.connect(self._on_narrative_failed)
        controller.shallow_ready.connect(self._on_shallow_ready)
        controller.shallow_failed.connect(self._on_shallow_failed)
        controller.shallow_partial.connect(self._on_shallow_partial)
        controller.ai_configured_changed.connect(self._on_ai_configured_changed)
        controller.ai_model_changed.connect(self._on_ai_model_changed)
        controller.results_invalidated.connect(self._clear_narrative_and_check_logs)

        # Restore the controller's token limit (survives a theme rebuild); don't write it back.
        self._tokens_spin.blockSignals(True)
        self._tokens_spin.setValue(controller.get_narrative_token_limit())
        self._tokens_spin.blockSignals(False)

        self._restore_selectors(controller)

        self._refresh_ai_state()

        # Re-draw the controller's latest chart outcome (no refresh is requested).
        for kind, value in controller.get_last_chart_events():
            if kind == "updated":
                self._on_charts_updated(value)
            elif kind == "unavailable":
                self._on_charts_unavailable(value)
            elif kind == "skipped":
                self._on_charts_skipped(value)

        # Re-display any results cached in the controller (e.g. after a theme rebuild).
        # Called after signal connections so _on_narrative_ready/_refresh_ai_state work.
        narrative, flags, usage = controller.get_last_narrative_result()
        if narrative:
            self._on_narrative_ready(narrative, flags, usage)
        shallow_keys, vague_keys, shallow_usage = controller.get_last_shallow_result()
        if shallow_keys or vague_keys or shallow_usage:
            self._shallow_token_label.setText(self._format_token_usage(shallow_usage))
            self._refresh_ai_state()

    def _restore_selectors(self, controller: ChessLogChartsController) -> None:
        """Show the controller's source, player and timeout; signals blocked so nothing reselects."""
        self._timeout_spin.blockSignals(True)
        self._timeout_spin.setValue(controller.get_narrative_timeout_seconds())
        self._timeout_spin.blockSignals(False)

        self._source_combo.blockSignals(True)
        self._source_combo.setCurrentIndex(controller.get_source_selection())
        self._source_combo.blockSignals(False)

        player = controller.get_player_display_name() if controller.has_player_selected() else ""
        self._player_combo.blockSignals(True)
        self._player_combo.clear()
        for name, count in controller.get_last_players():
            self._player_combo.addItem(f"{name} ({count} logged)", name)
        idx = self._player_combo.findData(player) if player else -1
        if player and idx < 0:
            # List not delivered yet; players_ready replaces this item when it arrives.
            self._player_combo.addItem(player, player)
            idx = self._player_combo.count() - 1
        self._player_combo.setCurrentIndex(idx)
        self._player_combo.blockSignals(False)

    def refresh_ai_state(self) -> None:
        """Called externally when AI model settings change."""
        self._refresh_ai_state()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )

        content_widget = QWidget()
        content_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        content_widget.setMinimumWidth(0)

        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(8)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._content_layout = content_layout

        content_layout.addWidget(self._build_selector())

        # Placeholder + stacked charts in one container (no inner scroll area)
        self._placeholder = QLabel("Select a player to view Chess Log data.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._placeholder.setVisible(True)

        self._charts_container = QWidget()
        self._charts_layout = QVBoxLayout(self._charts_container)
        self._charts_layout.setContentsMargins(0, 0, 0, 0)
        self._charts_layout.setSpacing(12)
        self._charts_container.setVisible(False)

        self._skip_note = QLabel()
        self._skip_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._skip_note.setWordWrap(False)
        self._skip_note.setVisible(False)

        content_layout.addWidget(self._placeholder)
        content_layout.addWidget(self._charts_container)
        content_layout.addWidget(self._skip_note)
        content_layout.addWidget(self._build_narrative_panel())
        content_layout.addStretch()

        self._scroll_area.setWidget(content_widget)
        root.addWidget(self._scroll_area)

    def _build_selector(self) -> QWidget:
        from PyQt6.QtGui import QFont
        selector_font = QFont(
            resolve_font_family("Helvetica Neue"),
            int(scale_font_size(11)),
        )

        frame = QFrame()
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(8, 6, 8, 6)
        outer.setSpacing(4)

        label_names = ("Data Source:", "Player:")
        fm = QFontMetrics(selector_font)
        label_width = max(fm.horizontalAdvance(s) for s in label_names) + 8

        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        source_label = QLabel("Data Source:")
        source_label.setFont(selector_font)
        source_label.setMinimumWidth(label_width)
        source_row.addWidget(source_label)
        self._source_combo = QComboBox()
        self._source_combo.setFont(selector_font)
        self._source_combo.setEditable(True)
        self._source_combo.lineEdit().setReadOnly(True)
        for label in _SOURCE_LABELS:
            self._source_combo.addItem(label)
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)
        source_row.addWidget(self._source_combo, 1)
        source_row.addStretch()
        outer.addLayout(source_row)

        player_row = QHBoxLayout()
        player_row.setSpacing(8)
        player_label = QLabel("Player:")
        player_label.setFont(selector_font)
        player_label.setMinimumWidth(label_width)
        player_row.addWidget(player_label)
        self._player_combo = QComboBox()
        self._player_combo.setFont(selector_font)
        self._player_combo.setEditable(True)
        self._player_combo.lineEdit().setReadOnly(True)
        self._player_combo.lineEdit().setPlaceholderText("Select player")
        self._player_combo.setCurrentIndex(-1)
        self._player_combo.currentIndexChanged.connect(self._on_player_changed)
        player_row.addWidget(self._player_combo, 1)
        outer.addLayout(player_row)

        return frame

    def _build_narrative_panel(self) -> QWidget:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._ai_hint = QLabel()
        self._ai_hint.setWordWrap(True)
        self._ai_hint.setVisible(True)
        self._ai_hint.setTextFormat(Qt.TextFormat.RichText)
        self._ai_hint.setOpenExternalLinks(False)
        self._ai_hint.linkActivated.connect(self._on_ai_hint_link_clicked)
        layout.addWidget(self._ai_hint)

        # Model / timeout / tokens row (mirrors AI Summary's input row, no reactive layout).
        model_row = QHBoxLayout()
        model_row.setSpacing(8)

        model_label = QLabel("Model:")
        model_row.addWidget(model_label)
        self._model_combo = QComboBox()
        self._model_combo.setEditable(False)
        self._model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._model_combo.currentTextChanged.connect(self._on_narrative_model_changed)
        model_row.addWidget(self._model_combo, 1)

        timeout_label = QLabel("Timeout (s):")
        model_row.addWidget(timeout_label)
        self._timeout_spin = QSpinBox()
        self._timeout_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._timeout_spin.setRange(10, 600)
        self._timeout_spin.setValue(60)
        self._timeout_spin.setFixedWidth(56)
        self._timeout_spin.valueChanged.connect(self._on_narrative_timeout_changed)
        model_row.addWidget(self._timeout_spin)

        tokens_label = QLabel("Tokens:")
        model_row.addWidget(tokens_label)
        self._tokens_spin = QSpinBox()
        self._tokens_spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self._tokens_spin.setRange(256, 99999)
        self._tokens_spin.setSingleStep(1000)
        self._tokens_spin.setValue(DEFAULT_NARRATIVE_TOKEN_LIMIT)  # GFM tables render natively in Qt 6.4+; requirements.txt pins 6.11
        self._tokens_spin.setFixedWidth(80)
        self._tokens_spin.valueChanged.connect(self._on_narrative_tokens_changed)
        model_row.addWidget(self._tokens_spin)

        layout.addLayout(model_row)

        shallow_row = QHBoxLayout()
        self._show_shallow_btn = QPushButton("Check Logs")
        self._show_shallow_btn.clicked.connect(self._on_show_shallow_clicked)
        self._show_shallow_btn.setEnabled(False)
        shallow_row.addWidget(self._show_shallow_btn)
        _spinner_rgb = (
            self._config.get("ui", {}).get("panels", {}).get("detail", {})
            .get("chess_log_charts", {}).get("colors", {})
            .get("spinner_color", [180, 180, 200])
        )
        self._shallow_spinner = BusySpinner(color=QColor(*_spinner_rgb), size=18, line_width=2)
        shallow_row.addWidget(self._shallow_spinner)
        self._shallow_status_label = QLabel("Checking logs…")
        self._shallow_status_label.setVisible(False)
        shallow_row.addWidget(self._shallow_status_label)
        shallow_row.addStretch()
        layout.addLayout(shallow_row)

        self._shallow_token_label = QLabel("")
        self._shallow_token_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self._shallow_token_label)

        self._shallow_hint = QLabel("")
        self._shallow_hint.setWordWrap(True)
        self._shallow_hint.setVisible(False)
        layout.addWidget(self._shallow_hint)

        btn_row = QHBoxLayout()
        self._generate_btn = QPushButton("Generate Narrative Summary")
        self._generate_btn.clicked.connect(self._on_generate_clicked)
        self._generate_btn.setEnabled(False)
        btn_row.addWidget(self._generate_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._narrative_edit = QTextEdit()
        self._narrative_edit.setReadOnly(True)
        self._narrative_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self._narrative_edit.setPlaceholderText(
            "Click 'Generate Narrative Summary' to get an AI-written reflection on your Chess Log moments."
        )
        self._narrative_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._narrative_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._narrative_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._narrative_edit.document().contentsChanged.connect(self._fit_narrative_height)
        layout.addWidget(self._narrative_edit)

        self._narrative_token_label = QLabel("")
        self._narrative_token_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self._narrative_token_label)

        self._flagged_box = QGroupBox("Also flagged")
        self._flagged_box.setCheckable(True)
        self._flagged_box.setChecked(False)
        flagged_layout = QVBoxLayout(self._flagged_box)
        self._flagged_label = QLabel()
        self._flagged_label.setWordWrap(True)
        self._flagged_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        flagged_layout.addWidget(self._flagged_label)
        self._flagged_box.setVisible(False)
        layout.addWidget(self._flagged_box)

        frame.setProperty("section_name", "narrative")
        return frame

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _apply_styling(self) -> None:
        panel_cfg = self._config.get("ui", {}).get("panels", {}).get("detail", {})
        cl_cfg = panel_cfg.get("chess_log_charts", {})
        colors = cl_cfg.get("colors", {})

        bg = colors.get("background", [28, 28, 33])
        text = colors.get("text", [210, 210, 220])
        input_bg = colors.get("input_background", [38, 38, 44])
        border = colors.get("border", [60, 60, 68])
        hint_text = colors.get("hint_text", [150, 150, 160])
        link = colors.get("link", [100, 150, 255])

        bg_s = f"rgb({bg[0]},{bg[1]},{bg[2]})"
        text_s = f"rgb({text[0]},{text[1]},{text[2]})"
        input_s = f"rgb({input_bg[0]},{input_bg[1]},{input_bg[2]})"
        border_s = f"rgb({border[0]},{border[1]},{border[2]})"
        hint_s = f"rgb({hint_text[0]},{hint_text[1]},{hint_text[2]})"
        link_s = f"rgb({link[0]},{link[1]},{link[2]})"

        self.setStyleSheet(f"""
            QWidget {{ background-color: {bg_s}; color: {text_s}; }}
            QFrame {{ border: 1px solid {border_s}; border-radius: 4px; }}
            QScrollArea {{ border: none; }}
            QComboBox {{
                background-color: {input_s}; color: {text_s};
                border: 1px solid {border_s}; border-radius: 3px; padding: 2px 6px;
            }}
            QComboBox QLineEdit {{
                background-color: {input_s}; color: {text_s};
                border: none; padding: 0px 2px;
            }}
            QLabel {{ border: none; color: {text_s}; }}
            QPushButton {{
                background-color: {input_s}; color: {text_s};
                border: 1px solid {border_s}; border-radius: 4px; padding: 4px 12px;
            }}
            QPushButton:disabled {{ color: {hint_s}; }}
            QTextEdit {{
                background-color: {input_s}; color: {text_s};
                border: 1px solid {border_s}; border-radius: 4px;
            }}
            QGroupBox {{ border: 1px solid {border_s}; border-radius: 4px; margin-top: 8px; }}
            QGroupBox::title {{ color: {text_s}; subcontrol-origin: margin; left: 8px; }}
        """)
        token_label_cfg = cl_cfg.get("token_usage_label", {})
        token_color = token_label_cfg.get("color")
        token_font_size = token_label_cfg.get("font_size", 10)
        if isinstance(token_color, list) and len(token_color) >= 3:
            token_color_s = f"rgb({token_color[0]},{token_color[1]},{token_color[2]})"
        else:
            token_color_s = hint_s
        token_label_style = f"color: {token_color_s}; font-size: {token_font_size}pt; border: none;"
        self._narrative_token_label.setStyleSheet(token_label_style)
        self._shallow_token_label.setStyleSheet(token_label_style)

        self._ai_hint.setStyleSheet(f"color: {hint_s}; border: none;")
        self._ai_hint.setText(
            f'Configure an AI provider in AI Summary → '
            f'<a href="ai-model-settings" style="color: {link_s}; text-decoration: underline;">'
            f'AI Model Settings</a> to enable narrative summaries.'
        )
        self._shallow_hint.setStyleSheet(f"color: {hint_s}; border: none;")
        self._placeholder.setStyleSheet(f"color: {hint_s}; border: none;")
        self._skip_note.setStyleSheet(f"color: {hint_s}; border: none;")

    def _on_ai_hint_link_clicked(self, url: str) -> None:
        if url != "ai-model-settings":
            return
        w = self.window()
        if hasattr(w, "_show_ai_model_settings"):
            w._show_ai_model_settings()

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_source_changed(self, index: int) -> None:
        self._reset_player_selection()
        if self._controller:
            self._controller.set_source_selection(index)

    def _on_player_changed(self, index: int) -> None:
        self._refresh_ai_state()
        if not self._controller:
            return
        if index < 0:
            self._controller.clear_player_selection()
            return
        raw_name = self._player_combo.itemData(index)
        if raw_name:
            self._controller.set_player_selection(raw_name)

    def _on_generate_clicked(self) -> None:
        if self._controller:
            self._generate_btn.setEnabled(False)
            self._narrative_edit.setPlainText("Generating…")
            self._narrative_token_label.setText("")
            self._controller.request_narrative()

    def _on_charts_loading(self) -> None:
        self._clear_charts()
        self._placeholder.setVisible(False)
        self._charts_container.setVisible(False)

    def _on_charts_updated(self, data: Dict[str, ChessLogPresetSeries]) -> None:
        self._clear_charts()
        if not data:
            self._show_placeholder()
            return
        self._placeholder.setVisible(False)
        self._charts_container.setVisible(True)
        for preset in sorted(data):
            widget = ChessLogCategoryChartWidget(config=self._config)
            widget.set_series(data[preset], colors=self._cat_colors_for_preset(preset))
            widget.setProperty("section_name", f"chart_{preset}")
            self._charts_layout.addWidget(widget)
            self._chart_widgets.append(widget)

    def _on_charts_unavailable(self, reason: str) -> None:
        self._clear_charts()
        if reason == "no_player":
            self._set_placeholder_text("Select a player to view Chess Log data.")
        elif reason == "no_source":
            self._set_placeholder_text("Select a Data Source to view Chess Log data.")
        elif reason == "no_chartable_preset":
            self._set_placeholder_text(
                "No chart data for this selection.\n"
                "3x3 moments are not shown in charts — use Generate Narrative Summary below."
            )
        elif reason.startswith("no_dated_clamp_cct:"):
            parts = reason.split(":")
            n = int(parts[1]) if len(parts) > 1 else 0
            has_3x3 = len(parts) > 2 and parts[2] == "1"
            noun = "game" if n == 1 else "games"
            verb = "has" if n == 1 else "have"
            msg = (
                f"No chart data for this selection.\n"
                f"{n} {noun} with CLAMP/CCT moments {verb} no date, and charts need dated games."
            )
            if has_3x3:
                msg += "\n3x3 moments are not shown in charts — use Generate Narrative Summary below."
            self._set_placeholder_text(msg)
        else:
            self._set_placeholder_text(
                "No Chess Log moments in the selected data.\n"
                "Tag some via right-click on a move in the Moves List."
            )
        self._show_placeholder()

    def _on_charts_skipped(self, n: int) -> None:
        if n > 0:
            noun = "game" if n == 1 else "games"
            self._skip_note.setText(f"{n} {noun} not charted: no date.")
            self._skip_note.setVisible(True)
        else:
            self._skip_note.setVisible(False)

    def _on_players_ready(self, players: List) -> None:
        current_raw = self._player_combo.itemData(self._player_combo.currentIndex())
        had_selection = self._player_combo.currentIndex() >= 0
        self._player_combo.blockSignals(True)
        self._player_combo.clear()
        for name, count in players:
            self._player_combo.addItem(f"{name} ({count} logged)", name)
        if had_selection and players:
            idx = self._player_combo.findData(current_raw)
            self._player_combo.setCurrentIndex(idx)  # -1 if not found → stay unselected
        else:
            self._player_combo.setCurrentIndex(-1)
        self._player_combo.blockSignals(False)
        if had_selection and self._player_combo.currentIndex() < 0 and self._controller:
            # The selected player vanished from the list; the controller owns the selection.
            self._controller.clear_player_selection()
        if not players:
            self._set_placeholder_text("No players found in this data.")

    def _on_narrative_ready(self, narrative: str, flags: List[str], usage) -> None:
        self._narrative_edit.setMarkdown(sanitize_narrative_markdown(narrative))
        if flags:
            self._flagged_label.setText("\n".join(f"• {f}" for f in flags))
            self._flagged_box.setVisible(True)
        else:
            self._flagged_box.setVisible(False)
        self._narrative_token_label.setText(self._format_token_usage(usage))
        self._refresh_ai_state()

    def _on_narrative_failed(self, message: str) -> None:
        self._narrative_edit.setPlainText(f"Error: {message}")
        self._narrative_token_label.setText("")
        self._refresh_ai_state()

    def _on_ai_configured_changed(self, configured: bool) -> None:
        self._refresh_ai_state()

    def _on_ai_model_changed(self) -> None:
        self._refresh_ai_state(prefer_default=True)

    def _on_narrative_model_changed(self, text: str) -> None:
        if self._controller:
            self._controller.set_narrative_model_override(text or None)

    def _on_narrative_timeout_changed(self, value: int) -> None:
        if self._controller:
            self._controller.set_narrative_timeout_seconds(value)

    def _on_narrative_tokens_changed(self, value: int) -> None:
        if self._controller:
            self._controller.set_narrative_token_limit(value)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_token_usage(self, usage: Optional[TokenUsage]) -> str:
        if usage is None:
            return ""
        if not usage.reported:
            return "Token usage not reported by this provider"
        inp = f"{usage.input_tokens:,}" if usage.input_tokens is not None else "?"
        out = f"{usage.output_tokens:,}" if usage.output_tokens is not None else "?"
        text = f"Tokens: {inp} in / {out} out"
        if usage.reasoning_tokens and usage.reasoning_tokens > 0:
            thinking = f"{usage.reasoning_tokens:,}"
            text += f" / {thinking} thinking"
        return text

    def _fit_narrative_height(self) -> None:
        """Resize _narrative_edit to its document height so the outer scroll area handles overflow."""
        doc = self._narrative_edit.document()
        width = self._narrative_edit.viewport().width()
        if width > 0:
            doc.setTextWidth(width)
        h = int(doc.size().height())
        margins = self._narrative_edit.contentsMargins()
        total = h + margins.top() + margins.bottom() + 4
        self._narrative_edit.setMinimumHeight(max(total, 60))

    def _cat_colors_for_preset(self, preset: str) -> Dict[str, "QColor"]:
        from PyQt6.QtGui import QColor
        panel_cfg = self._config.get("ui", {}).get("panels", {}).get("detail", {})
        cat_colors_cfg = panel_cfg.get("chess_log_charts", {}).get("category_colors", {})
        preset_map = cat_colors_cfg.get(preset, {})
        result: Dict[str, "QColor"] = {}
        for cat, rgb in preset_map.items():
            if isinstance(rgb, list) and len(rgb) >= 3:
                result[cat] = QColor(int(rgb[0]), int(rgb[1]), int(rgb[2]))
        return result

    def _clear_charts(self) -> None:
        for w in self._chart_widgets:
            self._charts_layout.removeWidget(w)
            w.deleteLater()
        self._chart_widgets.clear()
        self._skip_note.setVisible(False)

    def _clear_narrative_and_check_logs(self) -> None:
        """Reset the narrative and Check Logs display to first-open state (display only;
        the controller has already dropped the stored results)."""
        self._narrative_edit.clear()
        self._narrative_token_label.setText("")
        self._flagged_box.setVisible(False)
        self._shallow_token_label.setText("")
        self._pending_partial_message = None

    def _reset_player_selection(self) -> None:
        self._player_combo.blockSignals(True)
        self._player_combo.setCurrentIndex(-1)
        self._player_combo.blockSignals(False)
        self._set_placeholder_text("Select a player to view Chess Log data.")
        self._refresh_ai_state()

    def _set_placeholder_text(self, text: str) -> None:
        self._placeholder.setText(text)

    def _show_placeholder(self) -> None:
        self._placeholder.setVisible(True)
        self._charts_container.setVisible(False)

    def _on_show_shallow_clicked(self) -> None:
        if not self._controller:
            return
        combo_text = self._model_combo.currentText()
        combo_data = self._model_combo.currentData()
        override = self._controller.get_narrative_model_override()
        default_model = self._controller.get_default_narrative_model() or ""
        will_pass = override or default_model or ""
        LoggingService.get_instance().info(
            "check-logs model resolution: combo_text=%r, combo_data=%r, "
            "override=%r, default_model=%r, will_pass=%r"
            % (combo_text, combo_data, override, default_model, will_pass)
        )
        self._show_shallow_btn.setEnabled(False)
        self._shallow_spinner.start()
        self._shallow_status_label.setVisible(True)
        self._shallow_token_label.setText("")
        self._controller.request_flag_shallow_notes()

    def _on_shallow_ready(self, shallow_keys, vague_keys, classified_keys, usage) -> None:
        self._shallow_spinner.stop()
        self._shallow_status_label.setVisible(False)
        self._shallow_token_label.setText(self._format_token_usage(usage))
        self._refresh_ai_state()
        partial_notice = self._pending_partial_message
        self._pending_partial_message = None
        if not self._controller:
            return
        if not shallow_keys and not vague_keys:
            msgs = (self._config or {}).get("ui", {}).get("dialogs", {}).get(
                "chess_log_messages", {}
            ).get("shallow_notes", {}).get("none_found", {})
            title = msgs.get("title", "Nothing Flagged")
            message = msgs.get("message_template", "No shallow notes or vague lessons found — great job.")
            if partial_notice:
                message = f"{html.escape(partial_notice)}<br><br>{message}"
            MessageDialog.show_information(self._config, title, message, self)
            return
        games = self._controller.resolve_games()
        chess_log_ctrl = self._controller.get_chess_log_controller()
        if not chess_log_ctrl:
            return
        source_label = self._controller.get_source_description()
        model_label = self._controller.get_cached_shallow_model_label() if self._controller else ""
        timestamp = self._controller.get_cached_shallow_timestamp() if self._controller else ""
        check_run_info = {"model": model_label, "date": timestamp} if model_label and timestamp else None
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        dlg = ShowShallowTagsDialog(
            config=self._config,
            games=games,
            controller=chess_log_ctrl,
            shallow_keys=shallow_keys,
            vague_keys=vague_keys,
            classified_keys=classified_keys,
            partial_notice=partial_notice,
            source_label=source_label,
            model_label=model_label,
            check_run_info=check_run_info,
            parent=self,
        )
        dlg.exec()

    def _on_shallow_failed(self, message: str) -> None:
        self._shallow_spinner.stop()
        self._shallow_status_label.setVisible(False)
        self._shallow_token_label.setText("")
        self._refresh_ai_state()
        MessageDialog.show_warning(self._config, "Check Logs Error", f"Could not classify notes:<br>{html.escape(message)}", self)

    def _on_shallow_partial(self, message: str) -> None:
        self._pending_partial_message = message

    def _refresh_ai_state(self, prefer_default: bool = False) -> None:
        configured = bool(self._controller and self._controller.is_ai_configured())
        source_selected = self._source_combo.currentIndex() > 0
        player_selected = self._player_combo.currentIndex() >= 0
        shallow_enabled = configured and source_selected and player_selected
        self._generate_btn.setEnabled(configured)
        self._show_shallow_btn.setEnabled(shallow_enabled)
        self._ai_hint.setVisible(not configured)
        if not configured:
            self._shallow_hint.setText(
                "Configure an AI provider in AI Summary → AI Model Settings to enable Check Logs."
            )
            self._shallow_hint.setVisible(True)
        elif not source_selected:
            self._shallow_hint.setText("Select a Data Source to enable Check Logs.")
            self._shallow_hint.setVisible(True)
        elif not player_selected:
            self._shallow_hint.setText("Select a player to enable Check Logs.")
            self._shallow_hint.setVisible(True)
        else:
            self._shallow_hint.setText("")
            self._shallow_hint.setVisible(False)
        # Sync timeout from Chess Log's own setting without triggering valueChanged persist.
        if self._controller:
            self._timeout_spin.blockSignals(True)
            self._timeout_spin.setValue(self._controller.get_narrative_timeout_seconds())
            self._timeout_spin.blockSignals(False)
        self._model_combo.setEnabled(configured)
        self._timeout_spin.setEnabled(configured)
        self._tokens_spin.setEnabled(configured)

        if configured and self._controller:
            models = self._controller.get_available_models()
            default_model = self._controller.get_default_narrative_model() or ""

            # Repopulate combo without firing model-changed signal.
            # Priority: (1) current visible selection, (2) persisted override
            # from the controller (survives a DB switch that clears the combo),
            # (3) provider default.
            current_selection = self._model_combo.currentText()
            override = self._controller.get_narrative_model_override() or ""
            self._model_combo.blockSignals(True)
            self._model_combo.clear()
            for m in models:
                self._model_combo.addItem(m)
            idx = self._model_combo.findText(current_selection) if (current_selection and not prefer_default) else -1
            if idx < 0 and override:
                idx = self._model_combo.findText(override)
            if idx < 0:
                idx = self._model_combo.findText(default_model)
            self._model_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self._model_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Right-click context menu
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event) -> None:
        if not self._controller:
            return
        section_name = self._hit_section(event.globalPos())
        from app.views.menus.chess_log_charts_context_menu import (
            build_chess_log_charts_context_menu,
        )
        menu = build_chess_log_charts_context_menu(self, section_name=section_name)
        menu.exec(event.globalPos())

    def _hit_section(self, global_pos: QPoint) -> Optional[str]:
        """Return the section_name of the widget under global_pos, or None."""
        for chart_widget in self._chart_widgets:
            top_left = chart_widget.mapToGlobal(QPoint(0, 0))
            rect = QRect(top_left, chart_widget.size())
            if rect.contains(global_pos):
                name = chart_widget.property("section_name")
                if name:
                    return str(name)
        if self._content_layout is not None:
            for i in range(self._content_layout.count()):
                item = self._content_layout.itemAt(i)
                widget = item.widget() if item else None
                if widget is None:
                    continue
                name = widget.property("section_name")
                if not name:
                    continue
                top_left = widget.mapToGlobal(QPoint(0, 0))
                rect = QRect(top_left, widget.size())
                if rect.contains(global_pos):
                    return str(name)
        return None

    def _narrative_text(self) -> str:
        """The raw markdown narrative from the controller ('' when none)."""
        if not self._controller:
            return ""
        return self._controller.get_last_narrative_result()[0] or ""

    def _narrative_metadata(self) -> tuple:
        """(generated_at, model_label, n, g, m, s, has_3x3) from the controller."""
        if not self._controller:
            return ("", "", 0, 0, 0, 0, False)
        return self._controller.get_last_narrative_metadata()

    def _export_header(self) -> Tuple[str, str]:
        """(player name, source description) for exports, both read from the controller."""
        if not self._controller:
            return "", ""
        return self._controller.get_player_display_name(), self._controller.get_source_description()

    def _copy_section_to_clipboard(self, section_name: str) -> None:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QMimeData
        if section_name.startswith("chart_"):
            preset = section_name[len("chart_"):]
            text = f"Category chart — {preset}: see Chess Log Charts tab in CARA."
            if text:
                QApplication.clipboard().setText(text)
        elif section_name == "narrative":
            text = self._narrative_text().strip() or "(no narrative yet)"
            html_text = self._narrative_html_for_copy()
            mime = QMimeData()
            mime.setHtml(html_text)
            mime.setText(text)
            QApplication.clipboard().setMimeData(mime)
        else:
            text = ""
            if text:
                QApplication.clipboard().setText(text)

    def _narrative_html_for_copy(self) -> str:
        """Build HTML for the Narrative Summary clipboard action."""
        from app.services.chess_log_html_service import ChessLogHTMLService
        narrative = sanitize_narrative_markdown(self._narrative_text())
        player_name, source_label = self._export_header()
        generated_at, model_label, n, g, m, s, has_3x3 = self._narrative_metadata()
        return ChessLogHTMLService(self._config).narrative_html(
            player_name,
            source_label,
            narrative,
            n_games=n,
            g_games=g,
            m_moments=m,
            s_flagged=s,
            has_3x3=has_3x3,
            generated_at=generated_at,
            model_label=model_label,
        )

    def _check_log_moments(self) -> List[CheckLogMoment]:
        """The one source of Check Logs rows for every export: saved flags only."""
        return self._controller.get_check_log_moments() if self._controller else []

    def _copy_log_to_clipboard(self) -> None:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import QMimeData
        # Plain text: keep today's format exactly (decision 9).
        lines: List[str] = []
        player_name = self._controller.get_player_display_name() if self._controller else ""
        source_text = self._controller.get_source_label() if self._controller else ""
        lines.append(f"Chess Log — {player_name}")
        lines.append(f"Source: {source_text}")
        lines.append("")
        for widget in self._chart_widgets:
            preset = (widget.property("section_name") or "").replace("chart_", "")
            lines.append(f"Category chart — {preset}: see Chess Log Charts tab in CARA.")
        lines.append("")
        narrative = self._narrative_text().strip()
        if narrative:
            lines.append("Narrative Summary:")
            lines.append(narrative)
            lines.append("")
        rendered = self._render_check_log_moments()
        if rendered.plain:
            lines.append("Check Logs:")
            lines.append(rendered.plain)
        plain_text = "\n".join(lines)

        html_text = self._charts_log_html_for_copy(rendered)
        mime = QMimeData()
        mime.setHtml(html_text)
        mime.setText(plain_text)
        QApplication.clipboard().setMimeData(mime)

    def _render_check_log_moments(self):
        """Both clipboard flavors of the flagged moments, via the shared renderer (#93)."""
        from app.services.chess_log_moment_renderer import (
            ChessLogMomentRenderer,
            MomentRef,
            RenderedMoments,
        )

        if self._controller is None:
            return RenderedMoments(plain="", html="")
        refs = [MomentRef(mo.game, mo.path_key, mo.preset) for mo in self._check_log_moments()]
        return ChessLogMomentRenderer(self._controller, self._config).render(refs)

    def _charts_log_html_for_copy(self, rendered=None) -> str:
        """Build HTML for the Charts log clipboard action."""
        from app.services.chess_log_html_service import ChessLogHTMLService

        if rendered is None:
            rendered = self._render_check_log_moments()

        player_name, source_label = self._export_header()
        narrative = sanitize_narrative_markdown(self._narrative_text())
        generated_at = model_label = ""
        n = g = m = s = 0
        has_3x3 = False
        if narrative:
            generated_at, model_label, n, g, m, s, has_3x3 = self._narrative_metadata()

        chart_preset_names = [
            (w.property("section_name") or "").replace("chart_", "")
            for w in self._chart_widgets
        ]

        return ChessLogHTMLService(self._config).charts_log_html(
            player_name,
            source_label,
            chart_preset_names,
            narrative,
            [],
            moments_html=rendered.html,
            n_games=n,
            g_games=g,
            m_moments=m,
            s_flagged=s,
            has_3x3=has_3x3,
            generated_at=generated_at,
            model_label=model_label,
        )

    def _build_check_log_tag_groups(self) -> List[Dict]:
        """Game-grouped TagRowSnapshot lists for the flagged moments (HTML and PDF)."""
        from io import StringIO
        import chess.pgn as _chess_pgn
        from app.models.chess_log_snapshot import TagRowSnapshot
        from app.views.dialogs._tag_row_helpers import (
            game_header_text as _game_header_text,
            node_info as _node_info,
        )

        groups: List[Dict] = []
        pgn_games: Dict[int, Any] = {}
        current: Optional[Dict] = None
        current_game = None
        for mo in self._check_log_moments():
            game = mo.game
            if id(game) not in pgn_games:
                pgn_game = None
                try:
                    pgn = getattr(game, "pgn", None)
                    if pgn:
                        pgn_game = _chess_pgn.read_game(StringIO(pgn))
                except Exception:
                    pass
                pgn_games[id(game)] = pgn_game
            if current is None or game is not current_game:
                current = {"header": _game_header_text(game), "rows": []}
                current_game = game
                groups.append(current)
            fen, played_move, move_label, mover_is_black = _node_info(pgn_games[id(game)], mo.path_key)
            current["rows"].append(TagRowSnapshot(
                move_label=move_label,
                preset=mo.preset,
                entries=mo.entries,
                fen=fen or None,
                played_move=played_move,
                show_ignore=True,
                is_flipped=mover_is_black,
                is_shallow=mo.is_shallow,
                is_vague=mo.is_vague,
                shallow_cats=mo.shallow_cats,
                vague_cats=mo.vague_cats,
            ))
        return groups

    def _export_pdf_report(self) -> None:
        from pathlib import Path

        from PyQt6.QtWidgets import QFileDialog

        from app.services.chess_log_pdf_service import (
            ChessLogPDFService,
            default_chess_log_charts_pdf_filename,
        )

        player_name, source_label = self._export_header()
        suggested = default_chess_log_charts_pdf_filename(player_name)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF Report", suggested, "PDF Files (*.pdf)"
        )
        if not path:
            return

        chart_pixmaps = []
        for widget in self._chart_widgets:
            preset = (widget.property("section_name") or "").replace("chart_", "")
            chart_pixmaps.append((preset, widget.grab()))

        narrative_text = self._narrative_text().strip()
        shallow_rows = [row for grp in self._build_check_log_tag_groups() for row in grp["rows"]]

        narrative_model_label = generated_at = ""
        n = g = m = s = 0
        has_3x3 = False
        if narrative_text:
            generated_at, narrative_model_label, n, g, m, s, has_3x3 = self._narrative_metadata()
        ChessLogPDFService(self._config).export_charts_report(
            Path(path),
            player_name,
            source_label,
            chart_pixmaps,
            narrative_text,
            shallow_rows,
            model_label=narrative_model_label,
            generated_at=generated_at,
            n_games=n,
            g_games=g,
            m_moments=m,
            s_flagged=s,
            has_3x3=has_3x3,
        )

    def _export_narrative_pdf(self) -> None:
        from pathlib import Path
        from PyQt6.QtWidgets import QFileDialog
        from app.services.chess_log_pdf_service import (
            ChessLogPDFService,
            default_chess_log_narrative_pdf_filename,
        )

        narrative = self._narrative_text()
        if not narrative:
            MessageDialog.show_information(self._config, "No Narrative", "Generate a Narrative Summary first.", self)
            return

        player_name, source_label = self._export_header()
        suggested = default_chess_log_narrative_pdf_filename(player_name)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Narrative Summary", suggested, "PDF Files (*.pdf)"
        )
        if not path:
            return

        generated_at, model_label, n, g, m, s, has_3x3 = self._narrative_metadata()

        ChessLogPDFService(self._config).export_narrative_report(
            Path(path),
            player_name,
            source_label,
            narrative,
            model_label=model_label,
            generated_at=generated_at,
            n_games=n,
            g_games=g,
            m_moments=m,
            s_flagged=s,
            has_3x3=has_3x3,
        )
