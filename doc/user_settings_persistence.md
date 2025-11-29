
Column Profiles and User Settings Persistence System

1. Overview

The application uses a persistent user settings system that stores user preferences in a JSON file (user_settings.json) located in the app root directory. This system handles:

• Moves List column profiles (visibility, width, order)
• Board visibility settings (coordinates, turn indicator, game info)
• PGN visibility settings (metadata display)
• Active profile selection

2. Architecture

The system follows MVVM pattern with clear separation of concerns:

• UserSettingsService (app/services/user_settings_service.py)
  - Handles file I/O for user_settings.json
  - Provides default settings structure
  - Validates and ensures required sections exist

• ColumnProfileModel (app/models/column_profile_model.py)
  - Manages column profile data and state
  - Emits signals for profile changes
  - Defines column name constants

• ColumnProfileController (app/controllers/column_profile_controller.py)
  - Orchestrates profile operations
  - Bridges between UI and model/service layers

• MainWindow (app/main_window.py)
  - Loads and saves board/PGN visibility settings
  - Manages menu bar integration
  - Handles application lifecycle (save on exit)

3. File Structure

3.1 user_settings.json Location
Location: app_root/user_settings.json
Created: Automatically on first save
Format: JSON with UTF-8 encoding, 2-space indentation

3.2 JSON Structure

