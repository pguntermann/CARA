"""Entry point for CARA: Chess Analysis Review Application."""

import sys
import os
import multiprocessing
from pathlib import Path


def _configure_multiprocessing_for_qt_gui() -> None:
    """Force multiprocessing ``spawn`` before Qt loads (non-Windows).

    On Linux and macOS the default start method is often ``fork``. Forking after
    ``QApplication`` / Qt has initialized copies a fragile process (display
    connections, locks, plugins). ``ProcessPoolExecutor`` workers then deadlock
    or hang—commonly right after status text like "Prepared N game(s) for parsing...".

    Windows already uses ``spawn`` only; no change needed there.
    """
    if sys.platform == "win32":
        return
    try:
        multiprocessing.set_start_method("spawn")
    except RuntimeError:
        # Already set (e.g. by tests or embedding)
        pass


_configure_multiprocessing_for_qt_gui()


def _configure_linux_frozen_runtime() -> None:
    """Mitigate GLib/GIO plugin mismatch and GNOME Wayland decoration issues when frozen.

    System GIO modules under /usr/lib/.../gio/modules expect the distro GLib; a bundled
    older GLib causes undefined-symbol failures. GNOME on Wayland with some stacks (e.g.
    certain VMs) can show missing window frames unless Qt uses the X11/XWayland plugin.
    """
    if not getattr(sys, "frozen", False):
        return
    if not sys.platform.startswith("linux"):
        return

    os.environ.pop("GIO_MODULE_DIR", None)
    os.environ.setdefault("GIO_USE_VFS", "local")

    if os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland":
        desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").upper()
        if "GNOME" in desktop:
            os.environ.setdefault("QT_QPA_PLATFORM", "xcb")


_configure_linux_frozen_runtime()

# Suppress Qt font warnings before importing Qt modules
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts.warning=false")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import QtMsgType, qInstallMessageHandler, QLoggingCategory

from app.config.config_loader import (
    ConfigLoader,
    read_default_style_config_ref,
    resolve_style_config_path,
)
from app.main_window import MainWindow
from app.services.error_handler import ErrorHandler
from app.utils.path_resolver import get_app_resource_path
from app.services.theme_service import load_saved_theme_style_ref

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
        style_override = load_saved_theme_style_ref()
        if style_override:
            resolved = resolve_style_config_path(
                base_config_path=loader.config_path, style_ref=style_override
            )
            if not resolved.is_file():
                default_ref = read_default_style_config_ref(loader.config_path)
                default_name = default_ref or "app/config/style_default.config.json"
                err = (
                    f'Style config not found: "{resolved}" (from "{style_override}"). '
                    f"Falling back to default style config: {default_name}"
                )
                print(f"Configuration Error: {err}", file=sys.stderr)
                style_override = None
        config = loader.load_with_style_override(style_override) if style_override else loader.load()
        
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
        
        # Initialize MainWindow with injected configuration.
        # Reuse the same style ref we already loaded at startup to sync the Theme menu.
        active_style_ref = style_override or str(config.get("default_style_config", "") or "")
        window = MainWindow(config, active_style_ref=active_style_ref)
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
