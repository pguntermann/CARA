"""Tests for AccuracyDistributionChartWidget: import alias and smooth-line paint path.

Regression for #75: accuracy_distribution_chart_widget imported _smooth_polyline_path
from detail_player_stats_view, which no longer defined it after Phase 3 moved the
function to _chart_layout_helpers.  A re-export alias restores the name.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest import mock

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


_QT_AVAILABLE = _qt_starts_cleanly()

if _QT_AVAILABLE:
    from PyQt6.QtGui import QColor, QImage, QPainter
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication(sys.argv)

    from app.views.widgets.accuracy_distribution_chart_widget import (
        AccuracyDistributionChartWidget,
    )


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestSmoothPolylineAlias(unittest.TestCase):
    """The compat alias must be importable from detail_player_stats_view."""

    def test_import_alias(self) -> None:
        # This is the exact import that raised ImportError before the fix.
        from app.views.detail_player_stats_view import _smooth_polyline_path  # noqa: F401

        self.assertIsNotNone(_smooth_polyline_path)

    def test_alias_is_the_shared_helper(self) -> None:
        from app.views.detail_player_stats_view import _smooth_polyline_path
        from app.views.widgets._chart_layout_helpers import smooth_polyline_path

        self.assertIs(_smooth_polyline_path, smooth_polyline_path)


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestAccuracyDistributionSmoothRender(unittest.TestCase):
    """Widget must render in smooth mode without crashing (exercises line 494)."""

    def _render(self, widget: "AccuracyDistributionChartWidget", width: int = 600, height: int = 200) -> QImage:
        widget.resize(width, height)
        img = QImage(width, height, QImage.Format.Format_ARGB32)
        p = QPainter(img)
        widget.render(p)
        p.end()
        return img

    def test_smooth_mode_renders_without_crash(self) -> None:
        """_smooth_polyline_path at line 494 must be called during paint.

        10 accuracy values spread over 28 points → bin_count >= 5 →
        len(points_line) > 1 → smooth branch runs.  Patching the name as
        bound in the widget module (wraps=real fn) proves the branch is
        actually reached, not just that the import succeeded.
        """
        import app.views.widgets.accuracy_distribution_chart_widget as _wmod
        from app.views.widgets._chart_layout_helpers import smooth_polyline_path

        accuracy_values = [70.0, 75.0, 78.0, 80.0, 82.0, 85.0, 88.0, 92.0, 95.0, 98.0]
        widget = AccuracyDistributionChartWidget(
            config={},
            accuracy_values=accuracy_values,
            text_color=QColor(200, 200, 200),
        )
        with mock.patch.object(
            _wmod, "_smooth_polyline_path", wraps=smooth_polyline_path
        ) as spy:
            self._render(widget)
        self.assertGreaterEqual(
            spy.call_count, 1,
            "_smooth_polyline_path was never called — smooth branch not reached",
        )
