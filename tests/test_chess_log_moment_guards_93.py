"""Issue #93: guards for the shared moment renderer.

  - No user-facing text from Copy log to clipboard (Chess Log tab) or Show
    Shallow/Vague Logs' copy contains a path key (three or more dot-separated
    integers, so evaluations such as 0.5 and dates cannot trip it).
  - Source-level: both callers build their moment text through the renderer
    and nowhere else.
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_REPO = Path(__file__).resolve().parent.parent
PATH_KEY_RE = re.compile(r"\d+(?:\.\d+){2,}")


def _qt_starts_cleanly() -> bool:
    probe = (
        "import os; os.environ.setdefault('QT_QPA_PLATFORM','offscreen'); "
        "from PyQt6.QtWidgets import QApplication; a = QApplication([]); print('ok')"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, timeout=10, cwd=str(_REPO)
        )
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_QT_OK = _qt_starts_cleanly()
requires_qt = unittest.skipUnless(_QT_OK, "Qt platform plugin unavailable")

if _QT_OK:
    from PyQt6.QtWidgets import QApplication
    _APP = QApplication.instance() or QApplication(sys.argv[:1])


def _tags():
    from tests.test_chess_log_exports_91 import _entry
    return {
        "0.0.0": [_entry("CLAMP", "C", "clamp shallow note", is_shallow=True)],
        "0": [
            _entry("3x3", "Why1", "why one"),
            _entry("3x3", "Why2", "why two generic", is_shallow=True),
            _entry("3x3", "Why4", "vague lesson", is_vague=True),
        ],
        # A path the PGN does not reach: must fall back without printing the key.
        "0.0.0.0.0": [_entry("CLAMP", "L", "off the board", is_vague=True)],
    }


@requires_qt
class TestNoPathKeyInCopies(unittest.TestCase):
    def tearDown(self):
        self.h.close()

    def _assert_clean(self, text: str, html: str):
        from tests.services.test_chess_log_moment_renderer import _html_text
        self.assertNotRegex(text, PATH_KEY_RE)
        self.assertNotRegex(_html_text(html), PATH_KEY_RE)
        self.assertIn("[Shallow]", text)      # the copy really holds the moments
        self.assertIn("[Vague]", text)

    def test_chess_log_tab_copy(self):
        from tests.test_chess_log_exports_91 import _Harness, _clipboard, _game
        self.h = _Harness([_game(_tags())])
        self.h.view()._copy_log_to_clipboard()
        text, html = _clipboard()
        self._assert_clean(text, html)

    def test_show_shallow_vague_logs_copy(self):
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        from tests.test_chess_log_exports_91 import _Harness, _clipboard, _game
        game = _game(_tags())
        self.h = _Harness([game])
        shallow, vague = self.h.owner.get_shallow_vague_keys([game])
        dlg = ShowShallowTagsDialog(
            {}, [game], self.h.owner, shallow_keys=shallow, vague_keys=vague,
            check_run_info={"model": "m", "date": "2026-10-31T14:00:00Z"},
            source_label="src", saved_mode=True,
        )
        dlg._on_copy_to_clipboard()
        text, html = _clipboard()
        self._assert_clean(text, html)

    def test_both_callers_agree_on_the_moments_body(self):
        from tests.test_chess_log_exports_91 import _Harness, _clipboard, _game
        from app.views.dialogs.show_shallow_tags_dialog import ShowShallowTagsDialog
        game = _game(_tags())
        self.h = _Harness([game])
        self.h.view()._copy_log_to_clipboard()
        tab_text, _ = _clipboard()
        shallow, vague = self.h.owner.get_shallow_vague_keys([game])
        dlg = ShowShallowTagsDialog(
            {}, [game], self.h.owner, shallow_keys=shallow, vague_keys=vague, saved_mode=True,
        )
        dlg._on_copy_to_clipboard()
        dlg_text, _ = _clipboard()
        for answer in ("Why1: why one", "Why2: why two generic [Shallow]", "Why4: vague lesson [Vague]"):
            self.assertIn(answer, tab_text)
            self.assertIn(answer, dlg_text)


# ---------------------------------------------------------------------------
# Source-level guards
# ---------------------------------------------------------------------------

def _function(rel: str, name: str, cls: str) -> ast.FunctionDef:
    tree = ast.parse((_REPO / rel).read_text(encoding="utf-8"))
    klass = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == cls)
    return next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == name)


def _names(fn: ast.AST):
    out = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.alias):
            out.add(node.name)
    return out


_VIEW = "app/views/detail_chess_log_charts_view.py"
_DIALOG = "app/views/dialogs/show_shallow_tags_dialog.py"
# The routes that build moment text some other way (snapshots / per-row formatters).
_OTHER_ROUTES = {
    "_build_check_log_tag_groups", "_build_tag_groups", "_tag_groups_html", "_tag_groups_plain",
    "TagRowSnapshot", "snapshot", "node_info", "game_header_text",
}


class TestCallersUseTheRenderer(unittest.TestCase):
    CALLERS = (
        (_VIEW, "DetailChessLogChartsView", "_copy_log_to_clipboard"),
        (_VIEW, "DetailChessLogChartsView", "_render_check_log_moments"),
        (_VIEW, "DetailChessLogChartsView", "_charts_log_html_for_copy"),
        (_DIALOG, "ShowShallowTagsDialog", "_on_copy_to_clipboard"),
    )

    def test_chess_log_tab_copy_goes_through_the_renderer(self):
        render = _function(_VIEW, "_render_check_log_moments", "DetailChessLogChartsView")
        self.assertIn("ChessLogMomentRenderer", _names(render))
        self.assertIn("render", _names(render))
        copy = _function(_VIEW, "_copy_log_to_clipboard", "DetailChessLogChartsView")
        self.assertIn("_render_check_log_moments", _names(copy))
        html_fn = _function(_VIEW, "_charts_log_html_for_copy", "DetailChessLogChartsView")
        self.assertIn("_render_check_log_moments", _names(html_fn))

    def test_show_shallow_vague_copy_goes_through_the_renderer(self):
        fn = _function(_DIALOG, "_on_copy_to_clipboard", "ShowShallowTagsDialog")
        names = _names(fn)
        self.assertIn("ChessLogMomentRenderer", names)
        self.assertIn("render", names)
        # The document wrappers get the rendered body, never snapshot groups.
        kwargs = {kw.arg for n in ast.walk(fn) if isinstance(n, ast.Call) for kw in n.keywords}
        self.assertTrue({"moments_html", "moments_plain"} <= kwargs)

    def test_no_other_route_builds_moment_text_in_the_callers(self):
        for rel, cls, name in self.CALLERS:
            with self.subTest(caller=f"{cls}.{name}"):
                self.assertEqual(_names(_function(rel, name, cls)) & _OTHER_ROUTES, set())

    def test_callers_never_interpolate_a_path_key(self):
        for rel, cls, name in self.CALLERS:
            fn = _function(rel, name, cls)
            for node in ast.walk(fn):
                if isinstance(node, ast.JoinedStr):
                    self.assertNotIn("path_key", {n for n in _names(node)}, f"{cls}.{name}")
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
                    self.assertNotIn("path_key", _names(node), f"{cls}.{name}")

    def test_old_pipe_row_format_is_gone(self):
        src = (_REPO / _VIEW).read_text(encoding="utf-8")
        self.assertNotIn("mo.path_key}  |", src)

    def test_renderer_keeps_no_state_and_saves_nothing(self):
        rel = "app/services/chess_log_moment_renderer.py"
        tree = ast.parse((_REPO / rel).read_text(encoding="utf-8"))
        called = {n.func.attr for n in ast.walk(tree)
                  if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertFalse({n for n in called if n.startswith(("save", "store", "replace_", "add_"))})
        # Only __init__ assigns to self; the controller and html service are references.
        for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name != "__init__"):
            for node in ast.walk(fn):
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        self.assertFalse(
                            isinstance(t, ast.Attribute) and getattr(t.value, "id", "") == "self",
                            f"{fn.name} assigns self.{getattr(t, 'attr', '?')}",
                        )


if __name__ == "__main__":
    unittest.main()
