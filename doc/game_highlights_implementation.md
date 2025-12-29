# CARA - Game Highlights Detection System

## Overview

The Game Highlights Detection System automatically identifies and highlights key moments and interesting facts from chess games. It uses a rule-based architecture where independent rules evaluate moves and generate highlights based on chess theory, tactical patterns, and positional concepts. The system processes all moves in a game, applies sophisticated deduplication and filtering, and produces a curated list of highlights organized by game phase (Opening, Middlegame, Endgame).

## Purpose

The highlight system serves to:

- Identify critical tactical moments (combinations, missed opportunities, blunders)
- Recognize strategic achievements (bishop pair, pawn breaks, centralization)
- Track game flow (theory departures, momentum shifts, evaluation swings)
- Provide concise summaries of interesting game moments
- Help users quickly understand key aspects of a game without reviewing every move

## Architecture

### Core Components

The highlight system consists of three main components:

- **HighlightDetector** (`app/services/game_highlights/highlight_detector.py`)
  - Main orchestrator that coordinates rule evaluation
  - Handles post-processing: deduplication, filtering, sorting, limiting
  - Manages cross-phase priority adjustments
  - Groups highlights by game phase

- **RuleRegistry** (`app/services/game_highlights/rule_registry.py`)
  - Manages all highlight detection rules
  - Handles rule discovery and registration
  - Provides enabled/disabled rule filtering
  - Loads rules from configuration

- **HighlightRule** (`app/services/game_highlights/base_rule.py`)
  - Abstract base class for all highlight rules
  - Defines the rule interface (evaluate method)
  - Provides configuration support
  - Each rule is independent and testable

### Data Structures

- **GameHighlight** (dataclass)
  - `move_number`: Primary move number for the highlight
  - `is_white`: True if highlight is for white's move, False for black
  - `move_notation`: Display notation (e.g., "12. Nxc3" or "18-19. Rooks were exchanged")
  - `description`: Text description of the highlight
  - `move_number_end`: Optional end move for multi-move highlights
  - `priority`: Integer priority score (higher = more interesting, selected first)
  - `rule_type`: Rule type identifier for deduplication (e.g., "battery", "fork", "decoy")

- **RuleContext** (dataclass)
  - Provides move history (prev_move, next_move, moves list)
  - Contains phase boundaries (opening_end, middlegame_end)
  - Tracks material counts (prev_white_bishops, prev_black_material, etc.)
  - Includes classification thresholds (good_move_max_cpl, mistake_max_cpl)
  - Provides shared_state dictionary for cross-move tracking
  - Contains theory departure tracking (last_book_move_number, theory_departed)

## Rule System

### Rule Interface

All highlight rules inherit from `HighlightRule` and implement the `evaluate()` method:

```python
def evaluate(self, move: MoveData, context: RuleContext) -> List[GameHighlight]:
    """Evaluate move and return highlights."""
    pass
```

Rules are independent and can:

- Return zero, one, or multiple highlights per move
- Access previous/next moves via context
- Use shared_state for cross-move tracking
- Access full move history for complex patterns

### Available Rules

The system includes 44 rules covering various aspects of chess:

**Tactical Rules:**
- ForcingCombinationRule: Detects material sacrifices with forced responses
- TacticalResourceRule: Identifies strong tactical moves (captures, improvements)
- TacticalOpportunityRule: Flags missed tactical opportunities
- TacticalSequenceRule: Detects multi-move tactical sequences
- DefensiveResourceRule: Finds defensive moves when under threat
- DefensiveFortressRule: Identifies defensive fortress formations
- BlunderedPieceRule: Detects blundered queens/rooks
- DelayedMatingRule: Tracks consecutive missed mate opportunities
- ForkRule: Detects fork tactics
- SkewerRule: Detects skewer tactics
- PinRule: Detects pin tactics
- DiscoveredAttackRule: Detects discovered attacks
- BatteryRule: Detects battery formations
- DecoyRule: Detects decoy tactics
- ZwischenzugRule: Detects zwischenzug (in-between moves)
- InterferenceRule: Detects interference tactics
- WindmillRule: Detects windmill combinations
- BackRankWeaknessRule: Detects back rank weaknesses
- ExchangeSacrificeRule: Detects exchange sacrifices
- BreakthroughSacrificeRule: Detects breakthrough sacrifices

**Strategic Rules:**
- BishopPairRule: Detects when bishop pair is secured/gained
- PawnBreakRule: Identifies central pawn breaks
- PawnStormRule: Detects coordinated pawn advances on a flank
- CentralizationRule: Flags piece centralization moves
- PositionalImprovementRule: Recognizes positional improvements
- WeakSquareRule: Detects weak square exploitation
- IsolatedPawnRule: Detects isolated pawn structures
- KnightOutpostRule: Detects knight outposts
- RookLiftRule: Detects rook lift maneuvers
- PieceCoordinationRule: Detects coordinated piece play
- KingActivityRule: Detects active king play
- PawnPromotionThreatRule: Detects pawn promotion threats
- TempoGainRule: Detects tempo gains

