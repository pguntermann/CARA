"""Golden-fixture tests for Chess Log prompt assembly.

Captures the EXACT text produced by build_prompt(get_tags_for_game=ChessLogStorageService.load_resolved_paths) and the classifier
prompt builder before any production strings move to config.json.  When
config.json gets the prompts in commit 6, these fixtures are the acceptance
gate: assembled prompts must be byte-identical before and after the move.

Bootstrap: run once with CHESS_LOG_FIXTURE_BOOTSTRAP=1 to write fixture
files under tests/fixtures/chess_log_prompts/.  On every subsequent run the
tests assert byte-identical output.

Assembly-method reference (for commit 6 brace-escaping work):
  - _SYSTEM_PROMPT       : plain string concatenation; no {placeholders}; no literal braces
  - _PRESET_GLOSSARIES   : plain string concatenation; no {placeholders}; no literal braces
  - _NARRATIVE_STEP      : plain string concatenation; no {placeholders}; no literal braces
  - _3X3_STRUCTURE_BLOCK : module-load "\n".join(f"{i+1}. {q}") + concatenation; no placeholders
  - _3X3_MOMENT_FRAMING  : plain string concatenation; no {placeholders}; no literal braces
  - _USER_PREAMBLE       : triple-quoted template used with .format(); placeholders
                           {glossary_section}, {category_counts_block},
                           {why_notes_block}, {game_notes_block}; NO literal braces
                           in the template text other than these four placeholders.
                           Stays on .format() after the config move — no escaping needed.
  - classifier prompt    : plain string concatenation + f"{notes_text}" at the end;
                           the body text has no {}/{} other than that final interpolation.
                           After config move: body stored in config, notes_text appended
                           in Python — no brace escaping in the config value.
"""

from __future__ import annotations

import json
import os
import pathlib
import unittest

from app.models.database_model import GameData
from app.services.chess_log_storage_service import ChessLogStorageService
from app.services.chess_log_narrative_service import build_prompt
from app.services.notes_storage_service import NotesStorageService
from app.utils.path_resolver import get_app_resource_path

FIXTURE_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "chess_log_prompts"
BOOTSTRAP = os.getenv("CHESS_LOG_FIXTURE_BOOTSTRAP") == "1"

