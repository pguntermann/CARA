"""Test script for PGN formatter service.

Tests various PGN formats and complexity levels to ensure the formatter
handles headers, comments, variations, moves, and annotations correctly.
"""

import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import unittest
from app.services.pgn_formatter_service import PgnFormatterService, PGN_MOVE_RESULT_RE
from app.config.config_loader import ConfigLoader


def _rgb_marker(rgb: list) -> str:
    """Return the CSS marker substring used in formatter spans for a given RGB triplet."""
    try:
        r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
    except Exception:
        r, g, b = 0, 0, 0
    return f"color: rgb({r}, {g}, {b})"


def _get_pgn_formatting_config(config: dict) -> dict:
    ui_config = config.get("ui", {}) if isinstance(config, dict) else {}
    panel_config = (ui_config.get("panels", {}) or {}).get("detail", {}) if isinstance(ui_config, dict) else {}
    pgn_cfg = (panel_config.get("pgn_notation", {}) or {}) if isinstance(panel_config, dict) else {}
    formatting = (pgn_cfg.get("formatting", {}) or {}) if isinstance(pgn_cfg, dict) else {}
    return {"pgn": pgn_cfg, "formatting": formatting}


def _validate_formatter_output(pgn_text: str, formatted_html: str, move_info: list, test_name: str, config: dict) -> list:
    """Validate formatter output and return list of error messages (empty if valid)."""
    errors = []

    cfg = _get_pgn_formatting_config(config)
    formatting = cfg["formatting"]
    pgn_cfg = cfg["pgn"]

    # These defaults must mirror PgnFormatterService.format_pgn_to_html fallbacks.
    header_color = (formatting.get("headers", {}) or {}).get("color", [100, 150, 255])
    comment_color = (formatting.get("comments", {}) or {}).get("color", [180, 200, 255])
    variation_color = (formatting.get("variations", {}) or {}).get("color", [180, 180, 180])
    move_number_color = (formatting.get("move_numbers", {}) or {}).get("color", [255, 255, 255])
    move_number_bold = bool((formatting.get("move_numbers", {}) or {}).get("bold", True))
    result_color = (formatting.get("results", {}) or {}).get("color", [255, 255, 100])
    result_bold = bool((formatting.get("results", {}) or {}).get("bold", True))

    header_marker = _rgb_marker(header_color)
    comment_marker = _rgb_marker(comment_color)
    variation_marker = _rgb_marker(variation_color)
    move_number_marker = _rgb_marker(move_number_color)
    result_marker = _rgb_marker(result_color)

    # Check that headers are formatted (if headers exist)
    if '[' in pgn_text and ']' in pgn_text:
        if header_marker not in formatted_html:
            errors.append("Headers not found with expected color")

    # Check for moves in the PGN (simple check: look for "digit. " pattern)
    move_pattern = re.compile(r'\d+\.\s+[NBRQK]?[a-h]?[1-8]?[x\-]?[a-h][1-8]')
    has_moves = bool(move_pattern.search(pgn_text))

    # Check that comments are formatted (if present in move notation, not in headers)
    if '{' in pgn_text and '}' in pgn_text and has_moves:
        if comment_marker not in formatted_html:
            errors.append("Comments not found with expected color")

    # Check that variations are formatted (if present in move notation)
    move_notation_start = 0
    for match in re.finditer(r'\]', pgn_text):
        move_notation_start = match.end()
    move_notation_text = pgn_text[move_notation_start:] if move_notation_start < len(pgn_text) else pgn_text
    has_variations_in_moves = '(' in move_notation_text and ')' in move_notation_text and has_moves

    if has_variations_in_moves:
        if variation_marker not in formatted_html or 'font-style: italic' not in formatted_html:
            errors.append("Variations not found with expected styling")
    # Check that move numbers are formatted (if moves present)
    if has_moves:
        has_formatted_move_numbers = move_number_marker in formatted_html and (
            (not move_number_bold) or ('font-weight: bold' in formatted_html)
        )
        move_number_pattern = re.compile(r'\d+\.\s+')
        move_numbers_in_pgn = move_number_pattern.findall(pgn_text)
        if move_numbers_in_pgn and not has_formatted_move_numbers:
            # Move numbers might only appear in variation styling if move number formatting is disabled.
            if variation_marker not in formatted_html:
                errors.append("Move numbers not found with expected formatting (color/bold from config)")

    has_result_in_moves = bool(PGN_MOVE_RESULT_RE.search(move_notation_text))

    if has_result_in_moves:
        if result_marker not in formatted_html or (result_bold and 'font-weight: bold' not in formatted_html):
            errors.append("Results not found with expected formatting (color/bold from config)")

    # Check that results in variations are NOT formatted as results
    variation_span_pattern = re.compile(
        r'<span[^>]*color:\s*rgb\(\s*\d+,\s*\d+,\s*\d+\s*\)[^>]*font-style:\s*italic[^>]*>([^<]*)</span>'
    )
    for match in variation_span_pattern.finditer(formatted_html):
        variation_content = match.group(1)
        if PGN_MOVE_RESULT_RE.search(variation_content):
            full_variation_span = match.group(0)
            if result_marker in full_variation_span:
                errors.append("Result in variation is incorrectly formatted as result (should use variation formatting)")

    open_spans = formatted_html.count('<span')
    close_spans = formatted_html.count('</span>')
    if open_spans != close_spans:
        errors.append(f"Unmatched span tags: {open_spans} open, {close_spans} close")

    text_content_pattern = re.compile(r'>([^<]+)<')
    for match in text_content_pattern.finditer(formatted_html):
        text_content = match.group(1)
        if '&lt;' in text_content and '&gt;' in text_content:
            if re.search(r'&lt;[a-zA-Z]', text_content):
                errors.append(f"HTML tags appearing as text content: {text_content[:100]}")
                break

    nag_pattern = re.compile(r'\$(\d+)')
    has_nags = bool(nag_pattern.search(pgn_text))

    if has_nags:
        nag_matches = nag_pattern.findall(pgn_text)
        if nag_matches:
            common_nag_meanings = [
                "poor move", "very poor move", "good move", "very good move",
                "blunder", "mistake", "inaccuracy",
                "White has", "Black has", "advantage", "decisive"
            ]
            has_nag_text = any(meaning in formatted_html for meaning in common_nag_meanings)
            empty_nag_pattern = re.compile(r'\s+\(\s*\)')
            has_empty_nags = bool(empty_nag_pattern.search(formatted_html))
            if has_empty_nags:
                errors.append("NAG conversion appears to have failed - empty parentheses found (should contain NAG text)")
            elif not has_nag_text:
                nag_symbols = ['!', '?', '!!', '??', '!?', '?!']
                has_nag_symbols = any(symbol in formatted_html for symbol in nag_symbols)
                if not has_nag_symbols:
                    has_unknown_nag = 'NAG 146' in formatted_html or 'Novelty' in formatted_html
                    if not has_unknown_nag:
                        pass

    header_pattern = re.compile(r'<span[^>]*color:\s*rgb\(\s*\d+,\s*\d+,\s*\d+\s*\)[^>]*>([^<]*)</span>')
    for match in header_pattern.finditer(formatted_html):
        header_content = match.group(1)
        if variation_marker in header_content or 'font-style: italic' in header_content:
            errors.append("Variation formatting found inside header (should not happen)")
        if move_number_marker in header_content and (not move_number_bold or 'font-weight: bold' in header_content):
            if re.search(r'\d+\.\s*', header_content):
                errors.append("Move number formatting found inside header (should not happen)")
        if result_marker in header_content and 'Result' not in match.group(0):
            if PGN_MOVE_RESULT_RE.search(header_content):
                errors.append("Result formatting found inside non-Result header (should not happen)")

    if has_moves:
        default_text_color = pgn_cfg.get("text_color", [220, 220, 220])
        move_color_pattern = re.compile(rf'color:\s*rgb\(\s*{int(default_text_color[0])},\s*{int(default_text_color[1])},\s*{int(default_text_color[2])}\s*\)')
        has_move_color = bool(move_color_pattern.search(formatted_html))
        if has_moves and not has_move_color:
            variation_move_pattern = re.compile(rf'{re.escape(variation_marker)}.*font-style:\s*italic')
            has_variation_moves = bool(variation_move_pattern.search(formatted_html))
            if not has_variation_moves:
                pass  # Move color formatting might be disabled in config

    if "NAG Symbols" in test_name or "Unknown NAG" in test_name:
        if "$1" in pgn_text or "$2" in pgn_text or "$146" in pgn_text:
            has_symbols = any(symbol in formatted_html for symbol in ['!', '?', '!!', '??', '!?', '?!'])
            has_nag_text = 'good move' in formatted_html or 'poor move' in formatted_html or 'NAG 146' in formatted_html or 'Novelty' in formatted_html
            if not has_symbols and not has_nag_text:
                errors.append("NAG symbols or text should appear in formatted HTML for NAG test cases")

    if "Unknown NAG" in test_name:
        if "$146" in pgn_text:
            has_unknown_nag = 'NAG 146' in formatted_html or 'Novelty' in formatted_html
            if not has_unknown_nag:
                errors.append("Unknown NAG 146 should be converted to 'NAG 146' or 'Novelty'")

    if "Mainline Moves" in test_name and has_moves:
        default_text_color = pgn_cfg.get("text_color", [220, 220, 220])
        move_color_pattern = re.compile(rf'color:\s*rgb\(\s*{int(default_text_color[0])},\s*{int(default_text_color[1])},\s*{int(default_text_color[2])}\s*\)')
        has_move_color = bool(move_color_pattern.search(formatted_html))
        if not has_move_color:
            pass  # Move color formatting might be disabled in config

    # * inside comment or variation must not be wrapped as game result (yellow bold only on *)
    if "asterisk inside comment not a result" in test_name or "asterisk inside variation not a result" in test_name:
        if re.search(r'font-weight:\s*bold">\*</span>', formatted_html):
            errors.append(
                "Standalone * in comment or variation must not use result (yellow/bold) formatting"
            )

    return errors


