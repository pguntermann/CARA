"""#93: a flag belongs to the text it was checked on, in the tab's PDF data and copy.

Opens Show Shallow/Vague Logs from saved results, edits a Shallow-flagged answer,
then reads the Chess Log tab's PDF rows and Copy log to clipboard:
  A. edit not saved  -> the saved text with its saved flag (the PDF is saved-only);
  B. edit saved      -> the new text, never marked Shallow.
"""

from __future__ import annotations

import os
import sys
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.test_chess_log_moment_guards_93 import requires_qt  # noqa: E402

OLD, NEW = "old shallow text", "NEW unchecked text"


@requires_qt
class TestEditedFlaggedAnswer(unittest.TestCase):
    def tearDown(self):
        self.h.close()

    def _open(self, tags):
        from PyQt6.QtWidgets import QApplication
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        from tests.test_chess_log_exports_91 import _Harness, _game
        QApplication.instance() or QApplication(sys.argv[:1])
        game = _game(tags)
        self.h = _Harness([game])
        self.view = self.h.view()
        shallow, vague = self.h.owner.get_shallow_vague_keys([game])
        return ShowShallowTagsDialog(
            {}, [game], self.h.owner, shallow_keys=shallow, vague_keys=vague, saved_mode=True
        )

    def _outputs(self):
        from tests.test_chess_log_exports_91 import _clipboard
        rows = [r for g in self.view._build_check_log_tag_groups() for r in g["rows"]]
        self.view._copy_log_to_clipboard()
        text, _html = _clipboard()
        return rows, text

    def _clamp(self):
        from tests.test_chess_log_exports_91 import _entry
        return {"0": [_entry("CLAMP", "C", OLD, is_shallow=True)]}

    def _3x3(self):
        from tests.test_chess_log_exports_91 import _entry
        return {"0": [_entry("3x3", "Why1", OLD, is_shallow=True),
                      _entry("3x3", "Why4", "still vague", is_vague=True)]}

    def test_a_unsaved_edit_pdf_and_copy_keep_the_saved_text_and_flag(self):
        for tags, key in ((self._clamp(), "why"), (self._3x3(), "Why1")):
            with self.subTest(preset=next(iter(tags.values()))[0]["preset"]):
                dlg = self._open(tags)
                dlg._widget_for_row[0]._why_texts[key].setPlainText(NEW)
                rows, text = self._outputs()
                self.assertIn(OLD, [e["why"] for r in rows for e in r.entries])
                self.assertNotIn(NEW, [e["why"] for r in rows for e in r.entries])
                self.assertIn(f"{OLD} [Shallow]", text)
                self.assertNotIn(NEW, text)
                self.h.close()

    def test_b_saved_edit_new_text_is_never_marked_shallow(self):
        for tags, key in ((self._clamp(), "why"), (self._3x3(), "Why1")):
            with self.subTest(preset=next(iter(tags.values()))[0]["preset"]):
                dlg = self._open(tags)
                dlg._widget_for_row[0]._why_texts[key].setPlainText(NEW)
                dlg._on_save()
                rows, text = self._outputs()
                for r in rows:                       # PDF rows: no Shallow on the new text
                    self.assertFalse(r.is_shallow)
                    self.assertNotIn("Why1", r.shallow_cats)
                    self.assertFalse(any(e["why"] == NEW and e.get("is_shallow") for e in r.entries))
                for line in text.splitlines():       # tab copy: no marker on the new text
                    if NEW in line:
                        self.assertNotIn("[Shallow]", line)
                self.assertNotIn(f"{OLD} [Shallow]", text)
                self.h.close()


if __name__ == "__main__":
    unittest.main()
