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
import os

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
            finally:
                # Cleanup is handled by BulkAnalysisThread's finally block
                # This ensures cleanup happens even if worker finishes normally
                pass


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
                 re_analyze: bool = False, movetime_override: Optional[int] = None,
                 max_threads_override: Optional[int] = None,
                 parallel_games_override: Optional[int] = None) -> None:
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
            max_threads_override: Optional override for maximum total threads (None = unlimited).
            parallel_games_override: Optional override for number of parallel games (None = use config default).
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
        self.max_threads_override = max_threads_override
        self.parallel_games_override = parallel_games_override
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
        # Get status update interval from config
        threading_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {}).get('threading', {})
        self._status_update_interval = threading_config.get('status_update_interval', 0.1)
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
        # Thread information for status bar display
        self._total_threads_used = 0
        self._parallel_games = 0
        self._threads_per_engine = 0
        self._analysis_services: List[BulkAnalysisService] = []  # Store for cleanup
    
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
        # Don't update status if analysis has been cancelled
        if self._cancelled:
            return
        
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
            progress_display_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {}).get('progress_display', {})
            decimal_precision = progress_display_config.get('decimal_precision', 4)
            progress_percent_str = f"100.{'0' * decimal_precision}%"
            self.progress_updated.emit(100.0, dialog_status, progress_percent_str)
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
        
        # Calculate average progress of active games (with configurable decimal precision)
        progress_display_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {}).get('progress_display', {})
        decimal_precision = progress_display_config.get('decimal_precision', 4)
        if active_count > 0:
            avg_active_progress = (active_progress_sum / active_count) * 100.0
            avg_active_progress_str = f"{avg_active_progress:.{decimal_precision}f}"
        else:
            avg_active_progress = 0.0
            avg_active_progress_str = f"0.{'0' * decimal_precision}"
        
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
        
        # Calculate active workers and thread information dynamically
        active_workers_count = 0
        active_parallel_games = 0
        active_total_threads = 0
        
        if hasattr(self, '_workers') and self._workers:
            active_workers_count = sum(1 for w in self._workers if w.isRunning())
            if active_workers_count > 0 and hasattr(self, '_threads_per_engine_list'):
                active_parallel_games = active_workers_count
                # Sum actual thread counts for active workers (dynamic distribution)
                active_total_threads = sum(
                    self._threads_per_engine_list[i] 
                    for i in range(min(active_workers_count, len(self._threads_per_engine_list)))
                )
            elif active_workers_count > 0 and hasattr(self, '_threads_per_engine') and self._threads_per_engine > 0:
                # Fallback for backward compatibility
                active_parallel_games = active_workers_count
                active_total_threads = active_workers_count * self._threads_per_engine
            else:
                # Fall back to initial values if threads_per_engine not set or no active workers
                active_parallel_games = self._parallel_games if hasattr(self, '_parallel_games') else 0
                active_total_threads = self._total_threads_used if hasattr(self, '_total_threads_used') else 0
        else:
            # Workers not initialized yet, use initial values
            active_parallel_games = self._parallel_games if hasattr(self, '_parallel_games') else 0
            active_total_threads = self._total_threads_used if hasattr(self, '_total_threads_used') else 0
        
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
        
        # Use floating point progress with configurable decimal precision
        progress_display_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {}).get('progress_display', {})
        max_progress_cap = progress_display_config.get('max_progress_cap', 99.9999)
        decimal_precision = progress_display_config.get('decimal_precision', 4)
        progress_value = min(overall_progress, max_progress_cap)
        progress_percent_str = f"{progress_value:.{decimal_precision}f}%"
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
                
                # Format thread info - show distribution if threads vary, otherwise show simple format
                if active_total_threads > 0 and hasattr(self, '_threads_per_engine_list') and active_parallel_games <= len(self._threads_per_engine_list):
                    thread_counts = [self._threads_per_engine_list[i] for i in range(active_parallel_games)]
                    if len(set(thread_counts)) == 1:
                        # All same - show simple format
                        threads_info = f"{active_total_threads} threads ({active_parallel_games}×{thread_counts[0]})"
                    else:
                        # Varying - show distribution
                        thread_dist = "+".join(map(str, thread_counts))
                        threads_info = f"{active_total_threads} threads ({thread_dist})"
                elif active_total_threads > 0 and hasattr(self, '_threads_per_engine') and self._threads_per_engine > 0:
                    threads_info = f"{active_total_threads} threads ({active_parallel_games}×{self._threads_per_engine})"
                else:
                    threads_info = ""
                status_parts = [
                    f"Bulk Analysis: Analyzing {active_count} game{'s' if active_count != 1 else ''} ({avg_active_progress_str}%) from total {total_games} games, {completed_count} completed",
                    threads_info,
                    avg_depth_str,
                    avg_seldepth_str,
                    f"Estimated time remaining: {time_str}"
                ]
                status_bar_message = " | ".join([p for p in status_parts if p])
            else:
                # Format thread info - show distribution if threads vary, otherwise show simple format
                if active_total_threads > 0 and hasattr(self, '_threads_per_engine_list') and active_parallel_games <= len(self._threads_per_engine_list):
                    thread_counts = [self._threads_per_engine_list[i] for i in range(active_parallel_games)]
                    if len(set(thread_counts)) == 1:
                        # All same - show simple format
                        threads_info = f"{active_total_threads} threads ({active_parallel_games}×{thread_counts[0]})"
                    else:
                        # Varying - show distribution
                        thread_dist = "+".join(map(str, thread_counts))
                        threads_info = f"{active_total_threads} threads ({thread_dist})"
                elif active_total_threads > 0 and hasattr(self, '_threads_per_engine') and self._threads_per_engine > 0:
                    threads_info = f"{active_total_threads} threads ({active_parallel_games}×{self._threads_per_engine})"
                else:
                    threads_info = ""
                status_parts = [
                    f"Bulk Analysis: Analyzing {active_count} game{'s' if active_count != 1 else ''} ({avg_active_progress_str}%) from total {total_games} games, {completed_count} completed",
                    threads_info,
                    avg_depth_str,
                    avg_seldepth_str
                ]
                status_bar_message = " | ".join([p for p in status_parts if p])
        else:
            # Format thread info - show distribution if threads vary, otherwise show simple format
            if active_total_threads > 0 and hasattr(self, '_threads_per_engine_list') and active_parallel_games <= len(self._threads_per_engine_list):
                thread_counts = [self._threads_per_engine_list[i] for i in range(active_parallel_games)]
                if len(set(thread_counts)) == 1:
                    # All same - show simple format
                    threads_info = f"{active_total_threads} threads ({active_parallel_games}×{thread_counts[0]})"
                else:
                    # Varying - show distribution
                    thread_dist = "+".join(map(str, thread_counts))
                    threads_info = f"{active_total_threads} threads ({thread_dist})"
            elif active_total_threads > 0 and hasattr(self, '_threads_per_engine') and self._threads_per_engine > 0:
                threads_info = f"{active_total_threads} threads ({active_parallel_games}×{self._threads_per_engine})"
            else:
                threads_info = ""
            status_parts = [
                f"Bulk Analysis: Preparing analysis of {games_being_analyzed} game{'s' if games_being_analyzed != 1 else ''} from total {total_games} games, {completed_count} completed",
                threads_info
            ]
            status_bar_message = " | ".join([p for p in status_parts if p]) + "."
        
        progress_service.set_status(status_bar_message)
        
        # Update progress bar percentage (convert float to int, 0-100)
        progress_service.set_progress(int(overall_progress))
    
    def run(self) -> None:
        """Run bulk analysis with parallel execution."""
        try:
            # Get progress display config for formatting
            progress_display_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {}).get('progress_display', {})
            decimal_precision = progress_display_config.get('decimal_precision', 4)
            initial_progress_str = f"0.{'0' * decimal_precision}%"
            
            # Emit initial progress to show thread has started
            self.progress_updated.emit(0.0, "Initializing bulk analysis...", initial_progress_str)
            
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
            self.progress_updated.emit(0.0, f"Preparing to analyze {len(games_to_analyze)} games...", initial_progress_str)
            
            # Calculate parallel resources based on parallel_games_override or config default
            threading_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {}).get('threading', {})
            if self.parallel_games_override is not None:
                max_parallel_games = self.parallel_games_override
            else:
                max_parallel_games = threading_config.get('default_parallel_games', 4)
            parallel_games, threads_per_engine_list = BulkAnalysisService.calculate_parallel_resources(
                max_parallel_games=max_parallel_games, max_total_threads=self.max_threads_override
            )
            
            # Store thread information for status bar display
            self._parallel_games = parallel_games
            self._threads_per_engine_list = threads_per_engine_list  # Store full list for dynamic distribution
            self._threads_per_engine = threads_per_engine_list[0] if threads_per_engine_list else 0  # For backward compatibility
            self._total_threads_used = sum(threads_per_engine_list)
            
            # Limit parallel games to actual number of games
            parallel_games = min(parallel_games, len(games_to_analyze))
            
            # Initialize start time for time estimation
            self._start_time = time.time()
            
            # Store games and indices for queue access
            self._games_to_analyze = games_to_analyze
            self._original_indices = original_indices
            self._next_game_idx = 0
            
            # Emit progress update
            self.progress_updated.emit(0.0, f"Creating {parallel_games} analysis service(s)...", initial_progress_str)
            
            # Create BulkAnalysisService instances (one per parallel game)
            self._analysis_services = []
            for i in range(parallel_games):
                # Use dynamic thread distribution - each game may get different thread count
                threads_for_this_game = threads_per_engine_list[i] if i < len(threads_per_engine_list) else threads_per_engine_list[0]
                service = BulkAnalysisService(
                    self.config,
                    self.engine_model,
                    self.opening_service,
                    self.book_move_service,
                    self.classification_model,
                    threads_override=threads_for_this_game,
                    movetime_override=self.movetime_override
                )
                self._analysis_services.append(service)
            
            # Emit progress update
            self.progress_updated.emit(0.0, f"Starting {parallel_games} worker thread(s)...", initial_progress_str)
            
            # Create worker threads that will continuously pick up games
            self._workers = []
            for i in range(parallel_games):
                worker = ContinuousGameAnalysisWorker(
                    i,
                    total_games,
                    self._analysis_services[i],
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
            self.progress_updated.emit(0.0, f"Analysis started: {len(games_to_analyze)} games, {parallel_games} parallel worker(s)...", initial_progress_str)
            
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
            # Cleanup workers
            for worker in self._workers:
                if worker.isRunning():
                    worker.cancel()
                    worker.wait()
            
            # Cleanup all analysis services (even if workers finished normally)
            for service in self._analysis_services:
                if service:
                    service.cleanup()
            self._analysis_services = []
    
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
                 bulk_analysis_controller, database_panel=None, parent=None) -> None:
        """Initialize the bulk analysis dialog.
        
        Args:
            config: Configuration dictionary.
            database_model: DatabaseModel instance for the active database.
            bulk_analysis_controller: BulkAnalysisController instance.
            database_panel: Optional DatabasePanel instance for getting selected games.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.database_model = database_model
        self.controller = bulk_analysis_controller
        self.database_panel = database_panel
        
        # Set database panel in controller
        if database_panel:
            self.controller.set_database_panel(database_panel)
        self.selected_games: List[GameData] = []
        
        # Connect to controller signals
        self.controller.progress_updated.connect(self._on_progress_updated)
        self.controller.status_update_requested.connect(self._on_status_update_requested)
        self.controller.game_analyzed.connect(self._on_game_analyzed)
        self.controller.finished.connect(self._on_analysis_finished)
        
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
        from app.utils.font_utils import scale_font_size
        
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {})
        layout_config = dialog_config.get('layout', {})
        layout_spacing = layout_config.get('spacing', 15)
        layout_margins = layout_config.get('margins', [25, 25, 25, 25])
        spacing_config = dialog_config.get('spacing', {})
        section_spacing = spacing_config.get('section', 15)
        
        layout = QVBoxLayout(self)
        # Set spacing to 0 to disable automatic spacing - we'll use explicit spacing instead
        layout.setSpacing(0)
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
        
        layout.addSpacing(section_spacing)
        
        # Options group
        options_group = QGroupBox("Options")
        options_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(group_margins[0], group_margins[1], group_margins[2], group_margins[3])
        options_layout.setSpacing(section_spacing)
        
        # Re-analyze checkbox row
        self.re_analyze_checkbox = QCheckBox("Re-analyze already analyzed games")
        self.re_analyze_checkbox.setChecked(False)
        self.re_analyze_checkbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        options_layout.addWidget(self.re_analyze_checkbox)
        
        # Controls row: parallel games and max_threads on same row
        controls_row_layout = QHBoxLayout()
        controls_row_layout.setSpacing(spacing_config.get('controls_row', 20))
        
        # Parallel games input
        parallel_games_row_layout = QHBoxLayout()
        parallel_games_row_layout.setSpacing(spacing_config.get('label_spinbox', 8))
        
        # Get parallel games config
        parallel_games_config = dialog_config.get('parallel_games_spinbox', {})
        parallel_games_min = parallel_games_config.get('min_value', 1)
        parallel_games_max = parallel_games_config.get('max_value', 16)
        threading_config = dialog_config.get('threading', {})
        parallel_games_default = threading_config.get('default_parallel_games', 4)
        parallel_games_step = parallel_games_config.get('single_step', 1)
        parallel_games_suffix = parallel_games_config.get('suffix', '')
        
        # Store original max for "all games" mode
        self._parallel_games_max_all = parallel_games_max
        
        # Parallel games label (set fixed width to align with time per move)
        labels_config = dialog_config.get('labels', {})
        parallel_games_label = QLabel("Parallel games:")
        parallel_games_label.setStyleSheet(
            f"font-size: {scale_font_size(labels_config.get('font_size', 11))}pt; "
            f"color: rgb({labels_config.get('text_color', [200, 200, 200])[0]}, "
            f"{labels_config.get('text_color', [200, 200, 200])[1]}, "
            f"{labels_config.get('text_color', [200, 200, 200])[2]});"
        )
        # Set fixed width to match "Time per move:" label for vertical alignment
        label_fixed_width = labels_config.get('fixed_width', 110)
        parallel_games_label.setFixedWidth(label_fixed_width)
        parallel_games_row_layout.addWidget(parallel_games_label)
        
        # Parallel games spinbox
        self.parallel_games_spinbox = QSpinBox()
        self.parallel_games_spinbox.setMinimum(parallel_games_min)
        self.parallel_games_spinbox.setMaximum(parallel_games_max)
        self.parallel_games_spinbox.setSingleStep(parallel_games_step)
        self.parallel_games_spinbox.setValue(parallel_games_default)
        if parallel_games_suffix:
            self.parallel_games_spinbox.setSuffix(parallel_games_suffix)
        parallel_games_row_layout.addWidget(self.parallel_games_spinbox)
        
        controls_row_layout.addLayout(parallel_games_row_layout, 0)  # Stretch factor 0 to prevent stretching
        
        # Add stretch to push max threads to the right
        controls_row_layout.addStretch()
        
        # Max threads input (on same row as parallel games, aligned to the right)
        max_threads_row_layout = QHBoxLayout()
        max_threads_row_layout.setSpacing(spacing_config.get('label_spinbox', 8))
        
        # Get max threads config
        max_threads_config = dialog_config.get('max_threads_spinbox', {})
        max_threads_min = max_threads_config.get('min_value', 0)
        max_threads_max = max_threads_config.get('max_value', 128)
        max_threads_default = max_threads_config.get('default_value', 0)
        max_threads_step = max_threads_config.get('single_step', 1)
        max_threads_suffix = max_threads_config.get('suffix', '')
        max_threads_special_text = max_threads_config.get('special_value_text', 'Unlimited')
        
        # Use available cores as maximum if not specified or if specified max is too high
        cpu_count_fallback = threading_config.get('cpu_count_fallback', 4)
        available_cores = os.cpu_count() or cpu_count_fallback
        if max_threads_max > available_cores:
            max_threads_max = available_cores
        
        # Max threads label
        max_threads_label = QLabel("Max threads:")
        max_threads_label.setStyleSheet(
            f"font-size: {scale_font_size(labels_config.get('font_size', 11))}pt; "
            f"color: rgb({labels_config.get('text_color', [200, 200, 200])[0]}, "
            f"{labels_config.get('text_color', [200, 200, 200])[1]}, "
            f"{labels_config.get('text_color', [200, 200, 200])[2]});"
        )
        max_threads_row_layout.addWidget(max_threads_label)
        
        # Max threads spinbox
        self.max_threads_spinbox = QSpinBox()
        self.max_threads_spinbox.setMinimum(max_threads_min)
        self.max_threads_spinbox.setMaximum(max_threads_max)
        self.max_threads_spinbox.setSingleStep(max_threads_step)
        self.max_threads_spinbox.setValue(max_threads_default)
        if max_threads_suffix:
            self.max_threads_spinbox.setSuffix(max_threads_suffix)
        if max_threads_special_text and max_threads_min == 0:
            self.max_threads_spinbox.setSpecialValueText(max_threads_special_text)
        max_threads_row_layout.addWidget(self.max_threads_spinbox)
        
        controls_row_layout.addLayout(max_threads_row_layout, 0)  # Stretch factor 0 to prevent stretching
        
        options_layout.addLayout(controls_row_layout)
        
        # Time per move row (below parallel games and max threads)
        movetime_row_layout = QHBoxLayout()
        movetime_row_layout.setSpacing(spacing_config.get('label_spinbox', 8))
        
        movetime_label = QLabel("Time per move:")
        movetime_label.setStyleSheet(
            f"font-size: {scale_font_size(labels_config.get('font_size', 11))}pt; "
            f"color: rgb({labels_config.get('text_color', [200, 200, 200])[0]}, "
            f"{labels_config.get('text_color', [200, 200, 200])[1]}, "
            f"{labels_config.get('text_color', [200, 200, 200])[2]});"
        )
        # Set same fixed width as parallel games label for vertical alignment
        movetime_label.setFixedWidth(label_fixed_width)
        movetime_row_layout.addWidget(movetime_label)
        
        # Get movetime spinbox config
        movetime_config = dialog_config.get('movetime_spinbox', {})
        movetime_min = movetime_config.get('min_value', 100)
        movetime_max = movetime_config.get('max_value', 60000)
        movetime_step = movetime_config.get('single_step', 100)
        movetime_suffix = movetime_config.get('suffix', ' ms')
        movetime_fallback_default = movetime_config.get('fallback_default', 1000)
        
        # Get default movetime from engine parameters
        default_movetime = movetime_fallback_default
        engine_model = self.controller.engine_model
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
                default_movetime = task_params.get("movetime", movetime_fallback_default)
        
        self.movetime_spinbox = QSpinBox()
        self.movetime_spinbox.setMinimum(movetime_min)
        self.movetime_spinbox.setMaximum(movetime_max)
        self.movetime_spinbox.setSingleStep(movetime_step)
        self.movetime_spinbox.setValue(default_movetime)
        self.movetime_spinbox.setSuffix(movetime_suffix)
        movetime_row_layout.addWidget(self.movetime_spinbox)
        
        # Set fixed width for all spinboxes (after all are created)
        spinboxes_config = dialog_config.get('spinboxes', {})
        spinbox_fixed_width = spinboxes_config.get('fixed_width', 80)
        self.parallel_games_spinbox.setFixedWidth(spinbox_fixed_width)
        self.max_threads_spinbox.setFixedWidth(spinbox_fixed_width)
        self.movetime_spinbox.setFixedWidth(spinbox_fixed_width)
        
        movetime_row_layout.addStretch()
        
        options_layout.addLayout(movetime_row_layout)
        
        layout.addWidget(options_group)
        
        layout.addSpacing(section_spacing)
        
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
        progress_bar_layout.setSpacing(spacing_config.get('progress_bar', 8))
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)  # Hide text inside progress bar since we have a label
        progress_bar_layout.addWidget(self.progress_bar)
        
        # Percentage label
        progress_display_config = dialog_config.get('progress_display', {})
        decimal_precision = progress_display_config.get('decimal_precision', 4)
        percent_label_min_width = progress_display_config.get('percent_label_min_width', 80)
        initial_progress_str = f"0.{'0' * decimal_precision}%"
        self.progress_percent_label = QLabel(initial_progress_str)
        self.progress_percent_label.setStyleSheet(
            f"font-size: {status_font_size}pt; "
            f"color: rgb({status_text_color[0]}, {status_text_color[1]}, {status_text_color[2]});"
        )
        self.progress_percent_label.setMinimumWidth(percent_label_min_width)
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
        
        # Add spacing before buttons
        layout.addSpacing(section_spacing)
        layout.addLayout(button_layout)
        
        # Initialize parallel games limit based on current selection
        self._update_parallel_games_limit()
    
    def _on_selection_changed(self) -> None:
        """Handle selection radio button change."""
        if self.selected_games_radio.isChecked():
            self._update_selected_games()
            # Disable start button if no games selected
            if not self.selected_games:
                self.start_button.setEnabled(False)
            else:
                self.start_button.setEnabled(True)
            # Update parallel games max limit
            self._update_parallel_games_limit()
        else:
            self.start_button.setEnabled(True)
            # Reset parallel games max to config value
            self._update_parallel_games_limit()
    
    def _update_selected_games(self) -> None:
        """Update the list of selected games."""
        if self.database_model:
            self.selected_games = self.controller.get_selected_games(self.database_model)
            # Update parallel games limit if in selected games mode
            if self.selected_games_radio.isChecked():
                self._update_parallel_games_limit()
    
    def _update_parallel_games_limit(self) -> None:
        """Update the maximum value of the parallel games spinbox based on selection mode."""
        # Check if spinbox exists (may be called during initialization)
        if not hasattr(self, 'parallel_games_spinbox'):
            return
        
        if self.selected_games_radio.isChecked():
            # Limit to number of selected games (but not less than minimum)
            num_selected = len(self.selected_games)
            current_min = self.parallel_games_spinbox.minimum()
            new_max = max(current_min, num_selected)
            self.parallel_games_spinbox.setMaximum(new_max)
            # If current value exceeds new max, adjust it
            if self.parallel_games_spinbox.value() > new_max:
                self.parallel_games_spinbox.setValue(new_max)
        else:
            # Use config max value for "all games" mode
            self.parallel_games_spinbox.setMaximum(self._parallel_games_max_all)
    
    def _start_analysis(self) -> None:
        """Start the bulk analysis."""
        # Validate engine using controller
        is_valid, error_title, error_message = self.controller.validate_engine_for_analysis()
        if not is_valid:
            from app.views.message_dialog import MessageDialog
            dialog = MessageDialog(
                self.config,
                error_title,
                error_message,
                message_type="warning",
                parent=self
            )
            dialog.exec()
            return
        
        # Get games to analyze using controller
        selection_mode = "selected" if self.selected_games_radio.isChecked() else "all"
        games_to_analyze, error_title, error_message = self.controller.get_games_to_analyze(
            selection_mode,
            self.database_model,
            self.selected_games
        )
        
        if games_to_analyze is None:
            from app.views.message_dialog import MessageDialog
            message_type = "warning" if error_title == "No Games Selected" else "information"
            dialog = MessageDialog(
                self.config,
                error_title,
                error_message,
                message_type=message_type,
                parent=self
            )
            dialog.exec()
            return
        
        # Update progress group (always visible)
        progress_display_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {}).get('progress_display', {})
        decimal_precision = progress_display_config.get('decimal_precision', 4)
        initial_progress_str = f"0.{'0' * decimal_precision}%"
        self.progress_bar.setValue(0)
        self.progress_percent_label.setText(initial_progress_str)
        self.status_label.setText(f"Preparing to analyze {len(games_to_analyze)} games...")
        
        # Disable controls
        self.selected_games_radio.setEnabled(False)
        self.all_games_radio.setEnabled(False)
        self.re_analyze_checkbox.setEnabled(False)
        self.movetime_spinbox.setEnabled(False)
        self.parallel_games_spinbox.setEnabled(False)
        self.max_threads_spinbox.setEnabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setText("Cancel")
        
        # Prepare services using controller (with status updates)
        def status_callback(message: str) -> None:
            self.status_label.setText(message)
            QApplication.processEvents()  # Allow UI to update
        
        self.controller.prepare_services_for_analysis(status_callback)
        
        # Get analysis parameters from UI
        re_analyze = self.re_analyze_checkbox.isChecked()
        movetime_override = self.movetime_spinbox.value()  # Get value from spinbox
        
        # Get max_threads_override (0 means unlimited, convert to None)
        max_threads_value = self.max_threads_spinbox.value()
        max_threads_override = None if max_threads_value == 0 else max_threads_value
        
        # Get parallel_games_override (use value from spinbox)
        parallel_games_override = self.parallel_games_spinbox.value()
        
        # Show progress service in status bar
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        progress_service.show_progress()
        progress_service.set_progress(0)
        
        # Start analysis via controller
        self.controller.start_analysis(
            games_to_analyze,
            re_analyze=re_analyze,
            movetime_override=movetime_override,
            max_threads_override=max_threads_override,
            parallel_games_override=parallel_games_override
        )
    
    def _on_progress_updated(self, progress_percent: float, status_message: str, progress_percent_str: str) -> None:
        """Handle progress update from analysis thread."""
        # QProgressBar uses int, but we display the float value in the label next to it
        self.progress_bar.setValue(int(progress_percent))
        self.progress_percent_label.setText(progress_percent_str)
        self.status_label.setText(status_message)
        QApplication.processEvents()
    
    def _on_status_update_requested(self) -> None:
        """Handle status update request from analysis thread (called from main thread)."""
        analysis_thread = self.controller.get_analysis_thread()
        if analysis_thread:
            # Check if cancelled and update status accordingly
            if analysis_thread._cancelled:
                from app.services.progress_service import ProgressService
                progress_service = ProgressService.get_instance()
                # Show "Cancelling..." only if thread is still running
                # Once thread finishes, _on_analysis_finished will show "Cancelled by user"
                if analysis_thread.isRunning():
                    progress_service.set_status("Bulk Analysis: Cancelling...")
                    self.status_label.setText("Cancelling...")
                else:
                    progress_service.set_status("Bulk Analysis: Cancelled by user")
                    self.status_label.setText("Cancelled by user")
            else:
                analysis_thread._update_status_messages()
    
    def _on_game_analyzed(self, game: GameData) -> None:
        """Handle game analyzed signal."""
        # Update database model if needed
        if self.database_model:
            # Update game in database model (this will refresh the view)
            self.database_model.update_game(game)
            # Mark database as having unsaved changes to show flashing indicator
            if self.database_panel:
                self.database_panel.mark_database_unsaved(self.database_model)
            QApplication.processEvents()
    
    def _on_analysis_finished(self, success: bool, message: str) -> None:
        """Handle analysis finished signal."""
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        if success:
            progress_display_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {}).get('progress_display', {})
            decimal_precision = progress_display_config.get('decimal_precision', 4)
            final_progress_str = f"100.{'0' * decimal_precision}%"
            self.progress_bar.setValue(100)
            self.progress_percent_label.setText(final_progress_str)
            self.status_label.setText(message)
            # Update status bar
            progress_service.set_status(f"Bulk Analysis: {message}")
            self.cancel_button.setText("Close")
            self.cancel_button.clicked.disconnect()
            self.cancel_button.clicked.connect(self.accept)
        else:
            # Check if this is a cancellation
            if "cancelled" in message.lower():
                status_message = "Bulk Analysis: Cancelled by user"
                self.status_label.setText("Cancelled by user")
            else:
                status_message = f"Bulk Analysis: Error - {message}"
                self.status_label.setText(f"Error: {message}")
            
            # Update status bar - ALWAYS set status BEFORE hiding progress
            # This ensures the status is visible even if this is called after _on_cancel
            progress_service.set_status(status_message)
            QApplication.processEvents()  # Ensure status bar updates
            
            # Re-enable controls for retry
            self.selected_games_radio.setEnabled(True)
            self.all_games_radio.setEnabled(True)
            self.re_analyze_checkbox.setEnabled(True)
            self.movetime_spinbox.setEnabled(True)
            self.parallel_games_spinbox.setEnabled(True)
            self.max_threads_spinbox.setEnabled(True)
            self.start_button.setEnabled(True)
            self.cancel_button.setText("Cancel")
        
        # Hide progress service at the end (after status is set and processed)
        progress_service.hide_progress()
    
    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        if self.controller.is_analysis_running():
            self.controller.cancel_analysis()
            self.status_label.setText("Cancelling...")
            self.cancel_button.setEnabled(False)
            
            # Update status bar immediately
            progress_service.set_status("Bulk Analysis: Cancelling...")
            QApplication.processEvents()  # Ensure UI updates
            
            # Wait for thread to finish
            self.controller.wait_for_analysis()
            
            # Ensure status bar is updated with cancellation message
            # Set status BEFORE hiding progress to ensure it's visible
            progress_service.set_status("Bulk Analysis: Cancelled by user")
            self.status_label.setText("Cancelled by user")
            QApplication.processEvents()  # Ensure UI updates
            
            # Hide progress service AFTER setting status
            progress_service.hide_progress()
        else:
            # Thread not running, just hide progress
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
        
        # Group box styling - use StyleManager
        groups_config = dialog_config.get('groups', {})
        group_border_color = groups_config.get('border_color', [60, 60, 65])
        group_border_width = groups_config.get('border_width', 1)
        group_border_radius = groups_config.get('border_radius', 5)
        group_bg_color = groups_config.get('background_color')  # None = use unified default
        group_title_color = groups_config.get('title_color', [240, 240, 240])
        group_title_font_family_raw = groups_config.get('title_font_family', 'Helvetica Neue')
        from app.utils.font_utils import resolve_font_family, scale_font_size
        from app.views.style import StyleManager
        group_title_font_family = resolve_font_family(group_title_font_family_raw)
        group_title_font_size = scale_font_size(groups_config.get('title_font_size', 11))
        group_margin_top = groups_config.get('margin_top', 10)
        group_padding_top = groups_config.get('padding_top', 5)
        group_title_left = groups_config.get('title_left', 10)
        group_title_padding = groups_config.get('title_padding', [0, 5])
        
        group_boxes = list(self.findChildren(QGroupBox))
        if group_boxes:
            StyleManager.style_group_boxes(
                group_boxes,
                self.config,
                border_color=group_border_color,
                border_width=group_border_width,
                border_radius=group_border_radius,
                bg_color=group_bg_color,
                margin_top=group_margin_top,
                padding_top=group_padding_top,
                title_font_family=group_title_font_family,
                title_font_size=group_title_font_size,
                title_color=group_title_color,
                title_left=group_title_left,
                title_padding=group_title_padding
            )
        
        # Apply checkbox styling using StyleManager
        from app.views.style import StyleManager
        
        # Get checkmark icon path
        project_root = Path(__file__).parent.parent.parent
        checkmark_path = project_root / "app" / "resources" / "icons" / "checkmark.svg"
        
        # Use input border and background colors for checkbox indicator
        input_border_color = dialog_config.get('border_color', [60, 60, 65])
        input_bg_color = [bg_color[0] + 5, bg_color[1] + 5, bg_color[2] + 5]
        
        # Get all checkboxes and apply styling
        checkboxes = self.findChildren(QCheckBox)
        StyleManager.style_checkboxes(
            checkboxes,
            self.config,
            label_text_color,
            label_font_family,
            label_font_size,
            input_bg_color,
            input_border_color,
            checkmark_path
        )
        
        # Apply radio button styling using StyleManager (uses unified config)
        from app.views.style import StyleManager
        radio_buttons = list(self.findChildren(QRadioButton))
        if radio_buttons:
            StyleManager.style_radio_buttons(radio_buttons, self.config)
        
        # SpinBox styling (use input widget colors) - use StyleManager
        input_bg_color = dialog_config.get('background_color', [40, 40, 45])
        input_border = dialog_config.get('border_color', [60, 60, 65])
        input_text_color = dialog_config.get('text_color', [200, 200, 200])
        
        # Calculate background color with offset
        spinbox_bg_color = [
            min(255, input_bg_color[0] + 5),
            min(255, input_bg_color[1] + 5),
            min(255, input_bg_color[2] + 5)
        ]
        
        # Calculate focus border color with offset
        spinbox_focus_border_color = [
            min(255, input_border[0] + 20),
            min(255, input_border[1] + 20),
            min(255, input_border[2] + 20)
        ]
        
        # Apply unified spinbox styling using StyleManager
        spinboxes = list(self.findChildren(QSpinBox))
        if spinboxes:
            StyleManager.style_spinboxes(
                spinboxes,
                self.config,
                text_color=input_text_color,
                font_family=label_font_family,
                font_size=label_font_size,
                bg_color=spinbox_bg_color,
                border_color=input_border,
                focus_border_color=spinbox_focus_border_color,
                border_width=1,
                border_radius=3,
                padding=[6, 4]  # [horizontal, vertical]
            )
        
        # Apply button styling using StyleManager (uses unified config)
        buttons_config = dialog_config.get('buttons', {})
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        border_color = dialog_config.get('border_color', [60, 60, 65])
        bg_color_list = [bg_color[0], bg_color[1], bg_color[2]]
        border_color_list = [border_color[0], border_color[1], border_color[2]]
        
        from app.views.style import StyleManager
        all_buttons = self.findChildren(QPushButton)
        StyleManager.style_buttons(
            all_buttons,
            self.config,
            bg_color_list,
            border_color_list,
            min_width=button_width,
            min_height=button_height
        )
        
        # Progress bar styling (use dedicated progress bar config)
        progress_bar_config = dialog_config.get('progress_bar', {})
        progress_bg_color = progress_bar_config.get('background_color', [30, 30, 35])
        progress_border_color = progress_bar_config.get('border_color', [60, 60, 65])
        progress_border_radius = progress_bar_config.get('border_radius', 3)
        progress_chunk_bg_color = progress_bar_config.get('chunk_background_color', [70, 90, 130])
        progress_chunk_border_radius = progress_bar_config.get('chunk_border_radius', 2)
        
        progress_bar_style = (
            f"QProgressBar {{"
            f"border: 1px solid rgb({progress_border_color[0]}, {progress_border_color[1]}, {progress_border_color[2]});"
            f"border-radius: {progress_border_radius}px;"
            f"text-align: center;"
            f"background-color: rgb({progress_bg_color[0]}, {progress_bg_color[1]}, {progress_bg_color[2]});"
            f"}}"
            f"QProgressBar::chunk {{"
            f"background-color: rgb({progress_chunk_bg_color[0]}, {progress_chunk_bg_color[1]}, {progress_chunk_bg_color[2]});"
            f"border-radius: {progress_chunk_border_radius}px;"
            f"}}"
        )
        
        self.progress_bar.setStyleSheet(progress_bar_style)

