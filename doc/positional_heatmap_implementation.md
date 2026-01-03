# Positional Heatmap System Implementation

## Overview

The positional heatmap system provides visual feedback on chess positions by evaluating pieces based on positional factors. It uses a rule-based architecture where multiple independent rules evaluate different positional aspects, and their scores are aggregated and displayed as colored overlays on the chessboard.

## Architecture

The positional heatmap system follows a **rule-based service pattern** with **Model-Controller-Service** integration:

### Component Responsibilities

**PositionalAnalyzer** (`app/services/positional_heatmap/positional_analyzer.py`):
- Evaluates positions by running all enabled rules from `RuleRegistry`
- Aggregates rule scores using `ScoreAggregator` with weighted summation and normalization
- Caches results for performance (FIFO cache with configurable size limit)
- Provides detailed evaluation breakdowns for debugging
- Isolates errors: one failing rule doesn't break the entire system

**RuleRegistry** (`app/services/positional_heatmap/rule_registry.py`):
- Loads and registers all available rules from configuration
- Provides access to enabled/disabled rules
- Manages rule lookup by name

**ScoreAggregator** (`app/services/positional_heatmap/score_aggregator.py`):
- Combines scores from multiple rules using weighted summation
- Applies normalization (hard clamping or soft tanh scaling)
- Ensures scores stay within configured range (default: -100 to +100)

**PositionalRule** (`app/services/positional_heatmap/base_rule.py`):
- Abstract base class defining the rule interface
- Each rule implements `evaluate()` method returning `Dict[chess.Square, float]`
- Rules are independent, testable, and configurable
- Supports per-rule weights and enable/disable flags

**PositionalHeatmapModel** (`app/models/positional_heatmap_model.py`):
- Holds current scores and visibility state
- Emits `scores_changed` signal when scores update
- Emits `visibility_changed` signal when visibility toggles
- Analyzes positions from both perspectives (White and Black) and combines scores

**PositionalHeatmapController** (`app/controllers/positional_heatmap_controller.py`):
- Initializes `RuleRegistry`, `PositionalAnalyzer`, and `PositionalHeatmapModel`
- Connects to `BoardModel` position changes
- Handles visibility toggling
- Clears cache when position changes or visibility is toggled

### Component Interactions

**Initialization Flow**:
1. `PositionalHeatmapController` creates `RuleRegistry` from configuration
2. Controller creates `PositionalAnalyzer` with the registry
3. Controller creates `PositionalHeatmapModel` with the analyzer
4. Controller connects to `BoardModel.position_changed` signal

**Position Evaluation Flow**:
1. `BoardModel` emits `position_changed` signal
2. `PositionalHeatmapController` receives signal and clears analyzer cache
3. Controller calls `model.update_position()` with current board
4. Model calls `analyzer.analyze_position()` for both White and Black perspectives
5. Analyzer retrieves enabled rules from registry, evaluates each rule, aggregates scores
6. Model combines perspective-specific scores (White pieces use White perspective, Black pieces use Black perspective)
7. Model emits `scores_changed` signal with combined scores
8. View observes signal and updates visual overlay

**Visibility Toggle Flow**:
1. User toggles visibility via controller
2. Controller calls `model.set_visible()`
3. Model emits `visibility_changed` signal
4. If enabling, controller clears cache and triggers position evaluation
5. View observes signal and shows/hides overlay

## Rule System

### Rule Interface

All rules inherit from `PositionalRule` and implement:

```python
def evaluate(self, board: chess.Board, perspective: chess.Color) -> Dict[chess.Square, float]:
    """Evaluate position and return scores for each square.
    
    Args:
        board: Current chess position (python-chess Board).
        perspective: Color to evaluate from (chess.WHITE or chess.BLACK).
                    Positive scores favor this color, negative scores favor opponent.
    
    Returns:
        Dictionary mapping square -> score (typically -100 to +100).
        Only include squares that have a non-zero score.
        Scores should be from the perspective's viewpoint.
    """
```

### Available Rules

The system includes 9 built-in rules:

1. **PassedPawnRule**: Evaluates passed pawns with bonuses scaled by rank advancement
2. **BackwardPawnRule**: Identifies backward pawns (pawns that cannot advance safely)
3. **IsolatedPawnRule**: Detects isolated pawns (no friendly pawns on adjacent files)
4. **DoubledPawnRule**: Identifies doubled pawns (multiple pawns on same file)
5. **KingSafetyRule**: Evaluates king safety based on pawn shield and piece attacks
6. **WeakSquareRule**: Detects weak squares (attacked but undefended)
7. **PieceActivityRule**: Evaluates piece activity and mobility
8. **UndevelopedPieceRule**: Identifies undeveloped pieces (still on starting squares)
9. **OutpostSquareRule**: Evaluates outpost squares (squares controlled by knights/bishops)

### Rule Configuration

Rules are configured in `config.json` under `ui.positional_heatmap.rules`:

```json
{
  "rules": {
    "passed_pawn": {
      "enabled": true,
      "weight": 1.0,
      "score": 20.0
    },
    "weak_square": {
      "enabled": true,
      "weight": 1.0,
      "score": -8.0,
      "undefended_penalty": -2.0
    }
  }
}
```

