"""Evaluation engine service for continuous UCI engine evaluation."""

import time
from pathlib import Path
from typing import Optional, Dict, Any
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from app.services.uci_communication_service import UCICommunicationService
from app.services.logging_service import LoggingService


class EvaluationEngineThread(QThread):
    """Thread for communicating with UCI engine for continuous evaluation."""
    
    score_update = pyqtSignal(float, bool, int, int, int, int, str)  # centipawns, is_mate, mate_moves, depth, nps, hashfull (-1 for not available), pv (empty string for not available)
    error_occurred = pyqtSignal(str)  # error_message
    
    def __init__(self, engine_path: Path, max_depth: int = 40, update_interval_ms: int = 100, 
                 max_threads: Optional[int] = None, engine_options: Optional[Dict[str, Any]] = None, 
                 movetime: int = 0) -> None:
        """Initialize evaluation engine thread.
        
        Args:
            engine_path: Path to UCI engine executable.
            max_depth: Maximum depth to search (default 40, 0 = unlimited).
            update_interval_ms: Minimum time between updates in milliseconds (default 100ms = 10 updates/sec).
            max_threads: Maximum number of CPU threads/cores to use (None = use engine default).
            engine_options: Dictionary of engine-specific options to set (e.g., {"Hash": 64, "Ponder": False}).
            movetime: Maximum time per move in milliseconds (0 = unlimited).
        """
        super().__init__()
        self.engine_path = engine_path
        self.max_depth = max_depth
        self.update_interval_ms = update_interval_ms
        self.max_threads = max_threads
        self.engine_options = engine_options or {}
        self.movetime = movetime
        self.uci: Optional[UCICommunicationService] = None
        self.running = False
        self.current_fen: Optional[str] = None
        self._last_sent_fen: Optional[str] = None  # Track last FEN sent to engine
        self._go_sent_after_position = False  # Track if go depth was sent after current position
        self._stop_requested = False
        self._suspended = False  # Flag to indicate thread is suspended (keeps run loop alive)
        self._is_black_to_move = False  # Track side to move for evaluation flipping
        self._last_update_time = 0.0  # Track last signal emission time for throttling
        self._pending_update: Optional[tuple[float, bool, int, int, int, int, str]] = None
        self._current_depth = 0
        self._best_score: Optional[float] = None
        self._best_is_mate = False
        self._best_mate_moves = 0
        self._current_nps: int = -1
        self._current_hashfull: int = -1
        self._current_pv: str = ""
        self._max_pv_moves: int = 5
    
    def start_evaluation(self, fen: str) -> None:
        """Start evaluation for a position.
        
        Args:
            fen: FEN string of position to evaluate.
        """
        self.current_fen = fen
        if not self.running:
            self.start()
        else:
            # Update position if already running
            self._update_position(fen)
    
    def stop_evaluation(self) -> None:
        """Stop current evaluation."""
        self._stop_requested = True
        self._suspended = False  # Clear suspended flag when stopping
        if self.uci and self.uci.is_process_alive():
            self.uci.stop_search()
    
    def suspend(self) -> None:
        """Suspend evaluation (stop search but keep run loop alive)."""
        self._suspended = True
        # Keep running = True so the run loop continues
        # Don't set running = False, just set _suspended = True
        if self.uci and self.uci.is_process_alive():
            self.uci.stop_search()
    
    def resume(self, fen: str) -> None:
        """Resume evaluation (restart search).
        
        Raises:
            RuntimeError: If process is not alive or UCI is not initialized.
        """
        self._suspended = False
        # Check if process is still alive before resuming
        if not self.uci or not self.uci.is_process_alive():
            # Process has died - raise error so caller can create new thread
            raise RuntimeError("Engine process terminated unexpectedly")
        
        if not self.uci.is_initialized():
            # UCI not initialized - raise error so caller can create new thread
            raise RuntimeError("Engine not initialized when resuming")
        
        # Reset tracking flags to force restart of search
        self._go_sent_after_position = False
        self._last_sent_fen = None  # Reset to force position update
        self.current_fen = fen
        # Ensure engine is ready before resuming
        if not self.uci.confirm_ready():
            # Engine not ready - raise error so caller can create new thread
            raise RuntimeError("Engine not ready when resuming")
        # Update position and restart search
        self._update_position(fen)
    
    def shutdown(self) -> None:
        """Shutdown engine process."""
        self.running = False
        self._stop_requested = True
        if self.uci:
            self.uci.cleanup()
    
    def _update_position(self, fen: str) -> None:
        """Update engine position.
        
        Args:
            fen: FEN string of new position.
        """
        if not self.uci or not self.uci.is_process_alive():
            return
        
        try:
            # Parse FEN to determine side to move
            import chess
            try:
                board = chess.Board(fen)
                self._is_black_to_move = not board.turn  # board.turn is True for White
            except Exception:
                # If FEN parsing fails, default to White
                self._is_black_to_move = False
            
            # Check if position is the same as last sent position
            if fen == self._last_sent_fen:
                # Same position - only send go infinite if we haven't sent it yet
                if not self._go_sent_after_position:
                    # Use infinite search (depth=0) for continuous evaluation
                    if not self.uci.start_search(depth=0, movetime=self.movetime):
                        self.error_occurred.emit("Failed to start search")
                        return
                    self._go_sent_after_position = True
                # No need to update current_fen or reset tracking - position hasn't changed
                return
            
            # Different position - send stop, then position, then go infinite
            # Stop current search
            self.uci.stop_search()
            
            # Small delay to allow engine to process stop command
            time.sleep(0.01)
            
            # Set new position
            if not self.uci.set_position(fen):
                self.error_occurred.emit("Failed to set position")
                return
            
            # Update tracking
            self._last_sent_fen = fen
            self.current_fen = fen
            self._go_sent_after_position = False  # Reset flag for new position
            
            # Start new search with infinite depth for continuous evaluation
            # depth=0 means infinite search (engine will keep analyzing until stopped)
            if not self.uci.start_search(depth=0, movetime=self.movetime):
                self.error_occurred.emit("Failed to start search")
                return
            
            self._go_sent_after_position = True
            
            # Reset depth tracking for new position
            self._current_depth = 0
            self._best_score = None
            self._best_is_mate = False
            self._best_mate_moves = 0
            self._current_nps = -1
            self._current_hashfull = -1
            self._current_pv = ""
        except Exception as e:
            self.error_occurred.emit(f"Failed to update position: {str(e)}")
    
    def run(self) -> None:
        """Run engine communication thread."""
        try:
            # Create UCI communication service
            self.uci = UCICommunicationService(
                self.engine_path, 
                identifier="Evaluation"
            )
            
            # Spawn engine process
            if not self.uci.spawn_process():
                self.error_occurred.emit("Failed to spawn engine process")
                return
            
            # Initialize UCI protocol
            success, _ = self.uci.initialize_uci(timeout=5.0)
            if not success:
                self.error_occurred.emit("Engine did not respond with uciok")
                return
            
            # Set engine options
            # First set Threads if configured
            if self.max_threads is not None:
                if not self.uci.set_option("Threads", self.max_threads, wait_for_ready=False):
                    self.error_occurred.emit("Failed to set Threads option")
                    return
            
            # Set engine-specific options (excluding Threads which is handled separately)
            for option_name, option_value in self.engine_options.items():
                if option_name != "Threads":
                    self.uci.set_option(option_name, option_value, wait_for_ready=False)
            
            # Confirm engine is ready after setting all options
            if not self.uci.confirm_ready():
                self.error_occurred.emit("Engine did not respond with readyok after setting options")
                return
            
            # Set initial position and start evaluation
            # Check current_fen (may have been updated while thread was starting)
            if self.current_fen:
                # Parse FEN to determine side to move
                import chess
                try:
                    board = chess.Board(self.current_fen)
                    self._is_black_to_move = not board.turn  # board.turn is True for White
                except Exception:
                    # If FEN parsing fails, default to White
                    self._is_black_to_move = False
                
                if not self.uci.set_position(self.current_fen):
                    self.error_occurred.emit("Failed to set position")
                    return
                
                # Update tracking
                self._last_sent_fen = self.current_fen
                self._go_sent_after_position = False
                
                # Start infinite search for continuous evaluation
                # depth=0 means infinite search (engine will keep analyzing until stopped)
                if not self.uci.start_search(depth=0, movetime=self.movetime):
                    self.error_occurred.emit("Failed to start search")
                    return
                
                self._go_sent_after_position = True
            
            self.running = True
            
            # Read evaluation lines
            while self.running and not self._stop_requested:
                # If suspended, just sleep and wait (don't process anything)
                # Don't check process alive when suspended - we'll check when resuming
                if self._suspended:
                    time.sleep(0.1)  # Sleep longer when suspended to reduce CPU usage
                    continue
                
                # Check if process is alive (only when not suspended)
                if not self.uci.is_process_alive():
                    # Process terminated unexpectedly
                    self.error_occurred.emit("Engine process terminated unexpectedly")
                    break
                
                # Read a line (non-blocking with short timeout)
                line = self.uci.read_line(timeout=0.01)
                
                if not line:
                    # Empty line - check if we have a pending update that should be emitted
                    if self._pending_update is not None:
                        current_time = time.time() * 1000.0  # Convert to milliseconds
                        time_since_last_update = current_time - self._last_update_time
                        if time_since_last_update >= self.update_interval_ms:
                            # Emit pending update
                            centipawns, is_mate, mate_moves, depth, nps, hashfull, pv = self._pending_update
                            self.score_update.emit(centipawns, is_mate, mate_moves, depth, nps, hashfull, pv)
                            self._last_update_time = current_time
                            self._pending_update = None
                    
                    # Small delay to avoid busy waiting
                    time.sleep(0.01)
                    continue
                
                line = line.strip()
                
                # Parse info lines for evaluation
                if line.startswith("info"):
                    # Parse depth
                    depth = self._parse_depth(line)
                    if depth is not None and depth > self._current_depth:
                        self._current_depth = depth
                    
                    # Parse nodes per second (nps) if available
                    nps = self._parse_nps(line)
                    if nps is not None:
                        self._current_nps = nps
                    
                    # Parse hash table usage (hashfull) if available
                    hashfull = self._parse_hashfull(line)
                    if hashfull is not None:
                        self._current_hashfull = hashfull
                    
                    # Parse principal variation (PV) if available
                    pv = self._parse_pv(line)
                    if pv is not None:
                        self._current_pv = pv
                    
                    # Parse score
                    score = self._parse_score(line)
                    if score is not None:
                        centipawns, is_mate, mate_moves = score
                        
                        # Update if we have a deeper search, mate score, or score change
                        should_update = False
                        if depth is not None:
                            if depth > self._current_depth:
                                # Deeper search - always update
                                self._current_depth = depth
                                should_update = True
                            elif depth == self._current_depth:
                                # Same depth - update if score changed or mate
                                if self._best_score is None or is_mate or centipawns != self._best_score:
                                    should_update = True
                        else:
                            # No depth info - update if score changed or mate
                            if self._best_score is None or is_mate or centipawns != self._best_score:
                                should_update = True
                        
                        if should_update:
                            self._best_score = centipawns
                            self._best_is_mate = is_mate
                            self._best_mate_moves = mate_moves
                            
                            # Flip evaluation if Black is to move and engine returns from side-to-move perspective
                            adjusted_centipawns = centipawns
                            adjusted_is_mate = is_mate
                            adjusted_mate_moves = mate_moves
                            
                            if self._is_black_to_move:
                                # Flip evaluation: if engine returns +1 for Black, it means Black is winning
                                # but we want to show from White's perspective, so flip to -1
                                adjusted_centipawns = -centipawns
                                if is_mate:
                                    adjusted_mate_moves = -mate_moves
                            
                            # Calculate depth
                            emit_depth = self._current_depth if self._current_depth > 0 else (depth if depth is not None else 0)
                            
                            # Throttle updates to avoid flooding the UI thread
                            nps_value = self._current_nps if self._current_nps >= 0 else -1
                            hashfull_value = self._current_hashfull if self._current_hashfull >= 0 else -1
                            pv_value = self._current_pv if self._current_pv else ""
                            self._pending_update = (adjusted_centipawns, adjusted_is_mate, adjusted_mate_moves, emit_depth, nps_value, hashfull_value, pv_value)
                            
                            # Check if enough time has passed since last update
                            current_time = time.time() * 1000.0  # Convert to milliseconds
                            time_since_last_update = current_time - self._last_update_time
                            
                            if time_since_last_update >= self.update_interval_ms:
                                # Emit update immediately
                                self.score_update.emit(adjusted_centipawns, adjusted_is_mate, adjusted_mate_moves, emit_depth, nps_value, hashfull_value, pv_value)
                                self._last_update_time = current_time
                                self._pending_update = None
                
                elif line.startswith("bestmove"):
                    # Search completed (usually after stop command or if movetime was set)
                    # For continuous evaluation with infinite search, we should never get here
                    # unless we sent stop or movetime expired
                    # If we get bestmove, it means the search stopped - don't restart automatically
                    # Position updates will handle restarting the search when needed
                    # Just continue reading - position updates will restart search if needed
                    pass
            
        except Exception as e:
            self.error_occurred.emit(f"Engine communication error: {str(e)}")
        finally:
            self.running = False
            # Clean up UCI communication service
            if self.uci:
                self.uci.cleanup()
    
    def _parse_depth(self, line: str) -> Optional[int]:
        """Parse depth from info line.
        
        Args:
            line: Info line from engine.
            
        Returns:
            Depth value or None if not found.
        """
        parts = line.split()
        try:
            if "depth" in parts:
                idx = parts.index("depth")
                if idx + 1 < len(parts):
                    return int(parts[idx + 1])
        except (ValueError, IndexError):
            pass
        return None
    
    def _parse_nps(self, line: str) -> Optional[int]:
        """Parse nodes per second from info line.
        
        Args:
            line: Info line from engine.
            
        Returns:
            Nodes per second or None if not found.
        """
        parts = line.split()
        try:
            if "nps" in parts:
                idx = parts.index("nps")
                if idx + 1 < len(parts):
                    return int(parts[idx + 1])
        except (ValueError, IndexError):
            pass
        return None
    
    def _parse_hashfull(self, line: str) -> Optional[int]:
        """Parse hash table usage from info line.
        
        Args:
            line: Info line from engine.
            
        Returns:
            Hash table usage (0-1000) or None if not found.
        """
        parts = line.split()
        try:
            if "hashfull" in parts:
                idx = parts.index("hashfull")
                if idx + 1 < len(parts):
                    return int(parts[idx + 1])
        except (ValueError, IndexError):
            pass
        return None
    
    def _parse_pv(self, line: str) -> Optional[str]:
        """Parse principal variation from info line and convert to algebraic notation.
        
        Args:
            line: Info line from engine.
            
        Returns:
            Principal variation as space-separated algebraic moves (limited to max_pv_moves) or None if not found.
        """
        parts = line.split()
        try:
            if "pv" in parts:
                pv_idx = parts.index("pv")
                # Get all moves after "pv" (everything from pv_idx + 1 onwards)
                pv_moves_uci = parts[pv_idx + 1:]
                if not pv_moves_uci or not self.current_fen:
                    return None
                
                # Limit to max_pv_moves for display
                limited_moves_uci = pv_moves_uci[:self._max_pv_moves]
                
                # Convert UCI moves to algebraic notation
                try:
                    import chess
                    board = chess.Board(self.current_fen)
                    pv_algebraic = []
                    
                    for uci_move in limited_moves_uci:
                        try:
                            # Parse UCI move (e.g., "e2e4")
                            move = chess.Move.from_uci(uci_move)
                            # Check if move is legal
                            if move in board.legal_moves:
                                # Convert to algebraic notation (e.g., "e4")
                                san_move = board.san(move)
                                pv_algebraic.append(san_move)
                                # Apply move to board for next move
                                board.push(move)
                            else:
                                # Invalid move - stop parsing
                                break
                        except (ValueError, chess.InvalidMoveError):
                            # Invalid UCI move format - stop parsing
                            break
                    
                    if pv_algebraic:
                        return " ".join(pv_algebraic)
                except Exception:
                    # If conversion fails, fall back to UCI notation
                    return " ".join(limited_moves_uci)
        except (ValueError, IndexError):
            pass
        return None
    
    def _parse_score(self, line: str) -> Optional[tuple[float, bool, int]]:
        """Parse score from info line.
        
        Args:
            line: Info line from engine.
            
        Returns:
            Tuple of (centipawns, is_mate, mate_moves) or None if not found.
        """
        parts = line.split()
        try:
            if "score" in parts:
                score_idx = parts.index("score")
                if score_idx + 1 < len(parts):
                    score_type = parts[score_idx + 1]
                    
                    if score_type == "cp":
                        # Centipawns score
                        if score_idx + 2 < len(parts):
                            centipawns = float(parts[score_idx + 2])
                            return (centipawns, False, 0)
                    
                    elif score_type == "mate":
                        # Mate score
                        if score_idx + 2 < len(parts):
                            mate_moves = int(parts[score_idx + 2])
                            # Positive = white mates, negative = black mates
                            # Use large centipawn value for mate
                            centipawns = 10000.0 if mate_moves > 0 else -10000.0
                            return (centipawns, True, mate_moves)
        except (ValueError, IndexError):
            pass
        return None


