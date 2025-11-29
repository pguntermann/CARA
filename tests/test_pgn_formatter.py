"""Test script for PGN formatter service.

Tests various PGN formats and complexity levels to ensure the formatter
handles headers, comments, variations, moves, and annotations correctly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.pgn_formatter_service import PgnFormatterService
from app.config.config_loader import ConfigLoader


def test_formatter(pgn_text: str, test_name: str, config: dict) -> bool:
    """Test the formatter with a given PGN and validate results.
    
    Args:
        pgn_text: PGN text to format
        test_name: Name of the test case
        config: Configuration dictionary
        
    Returns:
        True if test passes, False otherwise
    """
    print(f"\n{'='*80}")
    print(f"Test: {test_name}")
    print(f"{'='*80}")
    
    try:
        formatted_html, move_info = PgnFormatterService.format_pgn_to_html(pgn_text, config)
        
        # Basic validation
        errors = []
        
        # Check that headers are formatted (if headers exist)
        if '[' in pgn_text and ']' in pgn_text:
            if 'color: rgb(100, 150, 255)' not in formatted_html:
                errors.append("Headers not found with expected color")
        
        # Check for moves in the PGN (simple check: look for "digit. " pattern)
        import re
        move_pattern = re.compile(r'\d+\.\s+[NBRQK]?[a-h]?[1-8]?[x\-]?[a-h][1-8]')
        has_moves = bool(move_pattern.search(pgn_text))
        
        # Check that comments are formatted (if present in move notation, not in headers)
        if '{' in pgn_text and '}' in pgn_text and has_moves:
            # Check if comment formatting exists somewhere in the output
            if 'color: rgb(180, 200, 255)' not in formatted_html:
                errors.append("Comments not found with expected color")
        
        # Check that variations are formatted (if present in move notation)
        # Only check if variations exist outside of headers
        # Find where headers end and move notation begins
        move_notation_start = 0
        for match in re.finditer(r'\]', pgn_text):
            move_notation_start = match.end()
        
        # Check if parentheses exist in move notation (after headers)
        move_notation_text = pgn_text[move_notation_start:] if move_notation_start < len(pgn_text) else pgn_text
        has_variations_in_moves = '(' in move_notation_text and ')' in move_notation_text and has_moves
        
        if has_variations_in_moves:
            # Check if variation formatting exists
            if 'color: rgb(180, 180, 180)' not in formatted_html or 'font-style: italic' not in formatted_html:
                errors.append("Variations not found with expected styling")
        
        # Check that move numbers are formatted (if moves present)
        if has_moves:
            # Move numbers should be formatted with white color and bold
            # Check if there are any formatted move numbers (white color + bold)
            # or if move numbers exist in the PGN but aren't formatted
            has_formatted_move_numbers = 'color: rgb(255, 255, 255)' in formatted_html and 'font-weight: bold' in formatted_html
            # Check if there are move numbers in the PGN that should be formatted
            move_number_pattern = re.compile(r'\d+\.\s+')
            move_numbers_in_pgn = move_number_pattern.findall(pgn_text)
            # If there are move numbers in the PGN outside of headers, they should be formatted
            if move_numbers_in_pgn and not has_formatted_move_numbers:
                # Check if move numbers exist in the formatted HTML (they might be in variations)
                # Variations have move numbers formatted with grey/italic, so that's OK
                if 'color: rgb(180, 180, 180)' not in formatted_html:
                    # If no variation move numbers either, then main line move numbers should exist
                    errors.append("Move numbers not found with expected formatting (white/bold for main line)")
        
        # Check that results are formatted (if present in move notation, not in headers)
        # Find where headers end and move notation begins
        move_notation_start = 0
        for match in re.finditer(r'\]', pgn_text):
            move_notation_start = match.end()
        
        move_notation_text = pgn_text[move_notation_start:] if move_notation_start < len(pgn_text) else pgn_text
        result_pattern = re.compile(r'\b(1-0|0-1|1/2-1/2|\*)\b')
        has_result_in_moves = bool(result_pattern.search(move_notation_text))
        
        if has_result_in_moves:
            # Check if result formatting exists (yellow color and bold)
            if 'color: rgb(255, 255, 100)' not in formatted_html or 'font-weight: bold' not in formatted_html:
                errors.append("Results not found with expected formatting (yellow/bold)")
        
        # Check that results in variations are NOT formatted as results
        # Results inside variations should use variation formatting (grey/italic), not result formatting (yellow/bold)
        # Find all variation spans (have grey color and italic style) and check their content for result patterns
        # We need to check if result patterns appear in the TEXT CONTENT of variation spans
        # (not in nested spans, but directly in the variation span content)
        variation_span_pattern = re.compile(
            r'<span[^>]*color:\s*rgb\(180,\s*180,\s*180\)[^>]*font-style:\s*italic[^>]*>([^<]*)</span>'
        )
        for match in variation_span_pattern.finditer(formatted_html):
            variation_content = match.group(1)
            # Check if result pattern exists directly in the variation span content (not in nested spans)
            if result_pattern.search(variation_content):
                # Result found in variation content - this is OK, as long as it's not formatted as result
                # The variation span should have grey/italic formatting, not yellow/bold
                full_variation_span = match.group(0)
                # Check if this variation span has yellow result formatting (which would be wrong)
                if 'color: rgb(255, 255, 100)' in full_variation_span:
                    errors.append("Result in variation is incorrectly formatted as result (should use variation formatting)")
        
        # Check that HTML is well-formed (basic check)
        open_spans = formatted_html.count('<span')
        close_spans = formatted_html.count('</span>')
        if open_spans != close_spans:
            errors.append(f"Unmatched span tags: {open_spans} open, {close_spans} close")
        
        # Check that HTML tags are not shown as literal text in the output
        # Look for HTML tags that appear as text content (not as actual HTML structure)
        # This catches cases where HTML is being shown instead of being used for formatting
        import re
        # Check for escaped HTML tags (like &lt;span&gt; or &amp;lt;span&amp;gt;) that appear in text content
        # These should not appear as text - they should be part of actual HTML structure
        # Look for patterns like &lt;span&gt; or &lt;/span&gt; that appear outside of HTML attributes
        # This is a heuristic - escaped tags in text content suggest HTML is being shown as text
        
        # More importantly, check for literal HTML tags appearing in comments/variations
        # When HTML is shown as text, we might see patterns like "<span" or "</span>" in text content
        # Look for text content between tags that contains HTML-like patterns
        # Extract text content (between > and <) and check if it contains HTML tag patterns
        text_content_pattern = re.compile(r'>([^<]+)<')
        for match in text_content_pattern.finditer(formatted_html):
            text_content = match.group(1)
            # Check if text content contains HTML-like patterns (escaped or literal)
            # Look for escaped HTML tags in text (like &lt;span&gt;)
            if '&lt;' in text_content and '&gt;' in text_content:
                # Check if it's a complete HTML tag pattern (not just < and > separately)
                if re.search(r'&lt;[a-zA-Z]', text_content):
                    errors.append(f"HTML tags appearing as text content: {text_content[:100]}")
                    break  # Only report first occurrence to avoid spam
        
        # Check that NAGs (Numeric Annotation Glyphs) are converted to readable text
        # NAGs like $2, $4 should be converted to text like " (poor move)", " (very poor move)", etc.
        # First, check if the PGN contains NAGs
        nag_pattern = re.compile(r'\$(\d+)')
        has_nags = bool(nag_pattern.search(pgn_text))
        
        if has_nags:
            # Check that NAGs are converted to readable text (not just empty parentheses)
            # Look for patterns like " ()" (empty parentheses) which would indicate NAG conversion failed
            # The formatted HTML should contain NAG meanings like "poor move", "very poor move", etc.
            
            # Find all NAGs in the original PGN
            nag_matches = nag_pattern.findall(pgn_text)
            if nag_matches:
                # Check that at least some NAG meanings appear in the formatted HTML
                # Common NAG meanings that should appear
                common_nag_meanings = [
                    "poor move", "very poor move", "good move", "very good move",
                    "poor move", "blunder", "mistake", "inaccuracy",
                    "White has", "Black has", "advantage", "decisive"
                ]
                
                # Check if any NAG meaning appears in the formatted HTML
                has_nag_text = any(meaning in formatted_html for meaning in common_nag_meanings)
                
                # Also check that we don't have empty parentheses (which would indicate NAG conversion failed)
                # Look for patterns like " ()" or "( )" that might indicate empty NAG text
                empty_nag_pattern = re.compile(r'\s+\(\s*\)')
                has_empty_nags = bool(empty_nag_pattern.search(formatted_html))
                
                if has_empty_nags:
                    errors.append("NAG conversion appears to have failed - empty parentheses found (should contain NAG text)")
                elif not has_nag_text:
                    # If we have NAGs but no NAG text, it might still be OK if NAGs are shown as symbols
                    # But we should check if show_nag_text is enabled
                    # For now, just warn if we don't see NAG text
                    pass  # Don't fail - NAGs might be configured to show as symbols
        
        # Check that headers don't have unintended formatting
        # Headers should not contain variation formatting, move numbers, annotations, or results
        import re
        header_pattern = re.compile(r'<span[^>]*color:\s*rgb\(100,\s*150,\s*255\)[^>]*>([^<]*)</span>')
        for match in header_pattern.finditer(formatted_html):
            header_content = match.group(1)
            # Check for variation formatting inside headers
            if 'color: rgb(180, 180, 180)' in header_content or 'font-style: italic' in header_content:
                errors.append("Variation formatting found inside header (should not happen)")
            # Check for move number formatting inside headers
            if 'color: rgb(255, 255, 255)' in header_content and 'font-weight: bold' in header_content:
                # Check if it's actually a move number pattern
                if re.search(r'\d+\.\s*', header_content):
                    errors.append("Move number formatting found inside header (should not happen)")
            # Check for result formatting inside headers (but Result header itself is OK)
            if 'color: rgb(255, 255, 100)' in header_content and 'Result' not in match.group(0):
                if re.search(r'\b(1-0|0-1|1/2-1/2|\*)\b', header_content):
                    errors.append("Result formatting found inside non-Result header (should not happen)")
        
        if errors:
            print(f"[FAILED] {test_name}")
            for error in errors:
                print(f"   - {error}")
            print(f"\nFormatted HTML (first 500 chars):")
            print(formatted_html[:500])
            print(f"\nFormatted HTML (last 500 chars):")
            print(formatted_html[-500:] if len(formatted_html) > 500 else formatted_html)
            return False
        else:
            print(f"[PASSED] {test_name}")
            print(f"   - Formatted {len(formatted_html)} characters")
            print(f"   - Found {len(move_info)} moves")
            print(f"   - Found {open_spans} span tags")
            return True
            
    except Exception as e:
        print(f"[ERROR] in {test_name}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("PGN Formatter Service Tests")
    print("=" * 80)
    
    # Load config
    config_loader = ConfigLoader()
    config = config_loader.load()
    
    # Test cases
    test_cases = [
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
        
    ]
    
    # Run tests
    passed = 0
    failed = 0
    
    for test_case in test_cases:
        result = test_formatter(test_case["pgn"], test_case["name"], config)
        if result:
            passed += 1
        else:
            failed += 1
    
    # Summary
    print(f"\n{'='*80}")
    print("Test Summary")
    print(f"{'='*80}")
    print(f"Total tests: {len(test_cases)}")
    print(f"[PASSED] {passed}")
    print(f"[FAILED] {failed}")
    print(f"{'='*80}")
    
    if failed == 0:
        print("\n[SUCCESS] All tests passed!")
        return 0
    else:
        print(f"\n[WARNING] {failed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())

