# Moves List Columns Implementation Guide

## Overview

This guide documents everything you need to know when adding new columns to the Moves List table. The system uses a dual-column architecture with column name constants (strings) and column indices (integers), along with a comprehensive profile system for visibility, ordering, and width management.

## Architecture

The moves list column system uses a dual-identifier architecture with profile-based configuration:

### Dual Column System

The system maintains two parallel identifiers for each column:

- **Column Name Constants (strings)**: Defined in `app/models/column_profile_model.py`
  - Used for: Profile persistence, column identification, user-facing names
  - Format: `COL_NEW_COLUMN = "col_new_column"`
  - Stable identifier that persists across code changes

- **Column Indices (integers)**: Defined in `app/models/moveslist_model.py`
  - Used for: Model data access, table view column mapping, QAbstractTableModel interface
  - Format: `COL_NEW_COLUMN = 32` (next available index, 0-based)
  - Sequential indices required by Qt's model/view architecture

**Why two identifiers?**
- String constants provide stable, readable identifiers for persistence and configuration
- Integer indices are required by Qt's `QAbstractTableModel` interface for efficient data access
- The view layer (`detail_moveslist_view.py`) maintains mappings between logical positions (user-defined order) and both identifier types

### Profile System

Column configuration is managed through a profile-based system:

- **Profile Model** (`ColumnProfileModel`): QObject-based model managing column visibility, order, and widths per profile
- **Persistence**: Profiles stored in `user_settings.json` under `moves_list_profiles`
- **In-Memory Changes**: Modifications are temporary until explicitly saved via "Save Profile" or "Save Profile as..."
- **Default Profile**: Read-only; changes require "Save Profile as..." to create a new profile
- **Migration**: New columns are automatically added to existing profiles with default settings (hidden by default)

### Current Column Count

- Total columns: 32 (indices 0-31)
- When adding a new column, you MUST update `columnCount()` to return the new total
- All column-related code must use `columnCount()` instead of hardcoded values for consistency

## Current Columns Reference

The following 32 columns are currently implemented, organized by category:

### Basic Columns

| Index | Constant | Display Name | Description |
|-------|----------|--------------|-------------|
| 0 | `COL_NUM` | "#" | Move number (1, 2, 3, ...) |
| 1 | `COL_WHITE` | "White" | White's move in SAN notation |
| 2 | `COL_BLACK` | "Black" | Black's move in SAN notation |
| 25 | `COL_COMMENT` | "Comment" | Move comments from PGN |

### Evaluation Columns

| Index | Constant | Display Name | Description |
|-------|----------|--------------|-------------|
| 3 | `COL_EVAL_WHITE` | "Eval White" | Evaluation after white's move (formatted as "+X.X" or "M{N}") |
| 4 | `COL_EVAL_BLACK` | "Eval Black" | Evaluation after black's move (formatted as "-X.X" or "-M{N}") |
| 5 | `COL_CPL_WHITE` | "CPL White" | Centipawn loss for white's move (see calculation below) |
| 6 | `COL_CPL_BLACK` | "CPL Black" | Centipawn loss for black's move (see calculation below) |
| 7 | `COL_CPL_WHITE_2` | "CPL White 2" | CPL for white's move vs. PV2 (second-best engine move) |
| 8 | `COL_CPL_WHITE_3` | "CPL White 3" | CPL for white's move vs. PV3 (third-best engine move) |
| 9 | `COL_CPL_BLACK_2` | "CPL Black 2" | CPL for black's move vs. PV2 (second-best engine move) |
| 10 | `COL_CPL_BLACK_3` | "CPL Black 3" | CPL for black's move vs. PV3 (third-best engine move) |

