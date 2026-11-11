"""Smoke test: every module under app/ must import without ImportError.

Catches cross-module import aliases broken by refactors (e.g. functions moved
to a shared module but re-exported names forgotten).
"""

from __future__ import annotations

import importlib
import os
import pkgutil
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
            cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        return result.returncode == 0 and b"ok" in result.stdout
    except Exception:
        return False


_QT_AVAILABLE = _qt_starts_cleanly()

if _QT_AVAILABLE:
    from PyQt6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication(sys.argv)


def _collect_app_modules() -> tuple[list[str], list[str]]:
    """Return (importable_modules, skipped_modules) under app/."""
    import app

    modules: list[str] = []
    skipped: list[str] = []
    for _importer, modname, _ispkg in pkgutil.walk_packages(
        path=app.__path__,
        prefix=app.__name__ + ".",
        onerror=lambda _name: None,
    ):
        if modname.endswith(".__main__"):
            skipped.append(modname)
            continue
        modules.append(modname)
    return modules, skipped


@unittest.skipUnless(_QT_AVAILABLE, "Qt not available in this environment")
class TestImportSmoke(unittest.TestCase):
    """Every module under app/ must be importable without ImportError."""

    def test_all_app_modules_import(self) -> None:
        modules, skipped = _collect_app_modules()
        if skipped:
            print(
                f"\n[smoke] Skipped {len(skipped)} __main__ module(s): {skipped}",
                file=sys.stderr,
            )
        failures: list[str] = []
        for modname in modules:
            try:
                importlib.import_module(modname)
            except ImportError as exc:
                failures.append(f"{modname}: {exc}")
        if failures:
            self.fail(
                f"{len(failures)} module(s) failed to import:\n"
                + "\n".join(f"  {f}" for f in failures)
            )
