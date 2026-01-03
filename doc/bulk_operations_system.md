# Bulk Operations System

## Overview

The bulk operations system provides efficient batch processing of games in databases. All operations follow a common pattern: iterate through games, apply transformations, collect updates, and batch-update the model with a single signal for performance.

## Architecture

The bulk operations system follows a Service-Controller-Model pattern consistent with the application's architecture:

- **Services**: Handle the business logic for bulk operations (`BulkTagService`, `BulkReplaceService`, etc.)
- **Controllers**: Orchestrate operations, handle UI concerns (progress, cancellation), and coordinate with models
- **Models**: Store game data; operations update `DatabaseModel` via batch updates

### Component Structure

Each bulk operation consists of:
- A **Service** class that implements the core operation logic
- A **Controller** class that orchestrates the operation, handles progress reporting, and manages UI integration
- Integration with `DatabaseModel` for efficient batch updates

### Common Pattern

All bulk operations follow this pattern:

1. **Filter games**: Select games to process (all games or selected indices)
2. **Process each game**: Parse PGN, apply transformation, regenerate PGN
3. **Collect updates**: Build list of modified games
4. **Batch update**: Call `database.batch_update_games()` once with all modified games
5. **Progress reporting**: Report progress via callback
6. **Error handling**: Continue processing on errors, track failures

### Result Classes

Each operation returns a result dataclass with statistics:

```python
@dataclass
class BulkOperationResult:
    success: bool
    games_processed: int
    games_updated: int
    games_failed: int
    games_skipped: int
    error_message: Optional[str] = None
```

## Available Operations

The system provides four main bulk operations:

- **Bulk Tag Operations**: Add or remove PGN tags from games
- **Bulk Replace Operations**: Replace text in metadata tags, copy tags, update Result/ECO tags
- **Bulk Clean PGN Operations**: Remove comments, variations, annotations, non-standard tags, results
- **Bulk Analysis Operations**: Analyze multiple games without making them active

## Bulk Tag Operations

### BulkTagService

`BulkTagService` (`app/services/bulk_tag_service.py`) handles adding and removing PGN tags.

**Add Tag** (`add_tag()`):
- Adds a tag to games that don't already have it
- Three value modes:
  - **Fixed value**: Set tag to specified value
  - **Copy from source**: Copy value from another tag
  - **Empty**: Add tag with empty value
- Skips games where tag already exists (`games_skipped`)

**Remove Tag** (`remove_tag()`):
- Removes specified tag from games
- Skips games where tag doesn't exist

**Tag-to-field mapping**:
When standard tags are modified, corresponding `GameData` fields are updated:
- `White` → `game.white`
- `Black` → `game.black`
- `Result` → `game.result`
- `Date` → `game.date`
- `ECO` → `game.eco`
- `Event` → `game.event`
- `Site` → `game.site`
- `WhiteElo` → `game.white_elo`
- `BlackElo` → `game.black_elo`

### BulkTagController

`BulkTagController` (`app/controllers/bulk_tag_controller.py`):
- Sanitizes tag names (removes whitespace, invalid characters)
- Shows/hides progress via `ProgressService`
- Refreshes active game if it was updated
- Marks database as unsaved on success
- Emits `operation_complete` signal

## Bulk Replace Operations

### BulkReplaceService

`BulkReplaceService` (`app/services/bulk_replace_service.py`) handles text replacement and tag updates.

**Replace Metadata Tag** (`replace_metadata_tag()`):
- Replaces text in specified PGN tag
- **Modes**:
  - **Normal replacement**: Find and replace text (case-sensitive or case-insensitive)
  - **Regex replacement**: Use regex pattern for finding
  - **Overwrite all**: Replace any value with new value (ignores find_text)
- Updates tag-to-field mappings for standard tags

**Copy Metadata Tag** (`copy_metadata_tag()`):
- Copies value from source tag to target tag
- Only updates if source has value and differs from current target value

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

### BulkReplaceController

`BulkReplaceController` (`app/controllers/bulk_replace_controller.py`):
- Gets engine configuration from `EngineController` and `EngineParametersService`
- Creates `OpeningService` instance for ECO updates
- Handles progress reporting and cancellation
- Refreshes active game and marks database unsaved

## Bulk Clean PGN Operations

### BulkCleanPgnService

`BulkCleanPgnService` (`app/services/bulk_clean_pgn_service.py`) removes elements from PGN notation.

**Clean PGN** (`clean_pgn()`):
- Applies multiple cleaning operations in sequence:
  - `remove_comments`: Remove all comments
  - `remove_variations`: Remove all variations
  - `remove_non_standard_tags`: Remove tags like `[%evp]`, `[%mdl]`, `[%clk]`
  - `remove_annotations`: Remove NAGs and move annotations (`!`, `?`, `!!`, `??`)
  - `remove_results`: Remove results from move notation (preserves `[Result]` tag)
- Uses `PgnCleaningService` for actual cleaning logic
- Tracks if game was modified (only updates if at least one operation modified the game)

### PgnCleaningService

`PgnCleaningService` (`app/services/pgn_cleaning_service.py`) provides cleaning methods:
- Uses `PgnFormatterService` filtering logic
- Preserves metadata tags during cleaning
- Each method returns `True` if game was modified

### BulkCleanPgnController

`BulkCleanPgnController` (`app/controllers/bulk_clean_pgn_controller.py`):
- Handles progress reporting
- Refreshes active game and marks database unsaved

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

- `app/services/bulk_tag_service.py`: Tag add/remove operations
- `app/services/bulk_replace_service.py`: Text replacement and tag updates
- `app/services/bulk_clean_pgn_service.py`: PGN cleaning operations
- `app/services/bulk_analysis_service.py`: Bulk game analysis
- `app/services/pgn_cleaning_service.py`: PGN cleaning utilities
- `app/controllers/bulk_tag_controller.py`: Tag operations orchestration
- `app/controllers/bulk_replace_controller.py`: Replace operations orchestration
- `app/controllers/bulk_clean_pgn_controller.py`: Clean operations orchestration

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

