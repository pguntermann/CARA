# Moves List Columns Implementation Guide

## Overview

This guide documents everything you need to know when adding new columns to the Moves List table. The system uses a dual-column architecture with column name constants (strings) and column indices (integers), along with a comprehensive profile system for visibility, ordering, and width management.

## Architecture

### Dual Column System

- **Column Name Constants (strings)**: Defined in `app/models/column_profile_model.py`
  - Used for: Profile persistence, column identification, user-facing names
  - Format: `COL_NEW_COLUMN = "col_new_column"`

- **Column Indices (integers)**: Defined in `app/models/moveslist_model.py`
  - Used for: Model data access, table view column mapping
  - Format: `COL_NEW_COLUMN = 32` (next available index, 0-based)

### Current Column Count

- Total columns: 32 (indices 0-31)
- When adding a new column, you MUST update `columnCount()` to return the new total

### Profile System

- Column visibility, order, and widths are managed per profile
- Profiles are persisted in `user_settings.json`
- Changes are in-memory until explicitly saved via "Save Profile" or "Save Profile as..."

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
  - Update `load()` method to migrate existing profiles (add column with defaults)

- **Step 8: Update Analysis Services** (if column displays analysis data)
  - Files: `app/controllers/game_analysis_controller.py`, `app/services/game_analysis_engine_service.py`
  - Update `MoveData` creation and signal emissions
  - Update analysis result parsing

- **Step 9: Test**
  - Verify column appears in moves list and setup dialog
  - Verify column visibility, order, and width can be adjusted
  - Verify profile persistence works
  - Verify column appears correctly after app restart

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
