"""Unit tests for ColumnProfile.get_column_order.

Covers the fix that appends newly added canonical columns (e.g. col_log)
to saved profiles that pre-date the new column, so they surface
automatically instead of being hidden.
"""

from __future__ import annotations

import unittest

from app.models.column_profile_model import ColumnProfile


class TestColumnProfileGetColumnOrder(unittest.TestCase):

    def _make_profile(self, column_order=None):
        return ColumnProfile(name="Test", columns={}, column_order=column_order)

    def test_returns_default_order_when_column_order_is_none(self):
        profile = self._make_profile(column_order=None)
        default = ["col_a", "col_b", "col_c"]
        result = profile.get_column_order(default)
        self.assertEqual(result, default)

    def test_returns_copy_not_same_object_when_column_order_is_none(self):
        profile = self._make_profile(column_order=None)
        default = ["col_a", "col_b"]
        result = profile.get_column_order(default)
        result.append("col_extra")
        self.assertNotIn("col_extra", default)

    def test_saved_order_preserved_when_all_canonical_columns_present(self):
        saved = ["col_c", "col_a", "col_b"]
        profile = self._make_profile(column_order=saved)
        default = ["col_a", "col_b", "col_c"]
        result = profile.get_column_order(default)
        self.assertEqual(result, ["col_c", "col_a", "col_b"])

    def test_missing_column_appended_at_end(self):
        """A profile saved before col_log existed gets col_log appended."""
        saved = ["col_notes", "col_source_db", "col_tags"]
        profile = self._make_profile(column_order=saved)
        default = ["col_notes", "col_log", "col_source_db", "col_tags"]
        result = profile.get_column_order(default)
        self.assertIn("col_log", result)
        # col_log must appear after all saved entries
        self.assertEqual(result.index("col_log"), 3)

    def test_existing_entries_stay_in_original_order(self):
        saved = ["col_z", "col_a", "col_m"]
        profile = self._make_profile(column_order=saved)
        default = ["col_a", "col_log", "col_m", "col_z"]
        result = profile.get_column_order(default)
        saved_part = [c for c in result if c in set(saved)]
        self.assertEqual(saved_part, ["col_z", "col_a", "col_m"])

    def test_multiple_missing_columns_appended_in_default_order(self):
        saved = ["col_b"]
        profile = self._make_profile(column_order=saved)
        default = ["col_a", "col_b", "col_c", "col_d"]
        result = profile.get_column_order(default)
        self.assertEqual(result, ["col_b", "col_a", "col_c", "col_d"])

    def test_idempotent_when_all_columns_present(self):
        """Calling get_column_order twice with the same default gives same result."""
        saved = ["col_b", "col_a", "col_log"]
        profile = self._make_profile(column_order=saved)
        default = ["col_a", "col_b", "col_log"]
        first = profile.get_column_order(default)
        second = profile.get_column_order(default)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
