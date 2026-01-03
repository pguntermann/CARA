# Column Profiles and User Settings Persistence System

## Overview

The application uses a persistent user settings system that stores user preferences in a JSON file (`user_settings.json`). This system handles:

- Moves List column profiles (visibility, width, order)
- Board visibility settings (coordinates, turn indicator, game info)
- PGN visibility settings (metadata display)
- Game analysis settings
- Manual analysis settings
- Engine configuration and assignments
- AI model settings
- Annotation preferences
- Active profile selection

## Architecture

The user settings persistence system follows a **singleton service pattern** with **Model-Controller-Service** integration:

### Component Responsibilities

**UserSettingsService** (`app/services/user_settings_service.py`):
- Singleton service managing file I/O and persistence
- Handles loading `user_settings.json` from disk (one-time at startup)
- Manages template-based migration to add missing settings
- Provides `update_*()` methods that modify model in memory
- Writes to disk only when `save()` is explicitly called
- Uses smart path resolution (app root if writable, otherwise user data directory)

**UserSettingsModel** (`app/models/user_settings_model.py`):
- `QObject`-based model managing settings state in memory
- Emits signals when settings change (`settings_changed`, `board_visibility_changed`, etc.)
- Provides typed accessor methods for all settings sections
- All runtime access is from memory (no disk I/O)

**ColumnProfileModel** (`app/models/column_profile_model.py`):
- Manages column profile data and state
- Emits signals for profile changes (`active_profile_changed`, `profiles_changed`)
- Defines column name constants (must be used consistently across codebase)
- Handles profile operations (create, update, delete, switch)

**ColumnProfileController** (`app/controllers/column_profile_controller.py`):
- Orchestrates profile operations
- Bridges between UI and model/service layers
- Loads profiles from `UserSettingsService` at startup
- Saves profiles through service when user explicitly saves

**MainWindow** (`app/main_window.py`):
- Loads and saves board/PGN visibility settings at startup/exit
- Manages menu bar integration for settings
- Handles application lifecycle (saves all settings on exit)

### Component Interactions

**Initialization Flow (Application Startup)**:
1. `UserSettingsService.get_instance()` is called (singleton pattern - returns existing or creates new)
2. On first access, service:
   - Calls `load()` to read `user_settings.json` from disk (or empty dict if missing)
   - Creates `UserSettingsModel` with loaded data
   - Runs `migrate()` once to check for missing settings from template
   - Saves to disk if migration added settings
3. `ColumnProfileController` is initialized and calls `_load_settings()`
4. Controller gets settings from service (from memory) and loads into `ColumnProfileModel`
5. `MainWindow._load_user_settings()` loads board/PGN visibility from model
6. Settings applied to domain models (`BoardModel`, etc.)
7. Views observe model signals and update UI

**Settings Update Flow (Runtime)**:
1. User modifies settings (e.g., toggles board visibility, changes column profile)
2. Changes saved to model in memory (`UserSettingsModel` or `ColumnProfileModel`)
3. Model emits signals (e.g., `board_visibility_changed`, `active_profile_changed`)
4. Views observe signals and update UI reactively
5. Settings remain in memory until explicit save

**Persistence Flow (Explicit Save)**:
1. User clicks "Save Profile" or application exits
2. `ColumnProfileController.save_settings()` or `MainWindow._save_user_settings()` called
3. Controller/Window collects current state from models/views
4. Calls `UserSettingsService.update_*()` methods to update model
5. Calls `UserSettingsService.save()` to write model state to disk
6. File is written to `user_settings.json` (UTF-8, 2-space indentation)

**Design Pattern: Singleton Service**:
- `UserSettingsService` uses singleton pattern to ensure single instance across application
- All components access settings via `UserSettingsService.get_instance()`
- Service manages single `UserSettingsModel` instance
- Prevents multiple file reads and ensures consistent state

## File Structure

### user_settings.json Location

The file location is determined by `resolve_data_file_path()`:

