# Bulk Operations System

## Overview

The bulk operations system provides efficient batch processing of games in databases. All operations follow a common pattern: iterate through games, apply transformations, collect updates, and batch-update the model with a single signal for performance.

## Architecture

The bulk operations system follows a Service-Controller-Model pattern consistent with the application's architecture:

- **Services**: `BulkPlanService` (ordered header/clean plan in one pass), `BulkReplaceService` (Smart Update Result/ECO), plus analysis/cleaning helpers
- **Controllers**: Orchestrate operations, handle UI concerns (progress, cancellation), and coordinate with models
- **Models**: Store game data; operations update `DatabaseModel` via batch updates

### Component Structure

Each bulk operation consists of:
- A **Service** class that implements the core operation logic
- A **Controller** class that orchestrates the operation, handles progress reporting, and manages UI integration
- Integration with `DatabaseModel` for efficient batch updates

### Common Pattern

Header-tag and clean steps share a **single pass** over games:

1. **Filter games**: Select games to process (all games or selected indices)
2. **Process each game once**: Parse PGN, apply the ordered plan in sequence, regenerate PGN
3. **Collect updates**: Build list of modified games
4. **Batch update**: Call `database.batch_update_games()` once with all modified games
5. **Progress reporting**: Report progress via callback
6. **Error handling**: Continue processing on errors, track failures

Optional Smart Update (Result / ECO) runs as separate post-passes after the plan.

### Result type and UI summaries

Plan and Smart Update services return **`BulkOperationStats`** from `app/services/bulk_operation_stats.py` (same fields as below). Dialogs format results via **`format_bulk_operation_summary_plain`** / **`format_bulk_operation_summary_html`** in `app/utils/bulk_operation_summary.py`.

```python
@dataclass
class BulkOperationStats:
    success: bool
    games_processed: int
    games_updated: int
    games_failed: int
    games_skipped: int
    error_message: Optional[str] = None
```

## Available Operations

The UI exposes two entry points:

- **Bulk Operations** (`BulkOperationsDialog`): ordered list of header-tag and PGN-clean steps, plus dialog-level Smart Update (Result / ECO)
- **Bulk Analysis**: analyze multiple games without making them active (separate dialog)

`BulkOperationsController` runs an ordered list of `BulkOperation` items via `execute_bulk_operations()` (single-pass plan), then optional Smart Update. Domain logic stays in the services below.

### Operation modes (`BulkOperation.mode`)

| Mode | Summary |
|------|---------|
| `find_replace` | Find/replace text in one or more header tags (case / regex options) |
| `overwrite` | Set selected tags to a value (empty clears) |
| `copy` | Copy a source tag into one or more targets |
| `add_tag` | Create tag if missing (fixed value or copy from source) |
| `remove_tags` | Remove selected tags (Seven Tag Roster omitted from UI) |
| `clean` | Remove comments / variations / non-standard inline tags / annotations |

## Plan service

### BulkPlanService

`BulkPlanService` (`app/services/bulk_plan_service.py`) applies the ordered header/clean plan in **one pass** over games (process pool).

- Each worker receives the full plan and applies steps in order on that game
- Header ops mutate an in-memory `chess.pgn.Game`; clean steps use `_process_game_for_cleaning` (`bulk_clean_pgn_service.py`) via `PgnCleaningService`
- Skipped steps (e.g. tag already present / nothing to remove) do not stop later steps
- One `batch_update_games()` after the pool completes

**Tag-to-field mapping** (via `game_data_header_sync`):
When standard tags are modified, corresponding `GameData` fields are updated (`White`, `Black`, `Result`, `Date`, `ECO`, `Event`, `Site`, `WhiteElo`, `BlackElo`, etc.).

## Smart Update services

### BulkReplaceService

`BulkReplaceService` (`app/services/bulk_replace_service.py`) provides dialog-level Smart Update only:

**Update Result Tags** (`update_result_tags()`):
- Analyzes final position of games to determine result
- Uses UCI engine evaluation
- Only updates indecisive results (`*`, `?`, empty)
- Preserves decisive results (`1-0`, `0-1`, `1/2-1/2`)
- Result determination:
  - Checkmate/stalemate: Determined from board state
  - Other positions: Uses evaluation thresholds (±500 centipawns for decisive, ±100 for draw)
- Reuses single engine instance across all games

**Update ECO Tags** (`update_eco_tags()`):
- Uses `OpeningService` to identify ECO code from game moves
- Only updates if ECO differs from current tag
- Skips games where no ECO found

### BulkOperationsController

`BulkOperationsController` (`app/controllers/bulk_operations_controller.py`):
- Runs the ordered plan via `BulkPlanService.apply_plan()` (one pass over games)
- Optionally runs Result/ECO Smart Update after the plan
- Aggregates multi-phase stats (unique games changed via PGN fingerprint when plan + Smart Update both run)
- Gets engine configuration from `EngineController` and `EngineParametersService`
- Creates `OpeningService` instance for ECO updates
- Handles progress reporting and cancellation
- Refreshes active game and marks database unsaved

## Clean PGN helpers

### `_process_game_for_cleaning`

`app/services/bulk_clean_pgn_service.py` exposes the picklable cleaning helper used by the plan worker:

- `remove_comments` / `remove_variations` / `remove_non_standard_tags` / `remove_annotations`
- Delegates to `PgnCleaningService`

### PgnCleaningService

