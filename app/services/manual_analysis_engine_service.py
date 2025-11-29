"""Manual analysis engine service for continuous UCI engine analysis with multipv support."""

import re
import sys
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer

from app.services.uci_communication_service import UCICommunicationService

# Try to import psutil for process tree killing (optional dependency)
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None


class ManualAnalysisEngineThread(QThread):
    """Thread for communicating with UCI engine for manual analysis with multipv support."""
    
    line_update = pyqtSignal(int, float, bool, int, int, int, int, str)  # multipv, centipawns, is_mate, mate_moves, depth, nps, hashfull (-1 for not available), pv (empty string for not available)
    error_occurred = pyqtSignal(str)  # error_message
    
    def __init__(self, engine_path: Path, multipv: int = 1, update_interval_ms: int = 100, max_threads: Optional[int] = None, engine_options: Optional[Dict[str, Any]] = None, max_depth: int = 0, movetime: int = 0) -> None:
        """Initialize manual analysis engine thread.
        
        Args:
            engine_path: Path to UCI engine executable.
            multipv: Number of analysis lines to compute (default 1).
            update_interval_ms: Minimum time between updates in milliseconds (default 100ms = 10 updates/sec).
            max_threads: Maximum number of CPU threads/cores to use (None = use engine default).
            engine_options: Dictionary of engine-specific options to set (e.g., {"Hash": 64, "Ponder": False}).
            max_depth: Maximum depth to search (0 = unlimited).
            movetime: Maximum time per move in milliseconds (0 = unlimited).
        """
        super().__init__()
        self.engine_path = engine_path
        self.multipv = multipv
        self.update_interval_ms = update_interval_ms
        self.max_threads = max_threads
        self.engine_options = engine_options or {}
        self.max_depth = max_depth
        self.movetime = movetime
        self.uci: Optional[UCICommunicationService] = None
        self.running = False
        self.current_fen: Optional[str] = None
        self._stop_requested = False
        # Thread identification for debugging
        self._thread_id = id(self)  # Unique instance ID
        self._os_thread_id: Optional[int] = None  # OS thread ID (set in run())
        self._is_black_to_move = False  # Track side to move for evaluation flipping
        self._last_update_time: Dict[int, float] = {}  # Track last signal emission time per multipv for throttling
        self._pending_updates: Dict[int, tuple[float, bool, int, int, int, int, str]] = {}  # Pending updates per multipv
        self._seen_explicit_multipv: bool = False  # Track if we've seen explicit multipv lines after restart
        self._pending_lines_without_multipv: list = []  # Queue for lines without explicit multipv after restart
        self._next_multipv_to_assign: int = 1  # Next multipv to assign to lines without explicit multipv
        self._updating_multipv: bool = False  # Flag to track if we're in the middle of a multipv change
        self._current_nps: int = -1  # Current nodes per second (-1 = not available)
        self._current_hashfull: int = -1  # Current hash table usage (0-1000, -1 = not available)
        self._max_pv_moves: int = 50  # Maximum number of PV moves for manual analysis view (status bar will truncate separately)
        self._position_update_lock = threading.Lock()  # Lock to prevent concurrent position updates
        self._pending_position_update: Optional[str] = None  # Queue for pending position updates
        self._updating_position = False  # Flag to track if position update is in progress
        self._readyok_event = threading.Event()  # Event to signal when readyok is received
    
    def _thread_info(self) -> str:
        """Get thread identification string for debugging."""
        os_id = f"os={self._os_thread_id}" if self._os_thread_id is not None else "os=?"
        return f"inst={self._thread_id} {os_id}"
    
    def _kill_process_tree(self, pid: int) -> bool:
        """Kill the full process tree for a given PID using psutil.
        
        Args:
            pid: Process ID to kill.
            
        Returns:
            True if successful, False otherwise.
        """
        if not PSUTIL_AVAILABLE:
            return False
        
        try:
            parent = psutil.Process(pid)
            # Get all children recursively
            children = parent.children(recursive=True)
            
            if not children:
                # Fallback: Try to find processes by name (in case children are detached)
                try:
                    parent_name = parent.name()
                    for proc in psutil.process_iter(['pid', 'name']):
                        try:
                            proc_info = proc.info
                            if proc_info['name'] == parent_name and proc_info['pid'] != pid:
                                try:
                                    proc.kill()
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    pass
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass  # Process may have exited between iterations
                except Exception:
                    pass
            
            # Kill all children first
            for child in children:
                try:
                    child.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Wait a bit for children to die
            gone, still_alive = psutil.wait_procs(children, timeout=1.0)
            if still_alive:
                # Force kill any remaining children
                for child in still_alive:
                    try:
                        child.kill()
                    except Exception:
                        pass
            
            # Kill the parent process
            try:
                parent.kill()
                return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False
        except psutil.NoSuchProcess:
            return False
        except Exception:
            return False
    
    def start_analysis(self, fen: str) -> None:
        """Start analysis for a position.
        
        Args:
            fen: FEN string of position to analyze.
        """
        self.current_fen = fen
        if not self.running:
            self.start()
        else:
            # Update position if already running
            self._update_position(fen)
    
    def stop_analysis(self) -> None:
        """Stop current analysis cleanly."""
        # Set running to False FIRST to prevent any new updates from being processed
        self.running = False
        self._stop_requested = True
        # Clear multipv update flag to prevent bestmove handler from interfering
        self._updating_multipv = False
        # Clear pending updates to prevent them from being emitted after stopping
        self._pending_updates.clear()
        self._last_update_time.clear()
        # Also clear any pending position updates
        with self._position_update_lock:
            self._pending_position_update = None
        
        if not self.uci:
            return
        
        # Store PID NOW before any commands are sent (so we can kill tree even if parent exits)
        stored_pid = self.uci.get_process_pid()
        
        # Reset readyok event before sending isready
        self._readyok_event.clear()
        
        # Step 1: Send UCI "stop" command to halt the current search
        if self.uci and self.uci.is_process_alive():
            self.uci.stop_search()
        
        # Step 1.5: Kill process tree IMMEDIATELY while process is still alive
        # This ensures we can find and kill all child processes before parent exits
        tree_killed = False
        process_exited = False
        if stored_pid and self.uci and self.uci.is_process_alive():
            # Kill the process tree now, while the parent is still alive
            if self._kill_process_tree(stored_pid):
                tree_killed = True
                # Check if process is now dead
                if not self.uci.is_process_alive():
                    process_exited = True
        
        # Step 2: Send "isready" to force engine to flush internal state and confirm it's idle
        # Skip if process tree was already killed
        isready_timeout = False
        if not tree_killed and self.uci and self.uci.is_process_alive():
            try:
                self.uci.send_command("isready")
                # Wait for readyok (with timeout)
                if not self._readyok_event.wait(timeout=5.0):
                    isready_timeout = True
            except Exception:
                pass
        
        # Step 3: Send "quit" to gracefully shut down the engine and all its child processes
        # Only send if process is still alive
        # Skip if process tree was already killed
        quit_sent = False
        process_exited = False
        
        if not tree_killed and self.uci and self.uci.is_process_alive():
            try:
                self.uci.quit_engine()
                quit_sent = True
                
                # Wait for the engine process to exit after quit
                # The engine should exit gracefully after receiving quit
                if self.uci.wait_for_process(timeout=3.0):
                    process_exited = True
            except Exception:
                pass
        else:
            # If process already exited, mark as exited
            if self.uci and not self.uci.is_process_alive():
                process_exited = True
        
        # Step 3.5: Fallback - Safety check: Try to kill process tree if it wasn't already killed and process is still running
        if not tree_killed and stored_pid and self.uci:
            if self.uci.is_process_alive():
                # Process is still running - try to kill it
                if self._kill_process_tree(stored_pid):
                    process_exited = True
        
        # Step 4: Cleanup UCI communication service
        if self.uci:
            self.uci.cleanup()
    
    def shutdown(self) -> None:
        """Shutdown engine process."""
        self.running = False
        self._stop_requested = False
        if self.uci:
            self.uci.cleanup()
    
    def set_multipv(self, multipv: int) -> None:
        """Set number of analysis lines (multipv).
        
        Args:
            multipv: Number of lines to analyze (1-based, minimum 1).
        """
        if multipv < 1:
            multipv = 1
        
        # Always update multipv and trigger position update if running
        # This ensures the engine restarts analysis with the new multipv value
        old_multipv = self.multipv
        
        # Update multipv BEFORE calling _update_position_with_multipv_change
        # This ensures the engine gets the correct multipv value when we send setoption
        self.multipv = multipv
        
        # If multipv changed and we're running, update position with new multipv
        # This will restart the engine search with the new multipv value
        if old_multipv != multipv and self.running and self.current_fen:
            self._update_position_with_multipv_change(self.current_fen)
    
    def _update_position_with_multipv_change(self, fen: str) -> None:
        """Update engine position with multipv change (forces update even if FEN is same).
        
        Args:
            fen: FEN string of position.
        """
        # Set flag to prevent bestmove handler from restarting search prematurely
        self._updating_multipv = True
        
        # Use lock to prevent concurrent position updates
        with self._position_update_lock:
            # If update is in progress, wait for it to complete
            if self._updating_position:
                self._pending_position_update = fen
                return
            
            # Mark as updating
            self._updating_position = True
        
        # Do the actual update outside the lock to avoid blocking
        try:
            # Check if process is alive before attempting update
            if not self.uci:
                self.error_occurred.emit("Engine process not initialized")
                return
            
            if not self.uci.is_process_alive():
                # Process has terminated
                self.error_occurred.emit("Engine process terminated unexpectedly")
                return
            
            if self.uci and self.uci.is_process_alive():
                # Parse FEN to determine side to move
                import chess
                try:
                    board = chess.Board(fen)
                    self._is_black_to_move = not board.turn  # board.turn is True for White
                except Exception:
                    # If FEN parsing fails, default to White
                    self._is_black_to_move = False
                
                # Stop current search - MUST send stop before position change (UCI protocol)
                # This ensures the engine halts the current search before we set a new position
                # For continuous analysis, we don't need to wait for bestmove - just send stop and proceed
                self.uci.stop_search()
                
                # CRITICAL: Add small delay to allow engine to process stop command
                # This prevents race conditions when commands are sent too quickly in succession
                # Without this delay, the engine may not have time to process "stop" before receiving
                # the next command, causing lost PV lines or engine restarts
                time.sleep(0.01)  # 10ms delay - minimal but sufficient for synchronization
                
                # Now set new position (engine should be ready after stop)
                # IMPORTANT: Update current_fen BEFORE sending position to engine
                # This ensures that when updates arrive, they're already associated with the new position
                self.current_fen = fen
                
                if not self.uci.set_position(fen):
                    self.error_occurred.emit("Failed to set position")
                    return
                
                # Set multipv option (this is the key change - always update multipv)
                if not self.uci.set_option("MultiPV", self.multipv, wait_for_ready=False):
                    self.error_occurred.emit("Failed to set MultiPV option")
                    return
                
                # Start new search (no need to wait for readyok - engine will process setoption asynchronously)
                if not self.uci.start_search(depth=self.max_depth, movetime=self.movetime):
                    self.error_occurred.emit("Failed to start search")
                    return
                # Reset tracking for new position/multipv
                # This ensures that when multipv changes, all lines get fresh updates
                # Without clearing, pending updates for old multipv values might block new ones
                self._last_update_time.clear()
                self._pending_updates.clear()
                self._current_nps = -1
                self._current_hashfull = -1
                # Track that we've seen explicit multipv lines after restart
                # This helps us distinguish between ambiguous lines
                self._seen_explicit_multipv = False
                # Reset queue for lines without explicit multipv
                self._pending_lines_without_multipv = []
                self._next_multipv_to_assign = 1
        except Exception as e:
            self.error_occurred.emit(f"Failed to update position: {str(e)}")
        finally:
            # Release the lock and clear multipv update flag
            with self._position_update_lock:
                self._updating_position = False
                # Clear multipv update flag AFTER the search has been restarted
                # This allows the bestmove handler to know that multipv change is complete
                self._updating_multipv = False
                # Pending updates will be processed on the next call to update_position
                # This prevents rapid-fire updates from overwhelming the engine
    
    def _update_position(self, fen: str) -> None:
        """Update engine position.
        
        Args:
            fen: FEN string of new position.
        """
        # Use lock to prevent concurrent position updates
        with self._position_update_lock:
            # If same position, ignore (unless we need to update multipv)
            if fen == self.current_fen:
                return
            
            # If update is in progress, queue this update and return
            if self._updating_position:
                self._pending_position_update = fen
                return
            
            # Check if there's a pending update that's different from the current request
            # If so, use the pending one (it's more recent)
            if self._pending_position_update and self._pending_position_update != fen:
                # Use the pending update instead (it's more recent)
                fen = self._pending_position_update
                self._pending_position_update = None
            
            # Mark as updating
            self._updating_position = True
        
        # Do the actual update outside the lock to avoid blocking
        try:
            # Check if process is alive before attempting update
            if not self.uci:
                self.error_occurred.emit("Engine process not initialized")
                return
            
            if not self.uci.is_process_alive():
                # Process has terminated
                self.error_occurred.emit("Engine process terminated unexpectedly")
                return
            
            if self.uci and self.uci.is_process_alive():
                # Parse FEN to determine side to move
                import chess
                try:
                    board = chess.Board(fen)
                    self._is_black_to_move = not board.turn  # board.turn is True for White
                except Exception:
                    # If FEN parsing fails, default to White
                    self._is_black_to_move = False
                
                # Stop current search - MUST send stop before position change (UCI protocol)
                # This ensures the engine halts the current search before we set a new position
                # For continuous analysis, we don't need to wait for bestmove - just send stop and proceed
                self.uci.stop_search()
                
                # CRITICAL: Add small delay to allow engine to process stop command
                # This prevents race conditions when commands are sent too quickly in succession
                # Without this delay, the engine may not have time to process "stop" before receiving
                # the next command, causing lost PV lines or engine restarts
                time.sleep(0.01)  # 10ms delay - minimal but sufficient for synchronization
                
                # Now set new position (engine should be ready after stop)
                # IMPORTANT: Update current_fen AFTER sending position to engine
                # This ensures that any updates that arrive before this are for the old position
                # and will be filtered out by the controller's expected_fen check
                if not self.uci.set_position(fen):
                    self.error_occurred.emit("Failed to set position")
                    return
                
                # Update current_fen NOW, after sending position to engine
                # This ensures that updates for the new position will pass the filter
                self.current_fen = fen
                
                # Start new search (MultiPV is already set during initialization and when user changes it)
                if not self.uci.start_search(depth=self.max_depth, movetime=self.movetime):
                    self.error_occurred.emit("Failed to start search")
                    return
                # Reset tracking for new position
                self._last_update_time.clear()
                self._pending_updates.clear()
                self._current_nps = -1
                self._current_hashfull = -1
                self._seen_explicit_multipv = False
                self._pending_lines_without_multipv = []
                self._next_multipv_to_assign = 1
        except Exception as e:
            self.error_occurred.emit(f"Failed to update position: {str(e)}")
        finally:
            # Release the lock
            with self._position_update_lock:
                self._updating_position = False
                # Pending updates will be processed on the next call to update_position
                # This prevents rapid-fire updates from overwhelming the engine
    
    def run(self) -> None:
        """Run engine communication thread."""
        # Set OS thread ID for debugging
        self._os_thread_id = threading.get_ident()
        try:
            # Create UCI communication service
            self.uci = UCICommunicationService(
                self.engine_path, 
                enable_debug=False,
                identifier=f"ManualAnalysis-MultiPV{self.multipv}"
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
            
            # Set UCI options (thread count, multipv, and engine-specific options) if configured
            # This must be done after "uciok" but before "isready" or "position"
            if self.max_threads is not None:
                self.uci.set_option("Threads", self.max_threads, wait_for_ready=False)
            
            # Set multipv option
            self.uci.set_option("MultiPV", self.multipv, wait_for_ready=False)
            
            # Set engine-specific options (excluding Threads and MultiPV which are handled separately)
            for option_name, option_value in self.engine_options.items():
                if option_name not in ["Threads", "MultiPV"]:
                    self.uci.set_option(option_name, option_value, wait_for_ready=False)
            
            # Confirm engine is ready after setting all options
            if not self.uci.confirm_ready():
                self.error_occurred.emit("Engine did not respond with readyok after setting options")
                return
            
            # Set position and start analysis
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
                
                if not self.uci.start_search(depth=self.max_depth, movetime=self.movetime):
                    self.error_occurred.emit("Failed to start search")
                    return
            
            self.running = True
            
            # Read analysis lines
            while self.running and not self._stop_requested:
                # Check if process is still alive
                if not self.uci:
                    self.error_occurred.emit("Engine process not initialized")
                    break
                
                if not self.uci.is_process_alive():
                    # Process terminated unexpectedly
                    self.error_occurred.emit("Engine process terminated unexpectedly")
                    break
                
                # Read a line (non-blocking with short timeout)
                try:
                    line = self.uci.read_line(timeout=0.01)
                except Exception as e:
                    # Read error - might be due to process termination
                    # If we're stopping, this is expected - just exit
                    if not self.running or self._stop_requested:
                        break
                    self.error_occurred.emit(f"Error reading from engine: {str(e)}")
                    break
                
                # CRITICAL: Check stop flags IMMEDIATELY after read_line() returns
                # This must happen before ANY processing, including checking if line is empty
                # If stop_analysis() was called, we must exit immediately, discarding any buffered lines
                if not self.running or self._stop_requested:
                    # Exit immediately - discard any buffered line and don't process anything
                    break
                
                if not line:
                    # Empty line - continue to next iteration
                    continue
                
                line = line.strip()
                
                # Check one more time before processing the line
                # CRITICAL: Re-check stop flags here because stop_analysis() might have been called
                # while we were processing the previous line or while read_line() was blocking
                if not self.running or self._stop_requested:
                    break
                
                # Parse info lines for analysis
                if line.startswith("info"):
                    # Check if we're still running - if not, exit immediately
                    # Also check _stop_requested to prevent race conditions
                    # CRITICAL: Check BEFORE any processing to avoid processing lines after stop
                    if not self.running or self._stop_requested:
                        # Exit immediately - don't process any more lines
                        break
                    
                    # Parse multipv (if present)
                    parsed_multipv = self._parse_multipv(line)
                    if parsed_multipv is not None:
                        # Explicit multipv field found - use it
                        multipv = parsed_multipv
                        self._seen_explicit_multipv = True
                        # Reset assignment counter when we see explicit multipv
                        # This means we've transitioned to explicit multipv mode
                        self._next_multipv_to_assign = 1
                        self._pending_lines_without_multipv = []
                    else:
                        # No explicit multipv field - need to infer
                        # The challenge: when multipv > 1, the engine may send lines without explicit multipv
                        # These lines are ambiguous - they could all be for multipv=1, or they could be for different lines
                        # 
                        # Strategy: When we see explicit multipv, we use it. When we don't, we default to multipv=1
                        # This is because in UCI, lines without explicit multipv are typically for the best line (multipv=1)
                        # If the engine supports multipv > 1, it should send explicit multipv fields
                        #
                        # However, after a restart, the engine might send lines without multipv before sending explicit ones
                        # In this case, we can't reliably assign them to specific multipv values
                        # So we default to multipv=1 and wait for explicit multipv fields
                        if self._seen_explicit_multipv:
                            # We've already seen explicit multipv, so this is a continuation of multipv=1
                            multipv = 1
                        else:
                            # Haven't seen explicit multipv yet
                            # If multipv > 1, we can't reliably assign - default to multipv=1
                            # The engine should send explicit multipv if it supports it
                            multipv = 1
                    
                    # Check running status BEFORE printing debug info AND before any processing
                    # This prevents debug output and processing from happening after stop_analysis()
                    # CRITICAL: Double-check here because stop_analysis() might have been called during parsing
                    # If we're not running, discard this line immediately and exit
                    # Use a local variable to capture the flag value once to avoid race conditions
                    is_running = self.running and not self._stop_requested
                    if not is_running:
                        # Exit immediately - don't process, don't print debug, just exit
                        break
                    
                    # Only process updates for lines within current multipv range
                    # This prevents processing updates for lines that were removed
                    if multipv > self.multipv:
                        # Skip updates for lines beyond current multipv
                        continue
                    
                    # Parse depth
                    depth = self._parse_depth(line)
                    
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
                    
                    # Parse score
                    score = self._parse_score(line)
                    if score is not None:
                        centipawns, is_mate, mate_moves = score
                        
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
                        emit_depth = depth if depth is not None else 0
                        
                        # Get nps and hashfull (use current values if not in this line)
                        nps_value = nps if nps is not None else self._current_nps
                        nps_value = nps_value if nps_value >= 0 else -1
                        hashfull_value = hashfull if hashfull is not None else self._current_hashfull
                        hashfull_value = hashfull_value if hashfull_value >= 0 else -1
                        pv_value = pv if pv is not None else ""
                        
                        # Only process updates for lines within current multipv range
                        # This prevents processing updates for lines that were removed
                        if multipv > self.multipv:
                            # Skip updates for lines beyond current multipv
                            continue
                        
                        # Throttle updates to avoid flooding the UI thread
                        # Store the pending update for this multipv
                        self._pending_updates[multipv] = (adjusted_centipawns, adjusted_is_mate, adjusted_mate_moves, emit_depth, nps_value, hashfull_value, pv_value)
                        
                        # Check if enough time has passed since last update for this multipv
                        current_time = time.time() * 1000.0  # Convert to milliseconds
                        last_update_time = self._last_update_time.get(multipv, 0.0)
                        time_since_last_update = current_time - last_update_time
                        
                        if time_since_last_update >= self.update_interval_ms:
                            # Only emit if we're still running and not stopped
                            # Double-check right before emitting to prevent race conditions
                            if self.running and not self._stop_requested:
                                # Emit update immediately
                                self.line_update.emit(multipv, adjusted_centipawns, adjusted_is_mate, adjusted_mate_moves, emit_depth, nps_value, hashfull_value, pv_value)
                                self._last_update_time[multipv] = current_time
                                del self._pending_updates[multipv]
                
                elif line.startswith("bestmove"):
                    # Search completed (usually after stop command)
                    # For continuous analysis, we don't wait for bestmove - just restart if needed
                    # For continuous analysis, restart the search if we're still running
                    # BUT: Don't restart if we're in the middle of a position update or multipv change
                    # (The _update_position or _update_position_with_multipv_change will handle the restart)
                    if self.running and not self._stop_requested and not self._updating_multipv and not self._updating_position:
                        # Restart search for continuous analysis
                        if self.current_fen and self.uci:
                            # Check if process is still alive before sending commands
                            if not self.uci.is_process_alive():
                                # Process terminated
                                self.error_occurred.emit("Engine process terminated unexpectedly")
                                break
                            try:
                                if not self.uci.start_search(depth=self.max_depth, movetime=self.movetime):
                                    self.error_occurred.emit("Failed to restart search")
                                    break
                                # Reset tracking for new search
                                self._last_update_time.clear()
                                self._pending_updates.clear()
                                self._current_nps = -1
                                self._current_hashfull = -1
                            except Exception as e:
                                # If write fails, emit error and exit
                                self.error_occurred.emit(f"Error writing to engine: {str(e)}")
                                break
                    elif self._updating_multipv:
                        # We're in the middle of a multipv change - don't restart here
                        # The _update_position_with_multipv_change method will handle the restart
                        pass
                    elif self._updating_position:
                        # We're in the middle of a position update - don't restart here
                        # The _update_position method will handle the restart with the new position
                        pass
                
                elif line.strip() == "readyok":
                    # Engine is ready after isready command
                    # Signal the event to unblock stop_analysis() if it's waiting
                    self._readyok_event.set()
            
        except Exception as e:
            self.error_occurred.emit(f"Engine communication error: {str(e)}")
        finally:
            self.running = False
            # Clean up UCI communication service
            if self.uci:
                self.uci.cleanup()
    
    def _parse_multipv(self, line: str) -> Optional[int]:
        """Parse multipv from info line.
        
        Args:
            line: Info line from engine.
            
        Returns:
            Multipv value or None if not found.
        """
        parts = line.split()
        try:
            if "multipv" in parts:
                idx = parts.index("multipv")
                if idx + 1 < len(parts):
                    return int(parts[idx + 1])
        except (ValueError, IndexError):
            pass
        return None
    
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


class ManualAnalysisEngineService(QObject):
    """Service for managing continuous UCI engine analysis with multipv support."""
    
    line_update = pyqtSignal(int, float, bool, int, int, int, int, str)  # multipv, centipawns, is_mate, mate_moves, depth, nps, hashfull (-1 for not available), pv (empty string for not available)
    error_occurred = pyqtSignal(str)  # error_message
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize manual analysis engine service.
        
        Args:
            config: Configuration dictionary.
        """
        super().__init__()
        self.config = config
        self.analysis_thread: Optional[ManualAnalysisEngineThread] = None
        self.current_engine_path: Optional[Path] = None
        manual_analysis_config = config.get("ui", {}).get("panels", {}).get("detail", {}).get("manual_analysis", {})
        self.update_interval_ms = manual_analysis_config.get("update_interval_ms", 100)  # Default 100ms = 10 updates/sec
        max_threads_value = manual_analysis_config.get("max_threads", None)
        # JSON null loads as Python None, so check for None and convert to int otherwise
        self.max_threads = None if max_threads_value is None else int(max_threads_value)
    
    def start_analysis(self, engine_path: Path, fen: str, multipv: int = 1) -> bool:
        """Start analysis for a position.
        
        Args:
            engine_path: Path to UCI engine executable.
            fen: FEN string of position to analyze.
            multipv: Number of analysis lines to compute (default 1).
            
        Returns:
            True if analysis started, False otherwise.
        """
        # Stop existing analysis if running
        # IMPORTANT: Preserve the thread's multipv value BEFORE stopping
        # This ensures that if we're restarting due to an error, we maintain the correct multipv
        # After stop_analysis(), the thread may be None, so we must preserve it before
        preserved_multipv = self.analysis_thread.multipv if self.analysis_thread else multipv
        
        # Only stop if there's actually a thread running
        if self.analysis_thread:
            self.stop_analysis()
        
        # Use the preserved multipv value (the thread is now None, so we use preserved value)
        final_multipv = preserved_multipv
        
        # Get task-specific parameters for this engine (with fallback to config.json)
        from app.services.engine_parameters_service import EngineParametersService
        task_params = EngineParametersService.get_task_parameters_for_engine(
            engine_path,
            "manual_analysis",
            self.config
        )
        
        # Use task-specific parameters if available, otherwise use config.json defaults
        max_threads = task_params.get("threads", self.max_threads)
        max_depth = task_params.get("depth", 0)
        movetime = task_params.get("movetime", 0)
        
        # Extract engine-specific options (all keys except common parameters)
        engine_options = {}
        for key, value in task_params.items():
            if key not in ["threads", "depth", "movetime"]:
                engine_options[key] = value
        
        # Create and start new analysis thread
        self.current_engine_path = engine_path
        self.analysis_thread = ManualAnalysisEngineThread(engine_path, final_multipv, self.update_interval_ms, max_threads, engine_options, max_depth, movetime)
        self.analysis_thread.line_update.connect(self.line_update.emit)
        self.analysis_thread.error_occurred.connect(self.error_occurred.emit)
        self.analysis_thread.start_analysis(fen)
        
        return True
    
    def update_position(self, fen: str) -> None:
        """Update analysis position.
        
        Args:
            fen: FEN string of new position.
        """
        try:
            if self.analysis_thread:
                if self.analysis_thread.running:
                    # Thread is running - update position
                    self.analysis_thread._update_position(fen)
                elif self.analysis_thread.isFinished():
                    # Thread finished (maybe due to error) - restart
                    if self.current_engine_path:
                        # IMPORTANT: Preserve the thread's multipv value before restarting
                        # This ensures we don't lose the multipv setting when restarting due to errors
                        multipv = self.analysis_thread.multipv if self.analysis_thread else 1
                        self.start_analysis(self.current_engine_path, fen, multipv)
                else:
                    # Thread is starting up - wait a bit and then update
                    # Don't restart immediately as it might be starting up
                    if self.analysis_thread.isRunning():
                        # Thread is running but not in "running" state yet - update position
                        self.analysis_thread._update_position(fen)
                    elif self.current_engine_path:
                        # Thread not running - restart
                        # IMPORTANT: Preserve the thread's multipv value before restarting
                        multipv = self.analysis_thread.multipv if self.analysis_thread else 1
                        self.start_analysis(self.current_engine_path, fen, multipv)
            elif self.current_engine_path:
                # No thread exists - start new analysis
                # This should not happen during normal operation, but if it does, use default multipv=1
                # (We can't use self.analysis_thread.multipv here because the thread is None)
                self.start_analysis(self.current_engine_path, fen, 1)
        except Exception as e:
            # Emit error but don't crash
            self.error_occurred.emit(f"Error updating position: {str(e)}")
    
    def set_multipv(self, multipv: int) -> None:
        """Set number of analysis lines (multipv).
        
        Args:
            multipv: Number of lines to analyze (1-based, minimum 1).
        """
        if not self.analysis_thread:
            return
        
        # Always update the thread's multipv value
        # If thread is running, it will trigger position update
        # If thread is not running, it will be used when it starts
        if self.analysis_thread.running:
            # Thread is running - update multipv (will restart search)
            self.analysis_thread.set_multipv(multipv)
        else:
            # Thread not running - just update for next start
            self.analysis_thread.multipv = multipv
    
    def stop_analysis(self, keep_engine_alive: bool = False) -> None:
        """Stop current analysis.
        
        Args:
            keep_engine_alive: If True, stop analysis but don't shutdown the engine process.
                              This is used when the same engine is needed by another service.
        """
        if self.analysis_thread:
            # Disconnect signal connections to prevent any pending updates from being emitted
            # This ensures that even if the thread is in the middle of processing a line,
            # the update won't reach the controller/model
            try:
                self.analysis_thread.line_update.disconnect()
            except Exception:
                pass  # Ignore if already disconnected
            try:
                self.analysis_thread.error_occurred.disconnect()
            except Exception:
                pass  # Ignore if already disconnected
            
            if keep_engine_alive:
                # Don't shutdown the engine process - just stop the thread
                # Set flags to make the thread exit its run loop naturally
                self.analysis_thread.running = False
                self.analysis_thread._stop_requested = True
                # Send stop command to halt search, but don't send quit or cleanup
                if self.analysis_thread.uci and self.analysis_thread.uci.is_process_alive():
                    self.analysis_thread.uci.stop_search()
                # Wait for thread to exit its run loop (but engine process stays alive)
                finished = self.analysis_thread.wait(3000)  # Wait up to 3 seconds (milliseconds)
                if finished or (self.analysis_thread and self.analysis_thread.isFinished()):
                    self.analysis_thread = None
                else:
                    # Thread didn't finish - force terminate (but engine process might still be alive)
                    if self.analysis_thread and self.analysis_thread.isRunning():
                        self.analysis_thread.terminate()
                        self.analysis_thread.wait(2000)
                    self.analysis_thread = None
            else:
                # Normal shutdown - terminate the engine process
                self.analysis_thread.stop_analysis()
                self.analysis_thread.shutdown()
                finished = self.analysis_thread.wait(3000)  # Wait up to 3 seconds (milliseconds)
                
                # If wait() timed out, the thread is still running - force terminate and wait again
                if not finished and self.analysis_thread and self.analysis_thread.isRunning():
                    # Force terminate the thread
                    self.analysis_thread.terminate()
                    # Wait again for termination
                    finished = self.analysis_thread.wait(2000)  # Wait up to 2 more seconds
                
                # Set to None if thread is finished (or terminated)
                # After termination, the thread should be finished, so we can safely set it to None
                if finished or (self.analysis_thread and self.analysis_thread.isFinished()):
                    self.analysis_thread = None
                else:
                    # Thread didn't finish even after termination - this shouldn't happen, but if it does,
                    # we still set it to None to prevent blocking future analysis starts
                    # The thread's run() loop should exit immediately when running=False (due to break statements)
                    # Force set to None - the thread's run() loop should exit when it checks running=False
                    self.analysis_thread = None

