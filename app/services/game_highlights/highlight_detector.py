"""Main highlight detector service that orchestrates rule evaluation."""

from typing import List, Dict, Any, Tuple
from app.models.moveslist_model import MoveData
from app.services.game_highlights.base_rule import GameHighlight, RuleContext
from app.services.game_highlights.rule_registry import RuleRegistry
from app.services.game_highlights.helpers import parse_evaluation


class HighlightDetector:
    """Main service for detecting game highlights.
    
    Coordinates rule evaluation, deduplication, and filtering.
    """
    
    def __init__(self, config: Dict, rule_registry: RuleRegistry, 
                 good_move_max_cpl: int = 50, inaccuracy_max_cpl: int = 100, 
                 mistake_max_cpl: int = 200) -> None:
        """Initialize the highlight detector.
        
        Args:
            config: Configuration dictionary.
            rule_registry: RuleRegistry instance with registered rules.
            good_move_max_cpl: Maximum CPL for good move (from classification model).
            inaccuracy_max_cpl: Maximum CPL for inaccuracy (from classification model).
            mistake_max_cpl: Maximum CPL for mistake (from classification model).
        """
        self.config = config
        self.registry = rule_registry
        self.highlights_per_phase_limit = config.get('highlights_per_phase_limit', 10)
        self.good_move_max_cpl = good_move_max_cpl
        self.inaccuracy_max_cpl = inaccuracy_max_cpl
        self.mistake_max_cpl = mistake_max_cpl
    
    def detect_highlights(self, moves: List[MoveData], total_moves: int,
                         opening_end: int, middlegame_end: int) -> List[GameHighlight]:
        """Detect game highlights by evaluating all rules.
        
        Args:
            moves: List of MoveData instances.
            total_moves: Total number of moves in the game.
            opening_end: Move number where opening phase ends.
            middlegame_end: Move number where middlegame phase ends.
            
        Returns:
            List of GameHighlight instances, sorted and limited per phase.
        """
        highlights: List[GameHighlight] = []
        
        # Shared state for rules that need cross-move tracking
        shared_state: Dict[str, Any] = {
            'eval_swing_highlights': {},  # Key: (is_white, phase, direction) -> (swing_value, highlight)
            'missed_mate_tracking': {},  # Key: (is_white, phase) -> (count, first_move, last_move, best_move)
            'delayed_mate_created': set(),
            'delayed_mating_ranges': [],
            'pawn_storm_created': set(),
        }
        
        # Initialize previous values
        prev_white_bishops = 2
        prev_black_bishops = 2
        prev_white_knights = 2
        prev_black_knights = 2
        prev_white_queens = 1
        prev_black_queens = 1
        prev_white_rooks = 2
        prev_black_rooks = 2
        prev_white_pawns = 8
        prev_black_pawns = 8
        prev_white_material = 0
        prev_black_material = 0
        last_book_move_number = 0
        theory_departed = False
        
        # Get enabled rules
        rules = self.registry.get_enabled_rules()
        
        # Iterate through moves and evaluate each rule
        for i, move in enumerate(moves):
            move_num = move.move_number
            
            # Determine phase
            if move_num <= opening_end:
                phase = "opening"
            elif move_num < middlegame_end:
                phase = "middlegame"
            else:
                phase = "endgame"
            
            # Create context for this move
            prev_move = moves[i - 1] if i > 0 else None
            next_move = moves[i + 1] if i < len(moves) - 1 else None
            
            context = RuleContext(
                move_index=i,
                total_moves=total_moves,
                opening_end=opening_end,
                middlegame_end=middlegame_end,
                prev_move=prev_move,
                next_move=next_move,
                prev_white_bishops=prev_white_bishops,
                prev_black_bishops=prev_black_bishops,
                prev_white_knights=prev_white_knights,
                prev_black_knights=prev_black_knights,
                prev_white_queens=prev_white_queens,
                prev_black_queens=prev_black_queens,
                prev_white_rooks=prev_white_rooks,
                prev_black_rooks=prev_black_rooks,
                prev_white_pawns=prev_white_pawns,
                prev_black_pawns=prev_black_pawns,
                prev_white_material=prev_white_material,
                prev_black_material=prev_black_material,
                last_book_move_number=last_book_move_number,
                theory_departed=theory_departed,
                good_move_max_cpl=self.good_move_max_cpl,
                inaccuracy_max_cpl=self.inaccuracy_max_cpl,
                mistake_max_cpl=self.mistake_max_cpl,
                shared_state=shared_state,
                moves=moves
            )
            
            # Evaluate all enabled rules
            for rule in rules:
                try:
                    rule_highlights = rule.evaluate(move, context)
                    highlights.extend(rule_highlights)
                except Exception:
                    # Silently skip rules that fail (to prevent one bad rule from breaking everything)
                    pass
            
            # Update previous values for next iteration
            prev_white_bishops = move.white_bishops
            prev_black_bishops = move.black_bishops
            prev_white_knights = move.white_knights
            prev_black_knights = move.black_knights
            prev_white_queens = move.white_queens
            prev_black_queens = move.black_queens
            prev_white_rooks = move.white_rooks
            prev_black_rooks = move.black_rooks
            prev_white_pawns = move.white_pawns
            prev_black_pawns = move.black_pawns
            prev_white_material = move.white_material
            prev_black_material = move.black_material
            
            # Update theory departure tracking
            if move.assess_white == "Book Move" or move.assess_black == "Book Move":
                last_book_move_number = move_num
            if not theory_departed and move_num > last_book_move_number:
                # Check if move is not the best move (theory departure)
                # Only "Best Move" counts as theory - "Good Move" is a deviation
                if (move.assess_white != "Best Move" and move.white_move) or \
                   (move.assess_black != "Best Move" and move.black_move):
                    theory_departed = True
        
        # Post-process highlights: deduplication and filtering
        highlights = self._post_process_highlights(highlights, shared_state, opening_end, middlegame_end)
        
        return highlights
    
    def _post_process_highlights(self, highlights: List[GameHighlight],
                                 shared_state: Dict[str, Any],
                                 opening_end: int, middlegame_end: int) -> List[GameHighlight]:
        """Post-process highlights: deduplication, filtering, and sorting.
        
        Args:
            highlights: Raw list of highlights from all rules.
            shared_state: Shared state dictionary from rule evaluation.
            opening_end: Move number where opening phase ends.
            middlegame_end: Move number where middlegame phase ends.
            
        Returns:
            Processed list of highlights, sorted and limited per phase.
        """
        # Build a list of all move ranges from multi-move highlights
        # This includes delayed_mating_ranges and any other highlights with move_number_end
        all_move_ranges: List[Tuple[int, int, bool, str]] = []  # (start, end, is_white, rule_type)
        
        # Add delayed mating ranges (already tracked in shared_state)
        delayed_mating_ranges = shared_state.get('delayed_mating_ranges', [])
        for range_start, range_end, range_is_white in delayed_mating_ranges:
            all_move_ranges.append((range_start, range_end, range_is_white, "delayed_mating"))
        
        # Add ranges from other multi-move highlights (tactical_sequence, perpetual_check, etc.)
        for highlight in highlights:
            if highlight.move_number_end is not None and highlight.move_number_end > highlight.move_number:
                all_move_ranges.append((
                    highlight.move_number,
                    highlight.move_number_end,
                    highlight.is_white,
                    highlight.rule_type if highlight.rule_type else ""
                ))
        
        # Filter out highlights that fall within any move range
        # This prevents duplicate highlights on moves that are part of a multi-move sequence
        if all_move_ranges:
            filtered_highlights: List[GameHighlight] = []
            for highlight in highlights:
                should_keep = True
                
                # Check if this highlight falls within any move range
                for range_start, range_end, range_is_white, range_rule_type in all_move_ranges:
                    # Only filter if it's the same side and different rule type
                    # (same rule type is already handled by deduplicate_phase)
                    if highlight.is_white == range_is_white and highlight.rule_type != range_rule_type:
                        # Check if highlight's move number falls within the range
                        # Exclude the start move (range_start) since that's where the sequence highlight is
                        # Only filter moves that are strictly within the range (range_start < move <= range_end)
                        if range_start < highlight.move_number <= range_end:
                            should_keep = False
                            break
                        # Also check if highlight has a range that overlaps
                        if highlight.move_number_end is not None:
                            # Check if any part of this highlight's range overlaps with the existing range
                            # (but don't filter if this highlight starts at the same move as the range)
                            if highlight.move_number != range_start:
                                if (range_start < highlight.move_number <= range_end) or \
                                   (range_start < highlight.move_number_end <= range_end) or \
                                   (highlight.move_number < range_start <= highlight.move_number_end):
                                    should_keep = False
                                    break
                
                if should_keep:
                    filtered_highlights.append(highlight)
            
            highlights = filtered_highlights
        
        # Filter out individual "missed checkmate opportunity" highlights that are part of delayed mating sequences
        # Also suppress all subsequent missed mate opportunities after a delayed mating has been detected
        if delayed_mating_ranges:
            # Track the latest move number where delayed mating was detected for each side
            latest_delayed_mate_white = None
            latest_delayed_mate_black = None
            
            for range_start, range_end, range_is_white in delayed_mating_ranges:
                if range_is_white:
                    if latest_delayed_mate_white is None or range_end > latest_delayed_mate_white:
                        latest_delayed_mate_white = range_end
                else:
                    if latest_delayed_mate_black is None or range_end > latest_delayed_mate_black:
                        latest_delayed_mate_black = range_end
            
            filtered_highlights: List[GameHighlight] = []
            for highlight in highlights:
                # Check if this is a "missed checkmate opportunity" highlight
                is_missed_mate = "missed a checkmate opportunity" in highlight.description
                
                if is_missed_mate:
                    should_keep = True
                    
                    # Check if this highlight falls within any delayed mating range
                    for range_start, range_end, range_is_white in delayed_mating_ranges:
                        if highlight.is_white == range_is_white:
                            if range_start <= highlight.move_number <= range_end:
                                should_keep = False
                                break
                    
                    # Also check if this highlight comes after a delayed mating for the same side
                    if should_keep:
                        if highlight.is_white and latest_delayed_mate_white is not None:
                            if highlight.move_number > latest_delayed_mate_white:
                                should_keep = False
                        elif not highlight.is_white and latest_delayed_mate_black is not None:
                            if highlight.move_number > latest_delayed_mate_black:
                                should_keep = False
                    
                    if should_keep:
                        filtered_highlights.append(highlight)
                else:
                    filtered_highlights.append(highlight)
            
            highlights = filtered_highlights
        
        # Add evaluation swing highlights (already deduplicated per side/phase/direction)
        eval_swing_highlights = shared_state.get('eval_swing_highlights', {})
        for swing_value, highlight in eval_swing_highlights.values():
            highlights.append(highlight)
        
        # Group highlights by phase FIRST (before deduplication and combination)
        opening_highlights = [h for h in highlights if h.move_number <= opening_end]
        middlegame_highlights = [h for h in highlights if opening_end < h.move_number < middlegame_end]
        endgame_highlights = [h for h in highlights if h.move_number >= middlegame_end]
        
        # Sort each phase by priority (descending), then by move number
        opening_highlights.sort(key=lambda x: (-x.priority, x.move_number))
        middlegame_highlights.sort(key=lambda x: (-x.priority, x.move_number))
        endgame_highlights.sort(key=lambda x: (-x.priority, x.move_number))
        
        # Extract pattern from highlight description (primary message)
        def extract_pattern(highlight: GameHighlight) -> str:
            """Extract the primary message pattern from a highlight description."""
            primary_message = highlight.description.split('.')[0].strip()
            return primary_message
        
        # Track patterns seen in previous phases for dynamic prioritization
        # Priority penalty for highlights that appeared in previous phases
        PRIORITY_PENALTY_FOR_REPEAT = 8
        MIN_HIGHLIGHTS_FOR_PENALTY = 7
        
        # Apply dynamic prioritization: penalize highlights that appeared in previous phases
        def apply_cross_phase_penalty(phase_highlights: List[GameHighlight],
                                      previous_patterns: set) -> List[GameHighlight]:
            """Apply priority penalty to highlights that match patterns from previous phases.
            
            Args:
                phase_highlights: List of highlights for current phase (already sorted).
                previous_patterns: Set of (is_white, pattern) tuples from previous phases.
            
            Returns:
                List of highlights with adjusted priorities, re-sorted.
            """
            # Only apply penalty if there are enough highlights to choose from
            if len(phase_highlights) <= MIN_HIGHLIGHTS_FOR_PENALTY:
                return phase_highlights
            
            # Create new highlights with adjusted priorities
            adjusted_highlights: List[GameHighlight] = []
            for highlight in phase_highlights:
                pattern = extract_pattern(highlight)
                pattern_key = (highlight.is_white, pattern)
                
                # Check if this pattern appeared in previous phases
                if pattern_key in previous_patterns:
                    # Apply penalty by creating a new highlight with reduced priority
                    adjusted_priority = highlight.priority - PRIORITY_PENALTY_FOR_REPEAT
                    adjusted_highlight = GameHighlight(
                        move_number=highlight.move_number,
                        is_white=highlight.is_white,
                        move_notation=highlight.move_notation,
                        description=highlight.description,
                        move_number_end=highlight.move_number_end,
                        priority=adjusted_priority
                    )
                    adjusted_highlights.append(adjusted_highlight)
                else:
                    adjusted_highlights.append(highlight)
            
            # Re-sort by adjusted priority (descending), then by move number
            adjusted_highlights.sort(key=lambda x: (-x.priority, x.move_number))
            return adjusted_highlights
        
        # Track patterns from previous phases for dynamic prioritization
        previous_patterns: set = set()
        
        # Remove duplicate descriptions within each phase (keep only first occurrence)
        # This happens BEFORE move-level combination to ensure each rule appears only once per phase/side
        def deduplicate_phase(phase_highlights: List[GameHighlight], phase_name: str = "") -> List[GameHighlight]:
            # Track count of each rule type per side (max 1 per rule type per phase)
            # Key: (is_white, rule_type) -> count
            rule_type_counts: Dict[Tuple[bool, str], int] = {}
            filtered: List[GameHighlight] = []
            removed_count = 0
            
            for highlight in phase_highlights:
                # Use rule_type for deduplication (groups all variations of the same rule together)
                # If rule_type is empty, fall back to primary message for backward compatibility
                rule_type = highlight.rule_type if highlight.rule_type else highlight.description.split('.')[0].strip()
                
                # Check if we've already seen this (side, rule_type) combination (max 1 per side per rule type per phase)
                key = (highlight.is_white, rule_type)
                count = rule_type_counts.get(key, 0)
                if count == 0:
                    filtered.append(highlight)
                    rule_type_counts[key] = 1
                else:
                    removed_count += 1
            
            return filtered
        
        # Combine highlights that refer to the same move (within each phase, after deduplication)
        def combine_same_move_highlights(phase_highlights: List[GameHighlight]) -> List[GameHighlight]:
            """Combine highlights on the same move, keeping max 2 descriptions."""
            # Group by (move_number, is_white)
            combined_highlights: Dict[Tuple[int, bool], List[GameHighlight]] = {}
            for highlight in phase_highlights:
                key = (highlight.move_number, highlight.is_white)
                if key not in combined_highlights:
                    combined_highlights[key] = []
                combined_highlights[key].append(highlight)
            
            # Merge highlights for each move, keeping max 2 descriptions
            merged_highlights: List[GameHighlight] = []
            for key, highlight_list in combined_highlights.items():
                # Sort by priority (descending) to keep the most important ones
                highlight_list.sort(key=lambda x: -x.priority)
                # Take up to 2 highlights
                selected = highlight_list[:2]
                
                if len(selected) == 1:
                    merged_highlights.append(selected[0])
                else:
                    # Combine descriptions
                    descriptions = [h.description for h in selected]
                    combined_description = ". ".join(descriptions)
                    # Use the highest priority
                    combined_priority = max(h.priority for h in selected)
                    # Use rule_type from first highlight (highest priority)
                    # If multiple highlights are combined, preserve the rule_type of the most important one
                    combined_rule_type = selected[0].rule_type if selected[0].rule_type else ""
                    # If first highlight has no rule_type, try the second one
                    if not combined_rule_type and len(selected) > 1:
                        combined_rule_type = selected[1].rule_type if selected[1].rule_type else ""
                    merged_highlights.append(GameHighlight(
                        move_number=selected[0].move_number,
                        is_white=selected[0].is_white,
                        move_notation=selected[0].move_notation,
                        description=combined_description,
                        move_number_end=selected[0].move_number_end,
                        priority=combined_priority,
                        rule_type=combined_rule_type
                    ))
            return merged_highlights
        
        # Process opening phase: apply penalty, deduplicate, combine same moves, then track patterns
        opening_highlights = apply_cross_phase_penalty(opening_highlights, previous_patterns)
        opening_highlights = deduplicate_phase(opening_highlights, "Opening")
        opening_highlights = combine_same_move_highlights(opening_highlights)
        # Track patterns from opening phase (after deduplication and combination, before limiting)
        for highlight in opening_highlights:
            pattern = extract_pattern(highlight)
            previous_patterns.add((highlight.is_white, pattern))
        
        # Process middlegame phase: apply penalty, deduplicate, combine same moves, then track patterns
        middlegame_highlights = apply_cross_phase_penalty(middlegame_highlights, previous_patterns)
        middlegame_highlights = deduplicate_phase(middlegame_highlights, "Middlegame")
        middlegame_highlights = combine_same_move_highlights(middlegame_highlights)
        # Track patterns from middlegame phase (after deduplication and combination, before limiting)
        for highlight in middlegame_highlights:
            pattern = extract_pattern(highlight)
            previous_patterns.add((highlight.is_white, pattern))
        
        # Process endgame phase: apply penalty, deduplicate, combine same moves
        endgame_highlights = apply_cross_phase_penalty(endgame_highlights, previous_patterns)
        endgame_highlights = deduplicate_phase(endgame_highlights, "Endgame")
        endgame_highlights = combine_same_move_highlights(endgame_highlights)
        
        # Limit per phase (after deduplication)
        opening_highlights = opening_highlights[:self.highlights_per_phase_limit]
        middlegame_highlights = middlegame_highlights[:self.highlights_per_phase_limit]
        endgame_highlights = endgame_highlights[:self.highlights_per_phase_limit]
        
        # Combine and sort by move number for final output
        # Sort by move_number first, then by is_white (white moves come before black moves)
        all_highlights = opening_highlights + middlegame_highlights + endgame_highlights
        all_highlights.sort(key=lambda x: (x.move_number, not x.is_white))
        
        return all_highlights