**Game Flow Rules:**
- TheoryDepartureRule: Tracks when players leave opening theory
- NoveltyRule: Identifies good moves not in top 3 engine moves
- InitiativeRule: Detects when initiative is seized
- MomentumShiftRule: Flags when advantage switches sides
- EvaluationSwingRule: Tracks large evaluation changes
- PerpetualCheckRule: Detects perpetual check patterns
- ZugzwangRule: Detects zugzwang positions

**Material/Exchange Rules:**
- MaterialImbalanceRule: Detects unusual material trades
- ExchangeSequenceRule: Tracks queen/rook exchanges
- SimplificationRule: Identifies simplification trades
- CastlingRule: Detects castling moves

### Rule Configuration

Rules are configured via config.json under:
```
ui.panels.detail.summary.highlights.rules
```

Each rule can have:
- `enabled`: Boolean to enable/disable the rule
- `name`: Display name for the rule
- `description`: Description of what the rule detects
- Rule-specific parameters (varies by rule)

## Processing Pipeline

### Detection Flow

The highlight detection process follows this sequence:

1. **Initialization**
   - Create RuleRegistry and load all rules from config
   - Initialize HighlightDetector with CPL thresholds
   - Set up shared_state for cross-move tracking
   - Initialize material tracking variables

2. **Rule Evaluation (per move)**
   - Iterate through all moves in the game
   - For each move, create RuleContext with:
     * Previous/next move references
     * Material counts from previous move
     * Phase information
     * Classification thresholds
     * Shared state dictionary
   - Evaluate all enabled rules
   - Collect all highlights from all rules

3. **Post-Processing**
   - Filter delayed mating sequences
   - Add evaluation swing highlights (special handling)
   - Combine highlights on same move (max 2 per move)
   - Group by phase (opening, middlegame, endgame)
   - Sort by priority (descending), then move number
   - Apply cross-phase priority penalties
   - Deduplicate within each phase
   - Limit per phase (default: 10 highlights per phase)

4. **Final Output**
   - Combine highlights from all phases
   - Sort by move number for chronological display

### Cross-Phase Priority Adjustment

To increase variety across phases, the system applies dynamic prioritization:

- Track which highlight patterns appeared in previous phases
- Apply -8 priority penalty to highlights matching previous patterns
- Only apply penalty if >7 highlights available in current phase (MIN_HIGHLIGHTS_FOR_PENALTY = 7)
- This ensures different types of highlights appear in different phases

### Deduplication Logic

The system uses multi-level deduplication:

1. **Move-Level Combination**
   - Highlights on the same move (same move_number and is_white) are combined
   - Maximum 2 highlights per move (selected by priority)
   - Descriptions are merged with ". " separator

2. **Phase-Level Deduplication**
   - Within each phase, track description patterns per side
   - Pattern matching uses primary message (first sentence before period)
   - Maximum 1 occurrence per (side, pattern) per phase
   - Prevents duplicate highlights like "White found a strong tactical resource" appearing twice

3. **Special Filtering**
   - Delayed mating highlights suppress individual "missed mate" highlights
   - Evaluation swing highlights are deduplicated per side/phase/direction
   - Only the largest swing per direction is kept

## Priority System

### Priority Hierarchy

Highlights are prioritized by integer scores (higher = more interesting):

**Tier 1 (50-55): Critical Mistakes and Mates**
- 55: Delayed mating (missed mate 2+ times consecutively)
- 50: Blundered queen/rook, Missed checkmate opportunity

**Tier 2 (40-45): Significant Tactical Events**
- 45: Forcing combination, Momentum shift
- 40: Defensive resource, Tactical resource, Evaluation swing

**Tier 3 (30-35): Strategic and Tactical Moves**
- 35: Tactical opportunity missed
- 32: Bishop pair
- 30: Initiative, Pawn storm, Simplification (queens)

**Tier 4 (20-28): Positional and Opening**
- 28: Novelty (reduced from higher priority)
- 25: Positional improvement, Pawn break, Material imbalance
- 20: Theory departure, Exchange sequence, Simplification (rooks)

**Tier 5 (15): Common Moves**
- 15: Castling, Centralization

### Priority Selection

When selecting highlights:

1. Sort by priority (descending)
2. Then by move number (ascending) for ties
3. Apply cross-phase penalties
4. Deduplicate
5. Take top N per phase (default: 10)

## Classification Thresholds

The system uses CPL (Centipawn Loss) thresholds from MoveClassificationModel:

- `good_move_max_cpl`: Maximum CPL for a "good move" (default: 50)
- `inaccuracy_max_cpl`: Maximum CPL for an "inaccuracy" (default: 100)
- `mistake_max_cpl`: Maximum CPL for a "mistake" (default: 200)

These thresholds are:

- User-configurable via the UI
- Passed to rules via RuleContext
- Used consistently across all rules (no hardcoded values)

Rules use these thresholds to determine:

