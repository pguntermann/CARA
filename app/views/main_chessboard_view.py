"""Chess board view for main panel."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from typing import Dict, Any, Optional

from app.views.chessboard_widget import ChessBoardWidget
from app.views.evaluation_bar_widget import EvaluationBarWidget
from app.models.board_model import BoardModel


class MainChessBoardView(QWidget):
    """Chess board view displaying the game board."""
    
    def __init__(self, config: Dict[str, Any], board_model: Optional[BoardModel] = None,
                 evaluation_model=None) -> None:
        """Initialize the chess board view.
        
        Args:
            config: Configuration dictionary.
            board_model: Optional BoardModel to observe.
            evaluation_model: Optional EvaluationModel to observe.
        """
        super().__init__()
        self.config = config
        self._board_model = board_model
        self._evaluation_model = evaluation_model
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """Setup the chess board UI."""
        # Use vertical layout (board widget will handle evaluation bar internally)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Create chess board widget with model (evaluation bar will be attached to left side)
        self.chessboard = ChessBoardWidget(self.config, self._board_model, self._evaluation_model)
        layout.addWidget(self.chessboard, 1)  # Takes remaining space
        
        # Connect to board model for visibility and rotation
        if self._board_model:
            self._board_model.evaluation_bar_visibility_changed.connect(self._on_evaluation_bar_visibility_changed)
            self._board_model.flip_state_changed.connect(self._on_board_flip_changed)
            # Set initial visibility
            self._on_evaluation_bar_visibility_changed(self._board_model.show_evaluation_bar)
            self._on_board_flip_changed(self._board_model.is_flipped)
    
    def set_evaluation_model(self, model) -> None:
        """Set the evaluation model.
        
        Args:
            model: EvaluationModel instance.
        """
        self._evaluation_model = model
        if self.chessboard:
            self.chessboard.set_evaluation_model(model)
    
    def _on_evaluation_bar_visibility_changed(self, show: bool) -> None:
        """Handle evaluation bar visibility change.
        
        Args:
            show: True if evaluation bar should be shown, False otherwise.
        """
        if self.chessboard:
            self.chessboard.set_evaluation_bar_visible(show)
    
    def _on_board_flip_changed(self, is_flipped: bool) -> None:
        """Handle board flip state change.
        
        Args:
            is_flipped: True if board is flipped, False otherwise.
        """
        if self.chessboard:
            self.chessboard.set_evaluation_bar_flipped(is_flipped)

