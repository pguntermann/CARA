"""Move classification settings model."""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Dict, Any


class MoveClassificationModel(QObject):
    """Model representing move classification settings.
    
    This model holds assessment thresholds and brilliancy criteria,
    and emits signals when settings change.
    """
    
    # Signals emitted when settings change
    settings_changed = pyqtSignal()  # Emitted when any setting changes
    
    def __init__(self) -> None:
        """Initialize the move classification model."""
        super().__init__()
        
        # Assessment thresholds
        self._good_move_max_cpl: int = 50
        self._inaccuracy_max_cpl: int = 100
        self._mistake_max_cpl: int = 200
        
        # Brilliant criteria
        self._shallow_depth_min: int = 2
        self._shallow_depth_max: int = 6
        self._min_depths_show_error: int = 1  # Min number of shallow depths that must show move as Mistake/Blunder
        self._require_blunder_only: bool = False  # If True, only count Blunder; if False, count Mistake or Blunder

    # Assessment thresholds properties
    @property
    def good_move_max_cpl(self) -> int:
        """Get good move max CPL threshold."""
        return self._good_move_max_cpl
    
    @property
    def inaccuracy_max_cpl(self) -> int:
        """Get inaccuracy max CPL threshold."""
        return self._inaccuracy_max_cpl
    
    @property
    def mistake_max_cpl(self) -> int:
        """Get mistake max CPL threshold."""
        return self._mistake_max_cpl
    
    # Brilliant criteria properties
    @property
    def shallow_depth_min(self) -> int:
        """Get minimum shallow depth for brilliancy detection."""
        return self._shallow_depth_min
    
    @property
    def shallow_depth_max(self) -> int:
        """Get maximum shallow depth for brilliancy detection."""
        return self._shallow_depth_max

    @property
    def min_depths_show_error(self) -> int:
        """Get minimum number of shallow depths that must show the move as Mistake/Blunder (min agreement)."""
        return self._min_depths_show_error

    @property
    def require_blunder_only(self) -> bool:
        """Get whether only Blunder (not Mistake) should be counted for brilliancy detection."""
        return self._require_blunder_only

    def load_settings(self, assessment_thresholds: Dict[str, int], 
                      brilliant_criteria: Dict[str, Any]) -> None:
        """Load settings from dictionaries.
        
        Args:
            assessment_thresholds: Dictionary with threshold values.
            brilliant_criteria: Dictionary with brilliancy criteria values.
        """
        # Load assessment thresholds
        self._good_move_max_cpl = assessment_thresholds.get("good_move_max_cpl", 50)
        self._inaccuracy_max_cpl = assessment_thresholds.get("inaccuracy_max_cpl", 100)
        self._mistake_max_cpl = assessment_thresholds.get("mistake_max_cpl", 200)
        
        # Load brilliant criteria
        self._shallow_depth_min = brilliant_criteria.get("shallow_depth_min", 2)
        self._shallow_depth_max = brilliant_criteria.get("shallow_depth_max", 6)
        self._min_depths_show_error = brilliant_criteria.get("min_depths_show_error", 1)
        self._require_blunder_only = brilliant_criteria.get("require_blunder_only", False)

        # Emit signal that settings changed
        self.settings_changed.emit()
    
    def update_assessment_thresholds(self, thresholds: Dict[str, int]) -> None:
        """Update assessment thresholds.
        
        Args:
            thresholds: Dictionary with threshold values to update.
        """
        changed = False
        
        if "good_move_max_cpl" in thresholds and thresholds["good_move_max_cpl"] != self._good_move_max_cpl:
            self._good_move_max_cpl = thresholds["good_move_max_cpl"]
            changed = True
        
        if "inaccuracy_max_cpl" in thresholds and thresholds["inaccuracy_max_cpl"] != self._inaccuracy_max_cpl:
            self._inaccuracy_max_cpl = thresholds["inaccuracy_max_cpl"]
            changed = True
        
        if "mistake_max_cpl" in thresholds and thresholds["mistake_max_cpl"] != self._mistake_max_cpl:
            self._mistake_max_cpl = thresholds["mistake_max_cpl"]
            changed = True
        
        if changed:
            self.settings_changed.emit()
    
    def update_brilliant_criteria(self, criteria: Dict[str, Any]) -> None:
        """Update brilliancy criteria.
        
        Args:
            criteria: Dictionary with criteria values to update.
        """
        changed = False
        
        if "shallow_depth_min" in criteria and criteria["shallow_depth_min"] != self._shallow_depth_min:
            self._shallow_depth_min = criteria["shallow_depth_min"]
            changed = True
        
        if "shallow_depth_max" in criteria and criteria["shallow_depth_max"] != self._shallow_depth_max:
            self._shallow_depth_max = criteria["shallow_depth_max"]
            changed = True

        if "min_depths_show_error" in criteria and criteria["min_depths_show_error"] != self._min_depths_show_error:
            self._min_depths_show_error = criteria["min_depths_show_error"]
            changed = True

        if "require_blunder_only" in criteria and criteria["require_blunder_only"] != self._require_blunder_only:
            self._require_blunder_only = criteria["require_blunder_only"]
            changed = True

        if changed:
            self.settings_changed.emit()
    
    def get_assessment_thresholds(self) -> Dict[str, int]:
        """Get all assessment thresholds as a dictionary.
        
        Returns:
            Dictionary with all threshold values.
        """
        return {
            "good_move_max_cpl": self._good_move_max_cpl,
            "inaccuracy_max_cpl": self._inaccuracy_max_cpl,
            "mistake_max_cpl": self._mistake_max_cpl
        }
    
    def get_brilliant_criteria(self) -> Dict[str, Any]:
        """Get all brilliancy criteria as a dictionary.
        
        Returns:
            Dictionary with all criteria values.
        """
        return {
            "shallow_depth_min": self._shallow_depth_min,
            "shallow_depth_max": self._shallow_depth_max,
            "min_depths_show_error": self._min_depths_show_error,
            "require_blunder_only": self._require_blunder_only
        }

