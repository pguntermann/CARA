"""Path resolution utility for determining where to store user data files.

This module handles smart path resolution that:
1. Checks if the app has write access to its root directory
2. If yes, uses the root directory (portable mode)
3. If no, uses platform-specific user data directories
4. Copies default files from app root to user data directory if needed
"""

import os
import sys
import shutil
from pathlib import Path
from typing import Optional, Tuple


def get_app_root() -> Path:
    """Get the application root directory.
    
    Handles both development mode and PyInstaller bundled mode.
    
    Returns:
        Path to the application root directory.
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller bundled mode
        # sys.executable points to Contents/MacOS/CARA
        # Data files are in Contents/Resources/
        executable_path = Path(sys.executable)
        if executable_path.parent.name == "MacOS":
            # macOS app bundle: go up to Contents, then to Resources
            return executable_path.parent.parent / "Resources"
        else:
            # Windows or other: data files are in _internal directory
            return executable_path.parent / "_internal"
    else:
        # Development mode
        # Use the directory containing cara.py (parent of app directory)
        return Path(__file__).parent.parent.parent


def has_write_access(directory: Path) -> bool:
    """Check if the application has write access to a directory.
    
    Args:
        directory: Directory path to check.
        
    Returns:
        True if write access is available, False otherwise.
    """
    directory_created = False
    if not directory.exists():
        # Try to create the directory
        try:
            directory.mkdir(parents=True, exist_ok=True)
            directory_created = True
        except (OSError, PermissionError):
            return False
    
    # Try to create a test file
    test_file = directory / ".write_test"
    try:
        test_file.touch()
        test_file.unlink()
        return True
    except (OSError, PermissionError):
        # If write test failed and we created the directory, clean it up
        if directory_created:
            try:
                directory.rmdir()
            except (OSError, PermissionError):
                # If cleanup fails, that's okay - directory might not be empty
                pass
        return False


def get_user_data_directory() -> Path:
    """Get the platform-specific user data directory.
    
    Returns:
        Path to the user data directory for CARA.
    """
    app_name = "CARA"
    
    if sys.platform == "win32":
        # Windows: %APPDATA%\CARA
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / app_name
        # Fallback to user home
        return Path.home() / "AppData" / "Roaming" / app_name
    elif sys.platform == "darwin":
        # macOS: ~/Library/Application Support/CARA
        return Path.home() / "Library" / "Application Support" / app_name
    else:
        # Linux and other Unix-like: ~/.config/CARA or ~/.local/share/CARA
        xdg_data_home = os.getenv("XDG_DATA_HOME")
        if xdg_data_home:
            return Path(xdg_data_home) / app_name
        return Path.home() / ".local" / "share" / app_name


def resolve_data_file_path(filename: str) -> Tuple[Path, bool]:
    """Resolve the path for a user data file (settings, parameters, etc.).
    
    This function implements the smart path resolution logic:
    1. Check if app root has write access
    2. If yes, use app root (portable mode)
    3. If no, use user data directory
    4. If using user data directory and file doesn't exist, copy from app root
    
    Args:
        filename: Name of the data file (e.g., "user_settings.json").
        
    Returns:
        Tuple of (resolved_path, is_portable_mode).
        - resolved_path: The path where the file should be stored/loaded
        - is_portable_mode: True if using app root, False if using user data directory
    """
    app_root = get_app_root()
    app_root_file = app_root / filename
    
    # Check if app root has write access
    if has_write_access(app_root):
        # Portable mode: use app root directory
        return app_root_file, True
    
    # No write access: use user data directory
    user_data_dir = get_user_data_directory()
    user_data_dir.mkdir(parents=True, exist_ok=True)
    user_data_file = user_data_dir / filename
    
    # If file doesn't exist in user data directory, copy from app root if it exists
    if not user_data_file.exists() and app_root_file.exists():
        try:
            shutil.copy2(app_root_file, user_data_file)
        except (OSError, PermissionError, shutil.Error) as e:
            # If copy fails, we'll just use the user data directory
            # The file will be created with defaults when first saved
            pass
    
    return user_data_file, False


def get_app_resource_path(relative_path: str) -> Path:
    """Get the path to an application resource file.
    
    Resources are always read from the app root directory, not user data.
    This is for read-only resources like config.json, icons, etc.
    
    Args:
        relative_path: Relative path from app root (e.g., "app/config/config.json").
        
    Returns:
        Path to the resource file.
    """
    app_root = get_app_root()
    return app_root / relative_path

