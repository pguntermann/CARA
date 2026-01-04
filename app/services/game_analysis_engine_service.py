"""Game analysis engine service for analyzing individual moves with time and depth limits."""

import sys
import time
import queue
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from app.services.uci_communication_service import UCICommunicationService


class AnalysisRequest:
    """Request for analyzing a position."""
    def __init__(self, fen: str, move_number: int, progress_interval_ms: int = 500):
        self.fen = fen
        self.move_number = move_number
        self.progress_interval_ms = progress_interval_ms
        self.completed = False
        self.result: Optional[Tuple[float, bool, int, str, str, int, int]] = None


class GameAnalysisEngineThread(QThread):
    """Persistent thread for analyzing multiple positions with a single engine instance."""
    
    analysis_complete = pyqtSignal(float, bool, int, str, str, str, str, float, float, float, float, int, int, str)  # centipawns, is_mate, mate_moves, best_move_san, pv1_string, pv2_move_san, pv3_move_san, pv2_score, pv3_score, pv2_score_black, pv3_score_black, depth, nps, engine_name
    progress_update = pyqtSignal(int, int, int, float, str, int, int)  # depth, seldepth, centipawns, time_elapsed_ms, engine_name, threads, move_number
    error_occurred = pyqtSignal(str)  # error_message
    
    def __init__(self, engine_path: Path, max_depth: int, time_limit_ms: int,
                 max_threads: Optional[int] = None, engine_name: str = "", engine_options: Optional[Dict[str, Any]] = None) -> None:
        """Initialize game analysis engine thread.
        
        Args:
            engine_path: Path to UCI engine executable.
            max_depth: Maximum depth to search.
            time_limit_ms: Maximum time per position in milliseconds.
            max_threads: Maximum number of CPU threads/cores to use (None = use engine default).
            engine_name: Name of the engine for progress reporting.
            engine_options: Dictionary of engine-specific options to set (e.g., {"Hash": 64, "Ponder": False}).
        """
        super().__init__()
        self.engine_path = engine_path
        self.max_depth = max_depth
        self.time_limit_ms = time_limit_ms
        self.max_threads = max_threads
        self.engine_name = engine_name
        self.engine_options = engine_options or {}
        self.uci: Optional[UCICommunicationService] = None
        self.running = False
        self._stop_requested = False
        self._analysis_queue: queue.Queue = queue.Queue()
        self._current_request: Optional[AnalysisRequest] = None
        self._current_depth = 0
        self._current_seldepth = 0
        self._best_score: Optional[float] = None
        self._best_is_mate = False
        self._best_mate_moves = 0
        self._best_move_uci: Optional[str] = None
        self._best_pv: str = ""
        self._is_black_to_move = False
        self._start_time = 0.0
        self._last_progress_time = 0.0
        self._progress_interval_ms = 500  # Default progress update interval
        self._current_nps: int = 0
        # Multi-PV storage: dict mapping multipv number (1, 2, 3) to (move_uci, pv_string, score, is_mate, mate_moves)
        # score is in centipawns (float), is_mate is bool, mate_moves is int
        self._multipv_moves: Dict[int, Tuple[Optional[str], str, Optional[float], bool, int]] = {
            1: (None, "", None, False, 0),
            2: (None, "", None, False, 0),
            3: (None, "", None, False, 0)
        }
    
    def queue_analysis(self, request: AnalysisRequest) -> None:
        """Queue a position for analysis.
        
        Args:
            request: AnalysisRequest with position details.
        """
        self._analysis_queue.put(request)
    
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
        """Shutdown engine process."""
        self.running = False
        self._stop_requested = True
        # Clear queue
        while not self._analysis_queue.empty():
            try:
                self._analysis_queue.get_nowait()
            except queue.Empty:
                break
        if self.uci:
            self.uci.cleanup()
    
    def run(self) -> None:
        """Run engine analysis thread - processes queue of positions."""
        try:
            # Create UCI communication service
            self.uci = UCICommunicationService(
                self.engine_path, 
                identifier=f"GameAnalysis-{self.engine_name or 'Unknown'}"
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
            
            # Set MultiPV to 3 for game analysis (always use 3 PV lines)
            if not self.uci.set_option("MultiPV", 3, wait_for_ready=False):
                self.error_occurred.emit("Failed to set MultiPV option")
                return
            
            # Set engine-specific options (excluding Threads and MultiPV which are handled separately)
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
                    self._analyze_position(request)
                    self._current_request = None
                    
                except Exception as e:
                    self.error_occurred.emit(f"Error processing analysis queue: {str(e)}")
                    break
            
            # Cleanup
            if self.uci:
                self.uci.cleanup()
        
        except Exception as e:
            self.error_occurred.emit(f"Error in analysis thread: {str(e)}")
        finally:
            self.running = False
            if self.uci:
                self.uci.cleanup()
    
    def _analyze_position(self, request: AnalysisRequest) -> None:
        """Analyze a single position.
        
        Args:
            request: AnalysisRequest with position details.
        """
        try:
            self._start_time = time.time() * 1000.0  # milliseconds
            self._last_progress_time = self._start_time
            self._progress_interval_ms = request.progress_interval_ms
            
            # Reset analysis state
            self._current_depth = 0
            self._current_seldepth = 0
            self._best_score = None
            self._best_is_mate = False
            self._best_mate_moves = 0
            self._best_move_uci = None
            self._best_pv = ""
            self._current_nps = 0
            # Reset multi-PV storage
            self._multipv_moves = {1: (None, "", None, False, 0), 2: (None, "", None, False, 0), 3: (None, "", None, False, 0)}
            
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
            
            # Start analysis with depth and/or movetime (UCI layer will skip if 0)
            if not self.uci.start_search(depth=self.max_depth, movetime=self.time_limit_ms):
                self.error_occurred.emit("Failed to start search")
                return
            
            # Read analysis output
            while not self._stop_requested:
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
                    
                    # Emit progress updates at intervals
                    current_time = time.time() * 1000.0
                    elapsed_time = current_time - self._start_time
                    if current_time - self._last_progress_time >= self._progress_interval_ms:
                        if self._best_score is not None:
                            self.progress_update.emit(
                                self._current_depth,
                                self._current_seldepth,
                                int(self._best_score),
                                elapsed_time,
                                self.engine_name,
                                self.max_threads or 0,
                                request.move_number
                            )
                        self._last_progress_time = current_time
                
                # Check for bestmove (analysis complete)
                elif line.startswith("bestmove"):
                    parts = line.split()
                    if len(parts) >= 2:
                        self._best_move_uci = parts[1]
                    
                    # Convert best move to SAN (use PV1 move)
                    best_move_san = ""
                    pv1_move_uci = self._multipv_moves[1][0] if self._multipv_moves[1][0] else self._best_move_uci
                    # Get PV2 and PV3 scores
                    pv2_score = self._multipv_moves[2][2] if self._multipv_moves[2][2] is not None else 0.0
                    pv3_score = self._multipv_moves[3][2] if self._multipv_moves[3][2] is not None else 0.0
                    # For black moves, we need scores from black's perspective (already flipped in parsing)
                    pv2_score_black = pv2_score
                    pv3_score_black = pv3_score
                    if pv1_move_uci and pv1_move_uci != "(none)":
                        try:
                            board = chess.Board(request.fen)
                            move = chess.Move.from_uci(pv1_move_uci)
                            if move in board.legal_moves:
                                best_move_san = board.san(move)
                        except Exception:
                            best_move_san = pv1_move_uci
                    
                    # Convert PV2 and PV3 moves to SAN
                    pv2_move_san = ""
                    pv3_move_san = ""
                    if self._multipv_moves[2][0]:
                        try:
                            board = chess.Board(request.fen)
                            move = chess.Move.from_uci(self._multipv_moves[2][0])
                            if move in board.legal_moves:
                                pv2_move_san = board.san(move)
                        except Exception:
                            pv2_move_san = self._multipv_moves[2][0]
                    if self._multipv_moves[3][0]:
                        try:
                            board = chess.Board(request.fen)
                            move = chess.Move.from_uci(self._multipv_moves[3][0])
                            if move in board.legal_moves:
                                pv3_move_san = board.san(move)
                        except Exception:
                            pv3_move_san = self._multipv_moves[3][0]
                    
                    # Get PV strings (first move only for PV2 and PV3)
                    pv1_string = self._multipv_moves[1][1] if self._multipv_moves[1][1] else self._best_pv
                    pv2_string = self._multipv_moves[2][1]
                    pv3_string = self._multipv_moves[3][1]
                    
                    # Emit final result
                    # If _best_score is None, it means no score was received in info lines
                    # This can happen when the game ends in checkmate - the engine sends bestmove without score
                    # In this case, use the mate score if we detected mate, otherwise use 0.0
                    if self._best_score is not None:
                        final_score = self._best_score
                        final_is_mate = self._best_is_mate
                        final_mate_moves = self._best_mate_moves
                    else:
                        # No score received - this typically happens at game end
                        # Check if the bestmove is a null move (game over)
                        if pv1_move_uci == "(none)" or (pv1_move_uci and len(pv1_move_uci) >= 4 and pv1_move_uci[:2] == pv1_move_uci[2:4]):
                            # Null move or same square (game over) - use mate score
                            # If black to move and game ends, white won (mate in 0 for black)
                            # If white to move and game ends, black won (mate in 0 for white)
                            final_score = 0.0  # Will be interpreted as mate
                            final_is_mate = True
                            final_mate_moves = 0
                        else:
                            # Fallback: use 0.0 as neutral score
                            final_score = 0.0
                            final_is_mate = False
                            final_mate_moves = 0
                    
                    self.analysis_complete.emit(
                        final_score,
                        final_is_mate,
                        final_mate_moves,
                        best_move_san,
                        pv1_string,
                        pv2_move_san,
                        pv3_move_san,
                        pv2_score,
                        pv3_score,
                        pv2_score_black,
                        pv3_score_black,
                        self._current_depth,
                        self._current_nps,
                        self.engine_name
                    )
                    break
        
        except Exception as e:
            self.error_occurred.emit(f"Error analyzing position: {str(e)}")
    
    def _parse_info_line(self, line: str) -> None:
        """Parse UCI info line.
        
        Args:
            line: UCI info line string.
        """
        parts = line.split()
        
        # Parse multipv number (1, 2, or 3)
        multipv_num = 1  # Default to PV1 if not specified
        if "multipv" in parts:
            idx = parts.index("multipv")
            if idx + 1 < len(parts):
                try:
                    multipv_num = int(parts[idx + 1])
                    if multipv_num < 1 or multipv_num > 3:
                        multipv_num = 1  # Fallback to PV1 if out of range
                except ValueError:
                    multipv_num = 1
        
        # Parse depth
        if "depth" in parts:
            idx = parts.index("depth")
            if idx + 1 < len(parts):
                try:
                    depth = int(parts[idx + 1])
                    # Update current depth (use max depth across all PVs)
                    if depth > self._current_depth:
                        self._current_depth = depth
                except ValueError:
                    pass
        
        # Parse seldepth
        if "seldepth" in parts:
            idx = parts.index("seldepth")
            if idx + 1 < len(parts):
                try:
                    seldepth = int(parts[idx + 1])
                    # Update current seldepth (use max seldepth across all PVs)
                    if seldepth > self._current_seldepth:
                        self._current_seldepth = seldepth
                except ValueError:
                    pass
        
        # Parse score for all multipv numbers
        if "score" in parts:
            idx = parts.index("score")
            if idx + 1 < len(parts):
                score_type = parts[idx + 1]
                score_value: Optional[float] = None
                is_mate_score = False
                mate_moves_value = 0
                
                if score_type == "cp" and idx + 2 < len(parts):
                    try:
                        centipawns = int(parts[idx + 2])
                        # Flip score if black to move
                        if self._is_black_to_move:
                            centipawns = -centipawns
                        score_value = float(centipawns)
                        is_mate_score = False
                        mate_moves_value = 0
                    except ValueError:
                        pass
                elif score_type == "mate" and idx + 2 < len(parts):
                    try:
                        mate_moves_raw = int(parts[idx + 2])
                        # In UCI protocol:
                        # - mate N where N > 0: side to move can mate in N moves
                        # - mate -N where N > 0: opponent can mate in N moves
                        # - mate 0: side to move is mated
                        # Convert to our convention: positive = white winning, negative = black winning
                        if mate_moves_raw == 0:
                            # mate 0 means the side to move is mated
                            # If black is to move and mated, white wins (positive)
                            # If white is to move and mated, black wins (negative)
                            if self._is_black_to_move:
                                mate_moves_value = 0  # Black is mated, white wins
                                score_value = 10000.0  # White wins
                            else:
                                mate_moves_value = 0  # White is mated, black wins
                                score_value = -10000.0  # Black wins
                        else:
                            # Mate in N moves - normalize to our convention
                            if self._is_black_to_move:
                                mate_moves_value = -mate_moves_raw
                            else:
                                mate_moves_value = mate_moves_raw
                            # Convert to centipawns (approximate)
                            if mate_moves_value > 0:
                                score_value = 10000.0 - (mate_moves_value * 100)  # White is winning
                            else:
                                score_value = -10000.0 - (abs(mate_moves_value) * 100)  # Black is winning
                        is_mate_score = True
                    except ValueError:
                        pass
                
                # Store score for this multipv number
                if score_value is not None:
                    # Update the multipv_moves tuple with score information
                    current_move_uci, current_pv_string, _, _, _ = self._multipv_moves[multipv_num]
                    self._multipv_moves[multipv_num] = (current_move_uci, current_pv_string, score_value, is_mate_score, mate_moves_value)
                    
                    # Also update _best_score for PV1 (backward compatibility)
                    if multipv_num == 1:
                        self._best_score = score_value
                        self._best_is_mate = is_mate_score
                        self._best_mate_moves = mate_moves_value
        
        # Parse principal variation (PV) for each multipv
        if "pv" in parts:
            idx = parts.index("pv")
            if idx + 1 < len(parts):
                # PV moves are after "pv"
                pv_moves = parts[idx + 1:]
                # Extract first move (UCI format)
                first_move_uci = pv_moves[0] if pv_moves else None
                # Limit PV length for display
                max_pv_moves = 5
                if len(pv_moves) > max_pv_moves:
                    pv_moves = pv_moves[:max_pv_moves]
                pv_string = " ".join(pv_moves)
                
                # Store PV move and string for this multipv (preserve existing score if present)
                current_move_uci, current_pv_string, current_score, current_is_mate, current_mate_moves = self._multipv_moves[multipv_num]
                # Update move and PV string, but preserve score if it hasn't been set yet
                if current_score is None:
                    # No score yet, keep None
                    self._multipv_moves[multipv_num] = (first_move_uci, pv_string, None, False, 0)
                else:
                    # Score already set, preserve it
                    self._multipv_moves[multipv_num] = (first_move_uci, pv_string, current_score, current_is_mate, current_mate_moves)
                
                # Also update _best_pv and _best_move_uci for PV1 (backward compatibility)
                if multipv_num == 1:
                    self._best_pv = pv_string
                    self._best_move_uci = first_move_uci
        
        # Parse nodes per second
        if "nps" in parts:
            idx = parts.index("nps")
            if idx + 1 < len(parts):
                try:
                    self._current_nps = int(parts[idx + 1])
                except ValueError:
                    pass


class GameAnalysisEngineService(QObject):
    """Service for managing game analysis engine operations."""
    
    def __init__(self, engine_path: Path, max_depth: int, time_limit_ms: int,
                 max_threads: Optional[int] = None, engine_name: str = "", engine_options: Optional[Dict[str, Any]] = None, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize game analysis engine service.
        
        Args:
            engine_path: Path to UCI engine executable.
            max_depth: Maximum depth to search.
            time_limit_ms: Maximum time per position in milliseconds.
            max_threads: Maximum number of CPU threads/cores to use.
            engine_name: Name of the engine.
            engine_options: Dictionary of engine-specific options to set (e.g., {"Hash": 64, "Ponder": False}).
            config: Optional configuration dictionary.
        """
        super().__init__()
        self.engine_path = engine_path
        self.max_depth = max_depth
        self.time_limit_ms = time_limit_ms
        self.max_threads = max_threads
        self.engine_name = engine_name
        self.engine_options = engine_options or {}
        self.config = config
        self.analysis_thread: Optional[GameAnalysisEngineThread] = None
    
    def start_engine(self) -> bool:
        """Start the persistent analysis thread.
        
        Returns:
            True if thread started successfully, False otherwise.
        """
        if self.analysis_thread and self.analysis_thread.isRunning():
            return True
        
        # Create new thread
        self.analysis_thread = GameAnalysisEngineThread(
            self.engine_path,
            self.max_depth,
            self.time_limit_ms,
            self.max_threads,
            self.engine_name,
            self.engine_options
        )
        
        # Connect signals (these will be used by the controller)
        # Note: The controller will also connect its own handlers
        
        # Start thread
        self.analysis_thread.start()
        
        # Wait for thread to initialize engine (check if running flag is set)
        # Give it some time to spawn process and initialize UCI
        import time
        start_time = time.time()
        while not self.analysis_thread.running and (time.time() - start_time) < 5.0:
            if not self.analysis_thread.isRunning():
                return False
            time.sleep(0.1)
        
        return self.analysis_thread.running
    
    def analyze_position(self, fen: str, move_number: int, progress_interval_ms: int = 500) -> GameAnalysisEngineThread:
        """Queue a position for analysis.
        
        Args:
            fen: FEN string of position to analyze.
            move_number: Move number for progress reporting.
            progress_interval_ms: Progress update interval in milliseconds.
            
        Returns:
            GameAnalysisEngineThread instance (for signal connections).
        """
        # Start engine thread if not already running
        if not self.analysis_thread or not self.analysis_thread.isRunning():
            if not self.start_engine():
                return None
        
        # Create analysis request
        request = AnalysisRequest(fen, move_number, progress_interval_ms)
        
        # Queue for analysis
        self.analysis_thread.queue_analysis(request)
        
        return self.analysis_thread
    
    def stop_analysis(self) -> None:
        """Stop current analysis and clear queue."""
        if self.analysis_thread and self.analysis_thread.isRunning():
            self.analysis_thread.stop()
    
    def shutdown(self) -> None:
        """Shutdown engine process and thread."""
        if self.analysis_thread:
            if self.analysis_thread.isRunning():
                self.analysis_thread.shutdown()
                self.analysis_thread.wait(5000)  # Wait up to 5 seconds for thread to finish
            self.analysis_thread = None
    
    def cleanup(self) -> None:
        """Cleanup resources."""
        self.shutdown()
