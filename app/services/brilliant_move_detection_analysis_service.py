"""Brilliant move detection analysis service for analyzing moves at shallow depths."""

import sys
import time
import queue
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from app.services.uci_communication_service import UCICommunicationService
from app.services.logging_service import LoggingService


class BrilliantMoveDetectionRequest:
    """Request for analyzing a position at shallow depth."""
    def __init__(self, fen: str, move_number: int, shallow_depth: int):
        self.fen = fen
        self.move_number = move_number
        self.shallow_depth = shallow_depth
        self.completed = False
        self.result: Optional[Tuple[float, bool, int, str]] = None  # centipawns, is_mate, mate_moves, best_move_san


class BrilliantMoveDetectionAnalysisThread(QThread):
    """Persistent thread for analyzing positions at shallow depths."""
    
    analysis_complete = pyqtSignal(float, bool, int, str, int)  # centipawns, is_mate, mate_moves, best_move_san, depth
    error_occurred = pyqtSignal(str)  # error_message
    
    def __init__(self, engine_path: Path, time_limit_ms: int,
                 max_threads: Optional[int] = None, engine_name: str = "", engine_options: Optional[Dict[str, Any]] = None) -> None:
        """Initialize brilliant move detection analysis thread.
        
        Args:
            engine_path: Path to UCI engine executable.
            time_limit_ms: Maximum time per position in milliseconds.
            max_threads: Maximum number of CPU threads/cores to use (None = use engine default).
            engine_name: Name of the engine for progress reporting.
            engine_options: Dictionary of engine-specific options to set (e.g., {"Hash": 64, "Ponder": False}).
        """
        super().__init__()
        self.engine_path = engine_path
        self.time_limit_ms = time_limit_ms
        self.max_threads = max_threads
        self.engine_name = engine_name
        self.engine_options = engine_options or {}
        self.uci: Optional[UCICommunicationService] = None
        self.running = False
        self._stop_requested = False
        self._stop_current_analysis = False
        self._analysis_queue: queue.Queue = queue.Queue()
        self._current_request: Optional[BrilliantMoveDetectionRequest] = None
        self._current_depth = 0
        self._current_seldepth = 0
        self._best_score: Optional[float] = None
        self._best_is_mate = False
        self._best_mate_moves = 0
        self._best_move_uci: Optional[str] = None
        self._best_pv: str = ""
        self._is_black_to_move = False
        self._start_time = 0.0
        self._current_nps: int = 0
    
    def queue_analysis(self, request: BrilliantMoveDetectionRequest) -> None:
        """Queue a position for analysis.
        
        Args:
            request: BrilliantMoveDetectionRequest with position details.
        """
        self._analysis_queue.put(request)
    
    def stop_current_analysis(self) -> None:
        """Stop only the current analysis without clearing queue or stopping thread."""
        # Set flag to break out of current _analyze_position loop
        self._stop_current_analysis = True
        # Stop current search
        if self.uci and self.uci.is_process_alive():
            self.uci.stop_search()
    
    def stop(self) -> None:
        """Stop current analysis and clear queue."""
        self._stop_requested = True
        # Clear queue
        while not self._analysis_queue.empty():
            try:
                self._analysis_queue.get_nowait()
            except queue.Empty:
                break
        # Stop current search
        if self.uci and self.uci.is_process_alive():
            self.uci.stop_search()
    
    def shutdown(self) -> None:
        """Shutdown engine process.
        
        Sets flags to stop the thread. Cleanup will be handled by the thread's finally block.
        """
        self.running = False
        self._stop_requested = True
        # Clear queue
        while not self._analysis_queue.empty():
            try:
                self._analysis_queue.get_nowait()
            except queue.Empty:
                break
        # Note: cleanup() is called in run()'s finally block, not here
    
    def run(self) -> None:
        """Run engine analysis thread - processes queue of positions."""
        try:
            # Create UCI communication service
            self.uci = UCICommunicationService(
                self.engine_path, 
                identifier=f"BrilliantMoveDetection-{self.engine_name or 'Unknown'}"
            )
            
            # Spawn engine process
            if not self.uci.spawn_process():
                self.error_occurred.emit("Failed to spawn engine process")
                return
            
            # Initialize UCI
            success, _ = self.uci.initialize_uci(timeout=5.0)
            if not success:
                self.error_occurred.emit("Engine did not respond with uciok")
                return
            
            # Set UCI options (threads and engine-specific options) once
            if self.max_threads is not None:
                if not self.uci.set_option("Threads", self.max_threads, wait_for_ready=False):
                    self.error_occurred.emit("Failed to set Threads option")
                    return
            
            # Set engine-specific options (excluding Threads which is handled separately)
            for option_name, option_value in self.engine_options.items():
                if option_name != "Threads" and option_name != "MultiPV":
                    self.uci.set_option(option_name, option_value, wait_for_ready=False)
            
            # Confirm engine is ready after setting all options
            if not self.uci.confirm_ready():
                self.error_occurred.emit("Engine did not respond with readyok after setting options")
                return
            
            self.running = True
            
            # Process analysis queue
            while self.running and not self._stop_requested:
                try:
                    # Get next analysis request (with timeout to allow checking stop flag)
                    try:
                        request = self._analysis_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    
                    if request is None:  # Sentinel value to stop
                        break
                    
                    self._current_request = request
                    # Reset stop flag before starting new analysis
                    self._stop_current_analysis = False
                    self._analyze_position(request)
                    self._current_request = None
                    
                except Exception as e:
                    self.error_occurred.emit(f"Error processing analysis queue: {str(e)}")
                    break
            
            # Note: cleanup is handled in finally block below
        
        except Exception as e:
            self.error_occurred.emit(f"Error in analysis thread: {str(e)}")
        finally:
            self.running = False
            if self.uci:
                self.uci.cleanup()
    
    def _analyze_position(self, request: BrilliantMoveDetectionRequest) -> None:
        """Analyze a single position at shallow depth.
        
        Args:
            request: BrilliantMoveDetectionRequest with position details.
        """
        try:
            self._start_time = time.time() * 1000.0  # milliseconds
            
            # Reset analysis state
            self._current_depth = 0
            self._current_seldepth = 0
            self._best_score = None
            self._best_is_mate = False
            self._best_mate_moves = 0
            self._best_move_uci = None
            self._best_pv = ""
            self._current_nps = 0
            
            # Parse FEN to determine side to move
            import chess
            try:
                board = chess.Board(request.fen)
                self._is_black_to_move = not board.turn
            except Exception:
                self._is_black_to_move = False
            
            # Set position
            if not self.uci.set_position(request.fen):
                self.error_occurred.emit("Failed to set position")
                return
            
            # Start analysis at shallow depth
            if not self.uci.start_search(depth=request.shallow_depth, movetime=self.time_limit_ms):
                self.error_occurred.emit("Failed to start search")
                return
            
            # Read analysis output
            while not self._stop_requested and not self._stop_current_analysis:
                if not self.uci.is_process_alive():
                    self.error_occurred.emit("Engine process terminated unexpectedly")
                    break
                
                # Read a line (non-blocking with short timeout)
                line = self.uci.read_line(timeout=0.01)
                
                if not line:
                    time.sleep(0.01)
                    continue
                
                # Parse info lines
                if line.startswith("info"):
                    self._parse_info_line(line)
                
                # Check for bestmove (analysis complete)
                elif line.startswith("bestmove"):
                    # If we've been asked to stop current analysis, ignore this result
                    if self._stop_current_analysis:
                        break
                    
                    parts = line.split()
                    if len(parts) >= 2:
                        self._best_move_uci = parts[1]
                    
                    # Convert best move to SAN
                    best_move_san = ""
                    if self._best_move_uci and self._best_move_uci != "(none)":
                        try:
                            board = chess.Board(request.fen)
                            move = chess.Move.from_uci(self._best_move_uci)
                            if move in board.legal_moves:
                                best_move_san = board.san(move)
                        except Exception:
                            best_move_san = self._best_move_uci
                    
                    # Emit final result
                    if self._best_score is not None:
                        final_score = self._best_score
                        final_is_mate = self._best_is_mate
                        final_mate_moves = self._best_mate_moves
                    else:
                        # No score received - use 0.0 as neutral score
                        final_score = 0.0
                        final_is_mate = False
                        final_mate_moves = 0
                    
                    self.analysis_complete.emit(
                        final_score,
                        final_is_mate,
                        final_mate_moves,
                        best_move_san,
                        request.shallow_depth
                    )
                    break
        
        except Exception as e:
            self.error_occurred.emit(f"Error analyzing position: {str(e)}")
    
    def _parse_info_line(self, line: str) -> None:
        """Parse UCI info line and update analysis state.
        
        Args:
            line: UCI info line string.
        """
        try:
            # Extract depth
            depth_match = None
            for part in line.split():
                if part.startswith("depth"):
                    try:
                        depth_idx = line.split().index("depth")
                        if depth_idx + 1 < len(line.split()):
                            self._current_depth = int(line.split()[depth_idx + 1])
                    except (ValueError, IndexError):
                        pass
                    break
            
            # Extract seldepth
            for part in line.split():
                if part.startswith("seldepth"):
                    try:
                        seldepth_idx = line.split().index("seldepth")
                        if seldepth_idx + 1 < len(line.split()):
                            self._current_seldepth = int(line.split()[seldepth_idx + 1])
                    except (ValueError, IndexError):
                        pass
                    break
            
            # Extract score (cp or mate)
            if "score cp" in line:
                try:
                    cp_idx = line.split().index("cp")
                    if cp_idx + 1 < len(line.split()):
                        cp_value = int(line.split()[cp_idx + 1])
                        # Flip score for black to move
                        if self._is_black_to_move:
                            cp_value = -cp_value
                        self._best_score = float(cp_value)
                        self._best_is_mate = False
                        self._best_mate_moves = 0
                except (ValueError, IndexError):
                    pass
            elif "score mate" in line:
                try:
                    mate_idx = line.split().index("mate")
                    if mate_idx + 1 < len(line.split()):
                        mate_moves = int(line.split()[mate_idx + 1])
                        # Flip mate moves for black to move
                        if self._is_black_to_move:
                            mate_moves = -mate_moves
                        self._best_is_mate = True
                        self._best_mate_moves = mate_moves
                        # Convert mate to centipawns (use large value)
                        if mate_moves > 0:
                            self._best_score = 10000.0 - abs(mate_moves) * 100.0
                        else:
                            self._best_score = -10000.0 + abs(mate_moves) * 100.0
                except (ValueError, IndexError):
                    pass
            
            # Extract nps
            if "nps" in line:
                try:
                    nps_idx = line.split().index("nps")
                    if nps_idx + 1 < len(line.split()):
                        self._current_nps = int(line.split()[nps_idx + 1])
                except (ValueError, IndexError):
                    pass
            
            # Extract PV (principal variation)
            if "pv" in line:
                try:
                    pv_idx = line.split().index("pv")
                    if pv_idx + 1 < len(line.split()):
                        pv_parts = line.split()[pv_idx + 1:]
                        self._best_pv = " ".join(pv_parts)
                        # Extract first move as best move if not already set
                        if not self._best_move_uci and len(pv_parts) > 0:
                            self._best_move_uci = pv_parts[0]
                except (ValueError, IndexError):
                    pass
        
        except Exception as e:
            # Silently ignore parsing errors for individual info lines
            pass