**CPL Calculation**: Centipawn Loss measures evaluation lost by playing a move instead of the best move:
- Primary: `CPL = |eval_after_best_move - eval_after_played_move|`
- Mate positions: When checkmate is involved, CPL uses special rules:
  - If checkmate is achieved: CPL = 0 (best move)
  - If checkmate is created (delivering mate): CPL = 0 (best move)
  - If checkmate is allowed (allowing opponent to mate): CPL = high value (blunder)
  - If both the position before the move and after the move are mate positions (forced mate sequences): CPL compares how many moves until checkmate (mate distance) - getting closer to mate is better, getting further from mate is worse
- PV2/PV3 CPL: `|pv_score - eval_after_played_move|`
- If played move matches best move: CPL = 0

### Best Moves Columns

| Index | Constant | Display Name | Description |
|-------|----------|--------------|-------------|
| 13 | `COL_BEST_WHITE` | "Best White" | Engine's best move suggestion for white (SAN notation) |
| 14 | `COL_BEST_BLACK` | "Best Black" | Engine's best move suggestion for black (SAN notation) |
| 15 | `COL_BEST_WHITE_2` | "Best White 2" | Engine's second-best move (PV2) for white |
| 16 | `COL_BEST_WHITE_3` | "Best White 3" | Engine's third-best move (PV3) for white |
| 17 | `COL_BEST_BLACK_2` | "Best Black 2" | Engine's second-best move (PV2) for black |
| 18 | `COL_BEST_BLACK_3` | "Best Black 3" | Engine's third-best move (PV3) for black |
| 19 | `COL_WHITE_IS_TOP3` | "White Is Top 3" | "✓" if white's move matches any top 3 engine moves, empty otherwise |
| 20 | `COL_BLACK_IS_TOP3` | "Black Is Top 3" | "✓" if black's move matches any top 3 engine moves, empty otherwise |

**Top 3 Detection**: Checks if the played move (normalized) matches any of the top 3 engine moves (best move, PV2, or PV3) after removing check/checkmate symbols and converting to lowercase.

### Analysis Columns

| Index | Constant | Display Name | Description | Calculation |
|-------|----------|--------------|-------------|-------------|
| 11 | `COL_ASSESS_WHITE` | "Assess White" | Move quality assessment for white's move | See assessment below |
| 12 | `COL_ASSESS_BLACK` | "Assess Black" | Move quality assessment for black's move | See assessment below |
| 21 | `COL_WHITE_DEPTH` | "White Depth" | Engine search depth for white's move analysis | Engine-reported depth value |
| 22 | `COL_BLACK_DEPTH` | "Black Depth" | Engine search depth for black's move analysis | Engine-reported depth value |

**Move Assessment Calculation**: Classification hierarchy (first match wins). All thresholds are configurable via `MoveClassificationModel` and can be customized in the application settings or `config.json`:

1. **Brilliant**: Material sacrifice ≥ `min_material_sacrifice` (configurable, default: 300 cp) AND evaluation swing ≥ `min_eval_swing` (configurable, default: 200 cp) AND (if `exclude_already_winning` is True) not already winning
2. **Best Move**: Played move matches best engine move (CPL = 0)
3. **Miss**: CPL ≥ 100 AND best move is tactical (capture/mate) AND played move is not tactical AND would be classified as Inaccuracy/Mistake/Blunder
4. **Good Move**: CPL ≤ `good_move_max_cpl` (configurable, default: 50)
5. **Inaccuracy**: CPL ≤ `inaccuracy_max_cpl` (configurable, default: 100)
6. **Mistake**: CPL ≤ `mistake_max_cpl` (configurable, default: 200)
7. **Blunder**: CPL > `mistake_max_cpl`

**Configuration**: Thresholds are loaded from `config.json` under `game_analysis.assessment_thresholds` and `game_analysis.brilliant_criteria`, and can be overridden by user settings in `user_settings.json` under `game_analysis_settings`. Settings are managed by `MoveClassificationModel` and can be modified via the classification settings dialog.

**Book Move**: If move is detected in opening book, assessment is "Book Move" (no CPL calculated).

### Material Columns

