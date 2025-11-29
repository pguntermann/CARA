Moves List Columns Implementation Guide
======================================

Overview
--------
This guide documents everything you need to know when adding new columns to the Moves List table. The system uses a dual-column architecture with column name constants (strings) and column indices (integers), along with a comprehensive profile system for visibility, ordering, and width management.

Architecture
------------

1. Dual Column System
   - Column Name Constants (strings): Defined in `app/models/column_profile_model.py`
     - Used for: Profile persistence, column identification, user-facing names
     - Format: `COL_NEW_COLUMN = "col_new_column"`
   
   - Column Indices (integers): Defined in `app/models/moveslist_model.py`
     - Used for: Model data access, table view column mapping
     - Format: `COL_NEW_COLUMN = 32` (next available index, 0-based)

2. Current Column Count
   - Total columns: 32 (indices 0-31)
   - When adding a new column, you MUST update `columnCount()` to return the new total

3. Profile System
   - Column visibility, order, and widths are managed per profile
   - Profiles are persisted in `user_settings.json`
   - Changes are in-memory until explicitly saved via "Save Profile" or "Save Profile as..."

Files That Must Be Updated
--------------------------

1. app/models/column_profile_model.py
   - Add column name constant at top of file
   - Add to `_column_names` list in `ColumnProfileModel.__init__()`
   - Add display name in `get_column_display_name()` method
   - Add default width in `load_profiles()` method's `default_widths` dictionary
   - Add to appropriate category in `MovesListProfileSetupDialog.column_categories` (if using setup dialog)

2. app/models/moveslist_model.py
   - Add column index constant (next available number, currently 0-31)
   - Update `columnCount()` to return new total (currently 32)
   - Update `__init__()` to initialize visibility for new column in `_column_visibility` dict
   - Add data handling in `data()` method for new column index
   - Add header handling in `headerData()` method for new column index
   - Update `set_column_visibility()` method's `name_to_index` mapping
   - Update `clear_analysis_data()` method if column contains analysis data
   - Update bounds checks that use hardcoded column counts (use `self.columnCount()` instead)

3. app/models/moveslist_model.py - MoveData class
   - Add field to `MoveData` dataclass if column displays move data
   - Update `__init__()` parameters if needed

4. app/views/detail_moveslist_view.py
   - Import new column constant
   - Add to `logical_to_name` mapping in `_apply_column_order_and_widths()`
   - Add to `name_to_logical` mapping in `_apply_column_order()`
   - Add to `logical_to_name` mapping in `_save_column_order()`
   - Add to `logical_to_name` mapping in `_save_column_widths()`
   - Update any hardcoded column count references (use `self._moveslist_model.columnCount()`)

5. app/views/moveslist_profile_setup_dialog.py
   - Import new column constant
   - Add to appropriate category in `column_categories` dictionary:
     - "Basic Columns": COL_NUM, COL_WHITE, COL_BLACK, COL_COMMENT
     - "Evaluation Columns": COL_EVAL_WHITE, COL_EVAL_BLACK, COL_CPL_WHITE, etc.
     - "Best Moves Columns": COL_BEST_WHITE, COL_BEST_BLACK, etc.
     - "Analysis Columns": COL_ASSESS_WHITE, COL_ASSESS_BLACK, etc.
     - "Material Columns": COL_WHITE_CAPTURE, COL_BLACK_CAPTURE, etc.
     - "Position Columns": COL_ECO, COL_OPENING, COL_FEN_WHITE, COL_FEN_BLACK
     - "Other": For any columns that don't fit existing categories

6. app/services/user_settings_service.py
   - Add to `DEFAULT_SETTINGS` in "moves_list_profiles" -> "Default" -> "columns":
     ```python
     COL_NEW_COLUMN: {"visible": True, "width": 100}  # Adjust as needed
     ```
   - Add to default "column_order" list if column should be visible by default
   - Update `load()` method to ensure new column is added to existing profiles during migration

7. app/main_window.py
   - No changes needed - menu items are auto-generated from `ColumnProfileModel`
   - Column visibility menu uses `get_column_names()` and `get_column_display_name()`

8. app/controllers/column_profile_controller.py
   - No changes needed - works with column name constants generically

