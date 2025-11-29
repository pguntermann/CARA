"""Evaluation bar widget for displaying position evaluation."""

from PyQt6.QtWidgets import QWidget
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush
from PyQt6.QtCore import Qt, QRect, QRectF, QTimer
from typing import Dict, Any, Optional
import time

from app.models.evaluation_model import EvaluationModel


class EvaluationBarWidget(QWidget):
    """Widget displaying evaluation bar with white/black bars."""
    
    def __init__(self, config: Dict[str, Any], evaluation_model: Optional[EvaluationModel] = None) -> None:
        """Initialize the evaluation bar widget.
        
        Args:
            config: Configuration dictionary.
            evaluation_model: Optional EvaluationModel to observe.
        """
        super().__init__()
        self.config = config
        self._evaluation_model: Optional[EvaluationModel] = None
        self._is_flipped = False
        
        # Animation state
        self._displayed_value: float = 0.0  # Currently displayed evaluation value
        self._target_value: float = 0.0  # Target evaluation value
        self._animation_start_time: float = 0.0
        self._animation_start_value: float = 0.0
        self._animation_duration_ms: int = 300
        self._animation_timer: Optional[QTimer] = None
        self._is_animating: bool = False
        
        self._load_config()
        self._setup_ui()
        
        # Connect to model if provided
        if evaluation_model:
            self.set_evaluation_model(evaluation_model)
    
    def _load_config(self) -> None:
        """Load configuration from config dictionary."""
        board_config = self.config.get("ui", {}).get("panels", {}).get("main", {}).get("board", {})
        eval_config = board_config.get("evaluation_bar", {})
        
        self.width = eval_config.get("width", 30)
        scale_max = eval_config.get("scale_max", 10.0)
        # Safety check: ensure scale_max is never 0 or negative to prevent division by zero
        if scale_max <= 0:
            scale_max = 10.0  # Use safe default
        self.scale_max = scale_max
        self.divisions = eval_config.get("divisions", [1, 2, 3, 5, 10])
        self._animation_duration_ms = eval_config.get("animation_duration_ms", 300)
        
        colors_config = eval_config.get("colors", {})
        self.white_color = QColor(*colors_config.get("white", [255, 255, 255]))
        self.black_color = QColor(*colors_config.get("black", [0, 0, 0]))
        
        # Set fixed width
        self.setFixedWidth(self.width)
        
        # Setup animation timer
        self._animation_timer = QTimer(self)
        self._animation_timer.timeout.connect(self._update_animation)
        self._animation_timer.setInterval(16)  # ~60 FPS
    
    def _setup_ui(self) -> None:
        """Setup the widget UI."""
        self.setMinimumSize(self.width, 100)
        self.setMaximumSize(self.width, 16777215)  # Max height
    
    def set_evaluation_model(self, model: EvaluationModel) -> None:
        """Set the evaluation model to observe.
        
        Args:
            model: EvaluationModel instance.
        """
        if self._evaluation_model:
            # Disconnect from old model
            try:
                self._evaluation_model.evaluation_changed.disconnect(self._on_evaluation_changed)
            except TypeError:
                # Signal was not connected, ignore
                pass
        
        self._evaluation_model = model
        
        if self._evaluation_model:
            # Connect to new model
            self._evaluation_model.evaluation_changed.connect(self._on_evaluation_changed)
            # Initialize with current value
            self._on_evaluation_changed()
    
    def set_flipped(self, is_flipped: bool) -> None:
        """Set board flip state.
        
        Args:
            is_flipped: True if board is flipped, False otherwise.
        """
        if self._is_flipped != is_flipped:
            self._is_flipped = is_flipped
            # When board flips, the evaluation should NOT change
            # The evaluation always represents the same position (from White's perspective)
            # The bar should visually rotate with the board, but the evaluation meaning stays the same
            # So we don't need to flip any values - just update the display
            self.update()
    
    def _on_evaluation_changed(self) -> None:
        """Handle evaluation change from model."""
        if not self._evaluation_model:
            return
        
        # Get target evaluation value (always from White's perspective)
        # Evaluation should not flip when board flips - it always represents the same position
        target_value = self._evaluation_model.get_evaluation_value(self.scale_max)
        
        # Start animation to target value
        self._start_animation(target_value)
    
    def _start_animation(self, target_value: float) -> None:
        """Start animation to target value.
        
        Args:
            target_value: Target evaluation value to animate to.
        """
        # If target is same as current, no animation needed
        if abs(self._displayed_value - target_value) < 0.001:
            return
        
        # Set target
        self._target_value = target_value
        
        # If not animating, start animation
        if not self._is_animating:
            self._animation_start_value = self._displayed_value
            self._animation_start_time = time.time()
            self._is_animating = True
            self._animation_timer.start()
        else:
            # If already animating, continue from current displayed value
            self._animation_start_value = self._displayed_value
    
    def _update_animation(self) -> None:
        """Update animation frame."""
        if not self._is_animating:
            return
        
        current_time = time.time()
        elapsed_ms = (current_time - self._animation_start_time) * 1000.0
        
        if elapsed_ms >= self._animation_duration_ms:
            # Animation complete
            self._displayed_value = self._target_value
            self._is_animating = False
            self._animation_timer.stop()
            self.update()
        else:
            # Interpolate between start and target
            progress = elapsed_ms / self._animation_duration_ms
            # Use easing curve for smooth animation (ease-out)
            # Simple ease-out: 1 - (1 - t)^3
            eased_progress = 1.0 - (1.0 - progress) ** 3
            
            # Interpolate value
            self._displayed_value = self._animation_start_value + (self._target_value - self._animation_start_value) * eased_progress
            self.update()
    
    def paintEvent(self, event) -> None:
        """Paint the evaluation bar.
        
        Args:
            event: Paint event.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        width = rect.width()
        height = rect.height()
        center_y = height / 2.0
        
        # Use animated displayed value
        eval_value = self._displayed_value
        
        # Safety check: ensure scale_max is never 0 to prevent division by zero
        if self.scale_max <= 0:
            self.scale_max = 10.0  # Use safe default
        
        # Calculate bar heights
        # Positive = white advantage (top), negative = black advantage (bottom)
        white_height = 0.0
        black_height = 0.0
        
        if eval_value > 0:
            # White advantage
            white_height = (eval_value / self.scale_max) * center_y
            black_height = 0.0
        elif eval_value < 0:
            # Black advantage
            white_height = 0.0
            black_height = (abs(eval_value) / self.scale_max) * center_y
        else:
            # Equal position
            white_height = 0.0
            black_height = 0.0
        
        # Draw black bar (bottom half)
        if black_height > 0:
            black_rect = QRectF(0, center_y, width, black_height)
            painter.fillRect(black_rect, QBrush(self.black_color))
        
        # Draw white bar (top half)
        if white_height > 0:
            white_rect = QRectF(0, center_y - white_height, width, white_height)
            painter.fillRect(white_rect, QBrush(self.white_color))
        
        # Draw center line
        center_pen = QPen(QColor(128, 128, 128), 1, Qt.PenStyle.SolidLine)
        painter.setPen(center_pen)
        painter.drawLine(0, int(center_y), width, int(center_y))
        
        # Draw division marks
        division_pen = QPen(QColor(128, 128, 128), 1, Qt.PenStyle.DashLine)
        painter.setPen(division_pen)
        
        for division in self.divisions:
            # Positive division (white advantage)
            div_y = center_y - (division / self.scale_max) * center_y
            if div_y > 0:
                painter.drawLine(0, int(div_y), width, int(div_y))
            
            # Negative division (black advantage)
            div_y = center_y + (division / self.scale_max) * center_y
            if div_y < height:
                painter.drawLine(0, int(div_y), width, int(div_y))

