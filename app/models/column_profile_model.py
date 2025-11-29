"""Column profile model for managing moves list column visibility."""

import copy
from PyQt6.QtCore import QObject, pyqtSignal
from typing import Dict, Any, List, Optional, Set

# Constants
DEFAULT_PROFILE_NAME = "Default"

# Column name constants
COL_NUM = "col_num"
COL_WHITE = "col_white"
COL_BLACK = "col_black"
COL_EVAL_WHITE = "col_eval_white"
COL_EVAL_BLACK = "col_eval_black"
COL_ASSESS_WHITE = "col_assess_white"
COL_ASSESS_BLACK = "col_assess_black"
COL_BEST_WHITE = "col_best_white"
COL_BEST_BLACK = "col_best_black"
COL_BEST_WHITE_2 = "col_best_white_2"
COL_BEST_WHITE_3 = "col_best_white_3"
COL_BEST_BLACK_2 = "col_best_black_2"
COL_BEST_BLACK_3 = "col_best_black_3"
COL_WHITE_IS_TOP3 = "col_white_is_top3"
COL_BLACK_IS_TOP3 = "col_black_is_top3"
COL_WHITE_DEPTH = "col_white_depth"
COL_BLACK_DEPTH = "col_black_depth"
COL_CPL_WHITE = "col_cpl_white"
COL_CPL_BLACK = "col_cpl_black"
COL_CPL_WHITE_2 = "col_cpl_white_2"
COL_CPL_WHITE_3 = "col_cpl_white_3"
COL_CPL_BLACK_2 = "col_cpl_black_2"
COL_CPL_BLACK_3 = "col_cpl_black_3"
COL_COMMENT = "col_comment"
COL_ECO = "col_eco"
COL_OPENING = "col_opening"
COL_WHITE_CAPTURE = "col_white_capture"
COL_BLACK_CAPTURE = "col_black_capture"
COL_WHITE_MATERIAL = "col_white_material"
COL_BLACK_MATERIAL = "col_black_material"
COL_FEN_WHITE = "col_fen_white"
COL_FEN_BLACK = "col_fen_black"


