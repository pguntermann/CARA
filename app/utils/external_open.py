"""Utilities to open URLs/paths using the OS default handlers.

Qt's QDesktopServices.openUrl() can fail on some Linux desktop environments
(notably with certain portal/platform theme configurations). This module keeps
the Qt-based approach as the first choice, and falls back to common Linux tools
when needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import os
import sys
import subprocess

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices


def _debug(message: str) -> None:
    """Best-effort debug logging (never raises)."""
    try:
        from app.services.logging_service import LoggingService

        logging_service = LoggingService.get_instance()
        if getattr(logging_service, "_initialized", False):
            logging_service.debug(message)
    except Exception:
        pass


def open_url(url: QUrl, *, context: str = "") -> bool:
    """Open a URL using the platform default handler.

    Args:
        url: URL to open.
        context: Optional context string to help debugging (e.g. "help.manual").

    Returns:
        True if a launch mechanism was successfully invoked, else False.
    """
    ctx = f"[{context}] " if context else ""
    # Avoid platform/version-specific QUrl formatting enums; prefer a safely encoded string.
    try:
        url_str = bytes(url.toEncoded()).decode("utf-8", errors="replace")
    except Exception:
        url_str = url.toString()

    _debug(f"{ctx}open_url: attempting QDesktopServices.openUrl({url_str!r})")
    try:
        ok = bool(QDesktopServices.openUrl(url))
    except Exception as e:
        _debug(f"{ctx}open_url: QDesktopServices.openUrl raised {type(e).__name__}: {e}")
        ok = False

    _debug(f"{ctx}open_url: QDesktopServices.openUrl returned {ok}")
    if ok:
        return True

    if not sys.platform.startswith("linux"):
        return False

    # Linux fallback: xdg-open is the most widely available handler.
    # Avoid shell=True; pass a fully encoded URL string.
    xdg_open = os.environ.get("CARA_XDG_OPEN", "xdg-open")
    for cmd in ([xdg_open, url_str], ["gio", "open", url_str]):
        _debug(f"{ctx}open_url: fallback trying {cmd!r}")
        try:
            completed = subprocess.run(cmd, check=False)
            _debug(f"{ctx}open_url: fallback exit_code={completed.returncode} cmd={cmd!r}")
            if completed.returncode == 0:
                return True
        except FileNotFoundError:
            _debug(f"{ctx}open_url: fallback command not found: {cmd[0]!r}")
        except Exception as e:
            _debug(f"{ctx}open_url: fallback raised {type(e).__name__}: {e} cmd={cmd!r}")

    return False


def open_path(path: Path, *, context: str = "") -> bool:
    """Open a filesystem path (file or directory) in the default OS handler."""
    try:
        url = QUrl.fromLocalFile(str(path.resolve()))
    except Exception:
        url = QUrl.fromLocalFile(str(path))
    return open_url(url, context=context)

