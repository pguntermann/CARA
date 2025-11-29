"""Game analysis controller for analyzing all moves in a game."""

import io
import chess
import chess.pgn
import time
import sys
from typing import Dict, Any, Optional, List
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from app.models.game_model import GameModel
from app.models.moveslist_model import MovesListModel
from app.models.engine_model import EngineModel
from app.models.move_classification_model import MoveClassificationModel
from app.models.database_model import DatabaseModel, GameData
from app.services.game_analysis_engine_service import GameAnalysisEngineService
from app.services.book_move_service import BookMoveService
from app.services.opening_service import OpeningService
from app.services.progress_service import ProgressService
from app.services.move_analysis_service import MoveAnalysisService
from app.utils.material_tracker import (calculate_material_loss, calculate_material_balance,
                                         get_captured_piece_letter, calculate_material_count, count_pieces)

# Module-level debug flag (thread-safe)
_debug_brilliant_enabled = False


# Global reference to GameAnalysisController instance for printing settings
_debug_controller_instance = None

def set_debug_brilliant(enabled: bool, controller_instance: Optional['GameAnalysisController'] = None) -> None:
    """Set thread-safe debug flag for brilliant move calculation.
    
    Args:
        enabled: True if brilliant debug output is enabled, False otherwise.
        controller_instance: Optional GameAnalysisController instance to print settings.
    """
    global _debug_brilliant_enabled, _debug_controller_instance
    _debug_brilliant_enabled = enabled
    if controller_instance is not None:
        _debug_controller_instance = controller_instance
    
    # Print confirmation and current settings when enabled
    if enabled and _debug_controller_instance is not None:
        _debug_controller_instance._print_brilliant_debug_settings()


