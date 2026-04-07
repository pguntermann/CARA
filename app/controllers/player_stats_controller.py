"""Controller for orchestrating player statistics calculations."""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QMutex, QMutexLocker, QTimer

from app.models.database_model import DatabaseModel
from app.models.moveslist_model import MoveData

if TYPE_CHECKING:
    from app.models.database_model import GameData
from app.models.database_panel_model import DatabasePanelModel
from app.models.game_model import GameModel
from app.services.player_stats_activity_heatmap_layout import effective_ordinal_for_heatmap
from app.services.player_stats_service import PlayerStatsService, AggregatedPlayerStats
from app.services.error_pattern_service import ErrorPatternService, ErrorPattern
from app.services.game_summary_service import GameSummaryService, GameSummary
from app.services.progress_service import ProgressService
from app.controllers.game_controller import GameController
from app.services.logging_service import LoggingService
from app.services.opening_service import OpeningService
from app.services.user_settings_service import UserSettingsService

# Sentinel: use callback / default resolution for selected-games snapshot (see _schedule_dropdown_update).
_DEFAULT_SELECTION_GAMES = object()


class PlayerDropdownWorker(QThread):
    """Worker thread for populating player dropdown asynchronously."""

    players_ready = pyqtSignal(list)  # List of (player_name, game_count, analyzed_count) tuples
    progress_update = pyqtSignal(int, str)  # progress_percent, status_message

    def __init__(
        self,
        stats_controller: "PlayerStatsController",
        use_all_databases: bool,
        selected_games: Optional[List["GameData"]] = None,
    ) -> None:
        """Initialize the dropdown worker.

        Args:
            stats_controller: PlayerStatsController instance.
            use_all_databases: Whether to use all databases or just active (ignored if selected_games is set).
            selected_games: If set, derive players from this list instead of querying databases.
        """
        super().__init__()
        self.stats_controller = stats_controller
        self.use_all_databases = use_all_databases
        self.selected_games = selected_games  # Optional; when set, use this list for dropdown
        self._cancelled = False
        self._mutex = QMutex()
    
    def cancel(self) -> None:
        """Cancel the worker."""
        with QMutexLocker(self._mutex):
            self._cancelled = True
    
    def _is_cancelled(self) -> bool:
        """Check if worker is cancelled."""
        with QMutexLocker(self._mutex):
            return self._cancelled
    
    def run(self) -> None:
        """Run the worker to populate dropdown."""
        try:
            if self._is_cancelled():
                return

            if self.selected_games is not None:
                self._run_from_selected_games()
                return

            self.progress_update.emit(10, "Collecting player names...")

            # Get unique players
            players = self.stats_controller.get_unique_players(self.use_all_databases)

            if self._is_cancelled() or not players:
                self.players_ready.emit([])
                return

            # Filter to only include players with at least 2 analyzed games
            players_with_analyzed = []
            total_players = len(players)

            # Cache databases once at the start to avoid repeated get_active_database() calls
            if self.use_all_databases:
                panel_model = self.stats_controller._database_controller.get_panel_model()
                cached_databases = panel_model.get_all_database_models()
            else:
                active_db = self.stats_controller._database_controller.get_active_database()
                cached_databases = [active_db] if active_db else []

            for idx, (player_name, game_count) in enumerate(players):
                if self._is_cancelled():
                    return

                # Update progress
                progress_percent = 10 + int((idx / total_players) * 80)
                self.progress_update.emit(progress_percent, f"Checking players: {idx + 1}/{total_players}...")

                # Check if this player has at least 2 analyzed games
                # Use cached databases to avoid repeated get_active_database() calls
                analyzed_count, _ = self.stats_controller.get_analyzed_game_count_with_databases(
                    player_name,
                    cached_databases
                )

                if analyzed_count >= 2:
                    players_with_analyzed.append((player_name, game_count, analyzed_count))

            if not self._is_cancelled():
                try:
                    self.progress_update.emit(100, f"Found {len(players_with_analyzed)} player(s)")
                    self.players_ready.emit(players_with_analyzed)
                except RuntimeError:
                    # Receiver might be deleted, ignore
                    pass

        except Exception as e:
            # Emit empty list on error
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error in PlayerDropdownWorker: {e}", exc_info=e)
            self.players_ready.emit([])

    def _run_from_selected_games(self) -> None:
        """Build player list from selected_games (same format as run() for DB path)."""
        from collections import Counter
        total_count_per_player: Dict[str, int] = Counter()
        analyzed_count_per_player: Dict[str, int] = Counter()
        for game in self.selected_games:
            for name in (game.white, game.black):
                if name and name.strip():
                    total_count_per_player[name] += 1
                    if getattr(game, "analyzed", False):
                        analyzed_count_per_player[name] += 1
        players_with_analyzed = [
            (name, total_count_per_player[name], analyzed_count_per_player[name])
            for name in total_count_per_player
            if analyzed_count_per_player.get(name, 0) >= 2
        ]
        players_with_analyzed.sort(key=lambda x: (-x[2], x[0]))
        if not self._is_cancelled():
            try:
                self.progress_update.emit(100, f"Found {len(players_with_analyzed)} player(s)")
                self.players_ready.emit(players_with_analyzed)
            except RuntimeError:
                pass


