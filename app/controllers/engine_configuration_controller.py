"""Engine configuration controller for managing engine parameter configuration."""

from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from PyQt6.QtCore import QObject, pyqtSignal

from app.services.engine_parameters_service import EngineParametersService
from app.services.engine_configuration_service import (
    EngineConfigurationService,
    TaskType,
    ValidationResult,
    ValidationSeverity,
)
from app.services.progress_service import ProgressService


class EngineConfigurationController(QObject):
    """Controller for managing engine parameter configuration.
    
    This controller orchestrates engine parameter operations including:
    - Loading engine options and parameters
    - Resetting parameters to defaults
    - Validating parameters
    - Saving parameters
    """
    
    # Signals for status updates
    status_update = pyqtSignal(str)  # Emitted when status changes
    
    # Task constants
    TASK_EVALUATION = "evaluation"
    TASK_GAME_ANALYSIS = "game_analysis"
    TASK_MANUAL_ANALYSIS = "manual_analysis"
    
    def __init__(self, config: Dict[str, Any], engine_path: Path, engine_controller) -> None:
        """Initialize the engine configuration controller.
        
        Args:
            config: Configuration dictionary.
            engine_path: Path to the engine executable.
            engine_controller: EngineController instance for accessing validation service.
        """
        super().__init__()
        self.config = config
        self.engine_path = engine_path
        self.engine_controller = engine_controller
        
        # Initialize services
        self.parameters_service = EngineParametersService.get_instance()
        self.config_service = EngineConfigurationService(config)
        self.progress_service = ProgressService.get_instance()
        
        # Load engine options
        self.parameters_service.load()
        self.engine_options = self.parameters_service.get_engine_options(str(self.engine_path))
        # Clipboard for Copy/Paste of engine-specific parameters (option_name -> value)
        self._engine_params_clipboard: Optional[Dict[str, Any]] = None

    def get_engine_options(self) -> List[Dict[str, Any]]:
        """Get engine options for the configured engine.
        
        Returns:
            List of engine option dictionaries.
        """
        return self.engine_options
    
    def get_task_parameters(self, task: str) -> Dict[str, Any]:
        """Get saved parameters for a specific task.
        
        Args:
            task: Task identifier (TASK_EVALUATION, TASK_GAME_ANALYSIS, TASK_MANUAL_ANALYSIS).
            
        Returns:
            Dictionary with parameter values.
        """
        return self.parameters_service.get_task_parameters(str(self.engine_path), task)
    
    def get_recommended_defaults(self, task: str) -> Dict[str, Any]:
        """Get recommended default values for a specific task.
        
        Args:
            task: Task identifier.
            
        Returns:
            Dictionary with recommended default values.
        """
        task_type_map = {
            self.TASK_EVALUATION: TaskType.EVALUATION,
            self.TASK_GAME_ANALYSIS: TaskType.GAME_ANALYSIS,
            self.TASK_MANUAL_ANALYSIS: TaskType.MANUAL_ANALYSIS
        }
        task_type = task_type_map.get(task, TaskType.EVALUATION)
        return self.config_service.get_recommended_defaults(task_type)

    def get_engine_param_names(self) -> List[str]:
        """Return list of engine option names (excluding 'Threads' and button types)."""
        names = []
        for option in self.engine_options:
            if option.get("type") == "button":
                continue
            if option.get("name") == "Threads":
                continue
            name = option.get("name", "")
            if name:
                names.append(name)
        return names

    def set_engine_params_clipboard(self, params: Dict[str, Any]) -> None:
        """Store engine-specific parameters for Paste."""
        self._engine_params_clipboard = dict(params)

    def get_engine_params_clipboard(self) -> Optional[Dict[str, Any]]:
        """Return copied engine-specific parameters, or None if nothing copied."""
        if not self._engine_params_clipboard:
            return None
        return dict(self._engine_params_clipboard)

    def has_engine_params_clipboard(self) -> bool:
        """Return True if there are parameters in the clipboard."""
        return bool(self._engine_params_clipboard)

    def parse_task_parameters_from_ui(self, raw: Dict[str, Any], task: str) -> Dict[str, Any]:
        """Parse raw widget state into task parameters (types and defaults).
        
        Args:
            raw: Raw state from view (strings for edit fields, bool for check, str for combo).
            task: Task identifier (determines which common params are forced to 0).
            
        Returns:
            Dictionary suitable for validate_parameters and save_parameters.
        """
        params = {}
        # Threads
        text = (raw.get("threads") or "").strip()
        if text:
            try:
                params["threads"] = int(round(float(text)))
            except (ValueError, OverflowError):
                params["threads"] = 1
        else:
            params["threads"] = 1
        # Depth: forced 0 for Game Analysis and Manual Analysis
        if task in (self.TASK_GAME_ANALYSIS, self.TASK_MANUAL_ANALYSIS):
            params["depth"] = 0
        else:
            text = (raw.get("depth") or "").strip()
            if text:
                try:
                    params["depth"] = int(round(float(text)))
                except (ValueError, OverflowError):
                    params["depth"] = 0
            else:
                params["depth"] = 0
        # Movetime: forced 0 for Evaluation and Manual Analysis
        if task in (self.TASK_EVALUATION, self.TASK_MANUAL_ANALYSIS):
            params["movetime"] = 0
        else:
            text = (raw.get("movetime") or "").strip()
            if text:
                try:
                    params["movetime"] = int(round(float(text)))
                except (ValueError, OverflowError):
                    params["movetime"] = 0
            else:
                params["movetime"] = 0
        # Engine options: raw keys are option names; preserve type (int/str/bool)
        option_names = self.get_engine_param_names()
        for name in option_names:
            if name not in raw:
                continue
            value = raw[name]
            if isinstance(value, bool):
                params[name] = value
            elif isinstance(value, str):
                value = value.strip()
                if value:
                    try:
                        params[name] = int(value)
                    except ValueError:
                        params[name] = value
                else:
                    params[name] = ""
            else:
                params[name] = value
        return params

    def get_defaults_for_task(self, task: str) -> Dict[str, Any]:
        """Return full default parameters for a task (common + engine-specific).
        
        Args:
            task: Task identifier.
            
        Returns:
            Dictionary with keys threads, depth, movetime, and engine option names.
        """
        out = self.get_recommended_defaults(task).copy()
        for option in self.engine_options:
            name = option.get("name", "")
            if not name or option.get("type") == "button" or name == "Threads":
                continue
            default = option.get("default")
            if default is not None:
                out[name] = default
            else:
                out[name] = "" if option.get("type") in ("string", "combo") else False
        return out

    def should_show_validation_dialog(self, validation_results: Dict[str, ValidationResult]) -> bool:
        """Return True if validation results contain issues the user should see."""
        for result in validation_results.values():
            if result.has_errors or result.has_warnings:
                return True
            for issue in result.issues:
                if issue.severity == ValidationSeverity.INFO:
                    return True
        return False

    def get_reset_error_dialog(self, success: bool, status_message: str) -> Optional[Tuple[str, str]]:
        """Return (title, message) for the error dialog to show after reset, or None."""
        if success:
            return None
        if "Failed to refresh" in status_message:
            return ("Refresh Failed", "Failed to refresh engine options. Using cached options.")
        return ("Reset Error", status_message)

    def notify_copy_engine_params(self) -> None:
        """Update progress service and status for copy engine-specific parameters."""
        self.progress_service.show_progress()
        self.progress_service.set_status("Copying engine-specific parameters...")
        self.status_update.emit("Copying engine-specific parameters...")
        self.progress_service.hide_progress()
        self.progress_service.set_status("Engine-specific parameters copied.")
        self.status_update.emit("Engine-specific parameters copied.")

    def notify_paste_engine_params(self) -> None:
        """Update progress service and status for paste engine-specific parameters."""
        self.progress_service.show_progress()
        self.progress_service.set_status("Pasting engine-specific parameters...")
        self.status_update.emit("Pasting engine-specific parameters...")
        self.progress_service.hide_progress()
        self.progress_service.set_status("Engine-specific parameters pasted.")
        self.status_update.emit("Engine-specific parameters pasted.")

    def reset_to_defaults(self, task: str) -> Tuple[bool, Optional[List[Dict[str, Any]]], str]:
        """Reset parameters to engine defaults for a specific task.
        
        This method refreshes engine options from the engine and returns
        the recommended defaults for the task.
        
        Args:
            task: Task identifier to reset.
            
        Returns:
            Tuple of (success: bool, refreshed_options: Optional[List[Dict]], status_message: str).
            If success is True, refreshed_options contains the updated engine options.
            If success is False, refreshed_options is None and status_message contains the error.
        """
        # Show progress and set initial status
        self.progress_service.show_progress()
        self.progress_service.set_status("Refreshing engine options from engine...")
        self.status_update.emit("Refreshing engine options from engine...")
        
        try:
            # Refresh engine options from the engine (without saving to file)
            validation_service = self.engine_controller.validation_service
            success, refreshed_options = validation_service.refresh_engine_options(
                self.engine_path,
                save_to_file=False  # Don't save to file - only update UI
            )
            
            if success and refreshed_options:
                # Update in-memory options with fresh defaults from engine
                self.engine_options = refreshed_options
                self.progress_service.set_status("Resetting parameters to engine defaults...")
                self.status_update.emit("Resetting parameters to engine defaults...")
                
                # Get recommended defaults for this task
                recommended_defaults = self.get_recommended_defaults(task)
                
                # Hide progress and set final status
                self.progress_service.hide_progress()
                self.progress_service.set_status("Parameters reset to engine defaults")
                self.status_update.emit("Parameters reset to engine defaults")
                
                return (True, refreshed_options, "Parameters reset to engine defaults")
            else:
                # If refresh failed, show error and use existing options
                self.progress_service.hide_progress()
                error_msg = "Failed to refresh engine options. Using cached options."
                self.progress_service.set_status(error_msg)
                self.status_update.emit(error_msg)
                return (False, None, error_msg)
        except Exception as e:
            self.progress_service.hide_progress()
            error_msg = f"Error refreshing engine options: {str(e)}"
            self.progress_service.set_status(error_msg)
            self.status_update.emit(error_msg)
            return (False, None, error_msg)

    def set_status(self, message: str) -> None:
        """Update progress service and status bar with a message."""
        self.progress_service.set_status(message)
        self.status_update.emit(message)

    def validate_parameters(self, task_params: Dict[str, Dict[str, Any]]) -> Dict[str, ValidationResult]:
        """Validate parameters for all tasks.
        
        Args:
            task_params: Dictionary mapping task identifiers to parameter dictionaries.
            
        Returns:
            Dictionary mapping task identifiers to ValidationResult objects.
        """
        # Show progress for validation
        self.progress_service.show_progress()
        self.progress_service.set_status("Validating parameters...")
        self.status_update.emit("Validating parameters...")
        
        task_type_map = {
            self.TASK_EVALUATION: TaskType.EVALUATION,
            self.TASK_GAME_ANALYSIS: TaskType.GAME_ANALYSIS,
            self.TASK_MANUAL_ANALYSIS: TaskType.MANUAL_ANALYSIS
        }
        
        validation_results = {}
        for task, parameters in task_params.items():
            task_type = task_type_map.get(task, TaskType.EVALUATION)
            validation_result = self.config_service.validate_parameters(task_type, parameters)
            validation_results[task] = validation_result
        
        # Hide progress after validation (will be shown again during save if needed)
        self.progress_service.hide_progress()
        
        return validation_results
    
    def save_parameters(self, task_params: Dict[str, Dict[str, Any]], engine_name: str) -> Tuple[bool, str]:
        """Save parameters to engine_parameters.json.
        
        Args:
            task_params: Dictionary mapping task identifiers to parameter dictionaries.
            engine_name: Name of the engine (for status message).
            
        Returns:
            Tuple of (success: bool, status_message: str).
        """
        # Show progress and set status
        self.progress_service.show_progress()
        self.progress_service.set_status("Saving parameters...")
        self.status_update.emit("Saving parameters...")
        
        try:
            # Prepare parameters for saving (separate common from engine-specific)
            tasks_parameters = {}
            for task, parameters in task_params.items():
                # Only save common parameters (threads, depth, movetime) and engine-specific options
                task_params_dict = {
                    "threads": parameters.get("threads", 1),
                    "depth": parameters.get("depth", 0),
                    "movetime": parameters.get("movetime", 0)
                }
                # Add engine-specific options (all keys that are not common parameters)
                for key, value in parameters.items():
                    if key not in ["threads", "depth", "movetime"]:
                        task_params_dict[key] = value
                
                tasks_parameters[task] = task_params_dict
            
            # Save to file
            self.parameters_service.set_all_task_parameters(str(self.engine_path), tasks_parameters)
            
            # Hide progress and set final status
            self.progress_service.hide_progress()
            status_msg = f"Engine configuration saved for {engine_name}"
            self.progress_service.set_status(status_msg)
            self.status_update.emit(status_msg)
            
            return (True, status_msg)
        except Exception as e:
            self.progress_service.hide_progress()
            error_msg = f"Error saving parameters: {str(e)}"
            self.progress_service.set_status(error_msg)
            self.status_update.emit(error_msg)
            return (False, error_msg)
    
    def get_task_type_enum(self) -> type:
        """Get the TaskType enum class.
        
        Returns:
            The TaskType enum class.
        """
        return TaskType
    
    def get_validation_severity_enum(self) -> type:
        """Get the ValidationSeverity enum class.
        
        Returns:
            The ValidationSeverity enum class.
        """
        from app.services.engine_configuration_service import ValidationSeverity
        return ValidationSeverity

