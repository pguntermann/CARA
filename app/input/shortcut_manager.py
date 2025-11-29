"""Global keyboard shortcut manager for routing key commands."""

from PyQt6.QtGui import QShortcut, QKeySequence
from PyQt6.QtCore import Qt
from typing import Dict, Any, Callable, Optional
from PyQt6.QtWidgets import QWidget


class ShortcutManager:
    """Manages global keyboard shortcuts and routes them to handlers.
    
    This manager registers global shortcuts that work regardless of
    widget focus. Shortcuts are routed through controllers following
    PyQt's Model/View architecture.
    
    Usage:
        ```python
        manager = ShortcutManager(main_window)
        manager.register_shortcut("X", lambda: controller.rotate_board())
        ```
    """
    
    def __init__(self, parent: QWidget) -> None:
        """Initialize the shortcut manager.
        
        Args:
            parent: Parent widget (typically MainWindow) for shortcuts.
        """
        self.parent = parent
        self.shortcuts: Dict[str, QShortcut] = {}
    
    def register_shortcut(self, key: str, handler: Callable[[], None]) -> None:
        """Register a global keyboard shortcut.
        
        Args:
            key: Key to register (e.g., "X", "Ctrl+S", "F1").
            handler: Callback function to execute when shortcut is triggered.
        """
        # Create QShortcut with MainWindow as parent (works globally)
        shortcut = QShortcut(QKeySequence(key), self.parent)
        shortcut.activated.connect(handler)
        self.shortcuts[key] = shortcut
    
    def unregister_shortcut(self, key: str) -> None:
        """Unregister a keyboard shortcut.
        
        Args:
            key: Key to unregister.
        """
        if key in self.shortcuts:
            self.shortcuts[key].setEnabled(False)
            del self.shortcuts[key]

