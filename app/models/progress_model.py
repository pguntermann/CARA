"""Progress state model."""

from PyQt6.QtCore import QObject, pyqtSignal


class ProgressModel(QObject):
    """Model representing the progress state of long-running tasks.
    
    This model holds the state and emits
    signals when that state changes. Views observe these signals to update
    the UI automatically.
    """
    
    # Signals emitted when progress state changes
    progress_changed = pyqtSignal(int)  # Emitted when progress value changes (0-100)
    status_changed = pyqtSignal(str)   # Emitted when status message changes
    visibility_changed = pyqtSignal(bool)  # Emitted when progress bar visibility changes
    indeterminate_changed = pyqtSignal(bool)  # Emitted when indeterminate mode changes
    
    def __init__(self) -> None:
        """Initialize the progress model."""
        super().__init__()
        self._progress_value: int = 0
        self._status_message: str = "Ready"
        self._is_visible: bool = False
        self._is_indeterminate: bool = False
    
    @property
    def progress(self) -> int:
        """Get current progress value (0-100).
        
        Returns:
            Current progress value.
        """
        return self._progress_value
    
    @progress.setter
    def progress(self, value: int) -> None:
        """Set progress value and emit signal.
        
        Args:
            value: Progress value (0-100). Clamped to valid range.
        """
        clamped_value = max(0, min(100, value))
        if self._progress_value != clamped_value:
            self._progress_value = clamped_value
            self.progress_changed.emit(self._progress_value)
    
    @property
    def status(self) -> str:
        """Get current status message.
        
        Returns:
            Current status message.
        """
        return self._status_message
    
    @status.setter
    def status(self, message: str) -> None:
        """Set status message and emit signal.
        
        Args:
            message: Status message to display.
        """
        if self._status_message != message:
            self._status_message = message
            self.status_changed.emit(self._status_message)
    
    @property
    def is_visible(self) -> bool:
        """Check if progress bar is visible.
        
        Returns:
            True if progress bar is visible, False otherwise.
        """
        return self._is_visible
    
    def show_progress(self) -> None:
        """Show the progress bar and emit signal."""
        if not self._is_visible:
            self._is_visible = True
            self.visibility_changed.emit(True)
    
    def hide_progress(self) -> None:
        """Hide the progress bar and emit signal."""
        if self._is_visible:
            self._is_visible = False
            self.visibility_changed.emit(False)
    
    @property
    def is_indeterminate(self) -> bool:
        """Check if progress bar is in indeterminate mode.
        
        Returns:
            True if progress bar is in indeterminate (pulsing) mode, False otherwise.
        """
        return self._is_indeterminate
    
    @is_indeterminate.setter
    def is_indeterminate(self, value: bool) -> None:
        """Set indeterminate mode and emit signal.
        
        Args:
            value: True to enable indeterminate (pulsing) mode, False for normal progress.
        """
        if self._is_indeterminate != value:
            self._is_indeterminate = value
            self.indeterminate_changed.emit(value)
    
    def reset(self) -> None:
        """Reset progress to initial state."""
        self.progress = 0
        self.status = "Ready"
        self.is_indeterminate = False
        self.hide_progress()

