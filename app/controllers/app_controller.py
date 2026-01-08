"""Central application controller for orchestrating business logic."""

from typing import Dict, Any, Optional, Tuple

from app.models.progress_model import ProgressModel
from app.services.progress_service import ProgressService
from app.controllers.board_controller import BoardController
from app.controllers.database_controller import DatabaseController
from app.controllers.game_controller import GameController
from app.controllers.column_profile_controller import ColumnProfileController
from app.controllers.engine_controller import EngineController, TASK_EVALUATION, TASK_GAME_ANALYSIS, TASK_MANUAL_ANALYSIS
from app.controllers.evaluation_controller import EvaluationController
from app.controllers.manual_analysis_controller import ManualAnalysisController
from app.controllers.game_analysis_controller import GameAnalysisController
from app.controllers.move_classification_controller import MoveClassificationController
from app.controllers.bulk_replace_controller import BulkReplaceController
from app.controllers.bulk_tag_controller import BulkTagController
from app.controllers.bulk_clean_pgn_controller import BulkCleanPgnController
from app.controllers.bulk_analysis_controller import BulkAnalysisController
from app.controllers.deduplication_controller import DeduplicationController
from app.controllers.positional_heatmap_controller import PositionalHeatmapController
from app.controllers.annotation_controller import AnnotationController
from app.controllers.ai_chat_controller import AIChatController
from app.controllers.game_summary_controller import GameSummaryController
from app.controllers.player_stats_controller import PlayerStatsController
from app.controllers.metadata_controller import MetadataController


