"""has_chess_log_tags from a CARAChessLog header edit uses the one definition (C4)."""

import unittest

from app.services.chess_log_storage_service import ChessLogStorageService
from app.utils.game_data_header_sync import game_data_updates_for_header_tag
from app.utils.pgn_tag_compression import compress_and_encode_from_str


def _encoded(paths):
    import json

    return compress_and_encode_from_str(json.dumps({"_v": 1, "paths": paths}))


class TestHeaderSyncChessLogFlag(unittest.TestCase):
    def test_tag_with_no_moments_leaves_flag_false(self):
        for paths in ({}, {"AAAA": []}):
            u = game_data_updates_for_header_tag("CARAChessLog", _encoded(paths))
            self.assertIs(u["has_chess_log_tags"], False)

    def test_undecodable_tag_leaves_flag_false(self):
        u = game_data_updates_for_header_tag("CARAChessLog", "not-a-payload")
        self.assertIs(u["has_chess_log_tags"], False)

    def test_tag_with_a_moment_sets_flag_true(self):
        entry = ChessLogStorageService.make_entry("CLAMP", "C", "x")
        u = game_data_updates_for_header_tag("CARAChessLog", _encoded({"AAAA": [entry]}))
        self.assertIs(u["has_chess_log_tags"], True)

    def test_removed_sets_flag_false(self):
        u = game_data_updates_for_header_tag("CARAChessLog", removed=True)
        self.assertIs(u["has_chess_log_tags"], False)


if __name__ == "__main__":
    unittest.main()