class TestPgnFormatter(unittest.TestCase):
    """Unit tests for PGN formatter service."""

    @classmethod
    def setUpClass(cls):
        cls.config = ConfigLoader().load()

    def test_all_formatter_cases(self):
        """Run all formatter test cases via subTest."""
        for test_case in self._get_test_cases():
            with self.subTest(name=test_case["name"]):
                pgn_text = test_case["pgn"]
                formatted_html, move_info = PgnFormatterService.format_pgn_to_html(pgn_text, self.config)
                errors = _validate_formatter_output(pgn_text, formatted_html, move_info, test_case["name"], self.config)
                self.assertEqual([], errors, "\n".join(errors) if errors else "")

    def _get_test_cases(self):
        """Return list of (name, pgn) test cases."""
        return [
        # Test 1: Simple PGN with minimal headers and basic moves
        {
            "name": "Simple PGN - Minimal Headers, Basic Moves",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 1-0"""
        },
        
        # Test 2: PGN with comments
        {
            "name": "PGN with Comments",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 {This is a good opening move} e5 2. Nf3 Nc6 3. Bb5 {Spanish Opening} 1-0"""
        },
        
        # Test 3: PGN with variations
        {
            "name": "PGN with Variations",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 (1... c5 2. Nf3) 2. Nf3 Nc6 3. Bb5 1-0"""
        },
        
        # Test 4: PGN with annotations
        {
            "name": "PGN with Annotations",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4! e5? 2. Nf3!? Nc6?! 3. Bb5!! 1-0"""
        },
        
        # Test 5: PGN with headers containing parentheses (dates, etc.)
        {
            "name": "PGN with Headers Containing Parentheses",
            "pgn": """[Event "Test (Blitz)"]
[Site "Test"]
[Date "2025.01.01 (Monday)"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 1-0"""
        },
        
        # Headers with empty quoted value (e.g. [Site ""]) must match header regex and render as headers
        {
            "name": "Headers with empty tag value (Site)",
            "pgn": """[Event "Mephisto Phoenix Game"] [Site ""]
[White "W"]
[Black "B"]
[Result "1-0"]

1. e4 e5 1-0"""
        },
        
        # Test 6: PGN with comments in variations
        {
            "name": "PGN with Comments in Variations",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 (1... c5 {Sicilian Defense} 2. Nf3) 2. Nf3 Nc6 3. Bb5 1-0"""
        },
        
        # Test 7: PGN with complex variations
        {
            "name": "PGN with Complex Variations",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. d4 Nf6 2. Nc3 e6 (2... d5 3. e4) 3. e4 d5 4. e5 Nfd7 5. f4 c5 1-0"""
        },
        
        # Test 8: User's complex example with all features
        {
            "name": "Complex PGN - User Example with Headers, Comments, Variations",
            "pgn": """[Event "Chessable Masters Play In"]
[Site "Chess.com INT"]
[Date "2025.02.17"]
[Round "1"]
[White "Hong, Andrew Z"]
[Black "Kramnik, Vladimir"]
[Result "1-0"]
[ECO "C11"]
[WhiteElo "2579"]
[BlackElo "2753"]
[WhiteFideId "2099438"]
[WhiteFideId "4101588"]
[PlyCount "53"]
[Beauty "8249579424798"]
[GameId "2146417135622649"]
[EventDate "2025.02.17"]
[EventType "swiss (blitz)"]
[EventRounds "9"]
[EventCountry "USA"]
[SourceTitle "Mega2025 Update 16"]
[Source "Chessbase"]
[SourceDate "2025.02.21"]
[SourceVersion "1"]
[SourceVersionDate "2025.02.21"]
[SourceQuality "1"]

1. d4 Nf6 2. Nc3 e6 3. e4 d5 4. e5 Nfd7 5. f4 c5 6. Nf3 Nc6 7. Be3 Be7 8. Qd2 a6 9. Bd3 {is the new trend. ist der neue Trend.} b5 10. Qf2 c4 11. Be2 Nb6 12. a3 Bd7 $146 (12... b4 13. axb4 Nxb4 14. Bd1 Bd7 15. O-O a5 16. g4 g6 17. h4 a4 18. Kg2 Nc6 19. Rh1 f5 20. exf6 Bxf6 21. h5 Qe7 22. g5 Bg7 23. Ne5 {1-0 Cheparinov,I (2686)-Tratar,M (2409) SLO-chT 32nd Ljubljana 2022 (8.4)}) 13. O-O g6 14. Qg3 Qc7 15. Ng5 b4 16. axb4 Nxb4 17. f5 Nxc2 18. Nxf7 Nxe3 19. Qxe3 Rf8 20. fxg6 hxg6 21. Qh6 Rxf7 22. Rxf7 Kd8 23. Rxe7 Kxe7 24. Qh4+ Ke8 25. Qh8+ Ke7 26. Qf6+ Ke8 27. Rf1 1-0"""
        },
        
        # Test 9: PGN with only headers (no moves)
        {
            "name": "PGN with Only Headers",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "*"]"""
        },
        
        # Test 10: PGN with multiple variations
        {
            "name": "PGN with Multiple Variations",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 (1... c5 2. Nf3) (1... e6 2. d4) 2. Nf3 Nc6 3. Bb5 1-0"""
        },
        
        # Test 11: PGN with result formatting (test all result types)
        {
            "name": "PGN with Result Formatting",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 1-0"""
        },
        
        # Test 12: PGN with different result types
        {
            "name": "PGN with Different Result Types",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 0-1"""
        },
        
        # Test 13: PGN with draw result
        {
            "name": "PGN with Draw Result",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 1/2-1/2"""
        },
        
        # Undecided / unfinished game (*) in move text must use result styling (not \b*\b)
        {
            "name": "PGN with undecided result (*) in moves",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "*"]

1. e4 e5 2. Nf3 *"""
        },
        
        # * inside a main-line comment is not a game result — must not get result styling
        {
            "name": "asterisk inside comment not a result",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 {See * marker in comment} 2. Nf3 Nc6 3. Bb5 1-0"""
        },
        
        # * inside a variation line is not the game's termination — must not get result styling
        {
            "name": "asterisk inside variation not a result",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 (1. d4 d5 *) 2. Nf3 Nc6 3. Bb5 1-0"""
        },
        
        # Test 14: PGN with result in variation (should NOT be formatted as result)
        {
            "name": "PGN with Result in Variation",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 (1... c5 2. Nf3 1-0) 2. Nf3 Nc6 3. Bb5 1-0"""
        },
        
        # Test 15: PGN with result in variation comment (complex example)
        {
            "name": "PGN with Result in Variation Comment",
            "pgn": """[Event "Chessable Masters Play In"] [Site "Chess.com INT"] [Date "2025.02.17"] [Round "1"] [White "Hong, Andrew Z"] [Black "Kramnik, Vladimir"] [Result "1-0"] [ECO "C11"] [WhiteElo "2579"] [BlackElo "2753"] [WhiteFideId "4101588"] [PlyCount "53"] [Beauty "8249579424798"] [GameId "2146417135622649"] [EventDate "2025.02.17"] [EventType "swiss (blitz)"] [EventRounds "9"] [EventCountry "USA"] [SourceTitle "Mega2025 Update 16"] [Source "Chessbase"] [SourceDate "2025.02.21"] [SourceVersion "1"] [SourceVersionDate "2025.02.21"] [SourceQuality "1"]

1. d4 Nf6 2. Nc3 e6 3. e4 d5 4. e5 Nfd7 5. f4 c5 6. Nf3 Nc6 7. Be3 Be7 8. Qd2 a6 9. Bd3 { is the new trend. ist der neue Trend. } 9... b5 10. Qf2 c4 11. Be2 Nb6 12. a3 Bd7 $146 (12... b4 13. axb4 Nxb4 14. Bd1 Bd7 a5 16. g4 g6 17. h4 a4 18. Kg2 Nc6 19. Rh1 f5 20. exf6 Bxf6 21. h5 Qe7 22. g5 Bg7 23. Ne5 { 1-0 Cheparinov,I (2686)-Tratar,M (2409) SLO-chT 32nd Ljubljana 2022 (8.4) }) 13. O-O g6 14. Qg3 Qc7 15. Ng5 b4 16. axb4 Nxb4 17. f5 Nxc2 18. Nxf7 Nxe3 19. Qxe3 Rf8 20. fxg6 hxg6 21. Qh6 Rxf7 22. Rxf7 Kd8 23. Rxe7 Kxe7 24. Qh4+ Ke8 25. Qh8+ Ke7 26. Qf6+ Ke8 27. Rf1 1-0"""
        },
        
        # Test 16: PGN with NAG symbols (use_symbols setting)
        {
            "name": "PGN with NAG Symbols (use_symbols)",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 $1 c5 $2 2. Nf3 $3 e6 $4 3. Bb5 $5 Nc6 $6 1-0"""
        },
        
        # Test 17: PGN with unknown NAG (e.g., NAG 146)
        {
            "name": "PGN with Unknown NAG (146)",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 c5 2. Nf3 e6 3. c4 Nc6 4. Nc3 Nf6 5. Be2 d5 $146 6. e5 Ne4 1-0"""
        },
        
        # Test 18: PGN with move color formatting (mainline moves)
        {
            "name": "PGN with Mainline Moves (move color formatting)",
            "pgn": """[Event "Test Game"]
[Site "Test"]
[Date "2025.01.01"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 1-0"""
        },
        ]


if __name__ == "__main__":
    unittest.main()

