"""Controller for Chess Log Charts tab (§5.1 + §5.2).

Owns Data Source + Player selection state, three worker threads:
  - ChessLogPlayerDropdownWorker — populates player dropdown from selected games
  - ChessLogAggregationWorker   — runs chess_log_stats_service.aggregate()
  - ChessLogNarrativeThread     — runs chess_log_narrative_service.generate_narrative()

Mirrors the selection/callback injection pattern from PlayerStatsController
(set_get_selected_games_callback, notify_selection_changed) for consistent
wiring in AppController / MainWindow.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple

from PyQt6.QtCore import QMutex, QMutexLocker, QObject, QThread, QTimer, pyqtSignal

from app.models.database_model import GameData
from app.services.chess_log_charts_user import (
    CHOICES_BINNING_MODE,
    CHOICES_LINE_STYLE,
    CHOICES_MAX_GAP_SEGMENT_DAYS,
    CHOICES_SMOOTHING_STRENGTH,
    CHOICES_TARGET_BINS,
    CHOICES_X_AXIS_LAYOUT,
    chart_cfg_with_chess_log_charts_overrides,
    normalize_chess_log_charts_settings,
)
from app.services.ai_service import TokenUsage
from app.services.chess_log_narrative_service import NarrativeResult, generate_narrative
from app.services.chess_log_stats_service import (
    ChessLogPresetSeries,
    aggregate,
    compute_narrative_counts,
    get_all_players,
)
from app.services.user_settings_service import UserSettingsService
from app.utils.ai_provider_config import (
    get_available_models as _get_available_models,
    resolve_default_provider,
)

_PROVIDER_DISPLAY: Dict[str, str] = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "custom": "Custom",
}

_3X3_SHORT_LABELS: Dict[str, str] = {
    "Why1": "Why I played it",
    "Why2": "What was wrong",
    "Why3": "Why the better move is better",
    "Why4": "Lesson",
}


class ChessLogPlayerDropdownWorker(QThread):
    """Populate the player dropdown from the current game set."""

    players_ready = pyqtSignal(list)   # List[Tuple[str, int]]

    def __init__(
        self,
        games: List[GameData],
        snapshot: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> None:
        super().__init__()
        self._games = games
        self._snapshot = snapshot  # {id(game): paths_data} captured on the main thread
        self._cancelled = False
        self._mutex = QMutex()

    def cancel(self) -> None:
        with QMutexLocker(self._mutex):
            self._cancelled = True

    def run(self) -> None:
        with QMutexLocker(self._mutex):
            if self._cancelled:
                return
        snap = self._snapshot
        players = get_all_players(self._games, get_tags_for_game=lambda g: snap.get(id(g), {}))
        with QMutexLocker(self._mutex):
            if not self._cancelled:
                self.players_ready.emit(players)


class ChessLogAggregationWorker(QThread):
    """Run chess_log_stats_service.aggregate() off the UI thread.

    Rendering-only fields (progression_x_axis_mode, compress_gap_max_segment_days,
    progression_line_style, progression_line_smooth_strength) are stamped onto every
    ChessLogPresetSeries returned by aggregate() before the result is emitted, so the
    widget can read them directly from the series without knowing controller state.
    """

    charts_updated = pyqtSignal(object)    # Dict[str, ChessLogPresetSeries]
    charts_unavailable = pyqtSignal(str)   # reason string
    charts_skipped = pyqtSignal(int)       # n undated CLAMP/CCT games skipped, emitted after charts_updated

    def __init__(
        self,
        games: List[GameData],
        player: str,
        color_filter: str,
        chart_cfg: Dict[str, Any],
        progression_x_axis_mode: str = "uniform_bins",
        compress_gap_max_segment_days: int = 28,
        progression_line_style: str = "smooth",
        progression_line_smooth_strength: float = 1.0,
        snapshot: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> None:
        super().__init__()
        self._games = games
        self._player = player
        self._color_filter = color_filter
        self._chart_cfg = chart_cfg
        self._progression_x_axis_mode = progression_x_axis_mode
        self._compress_gap_max_segment_days = compress_gap_max_segment_days
        self._progression_line_style = progression_line_style
        self._progression_line_smooth_strength = progression_line_smooth_strength
        self._snapshot = snapshot  # {id(game): paths_data} captured on the main thread
        self._cancelled = False
        self._mutex = QMutex()

    def cancel(self) -> None:
        with QMutexLocker(self._mutex):
            self._cancelled = True

    def run(self) -> None:
        with QMutexLocker(self._mutex):
            if self._cancelled:
                return
        try:
            snap = self._snapshot
            result = aggregate(
                self._games,
                player=self._player,
                color_filter=self._color_filter,
                chart_cfg=self._chart_cfg,
                get_tags_for_game=lambda g: snap.get(id(g), {}),
            )
        except Exception as exc:
            with QMutexLocker(self._mutex):
                if not self._cancelled:
                    self.charts_unavailable.emit(str(exc))
            return
        with QMutexLocker(self._mutex):
            if self._cancelled:
                return
        if result.series:
            # Stamp rendering fields onto each series before emit.
            for series in result.series.values():
                series.progression_x_axis_mode = self._progression_x_axis_mode
                series.compress_gap_max_segment_days = self._compress_gap_max_segment_days
                series.progression_line_style = self._progression_line_style
                series.progression_line_smooth_strength = self._progression_line_smooth_strength
            self.charts_updated.emit(result.series)
            with QMutexLocker(self._mutex):
                if self._cancelled:
                    return
            self.charts_skipped.emit(result.n_undated_clamp_cct)
        else:
            with QMutexLocker(self._mutex):
                if self._cancelled:
                    return
            n = result.n_undated_clamp_cct
            if n > 0:
                self.charts_unavailable.emit(
                    f"no_dated_clamp_cct:{n}:{1 if result.has_3x3 else 0}"
                )
            elif result.has_3x3:
                self.charts_unavailable.emit("no_chartable_preset")
            else:
                self.charts_unavailable.emit("no_data")


class ChessLogShallowThread(QThread):
    """Classify why-notes as SHALLOW/DEEP (CLAMP/CCT) and INTENT/LESSON (3x3) off the UI thread.

    Makes up to two API calls: one for legacy (CLAMP/CCT) notes, one for 3x3 notes.
    Emits a single shallow_ready with combined results when both complete.
    """

    shallow_ready = pyqtSignal(object, object, object, object, str)  # (shallow_keys, vague_keys, classified_keys, Optional[TokenUsage], model_label)
    shallow_failed = pyqtSignal(str)             # hard error — no results follow
    shallow_partial = pyqtSignal(str)            # informational: N notes unparsed, results follow

    def __init__(
        self,
        games: List[GameData],
        provider: str,
        model: str,
        api_key: str,
        base_url_override: Optional[str],
        config: Optional[Dict[str, Any]],
        timeout_seconds: int,
        legacy_notes: List[Tuple[int, Any, str, str, str]],           # (idx, game, pk, preset, why) — CLAMP/CCT
        three_notes: List[Tuple[int, Any, str, str, str, str, str, str]],  # (idx, game, pk, preset, w1..w4)
        three_ignored_sets: Optional[List[FrozenSet[str]]] = None,    # parallel to three_notes: cats ignored per note
    ) -> None:
        super().__init__()
        self._games = games
        self._provider = provider
        self._model = model
        self._api_key = api_key
        self._base_url_override = base_url_override
        self._config = config
        self._timeout_seconds = timeout_seconds
        self._legacy_notes = legacy_notes
        self._three_notes = three_notes
        self._three_ignored_sets = three_ignored_sets
        self._cancelled = False
        self._mutex = QMutex()

    def cancel(self) -> None:
        with QMutexLocker(self._mutex):
            self._cancelled = True

    def run(self) -> None:  # noqa: C901
        try:
            with QMutexLocker(self._mutex):
                if self._cancelled:
                    return
            from app.services.chess_log_shallow_service import classify_notes, classify_notes_3x3
            from app.services.ai_service import TokenUsage

            legacy_result = None
            three_result = None

            if self._legacy_notes:
                legacy_result = classify_notes(
                    notes=self._legacy_notes,
                    provider=self._provider,
                    model=self._model,
                    api_key=self._api_key,
                    base_url_override=self._base_url_override,
                    config=self._config,
                    timeout_seconds=self._timeout_seconds,
                )
                with QMutexLocker(self._mutex):
                    if self._cancelled:
                        return

            if self._three_notes:
                three_result = classify_notes_3x3(
                    notes=self._three_notes,
                    provider=self._provider,
                    model=self._model,
                    api_key=self._api_key,
                    base_url_override=self._base_url_override,
                    config=self._config,
                    timeout_seconds=self._timeout_seconds,
                )
                with QMutexLocker(self._mutex):
                    if self._cancelled:
                        return

            # Both failed (or both empty) → hard failure.
            if legacy_result is not None and not legacy_result.success and three_result is None:
                self.shallow_failed.emit(legacy_result.error or "Classification failed.")
                return
            if three_result is not None and not three_result.success and legacy_result is None:
                self.shallow_failed.emit(three_result.error or "3x3 classification failed.")
                return
            if (legacy_result is not None and not legacy_result.success
                    and three_result is not None and not three_result.success):
                err = legacy_result.error or three_result.error or "Classification failed."
                self.shallow_failed.emit(err)
                return

            # Merge results.
            all_notes = list(self._legacy_notes) + [
                (n[0], n[1], n[2], n[3]) + n[4:] for n in self._three_notes  # type: ignore[misc]
            ]
            merged_shallow: set = set()
            merged_vague: set = set()
            merged_unparsed_legacy: tuple = ()
            merged_unparsed_three: tuple = ()
            merged_usage: Optional[Any] = None
            merged_model_ids: set = set()

            if legacy_result is not None:
                if legacy_result.success:
                    # B11: only trust unparsed_indices on success; failure → all unparsed
                    merged_unparsed_legacy = legacy_result.unparsed_indices
                    merged_shallow.update(legacy_result.shallow_keys)
                    merged_model_ids.add(legacy_result.model)
                    if legacy_result.usage:
                        merged_usage = legacy_result.usage
                else:
                    merged_unparsed_legacy = tuple(range(len(self._legacy_notes)))

            if three_result is not None:
                if three_result.success:
                    # B11: only trust unparsed_indices on success; failure → all unparsed
                    merged_unparsed_three = three_result.unparsed_indices
                    merged_shallow.update(three_result.shallow_keys)
                    merged_vague.update(three_result.vague_keys)
                    merged_model_ids.add(three_result.model)
                    if three_result.usage and merged_usage:
                        merged_usage = TokenUsage(
                            input_tokens=(merged_usage.input_tokens or 0) + (three_result.usage.input_tokens or 0),
                            output_tokens=(merged_usage.output_tokens or 0) + (three_result.usage.output_tokens or 0),
                            reasoning_tokens=(
                                (merged_usage.reasoning_tokens or 0) + (three_result.usage.reasoning_tokens or 0)
                                if (merged_usage.reasoning_tokens is not None
                                    or three_result.usage.reasoning_tokens is not None)
                                else None
                            ),
                            reported=merged_usage.reported and three_result.usage.reported,
                        )
                    elif three_result.usage:
                        merged_usage = three_result.usage
                else:
                    merged_unparsed_three = tuple(range(len(self._three_notes)))

            # Build lookup {(gn, pk): ignored_cats} for filtering verdicts of ignored answers.
            three_ignored_lookup: Dict[Tuple[int, str], FrozenSet[str]] = {}
            if self._three_ignored_sets:
                for i, n in enumerate(self._three_notes):
                    if i < len(self._three_ignored_sets):
                        three_ignored_lookup[(n[1], n[2])] = self._three_ignored_sets[i]

            # Filter out verdicts for ignored 3x3 answers.
            merged_shallow = {
                k for k in merged_shallow
                if not (k[2] == "3x3" and k[3] in three_ignored_lookup.get((k[0], k[1]), frozenset()))
            }
            merged_vague = {
                k for k in merged_vague
                if not (k[2] == "3x3" and k[3] in three_ignored_lookup.get((k[0], k[1]), frozenset()))
            }

            msgs = (self._config or {}).get("ui", {}).get("dialogs", {}).get(
                "chess_log_messages", {}
            ).get("shallow_notes", {})
            s = lambda n: "" if n == 1 else "s"

            total_unparsed = len(merged_unparsed_legacy) + len(merged_unparsed_three)
            total_flagged = len(merged_shallow) + len(merged_vague)
            total_input = len(self._legacy_notes) + len(self._three_notes)

            if total_unparsed > 0 and total_flagged == 0:
                tmpl = msgs.get("all_failed", {}).get(
                    "message_template",
                    "None of the {count} note{s_suffix} could be classified. "
                    "Try again; the model's reply couldn't be read.",
                )
                msg = tmpl.format(count=total_unparsed, s_suffix=s(total_unparsed))
                self.shallow_failed.emit(msg)
                return
            if total_unparsed > 0:
                tmpl = msgs.get("partial", {}).get(
                    "message_template",
                    "{unparsed} of {total} note{s_suffix} couldn't be classified "
                    "— left unchanged. Flagged {flagged}.",
                )
                msg = tmpl.format(
                    unparsed=total_unparsed,
                    total=total_input,
                    s_suffix=s(total_unparsed),
                    flagged=total_flagged,
                )
                self.shallow_partial.emit(msg)

            # Build classified_keys — notes that received a parsed verdict this run.
            # Keys are 4-tuples (game, path_key, preset, cat)
            # where game is the GameData object (identity-keyed):
            #   CLAMP/CCT: cat="" (one entry per note)
            #   3x3: cat in {"Why1","Why2","Why3","Why4"} (four keys per parsed note)
            #   Ignored 3x3 cats are excluded: an ignored answer never appears in classified_keys.
            legacy_unparsed_set = frozenset(merged_unparsed_legacy)
            three_unparsed_set = frozenset(merged_unparsed_three)
            classified_keys = frozenset(
                (n[1], n[2], n[3], "")
                for i, n in enumerate(self._legacy_notes)
                if i not in legacy_unparsed_set
            ) | frozenset(
                (n[1], n[2], "3x3", cat)
                for i, n in enumerate(self._three_notes)
                if i not in three_unparsed_set
                for cat in ("Why1", "Why2", "Why3", "Why4")
                if cat not in three_ignored_lookup.get((n[1], n[2]), frozenset())
            )

            if not merged_model_ids:
                merged_model_ids.add(self._model)
            model_id_str = ", ".join(sorted(merged_model_ids))
            provider_display = _PROVIDER_DISPLAY.get(self._provider.lower(), self._provider)
            model_label = f"{provider_display} {model_id_str}"

            self.shallow_ready.emit(
                frozenset(merged_shallow),
                frozenset(merged_vague),
                classified_keys,
                merged_usage,
                model_label,
            )
        except Exception as exc:
            self.shallow_failed.emit(f"Unexpected error: {exc}")


class ChessLogNarrativeThread(QThread):
    """Run chess_log_narrative_service.generate_narrative() off the UI thread."""

    narrative_ready = pyqtSignal(str, list, object)   # narrative_text, shallow_flags, Optional[TokenUsage]
    narrative_failed = pyqtSignal(str)                # error message

    def __init__(
        self,
        games: List[GameData],
        provider: str,
        model: str,
        api_key: str,
        base_url_override: Optional[str],
        player: str,
        color_filter: str,
        config: Optional[Dict[str, Any]],
        timeout_seconds: int = 60,
        token_limit: Optional[int] = None,
        snapshot: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> None:
        super().__init__()
        self._games = games
        self._provider = provider
        self._model = model
        self._api_key = api_key
        self._base_url_override = base_url_override
        self._player = player
        self._color_filter = color_filter
        self._config = config
        self._timeout_seconds = timeout_seconds
        self._token_limit = token_limit
        self._snapshot = snapshot  # {id(game): paths_data} captured on the main thread
        self._cancelled = False
        self._mutex = QMutex()

    def cancel(self) -> None:
        with QMutexLocker(self._mutex):
            self._cancelled = True

    def run(self) -> None:
        try:
            with QMutexLocker(self._mutex):
                if self._cancelled:
                    return
            snap = self._snapshot
            narrative_result = generate_narrative(
                games=self._games,
                provider=self._provider,
                model=self._model,
                api_key=self._api_key,
                base_url_override=self._base_url_override,
                player=self._player,
                color_filter=self._color_filter,
                config=self._config,
                timeout_seconds=self._timeout_seconds,
                token_limit=self._token_limit,
                get_tags_for_game=lambda g: snap.get(id(g), {}),
            )
            with QMutexLocker(self._mutex):
                if self._cancelled:
                    return
            if narrative_result.success:
                self.narrative_ready.emit(
                    narrative_result.text, narrative_result.shallow_flags, narrative_result.usage
                )
            else:
                self.narrative_failed.emit(narrative_result.text)
        except Exception as exc:
            self.narrative_failed.emit(f"Unexpected error: {exc}")


# Default max output tokens for the Narrative Summary (the Tokens spin box in the Charts tab).
DEFAULT_NARRATIVE_TOKEN_LIMIT = 12000
CHESS_LOG_AI_TIMEOUT_KEY = "ai_timeout_seconds"  # under user_settings.chess_log


class ChessLogChartsController(QObject):
    """Controller for the Chess Log Charts detail tab."""

    charts_updated = pyqtSignal(object)    # Dict[str, ChessLogPresetSeries]
    charts_unavailable = pyqtSignal(str)   # reason ("no_source", "no_player", "no_data", ...)
    charts_skipped = pyqtSignal(int)       # n undated CLAMP/CCT games skipped; always emitted after charts_updated
    charts_loading = pyqtSignal()          # aggregation worker about to start; view should clear stale chart
    players_ready = pyqtSignal(list)       # List[Tuple[str, int]]
    player_selection_cleared = pyqtSignal()  # view should reset player combo to unselected
    narrative_ready = pyqtSignal(str, list, object)  # narrative_text, shallow_flags, Optional[TokenUsage]
    narrative_failed = pyqtSignal(str)
    shallow_ready = pyqtSignal(object, object, object, object)  # (shallow_keys, vague_keys, classified_keys, Optional[TokenUsage])
    shallow_failed = pyqtSignal(str)             # hard error — no results follow
    shallow_partial = pyqtSignal(str)            # informational: N notes unparsed, results follow
    ai_configured_changed = pyqtSignal(bool)  # True when LLM becomes available or unavailable
    ai_model_changed = pyqtSignal()           # default provider or model changed in AI Settings
    results_invalidated = pyqtSignal()        # charted game set changed mid-session; view should clear narrative/Check Logs

    def __init__(
        self,
        config: Dict[str, Any],
        database_controller: Any,
    ) -> None:
        super().__init__()
        self._config = config
        self._database_controller = database_controller
        # Last AI provider state announced via ai_configured_changed / ai_model_changed.
        self._ai_baseline: tuple = (False, None)

        self._source_selection: int = 0   # 0=None, 1=Active, 2=All, 3=SelectedActive, 4=SelectedAll
        self._current_player: str = ""
        self._color_filter: str = "both"
        self._player_explicit_selected: bool = False
        self._get_selected_games_callback: Optional[Callable[[bool], List[GameData]]] = None

        _charts_defaults = normalize_chess_log_charts_settings({})
        self._target_progression_bins: int = _charts_defaults["target_progression_bins"]
        self._ordinal_fallback_mode: str = _charts_defaults["ordinal_fallback_mode"]
        self._progression_x_axis_mode: str = _charts_defaults["progression_x_axis_mode"]
        self._compress_gap_max_segment_days: int = _charts_defaults["compress_gap_max_segment_days"]
        self._progression_line_style: str = _charts_defaults["progression_line_style"]
        self._progression_line_smooth_strength: float = _charts_defaults["progression_line_smooth_strength"]

        self._dropdown_worker: Optional[ChessLogPlayerDropdownWorker] = None
        self._agg_worker: Optional[ChessLogAggregationWorker] = None
        self._narrative_thread: Optional[ChessLogNarrativeThread] = None
        self._shallow_thread: Optional[ChessLogShallowThread] = None

        # Narrative-panel ephemeral settings (not persisted except timeout).
        self._narrative_token_limit: int = DEFAULT_NARRATIVE_TOKEN_LIMIT
        self._narrative_model_override: Optional[str] = None
        self._chess_log_controller: Optional[Any] = None
        self._pending_narrative_model_label: str = ""

        # Result cache — survives view rebuilds (e.g. theme change) so the narrative
        # and shallow-check results are re-displayed on the fresh view without
        # requiring the user to regenerate them.  Cleared on data-context changes
        # (database switch, source change) but NOT on cosmetic changes.
        self._cached_narrative: str = ""
        self._cached_narrative_flags: list = []
        self._cached_narrative_usage: Optional[Any] = None
        self._cached_narrative_counts: Optional[Tuple[int, int, int, int, bool]] = None
        self._cached_narrative_generated_at: str = ""
        self._cached_narrative_model_label: str = ""
        self._cached_shallow_keys: Optional[Any] = None
        self._cached_vague_keys: Optional[Any] = None
        self._cached_shallow_usage: Optional[Any] = None
        self._cached_shallow_model_label: str = ""
        self._cached_shallow_timestamp: str = ""  # UTC ISO-8601; set when shallow_ready fires

        self._selection_debounce = QTimer(self)
        self._selection_debounce.setSingleShot(True)
        self._selection_debounce.timeout.connect(self._on_selection_debounced)
        self._selection_debounce_ms = 100

        # Generation counter: incremented by _clear_result_cache() on every game-set
        # change.  Captured into _narrative_launch_gen / _shallow_launch_gen when a
        # thread starts; results whose captured gen no longer matches the current gen
        # are silently discarded so an in-flight run on game-set A cannot appear on B.
        self._game_set_generation: int = 0
        self._narrative_launch_gen: int = 0
        # Games and tag snapshot captured by request_narrative(); the header counts
        # are computed from these so they describe the same data as the text.
        self._narrative_request_games: Optional[List[GameData]] = None
        self._narrative_request_snapshot: Optional[Dict[int, Dict[str, Any]]] = None
        self._shallow_launch_gen: int = 0
        # Last resolved game-set identity key; compared in _schedule_charts_refresh to
        # detect mid-session changes (e.g. selected-game source 3/4 picks different rows).
        self._last_game_set_key: Optional[frozenset] = None

        self._connect_to_database_panel_model()

    # ------------------------------------------------------------------
    # Public API — called by AppController / MainWindow
    # ------------------------------------------------------------------

    def set_get_selected_games_callback(
        self, callback: Optional[Callable[[bool], List[GameData]]]
    ) -> None:
        self._get_selected_games_callback = callback

    def set_chess_log_controller(self, controller: Any) -> None:
        """Inject ChessLogController for Chess Log dialogs."""
        self._chess_log_controller = controller

    def get_chess_log_controller(self) -> Optional[Any]:
        """Return the injected ChessLogController."""
        return self._chess_log_controller

    def resolve_games(self) -> List[GameData]:
        """Public wrapper around _resolve_games()."""
        return self._resolve_games()

    def notify_chess_log_saved(self) -> None:
        """Re-run the player dropdown worker after Chess Log tags have been saved.

        Must be called after any successful Chess Log save so that the tagged-game
        counts in the player combo stay current.  Only refreshes the dropdown;
        does not re-run chart aggregation (the chart data is still valid).
        """
        if self._source_selection == 0:
            return
        self._start_dropdown_worker(self._resolve_games())

    def has_player_selected(self) -> bool:
        """True iff the user has explicitly picked a player in the Player dropdown."""
        return self._player_explicit_selected

    def get_tags_for_game(self, game: GameData) -> Dict[str, Any]:
        """Return Chess Log moments for *game* (delegates to ChessLogController).

        The injected ChessLogController (set_chess_log_controller) is required;
        raises RuntimeError when it is missing rather than reading storage around
        the owner.
        """
        if self._chess_log_controller is None:
            raise RuntimeError(
                "ChessLogChartsController has no ChessLogController; "
                "call set_chess_log_controller() first"
            )
        return self._chess_log_controller.get_tags_for_game(game)

    @staticmethod
    def _live_settings() -> Dict[str, Any]:
        """Current user settings, read at the moment of use (never cached)."""
        return UserSettingsService.get_instance().get_settings()

    def on_ai_settings_changed(self) -> None:
        """Re-resolve the AI provider from live settings; emit change signals if it moved."""
        provider_tuple = resolve_default_provider(self._live_settings())
        is_configured = provider_tuple is not None
        key = (provider_tuple[0], provider_tuple[1]) if provider_tuple else None
        was_configured, old_key = self._ai_baseline
        self._ai_baseline = (is_configured, key)
        if was_configured != is_configured:
            self.ai_configured_changed.emit(is_configured)
        if old_key != key:
            self._narrative_model_override = None
            self.ai_model_changed.emit()

    def set_user_settings(self, user_settings: Dict[str, Any]) -> None:
        """Apply Chess Log chart preferences from *user_settings* and re-check the AI provider.

        AI settings themselves are never cached here; they are read live from
        UserSettingsService.
        """
        self.on_ai_settings_changed()

        old = (
            self._target_progression_bins, self._ordinal_fallback_mode, self._progression_x_axis_mode,
            self._compress_gap_max_segment_days, self._progression_line_style, self._progression_line_smooth_strength,
        )
        charts = normalize_chess_log_charts_settings(
            user_settings.get("chess_log", {}).get("charts", {})
        )
        self._target_progression_bins = charts["target_progression_bins"]
        self._ordinal_fallback_mode = charts["ordinal_fallback_mode"]
        self._progression_x_axis_mode = charts["progression_x_axis_mode"]
        self._compress_gap_max_segment_days = charts["compress_gap_max_segment_days"]
        self._progression_line_style = charts["progression_line_style"]
        self._progression_line_smooth_strength = charts["progression_line_smooth_strength"]

        new = (
            self._target_progression_bins, self._ordinal_fallback_mode, self._progression_x_axis_mode,
            self._compress_gap_max_segment_days, self._progression_line_style, self._progression_line_smooth_strength,
        )
        if old != new:
            self._selection_debounce.stop()
            self._selection_debounce.start(self._selection_debounce_ms)

    def is_ai_configured(self) -> bool:
        return resolve_default_provider(self._live_settings()) is not None

    def get_last_narrative_result(self) -> tuple:
        """Return (narrative, flags, usage) from the most recent successful generation."""
        return self._cached_narrative, self._cached_narrative_flags, self._cached_narrative_usage

    def get_last_narrative_metadata(self) -> tuple:
        """Return (generated_at, model_label, n_games, g_games, m_moments, s_flagged, has_3x3)."""
        n, g, m, s, has_3x3 = self._cached_narrative_counts or (0, 0, 0, 0, False)
        return (
            self._cached_narrative_generated_at,
            self._cached_narrative_model_label,
            n, g, m, s, has_3x3,
        )

    def get_last_shallow_result(self) -> tuple:
        """Return (shallow_keys, vague_keys, usage) from the most recent successful shallow check."""
        return self._cached_shallow_keys, self._cached_vague_keys, self._cached_shallow_usage

    def get_cached_shallow_model_label(self) -> str:
        """Return '<Provider> <model-id>' from the most recent Check Logs run, or '' if none."""
        return self._cached_shallow_model_label

    def get_cached_shallow_timestamp(self) -> str:
        """Return UTC ISO-8601 timestamp when the last Check Logs result arrived, or ''."""
        return self._cached_shallow_timestamp

    def _clear_result_cache(self) -> None:
        self._game_set_generation += 1
        self._last_game_set_key = None
        self._cached_narrative = ""
        self._cached_narrative_flags = []
        self._cached_narrative_usage = None
        self._cached_narrative_counts = None
        self._cached_narrative_generated_at = ""
        self._cached_narrative_model_label = ""
        self._cached_shallow_keys = None
        self._cached_vague_keys = None
        self._cached_shallow_usage = None
        self._cached_shallow_model_label = ""
        self._cached_shallow_timestamp = ""

    # --- narrative panel controls ---

    def get_narrative_timeout_seconds(self) -> int:
        """Return Chess Log's own AI timeout (``chess_log.ai_timeout_seconds``), read live.

        Falls back to the config default when the key is absent. Independent of
        AI Summary's timeout.
        """
        stored = self._live_settings().get("chess_log", {}).get(CHESS_LOG_AI_TIMEOUT_KEY)
        if stored is None:
            return self._default_ai_timeout_seconds()
        return int(stored)

    def set_narrative_timeout_seconds(self, seconds: int) -> None:
        """Persist the timeout to ``chess_log.ai_timeout_seconds``."""
        try:
            UserSettingsService.get_instance().update_chess_log_settings(
                {CHESS_LOG_AI_TIMEOUT_KEY: int(seconds)}
            )
        except Exception:
            pass

    def _default_ai_timeout_seconds(self) -> int:
        """Default Chess Log AI timeout from config.json."""
        cfg = self._config
        if not cfg.get("ui", {}).get("panels", {}).get("detail", {}).get("chess_log_charts", {}).get("ai", {}):
            from app.config.config_loader import ConfigLoader
            cfg = ConfigLoader().load()
        return int(cfg["ui"]["panels"]["detail"]["chess_log_charts"]["ai"]["default_timeout_seconds"])

    def get_narrative_token_limit(self) -> int:
        return self._narrative_token_limit

    def set_narrative_token_limit(self, limit: int) -> None:
        self._narrative_token_limit = limit

    def set_narrative_model_override(self, model: Optional[str]) -> None:
        """Set a specific model to use for narrative generation (None = provider default)."""
        self._narrative_model_override = model or None

    def get_narrative_model_override(self) -> Optional[str]:
        """Return the user's currently persisted model override, or None."""
        return self._narrative_model_override

    def get_available_models(self) -> List[str]:
        """Return model IDs available for the active provider."""
        return _get_available_models(self._live_settings())

    def get_default_narrative_model(self) -> Optional[str]:
        """Return the default model ID for the active provider, or None if unconfigured."""
        provider_tuple = resolve_default_provider(self._live_settings())
        return provider_tuple[1] if provider_tuple else None

    # --- getters ---

    def get_target_progression_bins(self) -> int:
        return self._target_progression_bins

    def get_ordinal_fallback_mode(self) -> str:
        return self._ordinal_fallback_mode

    def get_progression_x_axis_mode(self) -> str:
        return self._progression_x_axis_mode

    def get_compress_gap_max_segment_days(self) -> int:
        return self._compress_gap_max_segment_days

    def get_progression_line_style(self) -> str:
        return self._progression_line_style

    def get_progression_line_smooth_strength(self) -> float:
        return self._progression_line_smooth_strength

    # --- setters (menu-driven) ---

    def set_target_progression_bins(self, n: int) -> None:
        if n not in CHOICES_TARGET_BINS:
            return
        self._target_progression_bins = n
        self._persist_chart_settings()
        self._kick_debounce()

    def set_ordinal_fallback_mode(self, mode: str) -> None:
        if mode not in CHOICES_BINNING_MODE:
            return
        self._ordinal_fallback_mode = mode
        self._persist_chart_settings()
        self._kick_debounce()

    def set_progression_x_axis_mode(self, layout: str) -> None:
        if layout not in CHOICES_X_AXIS_LAYOUT:
            return
        self._progression_x_axis_mode = layout
        self._persist_chart_settings()
        self._kick_debounce()

    def set_compress_gap_max_segment_days(self, days: int) -> None:
        if days not in CHOICES_MAX_GAP_SEGMENT_DAYS:
            return
        self._compress_gap_max_segment_days = days
        self._persist_chart_settings()
        self._kick_debounce()

    def set_progression_line_style(self, style: str) -> None:
        if style not in CHOICES_LINE_STYLE:
            return
        self._progression_line_style = style
        self._persist_chart_settings()
        self._kick_debounce()

    def set_progression_line_smooth_strength(self, strength: float) -> None:
        if strength not in CHOICES_SMOOTHING_STRENGTH:
            return
        self._progression_line_smooth_strength = strength
        self._persist_chart_settings()
        self._kick_debounce()

    def set_source_selection(self, source: int) -> None:
        """Set the Data Source (0=None, 1=Active, 2=All, 3=SelectedActive, 4=SelectedAll)."""
        self._source_selection = source
        self._player_explicit_selected = False
        self._clear_result_cache()
        if source == 0:
            self._cancel_agg_worker()
            self.charts_unavailable.emit("no_source")
            return
        # Refresh the player dropdown but hold off on aggregation until the
        # user explicitly picks a player.
        games = self._resolve_games()
        self._start_dropdown_worker(games)
        self.charts_unavailable.emit("no_player")

    def set_player_selection(self, player: str) -> None:
        self._current_player = player or ""
        self._player_explicit_selected = True
        self._clear_result_cache()
        self._kick_debounce()

    def set_color_filter(self, color_filter: str) -> None:
        self._color_filter = color_filter
        self._clear_result_cache()
        self.results_invalidated.emit()
        self._kick_debounce()

    def notify_selection_changed(self) -> None:
        """Called when database table selection changes (sources 3/4 only)."""
        if self._source_selection not in (3, 4):
            return
        self._kick_debounce()

    def request_narrative(self) -> None:
        """Start the narrative generation worker (idempotent: cancels running thread)."""
        if self._source_selection == 0:
            self.narrative_failed.emit("Please select a Data Source first.")
            return
        if not self._current_player:
            self.narrative_failed.emit("Please select a player first.")
            return
        provider_tuple = resolve_default_provider(self._live_settings())
        if not provider_tuple:
            self.narrative_failed.emit("No AI provider configured.")
            return
        provider, default_model, api_key, base_url = provider_tuple
        model = self._narrative_model_override or default_model
        provider_display = _PROVIDER_DISPLAY.get(provider.lower(), provider)
        self._pending_narrative_model_label = f"{provider_display} {model}"
        games = self._resolve_games()
        if not games:
            self.narrative_failed.emit("No games in scope.")
            return
        self._cancel_narrative_thread()
        snapshot = self._snapshot_tags(games)
        self._narrative_request_games = games
        self._narrative_request_snapshot = snapshot
        thread = ChessLogNarrativeThread(
            games=games,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url_override=base_url,
            player=self._current_player,
            color_filter=self._color_filter,
            config=self._config,
            timeout_seconds=self.get_narrative_timeout_seconds(),
            token_limit=self._narrative_token_limit,
            snapshot=snapshot,
        )
        thread.narrative_ready.connect(self._on_narrative_thread_ready)
        thread.narrative_failed.connect(self._on_narrative_thread_failed)
        thread.finished.connect(self._on_narrative_finished)
        self._narrative_thread = thread
        self._narrative_launch_gen = self._game_set_generation
        thread.start()

    def request_flag_shallow_notes(self) -> None:
        """Start shallow-note classification off the UI thread.

        Gathers all non-empty why-notes from games in scope, then spawns
        ChessLogShallowThread. On completion, emits ``shallow_ready`` with the
        set of (game, path_key, preset) keys whose notes were judged
        SHALLOW, and writes is_shallow onto each affected entry in the cache.
        Emits ``shallow_failed`` on error.
        """
        provider_tuple = resolve_default_provider(self._live_settings())
        if not provider_tuple:
            self.shallow_failed.emit("No AI provider configured.")
            return
        provider, default_model, api_key, base_url = provider_tuple
        model = self._narrative_model_override or default_model

        games = self._resolve_games()
        from app.services.chess_log_shallow_service import build_notes
        legacy_notes, three_notes, three_ignored_sets = build_notes(games, self.get_tags_for_game)

        if not legacy_notes and not three_notes:
            self.shallow_ready.emit(set(), set(), frozenset(), None)
            return

        self._cancel_shallow_thread()
        thread = ChessLogShallowThread(
            games=games,
            provider=provider,
            model=model,
            api_key=api_key,
            base_url_override=base_url,
            config=self._config,
            timeout_seconds=self.get_narrative_timeout_seconds(),
            legacy_notes=legacy_notes,
            three_notes=three_notes,
            three_ignored_sets=three_ignored_sets,
        )
        thread.shallow_ready.connect(self._on_shallow_thread_ready)
        thread.shallow_failed.connect(self._on_shallow_thread_failed)
        thread.shallow_partial.connect(self._on_shallow_thread_partial)
        thread.finished.connect(self._on_shallow_thread_finished)
        self._shallow_thread = thread
        self._shallow_launch_gen = self._game_set_generation
        thread.start()

    def _on_narrative_thread_ready(self, narrative: str, flags: list, usage) -> None:
        if self._narrative_launch_gen != self._game_set_generation:
            return
        from datetime import datetime
        self._cached_narrative = narrative
        self._cached_narrative_flags = list(flags)
        self._cached_narrative_usage = usage
        self._cached_narrative_generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
        self._cached_narrative_model_label = self._pending_narrative_model_label
        games = self._narrative_request_games
        snapshot = self._narrative_request_snapshot
        if games is None or snapshot is None:
            games = self._resolve_games()
            snapshot = self._snapshot_tags(games)
        self._cached_narrative_counts = compute_narrative_counts(
            games, self._current_player, self._color_filter,
            lambda g: snapshot.get(id(g), {}),
        )
        self.narrative_ready.emit(narrative, flags, usage)

    def _on_narrative_thread_failed(self, message: str) -> None:
        if self._narrative_launch_gen != self._game_set_generation:
            return
        self._cached_narrative = ""
        self._cached_narrative_flags = []
        self._cached_narrative_usage = None
        self._cached_narrative_counts = None
        self._cached_narrative_generated_at = ""
        self._cached_narrative_model_label = ""
        self.narrative_failed.emit(message)

    def _on_shallow_thread_ready(self, shallow_keys, vague_keys, classified_keys, usage, model_label: str = "") -> None:
        """Cache shallow/vague results then pass to the view; the dialog's Save commits them."""
        if self._shallow_launch_gen != self._game_set_generation:
            return
        from datetime import datetime, timezone
        self._cached_shallow_keys = frozenset(shallow_keys) if shallow_keys else None
        self._cached_vague_keys = frozenset(vague_keys) if vague_keys else None
        self._cached_shallow_usage = usage
        self._cached_shallow_model_label = model_label
        self._cached_shallow_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.shallow_ready.emit(shallow_keys, vague_keys, classified_keys, usage)

    def _on_shallow_thread_partial(self, message: str) -> None:
        if self._shallow_launch_gen != self._game_set_generation:
            return
        self.shallow_partial.emit(message)

    def _on_shallow_thread_failed(self, message: str) -> None:
        if self._shallow_launch_gen != self._game_set_generation:
            return
        self.shallow_failed.emit(message)

    def _cancel_shallow_thread(self) -> None:
        if self._shallow_thread:
            try:
                if self._shallow_thread.isRunning():
                    self._shallow_thread.cancel()
                    self._shallow_thread.finished.disconnect()
                    self._shallow_thread = None
                    return
                self._shallow_thread.finished.disconnect()
            except RuntimeError:
                pass
            self._shallow_thread = None

    def _on_shallow_thread_finished(self) -> None:
        try:
            if self._shallow_thread:
                self._shallow_thread.finished.disconnect()
        except RuntimeError:
            pass
        self._shallow_thread = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _kick_debounce(self) -> None:
        self._selection_debounce.stop()
        self._selection_debounce.start(self._selection_debounce_ms)

    def _on_selection_debounced(self) -> None:
        if self._source_selection == 0:
            return
        if not self._player_explicit_selected:
            self.charts_unavailable.emit("no_player")
            return
        if self._source_selection in (3, 4):
            self._refresh_dropdown_and_charts()
        else:
            self._schedule_charts_refresh()

    def _refresh_dropdown_and_charts(self) -> None:
        games = self._resolve_games()
        snapshot = self._snapshot_tags(games)
        self._start_dropdown_worker(games, snapshot=snapshot)
        self._schedule_charts_refresh(games=games, snapshot=snapshot)

    def _snapshot_tags(self, games: List[GameData]) -> Dict[int, Dict[str, Any]]:
        """Capture a main-thread snapshot of tags for all games.

        Called before starting background workers so they never read the
        controller cache directly across threads.  Returns {id(game): paths_data}.
        """
        return {id(g): self.get_tags_for_game(g) for g in games}

    def _schedule_charts_refresh(
        self,
        games: Optional[List[GameData]] = None,
        snapshot: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> None:
        if self._source_selection == 0:
            return
        self.charts_loading.emit()
        if games is None:
            games = self._resolve_games()
        if snapshot is None:
            snapshot = self._snapshot_tags(games)
        new_key = frozenset(id(g) for g in games)
        if self._last_game_set_key is not None and new_key != self._last_game_set_key:
            self._clear_result_cache()
            self.results_invalidated.emit()
        self._last_game_set_key = new_key
        self._cancel_agg_worker()
        chart_cfg = chart_cfg_with_chess_log_charts_overrides(
            self._config, self._target_progression_bins, self._ordinal_fallback_mode
        )
        worker = ChessLogAggregationWorker(
            games=games,
            player=self._current_player,
            color_filter=self._color_filter,
            chart_cfg=chart_cfg,
            progression_x_axis_mode=self._progression_x_axis_mode,
            compress_gap_max_segment_days=self._compress_gap_max_segment_days,
            progression_line_style=self._progression_line_style,
            progression_line_smooth_strength=self._progression_line_smooth_strength,
            snapshot=snapshot,
        )
        worker.charts_updated.connect(self.charts_updated)
        worker.charts_unavailable.connect(self.charts_unavailable)
        worker.charts_skipped.connect(self.charts_skipped)
        worker.finished.connect(self._on_agg_worker_finished)
        self._agg_worker = worker
        worker.start()

    def _start_dropdown_worker(
        self,
        games: List[GameData],
        snapshot: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> None:
        self._cancel_dropdown_worker()
        if snapshot is None:
            snapshot = self._snapshot_tags(games)
        worker = ChessLogPlayerDropdownWorker(games=games, snapshot=snapshot)
        worker.players_ready.connect(self._on_players_ready)
        worker.finished.connect(self._on_dropdown_worker_finished)
        self._dropdown_worker = worker
        worker.start()

    def _on_players_ready(self, players: List[str]) -> None:
        self.players_ready.emit(players)

    def _resolve_games(self) -> List[GameData]:
        if self._source_selection == 0:
            return []
        if self._source_selection == 1:
            db = self._database_controller.get_active_database()
            return db.get_all_games() if db else []
        if self._source_selection == 2:
            panel = self._database_controller.get_panel_model()
            if not panel:
                return []
            result: List[GameData] = []
            for db in panel.get_all_database_models():
                result.extend(db.get_all_games())
            return result
        if self._source_selection in (3, 4) and self._get_selected_games_callback:
            try:
                active_only = self._source_selection == 3
                raw = self._get_selected_games_callback(active_only)
                return list(raw) if raw else []
            except Exception:
                return []
        return []

    def get_current_source_filenames(self) -> List[str]:
        """Return display names of the databases backing the current source selection."""
        if self._source_selection == 0:
            return []
        if self._source_selection == 1:
            db = self._database_controller.get_active_database()
            return [db.display_name] if db else []
        if self._source_selection == 2:
            panel = self._database_controller.get_panel_model()
            if not panel:
                return []
            return [db.display_name for db in panel.get_all_database_models()]
        if self._source_selection == 3:
            db = self._database_controller.get_active_database()
            return [db.display_name] if db else []
        if self._source_selection == 4:
            panel = self._database_controller.get_panel_model()
            if not panel:
                return []
            return [db.display_name for db in panel.get_all_database_models()]
        return []

    def _persist_chart_settings(self) -> None:
        try:
            UserSettingsService.get_instance().update_chess_log_settings({
                "charts": {
                    "target_progression_bins": self._target_progression_bins,
                    "ordinal_fallback_mode": self._ordinal_fallback_mode,
                    "progression_x_axis_mode": self._progression_x_axis_mode,
                    "compress_gap_max_segment_days": self._compress_gap_max_segment_days,
                    "progression_line_style": self._progression_line_style,
                    "progression_line_smooth_strength": self._progression_line_smooth_strength,
                }
            })
        except Exception:
            pass

    def _cancel_agg_worker(self) -> None:
        if self._agg_worker:
            try:
                if self._agg_worker.isRunning():
                    self._agg_worker.cancel()
                    self._agg_worker.finished.disconnect()
                    self._agg_worker = None
                    return
                self._agg_worker.finished.disconnect()
            except RuntimeError:
                pass
            self._agg_worker = None

    def _cancel_dropdown_worker(self) -> None:
        if self._dropdown_worker:
            try:
                if self._dropdown_worker.isRunning():
                    self._dropdown_worker.cancel()
                    self._dropdown_worker.finished.disconnect()
                    self._dropdown_worker = None
                    return
                self._dropdown_worker.finished.disconnect()
            except RuntimeError:
                pass
            self._dropdown_worker = None

    def _cancel_narrative_thread(self) -> None:
        if self._narrative_thread:
            try:
                if self._narrative_thread.isRunning():
                    self._narrative_thread.cancel()
                    self._narrative_thread.finished.disconnect()
                    self._narrative_thread = None
                    return
                self._narrative_thread.finished.disconnect()
            except RuntimeError:
                pass
            self._narrative_thread = None

    def _on_agg_worker_finished(self) -> None:
        try:
            if self._agg_worker:
                self._agg_worker.finished.disconnect()
        except RuntimeError:
            pass
        self._agg_worker = None

    def _on_dropdown_worker_finished(self) -> None:
        try:
            if self._dropdown_worker:
                self._dropdown_worker.finished.disconnect()
        except RuntimeError:
            pass
        self._dropdown_worker = None

    def _on_narrative_finished(self) -> None:
        try:
            if self._narrative_thread:
                self._narrative_thread.finished.disconnect()
        except RuntimeError:
            pass
        self._narrative_thread = None

    def _connect_to_database_panel_model(self) -> None:
        panel_model = self._database_controller.get_panel_model()
        if not panel_model:
            return
        try:
            panel_model.active_database_changed.disconnect(self._on_active_database_changed)
        except (RuntimeError, TypeError):
            pass
        panel_model.active_database_changed.connect(self._on_active_database_changed)

    def _on_active_database_changed(self, database) -> None:
        """Reset player selection when the active database changes (sources 1 and 2 only)."""
        if self._source_selection not in (1, 2):
            return
        self.clear_player_selection()
        games = self._resolve_games()
        self._start_dropdown_worker(games)

    def clear_player_selection(self) -> None:
        """Drop the selected player and everything derived from it; the view resets to match."""
        self._cancel_agg_worker()
        self._cancel_shallow_thread()
        self._current_player = ""
        self._player_explicit_selected = False
        self._clear_result_cache()
        self.player_selection_cleared.emit()
        self.charts_unavailable.emit("no_player")
