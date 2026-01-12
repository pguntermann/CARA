"""Manual analysis engine service for continuous UCI engine analysis with multipv support."""

import re
import sys
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer

from app.services.uci_communication_service import UCICommunicationService
from app.services.logging_service import LoggingService


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
        self._search_just_started = False  # Flag to prevent bestmove handler from restarting immediately after position update
        self._search_start_time: Optional[float] = None  # Timestamp when search was last started (for ignoring stale bestmove messages)
        self._info_lines_received_after_start = 0  # Counter for info lines received after starting search (for multipv change)
        self._keep_engine_alive = False  # Flag to prevent cleanup when engine should be kept alive for reuse
    
    def _thread_info(self) -> str:
        """Get thread identification string for debugging."""
        os_id = f"os={self._os_thread_id}" if self._os_thread_id is not None else "os=?"
        return f"inst={self._thread_id} {os_id}"
    
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
        self.running = False
        self._stop_requested = True
        self._updating_multipv = False
        self._pending_updates.clear()
        self._last_update_time.clear()
        with self._position_update_lock:
            self._pending_position_update = None
        
        if not self.uci:
            return
        
        self._readyok_event.clear()
        
        # Stop search and attempt graceful shutdown
        if self.uci and self.uci.is_process_alive():
            self.uci.stop_search()
        
        # Send isready to confirm engine is idle
        if self.uci and self.uci.is_process_alive():
            try:
                self.uci.send_command("isready")
                self._readyok_event.wait(timeout=5.0)
            except Exception:
                pass
        
        # Send quit for graceful shutdown
        if self.uci and self.uci.is_process_alive():
            try:
                self.uci.quit_engine()
                self.uci.wait_for_process(timeout=3.0)
            except Exception:
                pass
        
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
        
        old_multipv = self.multipv
        self.multipv = multipv
        
        if old_multipv != multipv and self.running and self.current_fen:
            self._update_position_with_multipv_change(self.current_fen)
    
    def _update_position_with_multipv_change(self, fen: str) -> None:
        """Update engine position with multipv change (forces update even if FEN is same).
        
        Args:
            fen: FEN string of position.
        """
        self._updating_multipv = True
        
        with self._position_update_lock:
            if self._updating_position:
                self._pending_position_update = fen
                return
            self._updating_position = True
        
        try:
            if not self.uci:
                self.error_occurred.emit("Engine process not initialized")
                return
            
            if not self.uci.is_process_alive():
                self.error_occurred.emit("Engine process terminated unexpectedly")
                return
            
            if self.uci and self.uci.is_process_alive():
                import chess
                try:
                    board = chess.Board(fen)
                    self._is_black_to_move = not board.turn
                except Exception:
                    self._is_black_to_move = False
                
                # Stop search before position change (UCI protocol requirement)
                self.uci.stop_search()
                time.sleep(0.01)  # Small delay to allow engine to process stop command
                
                self.current_fen = fen
                if not self.uci.set_position(fen):
                    self.error_occurred.emit("Failed to set position")
                    return
                
                if not self.uci.set_option("MultiPV", self.multipv, wait_for_ready=False):
                    self.error_occurred.emit("Failed to set MultiPV option")
                    return
                
                if not self.uci.start_search(depth=self.max_depth, movetime=self.movetime):
                    self.error_occurred.emit("Failed to start search")
                    return
                
                # Set flags to prevent bestmove handler from restarting immediately
                self._search_just_started = True
                self._search_start_time = time.time()
                self._info_lines_received_after_start = 0
                
                # Reset tracking for new position/multipv
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
            with self._position_update_lock:
                self._updating_position = False
    
    def _update_position(self, fen: str) -> None:
        """Update engine position.
        
        Args:
            fen: FEN string of new position.
        """
        with self._position_update_lock:
            if fen == self.current_fen:
                return
            
            if self._updating_position:
                self._pending_position_update = fen
                return
            
            if self._pending_position_update and self._pending_position_update != fen:
                fen = self._pending_position_update
                self._pending_position_update = None
            
            self._updating_position = True
        
        try:
            if not self.uci:
                self.error_occurred.emit("Engine process not initialized")
                return
            
            if not self.uci.is_process_alive():
                self.error_occurred.emit("Engine process terminated unexpectedly")
                return
            
            if self.uci and self.uci.is_process_alive():
                import chess
                try:
                    board = chess.Board(fen)
                    self._is_black_to_move = not board.turn
                except Exception:
                    self._is_black_to_move = False
                
                # Stop search before position change (UCI protocol requirement)
                self.uci.stop_search()
                time.sleep(0.01)  # Small delay to allow engine to process stop command
                
                if not self.uci.set_position(fen):
                    self.error_occurred.emit("Failed to set position")
                    return
                
                self.current_fen = fen
                
                if not self.uci.start_search(depth=self.max_depth, movetime=self.movetime):
                    self.error_occurred.emit("Failed to start search")
                    return
                
                # Set flags to prevent bestmove handler from restarting immediately
                self._search_just_started = True
                self._search_start_time = time.time()
                self._info_lines_received_after_start = 0
                
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
            with self._position_update_lock:
                self._updating_position = False
    
    def run(self) -> None:
        """Run engine communication thread."""
        # Set OS thread ID for debugging
        self._os_thread_id = threading.get_ident()
        try:
            # Create UCI communication service
            self.uci = UCICommunicationService(
                self.engine_path, 
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
            
            # Set UCI options (must be done after uciok, before isready/position)
            if self.max_threads is not None:
                self.uci.set_option("Threads", self.max_threads, wait_for_ready=False)
            
            self.uci.set_option("MultiPV", self.multipv, wait_for_ready=False)
            
            for option_name, option_value in self.engine_options.items():
                if option_name not in ["Threads", "MultiPV"]:
                    self.uci.set_option(option_name, option_value, wait_for_ready=False)
            
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
                    self.error_occurred.emit("Engine process terminated unexpectedly")
                    break
                
                try:
                    line = self.uci.read_line(timeout=0.01)
                except Exception as e:
                    if not self.running or self._stop_requested:
                        break
                    self.error_occurred.emit(f"Error reading from engine: {str(e)}")
                    break
                
                # Check stop flags immediately after read
                if not self.running or self._stop_requested:
                    break
                
                if not line:
                    continue
                
                line = line.strip()
                
                # Re-check stop flags before processing
                if not self.running or self._stop_requested:
                    break
                
                if line.startswith("info"):
                    if not self.running or self._stop_requested:
                        break
                    
                    # Parse multipv (default to 1 if not explicit)
                    parsed_multipv = self._parse_multipv(line)
                    if parsed_multipv is not None:
                        multipv = parsed_multipv
                        self._seen_explicit_multipv = True
                        self._next_multipv_to_assign = 1
                        self._pending_lines_without_multipv = []
                    else:
                        # Lines without explicit multipv default to multipv=1
                        multipv = 1
                    
                    if not self.running or self._stop_requested:
                        break
                    
                    if multipv > self.multipv:
                        continue
                    
                    depth = self._parse_depth(line)
                    
                    nps = self._parse_nps(line)
                    if nps is not None:
                        self._current_nps = nps
                    
                    hashfull = self._parse_hashfull(line)
                    if hashfull is not None:
                        self._current_hashfull = hashfull
                    
                    # Track info lines to determine when search is established
                    if self._updating_multipv or self._search_just_started:
                        self._info_lines_received_after_start += 1
                    
                    # Clear flags when search is established (depth >= 1 or 2+ info lines after 100ms)
                    current_time = time.time()
                    time_since_search_start = (current_time - self._search_start_time) if self._search_start_time else float('inf')
                    search_established = (depth is not None and depth >= 1) or (self._info_lines_received_after_start >= 2 and time_since_search_start >= 0.1)
                    
                    if self._search_just_started and search_established:
                        self._search_just_started = False
                        self._search_start_time = None
                        self._info_lines_received_after_start = 0
                    
                    if self._updating_multipv and search_established and time_since_search_start >= 0.1:
                        self._updating_multipv = False
                        self._info_lines_received_after_start = 0
                    
                    pv = self._parse_pv(line)
                    score = self._parse_score(line)
                    if score is not None:
                        centipawns, is_mate, mate_moves = score
                        
                        # Flip evaluation if Black is to move
                        adjusted_centipawns = centipawns
                        adjusted_is_mate = is_mate
                        adjusted_mate_moves = mate_moves
                        if self._is_black_to_move:
                            adjusted_centipawns = -centipawns
                            if is_mate:
                                adjusted_mate_moves = -mate_moves
                        
                        emit_depth = depth if depth is not None else 0
                        nps_value = nps if nps is not None else self._current_nps
                        nps_value = nps_value if nps_value >= 0 else -1
                        hashfull_value = hashfull if hashfull is not None else self._current_hashfull
                        hashfull_value = hashfull_value if hashfull_value >= 0 else -1
                        pv_value = pv if pv is not None else ""
                        
                        if multipv > self.multipv:
                            continue
                        
                        # Throttle updates to avoid flooding the UI thread
                        self._pending_updates[multipv] = (adjusted_centipawns, adjusted_is_mate, adjusted_mate_moves, emit_depth, nps_value, hashfull_value, pv_value)
                        
                        current_time = time.time() * 1000.0
                        last_update_time = self._last_update_time.get(multipv, 0.0)
                        time_since_last_update = current_time - last_update_time
                        
                        if time_since_last_update >= self.update_interval_ms:
                            if self.running and not self._stop_requested:
                                self.line_update.emit(multipv, adjusted_centipawns, adjusted_is_mate, adjusted_mate_moves, emit_depth, nps_value, hashfull_value, pv_value)
                                self._last_update_time[multipv] = current_time
                                del self._pending_updates[multipv]
                
                # elif line.startswith("bestmove"):
                #     # Restart search for continuous analysis, but ignore bestmove from old searches
                #     current_time = time.time()
                #     time_since_search_start = (current_time - self._search_start_time) if self._search_start_time else float('inf')
                #     ignore_bestmove = time_since_search_start < 0.05
                #     
                #     should_restart = (self.running and not self._stop_requested and not self._updating_multipv 
                #                      and not self._updating_position and not self._search_just_started 
                #                      and not ignore_bestmove)
                #     
                #     # Clear flags if this is a valid bestmove (not from old search, 100ms+ elapsed)
                #     if not ignore_bestmove and time_since_search_start >= 0.1:
                #         if self._search_just_started:
                #             self._search_just_started = False
                #         if self._updating_multipv:
                #             self._updating_multipv = False
                #         self._search_start_time = None
                #         self._info_lines_received_after_start = 0
                #     
                #     if should_restart:
                #         if self.current_fen and self.uci:
                #             if not self.uci.is_process_alive():
                #                 self.error_occurred.emit("Engine process terminated unexpectedly")
                #                 break
                #             try:
                #                 if not self.uci.start_search(depth=self.max_depth, movetime=self.movetime):
                #                     self.error_occurred.emit("Failed to restart search")
                #                     break
                #                 self._last_update_time.clear()
                #                 self._pending_updates.clear()
                #                 self._current_nps = -1
                #                 self._current_hashfull = -1
                #             except Exception as e:
                #                 self.error_occurred.emit(f"Error writing to engine: {str(e)}")
                #                 break
                
                elif line.startswith("bestmove"):

                    # Just continue reading - position updates will restart search if needed
                    pass
                
                elif line.strip() == "readyok":
                    self._readyok_event.set()
            
        except Exception as e:
            self.error_occurred.emit(f"Engine communication error: {str(e)}")
        finally:
            self.running = False
            # Clean up UCI communication service (unless engine should be kept alive)
            if self.uci and not self._keep_engine_alive:
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
        # Preserve multipv value before stopping (thread may be None after stop)
        preserved_multipv = self.analysis_thread.multipv if self.analysis_thread else multipv
        
        if self.analysis_thread:
            self.stop_analysis()
        
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
        
        # Log manual analysis engine started
        logging_service = LoggingService.get_instance()
        options_str = f", options={engine_options}" if engine_options else ""
        logging_service.info(f"Manual analysis engine started: path={engine_path}, multipv={final_multipv}, depth={max_depth}, threads={max_threads}, movetime={movetime}ms{options_str}")
        
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
                    if self.current_engine_path:
                        multipv = self.analysis_thread.multipv if self.analysis_thread else 1
                        self.start_analysis(self.current_engine_path, fen, multipv)
                else:
                    if self.analysis_thread.isRunning():
                        self.analysis_thread._update_position(fen)
                    elif self.current_engine_path:
                        multipv = self.analysis_thread.multipv if self.analysis_thread else 1
                        self.start_analysis(self.current_engine_path, fen, multipv)
            elif self.current_engine_path:
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
        
        if self.analysis_thread.running:
            self.analysis_thread.set_multipv(multipv)
        else:
            self.analysis_thread.multipv = multipv
    
    def stop_analysis(self, keep_engine_alive: bool = False) -> None:
        """Stop current analysis.
        
        Args:
            keep_engine_alive: If True, stop analysis but don't shutdown the engine process.
                              This is used when the same engine is needed by another service.
        """
        if self.analysis_thread:
            # Disconnect signals to prevent pending updates from being emitted
            try:
                self.analysis_thread.line_update.disconnect()
            except Exception:
                pass
            try:
                self.analysis_thread.error_occurred.disconnect()
            except Exception:
                pass
            
            if keep_engine_alive:
                # Stop thread but keep engine process alive
                self.analysis_thread._keep_engine_alive = True
                self.analysis_thread.running = False
                self.analysis_thread._stop_requested = True
                if self.analysis_thread.uci and self.analysis_thread.uci.is_process_alive():
                    self.analysis_thread.uci.stop_search()
                # Don't wait - let thread exit naturally, cleanup will be skipped due to flag
                self.analysis_thread = None
            else:
                # Normal shutdown - terminate engine process
                # Set flags to stop the thread, it will exit naturally and cleanup in finally block
                self.analysis_thread._keep_engine_alive = False
                self.analysis_thread.running = False
                self.analysis_thread._stop_requested = True
                if self.analysis_thread.uci and self.analysis_thread.uci.is_process_alive():
                    self.analysis_thread.uci.stop_search()
                # Don't wait - let thread exit naturally, cleanup will happen in finally block
                self.analysis_thread = None

