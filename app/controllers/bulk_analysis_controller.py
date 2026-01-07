"""Bulk analysis controller for managing bulk game analysis operations."""

from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

from app.models.database_model import DatabaseModel, GameData
from app.models.engine_model import EngineModel
from app.models.move_classification_model import MoveClassificationModel
from app.services.engine_parameters_service import EngineParametersService
from app.services.book_move_service import BookMoveService


class BulkAnalysisController(QObject):
    """Controller for bulk game analysis operations.
    
    This controller orchestrates bulk analysis operations, handles validation,
    manages game selection logic, and coordinates the analysis thread.
    """
    
    # Signals forwarded from analysis thread
    progress_updated = pyqtSignal(float, str, str)  # progress_percent, status_message, progress_percent_str
    status_update_requested = pyqtSignal()  # Request status update from main thread
    game_analyzed = pyqtSignal(GameData)  # Emitted when a game is analyzed
    finished = pyqtSignal(bool, str)  # success, error_message
    
    def __init__(self, config: Dict[str, Any], engine_model: EngineModel,
                 game_analysis_controller, database_panel=None) -> None:
        """Initialize the bulk analysis controller.
        
        Args:
            config: Configuration dictionary.
            engine_model: EngineModel instance.
            game_analysis_controller: GameAnalysisController instance.
            database_panel: Optional DatabasePanel view instance for getting selected games.
        """
        super().__init__()
        self.config = config
        self.engine_model = engine_model
        self.game_analysis_controller = game_analysis_controller
        self.database_panel = database_panel
        self._analysis_thread = None
    
    def set_database_panel(self, database_panel) -> None:
        """Set the database panel view reference.
        
        Args:
            database_panel: DatabasePanel view instance.
        """
        self.database_panel = database_panel
    
    def validate_engine_for_analysis(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """Validate that an engine is configured and assigned for game analysis.
        
        Returns:
            Tuple of (is_valid, error_title, error_message).
            - is_valid: True if engine is valid, False otherwise
            - error_title: Error title if validation failed, None otherwise
            - error_message: Error message if validation failed, None otherwise
        """
        engine_assignment = self.engine_model.get_assignment(EngineModel.TASK_GAME_ANALYSIS)
        if engine_assignment is None:
            engines = self.engine_model.get_engines()
            if not engines:
                error_type = "no_engines"
            else:
                error_type = "no_assignment"
            
            # Get validation message from config
            messages_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_validation_messages', {})
            error_config = messages_config.get(error_type, {})
            title = error_config.get('title', 'Error')
            message_template = error_config.get('message_template', '')
            
            if message_template:
                # Use bulk_analysis action
                actions = messages_config.get('actions', {})
                tasks = messages_config.get('tasks', {})
                action = actions.get('bulk_analysis', 'starting bulk analysis')
                task_display = tasks.get('game_analysis', 'Game Analysis')
                
                # Format message
                message = message_template.format(action=action, task=task_display)
            else:
                # Fallback message
                if not engines:
                    title = "No Engine Configured"
                    message = "Please add at least one UCI chess engine before starting bulk analysis.\n\nGo to Engines → Add Engine... to configure an engine."
                else:
                    title = "No Engine Assigned"
                    message = "Please assign an engine to the Game Analysis task before starting bulk analysis.\n\nGo to Engines → [Engine Name] → Assign to Game Analysis."
            
            return (False, title, message)
        
        return (True, None, None)
    
    def get_selected_games(self, database_model: DatabaseModel) -> List[GameData]:
        """Get selected games from the database panel.
        
        Args:
            database_model: DatabaseModel instance to get games from.
            
        Returns:
            List of selected GameData instances.
        """
        selected_games = []
        if database_model and self.database_panel:
            # Get selected rows from the database panel (only works if this is the active database)
            # Check if the active database matches our database model
            active_info = self.database_panel.get_active_database_info()
            if active_info and active_info.get('model') == database_model:
                selected_indices = self.database_panel.get_selected_game_indices()
                for idx in selected_indices:
                    game = database_model.get_game(idx)
                    if game:
                        selected_games.append(game)
        return selected_games
    
    def get_games_to_analyze(self, selection_mode: str, database_model: Optional[DatabaseModel],
                             selected_games: List[GameData]) -> Tuple[Optional[List[GameData]], Optional[str], Optional[str]]:
        """Get games to analyze based on selection mode.
        
        Args:
            selection_mode: "selected" or "all"
            database_model: DatabaseModel instance (required for "all" mode)
            selected_games: List of selected games (required for "selected" mode)
            
        Returns:
            Tuple of (games_list, error_title, error_message).
            - games_list: List of games to analyze, or None if error
            - error_title: Error title if validation failed, None otherwise
            - error_message: Error message if validation failed, None otherwise
        """
        if selection_mode == "selected":
            if not selected_games:
                return (None, "No Games Selected",
                       "Please select games in the database view to analyze, or choose 'All games'.")
            games_to_analyze = selected_games
        else:  # "all"
            if not database_model:
                return (None, "No Database", "No database is available.")
            games_to_analyze = database_model.get_all_games()
        
        if not games_to_analyze:
            return (None, "No Games", "No games found in the database.")
        
        return (games_to_analyze, None, None)
    
    def prepare_services_for_analysis(self, status_callback=None) -> None:
        """Prepare services needed for analysis (opening service, engine parameters).
        
        This must be called in the main thread before creating worker threads.
        
        Args:
            status_callback: Optional callback(status_message) for status updates.
        """
        opening_service = self.game_analysis_controller.opening_service
        
        # Ensure opening service is loaded before starting analysis (to avoid blocking during analysis)
        if opening_service and not opening_service.is_loaded():
            if status_callback:
                status_callback("Loading opening database...")
            
            try:
                opening_service.load()
            except Exception as e:
                # If loading fails, continue anyway (opening info will just be missing)
                import sys
                print(f"Warning: Failed to load opening service: {e}", file=sys.stderr)
            
            if status_callback:
                status_callback("Ready")
        
        # Pre-load engine parameters to avoid blocking in worker thread
        if status_callback:
            status_callback("Loading engine parameters...")
        
        try:
            # Pre-load by calling get_task_parameters_for_engine (it will load if needed)
            engine_assignment = self.engine_model.get_assignment(EngineModel.TASK_GAME_ANALYSIS)
            if engine_assignment:
                engine = self.engine_model.get_engine(engine_assignment)
                if engine and engine.is_valid:
                    engine_path = Path(engine.path) if not isinstance(engine.path, Path) else engine.path
                    EngineParametersService.get_task_parameters_for_engine(
                        engine_path,
                        "game_analysis",
                        self.config
                    )
        except Exception as e:
            import sys
            print(f"Warning: Failed to pre-load engine parameters: {e}", file=sys.stderr)
        
        if status_callback:
            status_callback("Ready")
    
    def get_required_services(self) -> Tuple[EngineModel, 'OpeningService', BookMoveService, Optional[MoveClassificationModel]]:
        """Get required services for bulk analysis.
        
        Returns:
            Tuple of (engine_model, opening_service, book_move_service, classification_model).
        """
        engine_model = self.game_analysis_controller.engine_model
        opening_service = self.game_analysis_controller.opening_service
        book_move_service = self.game_analysis_controller.book_move_service
        classification_model = self.game_analysis_controller.classification_model
        
        return (engine_model, opening_service, book_move_service, classification_model)
    
    def start_analysis(self, games: List[GameData], re_analyze: bool = False,
                       movetime_override: Optional[int] = None,
                       max_threads_override: Optional[int] = None,
                       parallel_games_override: Optional[int] = None) -> None:
        """Start bulk analysis for the given games.
        
        Args:
            games: List of games to analyze.
            re_analyze: Whether to re-analyze already analyzed games.
            movetime_override: Optional override for movetime in milliseconds.
            max_threads_override: Optional override for maximum total threads (None = unlimited).
            parallel_games_override: Optional override for number of parallel games (None = use config default).
        """
        # Import here to avoid circular dependency
        from app.views.bulk_analysis_dialog import BulkAnalysisThread
        
        # Get required services
        engine_model, opening_service, book_move_service, classification_model = self.get_required_services()
        
        # Create and configure analysis thread
        self._analysis_thread = BulkAnalysisThread(
            games,
            self.config,
            engine_model,
            self.game_analysis_controller,
            opening_service,
            book_move_service,
            classification_model,
            re_analyze,
            movetime_override=movetime_override,
            max_threads_override=max_threads_override,
            parallel_games_override=parallel_games_override
        )
        
        # Forward signals from thread to controller
        self._analysis_thread.progress_updated.connect(self.progress_updated.emit)
        self._analysis_thread.status_update_requested.connect(self.status_update_requested.emit)
        self._analysis_thread.game_analyzed.connect(self.game_analyzed.emit)
        self._analysis_thread.finished.connect(self.finished.emit)
        
        # Start the thread
        self._analysis_thread.start()
    
    def cancel_analysis(self) -> None:
        """Cancel the current analysis if running."""
        if self._analysis_thread and self._analysis_thread.isRunning():
            self._analysis_thread.cancel()
    
    def is_analysis_running(self) -> bool:
        """Check if analysis is currently running.
        
        Returns:
            True if analysis thread is running, False otherwise.
        """
        return self._analysis_thread is not None and self._analysis_thread.isRunning()
    
    def wait_for_analysis(self) -> None:
        """Wait for the analysis thread to finish."""
        if self._analysis_thread:
            self._analysis_thread.wait()
    
    def get_analysis_thread(self):
        """Get the current analysis thread (for status updates).
        
        Returns:
            The BulkAnalysisThread instance, or None if not started.
        """
        return self._analysis_thread

