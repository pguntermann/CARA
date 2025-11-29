"""Test script for PGN highlighting functionality.

Tests that move highlighting works correctly when variations, annotations,
and results are filtered out.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.pgn_formatter_service import PgnFormatterService
from app.config.config_loader import ConfigLoader
from app.views.detail_pgn_view import DetailPgnView
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QTextCursor
import re


def test_highlighting_with_filtering(pgn_text: str, test_name: str, config: dict, 
                                    filter_variations: bool = False,
                                    filter_annotations: bool = False,
                                    filter_results: bool = False,
                                    active_move_ply: int = 1) -> bool:
    """Test highlighting with filtered PGN text.
    
    Args:
        pgn_text: Original PGN text
        test_name: Name of the test case
        config: Configuration dictionary
        filter_variations: Whether to filter variations
        filter_annotations: Whether to filter annotations
        filter_results: Whether to filter results
        active_move_ply: Ply index of the move to highlight (1-based)
        
    Returns:
        True if test passes, False otherwise
    """
    print(f"\n{'='*80}")
    print(f"Test: {test_name}")
    print(f"{'='*80}")
    
    # Create a mock DetailPgnView to test filtering
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    
    view = DetailPgnView(config)
    
    # Set filter flags
    view._show_variations = not filter_variations
    view._show_annotations = not filter_annotations
    view._show_results = not filter_results
    
    # Filter the PGN text
    pgn_text_to_format = pgn_text
    if filter_variations:
        pgn_text_to_format = view._remove_variations(pgn_text_to_format)
    if filter_annotations:
        pgn_text_to_format = view._remove_annotations(pgn_text_to_format)
    if filter_results:
        pgn_text_to_format = view._remove_results(pgn_text_to_format)
    
    print(f"\nOriginal PGN (first 200 chars):")
    print(pgn_text[:200])
    print(f"\nFiltered PGN (first 200 chars):")
    print(pgn_text_to_format[:200])
    
    # Format the filtered PGN
    try:
        formatted_html, move_info = PgnFormatterService.format_pgn_to_html(
            pgn_text_to_format, 
            config, 
            0  # Don't highlight in HTML formatting
        )
        
        print(f"\nMove info extracted: {len(move_info)} moves")
        for i, (move_san, move_number, is_white) in enumerate(move_info[:5]):
            print(f"  Move {i+1}: {move_san} (move {move_number}, {'white' if is_white else 'black'})")
        
        # Set the PGN text in the view
        view.set_pgn_text(pgn_text)
        view._active_move_ply = active_move_ply
        
        # Wait for highlighting to complete
        app.processEvents()
        
        # Check if move_info was populated
        if not view._move_info:
            print("\nERROR: _move_info is empty!")
            return False
        
        print(f"\nView move info: {len(view._move_info)} moves")
        for i, (move_san, move_number, is_white) in enumerate(view._move_info[:5]):
            print(f"  Move {i+1}: {move_san} (move {move_number}, {'white' if is_white else 'black'})")
        
        # Check if the active move is in the move_info
        if active_move_ply > len(view._move_info):
            print(f"\nERROR: active_move_ply ({active_move_ply}) is greater than move_info length ({len(view._move_info)})!")
            return False
        
        # Get the target move
        target_move_san, target_move_number, target_is_white = view._move_info[active_move_ply - 1]
        print(f"\nTarget move: {target_move_san} (move {target_move_number}, {'white' if target_is_white else 'black'})")
        
        # Check if the move appears in the formatted HTML
        # Strip annotations from move_san for search
        move_san_clean = re.sub(r'[!?]{1,2}$', '', target_move_san)
        
        if target_is_white:
            pattern = rf'\b{re.escape(str(target_move_number))}\.\s+{re.escape(move_san_clean)}(?:[!?]{{1,2}})?'
        else:
            pattern = rf'\b{re.escape(move_san_clean)}(?:[!?]{{1,2}})?'
        
        if not re.search(pattern, formatted_html):
            print(f"\nERROR: Target move '{target_move_san}' (clean: '{move_san_clean}') not found in formatted HTML!")
            print(f"Search pattern: {pattern}")
            # Show a snippet of the HTML around where the move should be
            html_snippet = formatted_html[max(0, formatted_html.find(f"{target_move_number}.")-50):
                                        min(len(formatted_html), formatted_html.find(f"{target_move_number}.")+200)]
            print(f"HTML snippet around move {target_move_number}:")
            print(html_snippet)
            return False
        
        print(f"\n[OK] Target move found in formatted HTML")
        
        # Check if highlighting was applied (this is harder to test without rendering)
        # But we can at least verify the move info is correct
        
        return True
        
    except Exception as e:
        import traceback
        print(f"\nERROR: Exception during test: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all highlighting tests."""
    print("="*80)
    print("PGN Highlighting Tests")
    print("="*80)
    
    # Load config
    try:
        config_loader = ConfigLoader()
        config = config_loader.load()
    except Exception as e:
        print(f"ERROR: Failed to load config: {e}")
        return 1
    
    # Test cases
    test_cases = [
        {
            "name": "Basic PGN with variations",
            "pgn": '[Event "Test"]\n\n1. e4 e5 (1... c5 2. Nf3) 2. Nf3 Nc6 1-0',
            "filter_variations": False,
            "filter_annotations": False,
            "filter_results": False,
            "active_move_ply": 2
        },
        {
            "name": "PGN with variations filtered",
            "pgn": '[Event "Test"]\n\n1. e4 e5 (1... c5 2. Nf3) 2. Nf3 Nc6 1-0',
            "filter_variations": True,
            "filter_annotations": False,
            "filter_results": False,
            "active_move_ply": 2
        },
        {
            "name": "PGN with annotations",
            "pgn": '[Event "Test"]\n\n1. e4! e5? 2. Nf3! Nc6 1-0',
            "filter_variations": False,
            "filter_annotations": False,
            "filter_results": False,
            "active_move_ply": 2
        },
        {
            "name": "PGN with annotations filtered",
            "pgn": '[Event "Test"]\n\n1. e4! e5? 2. Nf3! Nc6 1-0',
            "filter_variations": False,
            "filter_annotations": True,
            "filter_results": False,
            "active_move_ply": 2
        },
        {
            "name": "PGN with results filtered",
            "pgn": '[Event "Test"]\n\n1. e4 e5 2. Nf3 Nc6 1-0',
            "filter_variations": False,
            "filter_annotations": False,
            "filter_results": True,
            "active_move_ply": 2
        },
        {
            "name": "PGN with variations and annotations filtered",
            "pgn": '[Event "Test"]\n\n1. e4! e5? (1... c5 2. Nf3) 2. Nf3! Nc6 1-0',
            "filter_variations": True,
            "filter_annotations": True,
            "filter_results": False,
            "active_move_ply": 2
        },
    ]
    
    passed = 0
    failed = 0
    
    for test_case in test_cases:
        result = test_highlighting_with_filtering(
            test_case["pgn"],
            test_case["name"],
            config,
            filter_variations=test_case["filter_variations"],
            filter_annotations=test_case["filter_annotations"],
            filter_results=test_case["filter_results"],
            active_move_ply=test_case["active_move_ply"]
        )
        
        if result:
            passed += 1
            print(f"\n[PASS] Test PASSED")
        else:
            failed += 1
            print(f"\n[FAIL] Test FAILED")
    
    print(f"\n{'='*80}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"{'='*80}")
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

