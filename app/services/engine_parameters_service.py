"""Engine parameters service for managing engine option persistence."""

import json
import sys
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List

from app.utils.path_resolver import resolve_data_file_path


class EngineParametersService:
    """Service for managing engine parameters persistence.
    
    This service handles loading and saving engine options to a JSON file.
    Parameters are stored in the app root directory as engine_parameters.json.
    
    The service follows a singleton pattern to ensure a single source of truth
    and avoid repeated file I/O operations.
    """
    
    DEFAULT_PARAMETERS = {}
    _instance: Optional['EngineParametersService'] = None
    _lock = threading.Lock()  # Thread safety for file operations
    
    def __new__(cls) -> 'EngineParametersService':
        """Singleton pattern: ensure only one instance exists."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    # Initialize instance variables using smart path resolution
                    # Check write access to app root, fall back to user data directory if needed
                    cls._instance.parameters_path, _ = resolve_data_file_path("engine_parameters.json")
                    cls._instance._parameters: Dict[str, Any] = {}
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> 'EngineParametersService':
        """Get the singleton instance of EngineParametersService.
        
        Returns:
            The singleton EngineParametersService instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def __init__(self) -> None:
        """Initialize the engine parameters service.
        
        Note: This is called only once due to singleton pattern.
        The actual initialization happens in __new__.
        """
        # Initialization is done in __new__ to ensure singleton
        pass
    
    def load(self) -> Dict[str, Any]:
        """Load engine parameters from file.
        
        Returns:
            Loaded parameters dictionary. If file doesn't exist, returns default parameters.
        """
        with self._lock:
            if not self.parameters_path.exists():
                # File doesn't exist, return default parameters
                self._parameters = self._deep_copy(self.DEFAULT_PARAMETERS)
                return self._parameters
            
            try:
                with open(self.parameters_path, "r", encoding="utf-8") as f:
                    self._parameters = json.load(f)
                
                # Ensure parameters is a dictionary
                if not isinstance(self._parameters, dict):
                    self._parameters = self._deep_copy(self.DEFAULT_PARAMETERS)
                
                return self._parameters
            except (json.JSONDecodeError, IOError) as e:
                # If file is corrupted or can't be read, use defaults
                print(f"Warning: Failed to load engine parameters: {e}. Using defaults.", file=sys.stderr)
                self._parameters = self._deep_copy(self.DEFAULT_PARAMETERS)
                return self._parameters
    
    def reload(self) -> Dict[str, Any]:
        """Reload engine parameters from file, discarding any cached data.
        
        This is useful if the file has been modified externally.
        
        Returns:
            Reloaded parameters dictionary.
        """
        with self._lock:
            # Clear cached parameters to force reload
            self._parameters = {}
            return self.load()
    
    def save(self, parameters: Optional[Dict[str, Any]] = None) -> bool:
        """Save engine parameters to file.
        
        Args:
            parameters: Parameters dictionary to save. If None, saves current loaded parameters.
            
        Returns:
            True if save was successful, False otherwise.
        """
        with self._lock:
            if parameters is not None:
                self._parameters = parameters
            
            try:
                # Ensure directory exists
                self.parameters_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(self.parameters_path, "w", encoding="utf-8") as f:
                    json.dump(self._parameters, f, indent=2, ensure_ascii=False)
                
                return True
            except IOError as e:
                print(f"Error: Failed to save engine parameters: {e}", file=sys.stderr)
                return False
    
    def get_parameters(self) -> Dict[str, Any]:
        """Get current parameters.
        
        Returns:
            Current parameters dictionary.
        """
        return self._parameters
    
    def get_engine_options(self, engine_path: str) -> List[Dict[str, Any]]:
        """Get options for a specific engine.
        
        Args:
            engine_path: Path to engine executable (used as key).
            
        Returns:
            List of option dictionaries, or empty list if not found.
        """
        # Check if engine_path exists in _parameters
        if engine_path in self._parameters:
            return self._parameters[engine_path].get("options", [])
        return []
    
    def set_engine_options(self, engine_path: str, options: List[Dict[str, Any]]) -> bool:
        """Set options for a specific engine.
        
        Args:
            engine_path: Path to engine executable (used as key).
            options: List of option dictionaries.
            
        Returns:
            True if save was successful, False otherwise.
        """
        if engine_path not in self._parameters:
            self._parameters[engine_path] = {}
        
        self._parameters[engine_path]["options"] = options
        
        return self.save()
    
    def get_task_parameters(self, engine_path: str, task: str) -> Dict[str, Any]:
        """Get task-specific parameters for an engine.
        
        Args:
            engine_path: Path to engine executable (used as key).
            task: Task identifier (evaluation, game_analysis, manual_analysis).
            
        Returns:
            Dictionary with task parameters (threads, depth, movetime, and engine-specific options), or empty dict if not found.
        """
        if engine_path in self._parameters:
            tasks = self._parameters[engine_path].get("tasks", {})
            return tasks.get(task, {})
        return {}
    
    @staticmethod
    def get_task_parameters_for_engine(engine_path: Path, task: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Get task-specific parameters for an engine with fallback to config.json defaults.
        
        This is a convenience method that loads parameters from engine_parameters.json
        and falls back to config.json defaults if not found.
        
        Args:
            engine_path: Path to engine executable.
            task: Task identifier (evaluation, game_analysis, manual_analysis).
            config: Configuration dictionary from config.json.
            
        Returns:
            Dictionary with task parameters (threads, depth, movetime, and engine-specific options).
        """
        service = EngineParametersService.get_instance()
        service.load()  # Load if not already loaded
        engine_path_str = str(engine_path)
        params = service.get_task_parameters(engine_path_str, task)
        
        # If parameters found, return them
        if params:
            return params
        
        # Fallback to config.json defaults
        from app.services.engine_configuration_service import EngineConfigurationService, TaskType
        
        task_type_map = {
            "evaluation": TaskType.EVALUATION,
            "game_analysis": TaskType.GAME_ANALYSIS,
            "manual_analysis": TaskType.MANUAL_ANALYSIS
        }
        
        task_type = task_type_map.get(task)
        if task_type:
            config_service = EngineConfigurationService(config)
            return config_service.get_recommended_defaults(task_type)
        
        # Final fallback
        return {"threads": 1, "depth": 0, "movetime": 0}
    
    def set_task_parameters(self, engine_path: str, task: str, parameters: Dict[str, Any]) -> bool:
        """Set task-specific parameters for an engine.
        
        Args:
            engine_path: Path to engine executable (used as key).
            task: Task identifier (evaluation, game_analysis, manual_analysis).
            parameters: Dictionary with task parameters (threads, depth, movetime).
            
        Returns:
            True if save was successful, False otherwise.
        """
        if engine_path not in self._parameters:
            self._parameters[engine_path] = {}
        
        if "tasks" not in self._parameters[engine_path]:
            self._parameters[engine_path]["tasks"] = {}
        
        self._parameters[engine_path]["tasks"][task] = parameters
        
        return self.save()
    
    def set_all_task_parameters(self, engine_path: str, tasks_parameters: Dict[str, Dict[str, Any]]) -> bool:
        """Set all task-specific parameters for an engine at once.
        
        Args:
            engine_path: Path to engine executable (used as key).
            tasks_parameters: Dictionary mapping task names to their parameter dictionaries.
            
        Returns:
            True if save was successful, False otherwise.
        """
        if engine_path not in self._parameters:
            self._parameters[engine_path] = {}
        
        self._parameters[engine_path]["tasks"] = tasks_parameters
        
        return self.save()
    
    def remove_engine_options(self, engine_path: str) -> bool:
        """Remove options for a specific engine.
        
        Args:
            engine_path: Path to engine executable (used as key).
            
        Returns:
            True if removal was successful, False otherwise.
        """
        if engine_path in self._parameters:
            del self._parameters[engine_path]
            return self.save()
        return True  # Already removed, consider it successful
    
    def _deep_copy(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a deep copy of a dictionary.
        
        Args:
            data: Dictionary to copy.
            
        Returns:
            Deep copy of the dictionary.
        """
        return json.loads(json.dumps(data))

