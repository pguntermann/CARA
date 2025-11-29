"""Engine controller for managing UCI engine operations."""

from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
import uuid

from app.models.engine_model import EngineModel, EngineData
from app.services.engine_validation_service import EngineValidationService

# Task constants (re-exported from model for convenience)
TASK_GAME_ANALYSIS = EngineModel.TASK_GAME_ANALYSIS
TASK_EVALUATION = EngineModel.TASK_EVALUATION
TASK_MANUAL_ANALYSIS = EngineModel.TASK_MANUAL_ANALYSIS


class EngineController:
    """Controller for managing UCI engine operations.
    
    This controller orchestrates engine-related operations and manages
    the engine model.
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the engine controller.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config
        
        # Initialize engine model
        self.engine_model = EngineModel()
        
        # Initialize validation service
        self._validation_service = EngineValidationService()
    
    @property
    def validation_service(self) -> EngineValidationService:
        """Get the validation service.
        
        Returns:
            The EngineValidationService instance.
        """
        return self._validation_service
    
    def get_engine_model(self) -> EngineModel:
        """Get the engine model.
        
        Returns:
            The EngineModel instance for observing engine state.
        """
        return self.engine_model
    
    def validate_engine(self, engine_path: Path) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """Validate an engine executable.
        
        Args:
            engine_path: Path to engine executable.
            
        Returns:
            Tuple of (success: bool, error_message: str, engine_name: Optional[str], engine_author: Optional[str]).
            If success is True, engine_name and engine_author contain the engine info.
            If success is False, error_message contains the error description.
        """
        result = self._validation_service.validate_engine(engine_path)
        
        if result.is_valid:
            return (True, "", result.name, result.author)
        else:
            return (False, result.error_message, None, None)
    
    def add_engine(self, engine_path: Path, name: str, author: str, version: str) -> Tuple[bool, str, Optional[EngineData]]:
        """Add an engine to the model.
        
        Args:
            engine_path: Path to engine executable.
            name: Engine name.
            author: Engine author.
            version: Engine version.
            
        Returns:
            Tuple of (success: bool, message: str, engine: Optional[EngineData]).
            If success is True, message indicates success and engine contains the added engine.
            If success is False, message contains error description and engine is None.
        """
        # Check if engine with same path already exists
        existing_engine = self.engine_model.get_engine_by_path(str(engine_path))
        if existing_engine:
            return (False, f"Engine with path '{engine_path}' is already configured", None)
        
        # Create engine data
        engine = EngineData(
            id=str(uuid.uuid4()),
            path=str(engine_path),
            name=name,
            author=author,
            version=version,
            is_valid=True,
            validation_error="",
            last_validated=datetime.now().isoformat()
        )
        
        # Add to model
        if self.engine_model.add_engine(engine):
            return (True, f"Engine '{name}' added successfully", engine)
        else:
            return (False, "Failed to add engine (duplicate ID)", None)
    
    def remove_engine(self, engine_id: str) -> Tuple[bool, str]:
        """Remove an engine from the model.
        
        Args:
            engine_id: Engine ID to remove.
            
        Returns:
            Tuple of (success: bool, message: str).
            If success is True, message indicates success.
            If success is False, message contains error description.
        """
        engine = self.engine_model.get_engine(engine_id)
        if not engine:
            return (False, f"Engine with ID '{engine_id}' not found")
        
        # Remove engine options from engine_parameters.json
        from app.services.engine_parameters_service import EngineParametersService
        from pathlib import Path
        parameters_service = EngineParametersService.get_instance()
        parameters_service.load()
        engine_path = str(Path(engine.path))
        parameters_service.remove_engine_options(engine_path)
        
        if self.engine_model.remove_engine(engine_id):
            return (True, f"Engine '{engine.name}' removed successfully")
        else:
            return (False, "Failed to remove engine")
    
    def get_engines(self) -> List[EngineData]:
        """Get list of all configured engines.
        
        Returns:
            List of EngineData instances.
        """
        return self.engine_model.get_engines()
    
    def set_engine_assignment(self, task: str, engine_id: str) -> Tuple[bool, str]:
        """Set the engine assignment for a task.
        
        This will unassign other engines from the same task.
        
        Args:
            task: Task constant (TASK_GAME_ANALYSIS, TASK_EVALUATION, TASK_MANUAL_ANALYSIS).
            engine_id: Engine ID to assign.
            
        Returns:
            Tuple of (success: bool, message: str).
            If success is True, message indicates success.
            If success is False, message contains error description.
        """
        # Validate engine exists
        engine = self.engine_model.get_engine(engine_id)
        if not engine:
            return (False, f"Engine with ID '{engine_id}' not found")
        
        # Set assignment (this will unassign other engines from this task implicitly)
        if self.engine_model.set_assignment(task, engine_id):
            task_name = self._get_task_display_name(task)
            return (True, f"'{engine.name}' set as {task_name}")
        else:
            return (False, f"Invalid task or engine ID")
    
    def get_engine_assignment(self, task: str) -> Optional[str]:
        """Get the engine ID assigned to a task.
        
        Args:
            task: Task constant (TASK_GAME_ANALYSIS, TASK_EVALUATION, TASK_MANUAL_ANALYSIS).
            
        Returns:
            Engine ID or None if no engine is assigned.
        """
        return self.engine_model.get_assignment(task)
    
    def get_all_assignments(self) -> Dict[str, Optional[str]]:
        """Get all engine assignments.
        
        Returns:
            Dictionary mapping tasks to engine IDs (or None).
        """
        return self.engine_model.get_assignments()
    
    def _get_task_display_name(self, task: str) -> str:
        """Get display name for a task.
        
        Args:
            task: Task constant.
            
        Returns:
            Display name for the task.
        """
        task_names = {
            EngineModel.TASK_GAME_ANALYSIS: "Game Analysis Engine",
            EngineModel.TASK_EVALUATION: "Evaluation Engine",
            EngineModel.TASK_MANUAL_ANALYSIS: "Manual Analysis Engine"
        }
        return task_names.get(task, task)

