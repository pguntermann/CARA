"""Manual analysis controller for managing position analysis with multipv support."""

from pathlib import Path
from typing import Dict, Any, Optional
from PyQt6.QtCore import QTimer
import chess

from app.models.manual_analysis_model import ManualAnalysisModel, AnalysisLine
from app.services.manual_analysis_engine_service import ManualAnalysisEngineService
from app.services.progress_service import ProgressService
from app.services.pv_plan_parser_service import PvPlanParserService
from app.services.logging_service import LoggingService
from app.controllers.engine_controller import TASK_MANUAL_ANALYSIS, TASK_EVALUATION


class ManualAnalysisController:
    """Controller for managing manual position analysis.
    
    This controller orchestrates analysis operations and manages
    the analysis model and engine service.
    """
    
    def __init__(self, config: Dict[str, Any], engine_controller, game_controller) -> None:
        """Initialize the manual analysis controller.
        
        Args:
            config: Configuration dictionary.
            engine_controller: EngineController instance for getting manual analysis engine.
            game_controller: GameController instance for getting current position.
        """
        self.config = config
        self.engine_controller = engine_controller
        self.game_controller = game_controller
        
        # Initialize analysis model
        self.analysis_model = ManualAnalysisModel()
        
        # Initialize analysis engine service
        self.analysis_service = ManualAnalysisEngineService(config)
        
        # Get progress service for status updates
        self.progress_service = ProgressService.get_instance()
        
        # Get max depth for progress calculation (optional, may be None for uncapped)
        manual_analysis_config = config.get("ui", {}).get("panels", {}).get("detail", {}).get("manual_analysis", {})
        self.max_depth = manual_analysis_config.get("max_depth", None)  # None = uncapped
        
        # Debounce timer for position updates to prevent rapid-fire updates
        self._position_update_timer = QTimer()
        self._position_update_timer.setSingleShot(True)
        self._position_update_timer.timeout.connect(self._do_position_update)
        self._pending_position_fen: Optional[str] = None
        self._position_update_delay_ms = 100  # Delay of 100ms to debounce rapid updates (reduced from 300ms for better UX)
        
        # Connect to analysis model to update best next move when first PV changes
        self.analysis_model.analysis_changed.connect(self._on_analysis_changed)
        
        # Track the FEN we're currently expecting updates for
        # This allows us to filter out stale updates from previous positions
        self._expected_fen: Optional[str] = None
        
        # Connect service signals to model
        self.analysis_service.line_update.connect(self._on_line_update)
        self.analysis_service.error_occurred.connect(self._on_analysis_error)
        
        # Get configured thread count for status display
        self.max_threads = manual_analysis_config.get("max_threads", None)
        
        # Track current engine ID to detect engine changes
        self._current_engine_id: Optional[str] = None
        
        # Reference to evaluation controller for coordination
        self._evaluation_controller = None
        
        # Connect to engine model to detect engine assignment changes
        engine_model = self.engine_controller.get_engine_model()
        engine_model.assignment_changed.connect(self._on_engine_assignment_changed)
        
        # Connect to game model to detect position changes
        if self.game_controller:
            game_model = self.game_controller.get_game_model()
            game_model.active_move_changed.connect(self._on_active_move_changed)
        
        # Initialize PV plan parser service
        manual_analysis_config = config.get("ui", {}).get("panels", {}).get("detail", {}).get("manual_analysis", {})
        board_config = config.get("ui", {}).get("panels", {}).get("main", {}).get("board", {})
        positional_plans_config = board_config.get("positional_plans", {})
        min_moves_for_plan = positional_plans_config.get("min_moves_for_plan", 2)
        self.pv_plan_parser = PvPlanParserService(min_moves_for_plan)
        
        # Track which PV plan is being explored (0 = none, 1-3 = PV1-PV3)
        self._active_pv_plan: int = 0
        
        # Track max number of pieces to explore (1-3, default is 1)
        self._max_pieces_to_explore: int = 1
        
        # Track max exploration depth (2-4, default is 2)
        self._max_exploration_depth: int = 2
    
    def set_evaluation_controller(self, evaluation_controller) -> None:
        """Set the evaluation controller for coordination.
        
        Args:
            evaluation_controller: EvaluationController instance.
        """
        self._evaluation_controller = evaluation_controller
    
    def get_analysis_model(self) -> ManualAnalysisModel:
        """Get the analysis model.
        
        Returns:
            The ManualAnalysisModel instance for observing analysis state.
        """
        return self.analysis_model
    
    def get_board_model(self):
        """Get the board model for checking arrow visibility.
        
        Returns:
            The BoardModel instance, or None if game_controller is not available.
        """
        if self.game_controller:
            return self.game_controller.board_controller.get_board_model()
        return None
    
    def get_board_controller(self):
        """Get the board controller for position updates.
        
        Returns:
            BoardController instance, or None if game_controller is not available.
        """
        if self.game_controller:
            return self.game_controller.board_controller
        return None
    
    def start_analysis(self, fen: Optional[str] = None) -> bool:
        """Start analysis for a position.
        
        Args:
            fen: FEN string of position to analyze.
            
        Returns:
            True if analysis started, False if no manual analysis engine configured.
        """
        # Update UI FIRST for immediate feedback - before any synchronous operations
        # Get current multipv from model BEFORE resetting
        multipv = self.analysis_model.multipv
        
        # Reset first (clears lines and sets is_analyzing to False)
        self.analysis_model.reset()
        # Then set is_analyzing to True (after reset) - this emits signal immediately
        self.analysis_model.is_analyzing = True
        
        # Create default lines immediately so UI shows them (even if in default state)
        # This ensures the UI displays the correct number of lines immediately
        self.analysis_model._lines.clear()
        for i in range(1, multipv + 1):
            self.analysis_model._lines.append(AnalysisLine(i))
        self.analysis_model.analysis_changed.emit()
        self.analysis_model.lines_changed.emit()
        
        # Show progress bar immediately with generic status
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Manual Analysis: Starting...")
        
        # Now do synchronous operations AFTER UI update
        # Get manual analysis engine assignment
        engine_id = self.engine_controller.get_engine_assignment(TASK_MANUAL_ANALYSIS)
        if not engine_id:
            # Failed - reset UI
            self.analysis_model.is_analyzing = False
            self.analysis_model.reset()
            self._expected_fen = None
            return False
        
        # Get engine data
        engine = self.engine_controller.get_engine_model().get_engine(engine_id)
        if not engine:
            # Failed - reset UI
            self.analysis_model.is_analyzing = False
            self.analysis_model.reset()
            self._expected_fen = None
            return False
        
        # Get FEN if not provided
        if fen is None:
            # Get current position from board controller
            # IMPORTANT: We need to analyze the position AFTER the active move has been played
            if self.game_controller and self.game_controller.board_controller:
                board_fen = self.game_controller.board_controller.get_position_fen()
                
                # Get the active game and ply_index to ensure we're getting the position AFTER the move
                game_model = self.game_controller.get_game_model()
                active_game = game_model.active_game if game_model else None
                ply_index = game_model.get_active_move_ply() if game_model else 0
                
                if active_game and ply_index > 0:
                    try:
                        import chess.pgn
                        from io import StringIO
                        
                        # Parse the PGN
                        pgn_io = StringIO(active_game.pgn)
                        chess_game = chess.pgn.read_game(pgn_io)
                        
                        if chess_game:
                            # Navigate to the position AFTER ply_index moves
                            node = chess_game
                            for i in range(ply_index):
                                if not node.variations:
                                    break
                                node = node.variation(0)
                            
                            # Get the FEN after ply_index moves (this is what we want to analyze)
                            fen = node.board().fen()
                        else:
                            fen = board_fen
                    except Exception:
                        fen = board_fen
                else:
                    fen = board_fen
            else:
                # Failed - reset UI
                self.analysis_model.is_analyzing = False
                self.analysis_model.reset()
                self._expected_fen = None
                return False
        
        # Track current engine ID
        self._current_engine_id = engine_id
        
        # Update expected FEN - we'll only accept updates for this FEN
        self._expected_fen = fen
        
        # Load actual threads value from engine parameters (not just config.json default)
        from app.services.engine_parameters_service import EngineParametersService
        engine_path = Path(engine.path)
        task_params = EngineParametersService.get_task_parameters_for_engine(
            engine_path,
            "manual_analysis",
            self.config
        )
        # Update max_threads with actual configured value
        self.max_threads = task_params.get("threads", self.max_threads)
        
        # Update progress status with actual engine name
        self.progress_service.set_status(f"Manual Analysis: {engine.name}...")
        
        # Start analysis
        
        # If evaluation bar is visible, switch it to use manual analysis data
        # Do this in background to avoid blocking
        if self._evaluation_controller:
            board_model = self.game_controller.board_controller.get_board_model()
            if board_model.show_evaluation_bar:
                # Switch to manual analysis in background (non-blocking)
                QTimer.singleShot(0, lambda: self._evaluation_controller._switch_to_manual_analysis())
        
        # Log manual analysis started
        logging_service = LoggingService.get_instance()
        logging_service.info(f"Manual analysis started: engine={engine.name}, FEN={fen[:50]}..., multipv={multipv}")
        
        # Start service in background (non-blocking) using QTimer
        # This allows the UI to update immediately before the service starts
        QTimer.singleShot(0, lambda: self.analysis_service.start_analysis(engine_path, fen, multipv))
        
        return True
    
    def stop_analysis(self, synchronous: bool = False) -> None:
        """Stop current analysis.
        
        Args:
            synchronous: If True, stop synchronously (wait for cleanup to complete).
                        If False, stop asynchronously using QTimer (default, for UI responsiveness).
        """
        # Stop debounce timer
        self._position_update_timer.stop()
        self._pending_position_fen = None
        
        # Update UI FIRST for immediate feedback
        # Set is_analyzing to False BEFORE switching evaluation controller
        # This ensures that when start_evaluation() checks, manual analysis is no longer running
        self.analysis_model.is_analyzing = False
        
        # Reset analysis model (clears lines) - this emits signals immediately
        self.analysis_model.reset()
        
        # Hide progress bar (only if evaluation bar is not visible, as it will manage it)
        if not (self._evaluation_controller and 
                self.game_controller.board_controller.get_board_model().show_evaluation_bar):
            self.progress_service.hide_progress()
        
        # Log manual analysis stopped
        logging_service = LoggingService.get_instance()
        logging_service.info("Manual analysis stopped")
        
        # Stop service - synchronously or asynchronously based on parameter
        if synchronous:
            # Synchronous stop (for shutdown) - call directly
            self._stop_service_in_background(keep_engine_alive=False)
        else:
            # Asynchronous stop (for normal UI interaction) - use QTimer
            QTimer.singleShot(0, lambda: self._stop_service_in_background(keep_engine_alive=False))
        
        # If evaluation bar is visible and using manual analysis, switch it back to evaluation engine
        # Skip this during synchronous shutdown to avoid restarting evaluation
        if not synchronous and self._evaluation_controller:
            board_model = self.game_controller.board_controller.get_board_model()
            if board_model.show_evaluation_bar:
                # Switch evaluation bar back to evaluation engine
                self._evaluation_controller._switch_away_from_manual_analysis()
                # Restart evaluation engine if bar is still visible
                # The start_evaluation() will check if thread is valid and reuse it if same engine
                fen = self.game_controller.board_controller.get_position_fen()
                self._evaluation_controller.start_evaluation(fen)
        
        # Update progress bar status
        self.progress_service.set_indeterminate(False)
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Ready")
        
        # Clear current engine ID
        self._current_engine_id = None
        
        # Clear best next move, PV2, and PV3 moves in board model
        board_model = self.game_controller.board_controller.get_board_model()
        
        # Clear positional plans
        board_model.set_positional_plans([])
        board_model.set_active_pv_plan(0)
        board_model.set_best_next_move(None)
        board_model.set_pv2_move(None)
        board_model.set_pv3_move(None)
    
    def _on_analysis_changed(self) -> None:
        """Handle analysis change - update best next move, PV2, and PV3 moves in board model."""
        # Only update moves if analysis is running
        if not self.analysis_model.is_analyzing:
            return
        
        board_model = self.game_controller.board_controller.get_board_model()
        board = board_model.board
        
        # Get the first PV line (multipv=1)
        first_line = self.analysis_model.get_line(1)
        if not first_line or not first_line.pv:
            # No PV available - clear best next move
            board_model.set_best_next_move(None)
        else:
            # Extract first move from PV string (space-separated moves)
            pv_moves = first_line.pv.strip().split()
            if not pv_moves:
                # Empty PV - clear best next move
                board_model.set_best_next_move(None)
            else:
                # Parse first move from PV
                try:
                    first_move = board.parse_san(pv_moves[0])
                    # Set best next move in board model
                    board_model.set_best_next_move(first_move)
                except (ValueError, chess.InvalidMoveError):
                    # Invalid move - clear best next move
                    board_model.set_best_next_move(None)
        
        # Get the second PV line (multipv=2)
        second_line = self.analysis_model.get_line(2)
        if not second_line or not second_line.pv:
            # No PV2 available - clear PV2 move
            board_model.set_pv2_move(None)
        else:
            # Extract first move from PV string (space-separated moves)
            pv_moves = second_line.pv.strip().split()
            if not pv_moves:
                # Empty PV - clear PV2 move
                board_model.set_pv2_move(None)
            else:
                # Parse first move from PV
                try:
                    first_move = board.parse_san(pv_moves[0])
                    # Set PV2 move in board model
                    board_model.set_pv2_move(first_move)
                except (ValueError, chess.InvalidMoveError):
                    # Invalid move - clear PV2 move
                    board_model.set_pv2_move(None)
        
        # Get the third PV line (multipv=3)
        third_line = self.analysis_model.get_line(3)
        if not third_line or not third_line.pv:
            # No PV3 available - clear PV3 move
            board_model.set_pv3_move(None)
        else:
            # Extract first move from PV string (space-separated moves)
            pv_moves = third_line.pv.strip().split()
            if not pv_moves:
                # Empty PV - clear PV3 move
                board_model.set_pv3_move(None)
            else:
                # Parse first move from PV
                try:
                    first_move = board.parse_san(pv_moves[0])
                    # Set PV3 move in board model
                    board_model.set_pv3_move(first_move)
                except (ValueError, chess.InvalidMoveError):
                    # Invalid move - clear PV3 move
                    board_model.set_pv3_move(None)
        
        # Update positional plan if exploration is active
        self._update_positional_plan()
        
        # Clear expected FEN - no longer expecting updates
        self._expected_fen = None
    
    def _stop_service_in_background(self, keep_engine_alive: bool = False) -> None:
        """Stop analysis service in background (non-blocking).
        
        Args:
            keep_engine_alive: If True, stop analysis but keep engine process alive (not used currently).
        """
        if self.analysis_service:
            self.analysis_service.stop_analysis(keep_engine_alive=keep_engine_alive)
    
    def update_position(self, fen: str) -> None:
        """Update analysis position.
        
        Args:
            fen: FEN string of new position.
        """
        # Only update position if analysis is supposed to be running
        if not self.analysis_model.is_analyzing:
            return
        
        # Check if we still have an engine assigned
        engine_id = self.engine_controller.get_engine_assignment(TASK_MANUAL_ANALYSIS)
        if not engine_id:
            # Engine was unassigned - stop analysis
            self.stop_analysis()
            return
        
        # Check if engine changed
        if engine_id != self._current_engine_id:
            # Engine changed - restart with new engine
            self.stop_analysis()
            self.start_analysis(fen)
            return
        
        # Store pending position and start/restart debounce timer
        # IMPORTANT: Only update if FEN is actually different from current pending FEN
        # This prevents unnecessary updates when the same position is requested multiple times
        if fen == self._pending_position_fen:
            return
        
        self._pending_position_fen = fen
        
        # Don't clear lines immediately - keep old lines visible until new data arrives
        # This prevents the UI flicker where lines disappear and reappear
        # The lines will be updated/cleared when new analysis data arrives from the engine
        
        # Restart debounce timer - this will delay the actual update
        self._position_update_timer.stop()
        self._position_update_timer.start(self._position_update_delay_ms)
    
    def _do_position_update(self) -> None:
        """Actually perform the position update (called by debounce timer)."""
        if not self._pending_position_fen:
            return
        
        fen = self._pending_position_fen
        self._pending_position_fen = None
        
        # Only update if analysis is still running
        if not self.analysis_model.is_analyzing:
            return
        
        # Clear old lines now, right before updating position
        # This minimizes the time lines are missing (they'll be repopulated as engine updates arrive)
        self.analysis_model._lines.clear()
        self.analysis_model.analysis_changed.emit()
        self.analysis_model.lines_changed.emit()
        
        # Update expected FEN - we'll only accept updates for this FEN
        # This prevents stale updates from previous positions from updating the lines
        self._expected_fen = fen
        
        # Update position in service
        try:
            self.analysis_service.update_position(fen)
        except Exception as e:
            # Don't stop analysis on error - let the service handle it
            self._on_analysis_error(f"Failed to update position: {str(e)}")
    
    def set_multipv(self, multipv: int) -> None:
        """Set number of analysis lines (multipv).
        
        Args:
            multipv: Number of lines to analyze (1-based, minimum 1).
        """
        # Update model FIRST for immediate UI feedback
        # This ensures the UI displays the correct number of lines immediately
        self.analysis_model.multipv = multipv
        
        # Then update service if analysis is running (happens in background thread)
        # This ensures the engine gets the new multipv value and restarts analysis
        if self.analysis_model.is_analyzing:
            # Update service - this will trigger engine restart with new multipv
            self.analysis_service.set_multipv(multipv)
    
    def add_pv_line(self) -> None:
        """Add an additional PV line by incrementing multipv."""
        if not self.analysis_model:
            return
        current_multipv = self.analysis_model.multipv
        new_multipv = current_multipv + 1
        self.set_multipv(new_multipv)
    
    def remove_pv_line(self) -> None:
        """Remove the last PV line by decrementing multipv (minimum 1)."""
        if not self.analysis_model:
            return
        # Decrease multipv (minimum 1, model will handle the rest)
        if self.analysis_model.multipv > 1:
            new_multipv = self.analysis_model.multipv - 1
            self.set_multipv(new_multipv)
    
    def _on_line_update(self, multipv: int, centipawns: float, is_mate: bool, mate_moves: int, depth: int, nps: int, hashfull: int, pv: str) -> None:
        """Handle analysis line update from service.
        
        Args:
            multipv: Line number (1-based).
            centipawns: Evaluation in centipawns.
            is_mate: True if mate score.
            mate_moves: Mate moves (positive for white, negative for black).
            depth: Current depth.
            nps: Nodes per second (-1 if not available).
            hashfull: Hash table usage 0-1000 (-1 if not available).
            pv: Principal variation as space-separated moves (empty string if not available).
        """
        # Check if this update matches the expected FEN
        # This prevents stale updates from previous positions from updating the lines
        # We can't directly check the FEN from the update, but we can check if we have an expected FEN
        # and if the service's thread has the same current_fen
        if self._expected_fen is not None:
            # Check if the service thread's current FEN matches our expected FEN
            # Also check if we're in the middle of a position update (which would mean we're waiting for new position)
            # If not, this update is for a stale position and should be ignored
            if self.analysis_service.analysis_thread:
                thread_current_fen = self.analysis_service.analysis_thread.current_fen
                is_updating_position = self.analysis_service.analysis_thread._updating_position
                
                # Ignore updates if:
                # 1. Thread's current_fen doesn't match expected FEN, OR
                # 2. We're in the middle of a position update
                # This ensures we only accept updates for the current position, not stale ones
                if thread_current_fen != self._expected_fen or is_updating_position:
                    # This update is for a different position or we're updating - ignore it
                    return
        
        # Update model (this will trigger UI updates)
        self.analysis_model.update_line(multipv, centipawns, is_mate, mate_moves, depth, pv, nps, hashfull)
        
        # Update progress bar with analysis details (use best line for status)
        # Use a timer to defer the status update, allowing UI to process events
        if multipv == 1:  # Only update status bar for best line (multipv 1)
            QTimer.singleShot(0, lambda: self._update_progress_status(depth, centipawns, is_mate, mate_moves, nps, hashfull, pv))
    
    def _update_progress_status(self, depth: int, centipawns: float, is_mate: bool, mate_moves: int, nps: int, hashfull: int, pv: str) -> None:
        """Update progress bar status with analysis details.
        
        Args:
            depth: Current analysis depth.
            centipawns: Evaluation in centipawns.
            is_mate: True if mate score.
            mate_moves: Mate moves (positive for white, negative for black).
            nps: Nodes per second (-1 if not available).
            hashfull: Hash table usage 0-1000 (-1 if not available).
            pv: Principal variation as space-separated moves (empty string if not available).
        """
        # Get engine name for status
        engine_id = self.engine_controller.get_engine_assignment(TASK_MANUAL_ANALYSIS)
        engine_name = "Engine"
        if engine_id:
            engine = self.engine_controller.get_engine_model().get_engine(engine_id)
            if engine:
                engine_name = engine.name
        
        # Format evaluation value
        if is_mate:
            if mate_moves > 0:
                eval_str = f"M{mate_moves}"  # White mates
            else:
                eval_str = f"M{abs(mate_moves)}"  # Black mates
        else:
            # Convert centipawns to pawns and format
            pawns = centipawns / 100.0
            if pawns > 0:
                eval_str = f"+{pawns:.2f}"
            else:
                eval_str = f"{pawns:.2f}"
        
        # Get number of lines being analyzed
        lines_count = self.analysis_model.multipv
        
        # Build status message with hardware info
        status_parts = [f"Manual Analysis: {engine_name}", f"Depth: {depth}", f"Eval: {eval_str}"]
        
        # Add lines count if more than 1
        if lines_count > 1:
            status_parts.append(f"Lines: {lines_count}")
        
        # Add thread count if configured
        if self.max_threads is not None:
            status_parts.append(f"Threads: {self.max_threads}")
        
        # Add nodes per second if available (nps >= 0 means available)
        if nps >= 0:
            # Format nps nicely (e.g., 1.5M, 500K, etc.)
            if nps >= 1_000_000:
                nps_str = f"{nps / 1_000_000:.1f}M"
            elif nps >= 1_000:
                nps_str = f"{nps / 1_000:.1f}K"
            else:
                nps_str = str(nps)
            status_parts.append(f"NPS: {nps_str}")
        
        # Add hash table usage if available (hashfull >= 0 means available)
        if hashfull >= 0:
            hash_percent = hashfull / 10.0  # hashfull is 0-1000, convert to percentage
            status_parts.append(f"Hash: {hash_percent:.1f}%")
        
        # Add principal variation if available (pv non-empty means available)
        # Truncate PV for status bar to keep it concise (first 5 moves)
        if pv:
            pv_moves = pv.strip().split()
            if len(pv_moves) > 5:
                status_pv = " ".join(pv_moves[:5]) + "..."
            else:
                status_pv = pv
            status_parts.append(f"PV: {status_pv}")
        
        status_message = " | ".join(status_parts)
        self.progress_service.set_status(status_message)
        
        # Update progress bar based on depth
        if self.max_depth is not None:
            # Capped depth - show as percentage (0-100% based on max_depth)
            # Disable indeterminate mode and show normal progress
            self.progress_service.set_indeterminate(False)
            progress_percent = int((depth / self.max_depth) * 100) if depth > 0 else 0
            progress_percent = min(100, max(0, progress_percent))
            self.progress_service.set_progress(progress_percent)
        else:
            # Uncapped/infinite depth - use indeterminate (pulsing) mode
            # For infinite analysis, there's no completion to track
            # Use pulsing indicator to show that analysis is running continuously
            self.progress_service.set_indeterminate(True)
    
    def _on_analysis_error(self, error_message: str) -> None:
        """Handle analysis error from service.
        
        Args:
            error_message: Error message.
        """
        # Don't set is_analyzing to False here - let the service try to recover
        # Only stop if we don't have an engine assigned
        engine_id = self.engine_controller.get_engine_assignment(TASK_MANUAL_ANALYSIS)
        if not engine_id:
            # No engine assigned - stop analysis
            self.stop_analysis()
            return
        
        # Update progress bar with error status
        self.progress_service.set_status(f"Manual Analysis error: {error_message}")
        
        # Try to restart analysis if we still have an engine assigned
        # The service will handle restarting if the position is updated
        if self.game_controller and self.game_controller.board_controller:
            # Get current position from board controller
            fen = self.game_controller.board_controller.get_position_fen()
            # Only restart if analysis is still supposed to be running
            if self.analysis_model.is_analyzing:
                # Try to restart after a short delay
                QTimer.singleShot(1000, lambda: self._restart_after_error(fen))
    
    def _restart_after_error(self, fen: str) -> None:
        """Restart analysis after an error.
        
        Args:
            fen: FEN string of position to analyze.
        """
        # Only restart if analysis is still supposed to be running
        if not self.analysis_model.is_analyzing:
            return
        
        try:
            # Stop the current analysis service completely (this will clean up the thread)
            self.analysis_service.stop_analysis()
            
            # Wait a moment for cleanup
            QTimer.singleShot(500, lambda: self._do_restart_after_error(fen))
        except Exception as e:
            # If restart fails, stop analysis
            self.stop_analysis()
    
    def _do_restart_after_error(self, fen: str) -> None:
        """Actually perform the restart after error cleanup.
        
        Args:
            fen: FEN string of position to analyze.
        """
        # Only restart if analysis is still supposed to be running
        if not self.analysis_model.is_analyzing:
            return
        
        try:
            # Restart analysis completely
            self.start_analysis(fen)
        except Exception as e:
            # If restart fails, stop analysis
            self.stop_analysis()
    
    def _on_engine_assignment_changed(self) -> None:
        """Handle engine assignment change from engine model.
        
        This handles the edge case where the user changes the manual analysis engine
        while analysis is running. We need to restart analysis with the new engine.
        """
        # Only handle if analysis is currently running
        if not self.analysis_model.is_analyzing:
            return
        
        # Get new engine assignment
        engine_id = self.engine_controller.get_engine_assignment(TASK_MANUAL_ANALYSIS)
        
        # Check if engine changed
        if engine_id != self._current_engine_id:
            # Engine changed - restart with new engine
            if self.game_controller and self.game_controller.board_controller:
                # Get current position from board controller
                fen = self.game_controller.board_controller.get_position_fen()
                # Stop current analysis and start with new engine
                self.stop_analysis()
                self.start_analysis(fen)
            else:
                # No board controller - just stop
                self.stop_analysis()
        elif engine_id is None:
            # Engine was unassigned - stop analysis
            self.stop_analysis()
    
    def _on_active_move_changed(self, ply_index: int) -> None:
        """Handle active move change from game model.
        
        Args:
            ply_index: Ply index of the active move (0 = starting position).
        """
        # Only update position if analysis is running
        if not self.analysis_model.is_analyzing:
            return
        
        # IMPORTANT: We need to analyze the position AFTER the active move has been played
        # The board controller's FEN might not be updated yet when this signal fires,
        # so we should ALWAYS get the FEN from the game tree based on ply_index
        if self.game_controller and self.game_controller.board_controller:
            game_model = self.game_controller.get_game_model()
            active_game = game_model.active_game if game_model else None
            
            if active_game and ply_index >= 0:
                # Get FEN from game tree - this is the most reliable source
                # and ensures we get the position AFTER ply_index moves
                try:
                    import chess.pgn
                    from io import StringIO
                    
                    # Parse the PGN
                    pgn_io = StringIO(active_game.pgn)
                    chess_game = chess.pgn.read_game(pgn_io)
                    
                    if chess_game:
                        # Navigate to the position AFTER ply_index moves
                        # This is the position we want to analyze
                        node = chess_game
                        for i in range(ply_index):
                            if not node.variations:
                                break
                            node = node.variation(0)
                        
                        # Get the FEN after ply_index moves (this is what we want to analyze)
                        fen = node.board().fen()
                    else:
                        # Fallback to board FEN if parsing fails
                        fen = self.game_controller.board_controller.get_position_fen()
                except Exception:
                    # If parsing fails, use board FEN (should still be correct)
                    fen = self.game_controller.board_controller.get_position_fen()
            else:
                # No active game or at starting position - use board FEN
                fen = self.game_controller.board_controller.get_position_fen()
            
            # Update position in analysis
            self.update_position(fen)
    
    def set_explore_pv_plan(self, pv_number: int) -> None:
        """Set which PV plan to explore (0 = none, 1-3 = PV1-PV3).
        
        Args:
            pv_number: 0 to disable, 1-3 for PV1-PV3.
        """
        if pv_number < 0 or pv_number > 3:
            pv_number = 0
        
        self._active_pv_plan = pv_number
        
        # Update board model
        board_model = self.game_controller.board_controller.get_board_model()
        board_model.set_active_pv_plan(pv_number)
        
        # Update positional plan if analysis is running
        if self.analysis_model.is_analyzing:
            self._update_positional_plan()
        else:
            # Clear plan if analysis is not running
            board_model.set_positional_plans([])
    
    def set_max_pieces_to_explore(self, max_pieces: int) -> None:
        """Set the maximum number of pieces to explore (1-3).
        
        Args:
            max_pieces: Maximum number of pieces to explore (1-3).
        """
        if max_pieces < 1 or max_pieces > 3:
            max_pieces = 1
        
        self._max_pieces_to_explore = max_pieces
        
        # Update positional plans if analysis is running
        if self.analysis_model.is_analyzing:
            self._update_positional_plan()
    
    def set_max_exploration_depth(self, max_depth: int) -> None:
        """Set the maximum exploration depth (2-4).
        
        Args:
            max_depth: Maximum number of moves to show in trajectory (2-4).
        """
        if max_depth < 2 or max_depth > 4:
            max_depth = 2
        
        self._max_exploration_depth = max_depth
        
        # Update positional plans if analysis is running
        if self.analysis_model.is_analyzing:
            self._update_positional_plan()
    
    def _update_positional_plan(self) -> None:
        """Update the positional plan based on active PV plan exploration."""
        if self._active_pv_plan == 0:
            # No plan exploration active
            board_model = self.game_controller.board_controller.get_board_model()
            board_model.set_positional_plans([])
            return
        
        # Get the PV line for the active plan
        line = self.analysis_model.get_line(self._active_pv_plan)
        if not line or not line.pv:
            # No PV available - clear plan but keep arrow visible (fallback behavior)
            board_model = self.game_controller.board_controller.get_board_model()
            board_model.set_positional_plans([])
            return
        
        # Get current position FEN
        board_model = self.game_controller.board_controller.get_board_model()
        current_fen = board_model.get_fen()
        
        # Extract plans from PV (up to max_pieces_to_explore)
        plans = self.pv_plan_parser.extract_plan(line.pv, current_fen, self._max_pieces_to_explore)
        
        if plans:
            # Limit each trajectory to max_exploration_depth moves
            limited_plans = []
            for plan in plans:
                # Truncate squares and ply_indices to max_exploration_depth
                limited_squares = plan.squares[:self._max_exploration_depth]
                limited_ply_indices = plan.ply_indices[:self._max_exploration_depth]
                
                # Only include the plan if it still has at least min_moves_for_plan moves
                if len(limited_squares) >= self.pv_plan_parser.min_moves_for_plan:
                    from app.services.pv_plan_parser_service import PieceTrajectory
                    limited_plan = PieceTrajectory(
                        piece_type=plan.piece_type,
                        piece_color=plan.piece_color,
                        squares=limited_squares,
                        ply_indices=limited_ply_indices,
                        starting_square=plan.starting_square
                    )
                    limited_plans.append(limited_plan)
            
            if limited_plans:
                # Plans detected - set them (arrow will be hidden automatically)
                board_model.set_positional_plans(limited_plans)
            else:
                # No plans after limiting - clear plans, show normal arrow (fallback behavior)
                board_model.set_positional_plans([])
        else:
            # No plans detected - clear plans, show normal arrow (fallback behavior)
            board_model.set_positional_plans([])

