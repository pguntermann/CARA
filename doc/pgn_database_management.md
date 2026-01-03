# PGN Database Management System

## Overview

The PGN database management system handles loading, parsing, storing, searching, and saving chess games in PGN format. It supports multiple databases simultaneously, each displayed in its own tab, with a clipboard database for temporary storage.

## Architecture

The PGN database management system follows a **Model-Controller-Service** pattern, with clear separation of concerns:

### Component Responsibilities

- **DatabaseModel** (`QAbstractTableModel`): Represents a single database containing multiple games. Provides Qt table model interface for views, handles game storage, sorting, and per-game unsaved change tracking. Emits `dataChanged` and `layoutChanged` signals for view updates.

- **DatabasePanelModel** (`QObject`): Manages multiple databases simultaneously. Tracks which databases are open, which is active, and which have unsaved changes. Emits signals when active database changes or databases are added/removed. The clipboard database is always present and cannot be closed.

- **DatabaseController**: Orchestrates database operations by coordinating between models and services. Handles file I/O, delegates PGN parsing to `PgnService`, creates and manages `DatabaseModel` instances, and updates `DatabasePanelModel` state. Acts as the primary interface for database operations.

- **PgnService**: Stateless service for parsing PGN text into structured game data. Handles format normalization, validation, and extraction of metadata and CARA-specific tags.

- **DatabaseSearchService**: Stateless service for evaluating search criteria against games. Supports complex queries with AND/OR logic, grouping, and custom tag searches.

### Component Interactions

**Database Lifecycle**:
1. `DatabaseController` creates a `DatabaseModel` instance for each database (clipboard or file-based)
2. `DatabaseController` registers each database with `DatabasePanelModel` using a unique identifier
3. `DatabasePanelModel` tracks active database and emits signals when it changes
4. Views observe `DatabasePanelModel` signals to update UI (tabs, active selection)

**Loading Games**:
1. `DatabaseController` reads PGN file or receives PGN text
2. `DatabaseController` calls `PgnService` to parse PGN text
3. `PgnService` returns parsed game data
4. `DatabaseController` creates `GameData` instances and adds them to `DatabaseModel`
5. `DatabaseModel` emits `dataChanged` signals for view updates

**Unsaved Changes**:
- `DatabaseModel` tracks per-game unsaved changes via `_unsaved_games` set
- When games are updated, `DatabaseModel` automatically adds them to `_unsaved_games`
- `DatabaseController` notifies `DatabasePanelModel` when database-level changes occur
- `DatabasePanelModel` tracks which databases have unsaved changes and emits signals for tab indicators

**Search Operations**:
- Search criteria are built using `SearchCriteria` model classes
- `DatabaseSearchService` evaluates criteria against games from one or more `DatabaseModel` instances
- Search results include games with their source database identifiers

## Data Model

### GameData

`GameData` (`app/models/database_model.py`) represents a single game:

```python
class GameData:
    game_number: int          # Row index in table
    white: str               # White player name
    black: str               # Black player name
    result: str              # Game result ("1-0", "0-1", "1/2-1/2")
    date: str                # Game date
    moves: int               # Number of moves
    eco: str                 # ECO code
    pgn: str                 # Full PGN text
    event: str               # Event name
    site: str                # Site name
    white_elo: str           # White Elo rating
    black_elo: str           # Black Elo rating
    analyzed: bool           # Has CARAAnalysisData tag
    annotated: bool          # Has CARAAnnotations tag
    source_database: str     # Database name (for search results)
```

### DatabaseModel

`DatabaseModel` (`app/models/database_model.py`) extends `QAbstractTableModel`:

- **Columns**: 16 columns including game number, unsaved indicator, metadata fields, and PGN
- **Signals**: Emits `dataChanged` when games are updated, `layoutChanged` when sorted
- **Sorting**: Supports sorting by any column with proper date parsing (see "Date Parsing and Sorting" section)
- **Batch operations**: `batch_update_games()` for efficient bulk updates

