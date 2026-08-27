"""Tests for app.utils.macos_startup — the UF_HIDDEN platform-plugin guard.

These tests cover the safety contracts: the helper must never raise,
never block startup, and correctly clear the UF_HIDDEN bit when present.
Platform-specific paths are mocked so the tests run on all OSes.
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from app.utils.macos_startup import (
    _UF_HIDDEN,
    _clear_hidden_flag,
    _clear_hidden_recursive,
    clear_platform_plugin_hidden_flags,
)


class TestClearHiddenFlag(unittest.TestCase):
    """Unit tests for the low-level _clear_hidden_flag helper."""

    def test_clears_uf_hidden_when_set(self):
        calls = []

        def fake_lstat(path):
            st = MagicMock()
            st.st_flags = _UF_HIDDEN | 0x0040  # hidden + tracked
            return st

        def fake_chflags(path, flags):
            calls.append((path, flags))

        with patch("app.utils.macos_startup.os.lstat", fake_lstat), \
             patch("app.utils.macos_startup.os.chflags", fake_chflags):
            _clear_hidden_flag("/fake/libqcocoa.dylib")

        self.assertEqual(len(calls), 1)
        _, new_flags = calls[0]
        self.assertFalse(new_flags & _UF_HIDDEN, "UF_HIDDEN should have been cleared")
        self.assertTrue(new_flags & 0x0040, "Other flags should be preserved")

    def test_noop_when_flag_not_set(self):
        calls = []

        def fake_lstat(path):
            st = MagicMock()
            st.st_flags = 0x0040  # tracked, no hidden
            return st

        with patch("app.utils.macos_startup.os.lstat", fake_lstat), \
             patch("app.utils.macos_startup.os.chflags", lambda p, f: calls.append((p, f))):
            _clear_hidden_flag("/fake/libqcocoa.dylib")

        self.assertEqual(calls, [], "chflags should not be called if flag is not set")

    def test_silently_ignores_oserror_on_lstat(self):
        with patch("app.utils.macos_startup.os.lstat", side_effect=OSError("no permission")):
            _clear_hidden_flag("/nonexistent/path")  # must not raise

    def test_silently_ignores_oserror_on_chflags(self):
        def fake_lstat(path):
            st = MagicMock()
            st.st_flags = _UF_HIDDEN
            return st

        with patch("app.utils.macos_startup.os.lstat", fake_lstat), \
             patch("app.utils.macos_startup.os.chflags", side_effect=OSError("read-only")):
            _clear_hidden_flag("/fake/path")  # must not raise

    def test_handles_stat_without_st_flags(self):
        """Non-macOS stat objects lack st_flags — should be a no-op."""
        def fake_lstat(path):
            st = MagicMock(spec=[])  # no attributes at all
            return st

        with patch("app.utils.macos_startup.os.lstat", fake_lstat):
            _clear_hidden_flag("/fake/path")  # must not raise


class TestClearHiddenRecursive(unittest.TestCase):
    def test_clears_directory_and_children(self):
        cleared = []

        def fake_lstat(path):
            st = MagicMock()
            st.st_flags = _UF_HIDDEN
            return st

        with patch("app.utils.macos_startup.os.lstat", fake_lstat), \
             patch("app.utils.macos_startup.os.chflags", lambda p, f: cleared.append(p)), \
             patch("app.utils.macos_startup.os.path.isdir", return_value=True), \
             patch("app.utils.macos_startup.os.listdir", return_value=["libqcocoa.dylib", "libqminimal.dylib"]):
            _clear_hidden_recursive("/fake/platforms")

        # Should clear the dir itself + both children
        self.assertEqual(len(cleared), 3)

    def test_silently_ignores_listdir_error(self):
        def fake_lstat(path):
            st = MagicMock()
            st.st_flags = 0  # no hidden
            return st

        with patch("app.utils.macos_startup.os.lstat", fake_lstat), \
             patch("app.utils.macos_startup.os.path.isdir", return_value=True), \
             patch("app.utils.macos_startup.os.listdir", side_effect=OSError("permission denied")):
            _clear_hidden_recursive("/fake/platforms")  # must not raise


class TestClearPlatformPluginHiddenFlags(unittest.TestCase):
    """Tests for the public entry-point."""

    def test_noop_on_non_macos(self):
        """On non-macOS platforms the function must return immediately."""
        with patch("app.utils.macos_startup.sys.platform", "linux"):
            clear_platform_plugin_hidden_flags()  # must not raise or do anything

    def test_noop_on_windows(self):
        with patch("app.utils.macos_startup.sys.platform", "win32"):
            clear_platform_plugin_hidden_flags()

    def test_handles_missing_pyqt6(self):
        """If PyQt6 is not importable the function must not raise."""
        with patch("app.utils.macos_startup.sys.platform", "darwin"), \
             patch("builtins.__import__", side_effect=ImportError("no PyQt6")):
            clear_platform_plugin_hidden_flags()  # must not raise

    def test_handles_nonexistent_plugins_dir(self):
        """If the plugins directory doesn't exist, must not raise."""
        fake_pyqt6 = MagicMock()
        fake_pyqt6.__file__ = "/nonexistent/PyQt6/__init__.py"

        with patch("app.utils.macos_startup.sys.platform", "darwin"), \
             patch.dict("sys.modules", {"PyQt6": fake_pyqt6}):
            clear_platform_plugin_hidden_flags()  # must not raise

    def test_macos_clears_flags_in_plugins_dir(self):
        """On darwin: locates the plugins dir and calls _clear_hidden_recursive."""
        fake_pyqt6 = MagicMock()
        fake_pyqt6.__file__ = "/fake/site-packages/PyQt6/__init__.py"
        expected_dir = "/fake/site-packages/PyQt6/Qt6/plugins/platforms"

        cleared = []
        with patch("app.utils.macos_startup.sys.platform", "darwin"), \
             patch.dict("sys.modules", {"PyQt6": fake_pyqt6}), \
             patch("app.utils.macos_startup._clear_hidden_recursive",
                   side_effect=lambda p: cleared.append(p)) as mock_clear:
            clear_platform_plugin_hidden_flags()

        self.assertEqual(cleared, [expected_dir])

    def test_exception_inside_does_not_propagate(self):
        """Any unexpected exception must be swallowed (startup must never be blocked)."""
        with patch("app.utils.macos_startup.sys.platform", "darwin"), \
             patch("app.utils.macos_startup._clear_hidden_recursive",
                   side_effect=RuntimeError("unexpected")):
            # Even if _clear_hidden_recursive blows up, no exception escapes
            clear_platform_plugin_hidden_flags()  # must not raise


if __name__ == "__main__":
    unittest.main()
