"""RegexEditorService: coloring, insertion, and live preview."""

from __future__ import annotations

import unittest

from app.config.config_loader import ConfigLoader
from app.services.regex_editor_service import (
    TOKEN_ALTERNATION,
    TOKEN_ANCHOR,
    TOKEN_ANY,
    TOKEN_ERROR,
    TOKEN_ESCAPE,
    TOKEN_GROUP,
    TOKEN_LITERAL,
    TOKEN_QUANTIFIER,
    TOKEN_RANGE,
    TOKEN_SET,
    RegexEditorService,
)


def _kinds(spans) -> list:
    return [kind for _, _, kind in spans]


class TestClassifyRegex(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RegexEditorService()

    def test_escape_quantifier_anchor_any_and_alternation(self) -> None:
        spans = self.service.classify(r"\d+^.$|")
        self.assertEqual(
            _kinds(spans),
            [
                TOKEN_ESCAPE,
                TOKEN_QUANTIFIER,
                TOKEN_ANCHOR,
                TOKEN_ANY,
                TOKEN_ANCHOR,
                TOKEN_ALTERNATION,
            ],
        )
        self.assertEqual(spans[-1][0:2], (6, 7))

    def test_group_flag_is_not_a_quantifier(self) -> None:
        spans = self.service.classify(r"(?:text)?")
        self.assertEqual(
            list(spans),
            [
                (0, 2, TOKEN_GROUP),
                (2, 7, TOKEN_LITERAL),
                (7, 8, TOKEN_GROUP),
                (8, 9, TOKEN_QUANTIFIER),
            ],
        )

    def test_character_class_keeps_a_leading_bracket(self) -> None:
        spans = self.service.classify("[]a]")
        self.assertEqual(_kinds(spans), [TOKEN_SET, TOKEN_LITERAL, TOKEN_SET])
        self.assertEqual(spans[0][0:2], (0, 1))
        self.assertEqual(spans[1][0:2], (1, 3))

    def test_character_class_marks_a_range_and_a_negation(self) -> None:
        self.assertEqual(
            _kinds(self.service.classify("[^a-z]")),
            [TOKEN_SET, TOKEN_RANGE, TOKEN_SET],
        )
        self.assertEqual(self.service.classify("[a-z]")[1][0:2], (1, 4))

    def test_quantifier_and_trailing_backslash(self) -> None:
        self.assertEqual(_kinds(self.service.classify("a{2,4}")), [TOKEN_LITERAL, TOKEN_QUANTIFIER])
        self.assertEqual(_kinds(self.service.classify("a{")), [TOKEN_LITERAL, TOKEN_ERROR])
        self.assertEqual(_kinds(self.service.classify("\\")), [TOKEN_ERROR])


class TestSavedRegexName(unittest.TestCase):
    def test_trims_the_name(self) -> None:
        service = RegexEditorService()
        self.assertEqual(service.normalize_name("  Titles  "), "Titles")
        self.assertEqual(service.normalize_name("   "), "")


class TestBlockGroups(unittest.TestCase):
    def test_groups_nest_and_flatten_in_menu_order(self) -> None:
        config = {
            "ui": {
                "dialogs": {
                    "regex_editor": {
                        "block_groups": [
                            {
                                "id": "characters",
                                "label": "Characters",
                                "blocks": [{"id": "digit", "label": "Digit", "insert": r"\d"}],
                            },
                            {
                                "id": "groups",
                                "label": "Groups",
                                "blocks": [{"id": "group", "label": "Group", "insert": "(text)", "select_text": "text"}],
                                "groups": [
                                    {
                                        "id": "lookaround",
                                        "label": "Lookaround",
                                        "blocks": [
                                            {"id": "lookahead", "label": "Lookahead", "insert": "(?=text)", "select_text": "text"}
                                        ],
                                    }
                                ],
                            },
                            {"id": "empty", "label": " ", "blocks": []},
                        ]
                    }
                }
            }
        }
        service = RegexEditorService()
        groups = service.block_groups(config)
        self.assertEqual([group.label for group in groups], ["Characters", "Groups"])
        self.assertEqual(groups[1].groups[0].blocks[0].id, "lookahead")
        self.assertEqual([block.id for block in service.blocks(config)], ["digit", "group", "lookahead"])


class TestInsertRegexBlock(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RegexEditorService()

    def test_selects_the_placeholder(self) -> None:
        text, start, end = self.service.insert_block("id", 2, 2, "(text)", "text")
        self.assertEqual(text, "id(text)")
        self.assertEqual(text[start:end], "text")

    def test_wraps_the_current_selection(self) -> None:
        text, start, end = self.service.insert_block("ab", 0, 2, "(text)", "text")
        self.assertEqual(text, "(ab)")
        self.assertEqual(text[start:end], "ab")


class TestExplainRegex(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RegexEditorService()

    def test_group_set_range_escape_and_quantifier(self) -> None:
        nodes = self.service.explain(r"([A-Z])\w+")
        group, word, plus = nodes
        self.assertEqual(group.token, "(")
        self.assertEqual(group.message_id, "capturing_group")
        self.assertEqual(group.closing_token, ")")
        charset = group.children[0]
        self.assertEqual(charset.token, "[")
        self.assertEqual(charset.message_id, "character_set")
        self.assertEqual(charset.closing_token, "]")
        self.assertEqual(charset.children[0].token, "A-Z")
        self.assertEqual(charset.children[0].message_id, "range")
        self.assertEqual(word.token, r"\w")
        self.assertEqual(word.message_id, "word")
        self.assertEqual(plus.token, "+")
        self.assertEqual(plus.message_id, "quantifier_one_or_more")

    def test_lazy_quantifier_and_alternation(self) -> None:
        nodes = self.service.explain(r"a+?|b")
        self.assertEqual([node.token for node in nodes], ["a", "+?", "|", "b"])
        self.assertEqual(dict(nodes[1].fields)["lazy"], "1")
        self.assertEqual(nodes[2].message_id, "alternation")


class TestPreviewRegex(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RegexEditorService()

    def test_case_flag_and_substitution(self) -> None:
        ignored = self.service.preview("a+", "X", "baA", case_sensitive=False, max_sample_chars=100, max_matches=10)
        self.assertTrue(ignored.valid)
        self.assertEqual(ignored.result, "bX")
        self.assertEqual(ignored.matches, ("aA",))
        self.assertEqual(ignored.match_count, 1)
        sensitive = self.service.preview("a+", "X", "baA", case_sensitive=True, max_sample_chars=100, max_matches=10)
        self.assertEqual(sensitive.result, "bXA")

    def test_highlights_a_group_inside_a_whole_string_match(self) -> None:
        preview = self.service.preview(
            r"^(.*?)\s*-\s*.*$",
            "",
            "Ok - World - Next",
            case_sensitive=True,
            max_sample_chars=100,
            max_matches=10,
        )
        self.assertEqual(preview.matches, ("Ok - World - Next",))
        self.assertEqual(
            tuple(preview.matches[0][start:end] for start, end in preview.spans),
            ("Ok",),
        )

    def test_empty_and_invalid_patterns(self) -> None:
        empty = self.service.preview("", "", "abc", case_sensitive=False, max_sample_chars=100, max_matches=10)
        self.assertTrue(empty.empty)
        self.assertFalse(empty.valid)
        invalid = self.service.preview("(", "", "abc", case_sensitive=False, max_sample_chars=100, max_matches=10)
        self.assertFalse(invalid.valid)
        self.assertTrue(invalid.error)

    def test_bad_replacement_group(self) -> None:
        preview = self.service.preview("a", r"\1", "a", case_sensitive=False, max_sample_chars=100, max_matches=10)
        self.assertFalse(preview.valid)
        self.assertTrue(preview.error)

    def test_caps_matches_and_sample(self) -> None:
        capped = self.service.preview("a", "", "aaa", case_sensitive=True, max_sample_chars=100, max_matches=2)
        self.assertTrue(capped.matches_capped)
        self.assertEqual(capped.match_count, 2)
        truncated = self.service.preview("a", "b", "aa", case_sensitive=True, max_sample_chars=1, max_matches=10)
        self.assertTrue(truncated.truncated)
        self.assertEqual(truncated.result, "b")


class TestRegexExamples(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RegexEditorService()

    def test_shipped_examples_match_their_samples(self) -> None:
        examples = self.service.examples(ConfigLoader().load())
        ids = [example.id for example in examples]
        self.assertIn("remove_titles", ids)
        self.assertIn("remove_federation_code", ids)
        self.assertIn("remove_time_control", ids)
        self.assertIn("games_across_years", ids)
        self.assertIn("tc_increment", ids)
        self.assertEqual(
            [example.group for example in examples if example.group][:1],
            ["Players"],
        )
        for example in examples:
            preview = self.service.preview(
                example.pattern,
                "",
                example.sample,
                case_sensitive=True,
                max_sample_chars=1000,
                max_matches=20,
            )
            self.assertTrue(preview.valid, example.id)
            self.assertTrue(preview.spans, example.id)

    def test_rejects_an_example_that_does_not_compile(self) -> None:
        config = {
            "ui": {
                "dialogs": {
                    "regex_editor": {
                        "examples": [
                            {"id": "bad", "label": "Bad", "pattern": "("},
                        ]
                    }
                }
            }
        }
        with self.assertRaisesRegex(ValueError, "bad"):
            self.service.examples(config)

    def test_rejects_select_text_that_is_not_in_the_pattern(self) -> None:
        config = {
            "ui": {
                "dialogs": {
                    "regex_editor": {
                        "examples": [
                            {
                                "id": "titles",
                                "label": "Titles",
                                "pattern": "GM",
                                "select_text": "IM",
                            },
                        ]
                    }
                }
            }
        }
        with self.assertRaisesRegex(ValueError, "select_text"):
            self.service.examples(config)


if __name__ == "__main__":
    unittest.main()