`PgnCleaningService` (`app/services/pgn_cleaning_service.py`) provides cleaning methods:
- Uses `PgnFormatterService` filtering logic
- Preserves metadata tags during cleaning
- Each method returns `True` if game was modified

## Bulk Analysis Operations

### BulkAnalysisService

`BulkAnalysisService` (`app/services/bulk_analysis_service.py`) analyzes games without making them active.

**Key features**:
- Analyzes games in background without loading them into active game view
- Supports parallel analysis (multiple games analyzed simultaneously)
- Stores analysis data in `CARAAnalysisData` PGN tag
- Uses `GameAnalysisEngineService` for engine communication
- Calculates move classifications (Best Move, Good Move, Inaccuracy, Mistake, Blunder, Brilliant Move, Miss)
- Tracks material balance and captures
- Detects book moves

**Parallel analysis**:
- `calculate_parallel_resources()`: Calculates optimal parallel games and threads per engine
- Distributes CPU cores across multiple engine instances
- Each engine instance analyzes one game
- Ensures each engine gets at least 2 threads
- Thread information updates dynamically as workers finish (e.g., "2 threads (1×2)" when only 1 worker remains)

**Analysis process** (`analyze_game()`):
1. Extract moves from game PGN
2. Initialize engine service (reused across games)
3. Analyze each move position:
   - Get evaluation from engine
   - Calculate CPL (centipawn loss)
   - Detect book moves
   - Calculate material sacrifice
   - Classify move quality
   - Track material balance
4. Store analysis data in `CARAAnalysisData` tag
5. Update game PGN and mark as analyzed

**Progress reporting**:
- Reports progress per move: `(game_move_index, total_moves, current_move_number, is_white_move, status_message, engine_info)`
- `engine_info` includes: depth, centipawns, engine_name, threads, elapsed_ms
- Thread information in status bar updates dynamically: shows active workers × threads per engine
- Example: Starts with "12 threads (6×2)", updates to "2 threads (1×2)" as workers finish

**Cleanup**:
- `cleanup()`: Cleans up engine service after analysis completes normally
- Called automatically in `BulkAnalysisThread`'s `finally` block
- Ensures all engine processes are terminated when bulk analysis completes
- Handles cleanup even if workers finish normally (not just on cancel)
- Non-blocking shutdown (no UI freezing during cleanup)

## Common Implementation Details

### PGN Processing

All operations follow this pattern:

```python
# Parse PGN
pgn_io = StringIO(game.pgn)
chess_game = chess.pgn.read_game(pgn_io)

# Modify headers or game structure
chess_game.headers[tag_name] = new_value

# Regenerate PGN
exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
new_pgn = chess_game.accept(exporter).strip()

# Update game data
game.pgn = new_pgn
```

### Batch Updates

All operations use `database.batch_update_games()` for efficiency:

```python
# Collect modified games
updated_games = []
for game in games_to_process:
    if game_was_modified:
        updated_games.append(game)

# Single batch update (emits one dataChanged signal)
if updated_games:
    database.batch_update_games(updated_games)
```

This is more efficient than calling `update_game()` for each game individually.

### Progress Reporting

All operations support progress callbacks:

```python
def progress_callback(game_index: int, total: int, message: str) -> None:
    # Update progress UI
    pass
```

Controllers use `ProgressService` to show/hide progress bars and update status.

### Error Handling

- Individual game failures don't stop the operation
- Failed games are tracked in `games_failed`
- Operations continue processing remaining games
- Final result includes statistics for all games

### Game Selection

Operations support two modes:
- **All games**: `game_indices=None` processes all games in database
- **Selected games**: `game_indices=[0, 5, 10]` processes only specified games

Controllers get selected indices from `DatabasePanel` view.

## Integration Points

### Database Model

- All operations modify `GameData` instances in `DatabaseModel`
- Use `batch_update_games()` for efficient updates
- Automatically mark games as unsaved

### Active Game Refresh

Controllers check if active game was updated and refresh it:
- Parses active game PGN to update metadata view
- Ensures UI reflects changes immediately

### Unsaved Changes Tracking

- Controllers mark database as unsaved after successful operations
- Uses `DatabaseController.mark_database_unsaved()`
- Tab indicators show unsaved status

## Code Location

Implementation files:

- `app/services/bulk_plan_service.py`: Single-pass ordered plan (header tags + clean)
- `app/services/bulk_replace_service.py`: Smart Update (Result / ECO)
- `app/services/bulk_clean_pgn_service.py`: Picklable PGN cleaning helper for the plan worker
- `app/services/bulk_analysis_service.py`: Bulk game analysis
- `app/services/pgn_cleaning_service.py`: PGN cleaning utilities
- `app/controllers/bulk_operations_controller.py`: Orchestrates plan + Smart Update
- `app/views/dialogs/bulk_operations_dialog.py`: Unified Bulk Operations UI
- `app/controllers/bulk_analysis_controller.py`: Bulk analysis orchestration

## Best Practices

### Performance

- Always use `batch_update_games()` instead of individual `update_game()` calls
- Collect modified games and update once at the end
- Reuse engine instances when possible (e.g., `BulkReplaceService.update_result_tags()`)

### Error Handling

- Continue processing on individual game errors
- Track failures but don't fail entire operation
- Return detailed statistics in result object

### Progress Reporting

- Report progress frequently for long operations
- Use `ProgressService` for consistent UI updates
- Support cancellation via `cancel_flag` callback

### Game Selection

- Support both "all games" and "selected games" modes
- Get selected indices from `DatabasePanel` view
- Validate indices before processing