- **Portable mode**: If app root has write access, file is stored in app root directory
- **User data directory**: If app root is not writable (or macOS app bundle), file is stored in platform-specific user data directory:
  - Windows: `%APPDATA%\CARA\`
  - macOS: `~/Library/Application Support/CARA/`
  - Linux: `~/.local/share/CARA/`

The file is created automatically on first save. Format: JSON with UTF-8 encoding, 2-space indentation.

### Template File

The application uses a template file (`user_settings.json.template`) located in the app root directory:

- **Purpose**: Source of truth for default settings structure
- **Location**: Always in app root directory (read-only)
- **Usage**: 
  - Used when `user_settings.json` doesn't exist (first run)
  - Used for migration to add missing settings/columns from new versions
  - Never modified by the application
- **Configuration**: Filename defined in `config.json` under `user_settings.template_filename`

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
  "profile_order": ["Default", "Profile 2", ...],
  "board_visibility": {
    "show_coordinates": true,
    "show_turn_indicator": true,
    "show_game_info": true
  },
  "pgn_visibility": {
    "show_metadata": true
  },
  "game_analysis": {...},
  "game_analysis_settings": {...},
  "manual_analysis": {...},
  "annotations": {...},
  "engines": [],
  "engine_assignments": {...},
  "ai_models": {...},
  "ai_summary": {...}
}
```

## Memory-Based Access Pattern

The system uses a **load-once, access-from-memory** pattern:

**Startup (One-Time Disk Read)**:
- `UserSettingsService.get_instance()` loads settings from disk once
- Creates `UserSettingsModel` with loaded data
- Runs migration to add missing settings from template
- All settings are now in memory

**Runtime (Memory Access Only)**:
- All `get_settings()` calls return from model (no disk access)
- All `update_*()` methods modify model in memory
- `save()` writes to disk only when explicitly called (e.g., on exit, after profile save)

**Benefits:**
- Fast access (no repeated disk I/O)
- Efficient (single read at startup)
- Reactive (model signals notify UI of changes)

## Column Profiles System

### Column Name Constants

All column names are defined as constants in `app/models/column_profile_model.py`:

- `COL_NUM = "col_num"`
- `COL_WHITE = "col_white"`
- `COL_BLACK = "col_black"`
- `COL_FEN_WHITE = "col_fen_white"`
- `COL_FEN_BLACK = "col_fen_black"`
- (and others...)

These constants must be used consistently across:
- `ColumnProfileModel._column_names` list
- `MovesListModel` column index mapping
- `DetailMovesListView` column name mappings
- Template file structure

### Profile Structure

Each profile contains:

- **columns**: Dictionary mapping column names to configuration
  - `"visible"`: bool - Column visibility
  - `"width"`: int - Column width in pixels (required)
- **column_order**: List of column names in display order (optional)
  - If not present, uses default order from `ColumnProfileModel._column_names`
  - Must include all columns (visible and hidden)

### Default Profile

The "Default" profile:

- Always exists (created if missing during migration)
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

The data flow is described in the "Component Interactions" section of Architecture. Key flows:

**Loading Settings (Application Startup)**: See "Initialization Flow" in Architecture section.

**Saving Settings (Application Exit)**: See "Persistence Flow" in Architecture section.

**Profile Changes (Runtime)**: See "Settings Update Flow" in Architecture section.

### Accessing Settings (Runtime)

```python
# Get settings service (singleton - returns existing instance)
settings_service = UserSettingsService.get_instance()

# Option 1: Get all settings (from memory)
all_settings = settings_service.get_settings()

# Option 2: Get model and use typed accessors (from memory)
model = settings_service.get_model()
board_vis = model.get_board_visibility()
show_coords = board_vis["show_coordinates"]

# Option 3: Update a setting (modifies model in memory)
settings_service.update_board_visibility({"show_coordinates": False})
# Model emits signals → UI updates reactively
```

## Migration

### Template-Based Migration

Migration runs **once** on first access to `UserSettingsService.get_instance()`:

1. Loads template file (`user_settings.json.template`) from app root
2. Compares current settings with template
3. Adds missing top-level sections from template
4. Recursively merges missing sub-keys within existing sections
5. Migrates column profiles (ensures all columns exist with proper structure)
6. Saves if any changes were made

**Key Points:**
- Migration is separate from loading (clean separation of concerns)
- Only runs once (`_migration_done` flag prevents re-running)
- Template is the source of truth for defaults
- User customizations are preserved (only missing keys are added)

### Adding New Columns

