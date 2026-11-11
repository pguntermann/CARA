"""Per-test isolation of the AI settings the Chess Log Charts controller reads live.

ChessLogChartsController reads AI settings from ``UserSettingsService.get_instance()``
at the moment it needs them. Tests must therefore never reach the real
``user_settings.json``: ``isolate_module(globals())`` (called from ``setUpModule``)
gives every TestCase in the module a fresh service on a temporary path.
"""

from __future__ import annotations

import functools
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch

from app.services.user_settings_service import UserSettingsService

_current: Optional[UserSettingsService] = None


def current_service() -> UserSettingsService:
    assert _current is not None, "isolate_module() was not applied to this test module"
    return _current


def apply_settings(settings: Dict[str, Any]) -> None:
    """Replace the isolated service's AI sections with those in *settings*."""
    model = current_service().get_model()
    model.set_ai_models(settings.get("ai_models", {}))
    model.set_ai_summary(settings.get("ai_summary", {}))


def set_user_settings(ctrl: Any, settings: Dict[str, Any]) -> None:
    """Write *settings* through the service, then notify the controller as main_window does."""
    apply_settings(settings)
    ctrl.set_user_settings(settings)


def _wrap_setup(original):
    @functools.wraps(original)
    def setUp(self):
        global _current
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        _current = UserSettingsService(Path(tmp.name) / "user_settings.json")
        _current.get_model().set_ai_models({})
        _current.get_model().set_ai_summary({})
        p = patch.object(UserSettingsService, "get_instance", classmethod(lambda cls, *a, **k: _current))
        p.start()
        self.addCleanup(p.stop)
        original(self)
    return setUp


def isolate_module(namespace: Dict[str, Any]) -> None:
    """Wrap setUp of every TestCase defined in *namespace* with the isolation above."""
    for obj in list(namespace.values()):
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase) and obj.__module__ == namespace["__name__"]:
            obj.setUp = _wrap_setup(obj.setUp)
