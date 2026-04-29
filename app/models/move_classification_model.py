"""Move classification settings model."""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Dict, Any, List


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
        self._shallow_depth_min: int = 3
        self._shallow_depth_max: int = 7
        self._min_depths_show_error: int = 3  # Min number of shallow depths that must show move as error
        self._shallow_error_classifications: List[str] = ["Mistake", "Blunder", "Miss"]  # Classifications that count as error at shallow depth (config-only)
        self._candidate_selection: str = "best_move_only"  # "best_move_only" or "best_or_good_move"
        self._exclude_already_winning_enabled: bool = True
        self._exclude_already_winning_threshold_cpl: int = 600

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
    def shallow_error_classifications(self) -> List[str]:
        """Get move classifications that count as error at shallow depth for brilliancy detection."""
        return self._shallow_error_classifications

    @property
    def candidate_selection(self) -> str:
        """Get candidate selection mode for brilliancy detection ("best_move_only" or "best_or_good_move")."""
        return self._candidate_selection

    @property
    def exclude_already_winning_enabled(self) -> bool:
        """Whether to exclude brilliant candidates when side-to-move is already winning."""
        return bool(self._exclude_already_winning_enabled)

    @property
    def exclude_already_winning_threshold_cpl(self) -> int:
        """Absolute CPL threshold (normalized to side-to-move) that counts as 'already winning'."""
        try:
            return int(self._exclude_already_winning_threshold_cpl)
        except Exception:
            return 600

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
        self._shallow_error_classifications = list(
            brilliant_criteria.get("shallow_error_classifications", ["Mistake", "Blunder", "Miss"])
        )
        self._candidate_selection = brilliant_criteria.get("candidate_selection", "best_move_only")
        self._exclude_already_winning_enabled = bool(
            brilliant_criteria.get("exclude_already_winning_enabled", True)
        )
        self._exclude_already_winning_threshold_cpl = int(
            brilliant_criteria.get("exclude_already_winning_threshold_cpl", 600)
        )

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

        if "shallow_error_classifications" in criteria and criteria["shallow_error_classifications"] != self._shallow_error_classifications:
            self._shallow_error_classifications = list(criteria["shallow_error_classifications"])
            changed = True

        if "candidate_selection" in criteria and criteria["candidate_selection"] != self._candidate_selection:
            self._candidate_selection = criteria["candidate_selection"]
            changed = True

        if (
            "exclude_already_winning_enabled" in criteria
            and bool(criteria["exclude_already_winning_enabled"]) != bool(self._exclude_already_winning_enabled)
        ):
            self._exclude_already_winning_enabled = bool(criteria["exclude_already_winning_enabled"])
            changed = True

        if "exclude_already_winning_threshold_cpl" in criteria:
            try:
                new_val = int(criteria["exclude_already_winning_threshold_cpl"])
            except Exception:
                new_val = self._exclude_already_winning_threshold_cpl
            if new_val != self._exclude_already_winning_threshold_cpl:
                self._exclude_already_winning_threshold_cpl = new_val
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
            "shallow_error_classifications": self._shallow_error_classifications,
            "candidate_selection": self._candidate_selection,
            "exclude_already_winning_enabled": bool(self._exclude_already_winning_enabled),
            "exclude_already_winning_threshold_cpl": int(self._exclude_already_winning_threshold_cpl),
        }

