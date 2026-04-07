"""Turn indicator widget showing whose turn it is."""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QBrush
from PyQt6.QtCore import Qt
from typing import Dict, Any, Optional

from app.models.board_model import BoardModel


class TurnIndicatorWidget(QWidget):
    """Circular indicator showing if it's White's or Black's turn."""
    
    def __init__(self, config: Dict[str, Any], board_model: Optional[BoardModel] = None) -> None:
        """Initialize the turn indicator widget.
        
        Args:
            config: Configuration dictionary.
            board_model: Optional BoardModel to observe.
        """
        super().__init__()
        self.config = config
        self._board_model: Optional[BoardModel] = None
        self._load_config()
        
        # Set model if provided
        if board_model:
            self.set_model(board_model)
        else:
            # Default to white's turn
            self._is_white_turn = True
    
    def _load_config(self) -> None:
        """Load configuration for the turn indicator."""
        ui_config = self.config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('main', {})
        board_config = panel_config.get('board', {})
        indicator_config = board_config.get('turn_indicator', {})
        
        self.size = indicator_config.get('size', 16)
        self.padding = indicator_config.get('padding', [0, 0, 10, 10])
        self.white_color = indicator_config.get('white_color', [250, 250, 250])
        self.black_color = indicator_config.get('black_color', [40, 40, 40])
        
        # Set fixed size based on indicator size and padding
        # Padding: [top, right, bottom, left]
        width = self.size + self.padding[1] + self.padding[3]  # left + right padding
        height = self.size + self.padding[0] + self.padding[2]  # top + bottom padding
        self.setFixedSize(width, height)
    
    def set_model(self, model: BoardModel) -> None:
        """Set the board model to observe.
        
        Args:
            model: The BoardModel instance to observe.
        """
        if self._board_model:
            # Disconnect from old model
            self._board_model.position_changed.disconnect(self._on_turn_changed)
            if hasattr(self._board_model, 'turn_changed'):
                self._board_model.turn_changed.disconnect(self._on_turn_changed)
        
        self._board_model = model
        
        # Connect to model signals
        model.position_changed.connect(self._on_turn_changed)
        if hasattr(model, 'turn_changed'):
            model.turn_changed.connect(self._on_turn_changed)
        
        # Initialize with current turn
        self._update_turn()
        self.update()
    
    def _on_turn_changed(self) -> None:
        """Handle turn change from model."""
        self._update_turn()
        self.update()
    
    def _update_turn(self) -> None:
        """Update the turn state from model."""
        if self._board_model:
            self._is_white_turn = self._board_model.is_white_turn()
        else:
            self._is_white_turn = True
    
    def paintEvent(self, event) -> None:
        """Paint the turn indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate circle position (centered with padding)
        # Padding: [top, right, bottom, left]
        circle_x = self.padding[3] + self.size // 2  # left padding + half size
        circle_y = self.padding[0] + self.size // 2  # top padding + half size
        circle_radius = self.size // 2
        
        # Choose color based on turn
        if self._is_white_turn:
            color = QColor(self.white_color[0], self.white_color[1], self.white_color[2])
        else:
            color = QColor(self.black_color[0], self.black_color[1], self.black_color[2])
        
        # Draw circle
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(int(circle_x - circle_radius), int(circle_y - circle_radius), 
                          self.size, self.size)

