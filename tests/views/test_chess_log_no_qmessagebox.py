"""Enforce that Chess Log source files never use QMessageBox.

Chess Log dialogs must use the themed MessageDialog instead of the native
QMessageBox so that messages respect CARA's theme system.
"""

from __future__ import annotations

import html
import os
import re
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_REPO = Path(__file__).resolve().parents[2]

_CHESS_LOG_FILES = [
    _REPO / "app/main_window.py",
    _REPO / "app/controllers/chess_log_controller.py",
    _REPO / "app/controllers/chess_log_charts_controller.py",
    _REPO / "app/views/detail_chess_log_charts_view.py",
    _REPO / "app/views/dialogs/chess_log_settings_dialog.py",
    _REPO / "app/views/dialogs/moment_dialog.py",
    _REPO / "app/views/dialogs/show_shallow_tags_dialog.py",
    _REPO / "app/views/dialogs/show_tags_dialog.py",
    _REPO / "app/views/menus/chess_log_menu.py",
    _REPO / "app/views/menus/chess_log_charts_menu.py",
    _REPO / "app/views/menus/chess_log_charts_context_menu.py",
    _REPO / "app/services/chess_log_storage_service.py",
    _REPO / "app/services/chess_log_stats_service.py",
    _REPO / "app/services/chess_log_narrative_service.py",
]

_QMESSAGEBOX_RE = re.compile(r'\bQMessageBox\b')


def _qt_available() -> bool:
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c",
             "import os; os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); "
             "from PyQt6.QtWidgets import QApplication; QApplication([]); print('ok')"],
            capture_output=True, timeout=10,
            cwd=str(_REPO),
        )
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_QT_AVAILABLE = _qt_available()


class TestChessLogNoQMessageBox(unittest.TestCase):
    """Chess Log source files must not use QMessageBox."""

    def test_no_qmessagebox_in_chess_log_files(self) -> None:
        hits: list[str] = []
        for path in _CHESS_LOG_FILES:
            if not path.exists():
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if _QMESSAGEBOX_RE.search(line):
                    hits.append(f"{path.relative_to(_REPO)}:{lineno}: {line.strip()}")
        if hits:
            self.fail(
                "QMessageBox found in Chess Log source files — use MessageDialog instead:\n"
                + "\n".join(f"  {h}" for h in hits)
            )


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestCheckLogsErrorEscaping(unittest.TestCase):
    """Dynamic text in Check Logs error messages must be HTML-escaped."""

    def test_check_logs_error_escapes_html_in_message(self) -> None:
        from unittest.mock import MagicMock, patch
        import sys
        from PyQt6.QtWidgets import QApplication
        _app = QApplication.instance() or QApplication(sys.argv)

        from app.views.detail_chess_log_charts_view import DetailChessLogChartsView
        import json, os as _os
        cfg_path = _REPO / "app/config/config.json"
        config = json.loads(cfg_path.read_text(encoding="utf-8"))

        view = DetailChessLogChartsView(config=config)
        view._shallow_spinner = MagicMock()
        view._shallow_status_label = MagicMock()
        view._shallow_token_label = MagicMock()
        view._controller = MagicMock()
        view._controller.is_ai_configured.return_value = False

        raw_message = "<html>500 Internal Error</html> & more"
        with patch("app.views.dialogs.message_dialog.MessageDialog.show_warning") as mock_warn:
            view._on_shallow_failed(raw_message)

        mock_warn.assert_called_once()
        _config, title, body, _parent = mock_warn.call_args[0]
        self.assertEqual(title, "Check Logs Error")
        self.assertIn("&lt;html&gt;", body)
        self.assertIn("&amp;", body)
        self.assertNotIn("<html>", body)
        self.assertIn("<br>", body)
