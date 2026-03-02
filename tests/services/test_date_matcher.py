"""Unit tests for DateMatcher (PGN date parsing and comparison)."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest
from app.services.date_matcher import DateMatcher


class TestDateMatcherParseDate(unittest.TestCase):
    """Tests for DateMatcher.parse_date."""

    def test_full_date(self):
        self.assertEqual(DateMatcher.parse_date("2025.11.09"), (2025, 11, 9))
        self.assertEqual(DateMatcher.parse_date("2024.01.01"), (2024, 1, 1))

    def test_partial_dates(self):
        self.assertEqual(DateMatcher.parse_date("2025.11.??"), (2025, 11, None))
        self.assertEqual(DateMatcher.parse_date("2025.??.??"), (2025, None, None))

    def test_wildcard_components(self):
        self.assertEqual(DateMatcher.parse_date("2025.?.??"), (2025, None, None))
        self.assertEqual(DateMatcher.parse_date("????.??.??"), (None, None, None))

    def test_whitespace_stripped(self):
        self.assertEqual(DateMatcher.parse_date("  2025.11.09  "), (2025, 11, 9))

    def test_invalid_returns_none(self):
        self.assertIsNone(DateMatcher.parse_date(""))
        self.assertIsNone(DateMatcher.parse_date(None))
        self.assertIsNone(DateMatcher.parse_date("2025-11-09"))  # wrong delimiter
        self.assertIsNone(DateMatcher.parse_date("2025.11"))  # only 2 parts
        self.assertIsNone(DateMatcher.parse_date("2025.11.09.extra"))  # 4 parts
        self.assertIsNone(DateMatcher.parse_date("not-a-date"))


class TestDateMatcherDateContains(unittest.TestCase):
    """Tests for DateMatcher.date_contains."""

    def test_substring_match(self):
        self.assertTrue(DateMatcher.date_contains("2025.11.09", "2025"))
        self.assertTrue(DateMatcher.date_contains("2025.11.09", "11"))
        self.assertTrue(DateMatcher.date_contains("2025.11.09", "09"))

    def test_case_insensitive(self):
        self.assertTrue(DateMatcher.date_contains("2025.11.09", "2025"))

    def test_empty_false(self):
        self.assertFalse(DateMatcher.date_contains("", "2025"))
        self.assertFalse(DateMatcher.date_contains("2025.11.09", ""))


class TestDateMatcherDateEquals(unittest.TestCase):
    """Tests for DateMatcher.date_equals (wildcard matching)."""

    def test_exact_match(self):
        self.assertTrue(DateMatcher.date_equals("2025.11.09", "2025.11.09"))

    def test_pattern_wildcards_match_any(self):
        self.assertTrue(DateMatcher.date_equals("2025.11.09", "2025.??.??"))
        self.assertTrue(DateMatcher.date_equals("2025.11.09", "2025.11.??"))
        self.assertTrue(DateMatcher.date_equals("2025.03.15", "2025.??.??"))

    def test_mismatch(self):
        self.assertFalse(DateMatcher.date_equals("2025.11.09", "2024.11.09"))
        self.assertFalse(DateMatcher.date_equals("2025.11.09", "2025.10.09"))
        self.assertFalse(DateMatcher.date_equals("2025.11.09", "2025.11.08"))

    def test_invalid_returns_false(self):
        self.assertFalse(DateMatcher.date_equals("", "2025.11.09"))
        self.assertFalse(DateMatcher.date_equals("2025.11.09", "invalid"))


class TestDateMatcherDateBefore(unittest.TestCase):
    """Tests for DateMatcher.date_before."""

    def test_before_year(self):
        self.assertTrue(DateMatcher.date_before("2024.06.15", "2025.01.01"))

    def test_before_month_same_year(self):
        self.assertTrue(DateMatcher.date_before("2025.06.15", "2025.12.01"))

    def test_before_day_same_month(self):
        self.assertTrue(DateMatcher.date_before("2025.06.10", "2025.06.20"))

    def test_equal_not_before(self):
        self.assertFalse(DateMatcher.date_before("2025.06.15", "2025.06.15"))

    def test_after_not_before(self):
        self.assertFalse(DateMatcher.date_before("2025.12.01", "2025.06.15"))

    def test_partial_unknown_returns_false(self):
        self.assertFalse(DateMatcher.date_before("2025.??.??", "2025.06.15"))
        self.assertFalse(DateMatcher.date_before("2025.06.15", "2025.??.??"))


class TestDateMatcherDateAfter(unittest.TestCase):
    """Tests for DateMatcher.date_after."""

    def test_after_year(self):
        self.assertTrue(DateMatcher.date_after("2026.01.01", "2025.12.31"))

    def test_after_month_same_year(self):
        self.assertTrue(DateMatcher.date_after("2025.12.01", "2025.06.15"))

    def test_after_day_same_month(self):
        self.assertTrue(DateMatcher.date_after("2025.06.25", "2025.06.10"))

    def test_equal_not_after(self):
        self.assertFalse(DateMatcher.date_after("2025.06.15", "2025.06.15"))

    def test_before_not_after(self):
        self.assertFalse(DateMatcher.date_after("2025.01.01", "2025.06.15"))

    def test_partial_unknown_returns_false(self):
        self.assertFalse(DateMatcher.date_after("2025.??.??", "2025.06.15"))


if __name__ == "__main__":
    unittest.main()
