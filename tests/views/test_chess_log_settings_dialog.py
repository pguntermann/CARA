"""Unit tests for ChessLogSettingsDialog.

Requires a working Qt platform plugin (CI uses QT_QPA_PLATFORM=offscreen).
Tests are skipped automatically when Qt cannot start.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from unittest.mock import MagicMock

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
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable in this environment")

if _QT_OK:
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv[:1])


def _make_uss(active_preset="CLAMP") -> MagicMock:
    uss = MagicMock()
    uss.get_chess_log.return_value = {"active_preset": active_preset}
    return uss


def _make_dialog(active_preset="CLAMP"):
    from app.views.dialogs.chess_log_settings_dialog import ChessLogSettingsDialog
    uss = _make_uss(active_preset)
    dlg = ChessLogSettingsDialog({}, uss)
    return dlg, uss


@requires_qt
class TestPresetPreselect(unittest.TestCase):
    def test_clamp_preselected_by_default(self):
        dlg, _ = _make_dialog("CLAMP")
        self.assertTrue(dlg._radio_buttons["CLAMP"].isChecked())
        for name in ("CCT", "3x3"):
            self.assertFalse(dlg._radio_buttons[name].isChecked())

    def test_cct_preselected_when_setting_is_cct(self):
        dlg, _ = _make_dialog("CCT")
        self.assertTrue(dlg._radio_buttons["CCT"].isChecked())

    def test_threexthree_preselected(self):
        dlg, _ = _make_dialog("3x3")
        self.assertTrue(dlg._radio_buttons["3x3"].isChecked())

    def test_unknown_preset_falls_back_to_clamp(self):
        dlg, _ = _make_dialog("Custom")
        self.assertTrue(dlg._radio_buttons["CLAMP"].isChecked())


@requires_qt
class TestCustomNotOffered(unittest.TestCase):
    """Custom must not appear as a preset option anywhere in the dialog."""

    def test_custom_not_in_radio_buttons(self):
        dlg, _ = _make_dialog("CLAMP")
        self.assertNotIn("Custom", dlg._radio_buttons)

    def test_custom_not_in_presets_list(self):
        from app.views.dialogs.chess_log_settings_dialog import ChessLogSettingsDialog
        self.assertNotIn("Custom", ChessLogSettingsDialog._PRESETS)


@requires_qt
class TestAcceptPersists(unittest.TestCase):
    def test_accept_saves_new_preset(self):
        dlg, uss = _make_dialog("CLAMP")
        dlg._radio_buttons["CCT"].setChecked(True)
        dlg._on_ok()
        uss.update_chess_log_settings.assert_called_once()
        saved = uss.update_chess_log_settings.call_args[0][0]
        self.assertEqual(saved["active_preset"], "CCT")
        uss.save.assert_called_once()

    def test_accept_does_not_write_custom_categories(self):
        dlg, uss = _make_dialog("CLAMP")
        dlg._on_ok()
        saved = uss.update_chess_log_settings.call_args[0][0]
        self.assertNotIn("custom_categories", saved)

    def test_cancel_does_not_persist(self):
        dlg, uss = _make_dialog("CLAMP")
        dlg._radio_buttons["CCT"].setChecked(True)
        dlg.reject()
        uss.update_chess_log_settings.assert_not_called()
        uss.save.assert_not_called()


@requires_qt
class TestAttributionLabels(unittest.TestCase):
    """Attribution subtitles must appear for CLAMP and 3x3, and nowhere else."""

    def _attribution_texts(self, dlg) -> set:
        from PyQt6.QtWidgets import QLabel
        return {lbl.text() for lbl in dlg.findChildren(QLabel) if lbl.text().startswith("Developed by")}

    def test_clamp_attribution_present(self):
        dlg, _ = _make_dialog("CLAMP")
        self.assertIn("Developed by Dr. Can Kabadayi", self._attribution_texts(dlg))

    def test_threexthree_attribution_present(self):
        dlg, _ = _make_dialog("CLAMP")
        self.assertIn("Developed by GM Noël Studer", self._attribution_texts(dlg))

    def test_exactly_two_attributions(self):
        """Exactly two attribution labels exist — CLAMP and 3x3."""
        dlg, _ = _make_dialog("CLAMP")
        texts = self._attribution_texts(dlg)
        self.assertEqual(len(texts), 2)


if __name__ == "__main__":
    unittest.main()
