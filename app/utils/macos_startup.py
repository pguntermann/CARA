"""macOS startup helpers that must run before QApplication is constructed."""

from __future__ import annotations

import os
import sys
import warnings


# UF_HIDDEN is 0x8000 in <sys/stat.h> on macOS.
_UF_HIDDEN = 0x8000


def clear_platform_plugin_hidden_flags() -> None:
    """Clear the UF_HIDDEN file flag from Qt's platform-plugins directory.

    macOS sometimes sets UF_HIDDEN on libqcocoa.dylib (and sibling plugins)
    during pip's download/extraction.  The flag is invisible to every
    file-integrity check — permissions, dlopen, codesigning, and architecture
    all look fine — but prevents Qt's own plugin-discovery from succeeding,
    causing QGuiApplicationPrivate::createPlatformIntegration() to qFatal-abort
    with "Could not find the Qt platform plugin 'cocoa'".  The flag can
    reassert itself between process launches, so this runs unconditionally on
    every macOS startup rather than as a one-time fix.

    Safe to call on any platform: returns immediately on non-macOS.  All errors
    are suppressed; this must never prevent startup.
    """
    if sys.platform != "darwin":
        return
    try:
        import PyQt6  # noqa: PLC0415  (late import by design)
        plugins_dir = os.path.join(
            os.path.dirname(PyQt6.__file__), "Qt6", "plugins", "platforms"
        )
        _clear_hidden_recursive(plugins_dir)
    except Exception as exc:  # pragma: no cover
        # Swallow everything — a broken path, missing permission, or non-standard
        # PyQt6 layout must never abort startup.
        warnings.warn(
            f"macOS UF_HIDDEN cleanup skipped ({type(exc).__name__}: {exc})",
            RuntimeWarning,
            stacklevel=2,
        )


def _clear_hidden_recursive(path: str) -> None:
    """Clear UF_HIDDEN from *path* and each file directly inside it if it's a directory."""
    _clear_hidden_flag(path)
    try:
        if os.path.isdir(path):
            for name in os.listdir(path):
                _clear_hidden_flag(os.path.join(path, name))
    except OSError:
        pass


def _clear_hidden_flag(path: str) -> None:
    """Clear UF_HIDDEN from a single file or directory; silently ignores errors."""
    try:
        st = os.lstat(path)
        current = getattr(st, "st_flags", 0)
        if current & _UF_HIDDEN:
            os.chflags(path, current & ~_UF_HIDDEN)  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        pass
