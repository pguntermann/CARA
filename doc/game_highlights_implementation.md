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

The game highlights detection system follows a **rule-based service pattern** with **stateless service integration**:

### Component Responsibilities

**HighlightDetector** (`app/services/game_highlights/highlight_detector.py`):
- Stateless service that orchestrates rule evaluation
- Iterates through moves and evaluates all enabled rules
- Skips rules whose `allowed_phases` exclude the current phase
- Applies optional `priority_override` from user settings onto emitted highlights
- Handles post-processing: deduplication, filtering, sorting, limiting
- Manages cross-phase priority adjustments using composer settings
- Groups highlights by game phase (opening, middlegame, endgame)
- Uses shared state dictionary for cross-move tracking

**RuleRegistry** (`app/services/game_highlights/rule_registry.py`):
- Manages all highlight detection rules
- Handles rule discovery and registration from configuration
- Provides enabled/disabled rule filtering
- Receives an effective per-rule config map (catalog defaults + `config.json` + user overrides)

**HighlightRule** (`app/services/game_highlights/base_rule.py`):
- Abstract base class for all highlight rules
- Defines the rule interface (`evaluate()` method)
- Reads `allowed_phases` and `priority_override` from rule config
- Provides configuration support
- Each rule is independent and testable

**Rule catalog** (`app/services/game_highlights/rule_catalog.py`):
- Built-in metadata for every rule (id, display name, description, UI category, default enabled/priority/phases)
- Stable rule IDs match `rule_type` / registry config keys

**GameHighlightRulesService** (`app/services/game_highlight_rules_service.py`):
- Loads/saves sparse user preferences under `user_settings.json` → `game_highlight_rules`
- Merges catalog defaults with per-rule overrides and optional custom priority order
- Builds the registry config passed into `RuleRegistry`
- Exposes composer settings (max per phase/move, cross-phase penalty knobs)

**Manage Game Highlight Rules UI**:
- Controller: `app/controllers/game_highlight_rules_controller.py`
- Dialog: `app/views/dialogs/manage_game_highlight_rules_dialog.py`
- Menu: `Game Analysis → Manage Game Highlight Rules...`
- Lets users enable/disable rules, restrict phases, reorder priority, and edit composition settings

**GameSummaryService** (`app/services/game_summary_service.py`):
- Integrates highlight detection into game summary calculation
- Asks `GameHighlightRulesService` for effective rule config and composer settings
- Creates `RuleRegistry` and `HighlightDetector` instances
- Passes CPL thresholds from `MoveClassificationModel` to detector
- Includes highlights in `GameSummary` object

### Component Interactions

**Highlight Detection Flow**:
1. `GameSummaryService.calculate_summary()` is called with moves and phase boundaries
2. Service loads `ui.panels.detail.summary.highlights` from `config.json` (e.g. default `max_per_phase`)
3. `GameHighlightRulesService.build_registry_config()` merges catalog defaults, optional `config.json` rule entries, and user overrides
4. Service creates `RuleRegistry` with that effective rule config
5. Service creates `HighlightDetector` with:
   - Rule registry instance
   - CPL thresholds from `MoveClassificationModel`
   - Composer settings (`max_per_phase`, `max_per_move`, phase dedupe, cross-phase penalty)
6. Service calls `detect_highlights()` with moves, total moves, and phase boundaries
7. `HighlightDetector` iterates through moves:
   - Creates `RuleContext` for each move (with previous/next moves, material counts, phase info)
   - Gets enabled rules from registry
   - Skips rules not allowed in the current phase
   - Evaluates each rule with move and context
   - Applies `priority_override` when present
   - Collects all highlights from all rules
8. Detector applies post-processing (deduplication, filtering, sorting, limiting)
9. Returns list of `GameHighlight` instances
10. Highlights included in `GameSummary` object
11. UI displays highlights grouped by phase

**Rule Evaluation Flow**:
1. For each move, `HighlightDetector` creates `RuleContext` with:
   - Previous/next move references
   - Material counts from previous move
   - Phase information (opening/middlegame/endgame)
   - Classification thresholds (CPL limits)
   - Shared state dictionary for cross-move tracking
2. Detector gets enabled rules from `RuleRegistry`
3. Rules whose `allowed_phases` exclude the current phase are skipped
4. Each remaining rule's `evaluate()` method is called with move and context
5. Rules return list of `GameHighlight` instances (empty list if no highlight)
6. If the rule has `priority_override`, that value replaces each highlight's priority
7. All highlights collected and passed to post-processing

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

**Built-in defaults** live in `rule_catalog.py` (enabled, display name, description, category, default priority, default phases).

**Optional `config.json` rule entries** under `ui.panels.detail.summary.highlights.rules` can still supply rule-specific algorithm parameters (and legacy name/description/enabled). The factory default for composition limit is:

```
ui.panels.detail.summary.highlights.max_per_phase   # default 7
```

**User overrides** are stored sparsely in `user_settings.json` under `game_highlight_rules`:

