"""Bulk analysis dialog for analyzing multiple games."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QCheckBox,
    QGroupBox,
    QProgressBar,
    QSizePolicy,
    QApplication,
    QSpinBox,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, QMutex, QWaitCondition, QMutexLocker
from PyQt6.QtGui import QPalette, QColor, QShowEvent, QResizeEvent
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
import threading
import time

from app.models.database_model import DatabaseModel, GameData
from app.models.engine_model import EngineModel
from app.services.bulk_analysis_service import BulkAnalysisService
from app.services.engine_parameters_service import EngineParametersService


class ContinuousGameAnalysisWorker(QThread):
    """Worker thread that continuously picks up and analyzes games from a queue."""
    
    def __init__(self, worker_id: int, total_games: int,
                 bulk_analysis_service: BulkAnalysisService, re_analyze: bool,
                 get_next_game_func, game_finished_callback, progress_callback,
                 queue_mutex: QMutex, queue_condition: QWaitCondition) -> None:
        """Initialize continuous game analysis worker.
        
        Args:
            worker_id: Unique ID for this worker.
            total_games: Total number of games in the full list.
            bulk_analysis_service: BulkAnalysisService instance for this worker.
            re_analyze: Whether to re-analyze already analyzed games.
            get_next_game_func: Function to get next game from queue (returns (game, original_idx) or None).
            game_finished_callback: Callback(game, success) when a game finishes.
            progress_callback: Callback(game_idx, game_move_index, total_moves, is_white_move, status_message, engine_info).
            queue_mutex: Mutex for queue access.
            queue_condition: Condition variable for queue notifications.
        """
        super().__init__()
        self.worker_id = worker_id
        self.total_games = total_games
        self.bulk_analysis_service = bulk_analysis_service
        self.re_analyze = re_analyze
        self._get_next_game = get_next_game_func
        self._game_finished_callback = game_finished_callback
        self._progress_callback = progress_callback
        self._queue_mutex = queue_mutex
        self._queue_condition = queue_condition
        self._cancelled = False
    
    def cancel(self) -> None:
        """Cancel the worker."""
        self._cancelled = True
        if self.bulk_analysis_service:
            self.bulk_analysis_service.cancel()
        # Wake up waiting threads
        with QMutexLocker(self._queue_mutex):
            self._queue_condition.wakeAll()
    
    def run(self) -> None:
        """Continuously pick up and analyze games until queue is empty."""
        while not self._cancelled:
            # Get next game from queue
            game_data = self._get_next_game()
            if game_data is None:
                # No more games, exit
                break
            
            game, original_idx = game_data
            
            # Check if game is already analyzed
            if not self.re_analyze and game.analyzed:
                # Skip this game
                self._game_finished_callback(game, True)
                continue
            
            # Analyze the game
            def progress_callback(game_move_index, total_moves, current_move_number, is_white_move, status_message, engine_info):
                if self._cancelled:
                    return
                self._progress_callback(
                    original_idx,
                    game_move_index,
                    total_moves,
                    is_white_move,
                    status_message,
                    engine_info or {}
                )
            
            try:
                success = self.bulk_analysis_service.analyze_game(game, progress_callback)
                self._game_finished_callback(game, success)
            except Exception as e:
                self._game_finished_callback(game, False)


class GameAnalysisWorker(QThread):
    """Worker thread for analyzing a single game."""
    
    game_finished = pyqtSignal(GameData, bool)  # game, success
    progress_updated = pyqtSignal(int, int, int, bool, str, dict)  # original_game_idx, game_move_index, total_moves, is_white_move, status_message, engine_info
    
    def __init__(self, game: GameData, original_game_idx: int, total_games: int,
                 bulk_analysis_service: BulkAnalysisService, re_analyze: bool) -> None:
        """Initialize game analysis worker.
        
        Args:
            game: GameData instance to analyze.
            original_game_idx: Original index of this game in the full list (0-based, including skipped games).
            total_games: Total number of games in the full list (including skipped).
            bulk_analysis_service: BulkAnalysisService instance for this worker.
            re_analyze: Whether to re-analyze already analyzed games.
        """
        super().__init__()
        self.game = game
        self.original_game_idx = original_game_idx
        self.total_games = total_games
        self.bulk_analysis_service = bulk_analysis_service
        self.re_analyze = re_analyze
        self._cancelled = False
    
    def cancel(self) -> None:
        """Cancel the analysis."""
        self._cancelled = True
        if self.bulk_analysis_service:
            self.bulk_analysis_service.cancel()
    
    def run(self) -> None:
        """Run game analysis."""
        if self._cancelled:
            self.game_finished.emit(self.game, False)
            return
        
        # Check if game is already analyzed
        if not self.re_analyze and self.game.analyzed:
            # Skip this game - emit with special flag
            self.game_finished.emit(self.game, True)  # Success but skipped
            return
        
        def progress_callback(game_move_index, total_moves, current_move_number, is_white_move, status_message, engine_info):
            if self._cancelled:
                return
            self.progress_updated.emit(
                self.original_game_idx,
                game_move_index,
                total_moves,
                is_white_move,
                status_message,
                engine_info or {}
            )
        
        try:
            success = self.bulk_analysis_service.analyze_game(self.game, progress_callback)
            self.game_finished.emit(self.game, success)
        except Exception as e:
            self.game_finished.emit(self.game, False)


class BulkAnalysisThread(QThread):
    """Thread for running bulk analysis in background with parallel execution."""
    
    progress_updated = pyqtSignal(float, str, str)  # progress_percent (float), status_message, progress_percent_str
    status_update_requested = pyqtSignal()  # Request status update from main thread
    game_analyzed = pyqtSignal(GameData)  # Emitted when a game is analyzed
    finished = pyqtSignal(bool, str)  # success, error_message
    
    def __init__(self, games: List[GameData], config: Dict[str, Any],
                 engine_model: EngineModel, analysis_controller,
                 opening_service, book_move_service, classification_model,
                 re_analyze: bool = False, movetime_override: Optional[int] = None) -> None:
        """Initialize bulk analysis thread.
        
        Args:
            games: List of games to analyze.
            config: Configuration dictionary.
            engine_model: EngineModel instance.
            analysis_controller: GameAnalysisController instance.
            opening_service: OpeningService instance.
            book_move_service: BookMoveService instance.
            classification_model: Optional MoveClassificationModel instance.
            re_analyze: Whether to re-analyze already analyzed games.
            movetime_override: Optional override for movetime in milliseconds.
        """
        super().__init__()
        self.games = games
        self.config = config
        self.engine_model = engine_model
        self.analysis_controller = analysis_controller
        self.opening_service = opening_service
        self.book_move_service = book_move_service
        self.classification_model = classification_model
        self.re_analyze = re_analyze
        self.movetime_override = movetime_override
        self._cancelled = False
        self._workers: List[GameAnalysisWorker] = []
        self._progress_lock = threading.Lock()
        self._game_progress: Dict[int, Dict[str, Any]] = {}  # game_idx -> progress info
        self._analyzed_count = 0
        self._error_count = 0
        self._skipped_count = 0
        self._start_time: Optional[float] = None
        self._active_workers: Dict[int, GameAnalysisWorker] = {}  # game_idx -> worker (for tracking active games)
        self._completed_game_indices: set = set()  # Track completed game indices
        self._last_status_update_time = 0.0
        self._status_update_interval = 0.1  # Update status at most every 100ms
        self._game_queue: List[Tuple[GameData, int]] = []  # Queue of (game, original_idx) tuples
        self._queue_mutex = QMutex()
        self._queue_condition = QWaitCondition()
        self._next_game_idx = 0  # Index of next game to assign
        self._games_to_analyze: List[GameData] = []
        self._original_indices: List[int] = []
        # Cumulative depth/seldepth tracking across all analyzed moves
        self._cumulative_depth_sum = 0
        self._cumulative_depth_count = 0
        self._cumulative_seldepth_sum = 0
        self._cumulative_seldepth_count = 0
    
    def _get_next_game(self) -> Optional[Tuple[GameData, int]]:
        """Get next game from queue (thread-safe).
        
        Returns:
            Tuple of (game, original_idx) or None if no more games.
        """
        with QMutexLocker(self._queue_mutex):
            if self._next_game_idx >= len(self._games_to_analyze):
                return None
            
            game = self._games_to_analyze[self._next_game_idx]
            original_idx = self._original_indices[self._next_game_idx]
            self._next_game_idx += 1
            return (game, original_idx)
    
    def cancel(self) -> None:
        """Cancel the analysis."""
        self._cancelled = True
        for worker in self._workers:
            worker.cancel()
    
    def _get_normal_thread_setting(self) -> int:
        """Get the normal thread setting for game analysis.
        
        Returns:
            Number of threads normally used for game analysis.
        """
        # Get engine assignment
        engine_assignment = self.engine_model.get_assignment(EngineModel.TASK_GAME_ANALYSIS)
        if engine_assignment is None:
            return 6  # Default fallback
        
        engine = self.engine_model.get_engine(engine_assignment)
        if engine is None or not engine.is_valid:
            return 6  # Default fallback
        
        # Get task-specific parameters
        engine_path = Path(engine.path) if not isinstance(engine.path, Path) else engine.path
        
        task_params = EngineParametersService.get_task_parameters_for_engine(
            engine_path,
            "game_analysis",
            self.config
        )
        
        return task_params.get("threads", 6)
    
    def _on_worker_progress(self, game_idx: int, game_move_index: int, total_moves: int,
                           is_white_move: bool, status_message: str, engine_info: dict) -> None:
        """Handle progress update from a worker thread."""
        with self._progress_lock:
            self._game_progress[game_idx] = {
                'game_move_index': game_move_index,
                'total_moves': total_moves,
                'is_white_move': is_white_move,
                'status_message': status_message,
                'engine_info': engine_info
            }
            
            # Accumulate depth/seldepth from all moves (cumulative across all games)
            # Note: We're already inside the lock, so no need to acquire it again
            if engine_info:
                depth = engine_info.get('depth', 0)
                if depth > 0:
                    self._cumulative_depth_sum += depth
                    self._cumulative_depth_count += 1
                seldepth = engine_info.get('seldepth', 0)
                if seldepth > 0:
                    self._cumulative_seldepth_sum += seldepth
                    self._cumulative_seldepth_count += 1
        
        # Request status update from main thread (throttled)
        current_time = time.time()
        if current_time - self._last_status_update_time >= self._status_update_interval:
            self._last_status_update_time = current_time
            self.status_update_requested.emit()
    
    def _update_status_messages(self) -> None:
        """Update dialog and status bar messages with parallel progress information.
        
        This method should be called from the main thread to avoid UI blocking.
        """
        # Get data from thread-safe storage (quick lock)
        with self._progress_lock:
            game_progress_copy = self._game_progress.copy()
            analyzed_count = self._analyzed_count
            skipped_count = self._skipped_count
            start_time = self._start_time
        
        total_games = len(self.games)
        if total_games == 0:
            return
        
        # Count games being analyzed (not skipped)
        games_being_analyzed = total_games - skipped_count
        if games_being_analyzed == 0:
            dialog_status = f"All games already analyzed ({skipped_count} skipped)"
            self.progress_updated.emit(100.0, dialog_status)
            return
        
        # Find currently active games (games with progress but not completed)
        # A game is active if it has progress data, is not yet finished, and is not in completed set
        with self._progress_lock:
            completed_indices = self._completed_game_indices.copy()
        
        active_progress_sum = 0.0
        active_count = 0
        
        for idx in range(total_games):
            if idx in completed_indices:
                continue  # Skip completed games
            if idx in game_progress_copy:
                prog = game_progress_copy[idx]
                total_moves = prog.get('total_moves', 0)
                if total_moves > 0:
                    game_move_index = prog.get('game_move_index', 0)
                    # Game is active if it has moves and hasn't completed all moves
                    if game_move_index < total_moves:
                        game_progress = game_move_index / total_moves
                        active_progress_sum += game_progress
                        active_count += 1
        
        # Calculate average progress of active games (with 4 decimal places)
        if active_count > 0:
            avg_active_progress = (active_progress_sum / active_count) * 100.0
            avg_active_progress_str = f"{avg_active_progress:.4f}"
        else:
            avg_active_progress = 0.0
            avg_active_progress_str = "0.0000"
        
        # Calculate average depth/seldepth from cumulative data (all analyzed moves across all games)
        with self._progress_lock:
            cumulative_depth_sum = self._cumulative_depth_sum
            cumulative_depth_count = self._cumulative_depth_count
            cumulative_seldepth_sum = self._cumulative_seldepth_sum
            cumulative_seldepth_count = self._cumulative_seldepth_count
        
        # Calculate average depth
        if cumulative_depth_count > 0:
            avg_depth = cumulative_depth_sum / cumulative_depth_count
            avg_depth_str = f"Avg Depth: {int(avg_depth)}"
        else:
            avg_depth_str = ""
        
        # Calculate average seldepth
        if cumulative_seldepth_count > 0:
            avg_seldepth = cumulative_seldepth_sum / cumulative_seldepth_count
            avg_seldepth_str = f"Avg SelDepth: {int(avg_seldepth)}"
        else:
            avg_seldepth_str = ""
        
        # Count completed games
        completed_count = analyzed_count + skipped_count
        
        # Format dialog status message (without percentage - that goes in progress bar label)
        if active_count > 0:
            dialog_status = f"Analyzing {active_count} game{'s' if active_count != 1 else ''} from total {total_games} games, {completed_count} game{'s' if completed_count != 1 else ''} completed."
        else:
            dialog_status = f"Preparing analysis of {games_being_analyzed} game{'s' if games_being_analyzed != 1 else ''} from total {total_games} games, {completed_count} game{'s' if completed_count != 1 else ''} completed."
        
        # Calculate overall progress for progress bar
        if games_being_analyzed > 0:
            # Sum progress from all games being analyzed (excluding completed ones)
            total_progress = 0
            games_with_progress = 0
            for idx in range(total_games):
                if idx in completed_indices:
                    # Completed games count as 100% progress
                    total_progress += 1.0
                    games_with_progress += 1
                elif idx in game_progress_copy:
                    prog = game_progress_copy[idx]
                    total_moves = prog.get('total_moves', 0)
                    if total_moves > 0:
                        game_progress = prog.get('game_move_index', 0) / total_moves
                        total_progress += game_progress
                        games_with_progress += 1
            
            if games_with_progress > 0:
                overall_progress = (total_progress / games_being_analyzed) * 100.0
            else:
                overall_progress = 0.0
        else:
            overall_progress = 100.0
        
        # Use floating point progress with 4 decimal places
        progress_value = min(overall_progress, 99.9999)
        progress_percent_str = f"{progress_value:.4f}%"
        self.progress_updated.emit(progress_value, dialog_status, progress_percent_str)
        
        # Update status bar with estimated time remaining
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        if active_count > 0 and start_time is not None:
            # Calculate estimated time remaining
            elapsed_time = time.time() - start_time
            if overall_progress > 0 and elapsed_time > 0:
                # Estimate: elapsed_time / progress = total_time, remaining = total_time - elapsed_time
                estimated_total_time = elapsed_time / (overall_progress / 100.0)
                estimated_remaining = estimated_total_time - elapsed_time
                
                # Format time remaining
                if estimated_remaining < 60:
                    time_str = f"{int(estimated_remaining)}s"
                elif estimated_remaining < 3600:
                    minutes = int(estimated_remaining // 60)
                    seconds = int(estimated_remaining % 60)
                    time_str = f"{minutes}m {seconds}s"
                else:
                    hours = int(estimated_remaining // 3600)
                    minutes = int((estimated_remaining % 3600) // 60)
                    time_str = f"{hours}h {minutes}m"
                
                status_parts = [
                    f"Bulk Analysis: Analyzing {active_count} game{'s' if active_count != 1 else ''} ({avg_active_progress_str}%) from total {total_games} games, {completed_count} completed",
                    avg_depth_str,
                    avg_seldepth_str,
                    f"Estimated time remaining: {time_str}"
                ]
                status_bar_message = " | ".join([p for p in status_parts if p])
            else:
                status_parts = [
                    f"Bulk Analysis: Analyzing {active_count} game{'s' if active_count != 1 else ''} ({avg_active_progress_str}%) from total {total_games} games, {completed_count} completed",
                    avg_depth_str,
                    avg_seldepth_str
                ]
                status_bar_message = " | ".join([p for p in status_parts if p])
        else:
            status_bar_message = f"Bulk Analysis: Preparing analysis of {games_being_analyzed} game{'s' if games_being_analyzed != 1 else ''} from total {total_games} games, {completed_count} completed."
        
        progress_service.set_status(status_bar_message)
        
        # Update progress bar percentage (convert float to int, 0-100)
        progress_service.set_progress(int(overall_progress))
    
    def run(self) -> None:
        """Run bulk analysis with parallel execution."""
        try:
            # Emit initial progress to show thread has started
            self.progress_updated.emit(0.0, "Initializing bulk analysis...", "0.0000%")
            
            total_games = len(self.games)
            if total_games == 0:
                self.finished.emit(True, "No games to analyze")
                return
            
            # Filter games that need analysis, keeping track of original indices
            games_to_analyze = []
            original_indices = []  # Maps games_to_analyze index to original game index
            for idx, game in enumerate(self.games):
                if not self.re_analyze and game.analyzed:
                    self._skipped_count += 1
                else:
                    games_to_analyze.append(game)
                    original_indices.append(idx)
            
            if not games_to_analyze:
                self.finished.emit(True, f"All games already analyzed ({self._skipped_count} skipped)")
                return
            
            # Emit progress update
            self.progress_updated.emit(0.0, f"Preparing to analyze {len(games_to_analyze)} games...", "0.0000%")
            
            # Get normal thread setting and calculate parallel resources
            normal_threads = self._get_normal_thread_setting()
            parallel_games, threads_per_engine = BulkAnalysisService.calculate_parallel_resources(
                normal_threads, max_parallel_games=4
            )
            
            # Limit parallel games to actual number of games
            parallel_games = min(parallel_games, len(games_to_analyze))
            
            # Initialize start time for time estimation
            self._start_time = time.time()
            
            # Store games and indices for queue access
            self._games_to_analyze = games_to_analyze
            self._original_indices = original_indices
            self._next_game_idx = 0
            
            # Emit progress update
            self.progress_updated.emit(0.0, f"Creating {parallel_games} analysis service(s)...", "0.0000%")
            
            # Create BulkAnalysisService instances (one per parallel game)
            analysis_services: List[BulkAnalysisService] = []
            for i in range(parallel_games):
                service = BulkAnalysisService(
                    self.config,
                    self.engine_model,
                    self.opening_service,
                    self.book_move_service,
                    self.classification_model,
                    threads_override=threads_per_engine,
                    movetime_override=self.movetime_override
                )
                analysis_services.append(service)
            
            # Emit progress update
            self.progress_updated.emit(0.0, f"Starting {parallel_games} worker thread(s)...", "0.0000%")
            
            # Create worker threads that will continuously pick up games
            self._workers = []
            for i in range(parallel_games):
                worker = ContinuousGameAnalysisWorker(
                    i,
                    total_games,
                    analysis_services[i],
                    self.re_analyze,
                    self._get_next_game,
                    self._on_game_finished,
                    self._on_worker_progress,
                    self._queue_mutex,
                    self._queue_condition
                )
                worker.start()
                self._workers.append(worker)
            
            # Emit progress update - analysis is starting
            self.progress_updated.emit(0.0, f"Analysis started: {len(games_to_analyze)} games, {parallel_games} parallel worker(s)...", "0.0000%")
            
            # Wait for all workers to finish (they'll stop when queue is empty)
            for worker in self._workers:
                worker.wait()
            
            # Final status
            if self._cancelled:
                self.finished.emit(False, "Analysis cancelled by user")
            else:
                status = f"Completed: {self._analyzed_count} analyzed, {self._skipped_count} skipped, {self._error_count} errors"
                self.finished.emit(True, status)
        
        except Exception as e:
            self.finished.emit(False, f"Error during analysis: {str(e)}")
        finally:
            # Cleanup
            for worker in self._workers:
                if worker.isRunning():
                    worker.cancel()
                    worker.wait()
    
    def _on_game_finished(self, game: GameData, success: bool) -> None:
        """Handle game analysis completion."""
        with self._progress_lock:
            # Find and remove from active workers, and mark as completed
            for idx, worker in list(self._active_workers.items()):
                if worker.game == game:
                    del self._active_workers[idx]
                    # Mark this game index as completed
                    self._completed_game_indices.add(idx)
                    break
            
            if success:
                self._analyzed_count += 1
                self.game_analyzed.emit(game)
            else:
                self._error_count += 1
        
        # Request status update from main thread
        self.status_update_requested.emit()


class BulkAnalysisDialog(QDialog):
    """Dialog for bulk game analysis."""
    
    def __init__(self, config: Dict[str, Any], database_model: Optional[DatabaseModel],
                 analysis_controller, database_panel=None, parent=None) -> None:
        """Initialize the bulk analysis dialog.
        
        Args:
            config: Configuration dictionary.
            database_model: DatabaseModel instance for the active database.
            analysis_controller: GameAnalysisController instance.
            database_panel: Optional DatabasePanel instance for getting selected games.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.database_model = database_model
        self.analysis_controller = analysis_controller
        self.database_panel = database_panel
        self.analysis_thread: Optional[BulkAnalysisThread] = None
        self.selected_games: List[GameData] = []
        self.bulk_analysis_service: Optional[BulkAnalysisService] = None
        
        # Store fixed size
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {})
        width = dialog_config.get('width', 550)
        height = dialog_config.get('height', 400)
        self._fixed_size = QSize(width, height)
        
        # Set fixed size
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        self._setup_ui()
        self._apply_styling()
        self.setWindowTitle("Bulk Analyze Database")
        self.setModal(True)
    
    def showEvent(self, event: QShowEvent) -> None:
        """Handle show event to enforce fixed size."""
        super().showEvent(event)
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
    
    def sizeHint(self) -> QSize:
        """Return the fixed size as the size hint."""
        return self._fixed_size
    
    def minimumSizeHint(self) -> QSize:
        """Return the fixed size as the minimum size hint."""
        return self._fixed_size
    
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize event to prevent resizing."""
        super().resizeEvent(event)
        if event.size() != self._fixed_size:
            self.blockSignals(True)
            current_pos = self.pos()
            self.setGeometry(current_pos.x(), current_pos.y(), self._fixed_size.width(), self._fixed_size.height())
            self.setFixedSize(self._fixed_size)
            self.setMinimumSize(self._fixed_size)
            self.setMaximumSize(self._fixed_size)
            self.blockSignals(False)
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {})
        layout_config = dialog_config.get('layout', {})
        layout_spacing = layout_config.get('spacing', 15)
        layout_margins = layout_config.get('margins', [25, 25, 25, 25])
        spacing_config = dialog_config.get('spacing', {})
        section_spacing = spacing_config.get('section', 15)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(layout_spacing)
        layout.setContentsMargins(layout_margins[0], layout_margins[1], layout_margins[2], layout_margins[3])
        
        # Game selection group
        selection_group = QGroupBox("Game Selection")
        selection_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        selection_layout = QVBoxLayout(selection_group)
        groups_config = dialog_config.get('groups', {})
        group_margins = groups_config.get('content_margins', [10, 20, 10, 15])
        selection_layout.setContentsMargins(group_margins[0], group_margins[1], group_margins[2], group_margins[3])
        selection_layout.setSpacing(section_spacing)
        
        # Radio buttons for selection
        self.selection_button_group = QButtonGroup()
        self.selected_games_radio = QRadioButton("Selected games only")
        self.all_games_radio = QRadioButton("All games")
        
        # Ensure radio buttons have proper size policy to prevent truncation
        self.selected_games_radio.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.all_games_radio.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        
        self.selection_button_group.addButton(self.selected_games_radio, 0)
        self.selection_button_group.addButton(self.all_games_radio, 1)
        
        # Default to selected games if any are selected, otherwise all games
        if self.database_model and self.database_panel:
            active_info = self.database_panel.get_active_database_info()
            if active_info and active_info.get('model') == self.database_model:
                selected_indices = self.database_panel.get_selected_game_indices()
                if selected_indices:
                    self.selected_games_radio.setChecked(True)
                    self._update_selected_games()
                else:
                    self.all_games_radio.setChecked(True)
        else:
            self.all_games_radio.setChecked(True)
        
        self.selected_games_radio.toggled.connect(self._on_selection_changed)
        self.all_games_radio.toggled.connect(self._on_selection_changed)
        
        # Radio buttons in a vertical layout
        selection_layout.addWidget(self.selected_games_radio)
        selection_layout.addWidget(self.all_games_radio)
        
        layout.addWidget(selection_group)
        
        # Options group
        options_group = QGroupBox("Options")
        options_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(group_margins[0], group_margins[1], group_margins[2], group_margins[3])
        options_layout.setSpacing(section_spacing)
        
        # Options row: checkbox on left, movetime on right
        options_row_layout = QHBoxLayout()
        options_row_layout.setSpacing(20)  # Space between checkbox and movetime
        
        # Re-analyze checkbox (left side)
        self.re_analyze_checkbox = QCheckBox("Re-analyze already analyzed games")
        self.re_analyze_checkbox.setChecked(False)
        self.re_analyze_checkbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        options_row_layout.addWidget(self.re_analyze_checkbox)
        
        # Add stretch to push movetime to the right
        options_row_layout.addStretch()
        
        # Movetime input (right side)
        movetime_row_layout = QHBoxLayout()
        movetime_row_layout.setSpacing(8)  # Space between label and spinbox
        
        # Movetime input
        from app.utils.font_utils import scale_font_size
        movetime_label = QLabel("Time per move:")
        movetime_label.setStyleSheet(
            f"font-size: {scale_font_size(dialog_config.get('labels', {}).get('font_size', 11))}pt; "
            f"color: rgb({dialog_config.get('labels', {}).get('text_color', [200, 200, 200])[0]}, "
            f"{dialog_config.get('labels', {}).get('text_color', [200, 200, 200])[1]}, "
            f"{dialog_config.get('labels', {}).get('text_color', [200, 200, 200])[2]});"
        )
        movetime_row_layout.addWidget(movetime_label)
        
        # Get default movetime from engine parameters
        default_movetime = 1000  # Fallback default
        if self.analysis_controller and hasattr(self.analysis_controller, 'engine_model'):
            engine_model = self.analysis_controller.engine_model
            engine_assignment = engine_model.get_assignment(EngineModel.TASK_GAME_ANALYSIS)
            if engine_assignment:
                engine = engine_model.get_engine(engine_assignment)
                if engine and engine.is_valid:
                    engine_path = Path(engine.path) if not isinstance(engine.path, Path) else engine.path
                    task_params = EngineParametersService.get_task_parameters_for_engine(
                        engine_path,
                        "game_analysis",
                        self.config
                    )
                    default_movetime = task_params.get("movetime", 1000)
        
        self.movetime_spinbox = QSpinBox()
        self.movetime_spinbox.setMinimum(100)
        self.movetime_spinbox.setMaximum(60000)
        self.movetime_spinbox.setSingleStep(100)
        self.movetime_spinbox.setValue(default_movetime)
        self.movetime_spinbox.setSuffix(" ms")
        movetime_row_layout.addWidget(self.movetime_spinbox)
        
        options_row_layout.addLayout(movetime_row_layout)
        options_layout.addLayout(options_row_layout)
        
        layout.addWidget(options_group)
        
        # Progress group (always visible)
        self.progress_group = QGroupBox("Progress")
        self.progress_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        progress_layout = QVBoxLayout(self.progress_group)
        progress_layout.setContentsMargins(group_margins[0], group_margins[1], group_margins[2], group_margins[3])
        progress_layout.setSpacing(section_spacing)
        
        # Get progress config first
        progress_config = dialog_config.get('progress', {})
        status_font_size = progress_config.get('status_font_size', 10)
        status_text_color = progress_config.get('status_text_color', [150, 150, 150])
        
        # Progress bar with percentage label
        progress_bar_layout = QHBoxLayout()
        progress_bar_layout.setSpacing(8)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)  # Hide text inside progress bar since we have a label
        progress_bar_layout.addWidget(self.progress_bar)
        
        # Percentage label
        self.progress_percent_label = QLabel("0.0000%")
        self.progress_percent_label.setStyleSheet(
            f"font-size: {status_font_size}pt; "
            f"color: rgb({status_text_color[0]}, {status_text_color[1]}, {status_text_color[2]});"
        )
        self.progress_percent_label.setMinimumWidth(80)  # Reserve space for "100.0000%"
        progress_bar_layout.addWidget(self.progress_percent_label)
        
        progress_layout.addLayout(progress_bar_layout)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(
            f"font-size: {status_font_size}pt; "
            f"color: rgb({status_text_color[0]}, {status_text_color[1]}, {status_text_color[2]});"
        )
        progress_layout.addWidget(self.status_label)
        
        layout.addWidget(self.progress_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        buttons_config = dialog_config.get('buttons', {})
        button_spacing = buttons_config.get('spacing', 10)
        button_layout.setSpacing(button_spacing)
        button_layout.addStretch()
        
        self.start_button = QPushButton("Start Analysis")
        self.start_button.clicked.connect(self._start_analysis)
        button_layout.addWidget(self.start_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
    
    def _on_selection_changed(self) -> None:
        """Handle selection radio button change."""
        if self.selected_games_radio.isChecked():
            self._update_selected_games()
            # Disable start button if no games selected
            if not self.selected_games:
                self.start_button.setEnabled(False)
            else:
                self.start_button.setEnabled(True)
        else:
            self.start_button.setEnabled(True)
    
    def _update_selected_games(self) -> None:
        """Update the list of selected games."""
        self.selected_games = []
        if self.database_model and self.database_panel:
            # Get selected rows from the database panel (only works if this is the active database)
            # Check if the active database matches our database model
            active_info = self.database_panel.get_active_database_info()
            if active_info and active_info.get('model') == self.database_model:
                selected_indices = self.database_panel.get_selected_game_indices()
                for idx in selected_indices:
                    game = self.database_model.get_game(idx)
                    if game:
                        self.selected_games.append(game)
    
    def _start_analysis(self) -> None:
        """Start the bulk analysis."""
        # Get games to analyze
        if self.selected_games_radio.isChecked():
            if not self.selected_games:
                # Show error message
                from app.views.message_dialog import MessageDialog
                dialog = MessageDialog(
                    self.config,
                    "No Games Selected",
                    "Please select games in the database view to analyze, or choose 'All games'.",
                    message_type="warning",
                    parent=self
                )
                dialog.exec()
                return
            games_to_analyze = self.selected_games
        else:
            # All games
            if not self.database_model:
                return
            games_to_analyze = self.database_model.get_all_games()
        
        if not games_to_analyze:
            from app.views.message_dialog import MessageDialog
            dialog = MessageDialog(
                self.config,
                "No Games",
                "No games found in the database.",
                message_type="information",
                parent=self
            )
            dialog.exec()
            return
        
        # Update progress group (always visible)
        self.progress_bar.setValue(0)
        self.progress_percent_label.setText("0.0000%")
        self.status_label.setText(f"Preparing to analyze {len(games_to_analyze)} games...")
        
        # Disable controls
        self.selected_games_radio.setEnabled(False)
        self.all_games_radio.setEnabled(False)
        self.re_analyze_checkbox.setEnabled(False)
        self.movetime_spinbox.setEnabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setText("Cancel")
        
        # Get required services from analysis controller
        engine_model = self.analysis_controller.engine_model
        opening_service = self.analysis_controller.opening_service
        book_move_service = self.analysis_controller.book_move_service
        classification_model = self.analysis_controller.classification_model
        
        # Ensure opening service is loaded before starting analysis (to avoid blocking during analysis)
        # This must happen in the main thread before creating worker threads
        if opening_service and not opening_service.is_loaded():
            # Update status to show we're loading opening database
            self.status_label.setText("Loading opening database...")
            QApplication.processEvents()  # Allow UI to update
            
            try:
                opening_service.load()
            except Exception as e:
                # If loading fails, continue anyway (opening info will just be missing)
                import sys
                print(f"Warning: Failed to load opening service: {e}", file=sys.stderr)
            
            # Clear status
            self.status_label.setText("Ready")
            QApplication.processEvents()  # Allow UI to update
        
        # Pre-load engine parameters to avoid blocking in worker thread
        self.status_label.setText("Loading engine parameters...")
        QApplication.processEvents()  # Allow UI to update
        try:
            # Pre-load by calling get_task_parameters_for_engine (it will load if needed)
            engine_assignment = engine_model.get_assignment(EngineModel.TASK_GAME_ANALYSIS)
            if engine_assignment:
                engine = engine_model.get_engine(engine_assignment)
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
        
        self.status_label.setText("Ready")
        QApplication.processEvents()  # Allow UI to update
        
        # Start analysis thread (it will create its own BulkAnalysisService instances for parallel execution)
        re_analyze = self.re_analyze_checkbox.isChecked()
        movetime_override = self.movetime_spinbox.value()  # Get value from spinbox
        self.analysis_thread = BulkAnalysisThread(
            games_to_analyze,
            self.config,
            engine_model,
            self.analysis_controller,
            opening_service,
            book_move_service,
            classification_model,
            re_analyze,
            movetime_override=movetime_override
        )
        self.analysis_thread.progress_updated.connect(self._on_progress_updated)
        self.analysis_thread.status_update_requested.connect(self._on_status_update_requested)
        self.analysis_thread.game_analyzed.connect(self._on_game_analyzed)
        self.analysis_thread.finished.connect(self._on_analysis_finished)
        
        # Show progress service in status bar
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        progress_service.show_progress()
        progress_service.set_progress(0)
        
        self.analysis_thread.start()
    
    def _on_progress_updated(self, progress_percent: float, status_message: str, progress_percent_str: str) -> None:
        """Handle progress update from analysis thread."""
        # QProgressBar uses int, but we display the float value in the label next to it
        self.progress_bar.setValue(int(progress_percent))
        self.progress_percent_label.setText(progress_percent_str)
        self.status_label.setText(status_message)
        QApplication.processEvents()
    
    def _on_status_update_requested(self) -> None:
        """Handle status update request from analysis thread (called from main thread)."""
        if self.analysis_thread:
            self.analysis_thread._update_status_messages()
    
    def _on_game_analyzed(self, game: GameData) -> None:
        """Handle game analyzed signal."""
        # Update database model if needed
        if self.database_model:
            # Update game in database model (this will refresh the view)
            self.database_model.update_game(game)
            QApplication.processEvents()
    
    def _on_analysis_finished(self, success: bool, message: str) -> None:
        """Handle analysis finished signal."""
        # Hide progress service
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        progress_service.hide_progress()
        
        if success:
            self.progress_bar.setValue(100)
            self.progress_percent_label.setText("100.0000%")
            self.status_label.setText(message)
            self.cancel_button.setText("Close")
            self.cancel_button.clicked.disconnect()
            self.cancel_button.clicked.connect(self.accept)
        else:
            self.status_label.setText(f"Error: {message}")
            # Re-enable controls for retry
            self.selected_games_radio.setEnabled(True)
            self.all_games_radio.setEnabled(True)
            self.re_analyze_checkbox.setEnabled(True)
            self.movetime_spinbox.setEnabled(True)
            self.start_button.setEnabled(True)
            self.cancel_button.setText("Cancel")
    
    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        if self.analysis_thread and self.analysis_thread.isRunning():
            self.analysis_thread.cancel()
            if self.bulk_analysis_service:
                self.bulk_analysis_service.cancel()
            self.status_label.setText("Cancelling...")
            self.cancel_button.setEnabled(False)
            
            # Update status bar
            progress_service.set_status("Bulk Analysis: Cancelling...")
            
            # Wait for thread to finish
            self.analysis_thread.wait()
            
            # Update status bar with cancellation message
            progress_service.set_status("Bulk Analysis: Cancelled by user")
        
        # Hide progress service
        progress_service.hide_progress()
        
        self.reject()
    
    def _apply_styling(self) -> None:
        """Apply styling to UI elements based on configuration."""
        ui_config = self.config.get('ui', {})
        dialog_config = ui_config.get('dialogs', {}).get('bulk_analysis_dialog', {})
        
        # Dialog background color
        bg_color = dialog_config.get('background_color', [40, 40, 45])
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(bg_color[0], bg_color[1], bg_color[2]))
        palette.setColor(QPalette.ColorRole.Window, QColor(bg_color[0], bg_color[1], bg_color[2]))
        self.setPalette(palette)
        
        # Labels styling
        labels_config = dialog_config.get('labels', {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
        label_font_family = resolve_font_family(labels_config.get('font_family', 'Helvetica Neue'))
        label_font_size = scale_font_size(labels_config.get('font_size', 11))
        label_text_color = labels_config.get('text_color', [200, 200, 200])
        
        label_style = (
            f"QLabel {{"
            f"font-family: {label_font_family}; "
            f"font-size: {label_font_size}pt; "
            f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
            f"margin: 0px;"
            f"padding: 0px;"
            f"}}"
        )
        
        for label in self.findChildren(QLabel):
            label.setStyleSheet(label_style)
        
        # Group box styling
        groups_config = dialog_config.get('groups', {})
        group_border_color = groups_config.get('border_color', [60, 60, 65])
        group_border_radius = groups_config.get('border_radius', 5)
        group_bg_color = groups_config.get('background_color', [45, 45, 50])
        group_title_color = groups_config.get('title_color', [240, 240, 240])
        group_title_font_family = groups_config.get('title_font_family', 'Helvetica Neue')
        group_title_font_size = groups_config.get('title_font_size', 11)
        group_margin_top = groups_config.get('margin_top', 10)
        group_padding_top = groups_config.get('padding_top', 5)
        group_title_left = groups_config.get('title_left', 10)
        group_title_padding = groups_config.get('title_padding', [0, 5])
        
        group_style = (
            f"QGroupBox {{"
            f"border: 1px solid rgb({group_border_color[0]}, {group_border_color[1]}, {group_border_color[2]});"
            f"border-radius: {group_border_radius}px;"
            f"margin-top: {group_margin_top}px;"
            f"padding-top: {group_padding_top}px;"
            f"background-color: rgb({group_bg_color[0]}, {group_bg_color[1]}, {group_bg_color[2]});"
            f"}}"
            f"QGroupBox::title {{"
            f"font-family: \"{group_title_font_family}\";"
            f"font-size: {group_title_font_size}pt;"
            f"color: rgb({group_title_color[0]}, {group_title_color[1]}, {group_title_color[2]});"
            f"subcontrol-origin: margin;"
            f"left: {group_title_left}px;"
            f"padding: {group_title_padding[0]} {group_title_padding[1]}px;"
            f"}}"
        )
        
        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(group_style)
        
        # Checkbox styling
        checkboxes_config = dialog_config.get('checkboxes', {})
        checkbox_spacing = checkboxes_config.get('spacing', 5)
        indicator_config = checkboxes_config.get('indicator', {})
        checkbox_indicator_width = indicator_config.get('width', 16)
        checkbox_indicator_height = indicator_config.get('height', 16)
        checkbox_indicator_border_radius = indicator_config.get('border_radius', 3)
        checked_config = checkboxes_config.get('checked', {})
        checkbox_checked_bg_color = checked_config.get('background_color', [70, 90, 130])
        checkbox_checked_border_color = checked_config.get('border_color', [100, 120, 160])
        checkbox_hover_border_offset = checkboxes_config.get('hover_border_offset', 20)
        
        # Get checkmark icon path
        project_root = Path(__file__).parent.parent.parent
        checkmark_path = project_root / "app" / "resources" / "icons" / "checkmark.svg"
        checkmark_url = str(checkmark_path).replace("\\", "/") if checkmark_path.exists() else ""
        
        # Use input border and background colors for checkbox indicator
        input_border_color = dialog_config.get('border_color', [60, 60, 65])
        input_bg_color = [bg_color[0] + 5, bg_color[1] + 5, bg_color[2] + 5]
        
        checkbox_style = (
            f"QCheckBox {{"
            f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
            f"font-size: {label_font_size}pt;"
            f"spacing: {checkbox_spacing}px;"
            f"}}"
            f"QCheckBox::indicator {{"
            f"width: {checkbox_indicator_width}px;"
            f"height: {checkbox_indicator_height}px;"
            f"border-radius: {checkbox_indicator_border_radius}px;"
            f"border: 1px solid rgb({input_border_color[0]}, {input_border_color[1]}, {input_border_color[2]});"
            f"background-color: rgb({input_bg_color[0]}, {input_bg_color[1]}, {input_bg_color[2]});"
            f"}}"
            f"QCheckBox::indicator:checked {{"
            f"background-color: rgb({checkbox_checked_bg_color[0]}, {checkbox_checked_bg_color[1]}, {checkbox_checked_bg_color[2]});"
            f"border-color: rgb({checkbox_checked_border_color[0]}, {checkbox_checked_border_color[1]}, {checkbox_checked_border_color[2]});"
            f"image: url({checkmark_url});"
            f"}}"
            f"QCheckBox::indicator:hover {{"
            f"border-color: rgb({input_border_color[0] + checkbox_hover_border_offset}, {input_border_color[1] + checkbox_hover_border_offset}, {input_border_color[2] + checkbox_hover_border_offset});"
            f"}}"
        )
        
        for checkbox in self.findChildren(QCheckBox):
            checkbox.setStyleSheet(checkbox_style)
        
        # Radio button styling (use same as labels)
        radio_style = (
            f"QRadioButton {{"
            f"font-family: {label_font_family}; "
            f"font-size: {label_font_size}pt; "
            f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
            f"spacing: {checkbox_spacing}px;"
            f"}}"
        )
        
        for radio in self.findChildren(QRadioButton):
            radio.setStyleSheet(radio_style)
        
        # SpinBox styling (use input widget colors, hide arrows)
        input_bg_color = dialog_config.get('background_color', [40, 40, 45])
        input_border = dialog_config.get('border_color', [60, 60, 65])
        input_text_color = dialog_config.get('text_color', [200, 200, 200])
        spinbox_style = (
            f"QSpinBox {{"
            f"font-family: {label_font_family}; "
            f"font-size: {label_font_size}pt; "
            f"color: rgb({input_text_color[0]}, {input_text_color[1]}, {input_text_color[2]});"
            f"background-color: rgb({input_bg_color[0] + 5}, {input_bg_color[1] + 5}, {input_bg_color[2] + 5});"
            f"border: 1px solid rgb({input_border[0]}, {input_border[1]}, {input_border[2]});"
            f"border-radius: 3px;"
            f"padding: 4px 6px;"
            f"}}"
            f"QSpinBox:focus {{"
            f"border-color: rgb({input_border[0] + 20}, {input_border[1] + 20}, {input_border[2] + 20});"
            f"}}"
            f"QSpinBox::up-button, QSpinBox::down-button {{"
            f"width: 0px;"
            f"}}"
        )
        
        for spinbox in self.findChildren(QSpinBox):
            spinbox.setStyleSheet(spinbox_style)
        
        # Buttons styling
        buttons_config = dialog_config.get('buttons', {})
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        button_border_radius = buttons_config.get('border_radius', 3)
        button_padding = buttons_config.get('padding', 5)
        button_bg_offset = buttons_config.get('background_offset', 20)
        button_hover_offset = buttons_config.get('hover_background_offset', 30)
        button_pressed_offset = buttons_config.get('pressed_background_offset', 10)
        
        input_border = dialog_config.get('border_color', [60, 60, 65])
        
        button_style = (
            f"QPushButton {{"
            f"min-width: {button_width}px;"
            f"min-height: {button_height}px;"
            f"background-color: rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
            f"border: 1px solid rgb({input_border[0]}, {input_border[1]}, {input_border[2]});"
            f"border-radius: {button_border_radius}px;"
            f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
            f"font-size: {label_font_size}pt;"
            f"padding: {button_padding}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({bg_color[0] + button_hover_offset}, {bg_color[1] + button_hover_offset}, {bg_color[2] + button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({bg_color[0] + button_pressed_offset}, {bg_color[1] + button_pressed_offset}, {bg_color[2] + button_pressed_offset});"
            f"}}"
            f"QPushButton:disabled {{"
            f"background-color: rgb({(bg_color[0] + button_bg_offset) // 2}, {(bg_color[1] + button_bg_offset) // 2}, {(bg_color[2] + button_bg_offset) // 2});"
            f"color: rgb({label_text_color[0] // 2}, {label_text_color[1] // 2}, {label_text_color[2] // 2});"
            f"}}"
        )
        
        for button in self.findChildren(QPushButton):
            button.setStyleSheet(button_style)
        
        # Progress bar styling (use input widget colors)
        progress_bar_style = (
            f"QProgressBar {{"
            f"border: 1px solid rgb({input_border[0]}, {input_border[1]}, {input_border[2]});"
            f"border-radius: 3px;"
            f"text-align: center;"
            f"background-color: rgb({input_bg_color[0]}, {input_bg_color[1]}, {input_bg_color[2]});"
            f"}}"
            f"QProgressBar::chunk {{"
            f"background-color: rgb({checkbox_checked_bg_color[0]}, {checkbox_checked_bg_color[1]}, {checkbox_checked_bg_color[2]});"
            f"border-radius: 2px;"
            f"}}"
        )
        
        self.progress_bar.setStyleSheet(progress_bar_style)

