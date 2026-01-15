"""User settings service for loading and saving user preferences."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from app.models.column_profile_model import DEFAULT_PROFILE_NAME
from app.models.user_settings_model import UserSettingsModel
from app.utils.path_resolver import resolve_data_file_path, get_app_root, get_app_resource_path
from app.services.logging_service import LoggingService


class UserSettingsService:
    """Service for managing user settings persistence.
    
    This service handles loading and saving user preferences to a JSON file.
    Settings are stored in the app root directory as user_settings.json.
    
    This is a singleton service - use get_instance() to get the shared instance.
    """
    
    _instance: Optional['UserSettingsService'] = None
    
    def __init__(self, settings_path: Optional[Path] = None) -> None:
        """Initialize the user settings service.
        
        Args:
            settings_path: Path to user_settings.json. If None, uses smart path resolution
                          (app root if writable, otherwise user data directory).
        """
        # Load filenames from config.json
        self._load_config_filenames()
        
        if settings_path is None:
            # Use smart path resolution: check write access to app root,
            # fall back to user data directory if needed
            settings_path, _ = resolve_data_file_path(self._settings_filename)
        
        self.settings_path = settings_path
        self._model: Optional[UserSettingsModel] = None
        self._migration_done = False
    
    def _load_config_filenames(self) -> None:
        """Load settings filenames from config.json.
        
        Falls back to defaults if config.json is unavailable or doesn't contain the settings.
        """
        try:
            config_path = get_app_resource_path("app/config/config.json")
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                
                user_settings_config = config.get("user_settings", {})
                self._settings_filename = user_settings_config.get("filename", "user_settings.json")
                self._template_filename = user_settings_config.get("template_filename", "user_settings.json.template")
            else:
                # Config file doesn't exist, use defaults
                self._settings_filename = "user_settings.json"
                self._template_filename = "user_settings.json.template"
        except (json.JSONDecodeError, IOError, KeyError):
            # Config is corrupted or missing, use defaults
            self._settings_filename = "user_settings.json"
            self._template_filename = "user_settings.json.template"
    
    def _get_template_path(self) -> Path:
        """Get the path to the template file (always in app root).
        
        Returns:
            Path to template file in app root directory.
        """
        app_root = get_app_root()
        return app_root / self._template_filename
    
    def _load_template(self) -> Optional[Dict[str, Any]]:
        """Load template file as reference defaults.
        
        Returns:
            Template settings dict if template exists, None otherwise.
        """
        template_path = self._get_template_path()
        if not template_path.exists():
            return None
        
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            # Template is corrupted or unreadable, ignore it
            return None
    
    def _extract_all_column_names(self, template_settings: Dict[str, Any]) -> set:
        """Extract all unique column names from all profiles in template.
        
        Args:
            template_settings: Template settings dictionary.
            
        Returns:
            Set of all column names found in any profile.
        """
        column_names = set()
        profiles = template_settings.get("moves_list_profiles", {})
        for profile_data in profiles.values():
            columns = profile_data.get("columns", {})
            column_names.update(columns.keys())
        return column_names
    
    def _merge_template_defaults(self, template_settings: Dict[str, Any]) -> None:
        """Merge missing keys from template into current settings.
        
        Only adds missing top-level keys and missing sub-keys within existing sections.
        Does not overwrite existing user settings.
        
        Args:
            template_settings: Settings loaded from template file.
        """
        for key, template_value in template_settings.items():
            if key not in self._settings:
                # Entire section missing - add from template
                self._settings[key] = self._deep_copy(template_value)
            elif isinstance(template_value, dict) and isinstance(self._settings[key], dict):
                # Section exists - merge missing sub-keys recursively
                self._merge_dict_defaults(self._settings[key], template_value)
    
    def _merge_dict_defaults(self, target: Dict[str, Any], source: Dict[str, Any]) -> bool:
        """Recursively merge missing keys from source into target.
        
        Args:
            target: Target dictionary to merge into.
            source: Source dictionary to merge from.
            
        Returns:
            True if any keys were added, False otherwise.
        """
        changed = False
        for key, source_value in source.items():
            if key not in target:
                # Key missing - add from source
                target[key] = self._deep_copy(source_value)
                changed = True
            elif isinstance(source_value, dict) and isinstance(target[key], dict):
                # Both are dicts - recurse
                if self._merge_dict_defaults(target[key], source_value):
                    changed = True
            # If key exists and is not a dict, don't overwrite existing user settings
        return changed
    
    def _migrate_column_profiles(self, current_settings: Dict[str, Any], template_settings: Dict[str, Any]) -> bool:
        """Migrate column profiles to ensure all columns exist with proper structure.
        
        Args:
            current_settings: Current user settings.
            template_settings: Template settings.
            
        Returns:
            True if any changes were made, False otherwise.
        """
        changed = False
        current_profiles = current_settings.get("moves_list_profiles", {})
        template_profiles = template_settings.get("moves_list_profiles", {})
        
        # Ensure default profile exists
        if DEFAULT_PROFILE_NAME not in current_profiles:
            if DEFAULT_PROFILE_NAME in template_profiles:
                current_profiles[DEFAULT_PROFILE_NAME] = self._deep_copy(template_profiles[DEFAULT_PROFILE_NAME])
                changed = True
            else:
                current_profiles[DEFAULT_PROFILE_NAME] = {"columns": {}}
                changed = True
        
        # Extract all column names from template
        all_column_names = self._extract_all_column_names(template_settings)
        
        # Get default profile columns from template for fallback values
        default_profile = template_profiles.get(DEFAULT_PROFILE_NAME, {})
        default_columns = default_profile.get("columns", {})
        
        # Migrate each profile
        for profile_name, profile_data in current_profiles.items():
            if "columns" not in profile_data:
                profile_data["columns"] = {}
                changed = True
            
            # Ensure all columns exist and have width parameters
            for col_name in all_column_names:
                if col_name not in profile_data["columns"]:
                    # Column missing, add from template defaults if available
                    if col_name in default_columns:
                        profile_data["columns"][col_name] = default_columns[col_name].copy()
                    else:
                        # Column exists in template but not in default profile - check other profiles
                        found_col = None
                        for template_profile_data in template_profiles.values():
                            template_cols = template_profile_data.get("columns", {})
                            if col_name in template_cols:
                                found_col = template_cols[col_name]
                                break
                        
                        if found_col:
                            profile_data["columns"][col_name] = found_col.copy()
                        else:
                            # Fallback: use reasonable defaults
                            profile_data["columns"][col_name] = {"visible": False, "width": 100}
                    changed = True
                elif "width" not in profile_data["columns"][col_name]:
                    # Column exists but missing width, add width from template defaults
                    default_col = default_columns.get(col_name, {})
                    if "width" in default_col:
                        profile_data["columns"][col_name]["width"] = default_col["width"]
                    else:
                        profile_data["columns"][col_name]["width"] = 100
                    changed = True
        
        return changed
    
    @classmethod
    def get_instance(cls, settings_path: Optional[Path] = None) -> 'UserSettingsService':
        """Get the singleton instance of UserSettingsService.
        
        Args:
            settings_path: Path to user_settings.json. Only used on first creation.
            
        Returns:
            The singleton UserSettingsService instance.
        """
        if cls._instance is None:
            cls._instance = cls(settings_path)
            # Load settings on first creation
            cls._instance.load()
            # Run migration once on first access
            cls._instance.migrate()
        return cls._instance
    
    def get_model(self) -> UserSettingsModel:
        """Get the user settings model.
        
        Returns:
            UserSettingsModel instance.
        """
        if self._model is None:
            # Initialize model with empty settings if not loaded yet
            self._model = UserSettingsModel({})
        return self._model
    
    def load(self) -> Dict[str, Any]:
        """Load user settings from file.
        
        Simple loading without migration. Migration is handled separately by migrate().
        
        Returns:
            Loaded settings dictionary. If file doesn't exist, returns empty dict.
        """
        if not self.settings_path.exists():
            # File doesn't exist, start with empty settings
            # Migration will populate from template
            settings = {}
        else:
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                # File is corrupted or unreadable, start with empty settings
                logging_service = LoggingService.get_instance()
                logging_service.warning(f"Failed to load user settings: {e}. Starting with empty settings.", exc_info=e)
                settings = {}
        
        # Initialize model with loaded settings
        self._model = UserSettingsModel(settings)
        settings_dict = self._model.get_settings()
        
        # Log user settings loaded
        logging_service = LoggingService.get_instance()
        settings_count = len(settings_dict) if isinstance(settings_dict, dict) else 0
        logging_service.info(f"User settings loaded: path={self.settings_path}, {settings_count} setting(s)")
        
        return settings_dict
    
    def migrate(self) -> None:
        """Migrate settings by adding missing keys from template.
        
        This method checks if any model settings are missing in the user settings file
        and migrates them from the template file. Runs once on first access.
        """
        if self._migration_done:
            return
        
        # Load template - it's the source of truth
        template_settings = self._load_template()
        if not template_settings:
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Template file not found at {self._get_template_path()}. Cannot migrate settings.")
            self._migration_done = True
            return
        
        model = self.get_model()
        current_settings = model.get_settings()
        
        # Check what's missing and merge from template
        needs_save = False
        
        # Merge missing top-level sections
        for key, template_value in template_settings.items():
            if key not in current_settings:
                # Entire section missing - add from template
                if key == "moves_list_profiles":
                    model.set_moves_list_profiles(template_value)
                elif key == "active_profile":
                    model.set_active_profile(template_value)
                elif key == "profile_order":
                    model.set_profile_order(template_value)
                elif key == "board_visibility":
                    model.set_board_visibility(template_value)
                elif key == "pgn_visibility":
                    model.set_pgn_visibility(template_value)
                elif key == "game_analysis":
                    model.set_game_analysis(template_value)
                elif key == "game_analysis_settings":
                    model.set_game_analysis_settings(template_value)
                elif key == "manual_analysis":
                    model.set_manual_analysis(template_value)
                elif key == "annotations":
                    model.set_annotations(template_value)
                elif key == "engines":
                    model.set_engines(template_value)
                elif key == "engine_assignments":
                    model.set_engine_assignments(template_value)
                elif key == "ai_models":
                    model.set_ai_models(template_value)
                elif key == "ai_summary":
                    model.set_ai_summary(template_value)
                else:
                    # Unknown key - add directly via update_from_dict
                    updated_settings = current_settings.copy()
                    updated_settings[key] = self._deep_copy(template_value)
                    model.update_from_dict(updated_settings)
                needs_save = True
                # Refresh current_settings after model update
                current_settings = model.get_settings()
            elif isinstance(template_value, dict) and isinstance(current_settings.get(key), dict):
                # Section exists - merge missing sub-keys recursively
                section_dict = current_settings[key].copy()
                if self._merge_dict_defaults(section_dict, template_value):
                    # Update model with merged section
                    if key == "moves_list_profiles":
                        model.set_moves_list_profiles(section_dict)
                    elif key == "board_visibility":
                        model.set_board_visibility(section_dict)
                    elif key == "pgn_visibility":
                        model.set_pgn_visibility(section_dict)
                    elif key == "pgn_notation":
                        model.set_pgn_notation(section_dict)
                    elif key == "game_analysis":
                        model.set_game_analysis(section_dict)
                    elif key == "game_analysis_settings":
                        model.set_game_analysis_settings(section_dict)
                    elif key == "manual_analysis":
                        model.set_manual_analysis(section_dict)
                    elif key == "annotations":
                        model.set_annotations(section_dict)
                    elif key == "engine_assignments":
                        model.set_engine_assignments(section_dict)
                    elif key == "ai_models":
                        model.set_ai_models(section_dict)
                    elif key == "ai_summary":
                        model.set_ai_summary(section_dict)
                    needs_save = True
                    # Refresh current_settings after model update
                    current_settings = model.get_settings()
        
        # Special handling for column profiles - ensure all columns exist
        current_settings = model.get_settings()
        if "moves_list_profiles" in current_settings:
            profiles_dict = current_settings["moves_list_profiles"].copy()
            if self._migrate_column_profiles(profiles_dict, template_settings):
                model.set_moves_list_profiles(profiles_dict)
                needs_save = True
        
        # Special handling for AI summary - ensure mutual exclusivity
        current_settings = model.get_settings()
        if "ai_summary" in current_settings:
            ai_summary = current_settings["ai_summary"].copy()
            self._normalize_ai_summary_settings(ai_summary)
            model.set_ai_summary(ai_summary)
        
        # Mark migration as done
        self._migration_done = True
        
        # Save if anything changed
        if needs_save:
            try:
                self.save()
            except Exception as e:
                logging_service = LoggingService.get_instance()
                logging_service.warning(f"Failed to save migrated settings: {e}.", exc_info=e)
    
    def save(self) -> bool:
        """Save current settings state to file.
        
        Persists the current model state to user_settings.json.
        
        Returns:
            True if save was successful, False otherwise.
        """
        try:
            model = self.get_model()
            settings = model.to_dict()
            
            # Ensure directory exists
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write to a temporary file first, then rename (atomic operation)
            temp_path = self.settings_path.with_suffix('.tmp')
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            
            # Atomic rename
            temp_path.replace(self.settings_path)
            
            # Log user settings saved
            logging_service = LoggingService.get_instance()
            settings_count = len(settings) if isinstance(settings, dict) else 0
            logging_service.info(f"User settings saved: path={self.settings_path}, {settings_count} setting(s)")
            
            return True
        except IOError as e:
            logging_service = LoggingService.get_instance()
            logging_service.error(f"Failed to save user settings: {e}", exc_info=e)
            return False
    
    def get_settings(self) -> Dict[str, Any]:
        """Get current settings.
        
        Returns:
            Current settings dictionary (read-only access).
        """
        return self.get_model().get_settings()
    
    def update_board_visibility(self, visibility: Dict[str, bool]) -> None:
        """Update board visibility settings.
        
        Args:
            visibility: Dictionary with board visibility settings.
        """
        model = self.get_model()
        current = model.get_board_visibility()
        current.update(visibility)
        model.set_board_visibility(current)
    
    def update_pgn_visibility(self, visibility: Dict[str, bool]) -> None:
        """Update PGN visibility settings.
        
        Args:
            visibility: Dictionary with PGN visibility settings.
        """
        model = self.get_model()
        current = model.get_pgn_visibility()
        current.update(visibility)
        model.set_pgn_visibility(current)
    
    def update_pgn_notation(self, notation: Dict[str, Any]) -> None:
        """Update PGN notation settings.
        
        Args:
            notation: Dictionary with PGN notation settings.
        """
        model = self.get_model()
        current = model.get_pgn_notation()
        current.update(notation)
        model.set_pgn_notation(current)
    
    def update_game_analysis(self, settings: Dict[str, Any]) -> None:
        """Update game analysis settings (menu toggles).
        
        Args:
            settings: Dictionary with game analysis settings.
        """
        model = self.get_model()
        current = model.get_game_analysis()
        current.update(settings)
        model.set_game_analysis(current)
    
    def update_game_analysis_settings(self, settings: Dict[str, Any]) -> None:
        """Update game analysis classification settings.
        
        Args:
            settings: Dictionary with classification settings (assessment_thresholds, brilliant_criteria).
                     If empty dict, clears the section.
        """
        model = self.get_model()
        if not settings:
            # Clear the section if empty dict is passed
            current = model.get_settings()
            if "game_analysis_settings" in current:
                del current["game_analysis_settings"]
                model.update_from_dict(current)
        else:
            current = model.get_game_analysis_settings()
            current.update(settings)
            model.set_game_analysis_settings(current)
    
    def update_manual_analysis(self, settings: Dict[str, Any]) -> None:
        """Update manual analysis settings.
        
        Args:
            settings: Dictionary with manual analysis settings.
        """
        model = self.get_model()
        current = model.get_manual_analysis()
        current.update(settings)
        model.set_manual_analysis(current)
    
    def update_annotations(self, settings: Dict[str, Any]) -> None:
        """Update annotation preferences.
        
        Args:
            settings: Dictionary with annotation settings (preset_colors, text_font_family, text_font_size).
        """
        model = self.get_model()
        current = model.get_annotations()
        current.update(settings)
        model.set_annotations(current)
    
    def update_engines(self, engines: list) -> None:
        """Update engine list.
        
        Args:
            engines: List of engine dictionaries.
        """
        self.get_model().set_engines(engines)
    
    def update_engine_assignments(self, assignments: Dict[str, Optional[str]]) -> None:
        """Update engine assignments.
        
        Args:
            assignments: Dictionary mapping engine roles to engine IDs.
        """
        model = self.get_model()
        current = model.get_engine_assignments()
        current.update(assignments)
        model.set_engine_assignments(current)
    
    def update_ai_model_settings(self, settings: Dict[str, Any]) -> None:
        """Update AI model settings.
        
        Args:
            settings: Dictionary with AI model settings (openai, anthropic).
        """
        model = self.get_model()
        current = model.get_ai_models()
        current.update(settings)
        model.set_ai_models(current)
    
    def update_ai_summary_settings(self, settings: Dict[str, Any]) -> None:
        """Update AI summary provider settings.
        
        Args:
            settings: Dictionary with provider toggles (use_openai_models, use_anthropic_models).
        """
        model = self.get_model()
        current = model.get_ai_summary()
        current.update(settings)
        self._normalize_ai_summary_settings(current)
        model.set_ai_summary(current)
    
    def update_moves_list_profiles(self, profiles: Dict[str, Any]) -> None:
        """Update moves list profiles.
        
        Args:
            profiles: Dictionary of profile data.
        """
        model = self.get_model()
        current = model.get_moves_list_profiles()
        current.update(profiles)
        model.set_moves_list_profiles(current)
    
    def update_active_profile(self, profile_name: str) -> None:
        """Update active profile name.
        
        Args:
            profile_name: Name of the active profile.
        """
        self.get_model().set_active_profile(profile_name)

    def _normalize_ai_summary_settings(self, ai_summary_settings: Dict[str, Any]) -> None:
        """Ensure AI summary provider toggles remain mutually exclusive."""
        use_openai = bool(ai_summary_settings.get("use_openai_models", True))
        use_anthropic = bool(ai_summary_settings.get("use_anthropic_models", False))
        
        # Enforce exclusivity: if both or neither are selected, default to OpenAI
        if use_openai == use_anthropic:
            use_openai = True
            use_anthropic = False
        
        ai_summary_settings["use_openai_models"] = use_openai
        ai_summary_settings["use_anthropic_models"] = use_anthropic
    
    def update_profile_order(self, order: list) -> None:
        """Update profile order.
        
        Args:
            order: List of profile names in order.
        """
        self.get_model().set_profile_order(order)
    
    
    def _deep_copy(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a deep copy of a dictionary.
        
        Args:
            data: Dictionary to copy.
            
        Returns:
            Deep copy of the dictionary.
        """
        return json.loads(json.dumps(data))