class AppController:
    """Central logic hub for the application.
    
    This controller orchestrates between services and models, following
    PyQt's Model/View architecture with Controllers. It coordinates multiple services and manages
    the connection between business logic and UI state.
    """
    
    def __init__(self, config: Dict[str, Any], user_settings_service: Optional[Any] = None) -> None:
        """Initialize the application controller.
        
        Args:
            config: Configuration dictionary.
            user_settings_service: Optional UserSettingsService instance (deprecated, uses singleton now).
        """
        self.config = config
        # Get singleton service instance
        from app.services.user_settings_service import UserSettingsService
        self.user_settings_service = UserSettingsService.get_instance()
        
        # Initialize models
        self.progress_model = ProgressModel()
        
        # Initialize controllers
        self.board_controller = BoardController(config)
        self.database_controller = DatabaseController(config)
        
        # Initialize game controller (depends on board controller)
        self.game_controller = GameController(config, self.board_controller)
        
        # Initialize column profile controller
        self.column_profile_controller = ColumnProfileController()
        
        # Initialize move classification controller (uses singleton service)
        self.move_classification_controller = MoveClassificationController(config, None)
        
        # Initialize game summary controller (depends on game model and classification model)
        self.game_summary_controller = GameSummaryController(
            config,
            self.game_controller.get_game_model(),
            None,
            self.move_classification_controller.get_classification_model()
        )
        
        # Initialize engine controller
        self.engine_controller = EngineController(config)
        
        # Initialize manual analysis controller first (depends on engine controller and game controller)
        self.manual_analysis_controller = ManualAnalysisController(config, self.engine_controller, self.game_controller)
        
        # Initialize evaluation controller (depends on engine controller and manual analysis controller)
        self.evaluation_controller = EvaluationController(config, self.engine_controller, self.manual_analysis_controller)
        
        # Connect evaluation controller to manual analysis controller for coordination
        self.manual_analysis_controller.set_evaluation_controller(self.evaluation_controller)
        
        # Initialize game analysis controller (depends on game controller, moves list model, engine controller, and opening service)
        # Note: moves_list_model will be set after DetailPanel is created (see set_moves_list_model)
        opening_service = self.game_controller.opening_service
        self.game_analysis_controller = GameAnalysisController(
            config,
            self.game_controller.get_game_model(),
            None,  # Will be set via set_moves_list_model
            self.engine_controller.get_engine_model(),
            opening_service,
            self.game_controller,  # Pass GameController to update board position
            self.user_settings_service,  # Pass singleton UserSettingsService instance
            self.move_classification_controller.get_classification_model(),  # Pass classification model
            self.database_controller  # Pass DatabaseController to mark databases as unsaved
        )
        
        # Initialize bulk replace controller (depends on database controller, engine controller, evaluation controller, and game controller)
        self.bulk_replace_controller = BulkReplaceController(
            config,
            self.database_controller,
            self.engine_controller,
            self.evaluation_controller,
            self.game_controller
        )
        
        # Initialize bulk tag controller (depends on database controller and game controller)
        self.bulk_tag_controller = BulkTagController(
            config,
            self.database_controller,
            self.game_controller
        )
        
        # Initialize bulk clean PGN controller (depends on database controller and game controller)
        self.bulk_clean_pgn_controller = BulkCleanPgnController(
            config,
            self.database_controller,
            self.game_controller
        )
        
        # Initialize bulk analysis controller (depends on engine controller and game analysis controller)
        self.bulk_analysis_controller = BulkAnalysisController(
            config,
            self.engine_controller.get_engine_model(),
            self.game_analysis_controller
        )
        
        # Initialize deduplication controller (depends on database controller and game controller)
        self.deduplication_controller = DeduplicationController(
            config,
            self.database_controller,
            self.game_controller
        )
        
        # Initialize positional heat-map controller (depends on board controller)
        self.positional_heatmap_controller = PositionalHeatmapController(
            config,
            self.board_controller,
            self.game_controller
        )
        
        # Initialize annotation controller (depends on game controller and database controller)
        self.annotation_controller = AnnotationController(
            config,
            self.game_controller.get_game_model(),
            self.database_controller
        )
        
        # Initialize AI chat controller (depends on game controller and app controller)
        self.ai_chat_controller = AIChatController(
            config,
            self.game_controller,
            self
        )
        
        # Initialize player stats controller (depends on database controller and game controller)
        self.player_stats_controller = PlayerStatsController(
            config,
            self.database_controller,
            self.game_controller,
            self.game_controller.get_game_model()
        )
        
        # Initialize metadata controller (depends on game controller and database controller)
        self.metadata_controller = MetadataController(
            self.game_controller.get_game_model(),
            self.database_controller
        )
        
        # Connect evaluation to board position changes
        self._connect_evaluation_to_board()
        
        # Initialize and connect services
        self._setup_services()
    
    def _setup_services(self) -> None:
        """Setup and connect services to models."""
        # Get or create ProgressService singleton
        progress_service = ProgressService.get_instance()
        
        # Connect ProgressService to ProgressModel
        # Services update models through the controller
        progress_service.set_model(self.progress_model)
    
    def get_progress_model(self) -> ProgressModel:
        """Get the progress model.
        
        Returns:
            The ProgressModel instance for observing progress state.
        """
        return self.progress_model
    
    def report_progress(self, message: str, percent: int) -> None:
        """Report progress (convenience method that goes through service).
        
        Args:
            message: Status message to display.
            percent: Progress value (0-100).
        """
        progress_service = ProgressService.get_instance()
        progress_service.report_progress(message, percent)
    
    def show_progress(self) -> None:
        """Show the progress bar."""
        progress_service = ProgressService.get_instance()
        progress_service.show_progress()
    
    def hide_progress(self) -> None:
        """Hide the progress bar."""
        progress_service = ProgressService.get_instance()
        progress_service.hide_progress()
    
    def set_status(self, message: str) -> None:
        """Set the status message.
        
        Args:
            message: Status message to display.
        """
        progress_service = ProgressService.get_instance()
        progress_service.set_status(message)
    
    def get_board_controller(self) -> BoardController:
        """Get the board controller.
        
        Returns:
            The BoardController instance for managing board operations.
        """
        return self.board_controller
    
    def rotate_board(self) -> None:
        """Rotate the board 180 degrees (flip board).
        
        This is a convenience method that goes through the board controller.
        """
        self.board_controller.rotate_board_180()
        
        # Show status message
        is_flipped = self.board_controller.get_board_model().is_flipped
        status = "Board flipped (rotated 180°)" if is_flipped else "Board unflipped (normal orientation)"
        self.set_status(status)
    
    def toggle_coordinates_visibility(self) -> None:
        """Toggle the visibility of board coordinates.
        
        This is a convenience method that goes through the board controller.
        """
        self.board_controller.toggle_coordinates_visibility()
        
        # Show status message
        show_coords = self.board_controller.get_board_model().show_coordinates
        status = "Coordinates shown" if show_coords else "Coordinates hidden"
        self.set_status(status)
    
    def toggle_turn_indicator_visibility(self) -> None:
        """Toggle the visibility of turn indicator.
        
        This is a convenience method that goes through the board controller.
        """
        self.board_controller.toggle_turn_indicator_visibility()
        
        # Show status message
        show_indicator = self.board_controller.get_board_model().show_turn_indicator
        status = "Turn indicator shown" if show_indicator else "Turn indicator hidden"
        self.set_status(status)
    
    def toggle_game_info_visibility(self) -> None:
        """Toggle the visibility of game info.
        
        This is a convenience method that goes through the board controller.
        """
        self.board_controller.toggle_game_info_visibility()
        
        # Show status message
        show_info = self.board_controller.get_board_model().show_game_info
        status = "Game info shown" if show_info else "Game info hidden"
        self.set_status(status)
    
    def toggle_playedmove_arrow_visibility(self) -> None:
        """Toggle the visibility of played move arrow.
        
        This is a convenience method that goes through the board controller.
        """
        self.board_controller.toggle_playedmove_arrow_visibility()
        
        # Show status message
        show_arrow = self.board_controller.get_board_model().show_playedmove_arrow
        status = "Played move arrow shown" if show_arrow else "Played move arrow hidden"
        self.set_status(status)
    
    def toggle_bestnextmove_arrow_visibility(self) -> None:
        """Toggle the visibility of best next move arrow.
        
        This is a convenience method that goes through the board controller.
        """
        self.board_controller.toggle_bestnextmove_arrow_visibility()
        
        # Show status message
        show_arrow = self.board_controller.get_board_model().show_bestnextmove_arrow
        status = "Best next move arrow shown" if show_arrow else "Best next move arrow hidden"
        self.set_status(status)
    
    def toggle_pv2_arrow_visibility(self) -> None:
        """Toggle the visibility of PV2 arrow.
        
        This is a convenience method that goes through the board controller.
        """
        self.board_controller.toggle_pv2_arrow_visibility()
        
        # Show status message
        show_arrow = self.board_controller.get_board_model().show_pv2_arrow
        status = "Next Best Move (PV2) arrow shown" if show_arrow else "Next Best Move (PV2) arrow hidden"
        self.set_status(status)
    
    def toggle_pv3_arrow_visibility(self) -> None:
        """Toggle the visibility of PV3 arrow.
        
        This is a convenience method that goes through the board controller.
        """
        self.board_controller.toggle_pv3_arrow_visibility()
        
        # Show status message
        show_arrow = self.board_controller.get_board_model().show_pv3_arrow
        status = "Next Best Move (PV3) arrow shown" if show_arrow else "Next Best Move (PV3) arrow hidden"
        self.set_status(status)
    
    def toggle_bestalternativemove_arrow_visibility(self) -> None:
        """Toggle the visibility of best alternative move arrow.
        
        This is a convenience method that goes through the board controller.
        """
        self.board_controller.toggle_bestalternativemove_arrow_visibility()
        
        # Show status message
        show_arrow = self.board_controller.get_board_model().show_bestalternativemove_arrow
        status = "Best alternative move arrow shown" if show_arrow else "Best alternative move arrow hidden"
        self.set_status(status)
    
    def copy_fen_to_clipboard(self) -> tuple[str, str]:
        """Copy current FEN to clipboard and return formatted status message.
        
        Returns:
            Tuple of (fen: str, status_message: str).
            fen is the FEN string that was copied.
            status_message is the formatted message to display.
        """
        from PyQt6.QtWidgets import QApplication
        
        fen = self.get_current_fen()
        clipboard = QApplication.clipboard()
        clipboard.setText(fen)
        
        status_message = self.board_controller.format_fen_copied_message(fen)
        return (fen, status_message)
    
    def copy_pgn_to_clipboard(self) -> tuple[bool, str]:
        """Copy current active game PGN to clipboard and return formatted status message.
        
        Returns:
            Tuple of (success: bool, status_message: str).
            If success is True, status_message indicates successful copy.
            If success is False, status_message indicates no active game.
        """
        from PyQt6.QtWidgets import QApplication
        
        game_model = self.game_controller.get_game_model()
        active_game = game_model.active_game
        
        if active_game is None:
            return (False, "No active game to copy")
        
        pgn = active_game.pgn
        clipboard = QApplication.clipboard()
        clipboard.setText(pgn)
        
        status_message = f"PGN copied to clipboard ({active_game.white} vs {active_game.black})"
        return (True, status_message)
    
    def copy_selected_games_to_clipboard(self, database_panel) -> tuple[bool, str]:
        """Copy PGN of selected games in active database to clipboard.
        
        Args:
            database_panel: DatabasePanel instance to get selected games from.
            
        Returns:
            Tuple of (success: bool, status_message: str).
            If success is True, status_message indicates successful copy.
            If success is False, status_message indicates error (no database, no selection, etc.).
        """
        from PyQt6.QtWidgets import QApplication
        
        # Get active database info
        active_info = database_panel.get_active_database_info()
        if not active_info:
            return (False, "No active database")
        
        database_model = active_info.get('model')
        if not database_model:
            return (False, "No active database")
        
        # Get selected game indices
        selected_indices = database_panel.get_selected_game_indices()
        if not selected_indices:
            return (False, "No games selected")
        
        # Get GameData objects for selected games
        games = []
        for idx in selected_indices:
            game = database_model.get_game(idx)
            if game:
                games.append(game)
        
        if not games:
            return (False, "No valid games found")
        
        # Extract raw PGN text from each game (not HTML-formatted)
        pgn_texts = []
        for game in games:
            # Use raw PGN property - contains full game with all tags
            pgn = game.pgn
            if pgn:
                pgn_texts.append(pgn)
        
        if not pgn_texts:
            return (False, "No PGN data found in selected games")
        
        # Concatenate PGN texts with double newline (standard PGN separator)
        combined_pgn = "\n\n".join(pgn_texts)
        
        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(combined_pgn)
        
        game_count = len(games)
        status_message = f"Copied {game_count} game(s) to clipboard"
        return (True, status_message)
    
    def cut_selected_games_to_clipboard(self, database_panel) -> tuple[bool, str]:
        """Cut PGN of selected games in active database to clipboard (copy and remove).
        
        Args:
            database_panel: DatabasePanel instance to get selected games from.
            
        Returns:
            Tuple of (success: bool, status_message: str).
            If success is True, status_message indicates successful cut.
            If success is False, status_message indicates error (no database, no selection, etc.).
        """
        from PyQt6.QtWidgets import QApplication
        
        # Get active database info
        active_info = database_panel.get_active_database_info()
        if not active_info:
            return (False, "No active database")
        
        database_model = active_info.get('model')
        if not database_model:
            return (False, "No active database")
        
        # Get selected game indices
        selected_indices = database_panel.get_selected_game_indices()
        if not selected_indices:
            return (False, "No games selected")
        
        # Get GameData objects for selected games
        games = []
        for idx in selected_indices:
            game = database_model.get_game(idx)
            if game:
                games.append(game)
        
        if not games:
            return (False, "No valid games found")
        
        # Extract raw PGN text from each game (not HTML-formatted)
        pgn_texts = []
        for game in games:
            # Use raw PGN property - contains full game with all tags
            pgn = game.pgn
            if pgn:
                pgn_texts.append(pgn)
        
        if not pgn_texts:
            return (False, "No PGN data found in selected games")
        
        # Concatenate PGN texts with double newline (standard PGN separator)
        combined_pgn = "\n\n".join(pgn_texts)
        
        # Copy to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(combined_pgn)
        
        # Get active game before removal (to check if we need to clear it)
        game_model = self.game_controller.get_game_model()
        active_game = game_model.active_game
        
        # Remove games from database
        database_model.remove_games(games)
        
        # Mark database as unsaved
        self.database_controller.mark_database_unsaved(database_model)
        
        # If active game was cut, clear it from game model
        if active_game and active_game in games:
            game_model.set_active_game(None)
        
        game_count = len(games)
        status_message = f"Cut {game_count} game(s) to clipboard"
        return (True, status_message)
    
    def paste_fen_from_clipboard(self) -> tuple[bool, str]:
        """Paste FEN from clipboard and update board position.
        
        When a FEN is pasted, the active game is cleared (set to None) to indicate
        that the board position is no longer associated with a game. This clears
        the PGN view and moves list view automatically.
        
        Returns:
            Tuple of (success: bool, status_message: str).
            If success is True, status_message indicates successful update.
            If success is False, status_message indicates the error.
        """
        from PyQt6.QtWidgets import QApplication
        
        clipboard = QApplication.clipboard()
        fen_text = clipboard.text().strip()
        
        if not fen_text:
            return (False, "Clipboard is empty")
        
        # Clear active game when FEN is pasted (board position is no longer from a game)
        self.game_controller.clear_active_game()
        
        # Validate and set FEN through controller
        success = self.set_fen_from_string(fen_text)
        
        if success:
            status_message = self.board_controller.format_fen_updated_message(fen_text)
        else:
            status_message = self.board_controller.format_fen_invalid_message(fen_text)
        
        return (success, status_message)
    
    def get_current_fen(self) -> str:
        """Get the current board position as FEN string.
        
        Returns:
            The current FEN string of the board position.
        """
        return self.board_controller.get_position_fen()
    
    def set_fen_from_string(self, fen: str) -> bool:
        """Set board position from FEN string with validation.
        
        Args:
            fen: FEN string to set (will be validated).
        
        Returns:
            True if FEN is valid and board was updated, False otherwise.
        """
        return self.board_controller.set_fen_with_validation(fen)
    
    def get_database_controller(self) -> DatabaseController:
        """Get the database controller.
        
        Returns:
            The DatabaseController instance for managing database operations.
        """
        return self.database_controller
    
    def get_game_controller(self) -> GameController:
        """Get the game controller.
        
        Returns:
            The GameController instance for managing active game operations.
        """
        return self.game_controller
    
    def get_column_profile_controller(self) -> ColumnProfileController:
        """Get the column profile controller.
        
        Returns:
            The ColumnProfileController instance for managing column profiles.
        """
        return self.column_profile_controller
    
    def get_engine_controller(self) -> EngineController:
        """Get the engine controller.
        
        Returns:
            The EngineController instance for managing UCI engine operations.
        """
        return self.engine_controller
    
    def is_engine_configured_for_task(self, task: str) -> Tuple[bool, Optional[str]]:
        """Check if an engine is configured and assigned for a task.
        
        This is a convenience method that delegates to the engine controller.
        
        Args:
            task: Task constant (TASK_GAME_ANALYSIS, TASK_EVALUATION, TASK_MANUAL_ANALYSIS).
            
        Returns:
            Tuple of (is_configured: bool, error_message: Optional[str]).
            If is_configured is True, error_message is None.
            If is_configured is False, error_message contains the reason:
            - "no_engines" if no engines are configured
            - "no_assignment" if no engine is assigned to the task
        """
        return self.engine_controller.is_engine_configured_for_task(task)
    
    def get_engine_validation_message(self, error_type: str, task: str) -> Tuple[str, str]:
        """Get validation message title and text from config for engine validation errors.
        
        Args:
            error_type: Error type ("no_engines" or "no_assignment").
            task: Task constant (TASK_GAME_ANALYSIS, TASK_EVALUATION, TASK_MANUAL_ANALYSIS).
            
        Returns:
            Tuple of (title: str, message: str).
        """
        messages_config = self.config.get('ui', {}).get('dialogs', {}).get('engine_validation_messages', {})
        
        # Map task constants to config keys
        task_key_map = {
            TASK_GAME_ANALYSIS: "game_analysis",
            TASK_MANUAL_ANALYSIS: "manual_analysis",
            TASK_EVALUATION: "evaluation"
        }
        action_key_map = {
            TASK_GAME_ANALYSIS: "game_analysis",
            TASK_MANUAL_ANALYSIS: "manual_analysis",
            TASK_EVALUATION: "evaluation_bar"
        }
        
        task_key = task_key_map.get(task, task)
        action_key = action_key_map.get(task, task)
        
        # Get error config
        error_config = messages_config.get(error_type, {})
        title = error_config.get('title', 'Error')
        message_template = error_config.get('message_template', '')
        
        # Get action and task display names
        actions = messages_config.get('actions', {})
        tasks = messages_config.get('tasks', {})
        action = actions.get(action_key, action_key)
        task_display = tasks.get(task_key, task_key)
        
        # Format message
        message = message_template.format(action=action, task=task_display)
        
        return (title, message)
    
    def get_evaluation_controller(self) -> EvaluationController:
        """Get the evaluation controller.
        
        Returns:
            The EvaluationController instance for managing position evaluation.
        """
        return self.evaluation_controller
    
    def get_manual_analysis_controller(self) -> ManualAnalysisController:
        """Get the manual analysis controller.
        
        Returns:
            The ManualAnalysisController instance for managing manual position analysis.
        """
        return self.manual_analysis_controller
    
    def get_game_analysis_controller(self) -> GameAnalysisController:
        """Get the game analysis controller.
        
        Returns:
            The GameAnalysisController instance for managing game analysis operations.
        """
        return self.game_analysis_controller
    
    def get_move_classification_controller(self) -> MoveClassificationController:
        """Get the move classification controller.
        
        Returns:
            The MoveClassificationController instance for managing classification settings.
        """
        return self.move_classification_controller
    
    def get_bulk_replace_controller(self) -> BulkReplaceController:
        """Get the bulk replace controller.
        
        Returns:
            The BulkReplaceController instance for managing bulk replacement operations.
        """
        return self.bulk_replace_controller
    
    def get_bulk_tag_controller(self) -> BulkTagController:
        """Get the bulk tag controller.
        
        Returns:
            The BulkTagController instance for managing bulk tag operations.
        """
        return self.bulk_tag_controller
    
    def get_deduplication_controller(self):
        """Get the deduplication controller.
        
        Returns:
            The DeduplicationController instance.
        """
        return self.deduplication_controller
    
    def get_bulk_clean_pgn_controller(self) -> BulkCleanPgnController:
        """Get the bulk clean PGN controller.
        
        Returns:
            The BulkCleanPgnController instance for managing bulk PGN cleaning operations.
        """
        return self.bulk_clean_pgn_controller
    
    def get_bulk_analysis_controller(self) -> BulkAnalysisController:
        """Get the bulk analysis controller.
        
        Returns:
            The BulkAnalysisController instance for managing bulk game analysis operations.
        """
        return self.bulk_analysis_controller
    
    def get_positional_heatmap_controller(self) -> PositionalHeatmapController:
        """Get the positional heat-map controller.
        
        Returns:
            The PositionalHeatmapController instance for managing positional heat-map.
        """
        return self.positional_heatmap_controller
    
    def get_annotation_controller(self) -> AnnotationController:
        """Get the annotation controller.
        
        Returns:
            The AnnotationController instance for managing annotations.
        """
        return self.annotation_controller
    
    def get_ai_chat_controller(self) -> AIChatController:
        """Get the AI chat controller.
        
        Returns:
            The AIChatController instance for managing AI conversations.
        """
        return self.ai_chat_controller
    
    def get_game_summary_controller(self) -> GameSummaryController:
        """Get the game summary controller."""
        return self.game_summary_controller
    
    def get_metadata_controller(self) -> MetadataController:
        """Get the metadata controller.
        
        Returns:
            The MetadataController instance.
        """
        return self.metadata_controller
    
    def get_player_stats_controller(self) -> PlayerStatsController:
        """Get the player stats controller.
        
        Returns:
            The PlayerStatsController instance for managing player statistics.
        """
        return self.player_stats_controller
    
    def set_moves_list_model(self, moves_list_model) -> None:
        """Set the moves list model for game analysis controller.
        
        Args:
            moves_list_model: MovesListModel instance.
        """
        if self.game_analysis_controller:
            self.game_analysis_controller.moves_list_model = moves_list_model
        if self.game_summary_controller:
            self.game_summary_controller.set_moveslist_model(moves_list_model)
    
    def is_game_analysis_running(self) -> bool:
        """Check if game analysis is currently running.
        
        Returns:
            True if game analysis is running, False otherwise.
        """
        if self.game_analysis_controller:
            return self.game_analysis_controller.is_analyzing
        return False
    
    def _connect_evaluation_to_board(self) -> None:
        """Connect evaluation controller to board position changes."""
        board_model = self.board_controller.get_board_model()
        board_model.position_changed.connect(self._on_board_position_changed)
        board_model.evaluation_bar_visibility_changed.connect(self._on_evaluation_bar_visibility_changed)
    
    def _on_board_position_changed(self) -> None:
        """Handle board position change."""
        # Update evaluation if bar is visible
        board_model = self.board_controller.get_board_model()
        if board_model.show_evaluation_bar:
            fen = board_model.get_fen()
            # Always update position - this will start evaluation if not running
            self.evaluation_controller.update_position(fen)
    
    def _on_evaluation_bar_visibility_changed(self, show: bool) -> None:
        """Handle evaluation bar visibility change.
        
        Args:
            show: True if evaluation bar should be shown, False otherwise.
        """
        if show:
            # Check if manual analysis is running first
            if self.manual_analysis_controller:
                analysis_model = self.manual_analysis_controller.get_analysis_model()
                if analysis_model.is_analyzing:
                    # Manual analysis is running - switch evaluation bar to use it
                    # Don't start evaluation engine
                    self.evaluation_controller._switch_to_manual_analysis()
                    return
            
            # Engine validation is already done in toggle_evaluation_bar_visibility()
            # If we reach here, the bar is being shown and engine is configured
            # Start evaluation engine
            board_model = self.board_controller.get_board_model()
            fen = board_model.get_fen()
            self.evaluation_controller.start_evaluation(fen)
        else:
            # Stop evaluation (will disconnect from manual analysis if using it)
            self.evaluation_controller.stop_evaluation()
    
    def toggle_evaluation_bar_visibility(self) -> None:
        """Toggle the visibility of evaluation bar.
        
        This is a convenience method that goes through the board controller.
        """
        board_model = self.board_controller.get_board_model()
        current_visibility = board_model.show_evaluation_bar
        
        # If we're trying to show the bar, validate engine configuration first
        if not current_visibility:
            # Check if engine is configured and assigned for evaluation
            is_configured, error_type = self.is_engine_configured_for_task(TASK_EVALUATION)
            if not is_configured:
                # Don't toggle - show warning message instead
                from PyQt6.QtWidgets import QApplication
                from app.views.message_dialog import MessageDialog
                parent = QApplication.activeWindow()
                
                title, message = self.get_engine_validation_message(error_type, TASK_EVALUATION)
                MessageDialog.show_warning(self.config, title, message, parent)
                return
        
        # Toggle visibility (either hiding or showing with valid engine)
        self.board_controller.toggle_evaluation_bar_visibility()
        
        # Show status message
        show_bar = self.board_controller.get_board_model().show_evaluation_bar
        status = "Evaluation bar shown" if show_bar else "Evaluation bar hidden"
        self.set_status(status)
    
    def toggle_material_widget_visibility(self) -> None:
        """Toggle the visibility of material widget.
        
        This is a convenience method that goes through the board controller.
        """
        self.board_controller.toggle_material_widget_visibility()
        
        # Show status message
        show_widget = self.board_controller.get_board_model().show_material_widget
        status = "Material widget shown" if show_widget else "Material widget hidden"
        self.set_status(status)
    
    def toggle_positional_heatmap_visibility(self) -> None:
        """Toggle the visibility of positional heat-map.
        
        This is a convenience method that goes through the positional heat-map controller.
        """
        self.positional_heatmap_controller.toggle_visibility()
        
        # Show status message
        show_heatmap = self.positional_heatmap_controller.get_model().is_visible
        status = "Positional heat-map shown" if show_heatmap else "Positional heat-map hidden"
        self.set_status(status)
    
    def paste_pgn_from_clipboard(self) -> tuple[bool, str]:
        """Parse PGN from clipboard and add to database.
        
        This method reads PGN text from the clipboard, parses it, and
        adds the games to the database model. The first parsed game
        automatically becomes the active game.
        
        Returns:
            Tuple of (success: bool, status_message: str).
            If success is True, status_message contains formatted success message.
            If success is False, status_message contains formatted error message.
        """
        from PyQt6.QtWidgets import QApplication
        
        clipboard = QApplication.clipboard()
        pgn_text = clipboard.text().strip()
        
        if not pgn_text:
            return (False, "Clipboard is empty")
        
        # Parse and add games to database through controller
        success, message, first_game_index, _ = self.database_controller.parse_pgn_from_text(pgn_text)
        
        # If successful, set the first game as active
        if success and first_game_index is not None:
            database_model = self.database_controller.get_database_model()
            first_game = database_model.get_game(first_game_index)
            if first_game:
                self.game_controller.set_active_game(first_game)
            # Return success message as-is (already formatted by database controller)
            status_message = message
        else:
            # Format error message
            status_message = self.database_controller.format_pgn_error_message(message)
        
        return (success, status_message)
    
    def paste_pgn_to_clipboard_db(self) -> tuple[bool, str, Optional[int], int]:
        """Parse PGN from clipboard and add to clipboard database.
        
        This method reads PGN text from the clipboard, parses it, and
        adds the games to the clipboard database model. Returns the first
        game index and count for highlighting.
        
        Returns:
            Tuple of (success: bool, status_message: str, first_game_index: Optional[int], games_added: int).
            If success is True, status_message contains formatted success message,
            first_game_index is the row index of the first game added, and games_added is the count.
            If success is False, status_message contains formatted error message,
            first_game_index is None, and games_added is 0.
        """
        from PyQt6.QtWidgets import QApplication
        
        clipboard = QApplication.clipboard()
        pgn_text = clipboard.text().strip()
        
        if not pgn_text:
            return (False, "Clipboard is empty", None, 0)
        
        # Parse and add games to clipboard database model
        database_model = self.database_controller.get_database_model()
        success, message, first_game_index, games_added = self.database_controller.parse_pgn_to_model(pgn_text, database_model)
        
        if success:
            # If successful, set the first game as active
            if first_game_index is not None:
                first_game = database_model.get_game(first_game_index)
                if first_game:
                    self.game_controller.set_active_game(first_game)
            # Return success message as-is (already formatted by database controller)
            status_message = message
        else:
            # Format error message
            status_message = self.database_controller.format_pgn_error_message(message)
        
        return (success, status_message, first_game_index, games_added)
    
    def paste_pgn_to_active_database(self) -> tuple[bool, str, Optional[int], int]:
        """Parse PGN from clipboard and add to the currently active database.
        
        This method reads PGN text from the clipboard, parses it, and
        adds the games to the active database model. Returns the first
        game index and count for highlighting.
        
        Returns:
            Tuple of (success: bool, status_message: str, first_game_index: Optional[int], games_added: int).
            If success is True, status_message contains formatted success message,
            first_game_index is the row index of the first game added, and games_added is the count.
            If success is False, status_message contains formatted error message,
            first_game_index is None, and games_added is 0.
        """
        from PyQt6.QtWidgets import QApplication
        
        # Get the currently active database
        active_database = self.database_controller.get_active_database()
        if active_database is None:
            return (False, "No active database selected", None)
        
        # Get PGN text from clipboard
        clipboard = QApplication.clipboard()
        pgn_text = clipboard.text().strip()
        
        if not pgn_text:
            return (False, "Clipboard is empty", None)
        
        # Parse and add games to the active database model
        success, message, first_game_index, games_added = self.database_controller.parse_pgn_to_model(pgn_text, active_database)
        
        if success:
            # If successful, set the first game as active
            if first_game_index is not None:
                first_game = active_database.get_game(first_game_index)
                if first_game:
                    self.game_controller.set_active_game(first_game)
            # Return success message as-is (already formatted by database controller)
            status_message = message
        else:
            # Format error message
            status_message = self.database_controller.format_pgn_error_message(message)
        
        return (success, status_message, first_game_index, games_added)
    
    def set_active_game_by_row(self, row: int) -> tuple[bool, Optional[str]]:
        """Set the active game by database table row index.
        
        Args:
            row: Row index in the database table.
            
        Returns:
            Tuple of (success: bool, status_message: Optional[str]).
            If success is True, status_message contains formatted message about the active game.
            If success is False, status_message is None.
        """
        # Check if game analysis is running
        if self.is_game_analysis_running():
            return (False, "Cannot load game while analysis is running")
        
        database_model = self.database_controller.get_database_model()
        game = database_model.get_game(row)
        
        if game is None:
            return (False, None)
        
        self.game_controller.set_active_game(game)
        status_message = self.game_controller.format_active_game_status_message(game)
        return (True, status_message)
    
    def save_user_settings(
        self,
        pgn_visibility_settings: Optional[Dict[str, bool]] = None,
        game_analysis_settings: Optional[Dict[str, bool]] = None
    ) -> None:
        """Save current user settings to file.
        
        This method collects settings from models and views, then delegates
        to the user settings service to persist them.
        
        Args:
            pgn_visibility_settings: Optional dictionary of PGN visibility settings
                from the view. If None, will use defaults or load from service.
            game_analysis_settings: Optional dictionary of game analysis settings
                from the view. If None, will use defaults or load from service.
        """
        # Update board visibility settings through UserSettingsService
        board_model = self.board_controller.get_board_model()
        self.user_settings_service.update_board_visibility({
            "show_coordinates": board_model.show_coordinates,
            "show_turn_indicator": board_model.show_turn_indicator,
            "show_game_info": board_model.show_game_info,
            "show_playedmove_arrow": board_model.show_playedmove_arrow,
            "show_bestnextmove_arrow": board_model.show_bestnextmove_arrow,
            "show_pv2_arrow": board_model.show_pv2_arrow,
            "show_pv3_arrow": board_model.show_pv3_arrow,
            "show_bestalternativemove_arrow": board_model.show_bestalternativemove_arrow,
            "show_annotations_layer": self.annotation_controller.get_annotation_model().show_annotations if self.annotation_controller else True,
            "hide_other_arrows_during_plan_exploration": board_model.hide_other_arrows_during_plan_exploration,
            "show_evaluation_bar": board_model.show_evaluation_bar,
            "show_material_widget": board_model.show_material_widget
        })
        
        # Update PGN visibility settings through UserSettingsService
        if pgn_visibility_settings is not None:
            self.user_settings_service.update_pgn_visibility(pgn_visibility_settings)
        else:
            # Try to get from settings if view doesn't have it yet
            settings = self.user_settings_service.get_settings()
            pgn_visibility = settings.get('pgn_visibility', {})
            self.user_settings_service.update_pgn_visibility({
                "show_metadata": pgn_visibility.get('show_metadata', True),
                "show_comments": pgn_visibility.get('show_comments', True),
                "show_variations": pgn_visibility.get('show_variations', True),
                "show_annotations": pgn_visibility.get('show_annotations', True),
                "show_results": pgn_visibility.get('show_results', True),
                "show_non_standard_tags": pgn_visibility.get('show_non_standard_tags', False)
            })
        
        # Update game analysis settings (menu toggles only, not classification settings)
        if game_analysis_settings is not None:
            self.user_settings_service.update_game_analysis(game_analysis_settings)
        else:
            # Use defaults if not provided
            settings = self.user_settings_service.get_settings()
            game_analysis = settings.get('game_analysis', {})
            self.user_settings_service.update_game_analysis({
                "return_to_first_move_after_analysis": game_analysis.get('return_to_first_move_after_analysis', False),
                "switch_to_moves_list_at_start_of_analysis": game_analysis.get('switch_to_moves_list_at_start_of_analysis', True),
                "switch_to_summary_after_analysis": game_analysis.get('switch_to_summary_after_analysis', False),
                "normalized_evaluation_graph": game_analysis.get('normalized_evaluation_graph', False),
                "post_game_brilliancy_refinement": game_analysis.get('post_game_brilliancy_refinement', False)
            })
        
        # Update engines settings through UserSettingsService
        engine_model = self.engine_controller.get_engine_model()
        self.user_settings_service.update_engines(engine_model.to_dict())
        
        # Update engine assignments through UserSettingsService
        self.user_settings_service.update_engine_assignments(engine_model.get_assignments())
        
        # Update manual analysis settings through UserSettingsService
        manual_analysis_controller = self.get_manual_analysis_controller()
        if manual_analysis_controller:
            manual_analysis_model = manual_analysis_controller.get_analysis_model()
            if manual_analysis_model:
                self.user_settings_service.update_manual_analysis({
                    "enable_miniature_preview": manual_analysis_model.enable_miniature_preview,
                    "miniature_preview_scale_factor": manual_analysis_model.miniature_preview_scale_factor
                })
        
        # Tell UserSettingsService to persist all settings to file
        self.user_settings_service.save()