- `overrides`: per-rule diffs from catalog defaults (`enabled`, `phases`, …)
- `priority_order`: optional full rule-id order when the user customizes ranking (empty = catalog defaults)
- `composer`: sparse diffs for composition settings (see Configuration)

`GameHighlightRulesService.build_registry_config()` merges catalog → config.json → user overrides into the map consumed by `RuleRegistry`. Each effective rule config may include:

- `enabled`: Boolean to enable/disable the rule
- `allowed_phases`: Subset of `opening` / `middlegame` / `endgame`
- `priority_override`: Integer used when the user has customized priority order
- `name` / `description`: Display metadata
- Rule-specific parameters (varies by rule)

## Processing Pipeline

The highlight detection process is described in the "Component Interactions" section of Architecture. The post-processing steps:

1. **Filter delayed mating sequences**: Suppress individual "missed mate" highlights within delayed mating ranges
2. **Add evaluation swing highlights**: Special handling for evaluation swings (see "Deduplication Logic")
3. **Combine highlights on same move**: Keep up to `max_per_move` highlights per move (selected by priority; default 2)
4. **Group by phase**: Separate highlights into opening, middlegame, endgame
5. **Sort by priority**: Descending priority, then move number for ties
6. **Apply cross-phase priority penalties**: See "Cross-Phase Priority Adjustment"
7. **Deduplicate within each phase**: See "Deduplication Logic" (always enabled)
8. **Limit per phase**: Keep top `max_per_phase` highlights (default 7; overridable via composer / config)
9. **Final output**: Combine highlights from all phases, sort by move number for chronological display

### Cross-Phase Priority Adjustment

To increase variety across phases, the system applies dynamic prioritization when the composer penalty is greater than zero:

- Track which highlight **rule types** appeared in previous phases
- Subtract `cross_phase_penalty` (default 8) from priority for repeats
- Only apply the penalty if the current phase has more than `cross_phase_penalty_min_highlights` candidates (default 7)
- Setting the penalty to 0 disables cross-phase down-ranking

### Deduplication Logic

The system uses multi-level deduplication:

1. **Move-Level Combination**
   - Highlights on the same move (same move_number and is_white) are combined
   - Up to `max_per_move` highlights per move (selected by priority; default 2)
   - Descriptions are merged with ". " separator

2. **Phase-Level Deduplication**
   - Always on (not user-togglable)
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
5. Take top N per phase (`max_per_phase`, default: 7)

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


## Adding New Rules

To add a new highlight rule:

1. **Create rule file** in `app/services/game_highlights/rules/`
   - Inherit from `HighlightRule`
   - Implement `evaluate(move, context) -> List[GameHighlight]`
   - Return empty list if no highlight, or list of `GameHighlight` instances
   - Set `rule_type` on emitted highlights to the stable snake_case rule id

2. **Register rule** in `RuleRegistry._load_rules()`
   - Import the rule class
   - Register with: `self.register_rule(RuleClass(config))`

3. **Add catalog metadata** in `app/services/game_highlights/rule_catalog.py`
   - `BuiltinRuleMeta` with id, display name, description, category, default priority/phases/enabled
   - Required so the Manage dialog and user overrides recognize the rule

4. **Optional `config.json` entry** under `ui.panels.detail.summary.highlights.rules`
   - Only needed for rule-specific algorithm parameters beyond catalog defaults

5. **Set appropriate priority**
   - Higher priority = more interesting/rare
   - Consider existing priority hierarchy
   - Test to ensure appropriate frequency

6. **Consider deduplication**
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
                priority=30,  # Set appropriate priority
                rule_type="my_new_rule",
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

### Factory defaults (`config.json`)

```json
{
  "ui": {
    "panels": {
      "detail": {
        "summary": {
          "highlights": {
            "max_per_phase": 7,
            "rules": {
              "forcing_combination": {
                "some_rule_specific_param": true
              }
            }
          }
        }
      }
    }
  }
}
```

`max_per_phase` in config is the factory default for the composer; user composer overrides win when present.

### User preferences (`user_settings.json` → `game_highlight_rules`)

Sparse storage only (empty objects/lists mean “use defaults”):

```json
{
  "game_highlight_rules": {
    "overrides": {
      "castling": {
        "enabled": false
      },
      "fork": {
        "phases": ["middlegame", "endgame"]
      }
    },
    "priority_order": [],
    "composer": {
      "max_per_phase": 5,
      "max_per_move": 2,
      "cross_phase_penalty": 8,
      "cross_phase_penalty_min_highlights": 7
    }
  }
}
```

Composer defaults (when not overridden): `max_per_phase` 7 (or config value), `max_per_move` 2, `cross_phase_penalty` 8, `cross_phase_penalty_min_highlights` 7. Phase-level dedupe is always on. A `cross_phase_penalty` of 0 disables cross-phase down-ranking.

## Performance Considerations

- Rules are evaluated sequentially per move
- FEN parsing uses python-chess library (efficient)
- Deduplication uses dictionary lookups (O(1) average)
- Sorting is O(n log n) but n is small (typically <50 highlights per phase)
- Cross-phase tracking uses set lookups (O(1))