{
  "moves_list_profiles": {
    "Default": {
      "columns": {
        "col_num": {"visible": true, "width": 50},
        "col_white": {"visible": true, "width": 100},
        "col_black": {"visible": true, "width": 100},
        "col_eval_white": {"visible": true, "width": 90},
        "col_eval_black": {"visible": true, "width": 90},
        "col_assess_white": {"visible": true, "width": 100},
        "col_assess_black": {"visible": true, "width": 100},
        "col_best_white": {"visible": true, "width": 100},
        "col_best_black": {"visible": true, "width": 100},
        "col_comment": {"visible": true}
      },
      "column_order": [
        "col_num", "col_white", "col_black", "col_eval_white",
        "col_eval_black", "col_assess_white", "col_assess_black",
        "col_best_white", "col_best_black", "col_comment"
      ]
    },
    "Profile Name": {
      "columns": { ... },
      "column_order": [ ... ]
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

4. Column Profiles System

4.1 Column Name Constants

All column names are defined as constants in app/models/column_profile_model.py:

COL_NUM = "col_num"
COL_WHITE = "col_white"
COL_BLACK = "col_black"
COL_EVAL_WHITE = "col_eval_white"
COL_EVAL_BLACK = "col_eval_black"
COL_ASSESS_WHITE = "col_assess_white"
COL_ASSESS_BLACK = "col_assess_black"
COL_BEST_WHITE = "col_best_white"
COL_BEST_BLACK = "col_best_black"
COL_COMMENT = "col_comment"

These constants must be used consistently across:
• ColumnProfileModel._column_names list
• MovesListModel column index mapping
• DetailMovesListView column name mappings
• UserSettingsService.DEFAULT_SETTINGS

4.2 Profile Structure

Each profile contains:
• columns: Dictionary mapping column names to configuration
  - "visible": bool - Column visibility
  - "width": int - Column width in pixels (optional, for non-stretching columns)
• column_order: List of column names in display order (optional)
  - If not present, uses default order from ColumnProfileModel._column_names
  - Must include all columns (visible and hidden)
  - Order determines visual position in table

4.3 Default Profile

The "Default" profile:
• Always exists (created if missing)
• Cannot be removed
• Cannot be updated via "Save Profile" (must use "Save Profile as...")
• Always appears first in menu
• Uses default column order from _column_names list

4.4 Profile Operations

• Create: "Save Profile as..." - Creates new profile with current settings
• Update: "Save Profile" - Overwrites current profile (not available for Default)
• Delete: "Remove Profile" - Removes profile (not available for Default)
• Switch: Click profile name in menu - Activates profile without saving current changes

5. Adding New Columns

When adding a new column to the Moves List table:

5.1 Define Column Constant

In app/models/column_profile_model.py:

1. Add constant at top of file:
   COL_NEW_COLUMN = "col_new_column"

2. Add to _column_names list in ColumnProfileModel.__init__:
   self._column_names: List[str] = [
       COL_NUM, COL_WHITE, ..., COL_NEW_COLUMN
   ]

5.2 Update MovesListModel

In app/models/moveslist_model.py:

1. Add column index constant:
   COL_NEW_COLUMN = 10  # Next available index

2. Update set_column_visibility() method:
   Add mapping in name_to_index dictionary:
   COL_NEW_COLUMN: self.COL_NEW_COLUMN

3. Update data() and headerData() methods:
   Add handling for new column index

5.3 Update DetailMovesListView

In app/views/detail_moveslist_view.py:

1. Import column constant:
   from app.models.column_profile_model import ..., COL_NEW_COLUMN

2. Update column name mappings:
   - Add to logical_to_name in _apply_column_order_and_widths()
   - Add to name_to_logical in _apply_column_order()
   - Add to logical_to_name in _save_column_order()
   - Add to logical_to_name in _save_column_widths()

3. Update default widths (if needed):
   Add to _column_widths list in __init__()

4. Add to default widths dictionary in _apply_column_order_and_widths():
   column_names = [..., COL_NEW_COLUMN]

5.4 Update UserSettingsService

In app/services/user_settings_service.py:

1. Import column constant:
   from app.models.column_profile_model import ..., COL_NEW_COLUMN

2. Add to DEFAULT_SETTINGS:
   In "moves_list_profiles" -> "Default" -> "columns":
   COL_NEW_COLUMN: {"visible": True, "width": 100}  # Adjust width as needed

3. Update load() method:
   Ensure new column is added to default profile if missing

5.5 Update ColumnProfileModel

In app/models/column_profile_model.py:

1. Update load_profiles() method:
   Add to default_widths dictionary if column should have a default width:
   COL_NEW_COLUMN: 100  # Adjust width as needed

2. Update get_column_display_name() method:
   Add display name mapping:
   COL_NEW_COLUMN: "New Column"

5.6 Update MainWindow Menu

In app/main_window.py:

1. Menu items are automatically generated from ColumnProfileModel
   No changes needed if display names are set correctly

5.7 Migration Considerations

When adding columns:
• Existing profiles will have the new column added with default visibility (True)
• Column order will append new column to end (or use default order)
• Default width will be applied if specified in default_widths

6. Adding New Visibility Settings

When adding new visibility settings (e.g., board features, PGN features):

6.1 Define Setting in UserSettingsService

In app/services/user_settings_service.py:

1. Add to DEFAULT_SETTINGS:
   "new_visibility": {
       "show_new_feature": true
   }

2. Update load() method:
   Ensure new section exists:
   if "new_visibility" not in self._settings:
       self._settings["new_visibility"] = self.DEFAULT_SETTINGS["new_visibility"]

6.2 Add Model Support

In appropriate model (e.g., BoardModel, DetailPgnView):

1. Add attribute:
   self._show_new_feature = True

2. Add property:
   @property
   def show_new_feature(self) -> bool:
       return self._show_new_feature

3. Add setter:
   def set_show_new_feature(self, show: bool) -> None:
       self._show_new_feature = show
       self.new_feature_visibility_changed.emit(show)

4. Add signal:
   new_feature_visibility_changed = pyqtSignal(bool)

6.3 Update MainWindow

In app/main_window.py:

1. Add menu item in _setup_menu_bar():
   self.new_feature_action = QAction("Show New Feature", self)
   self.new_feature_action.setCheckable(True)
   self.new_feature_action.triggered.connect(self.controller.toggle_new_feature_visibility)
   menu.addAction(self.new_feature_action)

2. Load setting in _load_user_settings():
   new_visibility = settings.get("new_visibility", {})
   show_new_feature = new_visibility.get("show_new_feature", True)
   model.set_show_new_feature(show_new_feature)
   self.new_feature_action.setChecked(show_new_feature)

3. Save setting in _save_user_settings():
   settings["new_visibility"] = {
       "show_new_feature": model.show_new_feature
   }

4. Connect to model signal:
   model.new_feature_visibility_changed.connect(self._on_new_feature_visibility_changed)

5. Add handler:
   def _on_new_feature_visibility_changed(self, visible: bool) -> None:
       self.new_feature_action.setChecked(visible)

6.4 Update Controller

In appropriate controller (e.g., BoardController):

1. Add method:
   def toggle_new_feature_visibility(self) -> None:
       self.board_model.toggle_new_feature_visibility()

2. Update model (e.g., BoardModel):
   def toggle_new_feature_visibility(self) -> None:
       self.set_show_new_feature(not self._show_new_feature)

6.5 Update View

In appropriate view (e.g., ChessBoardWidget):

1. Add attribute:
   self.show_new_feature = True

2. Connect to model signal:
   model.new_feature_visibility_changed.connect(self._on_new_feature_visibility_changed)

3. Add handler:
   def _on_new_feature_visibility_changed(self, visible: bool) -> None:
       self.show_new_feature = visible
       self.update()

4. Use in rendering:
   if self.show_new_feature:
       # Render feature

7. Data Flow

7.1 Loading Settings (Application Startup)

1. UserSettingsService.load() reads user_settings.json
2. Validates and ensures all required sections exist
3. ColumnProfileController._load_settings() loads profiles
4. ColumnProfileModel.load_profiles() initializes profiles
5. MainWindow._load_user_settings() loads board/PGN visibility
6. Settings applied to models
7. Views observe model signals and update UI

7.2 Saving Settings (Application Exit)

1. MainWindow.closeEvent() or _close_application() called
2. MainWindow._save_user_settings() collects current state:
   - Board visibility from BoardModel
   - PGN visibility from DetailPgnView
3. ColumnProfileController.save_settings() saves profiles:
   - Column visibility, widths, order from ColumnProfileModel
4. UserSettingsService.save() writes to user_settings.json

7.3 Profile Changes (Runtime)

1. User modifies column visibility/order/width
2. Changes saved to ColumnProfileModel (in memory only)
3. View updates immediately via signals
4. User clicks "Save Profile" or "Save Profile as..."
5. ColumnProfileController.save_settings() or update_current_profile()
6. UserSettingsService.save() persists to file

8. Integration Points

8.1 Column Profile Integration

• ColumnProfileModel manages profile state
• DetailMovesListView observes profile changes
• MovesListModel receives visibility updates
• MainWindow menu reflects profile state

8.2 Visibility Settings Integration

• BoardModel manages board visibility state
• ChessBoardWidget observes board visibility signals
• MainPanel observes game info visibility
• DetailPgnView manages PGN metadata visibility
• MainWindow menu reflects visibility state

9. Error Handling

9.1 File I/O Errors

• If user_settings.json is corrupted or unreadable:
  - Warning printed to stderr
  - Default settings used
  - Application continues normally

9.2 Missing Settings Sections

• If required sections are missing:
  - Default values inserted automatically
  - Settings file updated on next save

9.3 Missing Columns in Profiles

• If profile is missing columns:
  - Default profile: Missing columns added with defaults
  - Other profiles: Missing columns added with default visibility (True)

10. Best Practices

10.1 Column Constants

• Always use constants, never hardcode column names
• Import constants from column_profile_model.py
• Use consistent naming: COL_* = "col_*"

10.2 Default Values

• Define defaults in UserSettingsService.DEFAULT_SETTINGS
• Define default widths in ColumnProfileModel.load_profiles()
• Ensure defaults are applied when loading missing data

10.3 Signal Emission

• Emit signals when state changes
• Connect views to model signals (not direct attribute access)
• Use signals for all state changes to maintain MVVM pattern

10.4 Profile Persistence

• Changes are saved to model in memory immediately
• Persistence only happens on explicit "Save Profile" action
• Switching profiles does not save current changes
• Application exit saves all settings

11. Testing Considerations

When adding new columns or visibility settings:

1. Test with existing user_settings.json files
2. Test with missing columns in profiles
3. Test with corrupted JSON files
4. Test profile switching and persistence
5. Test default profile behavior
6. Test column reordering and persistence
7. Test visibility toggles and persistence

12. Future Enhancements

Potential additions to the system:

• Column sorting preferences
• Column alignment settings
• Profile import/export
• Profile templates
• Per-profile color schemes
• Additional visibility settings for other UI elements

