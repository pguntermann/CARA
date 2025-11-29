"""Helper utilities for highlight rule testing."""

import sys
import os
import json
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.models.moveslist_model import MoveData
from app.services.game_highlights.base_rule import GameHighlight, RuleContext
from app.services.game_highlights.highlight_detector import HighlightDetector
from app.services.game_highlights.rule_registry import RuleRegistry
from app.config.config_loader import ConfigLoader


def load_test_game(filename: str) -> List[MoveData]:
    """Load a test game from JSON file and convert to MoveData list.
    
    Args:
        filename: Name of JSON file in tests/highlight_rules/games/
    
    Returns:
        List of MoveData objects.
    """
    games_dir = Path(__file__).parent / "games"
    filepath = games_dir / filename
    
    if not filepath.exists():
        raise FileNotFoundError(f"Test game file not found: {filepath}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    moves = []
    for move_dict in data:
        move = MoveData(
            move_number=move_dict.get('move_number', 0),
            white_move=move_dict.get('white_move', ''),
            black_move=move_dict.get('black_move', ''),
            eval_white=move_dict.get('eval_white', ''),
            eval_black=move_dict.get('eval_black', ''),
            cpl_white=move_dict.get('cpl_white', ''),
            cpl_black=move_dict.get('cpl_black', ''),
            cpl_white_2=move_dict.get('cpl_white_2', ''),
            cpl_white_3=move_dict.get('cpl_white_3', ''),
            cpl_black_2=move_dict.get('cpl_black_2', ''),
            cpl_black_3=move_dict.get('cpl_black_3', ''),
            assess_white=move_dict.get('assess_white', ''),
            assess_black=move_dict.get('assess_black', ''),
            best_white=move_dict.get('best_white', ''),
            best_black=move_dict.get('best_black', ''),
            best_white_2=move_dict.get('best_white_2', ''),
            best_white_3=move_dict.get('best_white_3', ''),
            best_black_2=move_dict.get('best_black_2', ''),
            best_black_3=move_dict.get('best_black_3', ''),
            white_is_top3=move_dict.get('white_is_top3', False),
            black_is_top3=move_dict.get('black_is_top3', False),
            white_depth=move_dict.get('white_depth', 0),
            black_depth=move_dict.get('black_depth', 0),
            eco=move_dict.get('eco', ''),
            opening_name=move_dict.get('opening_name', ''),
            comment=move_dict.get('comment', ''),
            white_capture=move_dict.get('white_capture', ''),
            black_capture=move_dict.get('black_capture', ''),
            white_material=move_dict.get('white_material', 0),
            black_material=move_dict.get('black_material', 0),
            white_queens=move_dict.get('white_queens', 0),
            white_rooks=move_dict.get('white_rooks', 0),
            white_bishops=move_dict.get('white_bishops', 0),
            white_knights=move_dict.get('white_knights', 0),
            white_pawns=move_dict.get('white_pawns', 0),
            black_queens=move_dict.get('black_queens', 0),
            black_rooks=move_dict.get('black_rooks', 0),
            black_bishops=move_dict.get('black_bishops', 0),
            black_knights=move_dict.get('black_knights', 0),
            black_pawns=move_dict.get('black_pawns', 0),
            fen_white=move_dict.get('fen_white', ''),
            fen_black=move_dict.get('fen_black', '')
        )
        moves.append(move)
    
    return moves


def create_highlight_detector() -> HighlightDetector:
    """Create a HighlightDetector instance with configuration.
    
    Returns:
        Configured HighlightDetector instance.
    """
    config_loader = ConfigLoader()
    config = config_loader.load()
    highlights_config = config.get('ui', {}).get('panels', {}).get('detail', {}).get('summary', {}).get('highlights', {})
    
    rule_registry = RuleRegistry(highlights_config.get('rules', {}))
    
    # Get CPL thresholds from config or use defaults
    good_move_max_cpl = highlights_config.get('good_move_max_cpl', 50)
    inaccuracy_max_cpl = highlights_config.get('inaccuracy_max_cpl', 100)
    mistake_max_cpl = highlights_config.get('mistake_max_cpl', 200)
    
    detector = HighlightDetector(
        highlights_config,
        rule_registry,
        good_move_max_cpl=good_move_max_cpl,
        inaccuracy_max_cpl=inaccuracy_max_cpl,
        mistake_max_cpl=mistake_max_cpl
    )
    
    return detector


def run_highlight_detection(moves: List[MoveData]) -> List[GameHighlight]:
    """Run highlight detection on a list of moves.
    
    Args:
        moves: List of MoveData objects.
    
    Returns:
        List of GameHighlight objects.
    """
    detector = create_highlight_detector()
    
    # Calculate phase boundaries (simplified - can be enhanced)
    total_moves = len(moves)
    opening_end = 10  # Default opening end
    middlegame_end = 30  # Default middlegame end
    
    # Try to detect from moves
    for move in moves:
        if move.opening_name and move.opening_name != "*":
            # Still in opening
            if move.move_number > opening_end:
                opening_end = move.move_number
        if move.move_number > middlegame_end:
            middlegame_end = move.move_number
    
    highlights = detector.detect_highlights(
        moves,
        total_moves=total_moves,
        opening_end=opening_end,
        middlegame_end=middlegame_end
    )
    
    return highlights


def find_highlights(highlights: List[GameHighlight], 
                   move_number: int,
                   rule_type: str,
                   side: Optional[str] = None) -> List[GameHighlight]:
    """Find highlights matching criteria.
    
    Args:
        highlights: List of GameHighlight objects.
        move_number: Move number to match.
        rule_type: Rule type to match (e.g., "decoy", "fork").
        side: Optional side filter ("white" or "black").
    
    Returns:
        List of matching GameHighlight objects.
    """
    matching = []
    for h in highlights:
        if h.move_number == move_number and h.rule_type == rule_type:
            if side is None:
                matching.append(h)
            elif side == "white" and h.is_white:
                matching.append(h)
            elif side == "black" and not h.is_white:
                matching.append(h)
    return matching


def explain_failure(move_number: int,
                    rule_type: str,
                    side: str,
                    moves: List[MoveData],
                    highlights: List[GameHighlight]) -> None:
    """Provide detailed failure analysis for debugging.
    
    Args:
        move_number: Move number that should have matched.
        rule_type: Rule type that should have matched.
        side: Side ("white" or "black").
        moves: Full list of moves.
        highlights: All highlights found.
    """
    print(f"\n{'='*80}")
    print(f"FAILURE ANALYSIS: Move {move_number} - {rule_type} ({side})")
    print(f"{'='*80}\n")
    
    # Find the move
    move = None
    move_index = None
    for i, m in enumerate(moves):
        if m.move_number == move_number:
            move = m
            move_index = i
            break
    
    if not move:
        print(f"ERROR: Move {move_number} not found in game data!")
        return
    
    is_white = (side == "white")
    move_san = move.white_move if is_white else move.black_move
    
    print(f"Target Move: {move_number}. {move_san} ({side})")
    print(f"Expected Rule: {rule_type}")
    print()
    
    # Show move details
    print(f"Move Details:")
    print(f"  Move: {move_san}")
    if is_white:
        print(f"  CPL: {move.cpl_white}")
        print(f"  Assessment: {move.assess_white}")
        print(f"  Material (before): {move.white_material}")
        print(f"  Material (after): {move.black_material if move_index < len(moves) - 1 else 'N/A'}")
        print(f"  Capture: {move.white_capture}")
    else:
        print(f"  CPL: {move.cpl_black}")
        print(f"  Assessment: {move.assess_black}")
        print(f"  Material (before): {move.black_material}")
        print(f"  Material (after): {moves[move_index + 1].white_material if move_index < len(moves) - 1 else 'N/A'}")
        print(f"  Capture: {move.black_capture}")
    print()
    
    # Show FEN positions
    if is_white:
        print(f"Position After Move:")
        print(f"  FEN: {move.fen_white}")
    else:
        print(f"Position After Move:")
        print(f"  FEN: {move.fen_black}")
    print()
    
    # Show follow-up moves
    if move_index < len(moves) - 1:
        next_move = moves[move_index + 1]
        print(f"Follow-up Move:")
        if is_white:
            print(f"  {next_move.move_number}. ... {next_move.black_move}")
        else:
            print(f"  {next_move.move_number}. {next_move.white_move} ...")
        if move_index < len(moves) - 2:
            next_next = moves[move_index + 2]
            if is_white:
                print(f"  {next_next.move_number}. {next_next.white_move} ...")
            else:
                print(f"  {next_next.move_number}. ... {next_next.black_move}")
    print()
    
    # Show what highlights were found for this move
    move_highlights = [h for h in highlights if h.move_number == move_number]
    if move_highlights:
        print(f"Highlights Found for Move {move_number}:")
        for h in move_highlights:
            print(f"  - {h.rule_type} ({'white' if h.is_white else 'black'}): {h.description}")
            print(f"    Priority: {h.priority}")
    else:
        print(f"No highlights found for move {move_number}")
    print()
    
    # Show all highlights for context
    print(f"All Highlights in Game:")
    for h in highlights:
        print(f"  Move {h.move_number}: {h.rule_type} ({'white' if h.is_white else 'black'}) - {h.description}")
    print()
    
    # Material analysis for decoy/fork rules
    if rule_type in ["decoy", "fork", "pin", "skewer"]:
        print(f"Material Analysis:")
        if move_index > 0:
            prev_move = moves[move_index - 1]
            if is_white:
                material_before = prev_move.black_material
                material_after = move.black_material
                material_change = material_after - material_before
                print(f"  Black material before: {material_before}")
                print(f"  Black material after: {material_after}")
                print(f"  Material change: {material_change}")
            else:
                material_before = prev_move.white_material
                material_after = move.white_material
                material_change = material_after - material_before
                print(f"  White material before: {material_before}")
                print(f"  White material after: {material_after}")
                print(f"  Material change: {material_change}")
        print()
    
    print(f"{'='*80}\n")

