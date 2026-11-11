"""Unit tests for MomentDialog (active-preset design).

Requires a working Qt platform plugin (CI uses QT_QPA_PLATFORM=offscreen).
Tests are skipped automatically when Qt cannot start (e.g. macOS without display).
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _qt_starts_cleanly() -> bool:
    """Return True if QApplication can be created in this environment."""
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


def _make(active_preset="CLAMP", move_number=5, san="Nf3", is_white=True):
    from app.views.dialogs.moment_dialog import MomentDialog
    return MomentDialog({}, active_preset, move_number, san, is_white)


@requires_qt
class TestClampPreset(unittest.TestCase):
    def test_no_selection_returns_empty(self):
        dlg = _make("CLAMP")
        self.assertEqual(dlg.get_entries(), [])

    def test_single_chip_returns_one_entry(self):
        dlg = _make("CLAMP")
        m_btn = next(btn for cat, btn in dlg._chip_buttons if cat == "M")
        m_btn.setChecked(True)
        entries = dlg.get_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["preset"], "CLAMP")
        self.assertEqual(entries[0]["cat"], "M")
        self.assertEqual(entries[0]["why"], "")

    def test_multi_select_two_chips(self):
        dlg = _make("CLAMP")
        c_btn = next(btn for cat, btn in dlg._chip_buttons if cat == "C")
        l_btn = next(btn for cat, btn in dlg._chip_buttons if cat == "L")
        c_btn.setChecked(True)
        l_btn.setChecked(True)
        entries = dlg.get_entries()
        self.assertEqual(len(entries), 2)
        cats = {e["cat"] for e in entries}
        self.assertEqual(cats, {"C", "L"})
        self.assertTrue(all(e["preset"] == "CLAMP" for e in entries))

    def test_all_five_chips_multi_select(self):
        dlg = _make("CLAMP")
        for _, btn in dlg._chip_buttons:
            btn.setChecked(True)
        entries = dlg.get_entries()
        self.assertEqual(len(entries), 5)

    def test_why_shared_across_all_entries(self):
        dlg = _make("CLAMP")
        c_btn = next(btn for cat, btn in dlg._chip_buttons if cat == "C")
        l_btn = next(btn for cat, btn in dlg._chip_buttons if cat == "L")
        c_btn.setChecked(True)
        l_btn.setChecked(True)
        dlg._why_edit.setPlainText("Rook was trapped")
        entries = dlg.get_entries()
        self.assertTrue(all(e["why"] == "Rook was trapped" for e in entries))

    def test_zero_chips_with_why_returns_uncategorized_entry(self):
        dlg = _make("CLAMP")
        dlg._why_edit.setPlainText("general observation")
        entries = dlg.get_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["preset"], "CLAMP")
        self.assertEqual(entries[0]["cat"], "")
        self.assertEqual(entries[0]["why"], "general observation")

    def test_zero_chips_empty_why_returns_empty(self):
        dlg = _make("CLAMP")
        self.assertEqual(dlg.get_entries(), [])


@requires_qt
class TestCctPreset(unittest.TestCase):
    def test_no_selection_returns_empty(self):
        dlg = _make("CCT")
        self.assertEqual(dlg.get_entries(), [])

    def test_single_cct_returns_one_entry(self):
        dlg = _make("CCT")
        t_btn = next(btn for cat, btn in dlg._chip_buttons if cat == "Threats")
        t_btn.setChecked(True)
        entries = dlg.get_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["cat"], "Threats")
        self.assertEqual(entries[0]["preset"], "CCT")

    def test_multiple_cct_returns_multiple_entries_same_why(self):
        dlg = _make("CCT")
        c_btn = next(btn for cat, btn in dlg._chip_buttons if cat == "Checks")
        t_btn = next(btn for cat, btn in dlg._chip_buttons if cat == "Threats")
        c_btn.setChecked(True)
        t_btn.setChecked(True)
        dlg._why_edit.setPlainText("missed the threat")
        entries = dlg.get_entries()
        self.assertEqual(len(entries), 2)
        cats = {e["cat"] for e in entries}
        self.assertEqual(cats, {"Checks", "Threats"})
        self.assertTrue(all(e["why"] == "missed the threat" for e in entries))

    def test_all_three_cct_non_exclusive(self):
        dlg = _make("CCT")
        for _, btn in dlg._chip_buttons:
            btn.setChecked(True)
        self.assertEqual(len(dlg.get_entries()), 3)

    def test_zero_chips_with_why_returns_uncategorized_entry(self):
        dlg = _make("CCT")
        dlg._why_edit.setPlainText("missed a tactic")
        entries = dlg.get_entries()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["preset"], "CCT")
        self.assertEqual(entries[0]["cat"], "")
        self.assertEqual(entries[0]["why"], "missed a tactic")

    def test_zero_chips_empty_why_returns_empty(self):
        dlg = _make("CCT")
        self.assertEqual(dlg.get_entries(), [])


@requires_qt
class TestThreeByThreePreset(unittest.TestCase):
    def test_all_four_whys_filled(self):
        dlg = _make("3x3")
        answers = ["I wanted to attack", "It lost a tempo", "Engine moves centrally", "Check for pins first"]
        for (key, edit), answer in zip(dlg._threexthree_edits, answers):
            edit.setPlainText(answer)
        entries = dlg.get_entries()
        self.assertEqual(len(entries), 4)
        self.assertEqual([e["cat"] for e in entries], ["Why1", "Why2", "Why3", "Why4"])
        self.assertEqual([e["why"] for e in entries], answers)
        self.assertTrue(all(e["preset"] == "3x3" for e in entries))

    def test_partial_whys_skips_empty(self):
        dlg = _make("3x3")
        dlg._threexthree_edits[0][1].setPlainText("I wanted to attack")
        dlg._threexthree_edits[1][1].setPlainText("")
        dlg._threexthree_edits[2][1].setPlainText("")
        dlg._threexthree_edits[3][1].setPlainText("Slow down in sharp positions")
        entries = dlg.get_entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["cat"], "Why1")
        self.assertEqual(entries[1]["cat"], "Why4")

    def test_all_empty_returns_empty_list(self):
        dlg = _make("3x3")
        self.assertEqual(dlg.get_entries(), [])

    def test_ordering_why1_through_why4(self):
        dlg = _make("3x3")
        for _, edit in dlg._threexthree_edits:
            edit.setPlainText("answer")
        entries = dlg.get_entries()
        self.assertEqual([e["cat"] for e in entries], ["Why1", "Why2", "Why3", "Why4"])


@requires_qt
class TestMomentDialogConventions(unittest.TestCase):
    """CARA dialog conventions: resize grip, no fixed heights, config-driven spacing."""

    def test_resize_grip_installed_clamp(self):
        dlg = _make("CLAMP")
        self.assertTrue(hasattr(dlg, "_cara_themed_resize_grip"))

    def test_resize_grip_installed_cct(self):
        dlg = _make("CCT")
        self.assertTrue(hasattr(dlg, "_cara_themed_resize_grip"))

    def test_resize_grip_installed_3x3(self):
        dlg = _make("3x3")
        self.assertTrue(hasattr(dlg, "_cara_themed_resize_grip"))

    def test_dialog_height_not_fixed(self):
        dlg = _make("CLAMP")
        self.assertEqual(dlg.maximumHeight(), 16777215)

    def test_clamp_chips_no_fixed_height(self):
        dlg = _make("CLAMP")
        for _, btn in dlg._chip_buttons:
            self.assertEqual(btn.maximumHeight(), 16777215)

    def test_cct_chips_no_fixed_height(self):
        dlg = _make("CCT")
        for _, btn in dlg._chip_buttons:
            self.assertEqual(btn.maximumHeight(), 16777215)

    def test_why_min_height_from_config(self):
        dlg = _make("CLAMP")
        self.assertEqual(dlg._why_edit.minimumHeight(), dlg._why_min_height)


@requires_qt
class TestScrollbarStyling(unittest.TestCase):
    """All QTextEdits in MomentDialog must receive scrollbar styling."""

    def test_threexthree_edits_receive_scrollbar_styling(self):
        from unittest.mock import patch
        with patch("app.views.dialogs.moment_dialog.StyleManager.style_text_edit_scrollbar") as mock:
            dlg = _make("3x3")
        self.assertEqual(mock.call_count, 4)
        called_widgets = [call.args[0] for call in mock.call_args_list]
        for _, edit in dlg._threexthree_edits:
            self.assertIn(edit, called_widgets)

    def test_why_field_receives_scrollbar_styling_clamp(self):
        from unittest.mock import patch
        with patch("app.views.dialogs.moment_dialog.StyleManager.style_text_edit_scrollbar") as mock:
            dlg = _make("CLAMP")
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(mock.call_args.args[0], dlg._why_edit)

    def test_why_field_receives_scrollbar_styling_cct(self):
        from unittest.mock import patch
        with patch("app.views.dialogs.moment_dialog.StyleManager.style_text_edit_scrollbar") as mock:
            dlg = _make("CCT")
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(mock.call_args.args[0], dlg._why_edit)

    def test_3x3_edit_min_height_from_config(self):
        dlg = _make("3x3")
        for _, edit in dlg._threexthree_edits:
            self.assertEqual(edit.minimumHeight(), dlg._three_by_three_edit_min_height)


@requires_qt
class TestCustomNotOffered(unittest.TestCase):
    """Custom must not appear as an offered preset in MomentDialog."""

    def test_custom_preset_falls_back_to_clamp(self):
        dlg = _make("Custom")
        self.assertEqual(dlg._active_preset, "CLAMP")
        self.assertTrue(bool(dlg._chip_buttons), "CLAMP chips should be present")

    def test_tag_moment_static_factory_excludes_custom(self):
        from app.views.dialogs.moment_dialog import MomentDialog
        from unittest.mock import patch
        with patch.object(MomentDialog, "exec", return_value=0):
            result = MomentDialog.tag_moment({}, "Custom", 1, "e4", True, None)
        self.assertIsNone(result)


@requires_qt
class TestMomentDialogThemeColors(unittest.TestCase):
    """MomentDialog must read colors from config, not use hardcoded literals."""

    def _make_themed(self, extra_config: dict):
        from app.views.dialogs.moment_dialog import MomentDialog
        config = {"ui": {"dialogs": {"moment": extra_config}, "styles": {}}}
        return MomentDialog(config, "CLAMP", 1, "e4", True)

    def test_uses_hint_color_from_config(self):
        dlg = self._make_themed({"hint_color": [10, 20, 30]})
        self.assertEqual(dlg._hint_rgb, [10, 20, 30])
        self.assertIn("rgb(10,20,30)", dlg._hint.styleSheet())

    def test_uses_muted_color_from_config(self):
        dlg = self._make_themed({"muted_color": [11, 22, 33]})
        self.assertEqual(dlg._muted_rgb, [11, 22, 33])

    def test_uses_chip_border_from_config(self):
        dlg = self._make_themed({"chip_border_color": [44, 55, 66]})
        self.assertEqual(dlg._chip_border_rgb, [44, 55, 66])

    def test_uses_chip_hover_border_from_config(self):
        dlg = self._make_themed({"chip_hover_border_color": [77, 88, 99]})
        self.assertEqual(dlg._chip_hover_border_rgb, [77, 88, 99])

    def test_fallback_hint_color_dark(self):
        dlg = _make()
        self.assertEqual(dlg._hint_rgb, [220, 80, 80])

    def test_fallback_muted_color_dark(self):
        dlg = _make()
        self.assertEqual(dlg._muted_rgb, [130, 145, 165])

    def test_window_title_prefix_from_config(self):
        dlg = self._make_themed({"title": "My custom prefix"})
        self.assertIn("My custom prefix", dlg.windowTitle())

    def test_why_placeholder_from_config(self):
        dlg = self._make_themed({"why_placeholder": "My custom placeholder"})
        self.assertEqual(dlg._why_edit.placeholderText(), "My custom placeholder")


@requires_qt
class TestOnOkBehavior(unittest.TestCase):
    """_on_ok validation gating differs by preset."""

    def test_clamp_empty_shows_hint(self):
        dlg = _make("CLAMP")
        dlg._on_ok()
        self.assertIn("category", dlg._hint.text())

    def test_cct_empty_shows_hint(self):
        dlg = _make("CCT")
        dlg._on_ok()
        self.assertIn("category", dlg._hint.text())

    def test_3x3_empty_accepts_silently(self):
        from PyQt6.QtWidgets import QDialog
        dlg = _make("3x3")
        dlg._on_ok()
        # hint must NOT be shown
        self.assertFalse(dlg._hint.isVisible())
        # dialog must have accepted (result = Accepted)
        self.assertEqual(dlg.result(), QDialog.DialogCode.Accepted)


@requires_qt
class TestMomentDialogHeight(unittest.TestCase):
    """MomentDialog must open at a compact height (approx. 1/3 shorter than old default)."""

    # Before: sizeHint without the resize() call was 380 (CLAMP/CCT) and 1009 (3x3).
    _OLD_CLAMP_CCT_HEIGHT = 380
    _OLD_3X3_HEIGHT = 1009

    def _shown_height(self, preset):
        dlg = _make(preset)
        dlg.show()
        _APP.processEvents()
        return dlg.height()

    def test_clamp_height_at_least_25pct_shorter(self):
        h = self._shown_height("CLAMP")
        self.assertLess(
            h, self._OLD_CLAMP_CCT_HEIGHT * 0.75,
            f"CLAMP dialog height {h} must be at least 25% shorter than old height "
            f"{self._OLD_CLAMP_CCT_HEIGHT}",
        )

    def test_clamp_height_above_sane_minimum(self):
        h = self._shown_height("CLAMP")
        self.assertGreater(h, 150, f"CLAMP dialog height {h} must stay above 150px")

    def test_cct_height_at_least_25pct_shorter(self):
        h = self._shown_height("CCT")
        self.assertLess(
            h, self._OLD_CLAMP_CCT_HEIGHT * 0.75,
            f"CCT dialog height {h} must be at least 25% shorter than old height "
            f"{self._OLD_CLAMP_CCT_HEIGHT}",
        )

    def test_cct_height_above_sane_minimum(self):
        h = self._shown_height("CCT")
        self.assertGreater(h, 150, f"CCT dialog height {h} must stay above 150px")

    def test_3x3_height_at_least_25pct_shorter(self):
        h = self._shown_height("3x3")
        self.assertLess(
            h, self._OLD_3X3_HEIGHT * 0.75,
            f"3x3 dialog height {h} must be at least 25% shorter than old sizeHint "
            f"{self._OLD_3X3_HEIGHT}",
        )

    def test_3x3_height_above_sane_minimum(self):
        h = self._shown_height("3x3")
        self.assertGreater(h, 250, f"3x3 dialog height {h} must stay above 250px")


if __name__ == "__main__":
    unittest.main()
