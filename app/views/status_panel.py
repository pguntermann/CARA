"""Status-Panel below Database-Panel - replaces PyQt's native Statusbar."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QProgressBar, QSizeGrip
from PyQt6.QtGui import QPalette, QColor, QFont
from PyQt6.QtCore import Qt
from typing import Dict, Any, Optional

from app.models.progress_model import ProgressModel


class StatusPanel(QWidget):
    """Status panel showing formatted status message and progress bar.
    
    This view observes the ProgressModel and automatically
    updates when the model state changes via signal connections.
    """
    
    def __init__(self, config: Dict[str, Any], progress_model: Optional[ProgressModel] = None) -> None:
        """Initialize the status panel.
        
        Args:
            config: Configuration dictionary.
            progress_model: Optional ProgressModel to observe.
                           If provided, panel will automatically update when model changes.
        """
        super().__init__()
        self.config = config
        self._progress_model: Optional[ProgressModel] = None
        self._setup_ui()
        
        # Connect to model if provided
        if progress_model:
            self.set_model(progress_model)
    
    def _setup_ui(self) -> None:
        """Setup the status panel UI."""
        layout = QHBoxLayout(self)
        ui_config = self.config.get('ui', {})
        
        # Get margins from config
        margins = ui_config.get('margins', {}).get('status_panel', [5, 5, 5, 5])
        layout.setContentsMargins(margins[0], margins[1], margins[2], margins[3])
        layout.setSpacing(10)
        
        # Get panel config
        panel_config = ui_config.get('panels', {}).get('status', {})
        
        # Section 1: Version label (left)
        version_config = panel_config.get('version', {})
        version_font_family = version_config.get('font_family', 'Helvetica Neue')
        version_font_size = version_config.get('font_size', 10)
        version_color = version_config.get('color', [180, 180, 180])
        version_width = version_config.get('width', 80)
        
        app_version = self.config.get('version', '1.0')
        self.version_label = QLabel(f"v{app_version}")
        version_font = QFont(version_font_family, version_font_size)
        self.version_label.setFont(version_font)
        version_palette = self.version_label.palette()
        version_palette.setColor(QPalette.ColorRole.WindowText, QColor(version_color[0], version_color[1], version_color[2]))
        self.version_label.setPalette(version_palette)
        self.version_label.setFixedWidth(version_width)
        layout.addWidget(self.version_label, 0, Qt.AlignmentFlag.AlignLeft)
        
        # Section 2: Status message label (middle - expandable)
        message_config = panel_config.get('message', {})
        message_font_family = message_config.get('font_family', 'Helvetica Neue')
        message_font_size = message_config.get('font_size', 11)
        message_color = message_config.get('color', [220, 220, 220])
        
        self.status_label = QLabel("Ready")
        message_font = QFont(message_font_family, message_font_size)
        self.status_label.setFont(message_font)
        message_palette = self.status_label.palette()
        message_palette.setColor(QPalette.ColorRole.WindowText, QColor(message_color[0], message_color[1], message_color[2]))
        self.status_label.setPalette(message_palette)
        layout.addWidget(self.status_label, 1)  # Takes remaining space
        
        # Section 3: Progress bar (right)
        # Progress bar (only visible when app is computing)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)  # Hidden by default
        progress_config = ui_config.get('progress_bar', {})
        max_width = progress_config.get('maximum_width', 300)
        height = progress_config.get('height', 20)
        self.progress_bar.setMaximumWidth(max_width)
        self.progress_bar.setMinimumHeight(height)
        self.progress_bar.setMaximumHeight(height)
        layout.addWidget(self.progress_bar, 0, Qt.AlignmentFlag.AlignRight)
        
        # Resize grip on the right side (after progress bar)
        grip_config = panel_config.get('resize_grip', {})
        grip_width = grip_config.get('width', 20)
        grip_height = grip_config.get('height', 20)
        
        self.resize_grip = QSizeGrip(self)
        self.resize_grip.setFixedSize(grip_width, grip_height)
        layout.addWidget(self.resize_grip, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        
        # Set minimum height for status panel
        min_height = panel_config.get('minimum_height', 30)
        self.setMinimumHeight(min_height)
        
        # Set background color from config using palette
        debug_config = self.config.get("debug", {})
        if debug_config.get("enable_debug_backgrounds", False):
            # Use debug background color
            color = debug_config.get("background_color_debug_statuspanel", [255, 255, 255])
        else:
            # Use normal background color
            color = panel_config.get("background_color", [45, 45, 50])
        
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(color[0], color[1], color[2]))
        self.setPalette(palette)
        self.setAutoFillBackground(True)
    
    def set_status(self, message: str) -> None:
        """Set the status message.
        
        Args:
            message: Status message to display. Supports HTML formatting for colors and formatting.
        """
        # QLabel supports HTML formatting, so we can pass formatted text directly
        self.status_label.setText(message)
    
    def show_progress(self) -> None:
        """Show the progress bar."""
        self.progress_bar.setVisible(True)
    
    def hide_progress(self) -> None:
        """Hide the progress bar."""
        self.progress_bar.setVisible(False)
    
    def set_model(self, model: ProgressModel) -> None:
        """Set the progress model to observe.
        
        Args:
            model: The ProgressModel instance to observe.
        """
        self._progress_model = model
        
        # Connect model signals to view updates
        model.progress_changed.connect(self.progress_bar.setValue)
        model.status_changed.connect(self.status_label.setText)
        model.visibility_changed.connect(self.progress_bar.setVisible)
        model.indeterminate_changed.connect(self._on_indeterminate_changed)
        
        # Initialize view with current model state
        self.progress_bar.setValue(model.progress)
        self.status_label.setText(model.status)
        self.progress_bar.setVisible(model.is_visible)
        self._on_indeterminate_changed(model.is_indeterminate)
    
    def _on_indeterminate_changed(self, indeterminate: bool) -> None:
        """Handle indeterminate mode change.
        
        Args:
            indeterminate: True to enable indeterminate (pulsing) mode, False for normal progress.
        """
        if indeterminate:
            # Set range to (0, 0) for indeterminate mode (pulsing animation)
            self.progress_bar.setRange(0, 0)
        else:
            # Set range to (0, 100) for normal progress mode
            self.progress_bar.setRange(0, 100)
    
    def set_progress(self, value: int) -> None:
        """Set progress bar value.
        
        Args:
            value: Progress value (0-100).
        
        Note: If model is connected, prefer updating through model instead.
        """
        self.progress_bar.setValue(value)

