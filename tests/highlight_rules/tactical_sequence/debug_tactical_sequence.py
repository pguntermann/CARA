"""Debug script to trace tactical sequence rule checks."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from tests.highlight_rules.helpers import load_test_game
from app.services.game_highlights.highlight_detector import HighlightDetector
from app.services.game_highlights.rule_registry import RuleRegistry
from app.config.config_loader import ConfigLoader
from app.services.game_highlights.helpers import parse_evaluation


def debug_tactical_sequence():
    """Debug the tactical sequence rule for move 25."""
    print("="*80)
    print("DEBUG: Tactical Sequence Rule - Move 25 (Bxg4)")
    print("="*80)
    
    # Load config and game
    config_loader = ConfigLoader()
    config = config_loader.load()
    highlights_config = config.get('ui', {}).get('panels', {}).get('detail', {}).get('summary', {}).get('highlights', {})
    game_data = load_test_game("tactical_sequence_Bxg4_should_match.json")
    
    # Create detector
    rule_registry = RuleRegistry(highlights_config.get('rules', {}))
    detector = HighlightDetector(highlights_config, rule_registry)
    
    # Find move 25
    target_move_num = 25
    target_move = None
    move_index = None
    
    for i, move in enumerate(game_data):
        if move.move_number == target_move_num:
            target_move = move
            move_index = i
            break
    
    if not target_move:
        print(f"ERROR: Move {target_move_num} not found")
        return
    
    print(f"\nTarget Move: {target_move_num}. {target_move.white_move}")
    print(f"Move Index: {move_index}")
    print(f"White Capture: {target_move.white_capture if target_move.white_capture else 'None'}")
    print(f"CPL White: {target_move.cpl_white if target_move.cpl_white else 'None'}")
    
    # Show sequence of moves
    print("\n" + "="*80)
    print("SEQUENCE OF MOVES:")
    print("="*80)
    
    for i in range(max(0, move_index - 1), min(len(game_data), move_index + 4)):
        move = game_data[i]
        move_num = move.move_number
        print(f"\nMove {move_num}:")
        print(f"  White: {move.white_move or 'None'} | CPL: {move.cpl_white or 'None'} | CPL2: {move.cpl_white_2 or 'None'} | CPL3: {move.cpl_white_3 or 'None'}")
        print(f"  Black: {move.black_move or 'None'} | CPL: {move.cpl_black or 'None'} | CPL2: {move.cpl_black_2 or 'None'} | CPL3: {move.cpl_black_3 or 'None'}")
        print(f"  White Capture: {move.white_capture or 'None'} | Black Capture: {move.black_capture or 'None'}")
        print(f"  Eval White: {move.eval_white or 'None'} | Eval Black: {move.eval_black or 'None'}")
        print(f"  White Material: {move.white_material or 'None'} | Black Material: {move.black_material or 'None'}")
    
    # Run detection and get context
    print("\n" + "="*80)
    print("RULE CHECKS:")
    print("="*80)
    
    # Manually check each condition
    print("\n1. INITIAL CONDITIONS:")
    print(f"   - Has white_capture: {bool(target_move.white_capture)}")
    print(f"   - Has cpl_white: {bool(target_move.cpl_white)}")
    print(f"   - Move index > 0: {move_index > 0}")
    
    if target_move.cpl_white:
        cpl = float(target_move.cpl_white)
        # Get good_move_max_cpl from highlights config
        good_move_max_cpl = highlights_config.get('rules', {}).get('good_move_max_cpl', 30)
        print(f"   - CPL ({cpl}) < good_move_max_cpl ({good_move_max_cpl}): {cpl < good_move_max_cpl}")
    
    # Check forcing sequence
    print("\n2. FORCING SEQUENCE CHECK:")
    print("   Checking moves after move 25...")
    
    forcing_count = 0
    for i in range(1, min(4, len(game_data) - move_index)):
        check_index = move_index + i
        if check_index >= len(game_data):
            break
        
        check_move = game_data[check_index]
        move_num = check_move.move_number
        
        print(f"\n   Move {move_num}:")
        
        # Check our continuation
        if check_move.cpl_white:
            our_cpl = float(check_move.cpl_white)
            print(f"     Our move (White): CPL = {our_cpl}, Good (<30): {our_cpl < 30}")
            if our_cpl < 30:
                forcing_count += 1
                print(f"     [OK] Counted our good move (count = {forcing_count})")
        
        # Check opponent response
        if check_move.cpl_black:
            opponent_cpl = float(check_move.cpl_black)
            cpl_2 = check_move.cpl_black_2
            cpl_3 = check_move.cpl_black_3
            
            print(f"     Opponent move (Black): CPL = {opponent_cpl}, CPL2 = {cpl_2}, CPL3 = {cpl_3}")
            
            # Check if forcing
            is_forcing = False
            if opponent_cpl < 30:
                if cpl_2:
                    cpl_2_val = float(cpl_2)
                    margin = cpl_2_val - opponent_cpl
                    print(f"     Margin (CPL2 - CPL): {margin}")
                    if margin >= 50:
                        is_forcing = True
                        print(f"     [OK] Narrow margin detected (margin >= 50)")
                    else:
                        print(f"     [FAIL] Margin too small (margin < 50)")
                elif opponent_cpl < 10:
                    is_forcing = True
                    print(f"     [OK] Very low CPL (<10) indicates forcing")
            
            if is_forcing:
                forcing_count += 1
                print(f"     [OK] Counted opponent's forced response (count = {forcing_count})")
            else:
                print(f"     [FAIL] Opponent's response not forcing")
    
    print(f"\n   Total forcing moves counted: {forcing_count}")
    print(f"   Required: >= 2")
    print(f"   Result: {'PASS' if forcing_count >= 2 else 'FAIL'}")
    
    # Check material change
    print("\n3. MATERIAL CHANGE CHECK:")
    prev_move = game_data[move_index - 1] if move_index > 0 else None
    if prev_move:
        material_before = prev_move.white_material or 0
        print(f"   Material before (move {prev_move.move_number}): {material_before}")
    
    # Check for captures in sequence
    captures_found = []
    for i in range(move_index, min(len(game_data), move_index + 4)):
        move = game_data[i]
        if move.white_capture:
            captures_found.append(f"Move {move.move_number}: White captured {move.white_capture}")
        if move.black_capture:
            captures_found.append(f"Move {move.move_number}: Black captured {move.black_capture}")
    
    print(f"   Captures found in sequence:")
    for cap in captures_found:
        print(f"     - {cap}")
    print(f"   Result: {'PASS' if captures_found else 'FAIL'}")
    
    # Check evaluation improvement
    print("\n4. EVALUATION IMPROVEMENT CHECK:")
    eval_before_str = None
    if prev_move:
        eval_before_str = prev_move.eval_white
        if eval_before_str:
            eval_before = parse_evaluation(eval_before_str)
            print(f"   Eval before (move {prev_move.move_number}): {eval_before_str} = {eval_before}cp")
    
    # Find end of sequence (move 27)
    end_move = None
    for i in range(move_index + 1, min(len(game_data), move_index + 4)):
        move = game_data[i]
        if move.move_number == 27:
            end_move = move
            break
    
    if end_move:
        eval_after_str = end_move.eval_white
        if eval_after_str:
            eval_after = parse_evaluation(eval_after_str)
            print(f"   Eval after (move {end_move.move_number}): {eval_after_str} = {eval_after}cp")
            
            if eval_before_str:
                improvement = eval_after - eval_before
                print(f"   Improvement: {improvement}cp")
                print(f"   Required: >= 200cp")
                print(f"   Result: {'PASS' if improvement >= 200 else 'FAIL'}")
    
    # Test the rule directly by running detection and checking raw highlights
    print("\n" + "="*80)
    print("DIRECT RULE EVALUATION (checking raw highlights before deduplication):")
    print("="*80)
    
    # Use the helper to get raw highlights
    from tests.highlight_rules.helpers import run_highlight_detection
    
    # Get all highlights (before deduplication if possible)
    all_highlights_raw = run_highlight_detection(game_data)
    
    # Filter for move 25 tactical_sequence
    tactical_raw = [h for h in all_highlights_raw if h.move_number == 25 and h.rule_type == "tactical_sequence"]
    
    print(f"Raw tactical_sequence highlights on move 25: {len(tactical_raw)}")
    for h in tactical_raw:
        print(f"  - {h.rule_type}: {h.description} (priority {h.priority}, white={h.is_white})")
    
    # Also check all raw highlights for move 25
    all_raw_m25 = [h for h in all_highlights_raw if h.move_number == 25]
    print(f"\nAll raw highlights on move 25: {len(all_raw_m25)}")
    for h in all_raw_m25:
        print(f"  - {h.rule_type}: {h.description} (priority {h.priority}, white={h.is_white})")
    
    # Run actual detection
    print("\n" + "="*80)
    print("ACTUAL DETECTION RESULT:")
    print("="*80)
    
    highlights = detector.detect_highlights(game_data, total_moves, opening_end, middlegame_end)
    matching = [h for h in highlights if h.move_number == target_move_num and h.rule_type == "tactical_sequence"]
    
    if matching:
        print(f"[OK] Tactical sequence DETECTED on move {target_move_num}")
        for h in matching:
            print(f"  Description: {h.description}")
            print(f"  Priority: {h.priority}")
    else:
        print(f"[FAIL] Tactical sequence NOT detected on move {target_move_num}")
        print("\nAll highlights for move 25:")
        all_highlights = [h for h in highlights if h.move_number == target_move_num]
        for h in all_highlights:
            print(f"  - {h.rule_type}: {h.description}")


if __name__ == "__main__":
    debug_tactical_sequence()

