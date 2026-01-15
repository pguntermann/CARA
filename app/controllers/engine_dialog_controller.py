"""Controller for managing engine dialog operations."""

from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from PyQt6.QtCore import QObject, pyqtSignal, QThread

from app.services.progress_service import ProgressService
from app.services.engine_parameters_service import EngineParametersService
from app.services.engine_configuration_service import EngineConfigurationService, TaskType
from app.services.engine_validation_service import EngineValidationService


class EngineValidationThread(QThread):
    """Thread for validating engine in background."""
    
    validation_complete = pyqtSignal(bool, str, str, str)  # success, error, name, author
    
    def __init__(self, engine_path: Path, validation_service) -> None:
        """Initialize validation thread.
        
        Args:
            engine_path: Path to engine executable.
            validation_service: EngineValidationService instance.
        """
        super().__init__()
        self.engine_path = engine_path
        self.validation_service = validation_service
        self._validation_result: Optional[Any] = None  # Store validation result for options retrieval
    
    def run(self) -> None:
        """Run engine validation."""
        # Don't save to file during validation - only when user clicks "Add Engine"
        result = self.validation_service.validate_engine(self.engine_path, save_to_file=False)
        
        if result.is_valid:
            self.validation_complete.emit(True, "", result.name, result.author)
        else:
            self.validation_complete.emit(False, result.error_message, "", "")


