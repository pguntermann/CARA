# CARA - Player Statistics Implementation

## Overview

The Player Statistics feature aggregates performance statistics for a player across multiple games, calculating averages, phase-specific metrics, opening usage patterns, and error patterns. The system processes games in parallel using `ProcessPoolExecutor` for CPU-bound computation, significantly improving performance for large game sets. Statistics include accuracy, estimated ELO, phase-specific performance (opening, middlegame, endgame), and opening usage analysis.

## Architecture

The player statistics system follows a **Service-Controller-Worker** pattern with **parallel processing**:

### Component Responsibilities

**PlayerStatsService** (`app/services/player_stats_service.py`):
- Aggregates statistics across multiple games using parallel processing
- Processes games in parallel using `ProcessPoolExecutor` for CPU-bound computation
- Calculates per-game summaries via `GameSummaryService`
- Aggregates phase statistics, accuracy values, and opening usage
- Returns both aggregated statistics and individual game summaries
- Supports progress reporting via callback function

**PlayerStatsController** (`app/controllers/player_stats_controller.py`):
- Orchestrates player statistics calculation
- Manages `PlayerStatsService` and `ErrorPatternService`
- Handles synchronous calculation flow (for non-threaded contexts)
- Coordinates with `DatabaseController` for game retrieval

**PlayerStatsCalculationWorker** (`app/views/detail_player_stats_view.py`):
- QThread worker for asynchronous statistics calculation
- Manages progress reporting via signals
- Handles cancellation support
- Emits results via Qt signals for UI updates

**ErrorPatternService** (`app/services/error_pattern_service.py`):
- Detects error patterns in player performance
- Uses aggregated statistics and game summaries
- Identifies phase-specific issues, tactical misses, opening errors, etc.

### Component Interactions

**Statistics Calculation Flow**:
1. User requests player statistics (via UI or controller)
2. Controller/Worker retrieves player games from databases
3. Service filters analyzed games
4. Service processes games in parallel using `ProcessPoolExecutor`
5. Each game is processed independently:
   - Extracts moves from PGN (via analysis data storage)
   - Calculates game summary using `GameSummaryService`
   - Returns statistics and summary
6. Service aggregates results from all games
7. Service calculates opening usage and CPL patterns
8. Service returns aggregated stats and game summaries
9. Error pattern detection uses returned summaries (no recalculation)
10. Results displayed in UI

**Parallel Processing Flow**:
1. Service calculates optimal worker count: `max(1, os.cpu_count() - 2)`
2. Creates `ProcessPoolExecutor` with calculated worker count
3. Submits all games for parallel processing
4. Each process:
   - Loads analysis data from PGN tag
   - Creates `GameSummaryService` instance
   - Calculates game summary (includes formula evaluation via asteval)
   - Returns statistics dictionary
5. Main thread collects results as they complete (using `as_completed()`)
6. Progress callback updates UI as games finish
7. Results aggregated sequentially after all games complete

**Progress Reporting Flow**:
1. Worker thread defines progress callback function
2. Callback emits Qt signals for UI updates
3. Service calls callback as games complete (from main worker thread)
4. Progress calculated as: `50 + (completed / total_games) * 40`
5. Status message: `"Analyzing game {completed}/{total_games}..."`
6. UI updates progress bar and status text

## Parallel Processing Architecture

### Why ProcessPoolExecutor?

The player statistics processing is **CPU-bound**:
- Each game requires extensive computation (formula evaluation, statistics calculation)
- `GameSummaryService.calculate_summary()` performs CPU-intensive work:
  - Iterates through all moves
  - Calculates phase boundaries
  - Evaluates formulas using `asteval` (Python AST evaluation)
  - Aggregates statistics
- Python's Global Interpreter Lock (GIL) limits `ThreadPoolExecutor` effectiveness
- `ProcessPoolExecutor` bypasses GIL by using separate processes

### Worker Process Count

The system reserves CPU cores for UI responsiveness:
- Calculates: `max_workers = max(1, os.cpu_count() - 2)`
- Reserves 1-2 cores for UI and system operations
- Ensures UI remains responsive during processing
- Falls back to 1 worker if CPU count detection fails

### Process Isolation

Each worker process:
- Receives minimal data: PGN string, game metadata, player name, config dict
- Creates its own `GameSummaryService` instance
- Processes game independently
- Returns results dictionary (no shared state)
- Handles errors gracefully (returns `None` to skip failed games)

### Data Flow

**Input to Process**:
- `game_pgn`: PGN string (contains analysis data in tags)
- `game_result`: Game result string
- `game_white`, `game_black`: Player names
- `game_eco`: ECO code
- `player_name`: Player to analyze
- `config`: Configuration dictionary

