"""Engine model for managing UCI chess engines."""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
import uuid


@dataclass
class EngineData:
    """Represents a configured UCI chess engine."""
    
    id: str
    path: str
    name: str
    author: str
    version: str
    is_valid: bool
    validation_error: str
    last_validated: str
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for persistence.
        
        Returns:
            Dictionary representation of engine data.
        """
        return {
            "id": self.id,
            "path": self.path,
            "name": self.name,
            "author": self.author,
            "version": self.version,
            "is_valid": self.is_valid,
            "validation_error": self.validation_error,
            "last_validated": self.last_validated
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'EngineData':
        """Create EngineData from dictionary.
        
        Args:
            data: Dictionary with engine data.
            
        Returns:
            EngineData instance.
        """
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            path=data.get("path", ""),
            name=data.get("name", ""),
            author=data.get("author", ""),
            version=data.get("version", ""),
            is_valid=data.get("is_valid", False),
            validation_error=data.get("validation_error", ""),
            last_validated=data.get("last_validated", datetime.now().isoformat())
        )


class EngineModel(QObject):
    """Model representing configured UCI engines.
    
    This model holds the list of configured engines and emits signals
    when engines are added, removed, or updated.
    """
    
    # Signals emitted when engine state changes
    engine_added = pyqtSignal(str)  # Emitted when engine is added (engine_id)
    engine_removed = pyqtSignal(str)  # Emitted when engine is removed (engine_id)
    engine_updated = pyqtSignal(str)  # Emitted when engine is updated (engine_id)
    engines_changed = pyqtSignal()  # Emitted when engine list changes
    
    # Signals emitted when engine assignments change
    assignment_changed = pyqtSignal()  # Emitted when any assignment changes
    
    # Task assignment constants
    TASK_GAME_ANALYSIS = "game_analysis"
    TASK_EVALUATION = "evaluation"
    TASK_MANUAL_ANALYSIS = "manual_analysis"
    
    def __init__(self) -> None:
        """Initialize the engine model."""
        super().__init__()
        self._engines: Dict[str, EngineData] = {}
        # Engine assignments: task -> engine_id
        self._assignments: Dict[str, Optional[str]] = {
            self.TASK_GAME_ANALYSIS: None,
            self.TASK_EVALUATION: None,
            self.TASK_MANUAL_ANALYSIS: None
        }
    
    def get_engines(self) -> List[EngineData]:
        """Get list of all configured engines.
        
        Returns:
            List of EngineData instances.
        """
        return list(self._engines.values())
    
    def get_engine(self, engine_id: str) -> Optional[EngineData]:
        """Get engine by ID.
        
        Args:
            engine_id: Engine ID.
            
        Returns:
            EngineData instance or None if not found.
        """
        return self._engines.get(engine_id)
    
    def get_engine_by_path(self, path: str) -> Optional[EngineData]:
        """Get engine by file path.
        
        Args:
            path: Engine executable path.
            
        Returns:
            EngineData instance or None if not found.
        """
        for engine in self._engines.values():
            if engine.path == path:
                return engine
        return None
    
    def add_engine(self, engine: EngineData) -> bool:
        """Add an engine to the model.
        
        Automatically assigns the engine to any tasks that have no assignment.
        
        Args:
            engine: EngineData instance to add.
            
        Returns:
            True if engine was added, False if engine with same ID already exists.
        """
        if engine.id in self._engines:
            return False
        
        self._engines[engine.id] = engine
        
        # Auto-assign to tasks that have no assignment
        for task in [self.TASK_GAME_ANALYSIS, self.TASK_EVALUATION, self.TASK_MANUAL_ANALYSIS]:
            if self._assignments[task] is None:
                self._assignments[task] = engine.id
        
        self.engine_added.emit(engine.id)
        self.engines_changed.emit()
        self.assignment_changed.emit()
        return True
    
    def remove_engine(self, engine_id: str) -> bool:
        """Remove an engine from the model.
        
        Automatically reassigns tasks that were using the removed engine
        to the first available engine.
        
        Args:
            engine_id: Engine ID to remove.
            
        Returns:
            True if engine was removed, False if engine doesn't exist.
        """
        if engine_id not in self._engines:
            return False
        
        # Get remaining engines (before removal)
        remaining_engines = [e for e in self._engines.values() if e.id != engine_id]
        first_remaining_id = remaining_engines[0].id if remaining_engines else None
        
        # Reassign tasks that were using the removed engine
        for task in [self.TASK_GAME_ANALYSIS, self.TASK_EVALUATION, self.TASK_MANUAL_ANALYSIS]:
            if self._assignments[task] == engine_id:
                self._assignments[task] = first_remaining_id
        
        del self._engines[engine_id]
        self.engine_removed.emit(engine_id)
        self.engines_changed.emit()
        self.assignment_changed.emit()
        return True
    
    def update_engine(self, engine: EngineData) -> bool:
        """Update an engine in the model.
        
        Args:
            engine: EngineData instance with updated data.
            
        Returns:
            True if engine was updated, False if engine doesn't exist.
        """
        if engine.id not in self._engines:
            return False
        
        self._engines[engine.id] = engine
        self.engine_updated.emit(engine.id)
        self.engines_changed.emit()
        return True
    
    def load_engines(self, engines_data: List[Dict]) -> None:
        """Load engines from settings data.
        
        Args:
            engines_data: List of engine dictionaries from settings.
        """
        self._engines.clear()
        
        for engine_dict in engines_data:
            try:
                engine = EngineData.from_dict(engine_dict)
                self._engines[engine.id] = engine
            except Exception:
                # Skip invalid engine data
                continue
        
        self.engines_changed.emit()
    
    def get_assignment(self, task: str) -> Optional[str]:
        """Get the engine ID assigned to a task.
        
        Args:
            task: Task constant (TASK_GAME_ANALYSIS, TASK_EVALUATION, TASK_MANUAL_ANALYSIS).
            
        Returns:
            Engine ID or None if no engine is assigned.
        """
        return self._assignments.get(task)
    
    def set_assignment(self, task: str, engine_id: Optional[str]) -> bool:
        """Set the engine assignment for a task.
        
        Args:
            task: Task constant (TASK_GAME_ANALYSIS, TASK_EVALUATION, TASK_MANUAL_ANALYSIS).
            engine_id: Engine ID to assign, or None to clear.
            
        Returns:
            True if assignment was set, False if task or engine_id is invalid.
        """
        if task not in self._assignments:
            return False
        
        if engine_id is not None and engine_id not in self._engines:
            return False
        
        self._assignments[task] = engine_id
        self.assignment_changed.emit()
        return True
    
    def get_assignments(self) -> Dict[str, Optional[str]]:
        """Get all engine assignments.
        
        Returns:
            Dictionary mapping tasks to engine IDs (or None).
        """
        return self._assignments.copy()
    
    def load_assignments(self, assignments: Dict[str, Optional[str]]) -> None:
        """Load engine assignments from settings.
        
        Args:
            assignments: Dictionary mapping tasks to engine IDs.
        """
        for task, engine_id in assignments.items():
            if task in self._assignments:
                # Validate engine_id exists (or is None)
                if engine_id is None or engine_id in self._engines:
                    self._assignments[task] = engine_id
        
        # Ensure all tasks have assignments if engines exist
        engines = self.get_engines()
        if engines:
            first_engine_id = engines[0].id
            for task in [self.TASK_GAME_ANALYSIS, self.TASK_EVALUATION, self.TASK_MANUAL_ANALYSIS]:
                if self._assignments[task] is None:
                    self._assignments[task] = first_engine_id
        
        self.assignment_changed.emit()
    
    def to_dict(self) -> List[Dict]:
        """Convert engines to list of dictionaries for persistence.
        
        Returns:
            List of engine dictionaries.
        """
        return [engine.to_dict() for engine in self._engines.values()]

