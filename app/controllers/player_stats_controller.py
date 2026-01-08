"""Controller for orchestrating player statistics calculations."""

from typing import Any, Dict, List, Optional, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

from app.models.database_model import DatabaseModel
from app.models.database_panel_model import DatabasePanelModel
from app.models.game_model import GameModel
from app.services.player_stats_service import PlayerStatsService, AggregatedPlayerStats
from app.services.error_pattern_service import ErrorPatternService, ErrorPattern
from app.services.game_summary_service import GameSummaryService, GameSummary
from app.controllers.game_controller import GameController


class PlayerStatsController(QObject):
    """Controller responsible for producing and exposing player statistics data."""
    
    stats_updated = pyqtSignal(object, list, list)  # AggregatedPlayerStats, List[ErrorPattern], List[GameSummary]
    stats_unavailable = pyqtSignal(str)  # Reason key (e.g., "no_player", "no_analyzed_games")
    
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
        self._last_unavailable_reason: str = "no_player"
        self._current_player: Optional[str] = None
        self._use_all_databases: bool = False
        
        # Connect to game model for auto-selection
        if self._game_model:
            self._game_model.active_game_changed.connect(self._on_active_game_changed)
    
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
        
        Uses progress reporting and processes events to keep UI responsive during long operations.
        
        Args:
            player_name: Player name to analyze.
            use_all_databases: If True, analyze across all open databases.
                             If False, analyze only active database.
        """
        from app.services.progress_service import ProgressService
        from PyQt6.QtWidgets import QApplication
        
        progress_service = ProgressService.get_instance()
        progress_service.show_progress()
        progress_service.set_indeterminate(False)
        progress_service.set_progress(0)
        progress_service.set_status(f"Calculating statistics for {player_name}...")
        
        # Process events to show progress immediately
        QApplication.processEvents()
        
        try:
            self._current_player = player_name
            self._use_all_databases = use_all_databases
            
            if not player_name or not player_name.strip():
                self._emit_unavailable("no_player")
                return
            
            # Get databases
            progress_service.set_progress(5)
            progress_service.set_status("Loading databases...")
            QApplication.processEvents()
            
            if use_all_databases:
                panel_model = self._database_controller.get_panel_model()
                databases = panel_model.get_all_database_models()
            else:
                active_db = self._database_controller.get_active_database()
                databases = [active_db] if active_db else []
            
            if not databases:
                self._emit_unavailable("no_database")
                return
            
            # Get player games
            progress_service.set_progress(10)
            progress_service.set_status("Finding player games...")
            QApplication.processEvents()
            
            player_games, total_count = self.player_stats_service.get_player_games(
                player_name, databases, only_analyzed=False
            )
            
            if not player_games:
                self._emit_unavailable("player_not_found")
                return
            
            # Separate analyzed and unanalyzed
            analyzed_games = [g for g in player_games if g.analyzed]
            if not analyzed_games:
                self._emit_unavailable("no_analyzed_games")
                return
            
            # Aggregate statistics (includes parallel game summary calculation)
            progress_service.set_progress(20)
            progress_service.set_status(f"Aggregating statistics from {len(analyzed_games)} game(s)...")
            QApplication.processEvents()
            
            aggregated_stats, game_summaries = self.player_stats_service.aggregate_player_statistics(
                player_name, analyzed_games, self._game_controller
            )
            
            if not aggregated_stats:
                self._emit_unavailable("calculation_error")
                return
            
            # Detect error patterns (using summaries already calculated in parallel)
            progress_service.set_progress(90)
            progress_service.set_status("Detecting error patterns...")
            QApplication.processEvents()
            
            error_patterns = self.error_pattern_service.detect_error_patterns(
                player_name, analyzed_games, aggregated_stats, game_summaries
            )
            
            self.current_stats = aggregated_stats
            self.current_patterns = error_patterns
            self.current_game_summaries = game_summaries
            
            # Emit signal with results
            progress_service.set_progress(100)
            progress_service.set_status(f"Statistics calculated for {player_name}")
            QApplication.processEvents()
            
            self.stats_updated.emit(aggregated_stats, error_patterns, game_summaries)
            
        except Exception as e:
            # Avoid crashing the UI
            import sys
            print(f"Error calculating player statistics: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            self._emit_unavailable("error")
        finally:
            # Always hide progress, even if there's an error
            QApplication.processEvents()
            progress_service.hide_progress()
    
    def get_current_stats(self) -> Optional[AggregatedPlayerStats]:
        """Get the most recently calculated statistics."""
        return self.current_stats
    
    def get_current_patterns(self) -> List[ErrorPattern]:
        """Get the most recently detected error patterns."""
        return self.current_patterns
    
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
    
    def _emit_unavailable(self, reason: str) -> None:
        """Emit unavailable signal with reason."""
        self._last_unavailable_reason = reason
        self.current_stats = None
        self.current_patterns = []
        self.current_game_summaries = []
        self.stats_unavailable.emit(reason)

