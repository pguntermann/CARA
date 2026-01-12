"""Evaluation controller for managing position evaluation."""

from pathlib import Path
from typing import Dict, Any, Optional
from PyQt6.QtCore import QTimer

from app.models.evaluation_model import EvaluationModel
from app.services.evaluation_engine_service import EvaluationEngineService
from app.services.progress_service import ProgressService
from app.services.logging_service import LoggingService
from app.controllers.engine_controller import TASK_EVALUATION


class EvaluationController:
    """Controller for managing position evaluation.
    
    This controller orchestrates evaluation operations and manages
    the evaluation model and engine service.
    """
    
    def __init__(self, config: Dict[str, Any], engine_controller, manual_analysis_controller=None) -> None:
        """Initialize the evaluation controller.
        
        Args:
            config: Configuration dictionary.
            engine_controller: EngineController instance for getting evaluation engine.
            manual_analysis_controller: Optional ManualAnalysisController instance for sharing engine.
        """
        self.config = config
        self.engine_controller = engine_controller
        self.manual_analysis_controller = manual_analysis_controller
        
        # Initialize evaluation model
        self.evaluation_model = EvaluationModel()
        
        # Initialize evaluation engine service
        self.evaluation_service = EvaluationEngineService(config)
        
        # Get progress service for status updates
        self.progress_service = ProgressService.get_instance()
        
        # Get max depth for progress calculation
        # Note: max_depth_evaluation is now 0 (infinite analysis) by default
        # We use it for progress calculation, but if it's 0, we can't calculate progress
        self.max_depth = config.get("ui", {}).get("panels", {}).get("main", {}).get("board", {}).get("evaluation_bar", {}).get("max_depth_evaluation", 0)
        
        # Connect service signals to model
        self.evaluation_service.evaluation_update.connect(self._on_evaluation_update)
        self.evaluation_service.error_occurred.connect(self._on_evaluation_error)
        
        # Get configured thread count for status display
        eval_bar_config = config.get("ui", {}).get("panels", {}).get("main", {}).get("board", {}).get("evaluation_bar", {})
        self.max_threads = eval_bar_config.get("max_threads", None)
        
        # Track if we're using manual analysis data
        self._using_manual_analysis = False
    
    def get_evaluation_model(self) -> EvaluationModel:
        """Get the evaluation model.
        
        Returns:
            The EvaluationModel instance for observing evaluation state.
        """
        return self.evaluation_model
    
    def start_evaluation(self, fen: str) -> bool:
        """Start evaluation for a position.
        
        Args:
            fen: FEN string of position to evaluate.
            
        Returns:
            True if evaluation started, False if no evaluation engine configured.
        """
        # Check if manual analysis is running - if so, use its data instead
        if self.manual_analysis_controller:
            analysis_model = self.manual_analysis_controller.get_analysis_model()
            if analysis_model.is_analyzing:
                # Manual analysis is running - use its data instead of starting evaluation engine
                # Disconnect signal first to prevent any pending updates
                try:
                    self.evaluation_service.evaluation_update.disconnect(self._on_evaluation_update)
                except TypeError:
                    pass
                self._switch_to_manual_analysis()
                # Don't show progress bar here - manual analysis already manages it
                # The status will be updated by manual analysis controller
                return True
        
        # If already using manual analysis, don't start evaluation engine
        if self._using_manual_analysis:
            return True
        
        # Get evaluation engine assignment
        engine_id = self.engine_controller.get_engine_assignment(TASK_EVALUATION)
        if not engine_id:
            return False
        
        # Get engine data
        engine = self.engine_controller.get_engine_model().get_engine(engine_id)
        if not engine:
            return False
        
        # Ensure we're not using manual analysis before starting
        if self._using_manual_analysis:
            return True
        
        # Reconnect signal if it was disconnected
        try:
            self.evaluation_service.evaluation_update.connect(self._on_evaluation_update)
        except TypeError:
            pass  # Already connected
        
        # Log evaluation started
        logging_service = LoggingService.get_instance()
        logging_service.info(f"Evaluation started: engine={engine.name}, FEN={fen[:50]}...")
        
        # Start evaluation
        engine_path = Path(engine.path)
        
        # Load actual threads value from engine parameters (not just config.json default)
        from app.services.engine_parameters_service import EngineParametersService
        task_params = EngineParametersService.get_task_parameters_for_engine(
            engine_path,
            "evaluation",
            self.config
        )
        # Update max_threads with actual configured value
        self.max_threads = task_params.get("threads", self.max_threads)
        
        self.evaluation_model.is_evaluating = True
        self.evaluation_model.reset()
        
        # Show progress bar and set initial status
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status(f"Engine analyzing: {engine.name}...")
        
        self._using_manual_analysis = False
        return self.evaluation_service.start_evaluation(engine_path, fen)
    
    def update_position(self, fen: str) -> None:
        """Update evaluation position.
        
        Args:
            fen: FEN string of new position.
        """
        # If using manual analysis, don't update position here (manual analysis handles it)
        if self._using_manual_analysis:
            return
        
        # Check if manual analysis is running - if so, switch to it instead
        if self.manual_analysis_controller:
            analysis_model = self.manual_analysis_controller.get_analysis_model()
            if analysis_model.is_analyzing:
                # Manual analysis is running - switch to it
                self._switch_to_manual_analysis()
                return
        
        # Always update position if evaluation is supposed to be running
        # Check if we have an engine assigned first
        engine_id = self.engine_controller.get_engine_assignment(TASK_EVALUATION)
        if not engine_id:
            return
        
        # Check if evaluation thread exists and is running (don't rely on model flag)
        thread_exists = self.evaluation_service.evaluation_thread is not None
        thread_is_running = False
        if thread_exists:
            thread_is_running = self.evaluation_service.evaluation_thread.running
        
        # Reset evaluation model to clear old values first (before updating position)
        # This ensures the bar shows empty/zero while new evaluation starts
        self.evaluation_model.reset()
        
        # If thread exists, always update position (never restart)
        if thread_exists:
            # Update position in service
            self.evaluation_service.update_position(fen)
            # Mark as evaluating again (reset() might have cleared it)
            self.evaluation_model.is_evaluating = True
        else:
            # No thread exists - start evaluation
            # This handles the case where evaluation stopped but bar is still visible
            self.start_evaluation(fen)
    
    def stop_evaluation(self) -> None:
        """Stop current evaluation."""
        # Disconnect from manual analysis if we were using it
        if self._using_manual_analysis:
            self._switch_away_from_manual_analysis()
        
        # Disconnect signal first to prevent any updates during shutdown
        try:
            self.evaluation_service.evaluation_update.disconnect(self._on_evaluation_update)
        except TypeError:
            pass  # Not connected, ignore
        
        # Log evaluation stopped
        logging_service = LoggingService.get_instance()
        logging_service.info("Evaluation stopped")
        
        # Stop evaluation service (this ensures no more updates are emitted)
        self.evaluation_service.stop_evaluation()
        self._using_manual_analysis = False  # Ensure flag is cleared
        self.evaluation_model.is_evaluating = False
        self.evaluation_model.reset()
        
        # Hide progress bar (only if not using manual analysis)
        if not self._using_manual_analysis:
            self.progress_service.hide_progress()
            self.progress_service.set_progress(0)
    
    def _on_evaluation_update(self, centipawns: float, is_mate: bool, mate_moves: int, depth: int, nps: int, hashfull: int, pv: str) -> None:
        """Handle evaluation update from service.
        
        Args:
            centipawns: Evaluation in centipawns.
            is_mate: True if mate score.
            mate_moves: Mate moves (positive for white, negative for black).
            depth: Current depth.
            nps: Nodes per second (-1 if not available).
            hashfull: Hash table usage 0-1000 (-1 if not available).
            pv: Principal variation as space-separated moves (empty string if not available).
        """
        # Don't process updates if we're using manual analysis
        if self._using_manual_analysis:
            return
        
        # Update model (this will trigger UI updates)
        self.evaluation_model.centipawns = centipawns
        self.evaluation_model.is_mate = is_mate
        self.evaluation_model.mate_moves = mate_moves
        self.evaluation_model.depth = depth
        
        # Update progress bar with evaluation details
        # Use a timer to defer the status update, allowing UI to process events
        QTimer.singleShot(0, lambda: self._update_progress_status(depth, centipawns, is_mate, mate_moves, nps, hashfull, pv))
    
    def _update_progress_status(self, depth: int, centipawns: float, is_mate: bool, mate_moves: int, nps: int, hashfull: int, pv: str) -> None:
        """Update progress bar status with evaluation details.
        
        Args:
            depth: Current evaluation depth.
            centipawns: Evaluation in centipawns.
            is_mate: True if mate score.
            mate_moves: Mate moves (positive for white, negative for black).
            nps: Nodes per second (-1 if not available).
            hashfull: Hash table usage 0-1000 (-1 if not available).
            pv: Principal variation as space-separated moves (empty string if not available).
        """
        # Don't update status if we're using manual analysis (manual analysis handles it)
        if self._using_manual_analysis:
            return
        
        # Get engine name for status
        engine_id = self.engine_controller.get_engine_assignment(TASK_EVALUATION)
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
        
        # Build status message with hardware info
        status_parts = [f"Engine analyzing: {engine_name}", f"Depth: {depth}", f"Eval: {eval_str}"]
        
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
        if pv:
            status_parts.append(f"PV: {pv}")
        
        status_message = " | ".join(status_parts)
        self.progress_service.set_status(status_message)
        
        # Update progress bar based on depth
        if self.max_depth > 0 and depth > 0:
            # Capped depth - show as percentage (0-100% based on max_depth)
            # Disable indeterminate mode and show normal progress
            self.progress_service.set_indeterminate(False)
            progress_percent = int((depth / self.max_depth) * 100)
            progress_percent = min(100, max(0, progress_percent))
            self.progress_service.set_progress(progress_percent)
        else:
            # Infinite analysis (max_depth = 0) or no depth - use indeterminate (pulsing) mode
            # For infinite analysis, there's no completion to track
            # Use pulsing indicator to show that analysis is running continuously
            self.progress_service.set_indeterminate(True)
    
    def _on_evaluation_error(self, error_message: str) -> None:
        """Handle evaluation error from service.
        
        Args:
            error_message: Error message.
        """
        # Mark as not evaluating temporarily
        self.evaluation_model.is_evaluating = False
        
        # Update progress bar with error status
        self.progress_service.set_status(f"Evaluation error: {error_message}")
        
        # Try to restart evaluation if we still have an engine path
        # The service will handle restarting if the bar is still visible
        # by checking when update_position is called
    
    def _switch_to_manual_analysis(self) -> None:
        """Switch evaluation bar to use manual analysis data instead of evaluation engine."""
        if self._using_manual_analysis:
            return  # Already using manual analysis
        
        # Disconnect from evaluation service signals FIRST to prevent any pending updates
        try:
            self.evaluation_service.evaluation_update.disconnect(self._on_evaluation_update)
        except TypeError:
            pass  # Not connected, ignore
        
        # Set flag to prevent processing any pending evaluation updates
        self._using_manual_analysis = True
        
        # Check if manual analysis uses the same engine - if so, suspend instead of stopping
        if self.manual_analysis_controller:
            manual_engine_id = self.manual_analysis_controller._current_engine_id
            evaluation_engine_id = self.engine_controller.get_engine_assignment(TASK_EVALUATION)
            
            if manual_engine_id and evaluation_engine_id and manual_engine_id == evaluation_engine_id:
                # Same engine - suspend evaluation (keep engine process alive)
                self.evaluation_service.suspend_evaluation()
            else:
                # Different engine - stop evaluation normally
                self.evaluation_service.stop_evaluation()
        else:
            # No manual analysis controller - stop evaluation normally
            self.evaluation_service.stop_evaluation()
        
        # Wait a moment for any pending signals to be processed (with flag set, they'll be ignored)
        QTimer.singleShot(50, lambda: None)  # Small delay to let pending signals clear
        
        # Hide progress bar from evaluation only if manual analysis is not managing it
        # (If manual analysis is running, it will manage the progress bar)
        if self.manual_analysis_controller:
            analysis_model = self.manual_analysis_controller.get_analysis_model()
            if not analysis_model.is_analyzing:
                # Manual analysis not running, hide progress bar
                self.progress_service.hide_progress()
                self.progress_service.set_progress(0)
        
        # Connect to manual analysis model
        if self.manual_analysis_controller:
            analysis_model = self.manual_analysis_controller.get_analysis_model()
            # Connect to analysis_changed signal to update evaluation model
            analysis_model.analysis_changed.connect(self._on_manual_analysis_changed)
            # Update immediately with current best line
            self._on_manual_analysis_changed()
    
    def _switch_away_from_manual_analysis(self) -> None:
        """Switch evaluation bar back to using evaluation engine."""
        if not self._using_manual_analysis:
            return  # Not using manual analysis
        
        # Disconnect from manual analysis model
        if self.manual_analysis_controller:
            analysis_model = self.manual_analysis_controller.get_analysis_model()
            try:
                analysis_model.analysis_changed.disconnect(self._on_manual_analysis_changed)
            except TypeError:
                pass  # Not connected, ignore
        
        self._using_manual_analysis = False
        
        # Reconnect to evaluation service signals
        try:
            self.evaluation_service.evaluation_update.connect(self._on_evaluation_update)
        except TypeError:
            pass  # Already connected, ignore
        
        # Clear evaluation model (will be updated by evaluation engine when it starts)
        self.evaluation_model.reset()
    
    def _on_manual_analysis_changed(self) -> None:
        """Handle manual analysis change - update evaluation model from best line."""
        if not self.manual_analysis_controller:
            return
        
        analysis_model = self.manual_analysis_controller.get_analysis_model()
        best_line = analysis_model.get_best_line()
        
        if best_line:
            # Update evaluation model from best line
            self.evaluation_model.update_from_analysis_line(best_line)
        else:
            # No best line yet - reset evaluation
            self.evaluation_model.reset()

