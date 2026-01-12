"""Bulk analysis controller for managing bulk game analysis operations."""

import os
import threading
import time
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from PyQt6.QtCore import QObject, pyqtSignal, QThread, QMutex, QWaitCondition, QMutexLocker
from PyQt6.QtWidgets import QApplication

from app.models.database_model import DatabaseModel, GameData
from app.models.engine_model import EngineModel
from app.models.move_classification_model import MoveClassificationModel
from app.services.engine_parameters_service import EngineParametersService
from app.services.book_move_service import BookMoveService
from app.services.bulk_analysis_service import BulkAnalysisService
from app.services.progress_service import ProgressService


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
            game_finished_callback: Callback(game, original_idx, success) when a game finishes.
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
        self._is_actively_analyzing = False
    
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
                self._game_finished_callback(game, original_idx, True)
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
            
            self._is_actively_analyzing = True
            try:
                success = self.bulk_analysis_service.analyze_game(game, progress_callback)
                self._game_finished_callback(game, original_idx, success)
            except Exception as e:
                self._game_finished_callback(game, original_idx, False)
            finally:
                self._is_actively_analyzing = False


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
        self._workers: List[ContinuousGameAnalysisWorker] = []
        self._progress_lock = threading.Lock()
        self._game_progress: Dict[int, Dict[str, Any]] = {}  # game_idx -> progress info
        self._analyzed_count = 0
        self._error_count = 0
        self._skipped_count = 0
        self._start_time: Optional[float] = None
        self._completed_game_indices: set = set()  # Track completed game indices
        self._last_status_update_time = 0.0
        # Get status update interval from config
        threading_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {}).get('threading', {})
        self._status_update_interval = threading_config.get('status_update_interval', 0.1)
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
            # Count workers that are both running AND actively analyzing
            active_workers_count = sum(
                1 for w in self._workers 
                if w.isRunning() and getattr(w, '_is_actively_analyzing', False)
            )
            if active_workers_count > 0 and hasattr(self, '_threads_per_engine_list'):
                active_parallel_games = active_workers_count
                # Sum actual thread counts for active workers (dynamic distribution)
                active_worker_indices = [
                    i for i, w in enumerate(self._workers)
                    if w.isRunning() and getattr(w, '_is_actively_analyzing', False)
                ]
                active_total_threads = sum(
                    self._threads_per_engine_list[i] 
                    for i in active_worker_indices
                    if i < len(self._threads_per_engine_list)
                )
            elif active_workers_count > 0 and hasattr(self, '_threads_per_engine') and self._threads_per_engine > 0:
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
    
    def _on_game_finished(self, game: GameData, original_idx: int, success: bool) -> None:
        """Handle game analysis completion.
        
        Args:
            game: GameData instance that was analyzed.
            original_idx: Original index of the game in the full list.
            success: True if analysis succeeded, False otherwise.
        """
        with self._progress_lock:
            # Mark this game index as completed
            self._completed_game_indices.add(original_idx)
            
            if success:
                self._analyzed_count += 1
                self.game_analyzed.emit(game)
            else:
                self._error_count += 1
        
        # Request status update from main thread
        self.status_update_requested.emit()


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
                 game_analysis_controller, database_controller=None) -> None:
        """Initialize the bulk analysis controller.
        
        Args:
            config: Configuration dictionary.
            engine_model: EngineModel instance.
            game_analysis_controller: GameAnalysisController instance.
            database_controller: Optional DatabaseController instance for marking databases as unsaved.
        """
        super().__init__()
        self.config = config
        self.engine_model = engine_model
        self.game_analysis_controller = game_analysis_controller
        self.database_controller = database_controller
        self._analysis_thread = None
        self._current_database_model: Optional[DatabaseModel] = None  # Track database model for current analysis
    
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
    
    
    def get_games_to_analyze(self, selection_mode: str, selected_games: List[GameData]) -> Tuple[Optional[List[GameData]], Optional[str], Optional[str]]:
        """Get games to analyze based on selection mode.
        
        Args:
            selection_mode: "selected" or "all"
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
            if not self.database_controller:
                return (None, "No Database Controller", "Database controller is not available.")
            database_model = self.database_controller.get_active_database()
            if not database_model:
                return (None, "No Database", "No database is currently active.")
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
    
    def get_default_movetime(self, fallback_default: int) -> int:
        """Get default movetime from engine parameters.
        
        Args:
            fallback_default: Fallback value if engine parameters are not available.
            
        Returns:
            Default movetime in milliseconds.
        """
        engine_assignment = self.engine_model.get_assignment(EngineModel.TASK_GAME_ANALYSIS)
        if engine_assignment:
            engine = self.engine_model.get_engine(engine_assignment)
            if engine and engine.is_valid:
                engine_path = Path(engine.path) if not isinstance(engine.path, Path) else engine.path
                task_params = EngineParametersService.get_task_parameters_for_engine(
                    engine_path,
                    "game_analysis",
                    self.config
                )
                return task_params.get("movetime", fallback_default)
        return fallback_default
    
    def start_analysis(self, games: List[GameData], database_model: Optional[DatabaseModel] = None,
                       re_analyze: bool = False,
                       movetime_override: Optional[int] = None,
                       max_threads_override: Optional[int] = None,
                       parallel_games_override: Optional[int] = None) -> None:
        """Start bulk analysis for the given games.
        
        Args:
            games: List of games to analyze.
            database_model: Optional DatabaseModel instance that contains these games.
            re_analyze: Whether to re-analyze already analyzed games.
            movetime_override: Optional override for movetime in milliseconds.
            max_threads_override: Optional override for maximum total threads (None = unlimited).
            parallel_games_override: Optional override for number of parallel games (None = use config default).
        """
        # Track database model for updating games after analysis
        self._current_database_model = database_model
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
    
    def update_status(self) -> None:
        """Update status messages from the analysis thread.
        
        This should be called from the main thread when status_update_requested is emitted.
        """
        if self._analysis_thread:
            self._analysis_thread._update_status_messages()
    
    def is_cancelled(self) -> bool:
        """Check if analysis is cancelled.
        
        Returns:
            True if analysis thread exists and is cancelled, False otherwise.
        """
        return self._analysis_thread is not None and self._analysis_thread._cancelled
    
    def is_thread_running(self) -> bool:
        """Check if analysis thread is running.
        
        Returns:
            True if analysis thread exists and is running, False otherwise.
        """
        return self._analysis_thread is not None and self._analysis_thread.isRunning()
    
    def update_game_in_database(self, game: GameData, database_model: Optional[DatabaseModel] = None) -> None:
        """Update game in database model and mark database as unsaved.
        
        Args:
            game: GameData instance that was analyzed.
            database_model: Optional DatabaseModel instance to update. If None, uses the tracked database model.
        """
        # Use provided database model or fall back to tracked one
        target_model = database_model if database_model is not None else self._current_database_model
        
        if target_model:
            # Update game in database model (this will refresh the view)
            target_model.update_game(game)
            # Mark database as having unsaved changes to show flashing indicator
            if self.database_controller:
                self.database_controller.mark_database_unsaved(target_model)
    
    def set_progress_status(self, message: str) -> None:
        """Set progress service status message.
        
        Args:
            message: Status message to display.
        """
        progress_service = ProgressService.get_instance()
        progress_service.set_status(message)
    
    def hide_progress(self) -> None:
        """Hide progress service."""
        progress_service = ProgressService.get_instance()
        progress_service.hide_progress()
    
    def show_progress(self) -> None:
        """Show progress service."""
        progress_service = ProgressService.get_instance()
        progress_service.show_progress()
    
    def set_progress_value(self, value: int) -> None:
        """Set progress service progress value.
        
        Args:
            value: Progress value (0-100).
        """
        progress_service = ProgressService.get_instance()
        progress_service.set_progress(value)