class EvaluationEngineService(QObject):
    """Service for managing continuous UCI engine evaluation."""
    
    evaluation_update = pyqtSignal(float, bool, int, int, int, int, str)  # centipawns, is_mate, mate_moves, depth, nps, hashfull (-1 for not available), pv (empty string for not available)
    error_occurred = pyqtSignal(str)  # error_message
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize evaluation engine service.
        
        Args:
            config: Configuration dictionary.
        """
        super().__init__()
        self.config = config
        self.evaluation_thread: Optional[EvaluationEngineThread] = None
        self.current_engine_path: Optional[Path] = None
        eval_bar_config = config.get("ui", {}).get("panels", {}).get("main", {}).get("board", {}).get("evaluation_bar", {})
        self.max_depth = eval_bar_config.get("max_depth_evaluation", 40)
        self.update_interval_ms = eval_bar_config.get("update_interval_ms", 100)  # Default 100ms = 10 updates/sec
        max_threads_value = eval_bar_config.get("max_threads", None)
        # JSON null loads as Python None, so check for None and convert to int otherwise
        self.max_threads = None if max_threads_value is None else int(max_threads_value)
    
    def start_evaluation(self, engine_path: Path, fen: str) -> bool:
        """Start evaluation for a position.
        
        Args:
            engine_path: Path to UCI engine executable.
            fen: FEN string of position to evaluate.
            
        Returns:
            True if evaluation started, False otherwise.
        """
        # Check if thread already exists and is running with the same engine
        if self.evaluation_thread and self.current_engine_path == engine_path:
            # First check if thread is suspended - if so, resume it
            if hasattr(self.evaluation_thread, '_suspended') and self.evaluation_thread._suspended:
                # Thread is suspended - check if process is still alive
                if self.is_thread_valid() and not self.evaluation_thread.isFinished():
                    # Process is alive - try to resume it
                    try:
                        self.evaluation_thread.resume(fen)
                        self.evaluation_thread.running = True  # Set running flag
                        return True
                    except Exception:
                        # Resume failed - process might have died, create new thread
                        old_thread = self.evaluation_thread
                        self.evaluation_thread = None
                        # Fall through to create new thread
                else:
                    # Thread is finished or process died - clean up and create new one
                    old_thread = self.evaluation_thread
                    self.evaluation_thread = None
                    # Fall through to create new thread
            
            # Check if thread is actively running (not suspended)
            if self.evaluation_thread and self.evaluation_thread.running and not (hasattr(self.evaluation_thread, '_suspended') and self.evaluation_thread._suspended):
                # Thread exists and is running with same engine - just update position
                self.update_position(fen)
                return True
            
            # Check if thread is starting up
            if self.evaluation_thread and self.evaluation_thread.isRunning() and self.evaluation_thread.uci and self.evaluation_thread.uci.is_initialized():
                # Thread is starting up - just update position
                self.update_position(fen)
                return True
            
            # Thread exists but not running - check if it's still valid (process alive)
            if self.evaluation_thread and self.is_thread_valid():
                # Thread is valid but not running - try to resume it
                if not self.evaluation_thread.isFinished():
                    # Thread is still running but not in "running" state - resume it
                    self.evaluation_thread.resume(fen)
                    self.evaluation_thread.running = True  # Set running flag
                    return True
                else:
                    # Thread is finished but process is still alive - we can't reuse the thread
                    # Clean up the old thread reference and create a new one
                    old_thread = self.evaluation_thread
                    self.evaluation_thread = None
                    # Fall through to create new thread
        
        # Stop existing evaluation if running (different engine or thread not valid)
        self.stop_evaluation()
        
        # Get task-specific parameters for this engine (with fallback to config.json)
        from app.services.engine_parameters_service import EngineParametersService
        task_params = EngineParametersService.get_task_parameters_for_engine(
            engine_path,
            "evaluation",
            self.config
        )
        
        # Use task-specific parameters if available, otherwise use config.json defaults
        max_depth = task_params.get("depth", self.max_depth)
        max_threads = task_params.get("threads", self.max_threads)
        movetime = task_params.get("movetime", 0)
        
        # Extract engine-specific options (all keys except common parameters)
        engine_options = {}
        for key, value in task_params.items():
            if key not in ["threads", "depth", "movetime"]:
                engine_options[key] = value
        
        # Create and start new evaluation thread
        self.current_engine_path = engine_path
        self.evaluation_thread = EvaluationEngineThread(engine_path, max_depth, self.update_interval_ms, max_threads, engine_options, movetime)
        self.evaluation_thread.score_update.connect(self.evaluation_update.emit)
        self.evaluation_thread.error_occurred.connect(self.error_occurred.emit)
        self.evaluation_thread.start_evaluation(fen)
        
        # Log evaluation engine started
        logging_service = LoggingService.get_instance()
        options_str = f", options={engine_options}" if engine_options else ""
        logging_service.info(f"Evaluation engine started: path={engine_path}, depth={max_depth}, threads={max_threads}, movetime={movetime}ms{options_str}")
        
        return True
    
    def update_position(self, fen: str) -> None:
        """Update evaluation position.
        
        Args:
            fen: FEN string of new position.
        """
        if self.evaluation_thread:
            # Thread exists - always try to update position, never restart
            # Check if thread is running or if UCI is initialized (thread might be starting)
            if self.evaluation_thread.running:
                # Thread is running - update position directly
                self.evaluation_thread._update_position(fen)
            elif self.evaluation_thread.isRunning() and self.evaluation_thread.uci and self.evaluation_thread.uci.is_initialized():
                # Thread is starting but UCI is initialized - can update position directly
                self.evaluation_thread._update_position(fen)
            elif self.evaluation_thread.isRunning():
                # Thread is starting up but UCI not initialized yet - just update current_fen
                # The thread will pick it up when it initializes
                self.evaluation_thread.current_fen = fen
            else:
                # Thread exists but not running/starting - just update current_fen
                # Don't restart - let the thread handle it when it's ready
                self.evaluation_thread.current_fen = fen
        elif self.current_engine_path:
            # No thread exists - start new evaluation
            self.start_evaluation(self.current_engine_path, fen)
    
    def stop_evaluation(self) -> None:
        """Stop current evaluation."""
        if self.evaluation_thread:
            # Log evaluation engine stopped
            logging_service = LoggingService.get_instance()
            logging_service.info(f"Evaluation engine stopped: path={self.current_engine_path}")
            
            # Set flags to stop the thread, it will exit naturally and cleanup in finally block
            self.evaluation_thread.stop_evaluation()
            self.evaluation_thread.shutdown()
            # Don't wait - let thread exit naturally, cleanup will happen in finally block
            self.evaluation_thread = None
    
    def suspend_evaluation(self) -> None:
        """Suspend evaluation without shutting down the engine process.
        
        This is used when switching to manual analysis with the same engine,
        allowing the evaluation thread to be resumed later.
        """
        if self.evaluation_thread:
            self.evaluation_thread.suspend()
            # Don't call shutdown() - keep the engine process alive and run loop running
    
    def is_thread_valid(self) -> bool:
        """Check if the evaluation thread is still valid (process alive and initialized).
        
        Returns:
            True if thread exists and its engine process is still alive and initialized.
        """
        if not self.evaluation_thread:
            return False
        
        if not self.evaluation_thread.uci:
            return False
        
        return (self.evaluation_thread.uci.is_process_alive() and 
                self.evaluation_thread.uci.is_initialized())
    
    def set_max_depth(self, max_depth: int) -> None:
        """Set maximum evaluation depth.
        
        Args:
            max_depth: Maximum depth value.
        """
        self.max_depth = max_depth
        if self.evaluation_thread:
            self.evaluation_thread.max_depth = max_depth