**Output from Process**:
- Dictionary containing:
  - Player statistics (accuracy, ELO, phase stats)
  - Opening information (ECO, name, CPL)
  - Move collections for aggregation
  - Full `GameSummary` object for error pattern detection

## Statistics Calculation

### Per-Game Processing

For each game, the system:

1. **Extracts Moves**:
   - Loads analysis data from `CARAAnalysisData` PGN tag
   - Falls back to PGN parsing if tag missing (rare, as games must be analyzed)
   - Returns `None` if moves cannot be extracted (game skipped)

2. **Calculates Game Summary**:
   - Creates `GameSummaryService` instance with config
   - Calls `calculate_summary()` with moves and game result
   - Returns `GameSummary` object with:
     - White and black player statistics
     - Phase statistics (opening, middlegame, endgame)
     - Phase boundaries
     - Critical moves
     - Evaluation data
     - Game highlights

3. **Extracts Player Statistics**:
   - Determines if player is white or black
   - Extracts relevant statistics from `GameSummary`
   - Calculates opening CPL for opening usage analysis
   - Identifies opening ECO and name

### Aggregation Process

After parallel processing completes:

1. **Result Collection**:
   - Collects all successful game results
   - Extracts game summaries for error pattern detection
   - Filters out failed games (`None` results)

2. **Statistics Aggregation**:
   - **Win/Loss/Draw**: Counts results based on player color
   - **ELO and Accuracy**: Averages per-game values
   - **Phase Accuracies**: Averages per-game phase accuracies
   - **Phase CPL**: Weighted average (weighted by moves in phase)
   - **Move Classifications**: Sums counts across all games
   - **Opening Usage**: Counts openings and calculates average CPL per opening

3. **Overall Statistics**:
   - Determines majority color (white vs black)
   - Aggregates all moves for overall statistics
   - Calculates aggregated `PlayerStatistics` using `GameSummaryService`
   - Overrides ELO and accuracy with averaged values

### Formula Evaluation

The system uses `asteval` for configurable formula evaluation:

**Accuracy Formula** (`_evaluate_accuracy_formula()`):
- Default: `max(5.0, min(100.0, 100.0 - (average_cpl / 3.5)))`
- Configurable via `config.json` → `game_analysis.accuracy_formula.formula`
- Evaluated per-game using game-specific variables

**ELO Formula** (`_evaluate_elo_formula()`):
- Default: `max(0, int(2800 - (average_cpl * 8.5) - ((blunder_rate * 50 + mistake_rate * 20) * 40)))`
- Configurable via `config.json` → `game_analysis.elo_estimation.formula`
- Evaluated per-game using game-specific variables

**Phase Accuracy Formulas** (`_evaluate_phase_accuracy_formula()`):
- Phase-specific formulas for opening, middlegame, endgame
- Falls back to overall accuracy formula if not configured
- Uses phase-specific CPL values and overall game context

All formulas are evaluated using `asteval.Interpreter()` which:
- Parses formula strings safely (no arbitrary code execution)
- Supports built-in functions: `min`, `max`, `abs`, `int`, `not`
- Accesses variables from kwargs (CPL values, move counts, etc.)
- Handles errors gracefully (returns error value on failure)

## Opening Usage Analysis

The system tracks opening usage and performance:

1. **Opening Identification**:
   - Scans moves in reverse to find last non-"*" opening name
   - Falls back to game ECO if no move-level opening found
   - Tracks opening as `(ECO, opening_name)` tuple

2. **Opening CPL Calculation**:
   - Collects CPL values from all opening phase moves
   - Calculates per-game average CPL (capped at 500)
   - Averages per-game averages for overall opening CPL

3. **Opening Statistics**:
   - Counts games per opening
   - Calculates average CPL per opening
   - Identifies top 3 most played openings
   - Identifies top 3 worst accuracy openings (highest CPL)
   - Identifies top 3 best accuracy openings (lowest CPL)

## Error Pattern Detection

After statistics aggregation:

1. **Uses Pre-calculated Summaries**:
   - Game summaries are returned from `aggregate_player_statistics()`
   - No recalculation needed (eliminates duplicate processing)
   - Summaries passed directly to `ErrorPatternService`

2. **Pattern Detection**:
   - Phase-specific blunder patterns
   - Tactical miss patterns
   - Opening-specific error patterns
   - High CPL patterns
   - Missed top 3 move patterns
   - Conversion issues (problems in winning positions)

## Progress Reporting

### Progress Callback Pattern

The service supports optional progress callbacks:

```python
def progress_callback(completed: int, status: str) -> None:
    # Update UI progress
    progress_percent = completed  # 50-90 range
    status_message = status  # "Analyzing game X/Y..."
```

### Progress Calculation

