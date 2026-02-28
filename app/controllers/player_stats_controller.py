"""Controller for orchestrating player statistics calculations."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QMutex, QMutexLocker, QTimer

from app.models.database_model import DatabaseModel

if TYPE_CHECKING:
    from app.models.database_model import GameData
from app.models.database_panel_model import DatabasePanelModel
from app.models.game_model import GameModel
from app.services.player_stats_service import PlayerStatsService, AggregatedPlayerStats
from app.services.error_pattern_service import ErrorPatternService, ErrorPattern
from app.services.game_summary_service import GameSummaryService, GameSummary
from app.services.progress_service import ProgressService
from app.controllers.game_controller import GameController
from app.services.logging_service import LoggingService


class PlayerDropdownWorker(QThread):
    """Worker thread for populating player dropdown asynchronously."""
    
    players_ready = pyqtSignal(list)  # List of (player_name, game_count, analyzed_count) tuples
    progress_update = pyqtSignal(int, str)  # progress_percent, status_message
    
    def __init__(self, stats_controller: "PlayerStatsController", use_all_databases: bool) -> None:
        """Initialize the dropdown worker.
        
        Args:
            stats_controller: PlayerStatsController instance.
            use_all_databases: Whether to use all databases or just active.
        """
        super().__init__()
        self.stats_controller = stats_controller
        self.use_all_databases = use_all_databases
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


class PlayerStatsCalculationWorker(QThread):
    """Worker thread for calculating player statistics asynchronously."""
    
    stats_ready = pyqtSignal(object, list, list)  # AggregatedPlayerStats, List[ErrorPattern], List[GameSummary]
    stats_unavailable = pyqtSignal(str)  # Reason key
    progress_update = pyqtSignal(int, str)  # progress_percent, status_message
    
    def __init__(self, stats_controller: "PlayerStatsController", player_name: str, use_all_databases: bool) -> None:
        """Initialize the stats calculation worker.
        
        Args:
            stats_controller: PlayerStatsController instance.
            player_name: Player name to analyze.
            use_all_databases: Whether to use all databases or just active.
        """
        super().__init__()
        self.stats_controller = stats_controller
        self.player_name = player_name
        self.use_all_databases = use_all_databases
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
        try:
            if self._is_cancelled():
                return
            
            if not self.player_name or not self.player_name.strip():
                self.stats_unavailable.emit("no_player")
                return
            
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
                return
            
            # Separate analyzed and unanalyzed
            analyzed_games = [g for g in player_games if g.analyzed]
            if not analyzed_games:
                self.stats_unavailable.emit("no_analyzed_games")
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
                self.player_name, analyzed_games, self.stats_controller._game_controller, progress_callback, cancellation_check
            )
            
            if self._is_cancelled():
                return
            
            if not aggregated_stats:
                self.stats_unavailable.emit("calculation_error")
                return
            
            # Detect error patterns (using summaries already calculated in parallel)
            self.progress_update.emit(90, "Detecting error patterns...")
            
            error_patterns = self.stats_controller.error_pattern_service.detect_error_patterns(
                self.player_name, analyzed_games, aggregated_stats, game_summaries
            )
            
            if not self._is_cancelled():
                try:
                    self.progress_update.emit(100, f"Statistics calculated for {self.player_name}")
                    self.stats_ready.emit(aggregated_stats, error_patterns, game_summaries)
                except RuntimeError:
                    # Receiver might be deleted, ignore
                    pass
        
        except Exception as e:
            # Emit error signal
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error in PlayerStatsCalculationWorker: {e}", exc_info=e)
            self.stats_unavailable.emit("error")


class PlayerStatsController(QObject):
    """Controller responsible for producing and exposing player statistics data."""
    
    stats_updated = pyqtSignal(object, list, list)  # AggregatedPlayerStats, List[ErrorPattern], List[GameSummary]
    stats_unavailable = pyqtSignal(str)  # Reason key (e.g., "no_player", "no_analyzed_games")
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
        
        self.current_stats: Optional[AggregatedPlayerStats] = None
        self.current_patterns: List[ErrorPattern] = []
        self.current_game_summaries: List[GameSummary] = []
        # Keep the analyzed games used for the current stats so we can rank individual games.
        self._current_analyzed_games: List["GameData"] = []
        self._last_analyzed_games: List["GameData"] = []
        self._last_unavailable_reason: str = "no_player"
        self._current_player: Optional[str] = None
        self._use_all_databases: bool = False
        self._source_selection: int = 0  # 0=None, 1=Active Database, 2=All Open Databases
        
        # Worker threads
        self._dropdown_worker: Optional[PlayerDropdownWorker] = None
        self._stats_worker: Optional[PlayerStatsCalculationWorker] = None
        
        # Database change tracking
        self._connected_databases: List[DatabaseModel] = []
        self._database_update_timer = QTimer()
        self._database_update_timer.setSingleShot(True)
        self._database_update_timer.timeout.connect(self._on_database_update_debounced)
        self._database_update_debounce_ms = 500  # Debounce database updates by 500ms
        
        # Initialize ProgressService
        self._progress_service = ProgressService.get_instance()
        
        # Connect to game model for auto-selection
        if self._game_model:
            self._game_model.active_game_changed.connect(self._on_active_game_changed)
        
        # Connect to database panel model
        self._connect_to_database_panel_model()
    
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

    def get_pattern_games_with_sources(self, pattern: "ErrorPattern") -> List[Tuple["GameData", str]]:
        """Resolve each pattern game to (game, source_display_name) for opening in a Search Results tab.

        Args:
            pattern: ErrorPattern whose related_games to resolve.

        Returns:
            List of (GameData, source_display_name). Skipped if a game is not found in any database.
        """
        result: List[Tuple["GameData", str]] = []
        if not pattern or not pattern.related_games:
            return result
        panel_model = self._database_controller.get_panel_model()
        for game in pattern.related_games:
            found = self.find_game_in_databases(game, use_all_databases=True)
            if not found:
                continue
            database, _ = found
            identifier = panel_model.find_database_by_model(database)
            if identifier == "clipboard":
                display_name = "Clipboard"
            else:
                display_name = Path(identifier).stem
            result.append((game, display_name))
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
            index: 0=None, 1=Active Database, 2=All Open Databases
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
            # "Active Database" (index 1) or "All Open Databases" (index 2) selected
            self._use_all_databases = (index == 2)
            self._connect_to_database_changes()
            self._schedule_dropdown_update()
            
            # If a player is selected, recalculate stats with new source
            if self._current_player:
                QTimer.singleShot(200, self._schedule_stats_recalculation)
        
        self.source_selection_changed.emit(index)
    
    def get_source_selection(self) -> int:
        """Get the current source selection.
        
        Returns:
            0=None, 1=Active Database, 2=All Open Databases
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
    
    # Worker management
    
    def _cancel_stats_worker(self) -> None:
        """Cancel any running stats worker and clean up."""
        if self._stats_worker:
            try:
                is_running = self._stats_worker.isRunning()
            except RuntimeError:
                # Worker has been deleted, clean up reference
                self._stats_worker = None
                is_running = False
            
            if is_running:
                self._stats_worker.cancel()
                # Wait for worker to finish (with longer timeout for ProcessPoolExecutor shutdown)
                if not self._stats_worker.wait(10000):  # Wait up to 10 seconds
                    # If it didn't finish, disconnect signals and delete later
                    try:
                        self._stats_worker.stats_ready.disconnect()
                        self._stats_worker.stats_unavailable.disconnect()
                        self._stats_worker.progress_update.disconnect()
                        self._stats_worker.finished.disconnect()
                    except (RuntimeError, TypeError):
                        pass
                    self._stats_worker.deleteLater()
                    self._stats_worker = None
                else:
                    # Worker finished, disconnect and clean up
                    try:
                        self._stats_worker.stats_ready.disconnect()
                        self._stats_worker.stats_unavailable.disconnect()
                        self._stats_worker.progress_update.disconnect()
                        self._stats_worker.finished.disconnect()
                    except (RuntimeError, TypeError):
                        pass
                    self._stats_worker.deleteLater()
                    self._stats_worker = None
            else:
                # Worker not running, just clean up
                try:
                    self._stats_worker.stats_ready.disconnect()
                    self._stats_worker.stats_unavailable.disconnect()
                    self._stats_worker.progress_update.disconnect()
                    self._stats_worker.finished.disconnect()
                except (RuntimeError, TypeError):
                    pass
                self._stats_worker.deleteLater()
                self._stats_worker = None
    
    def _schedule_stats_recalculation(self) -> None:
        """Schedule an asynchronous statistics recalculation."""
        if not self._current_player:
            return
        
        # Cancel any running worker
        self._cancel_stats_worker()
        
        # Create and start new worker
        self._stats_worker = PlayerStatsCalculationWorker(
            self,
            self._current_player,
            self._use_all_databases
        )
        self._stats_worker.stats_ready.connect(self._on_stats_worker_ready)
        self._stats_worker.stats_unavailable.connect(self._on_stats_worker_unavailable)
        self._stats_worker.progress_update.connect(self._on_stats_worker_progress)
        self._stats_worker.finished.connect(self._on_stats_worker_finished)
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
        """Handle stats worker finished signal."""
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
    
    def _schedule_dropdown_update(self) -> None:
        """Schedule an asynchronous dropdown update."""
        # Don't populate if "None" is selected as data source
        if self._source_selection == 0:
            return
        
        # If a worker is already running, cancel it and wait for it to finish
        if self._dropdown_worker:
            try:
                is_running = self._dropdown_worker.isRunning()
            except RuntimeError:
                # Worker has been deleted, clean up reference
                self._dropdown_worker = None
                is_running = False
            
            if is_running:
                self._dropdown_worker.cancel()
                # Wait for worker to finish (with timeout)
                if not self._dropdown_worker.wait(2000):  # Wait up to 2 seconds
                    # If it didn't finish, disconnect signals and delete later
                    try:
                        self._dropdown_worker.players_ready.disconnect()
                        self._dropdown_worker.progress_update.disconnect()
                        self._dropdown_worker.finished.disconnect()
                    except (RuntimeError, TypeError):
                        pass
                    self._dropdown_worker.deleteLater()
                    self._dropdown_worker = None
                else:
                    # Worker finished, disconnect and clean up
                    try:
                        self._dropdown_worker.players_ready.disconnect()
                        self._dropdown_worker.progress_update.disconnect()
                        self._dropdown_worker.finished.disconnect()
                    except (RuntimeError, TypeError):
                        pass
                    self._dropdown_worker.deleteLater()
                    self._dropdown_worker = None
            else:
                # Worker not running, just clean up
                try:
                    self._dropdown_worker.players_ready.disconnect()
                    self._dropdown_worker.progress_update.disconnect()
                    self._dropdown_worker.finished.disconnect()
                except (RuntimeError, TypeError):
                    pass
                self._dropdown_worker.deleteLater()
                self._dropdown_worker = None
        
        # Create and start new worker
        try:
            self._dropdown_worker = PlayerDropdownWorker(self, self._use_all_databases)
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
        """Connect to DatabaseModel dataChanged signals to detect game updates."""
        if not self._database_controller:
            return
        
        # Disconnect from all previously connected databases
        for database in self._connected_databases:
            try:
                database.dataChanged.disconnect(self._on_database_data_changed)
            except (RuntimeError, TypeError):
                pass
        
        self._connected_databases.clear()
        
        # Connect to all current databases
        panel_model = self._database_controller.get_panel_model()
        if panel_model:
            databases = panel_model.get_all_database_models()
            for database in databases:
                database.dataChanged.connect(self._on_database_data_changed)
                self._connected_databases.append(database)
    
    def _on_active_database_changed(self, database) -> None:
        """Handle active database change - repopulate dropdown if 'Active Database' is selected."""
        # Reconnect to database changes
        self._connect_to_database_changes()
        
        # Only update if a source is selected (not "None") and "Active Database" is selected (not "All Open Databases")
        if self._source_selection == 0:
            # "None" selected - don't update
            return

        # If "Active Database" is selected and the active database was closed/cleared,
        # switch to "None" to avoid showing stale stats.
        if self._source_selection == 1 and database is None:
            self.set_source_selection(0)
            return
        
        # Only repopulate if "Active Database" is selected (not "All Open Databases")
        if not self._use_all_databases:
            self._schedule_dropdown_update()
            # If a player was selected, recalculate (might be in different database now)
            if self._current_player:
                self._schedule_stats_recalculation()
    
    def _on_database_added(self, identifier: str, info) -> None:
        """Handle database added - connect to its signals."""
        if info and info.model:
            info.model.dataChanged.connect(self._on_database_data_changed)
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
    
    def _on_database_data_changed(self, top_left, bottom_right, roles=None) -> None:
        """Handle database data changed signal - debounce and update."""
        # Debounce the update to avoid excessive recalculations
        self._database_update_timer.stop()
        self._database_update_timer.start(self._database_update_debounce_ms)
    
    def _on_database_update_debounced(self) -> None:
        """Handle debounced database update - refresh dropdown and recalculate stats."""
        # Update dropdown asynchronously
        self._schedule_dropdown_update()
        
        # If a player is selected, update their counts and recalculate stats
        if self._current_player:
            self._schedule_stats_recalculation()