9. app/controllers/game_analysis_controller.py (if column displays analysis data)
   - Update signal emissions to include new data fields
   - Update `_on_move_analysis_complete()` to populate new `MoveData` fields

10. app/services/game_analysis_engine_service.py (if column displays analysis data)
    - Update `MoveData` creation to include new fields
    - Update analysis result parsing if needed

Step-by-Step Implementation Checklist
--------------------------------------

When adding a new column, follow this checklist in order:

□ Step 1: Define Column Name Constant
  - File: `app/models/column_profile_model.py`
  - Add: `COL_NEW_COLUMN = "col_new_column"` at top of file
  - Add to `_column_names` list in `ColumnProfileModel.__init__()`
  - Add display name in `get_column_display_name()`: `COL_NEW_COLUMN: "New Column"`
  - Add default width in `load_profiles()`: `COL_NEW_COLUMN: 100` (adjust as needed)

□ Step 2: Define Column Index
  - File: `app/models/moveslist_model.py`
  - Add: `COL_NEW_COLUMN = 32` (or next available index)
  - Update `columnCount()` to return new total (e.g., 33 if adding one column)
  - Update `__init__()` visibility initialization: `for col in range(33):` (new total)

□ Step 3: Update MoveData (if needed)
  - File: `app/models/moveslist_model.py`
  - Add field to `MoveData` dataclass if column displays move data
  - Update `__init__()` parameters if needed

□ Step 4: Implement Data Display
  - File: `app/models/moveslist_model.py`
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

□ Step 5: Update Column Visibility Mapping
  - File: `app/models/moveslist_model.py`
  - Add to `name_to_index` in `set_column_visibility()`:
    ```python
    COL_NEW_COLUMN: self.COL_NEW_COLUMN,
    ```

□ Step 6: Update View Mappings
  - File: `app/views/detail_moveslist_view.py`
  - Import: `from app.models.column_profile_model import ..., COL_NEW_COLUMN`
  - Add to ALL `logical_to_name` mappings:
    - `_apply_column_order_and_widths()`
    - `_save_column_order()`
    - `_save_column_widths()`
  - Add to `name_to_logical` mapping in `_apply_column_order()`

□ Step 7: Update Setup Dialog
  - File: `app/views/moveslist_profile_setup_dialog.py`
  - Import: `from app.models.column_profile_model import ..., COL_NEW_COLUMN`
  - Add to appropriate category in `column_categories` dictionary

□ Step 8: Update Default Settings
  - File: `app/services/user_settings_service.py`
  - Add to `DEFAULT_SETTINGS["moves_list_profiles"]["Default"]["columns"]`:
    ```python
    COL_NEW_COLUMN: {"visible": True, "width": 100}
    ```
  - Add to default `column_order` if column should be visible by default
  - Update `load()` method to migrate existing profiles (add column with defaults)

□ Step 9: Update Analysis Services (if column displays analysis data)
  - Files: `game_analysis_controller.py`, `game_analysis_engine_service.py`
  - Update `MoveData` creation and signal emissions
  - Update analysis result parsing

□ Step 10: Test
  - Verify column appears in moves list
  - Verify column appears in setup dialog
  - Verify column visibility can be toggled
  - Verify column order can be changed
  - Verify column width can be adjusted
  - Verify profile persistence works
  - Verify column appears after app restart

Critical Rules
--------------

1. Column Count Consistency
   - `MovesListModel.columnCount()` MUST return the total number of columns
   - All bounds checks MUST use `self.columnCount()` instead of hardcoded values
   - Visibility initialization MUST cover all columns: `for col in range(self.columnCount()):`

2. Column Name Constants
   - MUST be defined in `column_profile_model.py`
   - MUST be added to `_column_names` list
   - MUST have a display name in `get_column_display_name()`
   - MUST be used consistently across all files

3. Column Indices
   - MUST be sequential (0, 1, 2, ..., N-1)
   - MUST be unique
   - MUST match the order in `_column_names` (for consistency, though not strictly required)

4. Profile Persistence
   - Column visibility, order, and widths are stored per profile
   - Changes are in-memory until explicitly saved
   - Default profile cannot be updated (must use "Save Profile as...")
   - Migration: New columns are automatically added to existing profiles with defaults

