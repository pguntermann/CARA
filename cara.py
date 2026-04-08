"""Entry point for CARA: Chess Analysis Review Application."""

import sys
import os
import multiprocessing
from pathlib import Path


def _configure_linux_frozen_runtime() -> None:
    """Mitigate GLib/GIO issues and Qt-on-Wayland problems when running a frozen Linux bundle.

    System GIO modules under /usr/lib/.../gio/modules expect the distro GLib; a bundled
    older GLib causes undefined-symbol failures.

    On Wayland, bundled Qt's native Wayland client can misbehave on some distros (e.g.
    segmentation faults on keyboard input on rolling releases). Defaulting to the xcb
    plugin uses XWayland and matches the previous GNOME-only workaround, now applied to
    all Wayland sessions unless the user opts out.

    Override behaviour:
    - Set ``QT_QPA_PLATFORM`` before launch (this function uses setdefault only).
    - Set ``CARA_USE_QT_WAYLAND=1`` to keep native Qt Wayland when not setting
      ``QT_QPA_PLATFORM``.
    """
    if not getattr(sys, "frozen", False):
        return
    if not sys.platform.startswith("linux"):
        return

    os.environ.pop("GIO_MODULE_DIR", None)
    os.environ.setdefault("GIO_USE_VFS", "local")

    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        use_native_wayland = (os.environ.get("CARA_USE_QT_WAYLAND") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if not use_native_wayland:
            os.environ.setdefault("QT_QPA_PLATFORM", "xcb")


_configure_linux_frozen_runtime()

# Suppress Qt font warnings before importing Qt modules
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.warning=false")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QtMsgType, qInstallMessageHandler, QLoggingCategory

from app.config.config_loader import ConfigLoader
from app.main_window import MainWindow
from app.services.error_handler import ErrorHandler
from app.utils.path_resolver import get_app_resource_path

def _is_kde_plasma_session() -> bool:
    """Best-effort detection of KDE Plasma desktop sessions (Linux only)."""
    if not sys.platform.startswith("linux"):
        return False
    xdg_current = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
    desktop_session = (os.environ.get("DESKTOP_SESSION") or "").lower()
    kde_full = (os.environ.get("KDE_FULL_SESSION") or "").lower()
    return (
        "kde" in xdg_current
        or "plasma" in xdg_current
        or "plasma" in desktop_session
        or kde_full in {"1", "true", "yes"}
    )


def _disable_plasma_platform_theme_plugin() -> None:
    """Disable KDE/Plasma Qt platform theme integration
    """
    if not _is_kde_plasma_session():
        return

    # Allow users to opt out explicitly.
    if (os.environ.get("CARA_DISABLE_PLASMA_PLATFORMTHEME") or "").strip() in {"0", "false", "no"}:
        return

    # If the user already configured a platform theme, don't override it.
    if os.environ.get("QT_QPA_PLATFORMTHEME"):
        return

    # Use a non-Plasma platform theme plugin to bypass Breeze/Plasma integration.
    # Qt will ignore this if the plugin is not available.
    os.environ["QT_QPA_PLATFORMTHEME"] = "gtk3"


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

    _disable_plasma_platform_theme_plugin()
    
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
