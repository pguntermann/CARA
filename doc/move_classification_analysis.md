# Move Classification & Analysis System

## Overview

The move classification system evaluates chess moves and assigns quality assessments based on centipawn loss (CPL), evaluation changes, material sacrifice, and tactical opportunities. It provides classifications such as "Best Move", "Good Move", "Inaccuracy", "Mistake", "Blunder", "Brilliant", and "Miss".

## Architecture

The move classification system follows a stateless service pattern with a configuration model:

- **MoveAnalysisService**: Stateless utility class providing pure calculation functions (all methods are static)
  - No instance state; all methods are `@staticmethod`
  - Provides CPL calculation, move assessment, classification, and formatting functions
  - Designed for reusability and testability without UI dependencies

- **MoveClassificationModel**: QObject-based model holding configurable classification thresholds
  - Stores thresholds for move quality assessment (good_move_max_cpl, inaccuracy_max_cpl, etc.)
  - Stores brilliancy criteria (min_eval_swing, min_material_sacrifice, etc.)
  - Emits `settings_changed` signal when thresholds are modified
  - Can be initialized from `config.json` or modified at runtime

- **Integration Pattern**: Analysis services use MoveAnalysisService statically during game analysis
  - `GameAnalysisEngineService` calls static methods after engine evaluation
  - `BulkAnalysisService` uses the same static methods for batch processing
  - Both services pass `MoveClassificationModel` settings to classification functions
  - Classification happens after engine analysis completes (no additional engine calls)

## Centipawn Loss (CPL) Calculation

### Basic CPL

CPL measures how much evaluation was lost by playing a move instead of the best move:

```python
CPL = |eval_after_best_move - eval_after_played_move|
```

If `eval_after_best_move` is not available, falls back to:
- White moves: `|eval_before - eval_after|`
- Black moves: `|eval_after - eval_before|`

### CPL for Mate Positions

Mate positions require special handling:

**Both positions are mate**:
- If checkmate achieved (`mate_moves_after == 0`): CPL = 0
- If same side winning: CPL based on mate distance change
  - Closer to mate (good): `abs(distance_change) * 50`
  - Further from mate (bad): `distance_change * 100`
- If mate switched sides: Use evaluation difference

**Only position after is mate**:
- If creating mate: CPL = 0 (best move)
- If allowing mate: CPL = evaluation difference (blunder)

**Only position before is mate**:
- CPL = evaluation change (escaped mate or evaluation changed)

### CPL for PV2/PV3 Moves

For alternative principal variations:
```python
CPL = |pv_score - eval_after_played_move|
```

## Move Quality Assessment

### Classification Hierarchy

Moves are classified in this order (first match wins):

1. **Brilliant**: Meets brilliancy criteria
2. **Best Move**: Played move matches best move
3. **Miss**: Failed to capitalize on tactical opportunity
4. **Good Move**: CPL ≤ `good_move_max_cpl` (default: 50)
5. **Inaccuracy**: CPL ≤ `inaccuracy_max_cpl` (default: 100)
6. **Mistake**: CPL ≤ `mistake_max_cpl` (default: 200)
7. **Blunder**: CPL > `mistake_max_cpl`

### Classification Thresholds

Thresholds are configurable via `MoveClassificationModel`:

- `good_move_max_cpl`: Maximum CPL for "Good Move" (default: 50)
- `inaccuracy_max_cpl`: Maximum CPL for "Inaccuracy" (default: 100)
- `mistake_max_cpl`: Maximum CPL for "Mistake" (default: 200)

Thresholds can be loaded from `config.json` under `game_analysis.move_classification`.

## Brilliant Move Detection

A move is classified as "Brilliant" if it meets all criteria:

1. **Material sacrifice**: Must sacrifice at least `min_material_sacrifice` centipawns (default: 100)
2. **Evaluation swing**: Must improve evaluation by at least `min_eval_swing` centipawns (default: 200)
   - White moves: `eval_after - eval_before ≥ min_eval_swing`
   - Black moves: `eval_before - eval_after ≥ min_eval_swing`
3. **Not already winning** (if `exclude_already_winning` is True):
   - White moves: `eval_before ≤ max_eval_before` (default: 500)
   - Black moves: `eval_before ≥ -max_eval_before` (default: -500)

### Material Sacrifice Calculation

Material sacrifice is calculated in two ways:

1. **Direct sacrifice**: Move itself loses material (piece captured)
2. **Forced sacrifice**: Move leaves piece en prise, opponent captures it within `lookahead_plies` (default: 3)