5. Setup Dialog Categories
   - Columns must be added to appropriate category in `column_categories`
   - Use "Other" category for columns that don't fit existing categories
   - Categories match the menu structure in MainWindow

6. View Mappings
   - ALL `logical_to_name` mappings must include the new column
   - ALL `name_to_logical` mappings must include the new column
   - Missing mappings cause columns to disappear or fail to save

7. Data Role Handling
   - `data()` method must handle `DisplayRole` for the new column
   - `headerData()` method must handle `DisplayRole` for the new column
   - `dataChanged` signals must include `BackgroundRole` if column needs highlighting

Common Pitfalls
---------------

1. Forgetting to update `columnCount()`
   - Symptom: Column doesn't appear, index out of range errors
   - Fix: Update `columnCount()` to return new total

2. Missing view mappings
   - Symptom: Column doesn't appear, order doesn't persist, widths don't save
   - Fix: Add to ALL `logical_to_name` and `name_to_logical` mappings

3. Hardcoded column counts
   - Symptom: Columns beyond hardcoded count don't work
   - Fix: Replace hardcoded values with `self.columnCount()` or `model.columnCount()`

4. Missing display name
   - Symptom: Column shows as "col_new_column" instead of "New Column"
   - Fix: Add to `get_column_display_name()` method

5. Missing default width
   - Symptom: Column width is 0 or incorrect
   - Fix: Add to `default_widths` in `load_profiles()` and `DEFAULT_SETTINGS`

6. Not adding to setup dialog categories
   - Symptom: Column doesn't appear in setup dialog
   - Fix: Add to appropriate category in `column_categories`

7. Missing migration in UserSettingsService
   - Symptom: Existing profiles don't have new column
   - Fix: Update `load()` method to add column to existing profiles

Example: Adding a New Column
-----------------------------

Let's say we want to add a "Time Spent" column that shows how long each move took.

Step 1: Define constant in `column_profile_model.py`:
```python
COL_TIME_SPENT = "col_time_spent"
```

Step 2: Add to `_column_names`:
```python
self._column_names: List[str] = [
    ..., COL_TIME_SPENT
]
```

Step 3: Add display name:
```python
COL_TIME_SPENT: "Time Spent",
```

Step 4: Add default width:
```python
COL_TIME_SPENT: 80,
```

Step 5: Add column index in `moveslist_model.py`:
```python
COL_TIME_SPENT = 32
```

Step 6: Update `columnCount()`:
```python
return 33  # Was 32, now 33
```

Step 7: Update visibility initialization:
```python
for col in range(33):  # Was 32, now 33
    self._column_visibility[col] = True
```

Step 8: Add to `MoveData`:
```python
time_spent: float = 0.0
```

Step 9: Add data handling:
```python
elif logical_col == self.COL_TIME_SPENT:
    move = self._moves[row]
    return f"{move.time_spent:.2f}s" if move.time_spent > 0 else ""
```

Step 10: Add header:
```python
elif section == self.COL_TIME_SPENT:
    return "Time"
```

Step 11: Add to view mappings (all locations)
Step 12: Add to setup dialog category
Step 13: Add to default settings
Step 14: Test thoroughly

Migration Notes
---------------

When adding columns to an existing installation:

1. Existing profiles will automatically get the new column with:
   - Visibility: True (default)
   - Width: Default width from `default_widths`
   - Order: Appended to end (or uses default order)

2. The `load_profiles()` method in `ColumnProfileModel` handles migration:
   - Checks if column exists in profile
   - Adds column with defaults if missing
   - Preserves existing column configurations

3. UserSettingsService.load() should also handle migration:
   - Ensures new columns are added to all existing profiles
   - Uses default visibility and width values

Testing Checklist
-----------------

After adding a new column, verify:

□ Column appears in moves list table
□ Column header displays correctly
□ Column data displays correctly (or empty if no data)
□ Column appears in setup dialog under correct category
□ Column visibility can be toggled via menu
□ Column visibility can be toggled via setup dialog
□ Column order can be changed via drag-and-drop in setup dialog
□ Column width can be adjusted in setup dialog
□ Column width persists when profile is saved
□ Column order persists when profile is saved
□ Column visibility persists when profile is saved
□ Column appears correctly after app restart
□ Column works with all existing profiles
□ Column highlighting works (if applicable)
□ No console errors or warnings