class PlayerStatsCalculationWorker(QThread):
    """Worker thread for calculating player statistics asynchronously."""
    
    stats_ready = pyqtSignal(object, list, list)  # AggregatedPlayerStats, List[ErrorPattern], List[GameSummary]
    stats_unavailable = pyqtSignal(str)  # Reason key
    progress_update = pyqtSignal(int, str)  # progress_percent, status_message
    
    def __init__(
        self,
        stats_controller: "PlayerStatsController",
        player_name: str,
        use_all_databases: bool,
        player_games: Optional[List["GameData"]] = None,
        time_series_user_settings: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the stats calculation worker.

        Args:
            stats_controller: PlayerStatsController instance.
            player_name: Player name to analyze.
            use_all_databases: Whether to use all databases or just active (ignored if player_games is set).
            player_games: If set, use this list for the player's games instead of querying databases.
            time_series_user_settings: Snapshot of user time-series prefs (main thread) for binning.
        """
        super().__init__()
        self.stats_controller = stats_controller
        self.player_name = player_name
        self.use_all_databases = use_all_databases
        self.player_games = player_games  # Optional; when set, already filtered to this player
        self._time_series_user_settings: Dict[str, Any] = (
            dict(time_series_user_settings) if time_series_user_settings else {}
        )
        self._cancelled = False
        self._mutex = QMutex()
    
    def cancel(self) -> None:
        """Cancel the worker."""
        with QMutexLocker(self._mutex):
            self._cancelled = True
    
    def _is_cancelled(self) -> bool:
        """Check if worker is cancelled."""
        with QMutexLocker(self._mutex):
            return self._cancelled
    
    def run(self) -> None:
        """Run the worker to calculate statistics."""
        result_emitted = False
        try:
            if self._is_cancelled():
                return
            
            if not self.player_name or not self.player_name.strip():
                self.stats_unavailable.emit("no_player")
                result_emitted = True
                return

            if self.player_games is not None:
                player_games = self.player_games
                total_count = len(player_games)
            else:
                # Get databases
                self.progress_update.emit(5, "Loading databases...")

                if self.use_all_databases:
                    panel_model = self.stats_controller._database_controller.get_panel_model()
                    databases = panel_model.get_all_database_models()
                else:
                    active_db = self.stats_controller._database_controller.get_active_database()
                    databases = [active_db] if active_db else []

                if self._is_cancelled():
                    return

                if not databases:
                    self.stats_unavailable.emit("no_database")
                    result_emitted = True
                    return

                # Get player games
                self.progress_update.emit(10, "Finding player games...")

                player_games, total_count = self.stats_controller.player_stats_service.get_player_games(
                    self.player_name, databases, only_analyzed=False
                )

                if self._is_cancelled():
                    return

            if not player_games:
                self.stats_unavailable.emit("player_not_found")
                result_emitted = True
                return
            
            # Separate analyzed and unanalyzed
            analyzed_games = [g for g in player_games if g.analyzed]
            if not analyzed_games:
                self.stats_unavailable.emit("no_analyzed_games")
                result_emitted = True
                return
            
            # Aggregate statistics (includes parallel game summary calculation)
            self.progress_update.emit(20, f"Aggregating statistics from {len(analyzed_games)} game(s)...")
            
            # Remember analyzed games so controller can reuse them for per-game features
            self.stats_controller._last_analyzed_games = analyzed_games
            
            # Define progress callback for parallel processing
            def progress_callback(completed: int, status: str) -> None:
                if not self._is_cancelled():
                    self.progress_update.emit(completed, status)
            
            # Define cancellation check function
            def cancellation_check() -> bool:
                return self._is_cancelled()
            
            aggregated_stats, game_summaries = self.stats_controller.player_stats_service.aggregate_player_statistics(
                self.player_name,
                analyzed_games,
                self.stats_controller._game_controller,
                progress_callback,
                cancellation_check,
                time_series_user_settings=self._time_series_user_settings,
            )
            
            if self._is_cancelled():
                return
            
            if not aggregated_stats:
                self.stats_unavailable.emit("calculation_error")
                result_emitted = True
                return
            
            # One move extraction per game — reused by all error-pattern detectors (avoids repeated PGN parse)
            precomputed_moves: List[Optional[List[MoveData]]] = []
            gc = self.stats_controller._game_controller
            n_for_moves = len(analyzed_games)
            if gc and n_for_moves > 0:
                for idx, g in enumerate(analyzed_games):
                    if self._is_cancelled():
                        return
                    # Map this sub-phase to 88–90% so the bar advances while loading each game
                    pct = 88 + int((idx + 1) / max(n_for_moves, 1) * 2)
                    if pct > 90:
                        pct = 90
                    self.progress_update.emit(
                        pct,
                        f"Loading moves for pattern detection ({idx + 1}/{n_for_moves})...",
                    )
                    try:
                        precomputed_moves.append(gc.extract_moves_from_game(g))
                    except Exception:
                        precomputed_moves.append(None)
            else:
                self.progress_update.emit(88, "Loading moves for pattern detection...")
                precomputed_moves = [None] * n_for_moves
            
            # Detect error patterns (using summaries already calculated in parallel)
            self.progress_update.emit(90, "Detecting error patterns...")
            
            error_patterns = self.stats_controller.error_pattern_service.detect_error_patterns(
                self.player_name,
                analyzed_games,
                aggregated_stats,
                game_summaries,
                precomputed_moves=precomputed_moves,
            )
            
            if not self._is_cancelled():
                try:
                    self.progress_update.emit(100, f"Statistics calculated for {self.player_name}")
                    self.stats_ready.emit(aggregated_stats, error_patterns, game_summaries)
                    result_emitted = True
                except RuntimeError:
                    # Receiver might be deleted, ignore
                    result_emitted = True
        
        except Exception as e:
            # Emit error signal
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error in PlayerStatsCalculationWorker: {e}", exc_info=e)
            self.stats_unavailable.emit("error")
            result_emitted = True
        finally:
            # Cancelled exits often return without emitting; clear UI unless a newer worker replaced us.
            if (
                not result_emitted
                and self._is_cancelled()
                and self.stats_controller._stats_worker is self
            ):
                try:
                    self.stats_unavailable.emit("calculation_cancelled")
                except RuntimeError:
                    pass


class PlayerStatsController(QObject):
    """Controller responsible for producing and exposing player statistics data."""
    
    stats_updated = pyqtSignal(object, list, list)  # AggregatedPlayerStats, List[ErrorPattern], List[GameSummary]
    stats_unavailable = pyqtSignal(str)  # Reason key (e.g., "no_player", "no_analyzed_games")
    stats_recalculation_started = pyqtSignal()  # Stats worker is about to run (UI may show a short status line)
    bulk_analysis_blocks_stats_recalculation = pyqtSignal(bool)  # True while bulk analysis runs; pauses DB-driven recalcs
    players_ready = pyqtSignal(list)  # List of (player_name, game_count, analyzed_count) tuples for dropdown
    player_selection_cleared = pyqtSignal()  # Emitted when player selection is cleared
    source_selection_changed = pyqtSignal(int)  # Emitted when source selection changes (0=None, 1=Active, 2=All)
    
    def __init__(
        self,
        config: Dict[str, Any],
        database_controller: Any,
        game_controller: Optional[GameController] = None,
        game_model: Optional[GameModel] = None,
    ) -> None:
        """Initialize the player stats controller.
        
        Args:
            config: Configuration dictionary.
            database_controller: DatabaseController instance.
            game_controller: Optional GameController for extracting moves.
            game_model: Optional GameModel for auto-selecting player from active game.
        """
        super().__init__()
        self.config = config
        self._database_controller = database_controller
        self._game_controller = game_controller
        self._game_model = game_model
        
        self.player_stats_service = PlayerStatsService(config, game_controller)
        self.error_pattern_service = ErrorPatternService(config, game_controller)
        self.summary_service = GameSummaryService(config)
        self._opening_service = OpeningService(config)
        
        self.current_stats: Optional[AggregatedPlayerStats] = None
        self.current_patterns: List[ErrorPattern] = []
        self.current_game_summaries: List[GameSummary] = []
        # Keep the analyzed games used for the current stats so we can rank individual games.
        self._current_analyzed_games: List["GameData"] = []
        self._last_analyzed_games: List["GameData"] = []
        self._last_unavailable_reason: str = "no_player"
        self._current_player: Optional[str] = None
        self._use_all_databases: bool = False
        self._source_selection: int = 0  # 0=None, 1=Active, 2=All DBs, 3=Selected (Active), 4=Selected (All)
        self._get_selected_games_callback: Optional[Callable[[bool], List["GameData"]]] = None
        
        # Worker threads
        self._dropdown_worker: Optional[PlayerDropdownWorker] = None
        self._stats_worker: Optional[PlayerStatsCalculationWorker] = None
        self._recalc_pending: bool = False  # Coalesce recalc requests while worker is running
        self._bulk_analysis_active: bool = False  # When True, skip scheduling stats recalculation (except explicit end-of-bulk refresh)
        
        # Database change tracking
        self._connected_databases: List[DatabaseModel] = []
        self._database_update_timer = QTimer()
        self._database_update_timer.setSingleShot(True)
        self._database_update_timer.timeout.connect(self._on_database_update_debounced)
        self._database_update_debounce_ms = 500  # Debounce database updates by 500ms

        self._selection_debounce_timer = QTimer(self)
        self._selection_debounce_timer.setSingleShot(True)
        self._selection_debounce_timer.timeout.connect(self._on_selection_changed_debounced)
        self._selection_debounce_ms = 100

        self._dropdown_restart_pending: bool = False
        self._dropdown_restart_explicit_snapshot: bool = False
        self._dropdown_restart_snapshot: Optional[List["GameData"]] = None
        
        # Initialize ProgressService
        self._progress_service = ProgressService.get_instance()
        
        # Connect to game model for auto-selection
        if self._game_model:
            self._game_model.active_game_changed.connect(self._on_active_game_changed)
        
        # Connect to database panel model
        self._connect_to_database_panel_model()
    
    def notify_bulk_analysis_started(self) -> None:
        """Pause player-stats recalculation while bulk analysis runs; cancel any in-flight stats worker."""
        self._bulk_analysis_active = True
        self._recalc_pending = False
        self._cancel_stats_worker()
        self.bulk_analysis_blocks_stats_recalculation.emit(True)
    
    def notify_bulk_analysis_finished(self) -> None:
        """Resume after bulk analysis (including cancel). Refreshes stats once if a player is selected."""
        self._bulk_analysis_active = False
        self.bulk_analysis_blocks_stats_recalculation.emit(False)
        # Defer so BulkAnalysisController.is_analysis_running() is false before we start a new worker
        def _deferred_recalc() -> None:
            if self._current_player:
                self._schedule_stats_recalculation()
        QTimer.singleShot(0, _deferred_recalc)
    
    def is_bulk_blocking_player_stats(self) -> bool:
        """True while bulk analysis is active and player-stats recalculation is paused."""
        return self._bulk_analysis_active
    
    def _on_active_game_changed(self, game) -> None:
        """Handle active game change - optionally auto-select player."""
        # This could auto-select player, but we'll let the view decide
        pass
    
    def get_unique_players(self, use_all_databases: bool = False) -> List[tuple]:
        """Get unique player names from database(s).
        
        Args:
            use_all_databases: If True, get players from all open databases.
                             If False, get from active database only.
        
        Returns:
            List of (player_name, game_count) tuples.
        """
        if use_all_databases:
            panel_model = self._database_controller.get_panel_model()
            databases = panel_model.get_all_database_models()
        else:
            active_db = self._database_controller.get_active_database()
            databases = [active_db] if active_db else []
        
        # Collect unique players across databases
        player_counts: Dict[str, int] = {}
        for database in databases:
            players = database.get_unique_players()
            for player_name, count in players:
                player_counts[player_name] = player_counts.get(player_name, 0) + count
        
        # Sort by game count (descending), then by name
        sorted_players = sorted(player_counts.items(), key=lambda x: (-x[1], x[0]))
        return sorted_players
    
    def calculate_player_statistics(self, player_name: str, use_all_databases: bool = False) -> None:
        """Calculate statistics for a player.
        
        This method now delegates all work to the asynchronous worker path.
        
        Args:
            player_name: Player name to analyze.
            use_all_databases: If True, analyze across all open databases.
                             If False, analyze only active database.
        """
        from app.services.progress_service import ProgressService
        from PyQt6.QtWidgets import QApplication
        
        self._current_player = player_name
        self._use_all_databases = use_all_databases
        
        progress_service = ProgressService.get_instance()
        progress_service.show_progress()
        progress_service.set_indeterminate(False)
        progress_service.set_progress(0)
        progress_service.set_status(f"Calculating statistics for {player_name}...")
        
        QApplication.processEvents()
        
        if not player_name or not player_name.strip():
            self._emit_unavailable("no_player")
            progress_service.hide_progress()
            return
        
        if self._bulk_analysis_active:
            progress_service.hide_progress()
            return
        
        # Kick off asynchronous recalculation. The worker will handle databases,
        # game collection, aggregation, error patterns, and status updates.
        self._schedule_stats_recalculation()
    
    def get_current_stats(self) -> Optional[AggregatedPlayerStats]:
        """Get the most recently calculated statistics."""
        return self.current_stats
    
    def get_current_patterns(self) -> List[ErrorPattern]:
        """Get the most recently detected error patterns."""
        return self.current_patterns
    
    def _get_ranked_games_by_cpl(self) -> List[Tuple[float, float, "GameData"]]:
        """Rank analyzed games by the player's average CPL (ascending = best).
        
        Returns:
            List of (average_cpl, accuracy, GameData) tuples sorted ascending by CPL.
        """
        if not self._current_analyzed_games or not self.current_game_summaries or not self._current_player:
            return []
        
        ranked: List[Tuple[float, float, "GameData"]] = []
        for game, summary in zip(self._current_analyzed_games, self.current_game_summaries):
            # Determine whether the player was White or Black in this game
            if game.white == self._current_player:
                player_stats = summary.white_stats
            elif game.black == self._current_player:
                player_stats = summary.black_stats
            else:
                # Game doesn't match current player (shouldn't happen, but be safe)
                continue
        
            ranked.append((player_stats.average_cpl, player_stats.accuracy, game))
        
        ranked.sort(key=lambda x: x[0])  # lower CPL is better
        return ranked

    def _map_games_to_sources(self, games: List["GameData"]) -> List[Tuple["GameData", str]]:
        """Map GameData instances to (GameData, source_display_name) using database identifiers."""
        if not games:
            return []

        panel_model = self._database_controller.get_panel_model()
        results: List[Tuple["GameData", str]] = []

        for game in games:
            found = self.find_game_in_databases(game, use_all_databases=True)
            if not found:
                continue
            database, _ = found
            identifier = panel_model.find_database_by_model(database)
            if identifier == "clipboard":
                display_name = "Clipboard"
            else:
                display_name = Path(identifier).stem
            results.append((game, display_name))

        return results

    def get_top_best_games_with_sources(self, max_best: int) -> List[Tuple["GameData", str]]:
        """Get top N best-performing games (lowest CPL) for the current player with source names."""
        ranked = self._get_ranked_games_by_cpl()
        if not ranked or max_best <= 0:
            return []

        best_count = min(max_best, len(ranked))
        best_games = [game for _, _, game in ranked[:best_count]]
        return self._map_games_to_sources(best_games)

    def get_top_worst_games_with_sources(self, max_worst: int, max_best: int) -> List[Tuple["GameData", str]]:
        """Get top N worst-performing games (highest CPL) for the current player with source names.

        Ensures that worst games are disjoint from the best games if both are shown.
        """
        ranked = self._get_ranked_games_by_cpl()
        if not ranked or max_worst <= 0:
            return []

        n = len(ranked)
        # Reserve up to max_best games for the "best" list so we don't overlap
        reserved_for_best = min(max_best, n)
        worst_available = max(0, n - reserved_for_best)
        worst_count = min(max_worst, worst_available)
        if worst_count <= 0:
            return []

        start = n - worst_count
        worst_games = [game for _, _, game in ranked[start:]]
        return self._map_games_to_sources(worst_games)

    def get_top_brilliant_moves_with_sources_and_ply(
        self, max_moves: int
    ) -> List[Tuple["GameData", str, int]]:
        """Get top N brilliant moves for the current player with source names and ply index.

        Returns a list of (GameData, source_display_name, ref_ply) tuples. Each entry
        corresponds to a single brilliant move in a game; games may appear multiple times
        if they contain multiple brilliant moves.
        """
        return self._get_top_moves_by_assessment_with_sources_and_ply(
            "Brilliant", match_startswith=True, max_moves=max_moves, sort_cpl_ascending=True
        )

    def _get_top_moves_by_assessment_with_sources_and_ply(
        self,
        assessment_match: str,
        match_startswith: bool,
        max_moves: int,
        sort_cpl_ascending: bool,
    ) -> List[Tuple["GameData", str, int]]:
        """Get top N moves for the current player by assessment type, with source names and ply.

        assessment_match: "Brilliant", "Miss", or "Blunder".
        match_startswith: If True, match assessment.startswith(assessment_match); else exact match.
        sort_cpl_ascending: True for brilliant (best first), False for miss/blunder (worst first).
        """
        from app.services.analysis_data_storage_service import AnalysisDataStorageService

        if not self._current_player or max_moves <= 0:
            return []

        analyzed_games = getattr(self, "_current_analyzed_games", []) or []
        if not analyzed_games:
            return []

        records: List[Tuple[float, "GameData", int]] = []

        for game in analyzed_games:
            if not getattr(game, "analyzed", False):
                continue
            is_white_game = (game.white == self._current_player)
            try:
                moves = AnalysisDataStorageService.load_analysis_data(game)
            except Exception:
                moves = None
            if not moves:
                continue

            if is_white_game:
                cpl_field, assess_field, move_field = "cpl_white", "assess_white", "white_move"
            else:
                cpl_field, assess_field, move_field = "cpl_black", "assess_black", "black_move"

            for move in moves:
                move_str = getattr(move, move_field, "")
                if not move_str:
                    continue
                assessment = getattr(move, assess_field, "") or ""
                if match_startswith:
                    if not assessment.startswith(assessment_match):
                        continue
                else:
                    if assessment != assessment_match:
                        continue
                cpl_str = getattr(move, cpl_field, "")
                if not cpl_str:
                    continue
                try:
                    cpl = float(cpl_str)
                except (ValueError, TypeError):
                    continue
                if is_white_game:
                    ply_index = move.move_number * 2 - 1
                else:
                    ply_index = move.move_number * 2
                records.append((cpl, game, ply_index))

        if not records:
            return []
        records.sort(key=lambda x: x[0], reverse=not sort_cpl_ascending)
        top_records = records[:max_moves]

        unique_games = list({rec[1] for rec in top_records})
        game_to_source: Dict["GameData", str] = {}
        for game, source_name in self._map_games_to_sources(unique_games):
            game_to_source[game] = source_name

        results: List[Tuple["GameData", str, int]] = []
        for _, game, ply_index in top_records:
            source_name = game_to_source.get(game)
            if not source_name:
                continue
            results.append((game, source_name, ply_index))
        return results

    def get_top_misses_with_sources_and_ply(
        self, max_moves: int
    ) -> List[Tuple["GameData", str, int]]:
        """Get top N misses (worst CPL first) for the current player with source names and ply."""
        return self._get_top_moves_by_assessment_with_sources_and_ply(
            "Miss", match_startswith=False, max_moves=max_moves, sort_cpl_ascending=False
        )

    def get_top_blunders_with_sources_and_ply(
        self, max_moves: int
    ) -> List[Tuple["GameData", str, int]]:
        """Get top N blunders (worst CPL first) for the current player with source names and ply."""
        return self._get_top_moves_by_assessment_with_sources_and_ply(
            "Blunder", match_startswith=False, max_moves=max_moves, sort_cpl_ascending=False
        )

    def get_opening_tree(
        self,
        max_depth: int = 12,
        min_games: int = 1,
    ) -> Dict[str, Any]:
        """Build an opening move tree from analyzed games for the current player.

        The tree differentiates White vs Black games and attaches ECO / opening
        family information when available.

        Structure:
            {
              "games": total_games_used,
              "white_games": count,
              "black_games": count,
              "children": {
                  "e4": {
                      "games": n_total,
                      "white_games": n_white,
                      "black_games": n_black,
                      "eco": "C20",
                      "opening_name": "King's Pawn Game",
                      "children": { ... }
                  },
                  ...
              }
            }

        Only sequences that appear in at least min_games games are kept.
        """
        from app.services.analysis_data_storage_service import AnalysisDataStorageService

        tree: Dict[str, Any] = {
            "games": 0,
            "white_games": 0,
            "black_games": 0,
            "children": {},
        }

        if not self._current_player:
            return tree

        analyzed_games = getattr(self, "_current_analyzed_games", []) or []
        summaries = getattr(self, "current_game_summaries", []) or []
        if not analyzed_games or not summaries or len(analyzed_games) != len(summaries):
            return tree

        total_games_used = 0

        for game, summary in zip(analyzed_games, summaries):
            if not getattr(game, "analyzed", False):
                continue
            try:
                moves = AnalysisDataStorageService.load_analysis_data(game)
            except Exception:
                moves = None
            if not moves:
                continue

            is_white_game = (game.white == self._current_player)

            # Per-game accuracy for this player:
            # - Overall game accuracy (used for "Game Acc" column)
            # - Opening-phase accuracy (used for "Opening Acc" column)
            if is_white_game:
                player_stats = summary.white_stats
                phase_stats = summary.white_opening
            else:
                player_stats = summary.black_stats
                phase_stats = summary.black_opening

            game_accuracy = player_stats.accuracy if player_stats and player_stats.accuracy is not None else 0.0
            opening_phase_accuracy = phase_stats.accuracy if phase_stats and phase_stats.accuracy is not None else 0.0

            node = tree
            ply_count = 0
            for move in moves:
                if ply_count >= max_depth:
                    break

                # White move
                if move.white_move:
                    ply_count += 1
                    if ply_count > max_depth:
                        break
                    san = move.white_move
                    children = node.setdefault("children", {})
                    child = children.setdefault(
                        san,
                        {
                            "games": 0,
                            "white_games": 0,
                            "black_games": 0,
                            # Aggregated overall game accuracy for this player in games
                            # that reached this node.
                            "game_accuracy_sum": 0.0,
                            "game_accuracy_count": 0,
                            # Aggregated opening-phase accuracy for this player in games
                            # that reached this node.
                            "opening_accuracy_sum": 0.0,
                            "opening_accuracy_count": 0,
                            "children": {},
                        },
                    )
                    child["games"] += 1
                    if is_white_game:
                        child["white_games"] += 1
                    else:
                        child["black_games"] += 1
                    child["game_accuracy_sum"] += float(game_accuracy)
                    child["game_accuracy_count"] += 1
                    child["opening_accuracy_sum"] += float(opening_phase_accuracy)
                    child["opening_accuracy_count"] += 1

                    # Attach ECO info (opening family) if available and not already set
                    fen_after = getattr(move, "fen_white", "") or ""
                    if fen_after and "eco" not in child:
                        eco, name = self._opening_service.get_opening_info(fen_after)
                        if eco or name:
                            if eco:
                                child["eco"] = eco
                            if name:
                                child["opening_name"] = name

                    node = child

                # Black move
                if move.black_move and ply_count < max_depth:
                    ply_count += 1
                    if ply_count > max_depth:
                        break
                    san = move.black_move
                    children = node.setdefault("children", {})
                    child = children.setdefault(
                        san,
                        {
                            "games": 0,
                            "white_games": 0,
                            "black_games": 0,
                            "game_accuracy_sum": 0.0,
                            "game_accuracy_count": 0,
                            "opening_accuracy_sum": 0.0,
                            "opening_accuracy_count": 0,
                            "children": {},
                        },
                    )
                    child["games"] += 1
                    if is_white_game:
                        child["white_games"] += 1
                    else:
                        child["black_games"] += 1
                    child["game_accuracy_sum"] += float(game_accuracy)
                    child["game_accuracy_count"] += 1
                    child["opening_accuracy_sum"] += float(opening_phase_accuracy)
                    child["opening_accuracy_count"] += 1

                    fen_after = getattr(move, "fen_black", "") or ""
                    if fen_after and "eco" not in child:
                        eco, name = self._opening_service.get_opening_info(fen_after)
                        if eco or name:
                            if eco:
                                child["eco"] = eco
                            if name:
                                child["opening_name"] = name

                    node = child

            total_games_used += 1
            tree["games"] += 1
            if is_white_game:
                tree["white_games"] += 1
            else:
                tree["black_games"] += 1

        # Prune nodes that are rarely played
        def prune(node: Dict[str, Any]) -> None:
            children = node.get("children", {})
            to_delete = []
            for san, child in children.items():
                if child.get("games", 0) < min_games:
                    to_delete.append(san)
                else:
                    prune(child)
            for san in to_delete:
                del children[san]

        if min_games > 1:
            prune(tree)

        return tree

    def get_games_for_opening_path(
        self,
        san_path: List[str],
        max_depth: int = 12,
    ) -> List[Tuple["GameData", str, int]]:
        """Return games (with source names and ref_ply) that follow the given SAN path from the start.
        
        san_path is a sequence of SAN moves like ["e4", "c5", "Nf3"] corresponding to
        the path of a node in the opening tree.
        
        ref_ply is set to the ply index of the last move in the SAN path so the
        Search Results tab can jump directly to the defining move of that opening.
        """
        from app.services.analysis_data_storage_service import AnalysisDataStorageService
        
        matches: List[Tuple["GameData", int]] = []
        if not san_path or not self._current_player:
            return []
        
        analyzed_games = getattr(self, "_current_analyzed_games", []) or []
        if not analyzed_games:
            return []
        
        max_plies = min(max_depth, len(san_path))
        
        for game in analyzed_games:
            if not getattr(game, "analyzed", False):
                continue
            try:
                moves = AnalysisDataStorageService.load_analysis_data(game)
            except Exception:
                moves = None
            if not moves:
                continue
            
            path_idx = 0
            ply_count = 0
            matched = True
            
            for move in moves:
                if ply_count >= max_plies:
                    break
                # White move
                if move.white_move:
                    if path_idx >= len(san_path):
                        break
                    ply_count += 1
                    if ply_count > max_plies:
                        break
                    if move.white_move != san_path[path_idx]:
                        matched = False
                        break
                    path_idx += 1
                # Black move
                if move.black_move and ply_count < max_plies:
                    if path_idx >= len(san_path):
                        break
                    ply_count += 1
                    if ply_count > max_plies:
                        break
                    if move.black_move != san_path[path_idx]:
                        matched = False
                        break
                    path_idx += 1
            
            if matched and path_idx == len(san_path):
                # ply_count now points at the last move in san_path
                ref_ply = int(ply_count) if ply_count > 0 else 0
                matches.append((game, ref_ply))
        
        if not matches:
            return []
        
        # Map games to source display names (database file names)
        games_only = [g for (g, _) in matches]
        mapped = self._map_games_to_sources(games_only)  # List[Tuple[GameData, str]]
        game_to_source: Dict["GameData", str] = {game: source for (game, source) in mapped}
        
        results_with_ref: List[Tuple["GameData", str, int]] = []
        for game, ref_ply in matches:
            source_name = game_to_source.get(game)
            if not source_name:
                continue
            results_with_ref.append((game, source_name, ref_ply))
        
        return results_with_ref

    def get_games_for_endgame_filter(
        self,
        raw_type: Optional[str] = None,
        group_key: Optional[str] = None,
    ) -> List[Tuple["GameData", str, int]]:
        """Return games (with source names and ref_ply) that match the given endgame type or group.
        
        Exactly one of raw_type or group_key must be set.
        - raw_type: filter by specific endgame type (e.g. "Rook + Minor Piece").
        - group_key: filter by endgame group (e.g. "Rook" includes all rook endgame types).
        
        ref_ply is set to the ply index corresponding to the middlegame/endgame
        boundary (`middlegame_end` from GameSummary, converted to ply index) so
        the Search Results tab can jump directly to the start of the endgame.
        """
        matches: List[Tuple["GameData", int]] = []
        analyzed_games = getattr(self, "_current_analyzed_games", []) or []
        summaries = getattr(self, "current_game_summaries", []) or []
        if not analyzed_games or not summaries or len(analyzed_games) != len(summaries):
            return []
        if (raw_type is None) == (group_key is None):
            return []
        for game, summary in zip(analyzed_games, summaries):
            if raw_type is not None:
                if getattr(summary, "endgame_type", None) != raw_type:
                    continue
            else:
                if getattr(summary, "endgame_type_group", None) != group_key:
                    continue
            # Convert middlegame_end (full-move number) to a ply index.
            middlegame_end = getattr(summary, "middlegame_end", 0) or 0
            if middlegame_end > 0:
                # Jump to the first full move classified as endgame.
                # Using ply = middlegame_end * 2 aligns with the endgame
                # boundary used in GameSummaryService.
                ref_ply = middlegame_end * 2
            else:
                ref_ply = 0
            matches.append((game, ref_ply))
        
        if not matches:
            return []
        
        games_only = [g for (g, _) in matches]
        mapped = self._map_games_to_sources(games_only)  # List[Tuple[GameData, str]]
        game_to_source: Dict["GameData", str] = {game: source for (game, source) in mapped}
        
        results_with_ref: List[Tuple["GameData", str, int]] = []
        for game, ref_ply in matches:
            source_name = game_to_source.get(game)
            if not source_name:
                continue
            results_with_ref.append((game, source_name, ref_ply))
        
        return results_with_ref

    def get_top_best_games_summary(self, max_best: int) -> Tuple[int, Optional[float], Optional[float]]:
        """Return count and accuracy range for the best-performing games."""
        ranked = self._get_ranked_games_by_cpl()
        if not ranked or max_best <= 0:
            return 0, None, None
        best_count = min(max_best, len(ranked))
        accuracies = [acc for _, acc, _ in ranked[:best_count]]
        return best_count, min(accuracies), max(accuracies)

    def get_top_worst_games_summary(self, max_worst: int, max_best: int) -> Tuple[int, Optional[float], Optional[float]]:
        """Return count and accuracy range for the worst-performing games."""
        ranked = self._get_ranked_games_by_cpl()
        if not ranked or max_worst <= 0:
            return 0, None, None
        n = len(ranked)
        reserved_for_best = min(max_best, n)
        worst_available = max(0, n - reserved_for_best)
        worst_count = min(max_worst, worst_available)
        if worst_count <= 0:
            return 0, None, None
        start = n - worst_count
        accuracies = [acc for _, acc, _ in ranked[start:]]
        return worst_count, min(accuracies), max(accuracies)

    def get_last_unavailable_reason(self) -> str:
        """Get the most recent reason for unavailability."""
        return self._last_unavailable_reason
    
    def get_analyzed_game_count(self, player_name: str, use_all_databases: bool = False) -> tuple:
        """Get analyzed and total game counts for a player.
        
        Args:
            player_name: Player name.
            use_all_databases: If True, check all databases.
            
        Returns:
            Tuple of (analyzed_count, total_count).
        """
        if use_all_databases:
            panel_model = self._database_controller.get_panel_model()
            databases = panel_model.get_all_database_models()
        else:
            active_db = self._database_controller.get_active_database()
            databases = [active_db] if active_db else []
        
        return self.get_analyzed_game_count_with_databases(player_name, databases)
    
    def get_analyzed_game_count_with_databases(self, player_name: str, databases: List[DatabaseModel]) -> tuple:
        """Get analyzed and total game counts for a player using provided databases.
        
        This method avoids repeated get_active_database() calls when checking multiple players.
        
        Args:
            player_name: Player name.
            databases: List of DatabaseModel instances to search.
            
        Returns:
            Tuple of (analyzed_count, total_count).
        """
        if not databases:
            return (0, 0)
        
        player_games, total_count = self.player_stats_service.get_player_games(
            player_name, databases, only_analyzed=False
        )
        analyzed_count = len([g for g in player_games if g.analyzed])
        
        return (analyzed_count, total_count)
    
    def find_game_in_databases(self, game: 'GameData', use_all_databases: bool = True) -> Optional[Tuple['DatabaseModel', int]]:
        """Find a game in the databases and return its database and row index.
        
        Args:
            game: GameData instance to find.
            use_all_databases: If True, search all databases. If False, search only active database.
            
        Returns:
            Tuple of (DatabaseModel, row_index) if found, None otherwise.
        """
        if use_all_databases:
            panel_model = self._database_controller.get_panel_model()
            databases = panel_model.get_all_database_models()
        else:
            active_db = self._database_controller.get_active_database()
            databases = [active_db] if active_db else []
        
        for database in databases:
            row_index = database.find_game(game)
            if row_index is not None:
                return (database, row_index)
        
        return None

    def get_pattern_games_with_sources(self, pattern: "ErrorPattern") -> List[Tuple["GameData", str, int]]:
        """Resolve each pattern game to (game, source_display_name, ref_ply) for opening in a Search Results tab.

        When pattern.related_ref_plies is set (e.g. repeated position patterns, brilliant/miss/blunder),
        returns one entry per (game, ply) so the user can jump directly to that move. ref_ply 0 means no jump.

        Args:
            pattern: ErrorPattern whose related_games (and optionally related_ref_plies) to resolve.

        Returns:
            List of (GameData, source_display_name, ref_ply). Skipped if a game is not found in any database.
        """
        result: List[Tuple["GameData", str, int]] = []
        if not pattern:
            return result
        # Use (game, ref_ply) pairs when available so search results can open at the specific move
        if getattr(pattern, "related_ref_plies", None):
            pairs: List[Tuple["GameData", int]] = pattern.related_ref_plies
            if not pairs:
                return result
            panel_model = self._database_controller.get_panel_model()
            for game, ref_ply in pairs:
                found = self.find_game_in_databases(game, use_all_databases=True)
                if not found:
                    continue
                database, _ = found
                identifier = panel_model.find_database_by_model(database)
                display_name = "Clipboard" if identifier == "clipboard" else Path(identifier).stem
                result.append((game, display_name, ref_ply))
            return result
        # Fallback: no ref_ply, one row per game
        if not pattern.related_games:
            return result
        panel_model = self._database_controller.get_panel_model()
        for game in pattern.related_games:
            found = self.find_game_in_databases(game, use_all_databases=True)
            if not found:
                continue
            database, _ = found
            identifier = panel_model.find_database_by_model(database)
            display_name = "Clipboard" if identifier == "clipboard" else Path(identifier).stem
            result.append((game, display_name, 0))
        return result

    def get_activity_heatmap_day_games_with_sources(
        self, day_ordinal: int
    ) -> List[Tuple["GameData", str, int]]:
        """Games whose activity-heatmap effective calendar day matches ``day_ordinal`` (Search Results tab).

        Uses the same partial-date rules as the heatmap. Order follows aggregated game order.
        """
        result: List[Tuple["GameData", str, int]] = []
        stats = self.current_stats
        if not stats or day_ordinal < 0:
            return result
        pairs = list(getattr(stats, "activity_heatmap_per_game_ordinals", None) or [])
        indices = list(getattr(stats, "activity_heatmap_source_game_indices", None) or [])
        if len(indices) != len(pairs):
            return result
        analyzed_games = getattr(self, "_current_analyzed_games", []) or []
        usr = UserSettingsService.get_instance().get_model().get_player_stats_activity_heatmap()
        partial = str(usr.get("partial_dates", "exclude"))
        panel_model = self._database_controller.get_panel_model()
        for game_idx, (full_o, trends_o) in zip(indices, pairs):
            eff = effective_ordinal_for_heatmap(partial, full_o, trends_o)
            if eff is None or int(eff) != int(day_ordinal):
                continue
            if not (0 <= game_idx < len(analyzed_games)):
                continue
            game = analyzed_games[game_idx]
            found = self.find_game_in_databases(game, use_all_databases=True)
            if not found:
                continue
            database, _ = found
            identifier = panel_model.find_database_by_model(database)
            display_name = "Clipboard" if identifier == "clipboard" else Path(identifier).stem
            result.append((game, display_name, 0))
        return result

    def highlight_rows(self, database: DatabaseModel, row_indices: List[int]) -> None:
        """Highlight rows in the database panel through the database controller.
        
        Args:
            database: DatabaseModel instance.
            row_indices: List of row indices to highlight.
        """
        if self._database_controller:
            self._database_controller.highlight_rows(database, row_indices)
    
    def show_progress(self) -> None:
        """Show the progress bar."""
        self._progress_service.show_progress()
    
    def hide_progress(self) -> None:
        """Hide the progress bar."""
        self._progress_service.hide_progress()
    
    def set_progress(self, progress: int) -> None:
        """Set progress value (0-100).
        
        Args:
            progress: Progress value (0-100).
        """
        self._progress_service.set_progress(progress)
    
    def set_status(self, status: str) -> None:
        """Set status message.
        
        Args:
            status: Status message to display.
        """
        self._progress_service.set_status(status)
    
    def set_indeterminate(self, indeterminate: bool) -> None:
        """Set whether progress bar is indeterminate.
        
        Args:
            indeterminate: True for indeterminate progress, False for determinate.
        """
        self._progress_service.set_indeterminate(indeterminate)
    
    def _emit_unavailable(self, reason: str) -> None:
        """Emit unavailable signal with reason."""
        self._last_unavailable_reason = reason
        self.current_stats = None
        self.current_patterns = []
        self.current_game_summaries = []
        self._current_analyzed_games = []
        self._last_analyzed_games = []
        self.stats_unavailable.emit(reason)
    
    # Source and player selection management
    
    def set_source_selection(self, index: int) -> None:
        """Set the data source selection.

        Args:
            index: 0=None, 1=Active Database, 2=All Open Databases, 3=Selected (Active), 4=Selected (All)
        """
        if self._source_selection == index:
            return

        self._source_selection = index

        if index == 0:
            # "None" selected - disable updates
            self._use_all_databases = False
            self._cancel_stats_worker()
            self._current_player = None
            self.player_selection_cleared.emit()
        else:
            # 1=Active, 2=All DBs, 3=Selected (Active), 4=Selected (All)
            self._use_all_databases = (index == 2 or index == 4)
            self._connect_to_database_changes()
            self._schedule_dropdown_update()

            # If a player is selected, recalculate stats with new source
            if self._current_player:
                QTimer.singleShot(200, self._schedule_stats_recalculation)

        self.source_selection_changed.emit(index)

    def get_source_selection(self) -> int:
        """Get the current source selection.

        Returns:
            0=None, 1=Active Database, 2=All Open Databases, 3=Selected (Active), 4=Selected (All)
        """
        return self._source_selection
    
    def set_player_selection(self, player_name: Optional[str]) -> None:
        """Set the selected player.
        
        Args:
            player_name: Player name to select, or None to clear selection.
        """
        if self._current_player == player_name:
            return
        
        if player_name is None:
            # Clear selection
            self._cancel_stats_worker()
            self._current_player = None
            self.player_selection_cleared.emit()
        else:
            self._current_player = player_name
            self._schedule_stats_recalculation()
    
    def get_current_player(self) -> Optional[str]:
        """Get the currently selected player."""
        return self._current_player
    
    def get_use_all_databases(self) -> bool:
        """Get whether using all databases."""
        return self._use_all_databases

    def set_get_selected_games_callback(self, callback: Optional[Callable[[bool], List["GameData"]]]) -> None:
        """Set the callback used to obtain selected games when source is 'Selected games (Active)' or 'Selected games (All)'.
        Callback receives active_only: bool and returns List[GameData]. Injected by app layer (e.g. MainWindow)."""
        self._get_selected_games_callback = callback

    def notify_selection_changed(self) -> None:
        """Called when database table selection changes. Refreshes dropdown and stats if source is Selected games."""
        if self._source_selection not in (3, 4):
            return
        self._selection_debounce_timer.stop()
        self._selection_debounce_timer.start(self._selection_debounce_ms)

    def _resolve_selected_games_for_dropdown(self) -> List["GameData"]:
        """Load selected games for sources 3/4 (main thread). Returns [] if unavailable."""
        if self._source_selection not in (3, 4):
            return []
        if not self._get_selected_games_callback:
            return []
        try:
            raw = self._get_selected_games_callback(active_only=(self._source_selection == 3))
            return list(raw) if raw else []
        except Exception as e:
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error getting selected games: {e}", exc_info=e)
            return []

    def _on_selection_changed_debounced(self) -> None:
        """After selection settles: one snapshot drives dropdown + stats (sources 3/4 only)."""
        if self._source_selection not in (3, 4):
            return
        snapshot = self._resolve_selected_games_for_dropdown()
        self._schedule_dropdown_update(snapshot)
        if self._current_player and not self._bulk_analysis_active:
            self._schedule_stats_recalculation(snapshot)

    # Worker management
    
    def _cancel_stats_worker(self) -> None:
        """Cancel any running stats worker and clean up. Never deletes a running QThread."""
        if self._stats_worker:
            try:
                is_running = self._stats_worker.isRunning()
            except RuntimeError:
                # Worker has been deleted, clean up reference
                self._stats_worker = None
                is_running = False
            
            if is_running:
                # Request cooperative shutdown; do NOT wait or deleteLater here.
                # _on_stats_worker_finished will perform cleanup when the thread actually stops.
                self._stats_worker.cancel()
                return
            # Worker not running: safe to disconnect and delete
            try:
                self._stats_worker.stats_ready.disconnect()
                self._stats_worker.stats_unavailable.disconnect()
                self._stats_worker.progress_update.disconnect()
                self._stats_worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._stats_worker.deleteLater()
            self._stats_worker = None
    
    def _schedule_stats_recalculation(
        self, selected_games_snapshot: Any = _DEFAULT_SELECTION_GAMES
    ) -> None:
        """Schedule an asynchronous statistics recalculation. Coalesces requests while a worker is running.

        If selected_games_snapshot is a list (possibly empty), use it for sources 3/4 instead of calling
        get_selected_games again (same tick as dropdown refresh).
        """
        if not self._current_player:
            return
        if self._bulk_analysis_active:
            return
        
        # If a worker is already running, mark that we need one more run when it finishes
        if self._stats_worker and self._stats_worker.isRunning():
            self._recalc_pending = True
            return
        
        self._recalc_pending = False
        self._cancel_stats_worker()  # Clean up any finished worker

        explicit_snapshot = selected_games_snapshot is not _DEFAULT_SELECTION_GAMES
        player_games_arg: Optional[List["GameData"]] = None
        if self._source_selection in (3, 4):
            if explicit_snapshot:
                raw = list(selected_games_snapshot) if selected_games_snapshot else []
                player_games_arg = [
                    g for g in raw
                    if (g.white == self._current_player or g.black == self._current_player)
                ]
            elif self._get_selected_games_callback:
                try:
                    selected = self._get_selected_games_callback(active_only=(self._source_selection == 3))
                    if selected:
                        player_games_arg = [
                            g for g in selected
                            if (g.white == self._current_player or g.black == self._current_player)
                        ]
                except Exception as e:
                    logging_service = LoggingService.get_instance()
                    logging_service.error(f"Error getting selected games for stats: {e}", exc_info=e)

        ts_user = UserSettingsService.get_instance().get_model().get_player_stats_time_series()
        self._stats_worker = PlayerStatsCalculationWorker(
            self,
            self._current_player,
            self._use_all_databases,
            player_games=player_games_arg,
            time_series_user_settings=ts_user,
        )
        self._stats_worker.stats_ready.connect(self._on_stats_worker_ready)
        self._stats_worker.stats_unavailable.connect(self._on_stats_worker_unavailable)
        self._stats_worker.progress_update.connect(self._on_stats_worker_progress)
        self._stats_worker.finished.connect(self._on_stats_worker_finished)
        self.stats_recalculation_started.emit()
        self._stats_worker.start()
    
    def _on_stats_worker_ready(self, stats: AggregatedPlayerStats, patterns: List[ErrorPattern], summaries: List[GameSummary]) -> None:
        """Handle stats worker ready signal."""
        self.current_stats = stats
        self.current_patterns = patterns
        self.current_game_summaries = summaries
        # Use the same analyzed games that were used for this calculation
        self._current_analyzed_games = getattr(self, "_last_analyzed_games", [])
        self.stats_updated.emit(stats, patterns, summaries)
    
    def _on_stats_worker_unavailable(self, reason: str) -> None:
        """Handle stats worker unavailable signal."""
        self._emit_unavailable(reason)
    
    def _on_stats_worker_progress(self, progress: int, status: str) -> None:
        """Handle stats worker progress update."""
        self._progress_service.set_progress(progress)
        self._progress_service.set_status(status)
    
    def _on_stats_worker_finished(self) -> None:
        """Handle stats worker finished signal. Schedules one recalc if requested while worker was running."""
        worker = self.sender()
        if worker and worker == self._stats_worker:
            try:
                worker.stats_ready.disconnect()
                worker.stats_unavailable.disconnect()
                worker.progress_update.disconnect()
                worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._stats_worker = None
            worker.deleteLater()
            if self._recalc_pending and self._current_player and not self._bulk_analysis_active:
                self._recalc_pending = False
                QTimer.singleShot(0, self._schedule_stats_recalculation)
    
    def _dispose_dropdown_worker_non_running(self) -> None:
        """Disconnect and delete a finished dropdown worker (never call while thread is running)."""
        if not self._dropdown_worker:
            return
        try:
            if self._dropdown_worker.isRunning():
                return
        except RuntimeError:
            self._dropdown_worker = None
            return
        try:
            self._dropdown_worker.players_ready.disconnect()
            self._dropdown_worker.progress_update.disconnect()
            self._dropdown_worker.finished.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._dropdown_worker.deleteLater()
        self._dropdown_worker = None

    def _start_dropdown_worker(self, selected_games: Optional[List["GameData"]]) -> None:
        """Create and start PlayerDropdownWorker (no running worker must be held)."""
        try:
            self._dropdown_worker = PlayerDropdownWorker(
                self, self._use_all_databases, selected_games=selected_games
            )
            self._dropdown_worker.players_ready.connect(self._on_dropdown_players_ready)
            self._dropdown_worker.progress_update.connect(self._on_dropdown_progress)
            self._dropdown_worker.finished.connect(self._on_dropdown_worker_finished)
            self._dropdown_worker.start()
        except Exception as e:
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error starting dropdown worker: {e}", exc_info=e)
            if self._dropdown_worker:
                self._dropdown_worker.deleteLater()
                self._dropdown_worker = None

    def _schedule_dropdown_update(self, selected_games_snapshot: Any = _DEFAULT_SELECTION_GAMES) -> None:
        """Schedule an asynchronous dropdown update.

        Pass a list for sources 3/4 to reuse a snapshot (e.g. debounced selection). Default fetches via callback.
        """
        if self._source_selection == 0:
            return

        explicit_snapshot = selected_games_snapshot is not _DEFAULT_SELECTION_GAMES
        if self._source_selection in (3, 4):
            if explicit_snapshot:
                sg = list(selected_games_snapshot) if selected_games_snapshot else []
            else:
                sg = self._resolve_selected_games_for_dropdown()
        else:
            sg = None

        if self._dropdown_worker:
            try:
                is_running = self._dropdown_worker.isRunning()
            except RuntimeError:
                self._dispose_dropdown_worker_non_running()
                is_running = False
        else:
            is_running = False

        if is_running:
            self._dropdown_worker.cancel()
            self._dropdown_restart_pending = True
            self._dropdown_restart_explicit_snapshot = explicit_snapshot
            self._dropdown_restart_snapshot = (
                list(sg) if explicit_snapshot and self._source_selection in (3, 4) else None
            )
            return

        self._dispose_dropdown_worker_non_running()
        self._start_dropdown_worker(sg)
    
    def _on_dropdown_players_ready(self, players_with_analyzed: List[Tuple[str, int, int]]) -> None:
        """Handle players ready from dropdown worker."""
        # Don't populate if "None" is selected as data source
        if self._source_selection == 0:
            return
        
        self.players_ready.emit(players_with_analyzed)
    
    def _on_dropdown_progress(self, progress: int, status: str) -> None:
        """Handle progress update from dropdown worker."""
        # Optionally show progress in status bar for long operations
        pass
    
    def _on_dropdown_worker_finished(self) -> None:
        """Handle dropdown worker finished signal."""
        worker = self.sender()
        if worker and worker == self._dropdown_worker:
            try:
                worker.players_ready.disconnect()
                worker.progress_update.disconnect()
                worker.finished.disconnect()
            except (RuntimeError, TypeError):
                pass
            self._dropdown_worker = None
            worker.deleteLater()

            if self._dropdown_restart_pending:
                self._dropdown_restart_pending = False
                explicit = self._dropdown_restart_explicit_snapshot
                snap = self._dropdown_restart_snapshot
                self._dropdown_restart_explicit_snapshot = False
                self._dropdown_restart_snapshot = None
                if explicit and snap is not None:
                    QTimer.singleShot(0, lambda s=snap: self._schedule_dropdown_update(s))
                else:
                    QTimer.singleShot(0, self._schedule_dropdown_update)
    
    # Database connection management
    
    def _connect_to_database_panel_model(self) -> None:
        """Connect to database panel model signals for active database changes."""
        if not self._database_controller:
            return
        
        panel_model = self._database_controller.get_panel_model()
        if not panel_model:
            return
        
        # Disconnect first to avoid duplicate connections
        try:
            panel_model.active_database_changed.disconnect(self._on_active_database_changed)
            panel_model.database_added.disconnect(self._on_database_added)
            panel_model.database_removed.disconnect(self._on_database_removed)
        except (RuntimeError, TypeError):
            pass  # Not connected yet, that's fine
        
        # Connect to active database changes
        panel_model.active_database_changed.connect(self._on_active_database_changed)
        panel_model.database_added.connect(self._on_database_added)
        panel_model.database_removed.connect(self._on_database_removed)
    
    def _connect_to_database_changes(self) -> None:
        """Connect to DatabaseModel stats_relevant_data_change (not generic dataChanged)."""
        if not self._database_controller:
            return
        
        # Disconnect from all previously connected databases
        for database in self._connected_databases:
            try:
                database.stats_relevant_data_change.disconnect(self._on_stats_relevant_data_change)
            except (RuntimeError, TypeError):
                pass
        
        self._connected_databases.clear()
        
        # Connect to all current databases
        panel_model = self._database_controller.get_panel_model()
        if panel_model:
            databases = panel_model.get_all_database_models()
            for database in databases:
                database.stats_relevant_data_change.connect(self._on_stats_relevant_data_change)
                self._connected_databases.append(database)
    
    def _on_active_database_changed(self, database) -> None:
        """Handle active database change - repopulate dropdown if 'Active Database' is selected."""
        # Reconnect to database changes
        self._connect_to_database_changes()
        
        # Only update if a source is selected (not "None") and "Active Database" is selected (not "All Open Databases")
        if self._source_selection == 0:
            # "None" selected - don't update
            return

        # Active Database source (source_selection == 1) can temporarily become None when
        # the user closes the active DB. In that case, the dropdown should be refreshed
        # to an empty list, and once a new active DB is opened, it should repopulate.
        # Crucially, we do not switch the source to "None" here, otherwise later active
        # database changes won't trigger dropdown updates.

        # Only repopulate if "Active Database" is selected (not "All Open Databases")
        if not self._use_all_databases:
            self._schedule_dropdown_update()
            # If a player was selected, recalculate (might be in different database now)
            if self._current_player and not self._bulk_analysis_active:
                self._schedule_stats_recalculation()
    
    def _on_database_added(self, identifier: str, info) -> None:
        """Handle database added - connect to its signals."""
        if info and info.model:
            info.model.stats_relevant_data_change.connect(self._on_stats_relevant_data_change)
            if info.model not in self._connected_databases:
                self._connected_databases.append(info.model)
            # Always trigger dropdown update when database is added
            # (will update if using all databases, or if this becomes the active database)
            # Use QTimer to ensure this happens after the database is fully initialized
            QTimer.singleShot(200, self._schedule_dropdown_update)
    
    def _on_database_removed(self, identifier: str) -> None:
        """Handle database removed - disconnect from its signals."""
        # Remove from connected list (will be cleaned up on next connection refresh)
        # The database model may already be destroyed, so we just refresh connections
        self._connect_to_database_changes()
        # If a source is selected (Active or All), treat removal like a data change and
        # use the existing debounce timer so multiple closes (e.g. \"Close all but this\")
        # only trigger a single recalculation.
        if self._source_selection != 0:
            self._database_update_timer.stop()
            self._database_update_timer.start(self._database_update_debounce_ms)
    
    def _on_stats_relevant_data_change(self) -> None:
        """Handle stats-relevant database mutations (not sort/unsaved-only). Debounce and update."""
        self._database_update_timer.stop()
        self._database_update_timer.start(self._database_update_debounce_ms)
    
    def _on_database_update_debounced(self) -> None:
        """Handle debounced database update - refresh dropdown and recalculate stats."""
        # Update dropdown asynchronously
        self._schedule_dropdown_update()
        
        # If a player is selected, update their counts and recalculate stats
        if self._current_player and not self._bulk_analysis_active:
            self._schedule_stats_recalculation()

