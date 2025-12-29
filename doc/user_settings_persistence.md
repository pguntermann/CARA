# Column Profiles and User Settings Persistence System

## Overview

The application uses a persistent user settings system that stores user preferences in a JSON file (`user_settings.json`). This system handles:

- Moves List column profiles (visibility, width, order)
- Board visibility settings (coordinates, turn indicator, game info)
- PGN visibility settings (metadata display)
- Active profile selection

## Architecture

The system follows PyQt's Model/View architecture with Controllers:

- **UserSettingsService** (`app/services/user_settings_service.py`): Handles file I/O, provides default settings structure, validates and ensures required sections exist
- **ColumnProfileModel** (`app/models/column_profile_model.py`): Manages column profile data and state, emits signals for profile changes, defines column name constants
- **ColumnProfileController** (`app/controllers/column_profile_controller.py`): Orchestrates profile operations, bridges between UI and model/service layers
- **MainWindow** (`app/main_window.py`): Loads and saves board/PGN visibility settings, manages menu bar integration, handles application lifecycle (save on exit)

## File Structure

### user_settings.json Location

The file location is determined by `resolve_data_file_path()`:

- **Portable mode**: If app root has write access, file is stored in app root directory
- **User data directory**: If app root is not writable (or macOS app bundle), file is stored in platform-specific user data directory:
  - Windows: `%APPDATA%\CARA\`
  - macOS: `~/Library/Application Support/CARA/`
  - Linux: `~/.local/share/CARA/`

The file is created automatically on first save. Format: JSON with UTF-8 encoding, 2-space indentation.

### JSON Structure

```json
{
  "moves_list_profiles": {
    "Default": {
      "columns": {
        "col_num": {"visible": true, "width": 50},
        "col_white": {"visible": true, "width": 100}
      },
      "column_order": ["col_num", "col_white", ...]
    }
  },
  "active_profile": "Default",
  "board_visibility": {
    "show_coordinates": true,
    "show_turn_indicator": true,
    "show_game_info": true
  },
  "pgn_visibility": {
    "show_metadata": true
  }
}
```

## Column Profiles System

### Column Name Constants

All column names are defined as constants in `app/models/column_profile_model.py`:

- `COL_NUM = "col_num"`
- `COL_WHITE = "col_white"`
- `COL_BLACK = "col_black"`
- (and others...)

These constants must be used consistently across:
- `ColumnProfileModel._column_names` list
- `MovesListModel` column index mapping
- `DetailMovesListView` column name mappings
- `UserSettingsService.DEFAULT_SETTINGS`

### Profile Structure

Each profile contains:

- **columns**: Dictionary mapping column names to configuration
  - `"visible"`: bool - Column visibility
  - `"width"`: int - Column width in pixels (optional)
- **column_order**: List of column names in display order (optional)
  - If not present, uses default order from `ColumnProfileModel._column_names`
  - Must include all columns (visible and hidden)

### Default Profile

The "Default" profile:

- Always exists (created if missing)
- Cannot be removed
- Cannot be updated via "Save Profile" (must use "Save Profile as...")
- Always appears first in menu
- Uses default column order from `_column_names` list

### Profile Operations

- **Create**: "Save Profile as..." - Creates new profile with current settings
- **Update**: "Save Profile" - Overwrites current profile (not available for Default)
- **Delete**: "Remove Profile" - Removes profile (not available for Default)
- **Switch**: Click profile name in menu - Activates profile without saving current changes

## Data Flow

### Loading Settings (Application Startup)

1. `UserSettingsService.load()` reads `user_settings.json`
2. Validates and ensures all required sections exist
3. `ColumnProfileController._load_settings()` loads profiles
4. `ColumnProfileModel.load_profiles()` initializes profiles
5. `MainWindow._load_user_settings()` loads board/PGN visibility
6. Settings applied to models
7. Views observe model signals and update UI

### Saving Settings (Application Exit)

1. `MainWindow.closeEvent()` or `_close_application()` called
2. `MainWindow._save_user_settings()` collects current state:
   - Board visibility from `BoardModel`
   - PGN visibility from `DetailPgnView`
3. `ColumnProfileController.save_settings()` saves profiles:
   - Column visibility, widths, order from `ColumnProfileModel`
4. `UserSettingsService.save()` writes to `user_settings.json`

### Profile Changes (Runtime)

1. User modifies column visibility/order/width
2. Changes saved to `ColumnProfileModel` (in memory only)
3. View updates immediately via signals
4. User clicks "Save Profile" or "Save Profile as..."
5. `ColumnProfileController.save_settings()` or `update_current_profile()`
6. `UserSettingsService.save()` persists to file

## Migration

### Adding New Columns

When adding columns to existing installations:

- Existing profiles will have the new column added with:
  - Visibility: False (hidden by default for existing profiles)
  - Width: Default width from `default_widths` (if specified)
  - Order: Appended to end (or uses default order)

The `load_profiles()` method in `ColumnProfileModel` handles migration automatically. `UserSettingsService.load()` also ensures new columns are added to all existing profiles.

### Missing Settings Sections

If required sections are missing:

- Default values inserted automatically
- Settings file updated on next save

## Error Handling

### File I/O Errors

- If `user_settings.json` is corrupted or unreadable:
  - Warning printed to stderr
  - Default settings used
  - Application continues normally

### Missing Columns in Profiles

- If profile is missing columns:
  - Default profile: Missing columns added with defaults
  - Other profiles: Missing columns added with default visibility (False) and default width

## Best Practices

### Column Constants

- Always use constants, never hardcode column names
- Import constants from `column_profile_model.py`
- Use consistent naming: `COL_* = "col_*"`

### Default Values

- Define defaults in `UserSettingsService.DEFAULT_SETTINGS`
- Define default widths in `ColumnProfileModel.load_profiles()`
- Ensure defaults are applied when loading missing data

### Signal Emission

- Emit signals when state changes
- Connect views to model signals (not direct attribute access)
- Use signals for all state changes to maintain MVVM pattern

### Profile Persistence

- Changes are saved to model in memory immediately
- Persistence only happens on explicit "Save Profile" action
- Switching profiles does not save current changes
- Application exit saves all settings

## Code Location

Implementation files:

- `app/services/user_settings_service.py`: File I/O and settings management
- `app/models/column_profile_model.py`: Profile data model and column constants
- `app/controllers/column_profile_controller.py`: Profile operations orchestration
- `app/views/detail_moveslist_view.py`: Column visibility and order application
- `app/main_window.py`: Board/PGN visibility settings loading and saving
- `app/utils/path_resolver.py`: File path resolution logic

## Adding New Columns

For detailed instructions on adding new columns, see `moveslist_columns_implementation.md`.

## Adding New Visibility Settings

When adding new visibility settings (e.g., board features, PGN features):

1. **Define setting in UserSettingsService**: Add to `DEFAULT_SETTINGS` and ensure it exists in `load()`
2. **Add model support**: Add attribute, property, setter, and signal in appropriate model
3. **Update MainWindow**: Add menu item, load/save setting, connect to model signal
4. **Update controller**: Add toggle method if needed
5. **Update view**: Connect to model signal and use in rendering
