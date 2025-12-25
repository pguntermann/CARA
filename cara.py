"""Entry point for CARA: Chess Analysis Review Application."""

import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from app.config.config_loader import ConfigLoader
from app.main_window import MainWindow
from app.services.error_handler import ErrorHandler
from app.utils.path_resolver import get_app_resource_path


def main() -> None:
    """Run CARA: Chess Analysis Review Application."""
    # Setup global exception handler for uncaught exceptions
    ErrorHandler.setup_exception_handler()
    
    try:
        app = QApplication(sys.argv)
        app.setApplicationName("CARA")
        app.setOrganizationName("CARA")
        
        # Set application icon
        icon_path = get_app_resource_path("appicon.svg")
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
        
        # Load configuration with strict validation
        loader = ConfigLoader()
        config = loader.load()
        
        # Initialize MainWindow with injected configuration
        window = MainWindow(config)
        window.show()
        
        sys.exit(app.exec())
    except Exception as e:
        # Catch any uncaught exceptions during startup or execution
        ErrorHandler.handle_fatal_error(e, "Application execution")


if __name__ == "__main__":
    main()