# Load the real config once so golden tests can pass it to build_prompt().
_CONFIG_PATH = get_app_resource_path("app/config/config.json")
with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
    _CONFIG = json.load(_f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game(
    game_number: int,
    white: str = "Alice",
    black: str = "Bob",
    date: str = "2025.06.01",
    entries_per_path: dict | None = None,
    notes: str = "",
) -> GameData:
    pgn = (
        f'[Event "Test"]\n'
        f'[Site "?"]\n'
        f'[Date "{date}"]\n'
        f'[Round "?"]\n'
        f'[White "{white}"]\n'
        f'[Black "{black}"]\n'
        f'[Result "*"]\n'
        f'\n1. e4 ( 1. d4 ) ( 1. c4 ) e5 2. Nf3 *\n'
    )
    game = GameData(game_number=game_number, pgn=pgn, white=white, black=black, date=date)
    if entries_per_path:
        ChessLogStorageService.store_tags(game, entries_per_path)
    if notes:
        NotesStorageService.store_notes(game, notes)
    return game


def _clamp(cat: str, why: str = "") -> dict:
    return ChessLogStorageService.make_entry("CLAMP", cat, why)


def _cct(cat: str, why: str = "") -> dict:
    return ChessLogStorageService.make_entry("CCT", cat, why)


def _threex(key: str, why: str = "") -> dict:
    return ChessLogStorageService.make_entry("3x3", key, why)


def _build_classifier_prompt(notes: list) -> str:
    """Build the classifier prompt using the same assembly path as classify_notes()."""
    notes_text = "\n".join(f"{i}: {why}" for (i, _gn, _pk, _pr, why) in notes)
    classifier_body = _CONFIG["prompts"]["chess_log"]["classifier"]
    return classifier_body + notes_text


def _build_classifier_prompt_3x3(notes: list) -> str:
    """Build the 3x3 classifier prompt mirroring classify_notes_3x3()."""
    from app.utils.chess_log_prompts import THREE_BY_THREE_PROMPTS
    raw_body = _CONFIG["prompts"]["chess_log"]["classifier_3x3"]
    classifier_body = raw_body.format(
        why1_q=THREE_BY_THREE_PROMPTS["Why1"],
        why2_q=THREE_BY_THREE_PROMPTS["Why2"],
        why3_q=THREE_BY_THREE_PROMPTS["Why3"],
        why4_q=THREE_BY_THREE_PROMPTS["Why4"],
    )

    def _fmt_why(text: str) -> str:
        return text.strip() if text and text.strip() else "(blank)"

    note_blocks = []
    for (i, _gn, _pk, _pr, why1, why2, why3, why4) in notes:
        block = (
            f"{i}:\n"
            f"  Why1: {_fmt_why(why1)}\n"
            f"  Why2: {_fmt_why(why2)}\n"
            f"  Why3: {_fmt_why(why3)}\n"
            f"  Why4: {_fmt_why(why4)}"
        )
        note_blocks.append(block)
    return classifier_body + "\n".join(note_blocks)


def _assert_or_write(name: str, actual: str) -> None:
    path = FIXTURE_DIR / f"{name}.txt"
    if BOOTSTRAP:
        FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(actual, encoding="utf-8")
    else:
        if not path.exists():
            raise FileNotFoundError(
                f"Fixture {path} not found. "
                "Run: CHESS_LOG_FIXTURE_BOOTSTRAP=1 python -m unittest "
                "tests.services.test_chess_log_prompts_config_roundtrip"
            )
        expected = path.read_text(encoding="utf-8")
        if expected != actual:
            # Show a short diff context to help diagnose divergence.
            exp_lines = expected.splitlines()
            act_lines = actual.splitlines()
            for i, (e, a) in enumerate(zip(exp_lines, act_lines)):
                if e != a:
                    raise AssertionError(
                        f"Fixture mismatch at {name}.txt line {i + 1}:\n"
                        f"  expected: {e!r}\n"
                        f"  actual:   {a!r}"
                    )
            if len(exp_lines) != len(act_lines):
                raise AssertionError(
                    f"Fixture mismatch at {name}.txt: "
                    f"expected {len(exp_lines)} lines, got {len(act_lines)}"
                )


# ---------------------------------------------------------------------------
# Constant-level fixtures
# Capture each prompt constant individually so commit 6 can pinpoint
# exactly which string changed if a fixture fails.
# ---------------------------------------------------------------------------

class TestConstantFixtures(unittest.TestCase):
    """Verify config.json prompt values are byte-identical to the pre-move Python constants."""

    def _cl(self):
        return _CONFIG["prompts"]["chess_log"]

    def test_system_prompt(self):
        _assert_or_write("system_prompt", self._cl()["narrative_system"])

    def test_narrative_step(self):
        _assert_or_write("narrative_step", self._cl()["narrative_step"])

    def test_glossary_clamp(self):
        _assert_or_write("glossary_clamp", self._cl()["narrative_glossaries"]["CLAMP"])

    def test_glossary_cct(self):
        _assert_or_write("glossary_cct", self._cl()["narrative_glossaries"]["CCT"])

    def test_3x3_structure_block(self):
        _assert_or_write("3x3_structure_block", self._cl()["narrative_3x3_structure"])

    def test_3x3_moment_framing(self):
        _assert_or_write("3x3_moment_framing", self._cl()["narrative_3x3_moment_framing"])


# ---------------------------------------------------------------------------
# Full prompt — CLAMP only
# ---------------------------------------------------------------------------

class TestFullPromptClampOnly(unittest.TestCase):

    def _make_games(self):
        return [
            _make_game(1, date="2024.10.05", entries_per_path={
                "0": [_clamp("C", "I forgot to check if the queen could come in."),
                      _clamp("L", "My bishop on d3 was undefended.")],
            }),
            _make_game(2, date="2024.11.20", entries_per_path={
                "1": [_clamp("A", "There was a pin I completely missed.")],
                "2": [_clamp("C", "Missed a back-rank check threat.")],
            }),
            _make_game(3, date="2025.02.14", entries_per_path={
                "0": [_clamp("M", "I let my knight get trapped in the corner."),
                      _clamp("L", "Left my rook on an open file unguarded.")],
            }),
            _make_game(4, date="2025.04.08", entries_per_path={
                "0": [_clamp("P", "Didn't advance my passed pawn quickly enough."),
                      _clamp("C", "Missed opponent's check enabling fork.")],
            }),
        ]

    def test_full_prompt(self):
        games = self._make_games()
        prompt = build_prompt(games, player="Alice", color_filter="white", config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        _assert_or_write("full_prompt_clamp_only", prompt)


# ---------------------------------------------------------------------------
# Full prompt — CCT only
# ---------------------------------------------------------------------------

class TestFullPromptCctOnly(unittest.TestCase):

    def _make_games(self):
        return [
            _make_game(1, date="2024.10.05", entries_per_path={
                "0": [_cct("Checks", "Didn't see the back rank check."),
                      _cct("Captures", "My knight on e5 was hanging.")],
            }),
            _make_game(2, date="2024.11.20", entries_per_path={
                "1": [_cct("Threats", "Missed the fork threat on f7.")],
                "2": [_cct("Checks", "Allowed a discovered check.")],
            }),
            _make_game(3, date="2025.02.14", entries_per_path={
                "0": [_cct("Captures", "Left a free piece on b4."),
                      _cct("Threats", "Didn't see the queen-rook fork threat.")],
            }),
            _make_game(4, date="2025.04.08", entries_per_path={
                "0": [_cct("Checks", "Missed perpetual check resource."),
                      _cct("Captures", "Blundered a piece to a simple recapture.")],
            }),
        ]

    def test_full_prompt(self):
        games = self._make_games()
        prompt = build_prompt(games, player="Alice", color_filter="white", config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        _assert_or_write("full_prompt_cct_only", prompt)


# ---------------------------------------------------------------------------
# Full prompt — 3x3 with all four Whys populated
# ---------------------------------------------------------------------------

class TestFullPrompt3x3AllWhys(unittest.TestCase):

    def _make_games(self):
        return [
            _make_game(1, date="2024.10.05", entries_per_path={
                "0": [
                    _threex("Why1", "I wanted to open the d-file for my rook."),
                    _threex("Why2", "It left my king exposed on the g-file."),
                    _threex("Why3", "Bg5 pins the knight and maintains the pressure."),
                    _threex("Why4", "Check for open lines to my king before attacking."),
                ],
            }),
            _make_game(2, date="2024.12.03", entries_per_path={
                "0": [
                    _threex("Why1", "I was trying to win material with a pawn grab."),
                    _threex("Why2", "It gave up the initiative and let them castle."),
                    _threex("Why3", "Nd5 forks the queen and rook immediately."),
                    _threex("Why4", "Material gains that give up tempo are often not worth it."),
                ],
            }),
            _make_game(3, date="2025.02.14", entries_per_path={
                "0": [
                    _threex("Why1", "I thought I was defending my pawn structure."),
                    _threex("Why2", "The move blocked my own bishop's diagonal."),
                    _threex("Why3", "Rfe1 keeps pressure and doesn't close lines."),
                    _threex("Why4", "Don't block your own pieces when defending."),
                ],
            }),
            _make_game(4, date="2025.05.01", entries_per_path={
                "0": [
                    _threex("Why1", "I was rushing to push my passed pawn."),
                    _threex("Why2", "It dropped a piece to a zwischenzug."),
                    _threex("Why3", "Ka2 sidesteps the zwischenzug and wins cleanly."),
                    _threex("Why4", "Always look for opponent's in-between moves before advancing."),
                ],
            }),
        ]

    def test_full_prompt(self):
        games = self._make_games()
        prompt = build_prompt(games, player="Alice", color_filter="white", config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        _assert_or_write("full_prompt_3x3_all_whys", prompt)


# ---------------------------------------------------------------------------
# Full prompt — 3x3 with blank Why2 and Why3
# ---------------------------------------------------------------------------

class TestFullPrompt3x3BlankWhy2Why3(unittest.TestCase):

    def _make_games(self):
        return [
            _make_game(1, date="2024.10.05", entries_per_path={
                "0": [
                    _threex("Why1", "I wanted to trade off the powerful bishop."),
                    _threex("Why2", ""),          # blank Why2
                    _threex("Why3", ""),          # blank Why3
                    _threex("Why4", "Don't trade good pieces just to simplify."),
                ],
            }),
            _make_game(2, date="2025.01.10", entries_per_path={
                "0": [
                    _threex("Why1", "I played h3 to prevent Bg4."),
                    _threex("Why2", ""),          # blank
                    _threex("Why3", "Nf3 develops and prevents the pin."),
                    _threex("Why4", "Preventive pawn moves cost a tempo."),
                ],
            }),
        ]

    def test_full_prompt(self):
        games = self._make_games()
        prompt = build_prompt(games, player="Alice", color_filter="white", config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        _assert_or_write("full_prompt_3x3_blank_why2_why3", prompt)


# ---------------------------------------------------------------------------
# Full prompt — games with whole-game notes
# ---------------------------------------------------------------------------

class TestFullPromptWithGameNotes(unittest.TestCase):

    def _make_games(self):
        return [
            _make_game(1, date="2024.10.05",
                       entries_per_path={
                           "0": [_clamp("C", "Missed a check that forked king and rook.")],
                           "1": [_clamp("A", "Alignment on the d-file slipped by me.")],
                       },
                       notes="Played too fast in the middlegame. The position was complex but I spent only 3 minutes total."),
            _make_game(2, date="2025.01.20",
                       entries_per_path={
                           "0": [_cct("Threats", "Missed a queen fork threat."),
                                 _cct("Captures", "Free pawn grab I walked past.")],
                       },
                       notes="Good opening but collapsed in the endgame. Need to study king-and-pawn endgames."),
            _make_game(3, date="2025.04.05",
                       entries_per_path={
                           "0": [_clamp("L", "Left my rook on a semi-open file.")],
                       },
                       notes=""),  # empty notes — should not appear in prompt
        ]

    def test_full_prompt(self):
        games = self._make_games()
        prompt = build_prompt(games, player="Alice", color_filter="white", config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        _assert_or_write("full_prompt_with_game_notes", prompt)


# ---------------------------------------------------------------------------
# Full prompt — mixed presets (CLAMP + CCT + 3x3)
# ---------------------------------------------------------------------------

class TestFullPromptMixedPresets(unittest.TestCase):

    def _make_games(self):
        return [
            _make_game(1, date="2024.09.15", entries_per_path={
                "0": [_clamp("C", "Missed the back-rank mate threat."),
                      _clamp("L", "My rook on d1 was loose.")],
            }),
            _make_game(2, date="2024.11.30", entries_per_path={
                "0": [_cct("Checks", "Missed opponent check enabling fork."),
                      _cct("Threats", "Didn't spot the queen-rook battery.")],
            }),
            _make_game(3, date="2025.02.14", entries_per_path={
                "0": [
                    _threex("Why1", "I was trying to simplify into an endgame."),
                    _threex("Why2", "The trade gave them a strong passed pawn."),
                    _threex("Why3", "Keep the tension rather than trading prematurely."),
                    _threex("Why4", "Evaluate pawn structure consequences before trading."),
                ],
            }),
            _make_game(4, date="2025.05.10", entries_per_path={
                "0": [_clamp("A", "Fork via alignment that I completely overlooked."),
                      _cct("Captures", "Walked into a free piece loss.")],
            }),
        ]

    def test_full_prompt(self):
        games = self._make_games()
        prompt = build_prompt(games, player="Alice", color_filter="white", config=_CONFIG, get_tags_for_game=ChessLogStorageService.load_resolved_paths)
        _assert_or_write("full_prompt_mixed_presets", prompt)


# ---------------------------------------------------------------------------
# Classifier prompt — mixed CLAMP / CCT / 3x3 notes
# ---------------------------------------------------------------------------

class TestClassifierPromptMixed(unittest.TestCase):

    def _make_notes(self):
        # (idx, game_number, path_key, preset, why)
        return [
            (0, 1, "0",   "CLAMP", "I blundered my bishop by not checking captures."),
            (1, 1, "1",   "CLAMP", "Missed it."),
            (2, 2, "0",   "CCT",   "I went to push my pawn not seeing the queen fork on f7."),
            (3, 2, "1",   "CCT",   "There was a discovered attack on my queen that I missed."),
            (4, 3, "0",   "3x3",
             "[3x3] Why I played it: I wanted to activate my rook. | "
             "What was wrong: It walked into a pin on the e-file. | "
             "Why the better move is better: Re1 avoids the pin and keeps the rook active. | "
             "Lesson: Check for pins before rook moves."),
            (5, 4, "0",   "CLAMP", "I was focused on my queen not realising my knight was hanging."),
            (6, 4, "1",   "CCT",   "This is a passive move, letting them seize the open file."),
        ]

    def test_classifier_prompt(self):
        notes = self._make_notes()
        prompt = _build_classifier_prompt(notes)
        _assert_or_write("classifier_prompt_mixed", prompt)


# ---------------------------------------------------------------------------
# Classifier prompt — 3x3 notes (new classifier body)
# ---------------------------------------------------------------------------

class TestClassifierPrompt3x3(unittest.TestCase):

    def _make_notes(self):
        return [
            (0, 1, "path/0", "3x3",
             "I wanted to activate my rook by opening the d-file.",
             "It dropped a pawn to the bishop fork on b5.",
             "Nf6 maintains the knight and prevents the fork.",
             "Look for piece forks before advancing pawns."),
            (1, 2, "path/0", "3x3",
             "I thought it was a good move.",
             "My rook was undefended after the move.",
             "Rd1 defends the rook and keeps pressure.",
             "Be more careful."),
            (2, 3, "path/0", "3x3",
             "",
             "The move allowed a discovered attack on the queen.",
             "Ke2 sidesteps the discovered attack and keeps the king safe.",
             ""),
        ]

    def test_classifier_prompt_3x3(self):
        notes = self._make_notes()
        prompt = _build_classifier_prompt_3x3(notes)
        _assert_or_write("classifier_prompt_3x3", prompt)
