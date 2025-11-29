"""Overlay widget for displaying positional heat-map on chess board."""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPaintEvent, QRadialGradient, QBrush
from PyQt6.QtCore import Qt, QPointF
from typing import Dict, Optional
import chess

from app.models.positional_heatmap_model import PositionalHeatmapModel


class PositionalHeatmapOverlay(QWidget):
    """Overlay widget for displaying positional heat-map on chess board.
    
    This widget overlays the chess board and displays heat-map scores
    as colored squares. It's transparent to mouse events so the board
    remains interactive.
    """
    
    def __init__(self, config: Dict, model: PositionalHeatmapModel, 
                 board_widget: QWidget) -> None:
        """Initialize the positional heat-map overlay.
        
        Args:
            config: Configuration dictionary.
            model: PositionalHeatmapModel instance to observe.
            board_widget: Parent chess board widget (for positioning).
        """
        super().__init__(board_widget)
        self.config = config
        self.model = model
        self.board_widget = board_widget
        self._scores: Dict[chess.Square, float] = {}
        
        # Make transparent to mouse events
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        
        # Load configuration
        heatmap_config = config.get('ui', {}).get('positional_heatmap', {})
        colors_config = heatmap_config.get('colors', {})
        self.positive_color = QColor(*colors_config.get('positive', [0, 255, 0]))
        self.negative_color = QColor(*colors_config.get('negative', [255, 0, 0]))
        self.neutral_color = QColor(*colors_config.get('neutral', [255, 255, 0]))
        self.neutral_threshold = colors_config.get('neutral_threshold', -5.0)
        self.opacity = colors_config.get('opacity', 0.9)
        self.gradient_radius_ratio = colors_config.get('gradient_radius_ratio', 0.8)
        self.gradient_center_ratio = colors_config.get('gradient_center_ratio', 0.3)
        self.score_range = heatmap_config.get('score_range', [-100, 100])
        self.min_score, self.max_score = self.score_range
        
        # Connect to model
        self.model.scores_changed.connect(self._on_scores_changed)
        self.model.visibility_changed.connect(self._on_visibility_changed)
        
        # Connect to board model flip state changes
        self._connect_to_board_model()
        
        # Initially hidden
        self.setVisible(False)
    
    def _on_scores_changed(self, scores: Dict[chess.Square, float]) -> None:
        """Handle scores update from model.
        
        Args:
            scores: Dictionary mapping square -> score.
        """
        self._scores = scores
        self.update()  # Trigger repaint
    
    def _on_visibility_changed(self, visible: bool) -> None:
        """Handle visibility change from model.
        
        Args:
            visible: True if heat-map should be visible, False otherwise.
        """
        self.setVisible(visible)
        if visible:
            self.update()  # Trigger repaint when shown
    
    def _connect_to_board_model(self) -> None:
        """Connect to board model flip state changes."""
        # Disconnect from previous board model if any
        if hasattr(self, '_board_model') and self._board_model:
            if hasattr(self._board_model, 'flip_state_changed'):
                try:
                    self._board_model.flip_state_changed.disconnect(self._on_flip_state_changed)
                except TypeError:
                    # Signal not connected, ignore
                    pass
        
        # Connect to current board model
        if hasattr(self.board_widget, '_board_model') and self.board_widget._board_model:
            self._board_model = self.board_widget._board_model
            if hasattr(self._board_model, 'flip_state_changed'):
                self._board_model.flip_state_changed.connect(self._on_flip_state_changed)
        else:
            self._board_model = None
    
    def _on_flip_state_changed(self, is_flipped: bool) -> None:
        """Handle flip state change from board model.
        
        Args:
            is_flipped: True if board is flipped, False otherwise.
        """
        # Trigger repaint to update gradient positions
        self.update()
    
    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the heat-map overlay.
        
        Args:
            event: Paint event.
        """
        if not self.model.is_visible or not self._scores:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Get board dimensions from parent widget
        if not hasattr(self.board_widget, '_cached_dimensions') or not self.board_widget._cached_dimensions:
            return
        
        dims = self.board_widget._cached_dimensions
        square_size = dims['square_size']
        board_start_x = dims['start_x']
        board_start_y = dims['start_y']
        
        # Get flip state
        is_flipped = False
        if hasattr(self.board_widget, '_board_model') and self.board_widget._board_model:
            is_flipped = self.board_widget._board_model.is_flipped
        
        # Get board to check for pieces
        board = None
        if hasattr(self.board_widget, '_board_model') and self.board_widget._board_model:
            board = self.board_widget._board_model.board
        
        # Draw circular gradients for each square with score
        for square, score in self._scores.items():
            # Only show gradient if there's a piece on this square
            if board is None or board.piece_at(square) is None:
                continue
            
            # Scores are now evaluated from each piece's own perspective
            # (White pieces scored from White's perspective, Black pieces from Black's perspective)
            # So we can use the score directly:
            # - Positive score = good for the piece → green
            # - Negative score = bad for the piece → red
            
            # Map score to color and intensity (no adjustment needed)
            color, intensity = self._score_to_color(score)
            
            # Get square position
            file = chess.square_file(square)
            rank = chess.square_rank(square)
            
            # Convert to board widget coordinates
            # Match the transformation used in chessboard_widget._load_position_from_model
            if is_flipped:
                # When flipped visually, mirror both file and rank for display
                # FEN position stays the same, but we display it rotated
                mirrored_file = 7 - file
                mirrored_rank = 7 - rank
                row = 7 - mirrored_rank  # Convert to our row system (rank 0 -> row 7)
                col = mirrored_file
            else:
                row = 7 - rank  # Invert rank (chess rank 0 = row 7)
                col = file
            
            # Calculate square center position
            square_x = board_start_x + col * square_size
            square_y = board_start_y + row * square_size
            center_x = square_x + square_size / 2
            center_y = square_y + square_size / 2
            
            # Calculate gradient radius (as fraction of square size)
            # Limit to half the square size to ensure it stays within square boundaries
            max_radius = square_size / 2
            gradient_radius = min(square_size * self.gradient_radius_ratio, max_radius)
            
            # Create radial gradient
            gradient = QRadialGradient(
                QPointF(center_x, center_y),  # Center point
                gradient_radius  # Radius
            )
            
            # Set gradient stops with very prominent colors
            # Center: full opacity and intensity
            center_color = QColor(color)
            center_color.setAlphaF(self.opacity * intensity)
            gradient.setColorAt(0.0, center_color)
            
            # Mid-point: still very visible
            mid_color = QColor(color)
            mid_color.setAlphaF(self.opacity * intensity * 0.7)
            gradient.setColorAt(0.4, mid_color)
            
            # Outer edge: fade to transparent but more gradually
            outer_color = QColor(color)
            outer_color.setAlphaF(self.opacity * intensity * 0.3)
            gradient.setColorAt(0.7, outer_color)
            
            # Edge: fade to transparent
            edge_color = QColor(color)
            edge_color.setAlphaF(0.0)
            gradient.setColorAt(1.0, edge_color)
            
            # Clip to square boundaries to prevent gradient from extending into adjacent squares
            painter.save()
            painter.setClipRect(
                int(square_x),
                int(square_y),
                int(square_size),
                int(square_size)
            )
            
            # Draw circular gradient
            painter.setBrush(QBrush(gradient))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                int(center_x - gradient_radius),
                int(center_y - gradient_radius),
                int(gradient_radius * 2),
                int(gradient_radius * 2)
            )
            
            painter.restore()
    
    def _score_to_color(self, score: float) -> tuple[QColor, float]:
        """Map score to color and intensity.
        
        Args:
            score: Positional score (typically -100 to +100).
        
        Returns:
            Tuple of (color, intensity) where:
            - color: QColor for the gradient
            - intensity: Float 0.0 to 1.0 indicating color intensity
        """
        # Normalize score to 0-1 range
        score_range = self.max_score - self.min_score
        if score_range == 0:
            normalized = 0.0
        else:
            normalized = (score - self.min_score) / score_range
        
        # Clamp to 0-1
        normalized = max(0.0, min(1.0, normalized))
        
        # Determine color based on score
        if score >= 0:
            # Positive score: use positive color (green)
            color = self.positive_color
            # Map normalized score to intensity (0.7 to 1.0 for maximum visibility)
            intensity = 0.7 + (normalized * 0.3)  # Higher score = higher intensity
        elif score >= self.neutral_threshold:
            # Small negative score: use neutral color (yellow)
            # Map score from neutral_threshold to 0, to intensity 0.7 to 1.0
            color = self.neutral_color
            # Normalize score between neutral_threshold and 0
            if self.neutral_threshold < 0:
                neutral_normalized = (score - self.neutral_threshold) / (-self.neutral_threshold)
                intensity = 0.7 + (neutral_normalized * 0.3)  # Closer to 0 = higher intensity
            else:
                intensity = 0.7
        else:
            # Large negative score: use negative color (red)
            color = self.negative_color
            # Map negative score to intensity (0.7 to 1.0)
            intensity = 0.7 + ((1.0 - normalized) * 0.3)  # More negative = higher intensity
        
        # Clamp intensity to valid range (minimum 0.7 for strong visibility)
        intensity = max(0.7, min(1.0, intensity))
        
        return color, intensity
    
    def resizeEvent(self, event) -> None:
        """Handle resize event.
        
        Args:
            event: Resize event.
        """
        # Match parent widget size
        if self.board_widget:
            self.setGeometry(self.board_widget.rect())
        super().resizeEvent(event)