- Whether a move is "good" (cpl < good_move_max_cpl)
- Whether a move is a "mistake" (cpl > mistake_max_cpl)
- Whether a move is an "inaccuracy" (inaccuracy_max_cpl < cpl <= mistake_max_cpl)

## Shared State

Some rules need to track information across multiple moves:

- **eval_swing_highlights**
  - Tracks largest evaluation swings per side/phase/direction
  - Key: (is_white, phase, direction) -> (swing_value, highlight)
  - Used by EvaluationSwingRule for deduplication

- **missed_mate_tracking**
  - Tracks consecutive missed mate opportunities
  - Key: (is_white, phase) -> (count, first_move, last_move, best_move)
  - Used by DelayedMatingRule to detect delayed mating sequences

- **delayed_mate_created**
  - Set of sides/phases where delayed mating was detected
  - Used to suppress individual "missed mate" highlights

- **delayed_mating_ranges**
  - List of (start_move, end_move, is_white) tuples
  - Used to filter out missed mate highlights within delayed mating ranges

- **pawn_storm_created**
  - Set of (is_white, phase) tuples where pawn storms were detected
  - Prevents duplicate pawn storm highlights

## FEN-Based Positional Analysis

Many rules use FEN (Forsyth-Edwards Notation) for precise positional analysis:

- **FEN Storage**
  - Each move stores fen_white and fen_black
  - Captured during game analysis
  - Serialized in CARAAnalysisTag for persistence

- **Rules Using FEN**
  - PawnBreakRule: Verifies pawn actually moved and advanced
  - CentralizationRule: Checks piece moved from non-central to central square
  - CastlingRule: Verifies castling rights and actual castling
  - BishopPairRule: Counts bishops on board accurately
  - PawnStormRule: Tracks pawn positions across multiple moves

## Integration with GameSummaryService

The highlight system is integrated into GameSummaryService:

1. `GameSummaryService.calculate_summary()` calls highlight detection
2. Creates RuleRegistry with rule configurations
3. Creates HighlightDetector with CPL thresholds from MoveClassificationModel
4. Calls `detect_highlights()` with moves, phase boundaries
5. Highlights are included in GameSummary object
6. UI displays highlights grouped by phase

## Adding New Rules

To add a new highlight rule:

1. **Create rule file** in `app/services/game_highlights/rules/`
   - Inherit from `HighlightRule`
   - Implement `evaluate(move, context) -> List[GameHighlight]`
   - Return empty list if no highlight, or list of `GameHighlight` instances

2. **Register rule** in `RuleRegistry._load_rules()`
   - Import the rule class
   - Register with: `self.register_rule(RuleClass(config))`

3. **Add rule configuration** to config.json
   - Under `ui.panels.detail.summary.highlights.rules`
   - Include enabled, name, description, and rule-specific params

4. **Set appropriate priority**
   - Higher priority = more interesting/rare
   - Consider existing priority hierarchy
   - Test to ensure appropriate frequency

5. **Consider deduplication**
   - Use unique description patterns
   - Consider if rule should be limited per phase
   - Check for conflicts with existing rules

Example rule structure:

```python
class MyNewRule(HighlightRule):
    def evaluate(self, move, context: RuleContext) -> List[GameHighlight]:
        highlights = []
        # Rule logic here
        if condition_met:
            highlights.append(GameHighlight(
                move_number=move.move_number,
                is_white=True,
                move_notation=f"{move.move_number}. {move.white_move}",
                description="Description text",
                priority=30  # Set appropriate priority
            ))
        return highlights
```

## Best Practices

### Rule Design

- Keep rules independent and focused on one concept
- Use RuleContext for move history, not global state
- Access CPL thresholds from context, not hardcoded values
- Use FEN for positional analysis when available
- Check for equal material exchanges to avoid false positives

### Priority Setting

- Rare, critical events: 40-55
- Common tactical/strategic: 25-35
- Positional/opening: 15-25
- Very common moves: 10-15

### Description Patterns

- Use consistent phrasing for pattern matching
- Primary message (first sentence) should be unique
- Consider cross-phase variety when writing descriptions

### Testing

- Test with various game types (tactical, positional, endgame)
- Verify deduplication works correctly
- Check priority ordering
- Ensure no false positives from simple exchanges

## Configuration

The highlight system is configured in config.json:

```json
{
  "ui": {
    "panels": {
      "detail": {
        "summary": {
          "highlights": {
            "highlights_per_phase_limit": 10,
            "rules": {
              "forcing_combination": {
                "enabled": true,
                "name": "Forcing Combination",
                "description": "Detects material sacrifices with forced responses"
              }
            }
          }
        }
      }
    }
  }
}
```

## Performance Considerations

- Rules are evaluated sequentially per move
- FEN parsing uses python-chess library (efficient)
- Deduplication uses dictionary lookups (O(1) average)
- Sorting is O(n log n) but n is small (typically <50 highlights per phase)
- Cross-phase tracking uses set lookups (O(1))
