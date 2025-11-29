"""Progress reporting service for long-running tasks."""

from typing import Optional

from app.models.progress_model import ProgressModel


class ProgressService:
    """Service for reporting progress of long-running tasks.
    
    This service provides a centralized way for services and controllers
    to report progress to the UI without direct dependencies on views.
    
    The service follows a singleton pattern and is automatically connected
    to the StatusPanel by MainWindow during initialization.
    
    Usage example:
        ```python
        from app.services.progress_service import ProgressService
        
        # Get the singleton instance
        progress = ProgressService.get_instance()
        
        # Start a long-running task
        progress.show_progress()
        progress.set_status("Loading data...")
        
        # Update progress during task
        for i in range(100):
            # Do some work...
            progress.report_progress(f"Processing item {i}/100", i)
        
        # Finish task
        progress.hide_progress()
        progress.set_status("Ready")
        ```
    """
    
    _instance: Optional['ProgressService'] = None
    _model: Optional[ProgressModel] = None
    
    def __new__(cls) -> 'ProgressService':
        """Singleton pattern: ensure only one instance exists."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> 'ProgressService':
        """Get the singleton instance of ProgressService.
        
        Returns:
            The singleton ProgressService instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def set_model(self, model: ProgressModel) -> None:
        """Set the progress model.
        
        Args:
            model: The ProgressModel instance to update.
        """
        self._model = model
    
    def show_progress(self) -> None:
        """Show the progress bar.
        
        This makes the progress bar visible and typically indicates
        the start of a long-running task.
        """
        if self._model:
            self._model.show_progress()
    
    def hide_progress(self) -> None:
        """Hide the progress bar.
        
        This hides the progress bar, typically called when a task completes.
        """
        if self._model:
            self._model.hide_progress()
    
    def set_progress(self, value: int) -> None:
        """Set progress bar value.
        
        Args:
            value: Progress value (0-100). Clamped to valid range.
        """
        if self._model:
            self._model.progress = value
            # Disable indeterminate mode when setting a specific progress value
            if self._model.is_indeterminate:
                self._model.is_indeterminate = False
    
    def set_indeterminate(self, indeterminate: bool = True) -> None:
        """Set progress bar to indeterminate (pulsing) mode.
        
        Args:
            indeterminate: True to enable indeterminate mode, False to disable.
        """
        if self._model:
            self._model.is_indeterminate = indeterminate
    
    def set_status(self, message: str) -> None:
        """Set the status message.
        
        Args:
            message: Status message to display. Supports HTML formatting
                     for colors and formatting.
        """
        if self._model:
            self._model.status = message
    
    def report_progress(self, message: str, percent: int) -> None:
        """Report both status message and progress percentage in one call.
        
        This is a convenience method that updates both the status message
        and the progress bar value in a single call.
        
        Args:
            message: Status message to display. Supports HTML formatting.
            percent: Progress value (0-100).
        """
        self.set_status(message)
        self.set_progress(percent)
    
    def reset(self) -> None:
        """Reset progress to initial state.
        
        This hides the progress bar and clears the progress value.
        """
        if self._model:
            self._model.reset()