class GameAnalysisController(QObject):
    """Controller for managing game analysis operations.
    
    This controller orchestrates the analysis of all moves in a game,
    updating evaluation, CPL, assessment, and best move columns.
    """
    
    # Signals
    analysis_started = pyqtSignal()
    analysis_completed = pyqtSignal()
    analysis_cancelled = pyqtSignal()
    analysis_progress = pyqtSignal(int, int, int, float, str, int, int)  # move_number, total_moves, depth, centipawns, engine_name, threads, elapsed_ms
    move_analyzed = pyqtSignal(int)  # row_index - emitted when a move is analyzed and should be scrolled to
    
    def __init__(self, config: Dict[str, Any], game_model: GameModel, moves_list_model: MovesListModel,
                 engine_model: EngineModel, opening_service: OpeningService,
                 game_controller: Optional['GameController'] = None,
                 user_settings_service: Optional[Any] = None,
                 classification_model: Optional[MoveClassificationModel] = None,
                 database_controller: Optional[Any] = None) -> None:
        """Initialize the game analysis controller.
        
        Args:
            config: Configuration dictionary.
            game_model: GameModel instance.
            moves_list_model: MovesListModel instance.
            engine_model: EngineModel instance.
            opening_service: OpeningService instance.
            game_controller: Optional GameController instance for updating board position.
            user_settings_service: Optional UserSettingsService instance for loading user settings.
            classification_model: Optional MoveClassificationModel instance for classification settings.
            database_controller: Optional DatabaseController instance for marking databases as unsaved.
        """
        super().__init__()
        self.config = config
        self.game_model = game_model
        self.moves_list_model = moves_list_model
        self.engine_model = engine_model
        self.opening_service = opening_service
        self.game_controller = game_controller
        self.user_settings_service = user_settings_service
        self.classification_model = classification_model
        self.database_controller = database_controller
        
        # Get game analysis configuration
        game_analysis_config = config.get("game_analysis", {})
        self.max_depth = game_analysis_config.get("max_depth", 18)
        self.time_limit_ms = game_analysis_config.get("time_limit_per_move_ms", 3000)
        self.max_threads = game_analysis_config.get("max_threads", 6)
        self.progress_update_interval_ms = game_analysis_config.get("progress_update_interval_ms", 500)
        
        # If no model provided, load settings the old way (for backward compatibility)
        if self.classification_model is None:
            self._load_settings()
        else:
            # Connect to model's settings_changed signal
            self.classification_model.settings_changed.connect(self._on_classification_settings_changed)
            # Initialize instance variables as fallbacks for properties
            self._load_settings()
        
        # Initialize book move service
        self.book_move_service = BookMoveService(config, opening_service)
        
        # Analysis state
        self._is_analyzing = False
        self._cancelled = False
        self._engine_service: Optional[GameAnalysisEngineService] = None
        self._current_move_index = 0
        self._moves_to_analyze: List[Dict[str, Any]] = []
        self._progress_timer: Optional[QTimer] = None
        self._previous_evaluation = 0.0  # Track previous position's evaluation
        self._previous_is_mate = False
        self._previous_mate_moves = 0
        self._analyzing_best_move = False  # Track if we're analyzing position before (best move) or after (evaluation)
        self._best_alternative_move = ""  # Store best alternative move (PV1) from position before
        self._best_move_evaluation = None  # Store evaluation after playing the best move (from position before analysis)
        self._best_move_is_mate = False  # Store whether best move leads to mate
        self._best_move_mate_moves = 0  # Store mate moves for best move
        self._best_move_pv2 = ""  # Store PV2 move from position before
        self._best_move_pv3 = ""  # Store PV3 move from position before
        self._best_move_depth = 0  # Store depth from position before analysis
        self._move_depth = 0  # Store depth from position after analysis
        self._consecutive_errors = 0  # Track consecutive errors to detect engine failure
        self._post_game_brilliancy_refinement = False  # Post-game brilliancy refinement toggle
        
        # Progress tracking
        self._last_progress_depth = 0
        self._last_progress_centipawns = 0.0
        self._last_progress_time = 0.0
        self._current_engine_name = ""
        self._current_threads = 0
        self._analysis_start_time: Optional[float] = None  # Track when analysis started (timestamp in ms)
        self._move_times: List[float] = []  # Track time taken for each completed move (in ms)
    
    def _load_settings(self) -> None:
        """Load settings from config and user settings."""
        # Get game analysis configuration (defaults)
        game_analysis_config = self.config.get("game_analysis", {})
        
        # Load defaults for assessment thresholds
        default_thresholds = game_analysis_config.get("assessment_thresholds", {})
        self._good_move_max_cpl = default_thresholds.get("good_move_max_cpl", 50)
        self._inaccuracy_max_cpl = default_thresholds.get("inaccuracy_max_cpl", 100)
        self._mistake_max_cpl = default_thresholds.get("mistake_max_cpl", 200)
        
        # Load defaults for brilliant criteria
        default_brilliant = game_analysis_config.get("brilliant_criteria", {})
        self._min_eval_swing = default_brilliant.get("min_eval_swing", 50)
        self._min_material_sacrifice = default_brilliant.get("min_material_sacrifice", 300)
        self._max_eval_before = default_brilliant.get("max_eval_before", 500)
        self._exclude_already_winning = default_brilliant.get("exclude_already_winning", True)
        self._material_sacrifice_lookahead_plies = default_brilliant.get("material_sacrifice_lookahead_plies", 3)
        
        # Override with user settings if available
        if self.user_settings_service:
            user_settings = self.user_settings_service.get_settings()
            user_game_analysis = user_settings.get("game_analysis_settings", {})
            
            # Override thresholds
            user_thresholds = user_game_analysis.get("assessment_thresholds", {})
            if user_thresholds:
                self._good_move_max_cpl = user_thresholds.get("good_move_max_cpl", self._good_move_max_cpl)
                self._inaccuracy_max_cpl = user_thresholds.get("inaccuracy_max_cpl", self._inaccuracy_max_cpl)
                self._mistake_max_cpl = user_thresholds.get("mistake_max_cpl", self._mistake_max_cpl)
            
            # Override brilliant criteria
            user_brilliant = user_game_analysis.get("brilliant_criteria", {})
            if user_brilliant:
                self._min_eval_swing = user_brilliant.get("min_eval_swing", self._min_eval_swing)
                self._min_material_sacrifice = user_brilliant.get("min_material_sacrifice", self._min_material_sacrifice)
                self._max_eval_before = user_brilliant.get("max_eval_before", self._max_eval_before)
                self._exclude_already_winning = user_brilliant.get("exclude_already_winning", self._exclude_already_winning)
                self._material_sacrifice_lookahead_plies = user_brilliant.get("material_sacrifice_lookahead_plies", self._material_sacrifice_lookahead_plies)
    
    def reload_settings(self) -> None:
        """Reload settings from config and user settings."""
        if self.classification_model is None:
            self._load_settings()
        # If using model, settings are automatically updated via signal
    
    def _on_classification_settings_changed(self) -> None:
        """Handle classification settings changed signal."""
        # Settings are automatically updated from model properties
        # This method can be used for any additional logic needed when settings change
        pass
    
    # Helper properties to access classification settings from model or instance variables
    @property
    def good_move_max_cpl(self) -> int:
        """Get good move max CPL threshold."""
        if self.classification_model:
            return self.classification_model.good_move_max_cpl
        return getattr(self, '_good_move_max_cpl', 50)
    
    @property
    def inaccuracy_max_cpl(self) -> int:
        """Get inaccuracy max CPL threshold."""
        if self.classification_model:
            return self.classification_model.inaccuracy_max_cpl
        return getattr(self, '_inaccuracy_max_cpl', 100)
    
    @property
    def mistake_max_cpl(self) -> int:
        """Get mistake max CPL threshold."""
        if self.classification_model:
            return self.classification_model.mistake_max_cpl
        return getattr(self, '_mistake_max_cpl', 200)
    
    @property
    def min_eval_swing(self) -> int:
        """Get minimum eval swing for brilliancy."""
        if self.classification_model:
            return self.classification_model.min_eval_swing
        return getattr(self, '_min_eval_swing', 50)
    
    @property
    def min_material_sacrifice(self) -> int:
        """Get minimum material sacrifice for brilliancy."""
        if self.classification_model:
            return self.classification_model.min_material_sacrifice
        return getattr(self, '_min_material_sacrifice', 300)
    
    @property
    def max_eval_before(self) -> int:
        """Get maximum eval before move for brilliancy."""
        if self.classification_model:
            return self.classification_model.max_eval_before
        return getattr(self, '_max_eval_before', 500)
    
    @property
    def exclude_already_winning(self) -> bool:
        """Get exclude already winning flag for brilliancy."""
        if self.classification_model:
            return self.classification_model.exclude_already_winning
        return getattr(self, '_exclude_already_winning', True)
    
    @property
    def material_sacrifice_lookahead_plies(self) -> int:
        """Get material sacrifice lookahead plies for brilliancy."""
        if self.classification_model:
            return self.classification_model.material_sacrifice_lookahead_plies
        return getattr(self, '_material_sacrifice_lookahead_plies', 3)
    
    @property
    def is_analyzing(self) -> bool:
        """Check if analysis is currently running.
        
        Returns:
            True if analysis is running, False otherwise.
        """
        return self._is_analyzing
    
    def start_analysis(self) -> tuple[bool, Optional[str]]:
        """Start game analysis.
        
        This method will:
        1. Clear previous analysis data
        2. Extract moves from the active game
        3. Iterate through each move and analyze it
        
        Returns:
            Tuple of (success: bool, error_message: Optional[str]).
            If success is True, error_message is None.
            If success is False, error_message contains the reason.
        """
        # Check if there's an active game
        active_game = self.game_model.active_game
        if active_game is None:
            return (False, "No active game")
        
        # Check if analysis is already running
        if self._is_analyzing:
            return (False, "Analysis already running")
        
        # Reset analysis flag at start (in case user runs analysis again but aborts)
        self.game_model.set_is_game_analyzed(False)
        
        # Get engine assignment for game analysis
        engine_assignment = self.engine_model.get_assignment(EngineModel.TASK_GAME_ANALYSIS)
        if engine_assignment is None:
            return (False, "No engine assigned to game analysis task")
        
        engine = self.engine_model.get_engine(engine_assignment)
        if engine is None:
            return (False, f"Engine with ID {engine_assignment} not found")
        
        if not engine.is_valid:
            return (False, f"Engine {engine.name} is not valid: {engine.validation_error}")
        
        # Check if moves list model is available
        if self.moves_list_model is None:
            return (False, "Moves list model not available")
        
        # Clear previous analysis data
        self.moves_list_model.clear_analysis_data()
        
        # Extract moves from game
        moves_data = self._extract_moves_for_analysis(active_game)
        if not moves_data:
            return (False, "No moves found in game")
        
        # Initialize analysis state
        self._is_analyzing = True
        self._cancelled = False
        self._current_move_index = 0
        self._moves_to_analyze = moves_data
        self._previous_evaluation = 0.0  # Starting position evaluation
        self._previous_is_mate = False
        self._previous_mate_moves = 0
        self._analyzing_best_move = False
        self._best_alternative_move = ""
        self._best_move_pv2 = ""
        self._best_move_pv3 = ""
        self._best_move_evaluation = None
        self._best_move_is_mate = False
        self._best_move_depth = 0
        self._move_depth = 0
        self._best_move_mate_moves = 0
        self._consecutive_errors = 0
        self._pending_best_move_analysis: Optional[Dict[str, Any]] = None
        
        # Track analysis timing for progress reporting
        self._analysis_start_time = time.time() * 1000.0  # milliseconds
        self._move_times = []  # Track time taken for each completed move
        self._current_move_start_time: Optional[float] = None  # Track when current move started
        
        # Get task-specific parameters for this engine (with fallback to config.json)
        from pathlib import Path
        from app.services.engine_parameters_service import EngineParametersService
        engine_path = Path(engine.path) if not isinstance(engine.path, Path) else engine.path
        
        # Load task-specific parameters from engine_parameters.json
        task_params = EngineParametersService.get_task_parameters_for_engine(
            engine_path,
            "game_analysis",
            self.config
        )
        
        # Use task-specific parameters if available, otherwise use config.json defaults
        max_depth = task_params.get("depth", self.max_depth)
        time_limit_ms = task_params.get("movetime", self.time_limit_ms)
        max_threads = task_params.get("threads", self.max_threads)
        
        # Extract engine-specific options (all keys except common parameters)
        engine_options = {}
        for key, value in task_params.items():
            if key not in ["threads", "depth", "movetime"]:
                engine_options[key] = value
        
        # Initialize engine service
        self._engine_service = GameAnalysisEngineService(
            engine_path,
            max_depth,
            time_limit_ms,
            max_threads,
            engine.name,
            engine_options
        )
        self._current_engine_name = engine.name
        self._current_threads = max_threads or 0
        
        # Start the persistent engine thread
        if not self._engine_service.start_engine():
            return (False, "Failed to start engine thread")
        
        # Connect signals once to the persistent thread
        analysis_thread = self._engine_service.analysis_thread
        if analysis_thread:
            # Disconnect any existing connections to avoid duplicates
            try:
                analysis_thread.analysis_complete.disconnect()
            except TypeError:
                pass  # No connections to disconnect
            try:
                analysis_thread.progress_update.disconnect()
            except TypeError:
                pass
            try:
                analysis_thread.error_occurred.disconnect()
            except TypeError:
                pass
            
            # Connect signals - we'll use move_info tracking to route to correct handlers
            analysis_thread.progress_update.connect(self._on_progress_update)
            analysis_thread.error_occurred.connect(self._on_analysis_error)
        
        # Show progress bar
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        progress_service.show_progress()
        progress_service.set_progress(0)
        
        # Emit started signal
        self.analysis_started.emit()
        
        # Start analyzing first move
        self._analyze_next_move()
        
        return (True, None)
    
    def cancel_analysis(self) -> None:
        """Cancel current analysis."""
        if not self._is_analyzing:
            return
        
        self._cancelled = True
        
        # Stop engine service
        if self._engine_service:
            self._engine_service.stop_analysis()
        
        # Stop progress timer
        if self._progress_timer:
            self._progress_timer.stop()
            self._progress_timer = None
        
        # Update status bar with cancellation message
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        total_half_moves = len(self._moves_to_analyze) if self._moves_to_analyze else 0
        total_full_moves = (total_half_moves + 1) // 2
        current_half_move = self._current_move_index + 1
        current_full_move = (current_half_move + 1) // 2
        progress_service.set_status(f"Game Analysis cancelled: Analyzed {current_full_move}/{total_full_moves} moves")
        progress_service.hide_progress()
        
        # Update state
        self._is_analyzing = False
        
        # Emit cancelled signal
        self.analysis_cancelled.emit()
        
        # Cleanup
        self._cleanup()
    
    def _extract_moves_for_analysis(self, game_data) -> List[Dict[str, Any]]:
        """Extract moves from game data for analysis.
        
        Args:
            game_data: GameData instance.
            
        Returns:
            List of move dictionaries with position info.
        """
        moves_list = []
        
        try:
            pgn_text = game_data.pgn
            pgn_io = io.StringIO(pgn_text)
            game = chess.pgn.read_game(pgn_io)
            
            if game is None:
                return []
            
            board = game.board()
            move_number = 1
            
            # Iterate through mainline moves
            # game.mainline() returns an iterator of nodes, but we need to iterate properly
            node = game
            while node.variations:
                # Get the next move in the mainline
                node = node.variation(0)
                move = node.move
                
                if move is None:
                    break
                
                is_white_move = board.turn == chess.WHITE
                
                # Get position before move
                fen_before = board.fen()
                board_before = board.copy()
                
                # Make move
                board.push(move)
                fen_after = board.fen()
                board_after = board.copy()
                
                # Get move SAN - use the board's SAN method
                # Need to temporarily undo the move to get SAN, then redo it
                board.pop()
                move_san = board.san(move)
                board.push(move)
                
                # Store move info
                # Note: move_number is the actual move number (1, 2, 3, etc.)
                # For white moves, move_number stays the same
                # For black moves, move_number is the same as the white move in that pair
                move_info = {
                    "move_number": move_number,
                    "is_white_move": is_white_move,
                    "move_san": move_san,
                    "move": move,
                    "fen_before": fen_before,
                    "fen_after": fen_after,
                    "board_before": board_before,
                    "board_after": board_after,
                }
                
                moves_list.append(move_info)
                
                # Update move number after black moves (completing a move pair)
                if not is_white_move:
                    move_number += 1
            
            return moves_list
        
        except Exception as e:
            # Return empty list on error
            return []
    
    def _analyze_next_move(self) -> None:
        """Analyze the next move in the queue."""
        # Check if analysis is complete (all moves analyzed or cancelled)
        moves_count = len(self._moves_to_analyze) if self._moves_to_analyze else 0
        is_complete = self._cancelled or self._current_move_index >= moves_count
        
        if is_complete:
            # Analysis complete
            self._is_analyzing = False
            
            # Update status bar with completion message
            from app.services.progress_service import ProgressService
            progress_service = ProgressService.get_instance()
            total_half_moves = moves_count
            total_full_moves = (total_half_moves + 1) // 2
            
            if self._cancelled:
                current_half_move = self._current_move_index + 1
                current_full_move = (current_half_move + 1) // 2
                progress_service.set_status(f"Game Analysis cancelled: Analyzed {current_full_move}/{total_full_moves} moves")
                # Flag stays False (already set at start)
            else:
                # Analysis completed successfully
                progress_service.set_status(f"Game Analysis completed: Analyzed {total_full_moves} moves")
                
                # If post-game brilliancy refinement is enabled, perform secondary pass
                if self._post_game_brilliancy_refinement:
                    progress_service.set_status("Performing post-game brilliancy refinement...")
                    self._perform_post_game_brilliancy_refinement()
                
                # Set flag to True after refinement (if enabled) completes
                self.game_model.set_is_game_analyzed(True)
                
                # Store analysis results in PGN tag if enabled
                if self.user_settings_service:
                    settings = self.user_settings_service.get_settings()
                    game_analysis_settings = settings.get("game_analysis", {})
                    store_analysis_results = game_analysis_settings.get("store_analysis_results_in_pgn_tag", False)
                    
                    if store_analysis_results and self.game_model.active_game and self.moves_list_model:
                        from app.services.analysis_data_storage_service import AnalysisDataStorageService
                        # Get all moves from model
                        moves = self.moves_list_model.get_all_moves()
                        if moves:
                            # Store analysis data in PGN tag (pass config for app version)
                            success = AnalysisDataStorageService.store_analysis_data(
                                self.game_model.active_game, 
                                moves, 
                                self.config
                            )
                            if success:
                                # Emit metadata_updated signal to notify views (e.g., PGN view, metadata view)
                                self.game_model.metadata_updated.emit()
                                
                                # Update database model to persist the change and mark as unsaved
                                if self.database_controller:
                                    # Find the database model that contains this game
                                    database_model = self._find_database_model_for_game(self.game_model.active_game)
                                    if database_model:
                                        # Update the game in the database model
                                        database_model.update_game(self.game_model.active_game)
                                        # Mark database as having unsaved changes
                                        self.database_controller.mark_database_unsaved(database_model)
            
            progress_service.hide_progress()
            
            self.analysis_completed.emit()
            self._cleanup()
            return
        
        move_info = self._moves_to_analyze[self._current_move_index]
        
        # Track when this move started
        self._current_move_start_time = time.time() * 1000.0  # milliseconds
        
        # Update active move to show the position being analyzed
        # This will update the board and PGN notation automatically
        # ply_index calculation:
        # - ply_index 0 = starting position
        # - ply_index 1 = after white's first move (move 1)
        # - ply_index 2 = after black's first move (move 1)
        # - ply_index 3 = after white's second move (move 2)
        # - etc.
        # For move_number N:
        #   - White move: ply_index = (N - 1) * 2 + 1 = N * 2 - 1
        #   - Black move: ply_index = (N - 1) * 2 + 2 = N * 2
        move_number = move_info["move_number"]
        is_white_move = move_info["is_white_move"]
        if is_white_move:
            ply_index = move_number * 2 - 1  # After white's move
        else:
            ply_index = move_number * 2  # After black's move
        
        # Update active move in game model and board position
        # This will update the board and PGN notation automatically
        if self.game_controller:
            # Use GameController to update both active move and board position
            self.game_controller.navigate_to_ply(ply_index)
        else:
            # Fallback: only update active move (board won't update)
            self.game_model.set_active_move_ply(ply_index)
        
        # We need to analyze TWO positions:
        # 1. Position BEFORE the move -> to get the best alternative move
        # 2. Position AFTER the move -> to get the evaluation (for CPL calculation)
        
        # First, analyze position BEFORE the move to get best alternative move
        # IMPORTANT: fen_before is the position where the move is ABOUT TO BE PLAYED
        # So if is_white_move is True, fen_before is the position where White is to move
        # If is_white_move is False, fen_before is the position where Black is to move
        fen_before = move_info["fen_before"]
        board_before = move_info["board_before"]
        
        # Verify that fen_before matches the expected position
        # The board_before should have the correct side to move
        expected_turn = move_info["is_white_move"]  # True if White is to move, False if Black
        if board_before.turn != expected_turn:
            # This is a critical error - the position doesn't match what we expect
            import logging
            logging.error(f"Position mismatch: move_info is_white_move={expected_turn}, but board_before.turn={board_before.turn}")
        
        self._analyzing_best_move = True
        self._best_alternative_move = ""
        
        # Queue position before for analysis
        # Store move_info for routing the completion signal
        self._pending_best_move_analysis = move_info
        
        # Queue analysis for position before
        thread = self._engine_service.analyze_position(
            fen_before,
            move_info["move_number"],
            self.progress_update_interval_ms
        )
        
        if not thread:
            self._on_analysis_error("Failed to queue position for analysis")
            return
        
        # Connect analysis_complete signal for this specific analysis
        # We need to disconnect any existing connection first
        try:
            thread.analysis_complete.disconnect()
        except TypeError:
            pass  # No connections to disconnect
        
        # Connect with lambda that captures move_info
        thread.analysis_complete.connect(
            lambda eval_cp, is_mate, mate_moves, best_move, pv1, pv2, pv3, pv2_score, pv3_score, pv2_score_black, pv3_score_black, depth, nps, engine_name: 
            self._on_best_move_analysis_complete(move_info, best_move, pv2, pv3, eval_cp, is_mate, mate_moves, depth)
        )
        
        # Setup progress timer for periodic updates
        if self._progress_timer:
            self._progress_timer.stop()
        self._progress_timer = QTimer()
        self._progress_timer.timeout.connect(self._emit_progress_update)
        self._progress_timer.start(self.progress_update_interval_ms)
    
    def _on_best_move_analysis_complete(self, move_info: Dict[str, Any], best_move_san: str, 
                                       pv2_move_san: str, pv3_move_san: str,
                                       best_move_eval: float, best_move_is_mate: bool, best_move_mate_moves: int, depth: int) -> None:
        """Handle completion of best move analysis (position before the move).
        
        Args:
            move_info: Move information dictionary.
            best_move_san: Best alternative move (PV1) in SAN notation.
            pv2_move_san: Second best move (PV2) in SAN notation.
            pv3_move_san: Third best move (PV3) in SAN notation.
            best_move_eval: Evaluation after playing the best move (from position before analysis).
            best_move_is_mate: True if best move leads to mate.
            best_move_mate_moves: Mate moves for best move.
            depth: Engine depth for this analysis.
        """
        if self._cancelled:
            return
        
        # Reset consecutive errors on successful analysis
        self._consecutive_errors = 0
        
        # Store the best alternative moves and their evaluation
        self._best_alternative_move = best_move_san
        self._best_move_pv2 = pv2_move_san
        self._best_move_pv3 = pv3_move_san
        self._best_move_evaluation = best_move_eval
        self._best_move_is_mate = best_move_is_mate
        self._best_move_mate_moves = best_move_mate_moves
        self._best_move_depth = depth
        
        # Check if this is a book move - if so, don't store best moves
        if self._is_book_move(move_info):
            self._best_alternative_move = ""
            self._best_move_pv2 = ""
            self._best_move_pv3 = ""
            self._best_move_evaluation = None
            self._best_move_depth = 0
        
        # Now analyze position AFTER the move to get evaluation
        self._analyzing_best_move = False
        fen_after = move_info["fen_after"]
        
        # Queue position after for analysis
        thread = self._engine_service.analyze_position(
            fen_after,
            move_info["move_number"],
            self.progress_update_interval_ms
        )
        
        if not thread:
            self._on_analysis_error("Failed to queue position for analysis")
            return
        
        # Connect analysis_complete signal for this specific analysis
        # We need to disconnect any existing connection first
        try:
            thread.analysis_complete.disconnect()
        except TypeError:
            pass  # No connections to disconnect
        
        # Connect with lambda that captures move_info
        thread.analysis_complete.connect(
            lambda eval_cp, is_mate, mate_moves, best_move, pv1, pv2, pv3, pv2_score, pv3_score, pv2_score_black, pv3_score_black, depth, nps, engine_name: 
            self._on_move_analysis_complete(move_info, eval_cp, is_mate, mate_moves, depth, pv2_score, pv3_score, pv2_score_black, pv3_score_black)
        )
    
    def _on_move_analysis_complete(self, move_info: Dict[str, Any], eval_after: float, 
                                   is_mate: bool, mate_moves: int, depth: int,
                                   pv2_score: float = 0.0, pv3_score: float = 0.0,
                                   pv2_score_black: float = 0.0, pv3_score_black: float = 0.0) -> None:
        """Handle completion of move evaluation analysis (position after the move).
        
        Args:
            move_info: Move information dictionary.
            eval_after: Evaluation after the move (centipawns).
            is_mate: True if mate was found.
            mate_moves: Number of moves to mate.
            depth: Engine depth for this analysis.
        """
        self._move_depth = depth
        if self._cancelled:
            return
        
        # Reset consecutive errors on successful analysis
        self._consecutive_errors = 0
        
        # Get evaluation before move (from previous position analysis)
        eval_before = self._previous_evaluation
        is_mate_before = self._previous_is_mate
        mate_moves_before = self._previous_mate_moves
        
        # If this is the first move, we need to analyze the position before
        # For now, if there's no previous evaluation, assume it's a normal position
        if eval_before is None:
            # Starting position - assume even position (0.0 evaluation)
            eval_before = 0.0
            is_mate_before = False
            mate_moves_before = 0
        
        # Get the evaluation after playing the best move (from position before analysis)
        # NOTE: This evaluation from analyzing fen_before represents the evaluation of the position
        # AFTER playing the best move (from the opponent's perspective after the move is played).
        # This is the standard UCI behavior - when you analyze a position, the score represents
        # the evaluation after playing the best move in the best continuation.
        eval_after_best_move = self._best_move_evaluation
        is_mate_after_best = self._best_move_is_mate if self._best_move_evaluation is not None else False
        mate_moves_after_best = self._best_move_mate_moves if self._best_move_evaluation is not None else 0
        
        # Calculate CPL
        # CPL = evaluation after playing best move - evaluation after playing actual move
        # If the played move matches the best move, CPL should be 0 (or very close due to engine variance)
        is_white_move = move_info["is_white_move"]
        played_move_san = move_info["move_san"]
        best_alternative_move = self._best_alternative_move
        
        # Check if the played move matches the best move
        # If so, CPL should be 0 (or very low due to engine variance)
        # Normalize moves by removing check/checkmate symbols and case differences
        played_move_normalized = MoveAnalysisService.normalize_move(played_move_san)
        best_move_normalized = MoveAnalysisService.normalize_move(best_alternative_move) if best_alternative_move else ""
        
        # Check if the played move matches the best move
        moves_match = bool(best_move_normalized and played_move_normalized == best_move_normalized)
        
        # Calculate CPL using service
        cpl = MoveAnalysisService.calculate_cpl(
            eval_before=eval_before,
            eval_after=eval_after,
            eval_after_best_move=eval_after_best_move,
            is_white_move=is_white_move,
            is_mate=is_mate,
            is_mate_before=is_mate_before,
            is_mate_after_best=is_mate_after_best,
            mate_moves=mate_moves,
            mate_moves_before=mate_moves_before,
            mate_moves_after_best=mate_moves_after_best,
            moves_match=moves_match
        )
        
        # Check if move is a book move
        is_book_move = self._is_book_move(move_info)
        
        # Get the best alternative move from the position before analysis
        best_alternative_move = self._best_alternative_move
        
        # Store evaluation data in move_info for post-game refinement
        move_info["eval_before"] = eval_before
        move_info["eval_after"] = eval_after
        move_info["best_move_san"] = best_alternative_move
        move_info["cpl"] = cpl
        
        # Assess move quality
        if is_book_move:
            assess = "Book Move"
        else:
            # Calculate material sacrifice for brilliant detection
            material_sacrifice = self._calculate_material_sacrifice_for_brilliance(move_info)
            
            # Prepare classification thresholds
            classification_thresholds = {
                "good_move_max_cpl": self.good_move_max_cpl,
                "inaccuracy_max_cpl": self.inaccuracy_max_cpl,
                "mistake_max_cpl": self.mistake_max_cpl,
                "min_eval_swing": self.min_eval_swing,
                "min_material_sacrifice": self.min_material_sacrifice,
                "max_eval_before": self.max_eval_before,
                "exclude_already_winning": self.exclude_already_winning,
                "best_move_is_mate": self._best_move_is_mate
            }
            
            assess = MoveAnalysisService.assess_move_quality(
                cpl, eval_before, eval_after, move_info, best_alternative_move, moves_match,
                classification_thresholds, material_sacrifice
            )
        
        # Calculate CPL for PV2 and PV3
        # CPL for PV2 = difference between PV2 score and played move evaluation
        # CPL for PV3 = difference between PV3 score and played move evaluation
        cpl_white_2_str = ""
        cpl_white_3_str = ""
        cpl_black_2_str = ""
        cpl_black_3_str = ""
        
        if not is_book_move:
            if is_white_move:
                # For white moves, use pv2_score and pv3_score (from white's perspective)
                if pv2_score != 0.0:  # Only calculate if PV2 score is available
                    cpl_2 = MoveAnalysisService.calculate_pv_cpl(pv2_score, eval_after)
                    cpl_white_2_str = MoveAnalysisService.format_cpl(cpl_2)
                if pv3_score != 0.0:  # Only calculate if PV3 score is available
                    cpl_3 = MoveAnalysisService.calculate_pv_cpl(pv3_score, eval_after)
                    cpl_white_3_str = MoveAnalysisService.format_cpl(cpl_3)
            else:
                # For black moves, use pv2_score_black and pv3_score_black (from black's perspective)
                if pv2_score_black != 0.0:  # Only calculate if PV2 score is available
                    cpl_2 = MoveAnalysisService.calculate_pv_cpl(pv2_score_black, eval_after)
                    cpl_black_2_str = MoveAnalysisService.format_cpl(cpl_2)
                if pv3_score_black != 0.0:  # Only calculate if PV3 score is available
                    cpl_3 = MoveAnalysisService.calculate_pv_cpl(pv3_score_black, eval_after)
                    cpl_black_3_str = MoveAnalysisService.format_cpl(cpl_3)
        
        # Format evaluation
        eval_str = MoveAnalysisService.format_evaluation(eval_after, is_mate, mate_moves, is_white_move)
        cpl_str = MoveAnalysisService.format_cpl(cpl) if not is_book_move else ""
        
        # Find the correct MoveData row based on move_number
        # MovesListModel stores full moves (white + black) per row
        # Row 0 = Move 1, Row 1 = Move 2, etc.
        move_number = move_info["move_number"]
        is_white_move = move_info["is_white_move"]
        
        # For white moves, the row index is move_number - 1
        # For black moves, the row index is also move_number - 1 (same row as white's move in that pair)
        row_index = move_number - 1
        
        # Validate row_index before accessing
        if row_index < 0 or row_index >= self.moves_list_model.rowCount():
            return
        
        # Get the move data for this row
        move_data = self.moves_list_model.get_move(row_index)
        if move_data:
            # Best alternative move is from position BEFORE the move
            # Evaluation is from position AFTER the move
            
            # Normalize moves for comparison (remove check/checkmate symbols)
            played_move_normalized = MoveAnalysisService.normalize_move(played_move_san)
            
            # Get board positions for capture and material calculation
            board_before = move_info["board_before"]
            board_after = move_info["board_after"]
            move = move_info["move"]
            
            # Calculate material for BOTH sides after each move
            # This ensures material values are always up-to-date for both players
            white_material_after = calculate_material_count(board_after, is_white=True)
            black_material_after = calculate_material_count(board_after, is_white=False)
            
            # Count pieces for both sides after each move
            white_pieces = count_pieces(board_after, is_white=True)
            black_pieces = count_pieces(board_after, is_white=False)
            
            if is_white_move:
                # White just moved - store evaluation after white's move
                move_data.eval_white = eval_str
                move_data.cpl_white = cpl_str
                move_data.cpl_white_2 = cpl_white_2_str
                move_data.cpl_white_3 = cpl_white_3_str
                move_data.assess_white = assess
                # Best alternative moves are for white (from position before white's move)
                if not is_book_move:
                    move_data.best_white = best_alternative_move
                    move_data.best_white_2 = self._best_move_pv2
                    move_data.best_white_3 = self._best_move_pv3
                    move_data.white_depth = self._best_move_depth
                    # Check if played move is in top 3
                    move_data.white_is_top3 = MoveAnalysisService.is_move_in_top3(
                        played_move_normalized,
                        best_alternative_move,
                        self._best_move_pv2,
                        self._best_move_pv3
                    )
                else:
                    move_data.best_white = ""
                    move_data.best_white_2 = ""
                    move_data.best_white_3 = ""
                    move_data.white_depth = 0
                    move_data.white_is_top3 = False
                
                # Calculate capture and material for white's move
                move_data.white_capture = get_captured_piece_letter(board_before, move)
                move_data.white_material = white_material_after
                move_data.black_material = black_material_after
                # Update piece counts after white's move
                move_data.white_queens = white_pieces[chess.QUEEN]
                move_data.white_rooks = white_pieces[chess.ROOK]
                move_data.white_bishops = white_pieces[chess.BISHOP]
                move_data.white_knights = white_pieces[chess.KNIGHT]
                move_data.white_pawns = white_pieces[chess.PAWN]
                move_data.black_queens = black_pieces[chess.QUEEN]
                move_data.black_rooks = black_pieces[chess.ROOK]
                move_data.black_bishops = black_pieces[chess.BISHOP]
                move_data.black_knights = black_pieces[chess.KNIGHT]
                move_data.black_pawns = black_pieces[chess.PAWN]
                # Capture FEN after white's move
                move_data.fen_white = board_after.fen()
            else:
                # Black just moved - store evaluation after black's move
                move_data.eval_black = eval_str
                move_data.cpl_black = cpl_str
                move_data.cpl_black_2 = cpl_black_2_str
                move_data.cpl_black_3 = cpl_black_3_str
                move_data.assess_black = assess
                # Best alternative moves are for black (from position before black's move)
                if not is_book_move:
                    move_data.best_black = best_alternative_move
                    move_data.best_black_2 = self._best_move_pv2
                    move_data.best_black_3 = self._best_move_pv3
                    move_data.black_depth = self._best_move_depth
                    # Check if played move is in top 3
                    move_data.black_is_top3 = MoveAnalysisService.is_move_in_top3(
                        played_move_normalized,
                        best_alternative_move,
                        self._best_move_pv2,
                        self._best_move_pv3
                    )
                else:
                    move_data.best_black = ""
                    move_data.best_black_2 = ""
                    move_data.best_black_3 = ""
                    move_data.black_depth = 0
                    move_data.black_is_top3 = False
                
                # Calculate capture and material for black's move
                move_data.black_capture = get_captured_piece_letter(board_before, move)
                move_data.white_material = white_material_after
                move_data.black_material = black_material_after
                # Update piece counts after black's move
                move_data.white_queens = white_pieces[chess.QUEEN]
                move_data.white_rooks = white_pieces[chess.ROOK]
                move_data.white_bishops = white_pieces[chess.BISHOP]
                move_data.white_knights = white_pieces[chess.KNIGHT]
                move_data.white_pawns = white_pieces[chess.PAWN]
                move_data.black_queens = black_pieces[chess.QUEEN]
                move_data.black_rooks = black_pieces[chess.ROOK]
                move_data.black_bishops = black_pieces[chess.BISHOP]
                move_data.black_knights = black_pieces[chess.KNIGHT]
                move_data.black_pawns = black_pieces[chess.PAWN]
                # Capture FEN after black's move
                move_data.fen_black = board_after.fen()
            
            # Emit data changed signal for this row
            # Use visible column indices (0 to columnCount()-1)
            # The model's index() method expects visible column indices
            from PyQt6.QtCore import QModelIndex, Qt
            parent = QModelIndex()  # Invalid parent for table models
            top_left = self.moves_list_model.index(row_index, 0, parent)
            column_count = self.moves_list_model.columnCount(parent)
            if column_count > 0:
                bottom_right = self.moves_list_model.index(row_index, column_count - 1, parent)
            else:
                bottom_right = top_left
            
            if top_left.isValid() and bottom_right.isValid():
                # Emit dataChanged with both DisplayRole and BackgroundRole to ensure view updates
                # BackgroundRole is needed for active row highlighting
                self.moves_list_model.dataChanged.emit(top_left, bottom_right, 
                                                      [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.BackgroundRole])
                
                # Emit signal to scroll to this row (for auto-scroll in view)
                # This will also trigger a repaint in the handler
                self.move_analyzed.emit(row_index)
        
        # Track time taken for this move
        if self._current_move_start_time is not None:
            move_time = time.time() * 1000.0 - self._current_move_start_time
            self._move_times.append(move_time)
            self._current_move_start_time = None
        
        # Update previous evaluation for next move
        self._previous_evaluation = eval_after
        self._previous_is_mate = is_mate
        self._previous_mate_moves = mate_moves
        
        # Move to next move
        self._current_move_index += 1
        
        # Check if we've completed all moves before calling _analyze_next_move
        moves_count = len(self._moves_to_analyze) if self._moves_to_analyze else 0
        if self._current_move_index >= moves_count:
            # Call _analyze_next_move which will detect completion and set the flag
            self._analyze_next_move()
        else:
            self._analyze_next_move()
    
    def _on_progress_update(self, depth: int, centipawns: int, elapsed_ms: float,
                           engine_name: str, threads: int, move_number: int) -> None:
        """Handle progress update from engine.
        
        Args:
            depth: Current search depth.
            centipawns: Current evaluation in centipawns.
            elapsed_ms: Elapsed time in milliseconds.
            engine_name: Engine name.
            threads: Number of threads.
            move_number: Current move number.
        """
        self._last_progress_depth = depth
        self._last_progress_centipawns = float(centipawns)
        self._last_progress_time = elapsed_ms
    
    def _format_time(self, seconds: float) -> str:
        """Format time duration nicely (seconds, minutes, hours).
        
        Args:
            seconds: Time in seconds.
            
        Returns:
            Formatted time string (e.g., "45s", "2m 30s", "1h 15m 30s").
        """
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s" if secs > 0 else f"{minutes}m"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            parts = [f"{hours}h"]
            if minutes > 0:
                parts.append(f"{minutes}m")
            if secs > 0:
                parts.append(f"{secs}s")
            return " ".join(parts)
    
    def _emit_progress_update(self) -> None:
        """Emit periodic progress update."""
        if not self._is_analyzing:
            return
        
        # Convert half-moves to full moves for display
        # total_half_moves includes all half-moves (white + black)
        # total_full_moves = (total_half_moves + 1) // 2 (round up for last move)
        total_half_moves = len(self._moves_to_analyze)
        total_full_moves = (total_half_moves + 1) // 2
        
        # current_move_index is 0-based, so current_half_move = current_move_index + 1
        # current_full_move = (current_half_move + 1) // 2
        current_half_move = self._current_move_index + 1
        current_full_move = (current_half_move + 1) // 2
        
        # Calculate progress percentage (0-100)
        progress_percent = int((current_full_move / total_full_moves) * 100) if total_full_moves > 0 else 0
        
        # Calculate estimated remaining time
        estimated_remaining_time = None
        if self._analysis_start_time is not None:
            # Calculate elapsed time
            elapsed_ms = time.time() * 1000.0 - self._analysis_start_time
            elapsed_seconds = elapsed_ms / 1000.0
            
            # Calculate remaining moves
            remaining_moves = total_full_moves - current_full_move
            
            estimated_remaining_seconds = None
            if remaining_moves > 0:
                if len(self._move_times) > 0:
                    # Use average time per completed half-move
                    # Note: _move_times tracks time per half-move, but remaining_moves is in full moves
                    # Each full move = 2 half-moves, so multiply by 2
                    avg_time_per_half_move = sum(self._move_times) / len(self._move_times) / 1000.0  # Convert to seconds
                    avg_time_per_full_move = avg_time_per_half_move * 2  # Each full move = 2 half-moves
                    estimated_remaining_seconds = avg_time_per_full_move * remaining_moves
                elif elapsed_seconds > 0 and current_full_move > 0:
                    # No completed moves yet, but we're analyzing a move
                    # Estimate based on elapsed time so far and current move progress
                    # Use elapsed time / current move number as rough estimate
                    avg_time_per_move = elapsed_seconds / max(current_full_move, 1)
                    estimated_remaining_seconds = avg_time_per_move * remaining_moves
                elif elapsed_seconds > 0:
                    # Very early in analysis - estimate based on elapsed time alone
                    # Assume similar time per move
                    estimated_remaining_seconds = elapsed_seconds * remaining_moves
            
            if estimated_remaining_seconds is not None and estimated_remaining_seconds > 0:
                estimated_remaining_time = self._format_time(estimated_remaining_seconds)
        
        # Update progress bar and status
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        progress_service.set_progress(progress_percent)
        
        # Build status message with progress info
        status_parts = [f"Game Analysis: Move {current_full_move}/{total_full_moves}"]
        if estimated_remaining_time:
            status_parts.append(f"Est. remaining: {estimated_remaining_time}")
        status_message = " - ".join(status_parts)
        progress_service.set_status(status_message)
        
        # Calculate total elapsed time since analysis started
        total_elapsed_ms = 0
        if self._analysis_start_time is not None:
            total_elapsed_ms = time.time() * 1000.0 - self._analysis_start_time
        
        self.analysis_progress.emit(
            current_full_move,
            total_full_moves,
            self._last_progress_depth,
            self._last_progress_centipawns,
            self._current_engine_name,
            self._current_threads,
            int(total_elapsed_ms)
        )
    
    def _on_analysis_error(self, error_message: str) -> None:
        """Handle analysis error.
        
        Args:
            error_message: Error message.
        """
        if self._cancelled:
            return
        
        # Track consecutive errors
        self._consecutive_errors += 1
        
        # Check if this is a critical engine failure
        critical_errors = [
            "Engine process terminated unexpectedly",
            "Engine process not initialized",
            "Engine did not respond",
            "Engine process terminated"
        ]
        
        is_critical_error = any(critical in error_message for critical in critical_errors)
        
        # If we have multiple consecutive errors or a critical error, stop analysis
        if is_critical_error or self._consecutive_errors >= 3:
            # Engine has failed - stop analysis and clean up
            self._is_analyzing = False
            
            # Update status bar with error message
            from app.services.progress_service import ProgressService
            progress_service = ProgressService.get_instance()
            total_half_moves = len(self._moves_to_analyze) if self._moves_to_analyze else 0
            total_full_moves = (total_half_moves + 1) // 2
            current_half_move = self._current_move_index + 1
            current_full_move = (current_half_move + 1) // 2
            progress_service.set_status(f"Game Analysis stopped: Engine error at move {current_full_move}/{total_full_moves} - {error_message}")
            progress_service.hide_progress()
            
            # Emit analysis completed signal (so UI can update)
            self.analysis_completed.emit()
            self._cleanup()
            return
        
        # Non-critical error - skip to next move and continue
        self._current_move_index += 1
        self._analyze_next_move()
    
    
    def _is_book_move(self, move_info: Dict[str, Any]) -> bool:
        """Check if a move is a book move.
        
        Args:
            move_info: Move information dictionary.
            
        Returns:
            True if move is in opening book, False otherwise.
        """
        board_before = move_info["board_before"]
        move = move_info["move"]
        
        return self.book_move_service.is_book_move(board_before, move)
    
    
    def _find_move_index(self, move_info: Dict[str, Any]) -> Optional[int]:
        """Find the index of a move in _moves_to_analyze.
        
        Args:
            move_info: Move information dictionary.
            
        Returns:
            Index in _moves_to_analyze, or None if not found.
        """
        move_number = move_info.get("move_number")
        is_white_move = move_info.get("is_white_move")
        
        for i, move in enumerate(self._moves_to_analyze):
            if (move.get("move_number") == move_number and 
                move.get("is_white_move") == is_white_move):
                return i
        return None
    
    def _calculate_material_sacrifice_for_brilliance(self, move_info: Dict[str, Any]) -> int:
        """Calculate material sacrifice for brilliancy detection.
        
        This method checks for material sacrifice in two ways:
        1. Direct material loss: The move itself loses material
        2. Forced material loss: The move leaves a piece en prise (undefended)
           and the opponent captures it on their next move.
        
        A move is NOT considered a sacrifice if:
        - The move itself captures material (gains material)
        - The opponent's later capture is unrelated to the current move
        
        Args:
            move_info: Current move information dictionary.
            
        Returns:
            Material sacrifice in centipawns (positive = material was sacrificed).
        """
        # Find current move index in _moves_to_analyze
        current_index = self._find_move_index(move_info)
        if current_index is None:
            return 0
        
        # Use service method with lookahead of 1 ply (immediate capture)
        return MoveAnalysisService.calculate_material_sacrifice(
            move_info, self._moves_to_analyze, current_index, lookahead_plies=1
        )
    
    
    
    def set_post_game_brilliancy_refinement(self, enabled: bool) -> None:
        """Set post-game brilliancy refinement toggle.
        
        Args:
            enabled: True if post-game brilliancy refinement is enabled, False otherwise.
        """
        self._post_game_brilliancy_refinement = enabled
    
    def _calculate_material_sacrifice_with_lookahead(self, move_info: Dict[str, Any], lookahead_plies: int = 3) -> int:
        """Calculate material sacrifice using multi-ply look-ahead.
        
        This method checks material balance over the next 2-3 plies to detect
        sacrifices that aren't immediately recaptured. It applies the same logic
        as _calculate_material_sacrifice_for_brilliance to avoid false positives.
        
        Args:
            move_info: Current move information dictionary.
            lookahead_plies: Number of plies to look ahead (default: 3).
            
        Returns:
            Material sacrifice in centipawns (positive = material was sacrificed).
        """
        current_index = self._find_move_index(move_info)
        if current_index is None:
            return 0
        
        # Use service method with specified lookahead
        return MoveAnalysisService.calculate_material_sacrifice(
            move_info, self._moves_to_analyze, current_index, lookahead_plies
        )
    
    def _perform_post_game_brilliancy_refinement(self) -> None:
        """Perform post-game brilliancy refinement using multi-ply look-ahead.
        
        This method re-checks all moves for brilliancy using a 2-3 ply look-ahead
        for material sacrifice detection, which can catch sacrifices that aren't
        immediately recaptured.
        """
        if not self._moves_to_analyze:
            return
        
        # Print debug header if brilliancy debug is enabled
        if _debug_brilliant_enabled:
            print("\n" + "=" * 80, file=sys.stderr)
            print("POST-GAME BRILLIANCY REFINEMENT PASS", file=sys.stderr)
            print("=" * 80, file=sys.stderr)
            print("Re-checking all moves with 2-3 ply look-ahead for material sacrifice detection.", file=sys.stderr)
            print("=" * 80 + "\n", file=sys.stderr)
        
        from app.services.progress_service import ProgressService
        from PyQt6.QtCore import QModelIndex, Qt
        progress_service = ProgressService.get_instance()
        
        moves_count = len(self._moves_to_analyze)
        brilliant_count = 0
        
        # Re-check each move for brilliancy using refined material sacrifice calculation
        for i, move_info in enumerate(self._moves_to_analyze):
            # Get stored evaluation data
            eval_before = move_info.get("eval_before", 0.0)
            eval_after = move_info.get("eval_after", 0.0)
            best_move_san = move_info.get("best_move_san", "")
            cpl = move_info.get("cpl", 0.0)
            
            # Calculate material sacrifice using multi-ply look-ahead
            material_loss = self._calculate_material_sacrifice_with_lookahead(move_info, lookahead_plies=self.material_sacrifice_lookahead_plies)
            
            # Re-check brilliancy with refined material sacrifice
            # Temporarily override material sacrifice calculation
            original_method = self._calculate_material_sacrifice_for_brilliance
            self._calculate_material_sacrifice_for_brilliance = lambda mi: material_loss if mi == move_info else original_method(mi)
            
            # Calculate material sacrifice for brilliant detection
            material_sacrifice = self._calculate_material_sacrifice_for_brilliance(move_info)
            
            # Prepare classification thresholds
            classification_thresholds = {
                "good_move_max_cpl": self.good_move_max_cpl,
                "inaccuracy_max_cpl": self.inaccuracy_max_cpl,
                "mistake_max_cpl": self.mistake_max_cpl,
                "min_eval_swing": self.min_eval_swing,
                "min_material_sacrifice": self.min_material_sacrifice,
                "max_eval_before": self.max_eval_before,
                "exclude_already_winning": self.exclude_already_winning
            }
            
            is_brilliant = MoveAnalysisService.is_brilliant_move(
                eval_before, eval_after, move_info, best_move_san, cpl,
                classification_thresholds, material_sacrifice
            )
            
            # Restore original method
            self._calculate_material_sacrifice_for_brilliance = original_method
            
            # If move is now brilliant, update assessment
            if is_brilliant:
                move_number = move_info.get("move_number", 0)
                is_white_move = move_info.get("is_white_move", True)
                row_index = move_number - 1
                
                # Validate row_index
                if 0 <= row_index < self.moves_list_model.rowCount():
                    move_data = self.moves_list_model.get_move(row_index)
                    if move_data:
                        # Check current assessment
                        current_assessment = move_data.assess_white if is_white_move else move_data.assess_black
                        if current_assessment != "Brilliant":
                            # Update assessment
                            if is_white_move:
                                move_data.assess_white = "Brilliant"
                            else:
                                move_data.assess_black = "Brilliant"
                            
                            brilliant_count += 1
                            
                            # Emit data changed signal
                            parent = QModelIndex()
                            top_left = self.moves_list_model.index(row_index, 0, parent)
                            column_count = self.moves_list_model.columnCount(parent)
                            if column_count > 0:
                                bottom_right = self.moves_list_model.index(row_index, column_count - 1, parent)
                            else:
                                bottom_right = top_left
                            
                            if top_left.isValid() and bottom_right.isValid():
                                self.moves_list_model.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole])
            
            # Update progress
            if (i + 1) % 10 == 0 or i == moves_count - 1:
                progress_service.set_status(f"Refining brilliancy: {i + 1}/{moves_count} moves checked")
        
        if brilliant_count > 0:
            progress_service.set_status(f"Post-game refinement: {brilliant_count} additional brilliant move(s) detected")
        else:
            progress_service.set_status("Post-game refinement: No additional brilliant moves detected")
    
    def _print_brilliant_debug_settings(self) -> None:
        """Print current brilliancy criteria settings when debug is enabled."""
        print("\n" + "=" * 80, file=sys.stderr)
        print("BRILLIANT MOVE DEBUG ENABLED", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print("Current Brilliancy Criteria Settings:", file=sys.stderr)
        print(f"  Min Eval Swing:        {self.min_eval_swing} centipawns", file=sys.stderr)
        print(f"  Min Material Sacrifice: {self.min_material_sacrifice} centipawns", file=sys.stderr)
        print(f"  Max Eval Before:       {self.max_eval_before} centipawns", file=sys.stderr)
        print(f"  Exclude Already Winning: {self.exclude_already_winning}", file=sys.stderr)
        print(f"  Material Sacrifice Lookahead: {self.material_sacrifice_lookahead_plies} plies", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print("Debug output will be printed for each move evaluated for brilliancy.\n", file=sys.stderr)
    
    def _debug_brilliant_output(self, move_info: Dict[str, Any], eval_before: float, 
                               eval_after: float, eval_swing: float, material_loss: int, 
                               cpl: float, best_move_san: str, is_white_move: bool, 
                               result: str) -> None:
        """Output debug information for brilliancy calculation.
        
        Args:
            move_info: Move information dictionary.
            eval_before: Evaluation before move.
            eval_after: Evaluation after move.
            eval_swing: Evaluation swing.
            material_loss: Material loss in centipawns.
            cpl: Centipawn loss.
            best_move_san: Best move suggestion.
            is_white_move: True if white move, False if black.
            result: Result string (PASS or FAIL with reason).
        """
        move_number = move_info.get("move_number", "?")
        move_san = move_info.get("move_san", "?")
        side = "White" if is_white_move else "Black"
        
        # Calculate net improvement
        if is_white_move:
            net_improvement = eval_swing - material_loss
        else:
            net_improvement = -eval_swing - material_loss
        
        # Format evaluation values
        eval_before_str = f"{eval_before:.1f}"
        eval_after_str = f"{eval_after:.1f}"
        eval_swing_str = f"{eval_swing:+.1f}"
        
        # Check results with clear pass/fail indicators
        eval_check_passed = (eval_swing >= self.min_eval_swing) if is_white_move else (eval_swing <= -self.min_eval_swing)
        material_check_passed = material_loss >= self.min_material_sacrifice
        already_winning_check_passed = True
        if self.exclude_already_winning:
            if is_white_move:
                already_winning_check_passed = eval_before <= self.max_eval_before
            else:
                already_winning_check_passed = eval_before >= -self.max_eval_before
        
        # Format check results
        eval_check = "✓" if eval_check_passed else "✗"
        material_check = "✓" if material_check_passed else "✗"
        already_winning_check = "✓" if already_winning_check_passed else "✗" if self.exclude_already_winning else "N/A"
        
        # Print formatted output
        print(f"\n{'─' * 80}", file=sys.stderr)
        print(f"Move {move_number} ({side}): {move_san}", file=sys.stderr)
        print(f"{'─' * 80}", file=sys.stderr)
        print(f"Evaluation:  {eval_before_str:>8} → {eval_after_str:>8}  (Swing: {eval_swing_str:>8})", file=sys.stderr)
        print(f"Material:    Sacrifice: {material_loss:>4} cp  |  CPL: {cpl:>6.1f} cp", file=sys.stderr)
        print(f"Best Move:   {best_move_san}", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"Checks:", file=sys.stderr)
        if is_white_move:
            print(f"  {eval_check}  Eval Swing:     {eval_swing:>6.1f} >= {self.min_eval_swing:>4} cp", file=sys.stderr)
        else:
            print(f"  {eval_check}  Eval Swing:     {eval_swing:>6.1f} <= {-self.min_eval_swing:>4} cp", file=sys.stderr)
        print(f"  {material_check}  Material Sac:   {material_loss:>6} >= {self.min_material_sacrifice:>4} cp", file=sys.stderr)
        if self.exclude_already_winning:
            if is_white_move:
                print(f"  {already_winning_check}  Not Winning:   {eval_before:>6.1f} <= {self.max_eval_before:>4} cp", file=sys.stderr)
            else:
                print(f"  {already_winning_check}  Not Winning:   {eval_before:>6.1f} >= {-self.max_eval_before:>4} cp", file=sys.stderr)
        else:
            print(f"  {already_winning_check}  Not Winning:   (disabled)", file=sys.stderr)
        print(f"", file=sys.stderr)
        print(f"Result: {result}", file=sys.stderr)
        print(f"{'─' * 80}", file=sys.stderr, flush=True)
    
    
    def _find_database_model_for_game(self, game) -> Optional[DatabaseModel]:
        """Find the database model that contains the given game.
        
        Args:
            game: GameData instance to find.
            
        Returns:
            DatabaseModel that contains the game, or None if not found.
        """
        if not self.database_controller or not game:
            return None
        
        # First try the active database
        active_database = self.database_controller.get_active_database()
        if active_database and active_database.find_game(game) is not None:
            return active_database
        
        # If not found, search through all databases in the panel model
        panel_model = self.database_controller.get_panel_model()
        if panel_model:
            all_databases = panel_model.get_all_databases()
            for identifier, info in all_databases.items():
                if info.model.find_game(game) is not None:
                    return info.model
        
        return None
    
    def _cleanup(self) -> None:
        """Cleanup resources."""
        if self._engine_service:
            self._engine_service.cleanup()
            self._engine_service = None
        
        if self._progress_timer:
            self._progress_timer.stop()
            self._progress_timer = None

