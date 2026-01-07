"""Manual analysis model for managing analysis lines state."""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import List, Optional
from dataclasses import dataclass
import time


@dataclass
class AnalysisLine:
    """Represents a single analysis line (multipv)."""
    
    multipv: int  # Line number (1-based)
    centipawns: float = 0.0  # Evaluation in centipawns
    is_mate: bool = False  # True if mate score
    mate_moves: int = 0  # Mate moves (positive for white, negative for black)
    depth: int = 0  # Current depth
    pv: str = ""  # Principal variation as space-separated moves
    nps: int = -1  # Nodes per second (-1 if not available)
    hashfull: int = -1  # Hash table usage 0-1000 (-1 if not available)


class ManualAnalysisModel(QObject):
    """Model representing manual analysis state.
    
    This model holds the current analysis lines and emits signals
    when the analysis changes.
    """
    
    # Signals emitted when analysis state changes
    analysis_changed = pyqtSignal()  # Emitted when any analysis line changes
    lines_changed = pyqtSignal()  # Emitted when number of lines changes
    is_analyzing_changed = pyqtSignal(bool)  # Emitted when analysis state changes (is_analyzing)
    enable_miniature_preview_changed = pyqtSignal(bool)  # Emitted when miniature preview setting changes
    miniature_preview_scale_factor_changed = pyqtSignal(float)  # Emitted when miniature preview scale factor changes
    
    def __init__(self) -> None:
        """Initialize the manual analysis model."""
        super().__init__()
        self._lines: List[AnalysisLine] = []
        self._is_analyzing: bool = False
        self._multipv: int = 2  # Number of lines to analyze
        self._start_time: Optional[float] = None  # Timestamp when analysis started (None if not analyzing)
        self._enable_miniature_preview: bool = True  # Enable miniature board preview on PV hover
        self._miniature_preview_scale_factor: float = 1.0  # Scale factor for miniature board preview (1.0 = default size)
    
    @property
    def lines(self) -> List[AnalysisLine]:
        """Get current analysis lines.
        
        Returns:
            List of AnalysisLine instances, sorted by multipv.
        """
        return sorted(self._lines, key=lambda line: line.multipv)
    
    @property
    def is_analyzing(self) -> bool:
        """Get whether analysis is currently running.
        
        Returns:
            True if analyzing, False otherwise.
        """
        return self._is_analyzing
    
    @is_analyzing.setter
    def is_analyzing(self, value: bool) -> None:
        """Set analysis state.
        
        Args:
            value: True if analyzing, False otherwise.
        """
        if self._is_analyzing != value:
            self._is_analyzing = value
            if value:
                # Start tracking time when analysis begins
                self._start_time = time.time()
            else:
                # Clear start time when analysis stops
                self._start_time = None
            self.is_analyzing_changed.emit(value)
    
    @property
    def multipv(self) -> int:
        """Get number of analysis lines (multipv).
        
        Returns:
            Number of lines to analyze (1-based).
        """
        return self._multipv
    
    @multipv.setter
    def multipv(self, value: int) -> None:
        """Set number of analysis lines (multipv).
        
        Args:
            value: Number of lines to analyze (1-based, minimum 1).
        """
        if value < 1:
            value = 1
        if self._multipv != value:
            old_multipv = self._multipv
            self._multipv = value
            
            # Always filter lines based on new multipv value (remove lines with multipv > value)
            # This ensures we remove lines when multipv is reduced, regardless of current line count
            lines_before = len(self._lines)
            
            # Filter out lines with multipv > value
            filtered_lines = [line for line in self._lines if line.multipv <= value]
            self._lines = filtered_lines
            lines_after = len(self._lines)
            
            # Emit analysis_changed if:
            # 1. We removed lines (count decreased), OR
            # 2. Multipv was reduced (even if count didn't change, we need to update UI to reflect new multipv)
            # This ensures the UI always updates when multipv is reduced
            if lines_after < lines_before or value < old_multipv:
                self.analysis_changed.emit()
            
            # Add missing lines (if we need more lines than we have)
            if len(self._lines) < value:
                existing_multipvs = {line.multipv for line in self._lines}
                for i in range(1, value + 1):
                    if i not in existing_multipvs:
                        self._lines.append(AnalysisLine(i))
                # Emit analysis_changed to notify UI that new lines were added
                self.analysis_changed.emit()
            
            # Always emit lines_changed when multipv changes
            self.lines_changed.emit()
    
    def get_line(self, multipv: int) -> Optional[AnalysisLine]:
        """Get analysis line by multipv number.
        
        Args:
            multipv: Line number (1-based).
            
        Returns:
            AnalysisLine instance or None if not found.
        """
        for line in self._lines:
            if line.multipv == multipv:
                return line
        return None
    
    def update_line(self, multipv: int, centipawns: float, is_mate: bool,
                    mate_moves: int, depth: int, pv: str = "",
                    nps: int = -1, hashfull: int = -1) -> None:
        """Update an analysis line.
        
        Args:
            multipv: Line number (1-based).
            centipawns: Evaluation in centipawns.
            is_mate: True if mate score.
            mate_moves: Mate moves (positive for white, negative for black).
            depth: Current depth.
            pv: Principal variation as space-separated moves.
            nps: Nodes per second (-1 if not available).
            hashfull: Hash table usage 0-1000 (-1 if not available).
        """
        # Check if line already exists - if so, always allow updates (even if multipv > current)
        # This handles the case where engine sends updates before model multipv is updated
        line = self.get_line(multipv)
        if line:
            # Update existing line - always allow, even if multipv > current
            # This handles race conditions where engine updates arrive before model multipv is set
            line.centipawns = centipawns
            line.is_mate = is_mate
            line.mate_moves = mate_moves
            line.depth = depth
            line.pv = pv
            line.nps = nps
            line.hashfull = hashfull
            self.analysis_changed.emit()
        else:
            # Line doesn't exist - only create if within current multipv range
            # This prevents stale engine updates from recreating removed lines
            if multipv <= self._multipv:
                line = AnalysisLine(multipv, centipawns, is_mate, mate_moves, depth, pv, nps, hashfull)
                self._lines.append(line)
                self.analysis_changed.emit()
            # If line doesn't exist and multipv > current, silently ignore
    
    def get_best_line(self) -> Optional[AnalysisLine]:
        """Get the best analysis line (multipv 1).
        
        Returns:
            AnalysisLine instance for multipv 1, or None if not available.
        """
        return self.get_line(1)
    
    def get_elapsed_time(self) -> float:
        """Get elapsed time since analysis started.
        
        Returns:
            Elapsed time in seconds, or 0.0 if not analyzing.
        """
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time
    
    @property
    def enable_miniature_preview(self) -> bool:
        """Get whether miniature preview is enabled.
        
        Returns:
            True if miniature preview is enabled, False otherwise.
        """
        return self._enable_miniature_preview
    
    @enable_miniature_preview.setter
    def enable_miniature_preview(self, value: bool) -> None:
        """Set miniature preview enabled state.
        
        Args:
            value: True to enable miniature preview, False to disable.
        """
        if self._enable_miniature_preview != value:
            self._enable_miniature_preview = value
            self.enable_miniature_preview_changed.emit(value)
    
    @property
    def miniature_preview_scale_factor(self) -> float:
        """Get miniature preview scale factor.
        
        Returns:
            Scale factor (1.0 = default size, 1.25 = 1.25x, etc.).
        """
        return self._miniature_preview_scale_factor
    
    @miniature_preview_scale_factor.setter
    def miniature_preview_scale_factor(self, value: float) -> None:
        """Set miniature preview scale factor.
        
        Args:
            value: Scale factor (1.0, 1.25, 1.5, 1.75, or 2.0).
        """
        if self._miniature_preview_scale_factor != value:
            self._miniature_preview_scale_factor = value
            self.miniature_preview_scale_factor_changed.emit(value)
    
    def reset(self) -> None:
        """Reset analysis to default state."""
        self._lines.clear()
        self._is_analyzing = False
        self._start_time = None
        self.analysis_changed.emit()
        self.lines_changed.emit()