Key methods:
- `add_game()`: Add game to model (optionally mark as unsaved)
- `update_game()`: Update existing game (see "Unsaved Changes Tracking" section)
- `batch_update_games()`: Update multiple games with single signal
- `remove_games()`: Remove games from model
- `clear_all_unsaved()`: Clear unsaved change indicators
- `sort()`: Sort games by column

## PGN Parsing

### PgnService

`PgnService` (`app/services/pgn_service.py`) handles PGN text parsing:

**Key features**:
- Parses multiple games from single PGN text
- Normalizes blank lines to handle various PGN formats
- Filters out empty/invalid games
- Extracts metadata from headers
- Counts moves in main line
- Detects CARA-specific tags (`CARAAnalysisData`, `CARAAnnotations`)

**Parsing process**:
1. Normalize blank lines (remove between headers/moves, keep between games)
2. Parse games sequentially using `chess.pgn.read_game()`
3. Extract game data via `_extract_game_data()`
4. Validate games (must have moves, valid PGN structure)
5. Return `PgnParseResult` with parsed games or error message

**Game validation**:
- Games must have at least one move
- PGN must contain move notation
- Empty games are filtered out

## Search System

### SearchCriteria

Search criteria are defined in `app/models/search_criteria.py`:

**SearchField enum**:
- `WHITE`, `BLACK`, `WHITE_ELO`, `BLACK_ELO`
- `RESULT`, `DATE`, `EVENT`, `SITE`, `ECO`
- `ANALYZED`, `ANNOTATED`
- `CUSTOM_TAG` (for arbitrary PGN tags)

**SearchOperator enum**:
- **Text**: `CONTAINS`, `EQUALS`, `NOT_EQUALS`, `STARTS_WITH`, `ENDS_WITH`, `IS_EMPTY`, `IS_NOT_EMPTY`
- **Numeric**: `EQUALS_NUM`, `NOT_EQUALS_NUM`, `GREATER_THAN`, `LESS_THAN`, `GREATER_THAN_OR_EQUAL`, `LESS_THAN_OR_EQUAL`
- **Date**: `DATE_EQUALS`, `DATE_NOT_EQUALS`, `DATE_BEFORE`, `DATE_AFTER`, `DATE_CONTAINS`
- **Boolean**: `IS_TRUE`, `IS_FALSE`

**Logic operators**:
- `AND`: All criteria must match (default)
- `OR`: Any criterion must match
- **Grouping**: Supports nested groups with `is_group_start`, `is_group_end`, `group_level`

### DatabaseSearchService

`DatabaseSearchService` (`app/services/database_search_service.py`) evaluates search criteria:

**Search process**:
1. Build criteria tree from criteria list
2. Evaluate each game against criteria tree recursively
3. Handle AND/OR logic and grouping
4. Return matching games with database names

**Date matching**:
Uses `DateMatcher` (`app/services/date_matcher.py`) for PGN date comparison:
- Supports partial dates: `"2025.??.??"`, `"2025.11.??"`, `"2025.11.09"`
- Handles wildcards (`??` matches any value)
- Conservative comparison for partial dates (returns False if uncertain)

**Custom tag search**:
- Parses PGN to extract custom tags
- Supports any PGN tag not in standard columns
- Uses `custom_tag_name` field in `SearchCriteria`

## Database Operations

### Opening Databases

`DatabaseController.open_pgn_database()` orchestrates loading a PGN file:
- Reads PGN file from disk
- Delegates parsing to `PgnService` to extract game data
- Creates a new `DatabaseModel` instance and populates it with `GameData` objects
- Registers the new database with `DatabasePanelModel` using the file path as identifier
- Sets the new database as the active database

Games loaded from files are not marked as unsaved (they match the file state).

### Saving Databases

`DatabaseController.save_pgn_to_file()` handles persisting database changes:
- Retrieves all games from the `DatabaseModel`
- Writes games incrementally to file (avoids memory issues with large databases)
- Formats PGN with blank lines between games
- Clears unsaved change indicators from the model
- Notifies `DatabasePanelModel` that the database is saved