When adding columns to existing installations:

1. Add column to template file (`user_settings.json.template`)
2. On next app start:
   - Migration detects missing column in existing profiles
   - Adds column with values from template (or reasonable defaults)
   - Saves updated profiles to `user_settings.json`

The `_migrate_column_profiles()` method handles this automatically by:
- Extracting all column names from template (from all profiles)
- Ensuring each profile has all columns
- Using template defaults when available, or reasonable fallbacks

### Adding New Settings Sections

When adding new settings sections:

1. Add section to template file (`user_settings.json.template`)
2. Add corresponding getter/setter methods to `UserSettingsModel`
3. On next app start:
   - Migration detects missing section
   - Adds entire section from template
   - Saves to `user_settings.json`

### Missing Settings Sections

If required sections are missing:

- Migration adds them from template automatically
- Settings file updated on next save
- Application continues normally

## Error Handling

### File I/O Errors

- If `user_settings.json` is corrupted or unreadable:
  - Warning printed to stderr
  - Starts with empty settings
  - Migration populates from template
  - Application continues normally

- If template file is missing:
  - Error printed to stderr
  - Migration cannot run
  - Application continues with loaded settings (or empty if file was missing)

### Missing Columns in Profiles

- If profile is missing columns:
  - Migration adds missing columns from template
  - Uses template defaults when available
  - Falls back to reasonable defaults (visible: False, width: 100)

## Best Practices

### Column Constants

- Always use constants, never hardcode column names
- Import constants from `column_profile_model.py`
- Use consistent naming: `COL_* = "col_*"`

### Default Values

- Define defaults in template file (`user_settings.json.template`)
- Template is the single source of truth
- Migration automatically applies template defaults
- No hardcoded defaults in code

### Signal Emission

- `UserSettingsModel` emits signals when settings change
- Connect views to model signals (not direct attribute access)
- Use signals for all state changes to maintain MVVM pattern
- Model signals: `settings_changed`, `moves_list_profiles_changed`, `board_visibility_changed`, etc.

### Profile Persistence

- Changes are saved to model in memory immediately
- Persistence only happens on explicit "Save Profile" action or app exit
- Switching profiles does not save current changes
- Application exit saves all settings

### Settings Access

- Always use `UserSettingsService.get_instance()` (singleton pattern)
- Access settings through model for typed accessors
- Use `get_settings()` for simple dictionary access
- Updates go through `update_*()` methods (not direct dict manipulation)

## Code Location

Implementation files:

- `app/services/user_settings_service.py`: File I/O, loading, migration, singleton management
- `app/models/user_settings_model.py`: Settings state model with signals and typed accessors
- `app/models/column_profile_model.py`: Profile data model and column constants
- `app/controllers/column_profile_controller.py`: Profile operations orchestration
- `app/views/detail_moveslist_view.py`: Column visibility and order application
- `app/main_window.py`: Board/PGN visibility settings loading and saving
- `app/utils/path_resolver.py`: File path resolution logic
- `app/config/config.json`: Configuration for settings filenames

## Adding New Columns

For detailed instructions on adding new columns, see `moveslist_columns_implementation.md`.

## Adding New Settings Sections

When adding new settings sections:

1. **Add to template file**: Add section to `user_settings.json.template` with default values
2. **Add model support**: Add getter/setter methods to `UserSettingsModel`:
   ```python
   def get_new_section(self) -> Dict[str, Any]:
       return self._settings.get("new_section", {}).copy()
   
   def set_new_section(self, settings: Dict[str, Any]) -> None:
       self._settings["new_section"] = settings.copy()
       self.new_section_changed.emit()  # Add signal if needed
       self.settings_changed.emit()
   ```
3. **Add service method**: Add `update_new_section()` to `UserSettingsService`
4. **Update migration**: Migration will automatically add missing section from template
5. **Update MainWindow**: Add menu items, load/save setting, connect to model signal
6. **Update controller**: Add toggle method if needed
7. **Update view**: Connect to model signal and use in rendering

## Configuration

Settings filenames are configurable via `config.json`:

```json
{
  "user_settings": {
    "filename": "user_settings.json",
    "template_filename": "user_settings.json.template"
  }
}
```

This allows customization of filenames without code changes.
