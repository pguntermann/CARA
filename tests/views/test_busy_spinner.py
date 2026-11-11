"""Tests for BusySpinner widget.

Requires a working Qt platform plugin (CI uses QT_QPA_PLATFORM=offscreen).
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt_starts_cleanly() -> bool:
    probe = (
        "import os; os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); "
        "from PyQt6.QtWidgets import QApplication; a = QApplication([]); print('ok')"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True,
            timeout=10,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        )
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_QT_OK = _qt_starts_cleanly()
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable")

if _QT_OK:
    from PyQt6.QtGui import QColor
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv[:1])

    from app.views.widgets.busy_spinner import BusySpinner


@requires_qt
class TestBusySpinner(unittest.TestCase):
    def _make(self, **kwargs):
        return BusySpinner(color=QColor(100, 150, 200), **kwargs)

    def test_hidden_on_construction(self):
        s = self._make()
        self.assertFalse(s.isVisible())

    def test_visible_after_start(self):
        s = self._make()
        s.start()
        self.assertTrue(s.isVisible())

    def test_hidden_after_stop(self):
        s = self._make()
        s.start()
        s.stop()
        self.assertFalse(s.isVisible())

    def test_timer_inactive_after_stop(self):
        s = self._make()
        s.start()
        s.stop()
        self.assertFalse(s._timer.isActive())

    def test_timer_active_after_start(self):
        s = self._make()
        s.start()
        self.assertTrue(s._timer.isActive())
        s.stop()

    def test_fixed_size_respected(self):
        s = self._make(size=32)
        self.assertEqual(s.width(), 32)
        self.assertEqual(s.height(), 32)


if __name__ == "__main__":
    unittest.main()