**Save As** (`save_pgn_database_as()`):
- Creates a new `DatabaseModel` with copied game data
- Saves the new model to a different file path
- Registers the new database with `DatabasePanelModel`
- Reloads the original database from disk (discarding unsaved changes)
- Sets the new database as active

### Reloading Databases

`DatabaseController.reload_database_from_file()` discards unsaved changes:
- Reads the original file from disk
- Parses PGN text using `PgnService`
- Clears the existing `DatabaseModel` and repopulates with fresh data from file
- All unsaved changes are lost

## Multiple Database Management

### DatabasePanelModel

`DatabasePanelModel` (`app/models/database_panel_model.py`) manages multiple databases:

- **Clipboard database**: Default database for temporary storage (cannot be closed)
- **File databases**: Databases loaded from PGN files
- **Active database**: Currently selected database
- **Unsaved tracking**: Tracks which databases have unsaved changes (see "Unsaved Changes Tracking" section)

**Database identifiers**:
- `"clipboard"`: Clipboard database
- File path: File-based databases identified by file path

**Operations**:
- `add_database()`: Add database with file path
- `remove_database()`: Remove database (cannot remove clipboard)
- `set_active_database()`: Set active database and emit signal
- `get_active_database()`: Get active database
- `mark_database_unsaved()`: Mark database as having unsaved changes
- `mark_database_saved()`: Clear unsaved flag

### Database Tab Management

When closing a database:
1. Determine new active database (previous tab, or next tab, or clipboard)
2. Remove database from panel model
3. Set new active database
4. Clipboard cannot be closed

## Date Parsing and Sorting

`DatabaseModel` includes date parsing functionality for sorting the date column:

### Date Format Detection

`DatabaseModel._parse_date_for_sort()` handles various PGN date formats:
- `"YYYY.MM.DD"` (most common)
- `"DD.MM.YYYY"` (European format)
- `"YYYY.DD.MM"` (alternative format)
- `"YYYY.MM"` (year and month)
- `"YYYY"` (year only)

Auto-detects format by analyzing values (year typically > 31 or > 1900).

### Date Sorting

Returns tuple `(year, month, day)` for comparison:
- Missing parts are 0
- Empty dates return `(0, 0, 0)` (sort to beginning)

## Unsaved Changes Tracking

### Per-Game Tracking

`DatabaseModel` tracks unsaved changes per game:
- `_unsaved_games`: Set of `GameData` instances with unsaved changes
- `update_game()`: Automatically marks game as unsaved
- `batch_update_games()`: Marks multiple games as unsaved
- Unsaved indicator icon displayed in second column

### Per-Database Tracking

`DatabasePanelModel` tracks unsaved databases:
- Emits signals when unsaved state changes
- Used for tab indicators and save prompts

## Code Location

Implementation files:

- `app/models/database_model.py`: `DatabaseModel` and `GameData`
- `app/models/database_panel_model.py`: Multiple database management
- `app/models/search_criteria.py`: Search criteria definitions
- `app/services/pgn_service.py`: PGN parsing
- `app/services/database_search_service.py`: Search evaluation
- `app/services/date_matcher.py`: Date comparison utilities
- `app/controllers/database_controller.py`: Database operations orchestration

## Best Practices

### Adding Games

- Use `add_game()` for single games
- Use `batch_update_games()` for multiple updates (more efficient)

### Updating Games

- Always use `update_game()` or `batch_update_games()` (not direct attribute modification)
- See "Unsaved Changes Tracking" section for details on how updates are tracked

### Searching

- Build `SearchCriteria` list with proper operators
- Use grouping for complex queries
- Date searches support partial dates with wildcards

### File Operations

- Use incremental writing for large databases (avoid building entire PGN string in memory)
- Handle progress reporting for long operations
- Clear unsaved indicators after successful save