| Index | Constant | Display Name | Description |
|-------|----------|--------------|-------------|
| 26 | `COL_WHITE_CAPTURE` | "White Capture" | Piece captured by white's move (e.g., "P", "N", "R") |
| 27 | `COL_BLACK_CAPTURE` | "Black Capture" | Piece captured by black's move (e.g., "P", "N", "R") |
| 28 | `COL_WHITE_MATERIAL` | "White Material" | White's material balance in centipawns after move |
| 29 | `COL_BLACK_MATERIAL` | "Black Material" | Black's material balance in centipawns after move |

**Material Balance**: Calculated using piece values (Pawn: 100, Knight/Bishop: 300, Rook: 500, Queen: 900) and represents the material difference from the starting position.

### Position Columns

| Index | Constant | Display Name | Description |
|-------|----------|--------------|-------------|
| 23 | `COL_ECO` | "Eco" | ECO code (opening classification, e.g., "B20") |
| 24 | `COL_OPENING` | "Opening Name" | Opening name from ECO database |
| 30 | `COL_FEN_WHITE` | "FEN White" | FEN string of position after white's move |
| 31 | `COL_FEN_BLACK` | "FEN Black" | FEN string of position after black's move |

**ECO/Opening**: Identified using `OpeningService` based on game moves. FEN strings represent the complete board state after each move.

## Step-by-Step Implementation Checklist

When adding a new column, follow this checklist in order:

- **Step 1: Define Column Name Constant** (`app/models/column_profile_model.py`)
  - Add: `COL_NEW_COLUMN = "col_new_column"` at top of file
  - Add to `_column_names` list in `ColumnProfileModel.__init__()`
  - Add display name in `get_column_display_name()`: `COL_NEW_COLUMN: "New Column"`
  - Add default width in `load_profiles()` method's `default_widths` dictionary: `COL_NEW_COLUMN: 100`

- **Step 2: Define Column Index** (`app/models/moveslist_model.py`)
  - Add: `COL_NEW_COLUMN = 32` (or next available index)
  - Update `columnCount()` to return new total (e.g., 33 if adding one column)
  - Update `__init__()` visibility initialization: `for col in range(33):` (new total)

- **Step 3: Update MoveData** (`app/models/moveslist_model.py`, if column displays move data)
  - Add field to `MoveData` dataclass
  - Update `__init__()` parameters if needed

- **Step 4: Implement Data Display** (`app/models/moveslist_model.py`)
  - Add handling in `data()` method:
    ```python
    elif logical_col == self.COL_NEW_COLUMN:
        move = self._moves[row]
        return move.new_column_data  # or appropriate data source
    ```
  - Add header in `headerData()` method:
    ```python
    elif section == self.COL_NEW_COLUMN:
        return "New Column"  # or use get_column_display_name()
    ```
  - Update `set_column_visibility()` method's `name_to_index` mapping:
    ```python
    COL_NEW_COLUMN: self.COL_NEW_COLUMN,
    ```
  - Update `clear_analysis_data()` method if column contains analysis data

- **Step 5: Update View Mappings** (`app/views/detail_moveslist_view.py`)
  - Import: `from app.models.column_profile_model import ..., COL_NEW_COLUMN`
  - Add to ALL `logical_to_name` mappings:
    - `_apply_column_order_and_widths()`
    - `_save_column_order()`
    - `_save_column_widths()`
  - Add to `name_to_logical` mapping in `_apply_column_order()`

- **Step 6: Update Setup Dialog** (`app/views/moveslist_profile_setup_dialog.py`)
  - Import: `from app.models.column_profile_model import ..., COL_NEW_COLUMN`
  - Add to appropriate category in `column_categories` dictionary:
    - "Basic Columns", "Evaluation Columns", "Best Moves Columns", "Analysis Columns", "Material Columns", "Position Columns", or "Other"

