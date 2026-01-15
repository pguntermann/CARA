"""Column profile controller for managing column visibility profiles."""

from typing import Dict, Any, Optional, List

from app.models.column_profile_model import ColumnProfileModel, DEFAULT_PROFILE_NAME
from app.services.user_settings_service import UserSettingsService
from app.services.logging_service import LoggingService


class ColumnProfileController:
    """Controller for managing column profile operations.
    
    This controller orchestrates column profile operations and manages
    the column profile model and user settings service.
    """
    
    def __init__(self) -> None:
        """Initialize the column profile controller."""
        # Get singleton service instance
        self.settings_service = UserSettingsService.get_instance()
        
        # Initialize model
        self.profile_model = ColumnProfileModel()
        
        # Load settings and initialize model
        self._load_settings()
    
    def _load_settings(self) -> None:
        """Load user settings and initialize model."""
        # Settings are already loaded by get_instance(), just get them
        settings = self.settings_service.get_settings()
        
        profiles_data = settings.get("moves_list_profiles", {})
        active_profile = settings.get("active_profile", DEFAULT_PROFILE_NAME)
        profile_order = settings.get("profile_order", None)  # Load creation order
        
        self.profile_model.load_profiles(profiles_data, active_profile, profile_order)
        
        # Ensure active profile is properly set after loading
        # This ensures signals are emitted for column visibility changes
        if active_profile in self.profile_model.get_profile_names():
            # Set active profile again to trigger signals
            self.profile_model.set_active_profile(active_profile)
    
    def _save_settings(self) -> bool:
        """Save current settings to file.
        
        Returns:
            True if save was successful, False otherwise.
        """
        profiles_dict = self.profile_model.to_dict()
        
        # Update settings through UserSettingsService
        self.settings_service.update_moves_list_profiles(profiles_dict["moves_list_profiles"])
        self.settings_service.update_active_profile(profiles_dict["active_profile"])
        self.settings_service.update_profile_order(profiles_dict.get("profile_order", []))
        
        # Persist to file
        return self.settings_service.save()
    
    def save_settings(self) -> bool:
        """Public method to save settings (for external use).
        
        Returns:
            True if save was successful, False otherwise.
        """
        result = self._save_settings()
        
        # Log column profile saved
        if result:
            logging_service = LoggingService.get_instance()
            active_profile = self.profile_model.active_profile_name
            profile_count = len(self.profile_model.get_all_profiles())
            column_count = len(self.profile_model.get_profile_columns(active_profile)) if active_profile else 0
            logging_service.info(f"Column profile saved: profile={active_profile}, profile_count={profile_count}, column_count={column_count}")
        
        return result
    
    def get_profile_model(self) -> ColumnProfileModel:
        """Get the column profile model.
        
        Returns:
            The ColumnProfileModel instance for observing profile state.
        """
        return self.profile_model
    
    def set_active_profile(self, profile_name: str) -> bool:
        """Set the active profile.
        
        Note: This does NOT persist changes to the previous profile.
        The user must explicitly save using update_current_profile() to persist changes.
        When switching profiles, the profile is reloaded from saved settings to ensure
        the correct state is displayed (not the modified in-memory state).
        
        Args:
            profile_name: Name of the profile to activate.
            
        Returns:
            True if profile was set, False if profile doesn't exist.
        """
        # Check if we're switching to a different profile
        current_profile = self.profile_model.get_active_profile_name()
        if current_profile == profile_name:
            # Already on this profile, just ensure signals are emitted
            self.profile_model.set_active_profile(profile_name)
            return True
        
        # Reload profiles from saved settings to ensure we're using the saved state,
        # not the modified in-memory state
        # Settings are already loaded by get_instance(), just get them
        settings = self.settings_service.get_settings()
        profiles_data = settings.get("moves_list_profiles", {})
        active_profile = settings.get("active_profile", profile_name)
        profile_order = settings.get("profile_order", None)  # Load creation order
        
        # Reload all profiles from saved settings
        self.profile_model.load_profiles(profiles_data, active_profile, profile_order)
        
        # Now switch to the requested profile (this will use the reloaded profile data)
        success = self.profile_model.set_active_profile(profile_name)
        
        # Update the active profile name in memory (will be saved on explicit save or exit)
        if success:
            self.settings_service.update_active_profile(profile_name)
        return success
    
    def add_profile(self, profile_name: str) -> tuple[bool, str]:
        """Add a new profile based on current column configuration.
        
        Args:
            profile_name: Name of the new profile.
            
        Returns:
            Tuple of (success: bool, message: str).
            If success is True, message indicates success.
            If success is False, message indicates the error.
        """
        # Validate profile name
        if not profile_name or not profile_name.strip():
            return (False, "Profile name cannot be empty")
        
        profile_name = profile_name.strip()
        
        # Check minimum length
        if len(profile_name) < 3:
            return (False, "Profile name must be at least 3 characters")
        
        # Check if profile already exists
        if profile_name in self.profile_model.get_profile_names():
            return (False, f"Profile '{profile_name}' already exists")
        
        # Get current column configuration for the new profile (before reloading)
        # This captures the current state including any unsaved changes to the active profile
        active_profile = self.profile_model._profiles[self.profile_model.get_active_profile_name()]
        columns = {}
        for col_name in self.profile_model.get_column_names():
            visible = active_profile.is_column_visible(col_name)
            col_config = {"visible": visible}
            # Copy width if it exists
            if col_name in active_profile.columns:
                width = active_profile.columns[col_name].get("width")
                if width is not None:
                    col_config["width"] = width
            columns[col_name] = col_config
        
        # Capture column_order from active profile
        column_order = active_profile.column_order.copy() if active_profile.column_order else None
        
        # Reload all profiles from saved settings to restore Default (and other profiles) to their saved state
        # This prevents unsaved changes from being persisted
        # Settings are already loaded by get_instance(), just get them
        settings = self.settings_service.get_settings()
        profiles_data = settings.get("moves_list_profiles", {})
        active_profile_name = settings.get("active_profile", DEFAULT_PROFILE_NAME)
        profile_order = settings.get("profile_order", None)
        
        # Reload profiles (this restores Default to its saved state)
        self.profile_model.load_profiles(profiles_data, active_profile_name, profile_order)
        
        # Now add the new profile with the captured configuration
        success = self.profile_model.add_profile(profile_name, columns, column_order)
        if success:
            # Save settings (Default is now restored to saved state, new profile is added)
            self._save_settings()
            return (True, f"Profile '{profile_name}' saved")
        else:
            return (False, f"Failed to add profile '{profile_name}'")
    
    def remove_profile(self, profile_name: str) -> tuple[bool, str]:
        """Remove a profile.
        
        Args:
            profile_name: Name of the profile to remove.
            
        Returns:
            Tuple of (success: bool, message: str).
            If success is True, message indicates success.
            If success is False, message indicates the error.
        """
        # Cannot remove default profile
        if profile_name == DEFAULT_PROFILE_NAME:
            return (False, "Cannot remove default profile")
        
        success = self.profile_model.remove_profile(profile_name)
        
        if success:
            self._save_settings()
            return (True, f"Profile '{profile_name}' removed")
        else:
            return (False, f"Failed to remove profile '{profile_name}'")
    
    def toggle_column_visibility(self, column_name: str) -> bool:
        """Toggle visibility of a column in the active profile.
        
        Note: This does NOT persist the changes. Call save_settings() or update_current_profile()
        to persist changes.
        
        Args:
            column_name: Name of the column to toggle.
            
        Returns:
            True if column is now visible, False if hidden.
        """
        visible = self.profile_model.toggle_column_visibility(column_name)
        # Don't save automatically - user must explicitly save
        return visible
    
    def update_current_profile(self) -> tuple[bool, str]:
        """Update the current active profile with current column configuration.
        
        This overwrites the current profile with the current column visibility
        and widths from the view. Cannot be used on default profile.
        
        Returns:
            Tuple of (success: bool, message: str).
            If success is True, message indicates success.
            If success is False, message indicates the error.
        """
        active_profile_name = self.profile_model.get_active_profile_name()
        
        # Cannot update default profile
        if active_profile_name == DEFAULT_PROFILE_NAME:
            return (False, "Cannot update default profile")
        
        # The profile model already has the current state (from toggle operations)
        # We just need to save it
        success = self._save_settings()
        
        if success:
            return (True, f"Profile '{active_profile_name}' saved")
        else:
            return (False, f"Failed to save profile '{active_profile_name}'")
    
    def get_column_visibility(self) -> Dict[str, bool]:
        """Get current column visibility state.
        
        Returns:
            Dictionary mapping column names to visibility (True/False).
        """
        return self.profile_model.get_current_column_visibility()
    
    def get_column_widths(self) -> Dict[str, int]:
        """Get current column widths from active profile.
        
        Returns:
            Dictionary mapping column names to widths.
            
        Raises:
            RuntimeError: If any column width is missing from user_settings.json.
        """
        return self.profile_model.get_current_column_widths()
    
    def update_column_widths(self, widths: Dict[str, int]) -> None:
        """Update column widths in the current active profile.
        
        Note: This does NOT persist the changes. Call save_settings() or update_current_profile()
        to persist changes.
        
        Args:
            widths: Dictionary mapping column names to widths.
        """
        self.profile_model.update_current_profile_column_widths(widths)
    
    def get_current_profile_state(self) -> Dict[str, Any]:
        """Get current in-memory state of active profile (not persisted to disk).
        
        This is used by dialogs to load the current state, including unsaved changes.
        
        Returns:
            Dictionary with keys:
            - 'visibility': Dict[str, bool] - column visibility
            - 'order': List[str] - column order
            - 'widths': Dict[str, int] - column widths
        """
        active_profile_name = self.profile_model.get_active_profile_name()
        active_profile = self.profile_model._profiles.get(active_profile_name)
        
        if not active_profile:
            # Fallback to default if profile doesn't exist
            return self.get_persisted_profile_state()
        
        visibility = {}
        widths = {}
        
        for column_name in self.profile_model.get_column_names():
            visibility[column_name] = active_profile.is_column_visible(column_name)
            widths[column_name] = active_profile.get_column_width(column_name)
        
        # Get current order from active profile
        default_order = self.profile_model._column_names.copy()
        order = active_profile.get_column_order(default_order).copy()
        
        return {
            'visibility': visibility,
            'order': order,
            'widths': widths
        }
    
    def get_persisted_profile_state(self) -> Dict[str, Any]:
        """Get persisted state of active profile from disk (not in-memory model).
        
        This is used by dialogs to get the initial state for cancel/reset functionality.
        
        Returns:
            Dictionary with keys:
            - 'visibility': Dict[str, bool] - column visibility
            - 'order': List[str] - column order
            - 'widths': Dict[str, int] - column widths
        """
        settings = self.settings_service.get_settings()
        active_profile_name = self.profile_model.get_active_profile_name()
        profiles_data = settings.get("moves_list_profiles", {})
        profile_data = profiles_data.get(active_profile_name, {})
        
        columns_data = profile_data.get("columns", {})
        visibility = {}
        widths = {}
        
        for column_name in self.profile_model.get_column_names():
            col_config = columns_data.get(column_name, {})
            visibility[column_name] = col_config.get("visible", True)
            # Get width from persisted state, fallback to default if missing
            if "width" in col_config:
                widths[column_name] = col_config["width"]
            else:
                # Use default width from active profile if available
                active_profile = self.profile_model._profiles.get(active_profile_name)
                if active_profile:
                    widths[column_name] = active_profile.get_column_width(column_name)
                else:
                    # Fallback to a reasonable default
                    widths[column_name] = 100
        
        # Get persisted order from settings
        order = profile_data.get("column_order", None)
        if order is not None:
            order = order.copy()
        else:
            # If no persisted order, use current profile's order (which might be default)
            active_profile = self.profile_model._profiles.get(active_profile_name)
            if active_profile:
                default_order = self.profile_model._column_names.copy()
                order = active_profile.get_column_order(default_order).copy()
            else:
                order = self.profile_model._column_names.copy()
        
        return {
            'visibility': visibility,
            'order': order,
            'widths': widths
        }
    
    def apply_dialog_changes(
        self,
        visibility: Dict[str, bool],
        order: List[str],
        widths: Dict[str, int]
    ) -> None:
        """Apply changes from dialog to active profile (in-memory only).
        
        Note: Does NOT persist to disk. User must save profile explicitly.
        
        Args:
            visibility: Dictionary mapping column names to visibility.
            order: List of column names in display order.
            widths: Dictionary mapping column names to widths.
        """
        active_profile = self.profile_model._profiles.get(
            self.profile_model.get_active_profile_name())
        if not active_profile:
            return
        
        # Update visibility
        for column_name, visible in visibility.items():
            active_profile.set_column_visible(column_name, visible)
            # Emit signal for UI updates
            self.profile_model.column_visibility_changed.emit(column_name, visible)
        
        # Update order
        active_profile.set_column_order(order)
        
        # Update widths
        for column_name, width in widths.items():
            active_profile.set_column_width(column_name, width)
    
    def clear_all_columns(self) -> Dict[str, bool]:
        """Clear all columns except COL_NUM in active profile.
        
        Returns:
            Dictionary mapping column names to new visibility state.
        """
        from app.models.column_profile_model import COL_NUM
        
        active_profile = self.profile_model._profiles.get(
            self.profile_model.get_active_profile_name())
        if not active_profile:
            return {}
        
        visibility = {}
        for column_name in self.profile_model.get_column_names():
            visible = (column_name == COL_NUM)  # Only COL_NUM visible
            active_profile.set_column_visible(column_name, visible)
            visibility[column_name] = visible
            # Emit signal
            self.profile_model.column_visibility_changed.emit(column_name, visible)
        
        return visibility

