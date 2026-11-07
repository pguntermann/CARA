"""#93: Show Shallow/Vague Logs' copy before Save shows what Save would write.

Live mode (opened from a Check Logs run): unsaved verdicts, unsaved text edits and
the Ignore state as currently set.  Saved mode: the saved results, as before.
The Chess Log tab's copy stays saved-flags-only (also covered in
test_chess_log_exports_91).
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.test_chess_log_moment_guards_93 import requires_qt  # noqa: E402

_PGN = (
    '[Event "T"][Site "?"][Date "2026.01.01"][Round "?"]'
    '[White "Alice"][Black "Bob"][Result "*"]\n\n'
    "1. e4 e5 2. Nf3 Nc6 *\n"
)


def _entry(preset, cat, why, **extra):
    d = {"preset": preset, "cat": cat, "why": why}
    d.update(extra)
    return d


@requires_qt
class TestDialogCopyBeforeSave(unittest.TestCase):
    def setUp(self):
        from PyQt6.QtWidgets import QApplication
        from app.models.database_model import GameData
        self._app = QApplication.instance() or QApplication(sys.argv[:1])
        self.game = GameData(game_number=1, pgn=_PGN, white="Alice", black="Bob", result="*")
        self.stored = {
            "0": [_entry("CLAMP", "C", "attacked too early")],           # unsaved Shallow verdict
            "0.0.0": [_entry("CLAMP", "L", "saved shallow", is_shallow=True)],  # will be edited
        }

    def _dialog(self, *, saved_mode, shallow_keys):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        ctrl = MagicMock()
        ctrl.get_tags_for_game.return_value = self.stored
        ctrl.count_unchecked_answers.return_value = 0
        return ShowShallowTagsDialog(
            {}, [self.game], ctrl, shallow_keys=shallow_keys, saved_mode=saved_mode,
        )

    def _copy(self, dlg):
        dlg._on_copy_to_clipboard()
        mime = self._app.clipboard().mimeData()
        return mime.text(), mime.html()

    def _live_keys(self):
        return {(self.game, "0", "CLAMP", ""), (self.game, "0.0.0", "CLAMP", "")}

    def test_live_mode_marks_unsaved_verdict(self):
        text, html = self._copy(self._dialog(saved_mode=False, shallow_keys=self._live_keys()))
        self.assertIn("attacked too early [Shallow]", text)
        self.assertIn("9a4400", html)

    def test_live_mode_shows_unsaved_text_edit(self):
        dlg = self._dialog(saved_mode=False, shallow_keys=self._live_keys())
        widget = dlg._widget_for_row[1]
        widget._why_texts["why"].setPlainText("edited just now")
        text, html = self._copy(dlg)
        self.assertIn("edited just now", text)
        self.assertIn("edited just now", html)
        self.assertNotIn("saved shallow", text)
        # The verdict was for the old text: Save would drop the chip, so the copy does too.
        self.assertNotIn("edited just now [Shallow]", text)

    def test_live_mode_follows_the_ignore_box(self):
        dlg = self._dialog(saved_mode=False, shallow_keys=self._live_keys())
        dlg._widget_for_row[0]._ignore_check.setChecked(True)
        text, _ = self._copy(dlg)
        self.assertIn("attacked too early", text)
        self.assertNotIn("attacked too early [Shallow]", text)

    def test_live_copy_equals_what_save_would_write(self):
        dlg = self._dialog(saved_mode=False, shallow_keys=self._live_keys())
        dlg._widget_for_row[1]._why_texts["why"].setPlainText("edited")
        pending = dlg._pending_entries(1)
        self.assertEqual([e["why"] for e in pending], ["edited"])
        self.assertFalse(any(e.get("is_shallow") for e in pending))

    def test_saved_mode_uses_saved_results_not_widget_edits(self):
        keys = {(self.game, "0.0.0", "CLAMP", "")}
        dlg = self._dialog(saved_mode=True, shallow_keys=keys)
        dlg._widget_for_row[0]._why_texts["why"].setPlainText("typed but unsaved")
        text, _ = self._copy(dlg)
        self.assertIn("saved shallow [Shallow]", text)
        self.assertNotIn("typed but unsaved", text)

    def test_saved_mode_does_not_mark_an_unsaved_verdict(self):
        dlg = self._dialog(saved_mode=True, shallow_keys={(self.game, "0.0.0", "CLAMP", "")})
        text, _ = self._copy(dlg)
        self.assertNotIn("attacked too early [Shallow]", text)


if __name__ == "__main__":
    unittest.main()
