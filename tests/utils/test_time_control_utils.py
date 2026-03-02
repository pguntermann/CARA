"""Unit tests for time control parsing and TC type mapping."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest
from app.utils import time_control_utils


class TestParseBaseSeconds(unittest.TestCase):
    """Tests for _parse_base_seconds (via get_base_seconds)."""

    def test_empty_or_none_returns_none(self):
        self.assertIsNone(time_control_utils.get_base_seconds(""))
        self.assertIsNone(time_control_utils.get_base_seconds("   "))
        self.assertIsNone(time_control_utils.get_base_seconds(None))

    def test_question_or_dash_returns_none(self):
        self.assertIsNone(time_control_utils.get_base_seconds("?"))
        self.assertIsNone(time_control_utils.get_base_seconds("-"))

    def test_integer_only_returns_seconds(self):
        self.assertEqual(time_control_utils.get_base_seconds("60"), 60)
        self.assertEqual(time_control_utils.get_base_seconds("300"), 300)
        self.assertEqual(time_control_utils.get_base_seconds("900"), 900)
        self.assertEqual(time_control_utils.get_base_seconds("  180  "), 180)

    def test_plus_increment_returns_base_only(self):
        self.assertEqual(time_control_utils.get_base_seconds("300+3"), 300)
        self.assertEqual(time_control_utils.get_base_seconds("180+2"), 180)
        self.assertEqual(time_control_utils.get_base_seconds("600+5"), 600)
        self.assertEqual(time_control_utils.get_base_seconds("60+1"), 60)

    def test_moves_slash_time_returns_period_seconds(self):
        self.assertEqual(time_control_utils.get_base_seconds("40/9000"), 9000)
        self.assertEqual(time_control_utils.get_base_seconds("40/7200+60"), 7200)
        self.assertEqual(time_control_utils.get_base_seconds("40/5400+30"), 5400)

    def test_predefined_string_returns_none(self):
        self.assertIsNone(time_control_utils.get_base_seconds("Blitz"))
        self.assertIsNone(time_control_utils.get_base_seconds("Rapid"))

    def test_invalid_formats_return_none(self):
        self.assertIsNone(time_control_utils.get_base_seconds("abc"))
        # "1/0" is parsed as moves=1, seconds=0 and returns 0; use 0 moves to get None
        self.assertIsNone(time_control_utils.get_base_seconds("0/60"))


class TestGetTcType(unittest.TestCase):
    """Tests for get_tc_type mapping."""

    def test_empty_or_unknown_returns_empty(self):
        self.assertEqual(time_control_utils.get_tc_type(""), "")
        self.assertEqual(time_control_utils.get_tc_type("?"), "")
        self.assertEqual(time_control_utils.get_tc_type("-"), "")

    def test_default_thresholds_bullet_blitz_rapid_classical(self):
        self.assertEqual(time_control_utils.get_tc_type("60"), "Bullet")
        self.assertEqual(time_control_utils.get_tc_type("180"), "Bullet")
        self.assertEqual(time_control_utils.get_tc_type("300"), "Blitz")
        self.assertEqual(time_control_utils.get_tc_type("600"), "Blitz")
        self.assertEqual(time_control_utils.get_tc_type("900"), "Rapid")
        self.assertEqual(time_control_utils.get_tc_type("3600"), "Rapid")
        self.assertEqual(time_control_utils.get_tc_type("7200"), "Classical")
        self.assertEqual(time_control_utils.get_tc_type("40/7200+60"), "Classical")

    def test_string_map_from_config(self):
        cfg = {"string_map": {"Blitz": "Blitz", "Custom": "Custom TC"}}
        self.assertEqual(time_control_utils.get_tc_type("Blitz", cfg), "Blitz")
        self.assertEqual(time_control_utils.get_tc_type("Custom", cfg), "Custom TC")

    def test_unparseable_non_empty_returns_unknown(self):
        self.assertEqual(time_control_utils.get_tc_type("Blitz"), "Unknown")
        self.assertEqual(time_control_utils.get_tc_type("SomeLabel"), "Unknown")

    def test_custom_thresholds_from_config(self):
        cfg = {
            "bullet_max_seconds": 120,
            "blitz_max_seconds": 300,
            "rapid_max_seconds": 1800,
        }
        self.assertEqual(time_control_utils.get_tc_type("60", cfg), "Bullet")
        self.assertEqual(time_control_utils.get_tc_type("120", cfg), "Bullet")
        self.assertEqual(time_control_utils.get_tc_type("180", cfg), "Blitz")
        self.assertEqual(time_control_utils.get_tc_type("300", cfg), "Blitz")
        self.assertEqual(time_control_utils.get_tc_type("600", cfg), "Rapid")
        self.assertEqual(time_control_utils.get_tc_type("1800", cfg), "Rapid")
        self.assertEqual(time_control_utils.get_tc_type("3600", cfg), "Classical")


if __name__ == "__main__":
    unittest.main()
