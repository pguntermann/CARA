"""Evaluation model for managing position evaluation state."""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Optional


class EvaluationModel(QObject):
    """Model representing position evaluation state.
    
    This model holds the current evaluation of the position and emits signals
    when the evaluation changes.
    """
    
    # Signals emitted when evaluation state changes
    evaluation_changed = pyqtSignal()  # Emitted when evaluation value changes
    depth_changed = pyqtSignal(int)  # Emitted when depth changes (depth)
    
    def __init__(self) -> None:
        """Initialize the evaluation model."""
        super().__init__()
        self._centipawns: float = 0.0
        self._is_mate: bool = False
        self._mate_moves: int = 0  # Positive for white mate, negative for black mate
        self._depth: int = 0
        self._is_evaluating: bool = False
    
    @property
    def centipawns(self) -> float:
        """Get current evaluation in centipawns.
        
        Returns:
            Evaluation in centipawns (positive = white advantage, negative = black advantage).
        """
        return self._centipawns
    
    @centipawns.setter
    def centipawns(self, value: float) -> None:
        """Set evaluation in centipawns.
        
        Args:
            value: Evaluation in centipawns.
        """
        if self._centipawns != value:
            self._centipawns = value
            self.evaluation_changed.emit()
    
    @property
    def is_mate(self) -> bool:
        """Get whether the evaluation is a mate score.
        
        Returns:
            True if evaluation is mate, False otherwise.
        """
        return self._is_mate
    
    @is_mate.setter
    def is_mate(self, value: bool) -> None:
        """Set mate status.
        
        Args:
            value: True if mate, False otherwise.
        """
        if self._is_mate != value:
            self._is_mate = value
            self.evaluation_changed.emit()
    
    @property
    def mate_moves(self) -> int:
        """Get mate moves.
        
        Returns:
            Positive number for white mate, negative for black mate, 0 if not mate.
        """
        return self._mate_moves
    
    @mate_moves.setter
    def mate_moves(self, value: int) -> None:
        """Set mate moves.
        
        Args:
            value: Positive for white mate, negative for black mate, 0 if not mate.
        """
        if self._mate_moves != value:
            self._mate_moves = value
            self.evaluation_changed.emit()
    
    @property
    def depth(self) -> int:
        """Get current evaluation depth.
        
        Returns:
            Current depth of evaluation.
        """
        return self._depth
    
    @depth.setter
    def depth(self, value: int) -> None:
        """Set evaluation depth.
        
        Args:
            value: Depth value.
        """
        if self._depth != value:
            self._depth = value
            self.depth_changed.emit(value)
    
    @property
    def is_evaluating(self) -> bool:
        """Get whether evaluation is currently running.
        
        Returns:
            True if evaluating, False otherwise.
        """
        return self._is_evaluating
    
    @is_evaluating.setter
    def is_evaluating(self, value: bool) -> None:
        """Set evaluation state.
        
        Args:
            value: True if evaluating, False otherwise.
        """
        if self._is_evaluating != value:
            self._is_evaluating = value
    
    def get_evaluation_value(self, scale_max: float = 10.0) -> float:
        """Get evaluation value normalized to scale.
        
        Args:
            scale_max: Maximum scale value (default 10.0).
            
        Returns:
            Evaluation value in pawns, clamped to scale_max.
            For mate, returns scale_max or -scale_max.
        """
        if self._is_mate:
            if self._mate_moves > 0:
                return scale_max  # White mate
            else:
                return -scale_max  # Black mate
        else:
            # Convert centipawns to pawns and clamp to scale
            pawns = self._centipawns / 100.0
            return max(-scale_max, min(scale_max, pawns))
    
    def reset(self) -> None:
        """Reset evaluation to default state."""
        self._centipawns = 0.0
        self._is_mate = False
        self._mate_moves = 0
        self._depth = 0
        self._is_evaluating = False
        self.evaluation_changed.emit()
    
    def update_from_analysis_line(self, line) -> None:
        """Update evaluation from an analysis line (from manual analysis).
        
        Args:
            line: AnalysisLine instance from manual analysis model.
        """
        self._centipawns = line.centipawns
        self._is_mate = line.is_mate
        self._mate_moves = line.mate_moves
        self._depth = line.depth
        self._is_evaluating = True  # Mark as evaluating if we have data
        self.evaluation_changed.emit()

