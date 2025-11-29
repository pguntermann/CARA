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
        self._min_eval_swing: int = 50
        self._min_material_sacrifice: int = 300
        self._max_eval_before: int = 500
        self._exclude_already_winning: bool = True
        self._material_sacrifice_lookahead_plies: int = 3
    
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
    def min_eval_swing(self) -> int:
        """Get minimum eval swing for brilliancy."""
        return self._min_eval_swing
    
    @property
    def min_material_sacrifice(self) -> int:
        """Get minimum material sacrifice for brilliancy."""
        return self._min_material_sacrifice
    
    @property
    def max_eval_before(self) -> int:
        """Get maximum eval before move for brilliancy."""
        return self._max_eval_before
    
    @property
    def exclude_already_winning(self) -> bool:
        """Get exclude already winning flag for brilliancy."""
        return self._exclude_already_winning
    
    @property
    def material_sacrifice_lookahead_plies(self) -> int:
        """Get material sacrifice lookahead plies for brilliancy."""
        return self._material_sacrifice_lookahead_plies
    
    
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
        self._min_eval_swing = brilliant_criteria.get("min_eval_swing", 50)
        self._min_material_sacrifice = brilliant_criteria.get("min_material_sacrifice", 300)
        self._max_eval_before = brilliant_criteria.get("max_eval_before", 500)
        self._exclude_already_winning = brilliant_criteria.get("exclude_already_winning", True)
        self._material_sacrifice_lookahead_plies = brilliant_criteria.get("material_sacrifice_lookahead_plies", 3)
        
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
        
        if "min_eval_swing" in criteria and criteria["min_eval_swing"] != self._min_eval_swing:
            self._min_eval_swing = criteria["min_eval_swing"]
            changed = True
        
        if "min_material_sacrifice" in criteria and criteria["min_material_sacrifice"] != self._min_material_sacrifice:
            self._min_material_sacrifice = criteria["min_material_sacrifice"]
            changed = True
        
        if "max_eval_before" in criteria and criteria["max_eval_before"] != self._max_eval_before:
            self._max_eval_before = criteria["max_eval_before"]
            changed = True
        
        if "exclude_already_winning" in criteria and criteria["exclude_already_winning"] != self._exclude_already_winning:
            self._exclude_already_winning = criteria["exclude_already_winning"]
            changed = True
        
        if "material_sacrifice_lookahead_plies" in criteria and criteria["material_sacrifice_lookahead_plies"] != self._material_sacrifice_lookahead_plies:
            self._material_sacrifice_lookahead_plies = criteria["material_sacrifice_lookahead_plies"]
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
            "min_eval_swing": self._min_eval_swing,
            "min_material_sacrifice": self._min_material_sacrifice,
            "max_eval_before": self._max_eval_before,
            "exclude_already_winning": self._exclude_already_winning,
            "material_sacrifice_lookahead_plies": self._material_sacrifice_lookahead_plies
        }

