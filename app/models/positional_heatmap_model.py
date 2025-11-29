"""Model for positional heat-map state."""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Dict
import chess

from app.services.positional_heatmap.positional_analyzer import PositionalAnalyzer


class PositionalHeatmapModel(QObject):
    """Model representing positional heat-map state.
    
    Holds state and emits signals when state changes.
    Views observe these signals to update the UI automatically.
    """
    
    # Signals
    scores_changed = pyqtSignal(dict)  # Emitted when scores change (Dict[chess.Square, float])
    visibility_changed = pyqtSignal(bool)  # Emitted when visibility toggles
    
    def __init__(self, config: Dict, analyzer: PositionalAnalyzer) -> None:
        """Initialize the positional heat-map model.
        
        Args:
            config: Configuration dictionary.
            analyzer: PositionalAnalyzer instance for position analysis.
        """
        super().__init__()
        self.config = config
        self.analyzer = analyzer
        self._scores: Dict[chess.Square, float] = {}
        self._visible = False
    
    def update_position(self, board: chess.Board) -> None:
        """Update scores for new position.
        
        Args:
            board: Current chess position.
        """
        # Analyze from both perspectives to get scores for all pieces
        # First analyze from White's perspective
        white_scores = self.analyzer.analyze_position(board, chess.WHITE)
        # Then analyze from Black's perspective
        black_scores = self.analyzer.analyze_position(board, chess.BLACK)
        
        # Combine scores: use White perspective for White pieces, Black perspective for Black pieces
        combined_scores = {}
        
        # Add White piece scores (from White's perspective)
        for square, score in white_scores.items():
            piece = board.piece_at(square)
            if piece and piece.color == chess.WHITE:
                combined_scores[square] = score
        
        # Add Black piece scores (from Black's perspective)
        for square, score in black_scores.items():
            piece = board.piece_at(square)
            if piece and piece.color == chess.BLACK:
                combined_scores[square] = score
        
        self._scores = combined_scores
        self.scores_changed.emit(self._scores)
    
    def get_scores(self) -> Dict[chess.Square, float]:
        """Get current scores.
        
        Returns:
            Dictionary mapping square -> score.
        """
        return self._scores.copy()
    
    def set_visible(self, visible: bool) -> None:
        """Set visibility state.
        
        Args:
            visible: True to show heat-map, False to hide.
        """
        if self._visible != visible:
            self._visible = visible
            self.visibility_changed.emit(visible)
    
    @property
    def is_visible(self) -> bool:
        """Check if heat-map is visible.
        
        Returns:
            True if visible, False otherwise.
        """
        return self._visible