- **Range**: 50-90% (aggregation phase)
- **Formula**: `50 + int((completed / total_games) * 40)`
- **Updates**: As each game completes (out of order)
- **Status**: `"Analyzing game {completed}/{total_games}..."`

### Worker Thread Integration

The `PlayerStatsCalculationWorker`:
- Defines progress callback that emits Qt signals
- Connects callback to service method
- Receives updates from main worker thread (not subprocesses)
- Updates UI via `progress_update` signal

## Error Handling

### Per-Game Errors

- Individual game processing errors don't crash the batch
- Failed games return `None` and are skipped
- Errors logged to stderr with traceback
- Processing continues for remaining games

### Process Errors

- Process creation failures handled by `ProcessPoolExecutor`
- Individual process exceptions caught and logged
- Failed futures return `None` and are skipped
- Main thread continues collecting other results

### Validation

- Empty game lists return `(None, [])`
- No analyzed games return `(None, [])`
- No valid results return `(None, [])`
- Controllers handle `None` results gracefully

## Configuration

Player statistics use configuration from `config.json`:

```json
{
  "game_analysis": {
    "accuracy_formula": {
      "formula": "max(5.0, min(100.0, 100.0 - (average_cpl / 3.5)))",
      "value_on_error": 0.0
    },
    "elo_estimation": {
      "formula": "max(0, int(2800 - (average_cpl * 8.5) - ((blunder_rate * 50 + mistake_rate * 20) * 40)))",
      "value_on_error": 0
    },
    "phase_accuracy_formulas": {
      "opening": { "formula": "...", "value_on_error": 0.0 },
      "middlegame": { "formula": "...", "value_on_error": 0.0 },
      "endgame": { "formula": "...", "value_on_error": 0.0 }
    }
  },
  "resources": {
    "opening_repeat_indicator": "*"
  }
}
```

## Performance Characteristics

### Parallel Processing Benefits

- **Speedup**: Near-linear scaling with CPU cores (for CPU-bound work)
- **UI Responsiveness**: Reserved cores keep UI responsive
- **Scalability**: Handles large game sets efficiently (100+ games)

### Memory Considerations

- Each process loads config and creates service instances
- Game summaries stored in memory until aggregation completes
- Memory usage scales with number of games and move counts

### CPU Usage

- Uses `os.cpu_count() - 2` processes by default
- Reserves cores for UI and system operations
- Processes run independently (no shared state)

## Code Locations

- **Service**: `app/services/player_stats_service.py`
  - `PlayerStatsService`: Main service class
  - `_process_game_for_stats()`: Top-level helper for parallel processing
  - `AggregatedPlayerStats`: Result dataclass

- **Controller**: `app/controllers/player_stats_controller.py`
  - `PlayerStatsController`: Orchestration layer

- **Worker**: `app/views/detail_player_stats_view.py`
  - `PlayerStatsCalculationWorker`: QThread worker for async processing

- **Error Patterns**: `app/services/error_pattern_service.py`
  - `ErrorPatternService`: Pattern detection

- **Game Summary**: `app/services/game_summary_service.py`
  - `GameSummaryService`: Statistics calculation
  - `GameSummary`: Result dataclass

- **Configuration**: `app/config/config.json`
  - `game_analysis`: Formula configuration
  - `resources`: Opening repeat indicator

## Best Practices

### Parallel Processing

- Always use `ProcessPoolExecutor` for CPU-bound work
- Reserve cores for UI (1-2 cores minimum)
- Handle per-game errors gracefully (don't crash batch)
- Use `as_completed()` for progress tracking

### Progress Reporting

- Emit progress from main thread (not subprocesses)
- Update frequently for better UX
- Handle cancellation checks in callback
- Use consistent progress ranges (50-90% for aggregation)

### Error Handling

- Log errors but continue processing
- Return `None` for failed games (skip gracefully)
- Validate inputs before processing
- Handle empty result sets

### Performance

- Process games in parallel (not sequentially)
- Return summaries to avoid recalculation
- Use batch aggregation (not per-game updates)
- Cache config in service instances

## Integration Points

### Database Model

- Retrieves games via `DatabaseController`
- Filters analyzed games (`game.analyzed == True`)
- Uses `GameData` instances for game metadata

### Game Summary Service

- Reuses `GameSummaryService` for statistics calculation
- Each process creates its own service instance
- Service is stateless (safe for parallel processing)

### Error Pattern Service

- Receives pre-calculated game summaries
- No need to recalculate summaries
- Uses aggregated statistics for pattern detection

### UI Integration

- Worker thread emits signals for UI updates
- Progress updates via `progress_update` signal
- Results via `stats_ready` signal
- Errors via `stats_unavailable` signal

