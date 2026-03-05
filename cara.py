"""Entry point for CARA: Chess Analysis Review Application."""

import sys
import os
import multiprocessing
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QtMsgType, qInstallMessageHandler, QLoggingCategory

from app.config.config_loader import ConfigLoader
from app.main_window import MainWindow
from app.services.error_handler import ErrorHandler
from app.utils.path_resolver import get_app_resource_path

# Suppress Qt font warnings before importing Qt modules
# Set environment variable to reduce Qt font logging
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.warning=false")


def _qt_message_handler(msg_type: QtMsgType, context, message: str) -> None:
    """Filter out harmless Qt font warnings on Windows.
    
    Suppresses DirectWrite font warnings about missing fonts like "8514oem"
    which are harmless but noisy. All other messages are printed normally.
    """
    # Filter out DirectWrite font warnings (these are harmless on Windows)
    # The message format is: "DirectWrite: CreateFontFaceFromHDC() failed..."
    # We check for "DirectWrite" keyword which appears in all these warnings
    if "DirectWrite" in message:
        return  # Suppress these warnings
    
    # For all other messages, print to stderr (Qt's default behavior)
    # This preserves important warnings and errors while filtering font noise
    print(message, file=sys.stderr)


def main() -> None:
    """Run CARA: Chess Analysis Review Application."""

    
    # Suppress harmless Qt font warnings before creating QApplication
    qInstallMessageHandler(_qt_message_handler)
    
    # Disable Qt font category warnings (suppresses DirectWrite font errors)
    font_category = QLoggingCategory("qt.qpa.fonts")
    font_category.setEnabled(QtMsgType.QtWarningMsg, False)
    
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
        
        # Initialize logging service
        from app.services.logging_service import LoggingService
        logging_service = LoggingService.get_instance(config)
        logging_service.initialize()
        
        # Log application version
        app_version = config.get('version', 'unknown')
        logging_service.info(f"CARA version {app_version}")
        
        # Test logging service with debug message
        logging_service.debug("CARA application starting")
        
        # Load user settings and run migrations before UI uses them
        from app.services.user_settings_service import UserSettingsService
        from app.services.migration_service import MigrationService
        UserSettingsService.get_instance()
        MigrationService.run()
        
        # Initialize MainWindow with injected configuration
        window = MainWindow(config)
        window.show()
        
        exit_code = app.exec()
        
        # Log application shutdown
        logging_service.debug("CARA application shutting down")
        
        # Shutdown logging service gracefully before exit
        logging_service.shutdown()
        
        sys.exit(exit_code)
    except Exception as e:
        # Catch any uncaught exceptions during startup or execution
        ErrorHandler.handle_fatal_error(e, "Application execution")


if __name__ == "__main__":
    # Required for Windows + PyInstaller + multiprocessing
    # Prevents worker processes from executing main() and launching new GUI instances
    multiprocessing.freeze_support()
    main()
