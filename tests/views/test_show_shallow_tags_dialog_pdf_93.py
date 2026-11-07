"""#93: Show Shallow/Vague Logs' Export to PDF shows what's on screen before Save.

Its rows take text, flags and Ignore state from ``_pending_entries(i)`` (the helper
Save and the copy use), so a flag follows its text: an edited answer is unflagged.
"""

from __future__ import annotations

import ast
import os
import re
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.test_chess_log_moment_guards_93 import requires_qt  # noqa: E402

OLD, NEW = "old shallow text", "NEW unchecked text"
_REPO = Path(__file__).resolve().parent.parent.parent


@requires_qt
class TestDialogPdfRows(unittest.TestCase):
    def tearDown(self):
        self.h.close()

    def _open(self, tags, saved_mode=True):
        from PyQt6.QtWidgets import QApplication
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        from tests.test_chess_log_exports_91 import _Harness, _game
        QApplication.instance() or QApplication(sys.argv[:1])
        game = _game(tags)
        self.h = _Harness([game])
        shallow, vague = self.h.owner.get_shallow_vague_keys([game])
        return ShowShallowTagsDialog(
            {}, [game], self.h.owner, shallow_keys=shallow, vague_keys=vague, saved_mode=saved_mode
        )

    def _clamp(self):
        from tests.test_chess_log_exports_91 import _entry
        return {"0": [_entry("CLAMP", "C", OLD, is_shallow=True)]}

    def _3x3(self):
        from tests.test_chess_log_exports_91 import _entry
        return {"0": [_entry("3x3", "Why1", OLD, is_shallow=True),
                      _entry("3x3", "Why4", "still vague", is_vague=True)]}

    @staticmethod
    def _rows(dlg):
        return [r for g in dlg._build_tag_groups() for r in g["rows"]]

    def test_unsaved_edit_clamp_pdf_row_has_new_text_and_no_flag(self):
        dlg = self._open(self._clamp())
        dlg._widget_for_row[0]._why_texts["why"].setPlainText(NEW)
        (row,) = self._rows(dlg)
        self.assertEqual([e["why"] for e in row.entries], [NEW])
        self.assertFalse(row.is_shallow)
        self.assertFalse(row.is_vague)

    def test_unsaved_edit_3x3_pdf_row_drops_only_the_edited_answers_flag(self):
        dlg = self._open(self._3x3())
        dlg._widget_for_row[0]._why_texts["Why1"].setPlainText(NEW)
        (row,) = self._rows(dlg)
        self.assertIn(NEW, [e["why"] for e in row.entries])
        self.assertNotIn("Why1", row.shallow_cats)
        self.assertEqual(set(row.vague_cats), {"Why4"})      # the untouched answer keeps its flag

    def test_unedited_rows_keep_their_flags(self):
        (row,) = self._rows(self._open(self._clamp()))
        self.assertTrue(row.is_shallow)
        dlg = self._open(self._3x3())
        (row,) = self._rows(dlg)
        self.assertEqual((set(row.shallow_cats), set(row.vague_cats)), ({"Why1"}, {"Why4"}))

    def test_live_mode_pdf_row_has_the_unsaved_verdict(self):
        from PyQt6.QtWidgets import QApplication
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        from tests.test_chess_log_exports_91 import _Harness, _entry, _game
        QApplication.instance() or QApplication(sys.argv[:1])
        game = _game({"0": [_entry("CLAMP", "C", "unchecked note")]})   # no saved flag
        self.h = _Harness([game])
        dlg = ShowShallowTagsDialog(
            {}, [game], self.h.owner, shallow_keys={(game, "0", "CLAMP", "")}, saved_mode=False
        )
        (row,) = self._rows(dlg)
        self.assertTrue(row.is_shallow)

    def test_pdf_rows_and_copy_agree_on_which_answers_are_flagged(self):
        from tests.test_chess_log_exports_91 import _entry
        cases = (
            (self._clamp(), "why", NEW),
            (self._3x3(), "Why1", NEW),
            (self._3x3(), "Why4", "still vague"),       # edited back to equal text: unchanged
            ({"0": [_entry("CLAMP", "C", OLD, is_shallow=True)]}, None, None),
        )
        for tags, key, new in cases:
            with self.subTest(key=key, new=new):
                dlg = self._open(tags)
                if key:
                    dlg._widget_for_row[0]._why_texts[key].setPlainText(new)
                (row,) = self._rows(dlg)
                dlg._on_copy_to_clipboard()
                from PyQt6.QtWidgets import QApplication
                text = QApplication.clipboard().mimeData().text()
                marked_shallow = "[Shallow]" in text
                marked_vague = "[Vague]" in text
                if row.preset == "3x3":
                    self.assertEqual(bool(row.shallow_cats), marked_shallow)
                    self.assertEqual(bool(row.vague_cats), marked_vague)
                else:
                    self.assertEqual(row.is_shallow, marked_shallow)
                    self.assertEqual(row.is_vague, marked_vague)
                self.h.close()

    def test_ignore_state_comes_from_pending_entries(self):
        dlg = self._open(self._clamp())
        dlg._widget_for_row[0]._ignore_check.setChecked(True)
        (row,) = self._rows(dlg)
        self.assertTrue(any(e.get("ignore_shallow") for e in row.entries))
        self.assertFalse(row.is_shallow)        # Ignored answers are unflagged, as in the copy


class TestPdfBuilderGuard(unittest.TestCase):
    def _fn(self):
        tree = ast.parse((_REPO / "app/views/dialogs/show_shallow_tags_dialog.py").read_text())
        cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "ShowShallowTagsDialog")
        return next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_build_tag_groups")

    def test_pdf_flags_come_only_through_pending_entries_and_shared_predicates(self):
        names = set()
        for node in ast.walk(self._fn()):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.alias):
                names.add(node.name)
        self.assertIn("_pending_entries", names)
        self.assertIn("moment_flags", names)
        for forbidden in ("_preserved_is_shallow", "_preserved_is_vague", "_preserved_per_cat",
                          "_is_shallow_key", "_is_vague_key", "entry_has_flag"):
            self.assertNotIn(forbidden, names)


if __name__ == "__main__":
    unittest.main()