class ColumnProfile:
    """Represents a column visibility profile."""
    
    def __init__(self, name: str, columns: Dict[str, Dict[str, Any]], column_order: Optional[List[str]] = None) -> None:
        """Initialize a column profile.
        
        Args:
            name: Profile name.
            columns: Dictionary mapping column names to their configuration.
                    Format: {"col_name": {"visible": bool, "width": int, ...}}
            column_order: Optional list of column names in display order.
                         If None, uses default order.
        """
        self.name = name
        self.columns = copy.deepcopy(columns)  # Deep copy to avoid shared references with settings
        self.column_order = column_order.copy() if column_order else None  # Store column display order
    
    def is_column_visible(self, column_name: str) -> bool:
        """Check if a column is visible in this profile.
        
        Args:
            column_name: Name of the column (e.g., "col_num").
            
        Returns:
            True if column is visible, False otherwise.
        """
        col_config = self.columns.get(column_name, {})
        return col_config.get("visible", True)
    
    def set_column_visible(self, column_name: str, visible: bool) -> None:
        """Set column visibility in this profile.
        
        Args:
            column_name: Name of the column.
            visible: True to show column, False to hide it.
        """
        if column_name not in self.columns:
            self.columns[column_name] = {}
        self.columns[column_name]["visible"] = visible
    
    def get_column_width(self, column_name: str) -> int:
        """Get column width from this profile.
        
        Args:
            column_name: Name of the column.
            
        Returns:
            Column width (uses default if column or width is missing).
        """
        col_config = self.columns.get(column_name)
        if col_config is None:
            # Column missing - use default width (migration should have added it)
            # Return a reasonable default to prevent crashes
            default_widths = {
                COL_NUM: 50, COL_WHITE: 100, COL_BLACK: 100,
                COL_EVAL_WHITE: 90, COL_EVAL_BLACK: 90,
                COL_CPL_WHITE: 90, COL_CPL_BLACK: 90,
                COL_CPL_WHITE_2: 90, COL_CPL_WHITE_3: 90,
                COL_CPL_BLACK_2: 90, COL_CPL_BLACK_3: 90,
                COL_ASSESS_WHITE: 100, COL_ASSESS_BLACK: 100,
                COL_BEST_WHITE: 100, COL_BEST_BLACK: 100,
                COL_BEST_WHITE_2: 100, COL_BEST_WHITE_3: 100,
                COL_BEST_BLACK_2: 100, COL_BEST_BLACK_3: 100,
                COL_WHITE_IS_TOP3: 80, COL_BLACK_IS_TOP3: 80,
                COL_WHITE_DEPTH: 70, COL_BLACK_DEPTH: 70,
                COL_ECO: 60, COL_OPENING: 150, COL_COMMENT: 200,
                COL_WHITE_CAPTURE: 80, COL_BLACK_CAPTURE: 80,
                COL_WHITE_MATERIAL: 100, COL_BLACK_MATERIAL: 100,
                COL_FEN_WHITE: 200, COL_FEN_BLACK: 200
            }
            return default_widths.get(column_name, 100)
        if "width" not in col_config:
            # Width missing - use default width
            default_widths = {
                COL_NUM: 50, COL_WHITE: 100, COL_BLACK: 100,
                COL_EVAL_WHITE: 90, COL_EVAL_BLACK: 90,
                COL_CPL_WHITE: 90, COL_CPL_BLACK: 90,
                COL_CPL_WHITE_2: 90, COL_CPL_WHITE_3: 90,
                COL_CPL_BLACK_2: 90, COL_CPL_BLACK_3: 90,
                COL_ASSESS_WHITE: 100, COL_ASSESS_BLACK: 100,
                COL_BEST_WHITE: 100, COL_BEST_BLACK: 100,
                COL_BEST_WHITE_2: 100, COL_BEST_WHITE_3: 100,
                COL_BEST_BLACK_2: 100, COL_BEST_BLACK_3: 100,
                COL_WHITE_IS_TOP3: 80, COL_BLACK_IS_TOP3: 80,
                COL_WHITE_DEPTH: 70, COL_BLACK_DEPTH: 70,
                COL_ECO: 60, COL_OPENING: 150, COL_COMMENT: 200,
                COL_WHITE_CAPTURE: 80, COL_BLACK_CAPTURE: 80,
                COL_WHITE_MATERIAL: 100, COL_BLACK_MATERIAL: 100,
                COL_FEN_WHITE: 200, COL_FEN_BLACK: 200
            }
            return default_widths.get(column_name, 100)
        return col_config["width"]
    
    def set_column_width(self, column_name: str, width: int) -> None:
        """Set column width in this profile.
        
        Args:
            column_name: Name of the column.
            width: Width in pixels.
        """
        if column_name not in self.columns:
            self.columns[column_name] = {}
        self.columns[column_name]["width"] = width
    
    def get_column_order(self, default_order: List[str]) -> List[str]:
        """Get column display order for this profile.
        
        Args:
            default_order: Default column order if not set in profile.
            
        Returns:
            List of column names in display order.
        """
        if self.column_order:
            return self.column_order.copy()
        return default_order.copy()
    
    def set_column_order(self, column_order: List[str]) -> None:
        """Set column display order for this profile.
        
        Args:
            column_order: List of column names in display order.
        """
        self.column_order = column_order.copy() if column_order else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary for persistence.
        
        Returns:
            Dictionary representation of the profile.
        """
        result = {
            "columns": copy.deepcopy(self.columns)  # Deep copy to ensure independence
        }
        
        # Include column_order if it exists
        if self.column_order:
            result["column_order"] = self.column_order.copy()
        
        return result


class ColumnProfileModel(QObject):
    """Model representing column profile state.
    
    This model holds the available profiles and the current active profile,
    and emits signals when profiles or column visibility changes.
    """
    
    # Signals emitted when profile state changes
    active_profile_changed = pyqtSignal(str)  # Emitted when active profile changes (profile name)
    profile_added = pyqtSignal(str)  # Emitted when a profile is added (profile name)
    profile_removed = pyqtSignal(str)  # Emitted when a profile is removed (profile name)
    column_visibility_changed = pyqtSignal(str, bool)  # Emitted when column visibility changes (column_name, visible)
    
    def __init__(self) -> None:
        """Initialize the column profile model."""
        super().__init__()
        self._profiles: Dict[str, ColumnProfile] = {}
        self._active_profile_name: str = DEFAULT_PROFILE_NAME
        self._profile_order: List[str] = []  # Track creation order of profiles (excluding Default)
        self._column_names: List[str] = [
            COL_NUM, COL_WHITE, COL_BLACK, COL_EVAL_WHITE, COL_EVAL_BLACK,
            COL_CPL_WHITE, COL_CPL_BLACK, COL_CPL_WHITE_2, COL_CPL_WHITE_3,
            COL_CPL_BLACK_2, COL_CPL_BLACK_3, COL_ASSESS_WHITE, COL_ASSESS_BLACK,
            COL_BEST_WHITE, COL_BEST_BLACK, COL_BEST_WHITE_2, COL_BEST_WHITE_3,
            COL_BEST_BLACK_2, COL_BEST_BLACK_3, COL_WHITE_IS_TOP3, COL_BLACK_IS_TOP3,
            COL_WHITE_DEPTH, COL_BLACK_DEPTH, COL_ECO, COL_OPENING, COL_COMMENT,
            COL_WHITE_CAPTURE, COL_BLACK_CAPTURE, COL_WHITE_MATERIAL, COL_BLACK_MATERIAL,
            COL_FEN_WHITE, COL_FEN_BLACK
        ]
    
    def get_column_names(self) -> List[str]:
        """Get list of all column names.
        
        Returns:
            List of column names in order.
        """
        return self._column_names.copy()
    
    def get_column_display_name(self, column_name: str) -> str:
        """Get display name for a column.
        
        Args:
            column_name: Internal column name (e.g., "col_num").
            
        Returns:
            Display name for the column.
        """
        display_names = {
            COL_NUM: "#",
            COL_WHITE: "White",
            COL_BLACK: "Black",
            COL_EVAL_WHITE: "Eval White",
            COL_EVAL_BLACK: "Eval Black",
            COL_CPL_WHITE: "CPL White",
            COL_CPL_BLACK: "CPL Black",
            COL_CPL_WHITE_2: "CPL White 2",
            COL_CPL_WHITE_3: "CPL White 3",
            COL_CPL_BLACK_2: "CPL Black 2",
            COL_CPL_BLACK_3: "CPL Black 3",
            COL_ASSESS_WHITE: "Assess White",
            COL_ASSESS_BLACK: "Assess Black",
            COL_BEST_WHITE: "Best White",
            COL_BEST_BLACK: "Best Black",
            COL_BEST_WHITE_2: "Best White 2",
            COL_BEST_WHITE_3: "Best White 3",
            COL_BEST_BLACK_2: "Best Black 2",
            COL_BEST_BLACK_3: "Best Black 3",
            COL_WHITE_IS_TOP3: "White Is Top 3",
            COL_BLACK_IS_TOP3: "Black Is Top 3",
            COL_WHITE_DEPTH: "White Depth",
            COL_BLACK_DEPTH: "Black Depth",
            COL_ECO: "Eco",
            COL_OPENING: "Opening Name",
            COL_COMMENT: "Comment",
            COL_WHITE_CAPTURE: "White Capture",
            COL_BLACK_CAPTURE: "Black Capture",
            COL_WHITE_MATERIAL: "White Material",
            COL_BLACK_MATERIAL: "Black Material",
            COL_FEN_WHITE: "FEN White",
            COL_FEN_BLACK: "FEN Black"
        }
        return display_names.get(column_name, column_name)
    
    def load_profiles(self, profiles_data: Dict[str, Dict[str, Any]], active_profile: str, profile_order: Optional[List[str]] = None) -> None:
        """Load profiles from settings data.
        
        Args:
            profiles_data: Dictionary of profile data from settings.
            active_profile: Name of the active profile.
            profile_order: Optional list of profile names in creation order (excluding Default).
        """
        self._profiles.clear()
        
        # Load profile order from settings (for backward compatibility, use alphabetical if not provided)
        if profile_order is not None:
            self._profile_order = [name for name in profile_order if name != DEFAULT_PROFILE_NAME]
        else:
            # For backward compatibility: if no order provided, use alphabetical (excluding Default)
            self._profile_order = sorted([name for name in profiles_data.keys() if name != DEFAULT_PROFILE_NAME])
        
        # Define default widths for default profile
        default_widths = {
            COL_NUM: 50,
            COL_WHITE: 100,
            COL_BLACK: 100,
            COL_EVAL_WHITE: 90,
            COL_EVAL_BLACK: 90,
            COL_CPL_WHITE: 90,
            COL_CPL_BLACK: 90,
            COL_CPL_WHITE_2: 90,
            COL_CPL_WHITE_3: 90,
            COL_CPL_BLACK_2: 90,
            COL_CPL_BLACK_3: 90,
            COL_ASSESS_WHITE: 100,
            COL_ASSESS_BLACK: 100,
            COL_BEST_WHITE: 100,
            COL_BEST_BLACK: 100,
            COL_BEST_WHITE_2: 100,
            COL_BEST_WHITE_3: 100,
            COL_BEST_BLACK_2: 100,
            COL_BEST_BLACK_3: 100,
            COL_WHITE_IS_TOP3: 80,
            COL_BLACK_IS_TOP3: 80,
            COL_WHITE_DEPTH: 70,
            COL_BLACK_DEPTH: 70,
            COL_ECO: 60,
            COL_OPENING: 150,
            COL_WHITE_CAPTURE: 80,
            COL_BLACK_CAPTURE: 80,
            COL_WHITE_MATERIAL: 100,
            COL_BLACK_MATERIAL: 100,
            COL_FEN_WHITE: 200,
            COL_FEN_BLACK: 200,
        }
        
        # Load profiles from settings
        for profile_name, profile_data in profiles_data.items():
            # Create deep copy of columns to avoid modifying the original settings dictionary
            columns = copy.deepcopy(profile_data.get("columns", {}))
            column_order = profile_data.get("column_order", None)
            if column_order is not None:
                column_order = column_order.copy()  # Copy list to avoid shared reference
            
            # Ensure all profiles have all columns with proper defaults (migration for new columns)
            for col_name in self._column_names:
                if col_name not in columns:
                    # New column missing - add with defaults
                    columns[col_name] = {"visible": False}  # Hidden by default for existing profiles
                    if col_name in default_widths:
                        columns[col_name]["width"] = default_widths[col_name]
                else:
                    # Column exists - ensure visibility and width are set
                    if "visible" not in columns[col_name]:
                        columns[col_name]["visible"] = True  # Default to visible if not set
                    # Ensure width is set
                    if col_name in default_widths and "width" not in columns[col_name]:
                        columns[col_name]["width"] = default_widths[col_name]
            
            profile = ColumnProfile(profile_name, columns, column_order)
            self._profiles[profile_name] = profile
        
        # Set active profile
        if active_profile in self._profiles:
            self._active_profile_name = active_profile
        else:
            # Fallback to default if active profile doesn't exist
            self._active_profile_name = DEFAULT_PROFILE_NAME
        
        # Ensure default profile exists with proper default settings
        if DEFAULT_PROFILE_NAME not in self._profiles:
            # Create default profile with all columns visible and default widths
            default_columns = {}
            for col_name in self._column_names:
                col_config = {"visible": True}
                if col_name in default_widths:
                    col_config["width"] = default_widths[col_name]
                default_columns[col_name] = col_config
            # Use default column order for default profile
            self._profiles[DEFAULT_PROFILE_NAME] = ColumnProfile(DEFAULT_PROFILE_NAME, default_columns, self._column_names.copy())
    
    def get_profile_names(self) -> List[str]:
        """Get list of all profile names.
        
        Returns Default first, followed by profiles in creation order.
        
        Returns:
            List of profile names.
        """
        # Start with Default if it exists
        result = []
        if DEFAULT_PROFILE_NAME in self._profiles:
            result.append(DEFAULT_PROFILE_NAME)
        
        # Add profiles in creation order (excluding Default)
        for profile_name in self._profile_order:
            if profile_name in self._profiles and profile_name != DEFAULT_PROFILE_NAME:
                result.append(profile_name)
        
        # Add any profiles that exist but aren't in the order list (for backward compatibility)
        for profile_name in sorted(self._profiles.keys()):
            if profile_name not in result:
                result.append(profile_name)
        
        return result
    
    def get_active_profile_name(self) -> str:
        """Get the active profile name.
        
        Returns:
            Active profile name.
        """
        return self._active_profile_name
    
    def set_active_profile(self, profile_name: str) -> bool:
        """Set the active profile.
        
        Args:
            profile_name: Name of the profile to activate.
            
        Returns:
            True if profile was set, False if profile doesn't exist.
        """
        if profile_name not in self._profiles:
            return False
        
        # Always emit signals even if profile name hasn't changed
        # This ensures column visibility is properly updated on startup
        self._active_profile_name = profile_name
        
        # Emit active profile changed signal
        self.active_profile_changed.emit(profile_name)
        
        # Emit column visibility changes for all columns
        active_profile = self._profiles[profile_name]
        for column_name in self._column_names:
            visible = active_profile.is_column_visible(column_name)
            self.column_visibility_changed.emit(column_name, visible)
        
        return True
    
    def add_profile(self, profile_name: str, columns: Optional[Dict[str, Dict[str, Any]]] = None, column_order: Optional[List[str]] = None) -> bool:
        """Add a new profile.
        
        Args:
            profile_name: Name of the new profile.
            columns: Optional column configuration. If None, copies from active profile.
            column_order: Optional column order. If None, copies from active profile.
            
        Returns:
            True if profile was added, False if profile already exists.
        """
        if profile_name in self._profiles:
            return False
        
        if columns is None:
            # Copy from active profile (including widths and order)
            active_profile = self._profiles[self._active_profile_name]
            columns = {}
            for col_name in self._column_names:
                visible = active_profile.is_column_visible(col_name)
                col_config = {"visible": visible}
                # Copy width if it exists
                if col_name in active_profile.columns:
                    width = active_profile.columns[col_name].get("width")
                    if width is not None:
                        col_config["width"] = width
                columns[col_name] = col_config
            # Copy column_order from active profile if not provided
            if column_order is None:
                column_order = active_profile.column_order.copy() if active_profile.column_order else None
        
        profile = ColumnProfile(profile_name, columns, column_order)
        self._profiles[profile_name] = profile
        
        # Add to creation order (if not Default and not already in order)
        if profile_name != DEFAULT_PROFILE_NAME and profile_name not in self._profile_order:
            self._profile_order.append(profile_name)
        
        self.profile_added.emit(profile_name)
        
        return True
    
    def remove_profile(self, profile_name: str) -> bool:
        """Remove a profile.
        
        Args:
            profile_name: Name of the profile to remove.
            
        Returns:
            True if profile was removed, False if profile doesn't exist or is default.
        """
        if profile_name not in self._profiles:
            return False
        
        # Cannot remove default profile
        if profile_name == DEFAULT_PROFILE_NAME:
            return False
        
        # Cannot remove active profile if it's the only one
        if profile_name == self._active_profile_name and len(self._profiles) == 1:
            return False
        
        del self._profiles[profile_name]
        
        # Remove from creation order
        if profile_name in self._profile_order:
            self._profile_order.remove(profile_name)
        
        # If we removed the active profile, switch to default
        if profile_name == self._active_profile_name:
            self.set_active_profile(DEFAULT_PROFILE_NAME)
        
        self.profile_removed.emit(profile_name)
        return True
    
    def update_current_profile_columns(self, columns: Dict[str, Dict[str, Any]]) -> None:
        """Update columns in the current active profile.
        
        Args:
            columns: Dictionary mapping column names to their configuration.
        """
        active_profile = self._profiles[self._active_profile_name]
        
        for column_name, col_config in columns.items():
            if column_name in self._column_names:
                visible = col_config.get("visible", True)
                active_profile.set_column_visible(column_name, visible)
                self.column_visibility_changed.emit(column_name, visible)
    
    def get_current_column_visibility(self) -> Dict[str, bool]:
        """Get current column visibility state.
        
        Returns:
            Dictionary mapping column names to visibility (True/False).
        """
        active_profile = self._profiles[self._active_profile_name]
        visibility = {}
        
        for column_name in self._column_names:
            visibility[column_name] = active_profile.is_column_visible(column_name)
        
        return visibility
    
    def get_current_column_widths(self) -> Dict[str, int]:
        """Get current column widths from active profile.
        
        Returns:
            Dictionary mapping column names to widths.
            
        Raises:
            RuntimeError: If any column width is missing from user_settings.json.
        """
        active_profile = self._profiles[self._active_profile_name]
        widths = {}
        
        for column_name in self._column_names:
            widths[column_name] = active_profile.get_column_width(column_name)
        
        return widths
    
    def update_current_profile_column_widths(self, widths: Dict[str, int]) -> None:
        """Update column widths in the current active profile.
        
        Args:
            widths: Dictionary mapping column names to widths.
        """
        active_profile = self._profiles[self._active_profile_name]
        
        for column_name, width in widths.items():
            if column_name in self._column_names:
                active_profile.set_column_width(column_name, width)
    
    
    def toggle_column_visibility(self, column_name: str) -> bool:
        """Toggle visibility of a column in the active profile.
        
        Args:
            column_name: Name of the column to toggle.
            
        Returns:
            True if column is now visible, False if hidden.
        """
        if column_name not in self._column_names:
            return False
        
        active_profile = self._profiles[self._active_profile_name]
        current_visible = active_profile.is_column_visible(column_name)
        new_visible = not current_visible
        
        active_profile.set_column_visible(column_name, new_visible)
        self.column_visibility_changed.emit(column_name, new_visible)
        
        return new_visible
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert profiles to dictionary for persistence.
        
        Returns:
            Dictionary representation of all profiles.
        """
        profiles_dict = {}
        for profile_name, profile in self._profiles.items():
            profiles_dict[profile_name] = profile.to_dict()
        
        return {
            "moves_list_profiles": profiles_dict,
            "active_profile": self._active_profile_name,
            "profile_order": self._profile_order.copy()  # Save creation order
        }