- **Step 7: Update Default Settings** (`app/services/user_settings_service.py`)
  - Add to `DEFAULT_SETTINGS["moves_list_profiles"]["Default"]["columns"]`:
    ```python
    COL_NEW_COLUMN: {"visible": True, "width": 100}
    ```
  - Add to default `column_order` if column should be visible by default
  - Update `load()` method to migrate existing profiles (see "Migration Notes" section below)

- **Step 8: Update Analysis Services** (if column displays analysis data)
  - Files: `app/controllers/game_analysis_controller.py`, `app/services/game_analysis_engine_service.py`
  - Update `MoveData` creation and signal emissions
  - Update analysis result parsing

- **Step 9: Test**
  - See "Testing Checklist" section below for comprehensive verification steps

## Critical Rules

### Column Count Consistency

- `MovesListModel.columnCount()` MUST return the total number of columns
- All bounds checks MUST use `self.columnCount()` instead of hardcoded values
- Visibility initialization MUST cover all columns: `for col in range(self.columnCount()):`

### Column Name Constants

- MUST be defined in `column_profile_model.py`
- MUST be added to `_column_names` list
- MUST have a display name in `get_column_display_name()`
- MUST be used consistently across all files

### Column Indices

- MUST be sequential (0, 1, 2, ..., N-1)
- MUST be unique
- SHOULD match the order in `_column_names` (for consistency)

### View Mappings

- ALL `logical_to_name` mappings must include the new column (in `_apply_column_order_and_widths()`, `_save_column_order()`, `_save_column_widths()`)
- ALL `name_to_logical` mappings must include the new column (in `_apply_column_order()`)
- Missing mappings cause columns to disappear or fail to save

### Profile Persistence

- Column visibility, order, and widths are stored per profile
- Changes are in-memory until explicitly saved
- Default profile cannot be updated (must use "Save Profile as...")
- Migration: New columns are automatically added to existing profiles with defaults (hidden by default)

## Common Pitfalls

1. **Forgetting to update `columnCount()`**
   - Symptom: Column doesn't appear, index out of range errors
   - Fix: Update `columnCount()` to return new total

2. **Missing view mappings**
   - Symptom: Column doesn't appear, order doesn't persist, widths don't save
   - Fix: Add to ALL `logical_to_name` and `name_to_logical` mappings

3. **Hardcoded column counts**
   - Symptom: Columns beyond hardcoded count don't work
   - Fix: Replace hardcoded values with `self.columnCount()` or `model.columnCount()`

4. **Missing display name**
   - Symptom: Column shows as "col_new_column" instead of "New Column"
   - Fix: Add to `get_column_display_name()` method

5. **Missing default width**
   - Symptom: Column width is 0 or incorrect
   - Fix: Add to `default_widths` in `load_profiles()` and `DEFAULT_SETTINGS`

6. **Not adding to setup dialog categories**
   - Symptom: Column doesn't appear in setup dialog
   - Fix: Add to appropriate category in `column_categories`

## Migration Notes

When adding columns to an existing installation:

- Existing profiles will automatically get the new column with:
  - Visibility: False (hidden by default for existing profiles)
  - Width: Default width from `default_widths`
  - Order: Appended to end (or uses default order)

- The `load_profiles()` method in `ColumnProfileModel` handles migration:
  - Checks if column exists in profile
  - Adds column with `{"visible": False}` if missing
  - Preserves existing column configurations
  - Ensures width is set from `default_widths` if missing

- `UserSettingsService.load()` should also handle migration:
  - Ensures new columns are added to all existing profiles
  - Uses default visibility (False) and width values

## Testing Checklist

After adding a new column, verify:

- Column appears in moves list table
- Column header displays correctly
- Column data displays correctly (or empty if no data)
- Column appears in setup dialog under correct category
- Column visibility can be toggled via menu and setup dialog
- Column order can be changed via drag-and-drop in setup dialog
- Column width can be adjusted in setup dialog
- Column width, order, and visibility persist when profile is saved
- Column appears correctly after app restart
- Column works with all existing profiles
- Column highlighting works (if applicable)
- No console errors or warnings