class BrilliantMoveDetectionAnalysisService(QObject):
    """Service for managing brilliant move detection analysis engine operations."""
    
    def __init__(self, engine_path: Path, time_limit_ms: int,
                 max_threads: Optional[int] = None, engine_name: str = "", engine_options: Optional[Dict[str, Any]] = None, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize brilliant move detection analysis engine service.
        
        Args:
            engine_path: Path to UCI engine executable.
            time_limit_ms: Maximum time per position in milliseconds.
            max_threads: Maximum number of CPU threads/cores to use.
            engine_name: Name of the engine.
            engine_options: Dictionary of engine-specific options to set (e.g., {"Hash": 64, "Ponder": False}).
            config: Optional configuration dictionary.
        """
        super().__init__()
        self.engine_path = engine_path
        self.time_limit_ms = time_limit_ms
        self.max_threads = max_threads
        self.engine_name = engine_name
        self.engine_options = engine_options or {}
        self.config = config
        self.analysis_thread: Optional[BrilliantMoveDetectionAnalysisThread] = None
    
    def start_engine(self) -> bool:
        """Start the persistent analysis thread.
        
        Returns:
            True if thread started successfully, False otherwise.
        """
        if self.analysis_thread and self.analysis_thread.isRunning():
            return True
        
        # Create new thread
        self.analysis_thread = BrilliantMoveDetectionAnalysisThread(
            self.engine_path,
            self.time_limit_ms,
            self.max_threads,
            self.engine_name,
            self.engine_options
        )
        
        # Start thread
        self.analysis_thread.start()
        
        # Wait for thread to initialize engine (check if running flag is set)
        # Use processEvents() to keep UI responsive while waiting
        from PyQt6.QtWidgets import QApplication
        start_time = time.time()
        timeout = 10.0  # Increased timeout for slow host environments
        
        while not self.analysis_thread.running and (time.time() - start_time) < timeout:
            if not self.analysis_thread.isRunning():
                return False
            
            # Process Qt events to keep UI responsive
            QApplication.processEvents()
            time.sleep(0.05)  # Reduced sleep time, events are processed above
        
        # Log engine thread started
        if self.analysis_thread.running:
            logging_service = LoggingService.get_instance()
            options_str = f", options={self.engine_options}" if self.engine_options else ""
            logging_service.info(f"Brilliant move detection engine thread started: engine={self.engine_name}, path={self.engine_path}, threads={self.max_threads}, movetime={self.time_limit_ms}ms{options_str}")
        
        return self.analysis_thread.running
    
    def analyze_position(self, fen: str, move_number: int, shallow_depth: int) -> BrilliantMoveDetectionAnalysisThread:
        """Queue a position for analysis at shallow depth.
        
        Args:
            fen: FEN string of position to analyze.
            move_number: Move number for progress reporting.
            shallow_depth: Depth to analyze (2-6).
            
        Returns:
            BrilliantMoveDetectionAnalysisThread instance (for signal connections).
        """
        # Start engine thread if not already running
        if not self.analysis_thread or not self.analysis_thread.isRunning():
            if not self.start_engine():
                return None
        
        # Create analysis request
        request = BrilliantMoveDetectionRequest(fen, move_number, shallow_depth)
        
        # Queue for analysis
        self.analysis_thread.queue_analysis(request)
        
        return self.analysis_thread
    
    def stop_current_analysis(self) -> None:
        """Stop only the current analysis without clearing queue or stopping thread."""
        if self.analysis_thread and self.analysis_thread.isRunning():
            self.analysis_thread.stop_current_analysis()
    
    def stop_analysis(self) -> None:
        """Stop current analysis and clear queue."""
        if self.analysis_thread and self.analysis_thread.isRunning():
            self.analysis_thread.stop()
    
    def shutdown(self) -> None:
        """Shutdown engine process and thread."""
        if self.analysis_thread:
            # Log engine thread shutdown
            logging_service = LoggingService.get_instance()
            logging_service.info(f"Brilliant move detection engine thread shutdown: engine={self.engine_name}")
            
            # Store reference to thread for cleanup
            thread = self.analysis_thread
            
            # Set flags to stop the thread, it will exit naturally and cleanup in finally block
            if thread.isRunning():
                thread.shutdown()
            
            # Wait for thread to finish before deleting (prevents Qt crash)
            # The thread should exit quickly once flags are set and it checks them in the loop
            # UCI cleanup can take up to ~2 seconds, so wait a bit longer
            if thread.isRunning():
                # Wait for thread to finish (with timeout to prevent indefinite blocking)
                if thread.wait(3000):  # Wait up to 3 seconds (allows time for UCI cleanup)
                    # Thread finished, safe to delete
                    self.analysis_thread = None
                else:
                    # Thread still running after timeout - schedule deletion
                    # Since thread has parent (this service), Qt will maintain reference and delete when safe
                    thread.deleteLater()
                    self.analysis_thread = None  # Clear our reference, Qt will handle deletion
            else:
                # Thread not running, safe to delete immediately
                self.analysis_thread = None
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        self.shutdown()