Each rule can have:
- `enabled`: Boolean to enable/disable the rule
- `weight`: Float multiplier for rule scores (default: 1.0)
- Rule-specific parameters (e.g., `score`, `undefended_penalty`)

## Score Aggregation

### Weighted Summation

Scores from all enabled rules are combined using weighted summation:

```
aggregated_score[square] = Σ(rule_score[square] × rule_weight)
```

Each rule's contribution is multiplied by its weight before summation.

### Normalization

After aggregation, scores are normalized to stay within the configured range (default: -100 to +100). Two normalization methods are available:

**Hard Clamping** (default):
- Simply clamps scores to min/max range
- Formula: `clamped = max(min_score, min(max_score, raw_score))`
- Can distort relative importance of scores

**Soft Scaling** (tanh-based):
- Uses hyperbolic tangent to preserve proportionality
- Formula: `scaled = tanh(raw_score / scale_factor) × max_score`
- Better preserves relative importance while keeping scores in range
- Configured via `aggregation.soft_scale_factor` (default: 50.0)

## Caching

The system uses a FIFO (First-In-First-Out) cache to avoid re-evaluating identical positions:

- Cache key: `"{fen}_{perspective}"`
- Cache size limit: Configurable via `max_cache_size` (default: 1000)
- Cache eviction: When limit reached, oldest entry is removed
- Cache can be disabled via `cache_enabled` configuration

Cache is cleared when:
- Position changes (controller receives `BoardModel.position_changed` signal)
- Visibility is toggled (to ensure fresh evaluation with updated rules)

## View Integration

**PositionalHeatmapOverlay** (`app/views/positional_heatmap_overlay.py`):
- Transparent overlay widget that displays heatmap on chessboard
- Observes `PositionalHeatmapModel` signals (`scores_changed`, `visibility_changed`)
- Renders circular radial gradients for each scored square
- Color mapping:
  - Positive scores: Green (good for the piece)
  - Small negative scores (above threshold): Yellow (neutral)
  - Large negative scores: Red (bad for the piece)
- Gradient opacity and radius are configurable

## Configuration

Configuration is located in `config.json` under `ui.positional_heatmap`:

```json
{
  "positional_heatmap": {
    "enabled": true,
    "cache_enabled": true,
    "max_cache_size": 1000,
    "score_range": [-100, 100],
    "aggregation": {
      "normalize": true,
      "normalization_method": "soft",
      "soft_scale_factor": 50.0
    },
    "colors": {
      "positive": [0, 255, 0],
      "negative": [255, 0, 0],
      "neutral": [255, 255, 0],
      "neutral_threshold": -5.0,
      "opacity": 0.9,
      "gradient_radius_ratio": 0.85,
      "gradient_center_ratio": 0.3
    },
    "rules": {
      "passed_pawn": { ... },
      "weak_square": { ... }
    }
  }
}
```

## Adding New Rules

To add a new positional evaluation rule:

1. **Create rule class** in `app/services/positional_heatmap/rules/`:
   ```python
   from app.services.positional_heatmap.base_rule import PositionalRule
   
   class NewRule(PositionalRule):
       def evaluate(self, board: chess.Board, perspective: chess.Color) -> Dict[chess.Square, float]:
           scores: Dict[chess.Square, float] = {}
           # Evaluation logic here
           return scores
   ```

2. **Register in RuleRegistry** (`app/services/positional_heatmap/rule_registry.py`):
   - Import the rule class in `_load_rules()`
   - Add registration logic:
     ```python
     if 'new_rule' in rules_config:
         self.register_rule(NewRule(rules_config.get('new_rule', {})))
     ```

3. **Add configuration** in `config.json`:
   ```json
   {
     "rules": {
       "new_rule": {
         "enabled": true,
         "weight": 1.0,
         "name": "New Rule",
         "description": "Description of what this rule evaluates"
       }
     }
   }
   ```

4. **Update `__init__.py`** in `app/services/positional_heatmap/rules/` if needed for imports

## Score Interpretation

Scores are evaluated from each piece's own perspective:
- White pieces: Scored from White's perspective
- Black pieces: Scored from Black's perspective

Score meaning:
- **Positive scores**: Good for the piece (displayed in green)
- **Negative scores**: Bad for the piece (displayed in red or yellow)
- **Zero scores**: Not evaluated by any rule (no overlay shown)

The overlay only displays scores for squares that contain pieces.

## Error Handling

The system uses error isolation: if one rule fails during evaluation, it is skipped and other rules continue to run. This ensures that a bug in one rule doesn't break the entire heatmap system.

## Code Location

Implementation files:

- `app/services/positional_heatmap/positional_analyzer.py`: Main analyzer service
- `app/services/positional_heatmap/rule_registry.py`: Rule management
- `app/services/positional_heatmap/score_aggregator.py`: Score aggregation logic
- `app/services/positional_heatmap/base_rule.py`: Rule base class
- `app/services/positional_heatmap/rules/`: Individual rule implementations
- `app/models/positional_heatmap_model.py`: Model for state management
- `app/controllers/positional_heatmap_controller.py`: Controller orchestration
- `app/views/positional_heatmap_overlay.py`: Visual overlay rendering

