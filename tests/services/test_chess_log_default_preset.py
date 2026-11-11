"""Default Chess Log method: a fresh user_settings.json starts on 3x3; a saved choice is kept."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app.models.user_settings_model import UserSettingsModel
from app.services.user_settings_service import UserSettingsService
from app.utils.path_resolver import get_app_root


class TestDefaultPreset(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.mkdtemp()
        self._path = Path(self._tmp_dir) / "user_settings.json"

    def tearDown(self):
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_template_default_is_3x3(self):
        template = json.loads((get_app_root() / "user_settings.json.template").read_text(encoding="utf-8"))
        self.assertEqual(template["chess_log"]["active_preset"], "3x3")

    def test_fresh_settings_start_on_3x3(self):
        svc = UserSettingsService(settings_path=self._path)
        svc.load()
        svc.migrate()  # as at startup: fills missing sections from the template
        self.assertEqual(svc.get_chess_log().get("active_preset"), "3x3")

    def test_saved_clamp_is_not_overwritten(self):
        self._path.write_text(json.dumps({"chess_log": {"active_preset": "CLAMP"}}), encoding="utf-8")
        svc = UserSettingsService(settings_path=self._path)
        svc.load()
        svc.migrate()  # as at startup: fills missing sections from the template
        self.assertEqual(svc.get_chess_log().get("active_preset"), "CLAMP")
        svc.save()
        saved = json.loads(self._path.read_text(encoding="utf-8"))
        self.assertEqual(saved["chess_log"]["active_preset"], "CLAMP")

    def test_saved_cct_is_not_overwritten(self):
        self._path.write_text(json.dumps({"chess_log": {"active_preset": "CCT"}}), encoding="utf-8")
        svc = UserSettingsService(settings_path=self._path)
        svc.load()
        svc.migrate()  # as at startup: fills missing sections from the template
        self.assertEqual(svc.get_chess_log().get("active_preset"), "CCT")

    def test_model_fallback_for_malformed_section_is_3x3(self):
        model = UserSettingsModel()
        model._settings["chess_log"] = "not a dict"
        self.assertEqual(model.get_chess_log(), {"active_preset": "3x3"})


if __name__ == "__main__":
    unittest.main()
