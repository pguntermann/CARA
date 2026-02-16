"""Engine configuration service for managing and validating engine parameters."""

import os
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from asteval import Interpreter
from app.services.logging_service import LoggingService


class TaskType(Enum):
    """Enum for different analysis task types."""
    EVALUATION = "evaluation"
    GAME_ANALYSIS = "game_analysis"
    MANUAL_ANALYSIS = "manual_analysis"


class ValidationSeverity(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"  # Must be fixed
    WARNING = "warning"  # Should be fixed but can be overridden
    INFO = "info"  # Informational recommendation


@dataclass
class ValidationIssue:
    """Represents a validation issue with a parameter setting."""
    severity: ValidationSeverity
    parameter: str
    message: str
    recommended_value: Optional[Any] = None


@dataclass
class ValidationResult:
    """Result of validating engine parameters."""
    is_valid: bool
    issues: List[ValidationIssue]
    has_errors: bool
    has_warnings: bool


class EngineConfigurationService:
    """Service for managing and validating engine parameter configurations.
    
    This service handles:
    - Loading recommended defaults from config.json
    - Validating user settings against recommendations
    - Providing structured feedback on validation issues
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the engine configuration service.
        
        Args:
            config: Configuration dictionary from config.json.
        """
        self.config = config
        self._load_recommended_defaults()
    
    def _load_recommended_defaults(self) -> None:
        """Load recommended default values from config.json using formulas."""
        # Get CPU count for formula evaluation
        cpu_count = os.cpu_count() or 4
        reserved_cores = 2  # Reserve cores for UI responsiveness
        
        # Game Analysis defaults
        game_analysis_config = self.config.get("game_analysis", {})
        threads_formula_config = game_analysis_config.get("default_threads_formula", {})
        threads_formula = threads_formula_config.get("formula")
        if not threads_formula:
            raise ValueError("default_threads_formula.formula is required in config.json under game_analysis")
        threads_value = self._evaluate_thread_formula(threads_formula, cpu_count, reserved_cores, "game_analysis")
        
        self.game_analysis_defaults = {
            "threads": threads_value,
            "depth": game_analysis_config.get("max_depth", 40),
            "movetime": game_analysis_config.get("time_limit_per_move_ms", 1000)
        }
        
        # Evaluation defaults
        evaluation_config = self.config.get("ui", {}).get("panels", {}).get("main", {}).get("board", {}).get("evaluation_bar", {})
        threads_formula_config = evaluation_config.get("default_threads_formula", {})
        threads_formula = threads_formula_config.get("formula")
        if not threads_formula:
            raise ValueError("default_threads_formula.formula is required in config.json under ui.panels.main.board.evaluation_bar")
        threads_value = self._evaluate_thread_formula(threads_formula, cpu_count, reserved_cores, "evaluation")
        
        self.evaluation_defaults = {
            "threads": threads_value,
            "depth": evaluation_config.get("max_depth_evaluation", 0),
            "movetime": 0  # No movetime for evaluation
        }
        
        # Manual Analysis defaults
        manual_analysis_config = self.config.get("ui", {}).get("panels", {}).get("detail", {}).get("manual_analysis", {})
        threads_formula_config = manual_analysis_config.get("default_threads_formula", {})
        threads_formula = threads_formula_config.get("formula")
        if not threads_formula:
            raise ValueError("default_threads_formula.formula is required in config.json under ui.panels.detail.manual_analysis")
        threads_value = self._evaluate_thread_formula(threads_formula, cpu_count, reserved_cores, "manual_analysis")
        
        self.manual_analysis_defaults = {
            "threads": threads_value,
            "depth": 0,  # No depth for manual analysis
            "movetime": 0  # No movetime for manual analysis
        }
    
    def _evaluate_thread_formula(self, formula: str, cpu_count: int, reserved_cores: int, task_type: str) -> int:
        """Evaluate thread count formula using asteval.
        
        Args:
            formula: Formula string to evaluate.
            cpu_count: Available CPU thread count.
            reserved_cores: Number of cores to reserve for UI responsiveness.
            task_type: Task type name for logging.
            
        Returns:
            Calculated thread count (clamped to >= 1).
        """
        try:
            aeval = Interpreter()
            # Set variables for formula evaluation
            aeval.symtable['cpu_count'] = cpu_count
            aeval.symtable['reserved_cores'] = reserved_cores
            aeval.symtable['task_type'] = task_type
            # Add built-in functions
            aeval.symtable['min'] = min
            aeval.symtable['max'] = max
            aeval.symtable['abs'] = abs
            aeval.symtable['int'] = int
            # Evaluate the formula
            result = aeval(formula)
            if result is None:
                # Fallback to safe default
                return max(1, min(4, cpu_count - reserved_cores))
            # Ensure result is at least 1
            result = max(1, int(result))
            return result
        except Exception as e:
            # Log error and return safe default
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Error evaluating thread formula for {task_type}: {e}", exc_info=e)
            return max(1, min(4, cpu_count - reserved_cores))
    
    def get_recommended_defaults(self, task: TaskType) -> Dict[str, Any]:
        """Get recommended default values for a specific task.
        
        Args:
            task: Task type.
            
        Returns:
            Dictionary with recommended default values (threads, depth, movetime).
        """
        if task == TaskType.EVALUATION:
            return self.evaluation_defaults.copy()
        elif task == TaskType.GAME_ANALYSIS:
            return self.game_analysis_defaults.copy()
        elif task == TaskType.MANUAL_ANALYSIS:
            return self.manual_analysis_defaults.copy()
        else:
            return {"threads": 1, "depth": 0, "movetime": 0}
    
    def validate_parameters(self, task: TaskType, parameters: Dict[str, Any]) -> ValidationResult:
        """Validate engine parameters against recommendations.
        
        Args:
            task: Task type.
            parameters: Dictionary with parameter values (threads, depth, movetime, and engine-specific options).
            
        Returns:
            ValidationResult with validation issues.
        """
        issues: List[ValidationIssue] = []
        
        threads = parameters.get("threads", 1)
        depth = parameters.get("depth", 0)
        movetime = parameters.get("movetime", 0)
        
        # Check if threads exceed available logical CPU threads
        # Note: os.cpu_count() returns logical cores/threads (includes hyperthreading/SMT)
        # Chess engines use logical threads, so this is the correct check
        # Example: An 8-core CPU with hyperthreading = 16 logical threads
        logical_cpu_count = os.cpu_count()
        if logical_cpu_count is not None and threads > logical_cpu_count:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                parameter="threads",
                message=f"Thread count ({threads}) exceeds available logical CPU threads ({logical_cpu_count}). This may not provide performance benefits and can waste resources.",
                recommended_value=logical_cpu_count
            ))
        
        # Check Hash size (if present)
        # Hash is typically in MB, warn if extremely small or large
        hash_mb = parameters.get("Hash", None)
        if hash_mb is not None:
            if hash_mb < 1:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    parameter="Hash",
                    message=f"Hash size ({hash_mb} MB) is very small. This may significantly hurt engine performance. Recommended: at least 16 MB.",
                    recommended_value=16
                ))
            elif hash_mb > 8192:  # 8 GB
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    parameter="Hash",
                    message=f"Hash size ({hash_mb} MB) is very large. This may consume excessive system memory. Consider using a smaller value unless you have sufficient RAM.",
                    recommended_value=min(4096, hash_mb // 2)  # Suggest half or 4GB, whichever is smaller
                ))
        
        # Check movetime for extreme values (applies to all tasks)
        if movetime > 0:
            if movetime < 10:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    parameter="movetime",
                    message=f"Move time ({movetime}ms) is extremely low. This may not provide meaningful analysis. Consider using at least 100ms.",
                    recommended_value=100
                ))
            elif movetime > 3600000:  # 1 hour
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    parameter="movetime",
                    message=f"Move time ({movetime}ms = {movetime // 1000}s) is extremely high. This may take a very long time. Verify this is intentional.",
                    recommended_value=None  # No specific recommendation
                ))
        
        # Check depth for extreme values (applies to all tasks)
        if depth > 0:
            if depth > 100:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    parameter="depth",
                    message=f"Search depth ({depth}) is very high. This may take a very long time to complete. Verify this is intentional.",
                    recommended_value=None  # No specific recommendation
                ))
        
        # Check MultiPV (if present)
        # High MultiPV significantly slows down analysis
        multipv = parameters.get("MultiPV", None)
        if multipv is not None and multipv > 10:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.INFO,
                parameter="MultiPV",
                message=f"MultiPV ({multipv}) is high. This will significantly slow down analysis. Consider using a lower value (e.g., 1-5) unless you specifically need many variations.",
                recommended_value=5
            ))
        
        if task == TaskType.EVALUATION:
            # Evaluation: runs on infinite analysis (depth=0, movetime=0)
            # Warn if user sets depth or movetime, as they will be ignored
            if depth > 0:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    parameter="depth",
                    message=f"Evaluation engine runs on infinite analysis. Depth setting ({depth}) will be ignored. The engine will continuously analyze until the position changes.",
                    recommended_value=0
                ))
            
            if movetime > 0:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    parameter="movetime",
                    message=f"Evaluation engine runs on infinite analysis. Move time setting ({movetime}ms) will be ignored. The engine will continuously analyze until the position changes.",
                    recommended_value=0
                ))
        
        elif task == TaskType.GAME_ANALYSIS:
            # Game Analysis: movetime required, optionally depth (warn if both set)
            if movetime == 0:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    parameter="movetime",
                    message="Game Analysis engine should have a move time limit. Current value: 0 (unlimited)",
                    recommended_value=self.game_analysis_defaults.get("movetime", 1000)
                ))
            
            if depth > 0 and movetime > 0:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    parameter="depth",
                    message=f"Game Analysis engine has both depth ({depth}) and movetime ({movetime}ms) set. Some engines may not work well when both are specified. Consider using only movetime.",
                    recommended_value=0
                ))
        
        elif task == TaskType.MANUAL_ANALYSIS:
            # Manual Analysis: no depth or movetime (continuous analysis)
            if depth > 0:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    parameter="depth",
                    message=f"Manual Analysis is a continuous analysis mode. Depth should be 0 (unlimited). Current value: {depth}",
                    recommended_value=0
                ))
            
            if movetime > 0:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    parameter="movetime",
                    message=f"Manual Analysis is a continuous analysis mode. Move time should be 0 (unlimited). Current value: {movetime}ms",
                    recommended_value=0
                ))
        
        # Check for errors and warnings
        has_errors = any(issue.severity == ValidationSeverity.ERROR for issue in issues)
        has_warnings = any(issue.severity == ValidationSeverity.WARNING for issue in issues)
        is_valid = not has_errors  # Valid if no errors (warnings can be overridden)
        
        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
            has_errors=has_errors,
            has_warnings=has_warnings
        )
    
    def apply_recommended_defaults(self, task: TaskType, current_parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Apply recommended defaults to parameters, preserving engine-specific options.
        
        Args:
            task: Task type.
            current_parameters: Current parameter dictionary (may include engine-specific options).
            
        Returns:
            Updated parameter dictionary with recommended defaults applied.
        """
        recommended = self.get_recommended_defaults(task)
        updated = current_parameters.copy()
        
        # Override common parameters with recommended defaults
        updated["threads"] = recommended["threads"]
        updated["depth"] = recommended["depth"]
        updated["movetime"] = recommended["movetime"]
        
        # Preserve engine-specific options
        # (They are not overridden)
        
        return updated