class EngineDialogController(QObject):
    """Controller for orchestrating engine dialog operations.
    
    This controller handles the business logic for engine validation,
    version extraction, and engine addition operations.
    """
    
    # Signal emitted when validation completes
    validation_complete = pyqtSignal(bool, str, str, str)  # success, error, name, author
    
    def __init__(self, config: Dict[str, Any], engine_controller) -> None:
        """Initialize the engine dialog controller.
        
        Args:
            config: Configuration dictionary.
            engine_controller: EngineController instance.
        """
        super().__init__()
        self.config = config
        self.engine_controller = engine_controller
        self.progress_service = ProgressService.get_instance()
        self.validation_thread: Optional[EngineValidationThread] = None
        # Cache validated engine options by engine path (cleared when dialog closes)
        self._cached_options: Dict[Path, List[Dict[str, Any]]] = {}
    
    def set_status(self, message: str) -> None:
        """Set status message.
        
        Args:
            message: Status message to display.
        """
        self.progress_service.set_status(message)
    
    def show_progress(self) -> None:
        """Show progress bar."""
        self.progress_service.show_progress()
    
    def hide_progress(self) -> None:
        """Hide progress bar."""
        self.progress_service.hide_progress()
    
    def set_indeterminate(self, indeterminate: bool) -> None:
        """Set progress bar indeterminate state.
        
        Args:
            indeterminate: True for indeterminate progress, False for determinate.
        """
        self.progress_service.set_indeterminate(indeterminate)
    
    def start_validation(self, engine_path: Path) -> None:
        """Start engine validation in background thread.
        
        Args:
            engine_path: Path to engine executable.
        """
        # Log engine validation started
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance()
        logging_service.info(f"Engine validation started: path={engine_path}")
        
        # Show progress and set status
        self.show_progress()
        self.set_indeterminate(True)
        self.set_status("Validating engine... Please wait.")
        
        # Start validation in background thread
        self.validation_thread = EngineValidationThread(
            engine_path,
            self.engine_controller.validation_service
        )
        self.validation_thread.validation_complete.connect(self._on_validation_complete)
        # Store engine_path for caching options later
        self._current_validation_path = engine_path
        self.validation_thread.start()
    
    def _on_validation_complete(self, success: bool, error: str, name: str, author: str) -> None:
        """Handle validation completion from thread.
        
        Args:
            success: True if validation succeeded.
            error: Error message if validation failed.
            name: Engine name if validation succeeded.
            author: Engine author if validation succeeded.
        """
        # Cache options from validation result if validation succeeded
        if success and self.validation_thread and hasattr(self.validation_thread, '_validation_result'):
            result = self.validation_thread._validation_result
            if result and result.is_valid and hasattr(self, '_current_validation_path'):
                self._cached_options[self._current_validation_path] = result.options
        
        # Log engine validation completed
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance()
        if success:
            logging_service.info(f"Engine validation completed: success=True, name={name}, author={author}")
        else:
            logging_service.warning(f"Engine validation completed: success=False, error={error}")
        
        # Hide progress bar
        self.hide_progress()
        self.set_indeterminate(False)
        
        # Forward signal to view
        self.validation_complete.emit(success, error, name, author)
    
    def extract_version(self, author: str, name: str) -> str:
        """Extract version string from author or name.
        
        Args:
            author: Author string from engine.
            name: Name string from engine.
            
        Returns:
            Version string if found, empty string otherwise.
        """
        return EngineValidationService._extract_version(author, name)
    
    def check_engine_exists(self, engine_path: Path) -> Tuple[bool, Optional[str]]:
        """Check if an engine with the same path already exists.
        
        Args:
            engine_path: Path to engine executable.
            
        Returns:
            Tuple of (exists: bool, error_message: Optional[str]).
            If exists is True, error_message contains the error description.
        """
        existing_engine = self.engine_controller.get_engine_model().get_engine_by_path(str(engine_path))
        if existing_engine:
            return (True, f"An engine with path '{engine_path}' is already configured.")
        return (False, None)
    
    def prepare_engine_for_addition(self, engine_path: Path) -> Tuple[bool, str]:
        """Prepare engine for addition by saving options and recommended defaults.
        
        This method:
        1. Uses cached engine options from validation (or refreshes if not cached)
        2. Saves engine options and recommended defaults for all tasks in one operation
        
        Args:
            engine_path: Path to engine executable.
            
        Returns:
            Tuple of (success: bool, error_message: str).
            If success is True, error_message is empty.
        """
        try:
            # Get parameters service and ensure data is loaded
            parameters_service = EngineParametersService.get_instance()
            parameters_service.load()
            
            # Get cached options from validation, or refresh if not available
            options = self._cached_options.get(engine_path)
            if not options:
                # Fallback: refresh options if not cached (shouldn't happen in normal flow)
                validation_service = self.engine_controller.validation_service
                options_saved, options = validation_service.refresh_engine_options(
                    engine_path,
                    save_to_file=False  # Don't save yet, we'll save everything together
                )
                if not options_saved or not options:
                    return (False, "Failed to retrieve engine options")
            
            # Set engine options in memory (without saving)
            engine_path_str = str(engine_path)
            if engine_path_str not in parameters_service.get_parameters():
                parameters_service.get_parameters()[engine_path_str] = {}
            parameters_service.get_parameters()[engine_path_str]["options"] = options
            
            # Get recommended defaults for each task
            config_service = EngineConfigurationService(self.config)
            tasks_parameters = {
                "evaluation": config_service.get_recommended_defaults(TaskType.EVALUATION),
                "game_analysis": config_service.get_recommended_defaults(TaskType.GAME_ANALYSIS),
                "manual_analysis": config_service.get_recommended_defaults(TaskType.MANUAL_ANALYSIS)
            }
            
            # Set task parameters in memory (without saving)
            parameters_service.get_parameters()[engine_path_str]["tasks"] = tasks_parameters
            
            # Save everything in one operation (both options and task parameters)
            parameters_service.save()
            
            return (True, "")
        except Exception as e:
            return (False, f"Failed to prepare engine: {str(e)}")
    
    def add_engine(self, engine_path: Path, name: str, author: str, version: str) -> Tuple[bool, str]:
        """Add engine through engine controller.
        
        Args:
            engine_path: Path to engine executable.
            name: Engine name.
            author: Engine author.
            version: Engine version.
            
        Returns:
            Tuple of (success: bool, message: str).
        """
        success, message, engine = self.engine_controller.add_engine(
            engine_path,
            name,
            author,
            version
        )
        return (success, message)
    
    def cancel_validation(self) -> None:
        """Cancel validation thread if running."""
        if self.validation_thread and self.validation_thread.isRunning():
            self.validation_thread.terminate()
            self.validation_thread.wait()

