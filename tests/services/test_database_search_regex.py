"""Regex operator on in-memory database search."""

from __future__ import annotations

import unittest

from app.models.database_model import GameData
from app.models.search_criteria import SearchCriteria, SearchField, SearchOperator
from app.services.database_search_service import DatabaseSearchService


def _game() -> GameData:
    return GameData(
        1,
        white="Karpov",
        black="Kasparov",
        date="1999.01.15",
        event="Tata Steel",
        site="Wijk aan Zee",
        eco="B22",
        time_control="300+5",
        pgn=(
            '[Event "Tata Steel"]\n'
            '[White "Karpov"]\n'
            '[Black "Kasparov"]\n'
            '[Opening "Sicilian Defense"]\n'
            '[Result "*"]\n\n'
            '*\n'
        ),
    )


def _matches(game: GameData, criterion: SearchCriteria) -> bool:
    patterns = DatabaseSearchService._compile_regex_patterns([criterion])
    return DatabaseSearchService._evaluate_criterion(
        game,
        criterion,
        {"regex_patterns": patterns},
    )


class TestDatabaseSearchRegex(unittest.TestCase):
    def test_pattern_error_rejects_blank_and_invalid(self) -> None:
        self.assertEqual(DatabaseSearchService.regex_pattern_error(""), "Enter a regular expression.")
        self.assertEqual(DatabaseSearchService.regex_pattern_error("   "), "Enter a regular expression.")
        self.assertEqual(DatabaseSearchService.regex_pattern_error("("), "That regular expression is not valid.")
        self.assertEqual(DatabaseSearchService.regex_pattern_error(r"\d+"), "")

    def test_search_is_unanchored_and_case_insensitive(self) -> None:
        game = _game()
        self.assertTrue(_matches(game, SearchCriteria(SearchField.WHITE, SearchOperator.MATCHES_REGEX, "karpov")))
        self.assertTrue(_matches(game, SearchCriteria(SearchField.WHITE, SearchOperator.MATCHES_REGEX, "pov")))
        self.assertFalse(_matches(game, SearchCriteria(SearchField.WHITE, SearchOperator.MATCHES_REGEX, "^pov")))
        self.assertTrue(_matches(game, SearchCriteria(SearchField.EVENT, SearchOperator.MATCHES_REGEX, "steel")))
        self.assertTrue(_matches(game, SearchCriteria(SearchField.DATE, SearchOperator.MATCHES_REGEX, r"1999\.01")))
        self.assertTrue(_matches(game, SearchCriteria(SearchField.ECO, SearchOperator.MATCHES_REGEX, "b22")))

    def test_time_control_uses_the_raw_tag(self) -> None:
        game = _game()
        self.assertTrue(_matches(game, SearchCriteria(SearchField.TIMECONTROL, SearchOperator.MATCHES_REGEX, r"\d+\+\d+")))
        self.assertFalse(_matches(game, SearchCriteria(SearchField.TIMECONTROL, SearchOperator.MATCHES_REGEX, r"^300$")))

    def test_custom_tag_and_invalid_pattern(self) -> None:
        game = _game()
        self.assertTrue(
            _matches(
                game,
                SearchCriteria(
                    SearchField.CUSTOM_TAG,
                    SearchOperator.MATCHES_REGEX,
                    "sicilian",
                    custom_tag_name="Opening",
                ),
            )
        )
        self.assertFalse(
            _matches(
                game,
                SearchCriteria(SearchField.WHITE, SearchOperator.MATCHES_REGEX, "("),
            )
        )
        self.assertFalse(
            _matches(
                game,
                SearchCriteria(SearchField.WHITE, SearchOperator.MATCHES_REGEX, "   "),
            )
        )

    def test_formula_names_the_operator(self) -> None:
        formula = DatabaseSearchService._format_search_formula(
            [SearchCriteria(SearchField.WHITE, SearchOperator.MATCHES_REGEX, "karpov")]
        )
        self.assertIn("matches regex", formula)
        self.assertIn("karpov", formula)


if __name__ == "__main__":
    unittest.main()