Material sacrifice is measured in centipawns using piece values:
- Pawn: 100
- Knight/Bishop: 300
- Rook: 500
- Queen: 900

A move is NOT a sacrifice if:
- The move itself captures material (gains material)
- The opponent's capture is unrelated to the current move

## Miss Detection

A move is classified as "Miss" if:

1. **Significant CPL**: CPL ≥ 100 centipawns
2. **Tactical opportunity**: Best move is a capture or checkmate
3. **Not tactical**: Played move is NOT a capture or checkmate
4. **Significant error**: Would be classified as Inaccuracy (CPL ≥ 150) or Mistake/Blunder

A miss indicates the player failed to capitalize on a tactical opportunity (capture or mate threat).

## Move Normalization

Moves are normalized for comparison by:
- Removing check (`+`) and checkmate (`#`) symbols
- Converting to lowercase
- Trimming whitespace

This ensures moves like `"Nf3+"` and `"nf3"` are considered equal.

## Top 3 Move Detection

`is_move_in_top3()` checks if played move matches any of the top 3 engine moves (best move, PV2, PV3):

- Normalizes all moves before comparison
- Returns `True` if played move matches any top 3 move

## Evaluation Formatting

### Format Evaluation

`format_evaluation()` formats evaluation for display:

- **Mate positions**: `"M{N}"` (white winning) or `"-M{N}"` (black winning)
- **Checkmate**: `"M0"` or `"-M0"`
- **Normal positions**: `"+X.X"` or `"-X.X"` (pawns with one decimal)

### Format CPL

`format_cpl()` formats CPL as integer string (e.g., `"150"`).

## Configuration

### MoveClassificationModel

`MoveClassificationModel` (`app/models/move_classification_model.py`) holds settings:

**Assessment thresholds**:
- `good_move_max_cpl`: int (default: 50)
- `inaccuracy_max_cpl`: int (default: 100)
- `mistake_max_cpl`: int (default: 200)

**Brilliant criteria**:
- `min_eval_swing`: int (default: 50)
- `min_material_sacrifice`: int (default: 300)
- `max_eval_before`: int (default: 500)
- `exclude_already_winning`: bool (default: True)
- `material_sacrifice_lookahead_plies`: int (default: 3)

**Signals**:
- `settings_changed`: Emitted when any setting changes

### Config.json Structure

Settings can be loaded from `config.json`:

```json
{
  "game_analysis": {
    "move_classification": {
      "good_move_max_cpl": 50,
      "inaccuracy_max_cpl": 100,
      "mistake_max_cpl": 200,
      "min_eval_swing": 200,
      "min_material_sacrifice": 100,
      "max_eval_before": 500,
      "exclude_already_winning": true,
      "material_sacrifice_lookahead_plies": 3
    }
  }
}
```

## Integration with Game Analysis

### During Game Analysis

`GameAnalysisEngineService` and `BulkAnalysisService` use `MoveAnalysisService` to:

1. Calculate CPL for each move
2. Detect book moves
3. Calculate material sacrifice
4. Assess move quality
5. Store classification in `MoveData`

### MoveData Structure

Each move in `MovesListModel` includes:

- `cpl`: Centipawn loss
- `assessment`: Classification string ("Best Move", "Good Move", etc.)
- `eval_before`: Evaluation before move
- `eval_after`: Evaluation after move
- `best_move_san`: Best move suggestion
- `material_sacrifice`: Material sacrifice in centipawns

## Code Location

Implementation files:

- `app/services/move_analysis_service.py`: Core calculation logic
- `app/models/move_classification_model.py`: Classification settings model
- `app/services/game_analysis_engine_service.py`: Uses classification during analysis
- `app/services/bulk_analysis_service.py`: Uses classification for bulk analysis

## Best Practices

### CPL Calculation

- Prefer `eval_after_best_move` over `eval_before` for accuracy
- Handle mate positions separately from normal evaluations
- Account for perspective (white vs. black) when calculating losses

### Classification

- Check brilliancy before other classifications
- Check "Best Move" before CPL-based classifications
- Check "Miss" before Mistake/Blunder (but after Best Move)

### Material Sacrifice

- Use lookahead to detect forced sacrifices
- Distinguish between direct and forced sacrifices
- Don't count captures as sacrifices

### Performance

- Classification calculations are lightweight (no engine calls)
- Can be performed after engine analysis completes
- Suitable for real-time display during analysis

