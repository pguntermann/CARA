"""Player-name matching for statistics: exact names and regular expressions."""

from __future__ import annotations

import unittest

from app.models.database_model import GameData
from app.services.player_name_match import game_includes_player, player_is_white
from app.services.player_stats_service import PlayerStatsService


def _game(white: str, black: str, *, analyzed: bool = True) -> GameData:
    return GameData(1, white=white, black=black, analyzed=analyzed)


class _Database:
    def __init__(self, games: list[GameData]) -> None:
        self._games = games

    def get_all_games(self) -> list[GameData]:
        return list(self._games)


class TestPlayerNameMatch(unittest.TestCase):
    def test_exact_match_keeps_whitespace_and_rejects_substrings(self) -> None:
        self.assertTrue(
            game_includes_player("Carlsen, M", "X", "Carlsen, M", name_is_regex=False)
        )
        self.assertFalse(
            game_includes_player("Carlsen, M ", "X", "Carlsen, M", name_is_regex=False)
        )
        self.assertFalse(
            game_includes_player("Carlsen, Magnus", "X", "Carl", name_is_regex=False)
        )

    def test_regex_is_case_insensitive_and_unanchored(self) -> None:
        self.assertTrue(
            game_includes_player("X", "Müller, Hans", r"müller|mueller", name_is_regex=True)
        )
        self.assertTrue(
            player_is_white("Mueller, Hans", "X", r"müller|mueller", name_is_regex=True)
        )

    def test_both_sides_count_as_white(self) -> None:
        self.assertTrue(
            player_is_white("Carlsen", "Carlsen", "Carlsen", name_is_regex=True)
        )
        self.assertFalse(
            player_is_white("Other", "Carlsen", "Carlsen", name_is_regex=True)
        )

    def test_invalid_or_blank_pattern_matches_nothing(self) -> None:
        self.assertFalse(game_includes_player("A", "B", "[", name_is_regex=True))
        self.assertFalse(game_includes_player("A", "B", "   ", name_is_regex=True))
        self.assertFalse(game_includes_player("", "", "B", name_is_regex=False))
        self.assertFalse(game_includes_player(None, None, "B", name_is_regex=True))

    def test_get_player_games_uses_the_same_rules(self) -> None:
        games = [
            _game("Mueller, Hans", "Other"),
            _game("Other", "Müller, Hans", analyzed=False),
            _game("Carlsen, M ", "Other"),
            _game("Carl", "Other"),
        ]
        service = PlayerStatsService({})
        matched, total = service.get_player_games(
            r"müller|mueller", [_Database(games)], only_analyzed=False, name_is_regex=True
        )
        self.assertEqual(total, 2)
        self.assertEqual([game.white for game in matched], ["Mueller, Hans", "Other"])

        exact, exact_total = service.get_player_games(
            "Carlsen, M", [_Database(games)], only_analyzed=False, name_is_regex=False
        )
        self.assertEqual(exact_total, 0)
        self.assertEqual(exact, [])

        spaced, _ = service.get_player_games(
            "Carlsen, M ", [_Database(games)], only_analyzed=False, name_is_regex=False
        )
        self.assertEqual(len(spaced), 1)
