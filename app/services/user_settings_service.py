"""User settings service for loading and saving user preferences."""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from app.models.column_profile_model import (DEFAULT_PROFILE_NAME, COL_NUM, COL_WHITE, COL_BLACK, COL_EVAL_WHITE, COL_EVAL_BLACK, 
                                             COL_CPL_WHITE, COL_CPL_BLACK, COL_CPL_WHITE_2, COL_CPL_WHITE_3, COL_CPL_BLACK_2, COL_CPL_BLACK_3,
                                             COL_ASSESS_WHITE, COL_ASSESS_BLACK, COL_BEST_WHITE, 
                                             COL_BEST_BLACK, COL_BEST_WHITE_2, COL_BEST_WHITE_3, COL_BEST_BLACK_2, COL_BEST_BLACK_3,
                                             COL_WHITE_IS_TOP3, COL_BLACK_IS_TOP3, COL_WHITE_DEPTH, COL_BLACK_DEPTH, 
                                             COL_COMMENT, COL_ECO, COL_OPENING, COL_WHITE_CAPTURE, COL_BLACK_CAPTURE,
                                             COL_WHITE_MATERIAL, COL_BLACK_MATERIAL)


class UserSettingsService:
    """Service for managing user settings persistence.
    
    This service handles loading and saving user preferences to a JSON file.
    Settings are stored in the app root directory as user_settings.json.
    
    This is a singleton service - use get_instance() to get the shared instance.
    """
    
    _instance: Optional['UserSettingsService'] = None
    
    DEFAULT_SETTINGS = {
        "moves_list_profiles": {
            DEFAULT_PROFILE_NAME: {
                "columns": {
                    COL_NUM: {"visible": True, "width": 50},
                    COL_WHITE: {"visible": True, "width": 100},
                    COL_BLACK: {"visible": True, "width": 100},
                    COL_EVAL_WHITE: {"visible": True, "width": 90},
                    COL_EVAL_BLACK: {"visible": True, "width": 90},
                    COL_CPL_WHITE: {"visible": True, "width": 90},
                    COL_CPL_BLACK: {"visible": True, "width": 90},
                    COL_CPL_WHITE_2: {"visible": False, "width": 90},
                    COL_CPL_WHITE_3: {"visible": False, "width": 90},
                    COL_CPL_BLACK_2: {"visible": False, "width": 90},
                    COL_CPL_BLACK_3: {"visible": False, "width": 90},
                    COL_ASSESS_WHITE: {"visible": True, "width": 100},
                    COL_ASSESS_BLACK: {"visible": True, "width": 100},
                    COL_BEST_WHITE: {"visible": True, "width": 100},
                    COL_BEST_BLACK: {"visible": True, "width": 100},
                    COL_BEST_WHITE_2: {"visible": False, "width": 100},
                    COL_BEST_WHITE_3: {"visible": False, "width": 100},
                    COL_BEST_BLACK_2: {"visible": False, "width": 100},
                    COL_BEST_BLACK_3: {"visible": False, "width": 100},
                    COL_WHITE_IS_TOP3: {"visible": False, "width": 80},
                    COL_BLACK_IS_TOP3: {"visible": False, "width": 80},
                    COL_WHITE_DEPTH: {"visible": False, "width": 70},
                    COL_BLACK_DEPTH: {"visible": False, "width": 70},
                    COL_ECO: {"visible": True, "width": 60},
                    COL_OPENING: {"visible": True, "width": 150},
                    COL_COMMENT: {"visible": True, "width": 200},
                    COL_WHITE_CAPTURE: {"visible": False, "width": 80},
                    COL_BLACK_CAPTURE: {"visible": False, "width": 80},
                    COL_WHITE_MATERIAL: {"visible": False, "width": 100},
                    COL_BLACK_MATERIAL: {"visible": False, "width": 100}
                }
            }
        },
        "active_profile": DEFAULT_PROFILE_NAME,
        "board_visibility": {
            "show_coordinates": True,
            "show_turn_indicator": True,
            "show_game_info": True,
            "show_playedmove_arrow": True,
            "show_bestnextmove_arrow": True,
            "show_pv2_arrow": True,
            "show_pv3_arrow": True,
            "show_bestalternativemove_arrow": True,
            "show_evaluation_bar": False,
            "show_material_widget": False,
            "hide_other_arrows_during_plan_exploration": False
        },
        "pgn_visibility": {
            "show_metadata": True,
            "show_comments": True,
            "show_variations": True,
            "show_annotations": True,
            "show_results": True,
            "show_non_standard_tags": False
        },
        "game_analysis": {
            "return_to_first_move_after_analysis": False,
            "switch_to_moves_list_at_start_of_analysis": True,
            "switch_to_summary_after_analysis": False,
            "normalized_evaluation_graph": False,
            "post_game_brilliancy_refinement": False,
            "store_analysis_results_in_pgn_tag": False
        },
        "manual_analysis": {
            "max_pieces_to_explore": 1,
            "max_exploration_depth": 2
        },
        "annotations": {
            "preset_colors": None,  # None means use config defaults
            "text_font_family": None,  # None means use config defaults
            "text_font_size": None  # None means use config defaults
        },
        "ai_summary": {
            "use_openai_models": True,
            "use_anthropic_models": False,
            "include_analysis_data_in_preprompt": False,
            "include_metadata_in_preprompt": True
        },
        "engines": [],
        "engine_assignments": {
            "game_analysis": None,
            "evaluation": None,
            "manual_analysis": None
        },
        "ai_models": {
            "openai": {
                "api_key": "",
                "model": "",
                "models": []
            },
            "anthropic": {
                "api_key": "",
                "model": "",
                "models": []
            }
        }
    }
    
    def __init__(self, settings_path: Optional[Path] = None) -> None:
        """Initialize the user settings service.
        
        Args:
            settings_path: Path to user_settings.json. If None, uses app root directory.
        """
        if settings_path is None:
            # Default: user_settings.json in app root directory
            app_root = Path(__file__).parent.parent.parent
            settings_path = app_root / "user_settings.json"
        
        self.settings_path = settings_path
        self._settings: Dict[str, Any] = {}
    
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
        return cls._instance
    
    def load(self) -> Dict[str, Any]:
        """Load user settings from file.
        
        Returns:
            Loaded settings dictionary. If file doesn't exist, returns default settings.
        """
        if not self.settings_path.exists():
            # File doesn't exist, return default settings
            self._settings = self._deep_copy(self.DEFAULT_SETTINGS)
            return self._settings
        
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                self._settings = json.load(f)
            
            # Ensure default profile exists
            if "moves_list_profiles" not in self._settings:
                self._settings["moves_list_profiles"] = {}
            
            if DEFAULT_PROFILE_NAME not in self._settings["moves_list_profiles"]:
                self._settings["moves_list_profiles"][DEFAULT_PROFILE_NAME] = self.DEFAULT_SETTINGS["moves_list_profiles"][DEFAULT_PROFILE_NAME]
            
            # Validate all profiles have all required columns with width parameters
            default_profile = self.DEFAULT_SETTINGS["moves_list_profiles"][DEFAULT_PROFILE_NAME]
            default_columns = default_profile["columns"]
            all_column_names = [COL_NUM, COL_WHITE, COL_BLACK, COL_EVAL_WHITE, COL_EVAL_BLACK,
                              COL_CPL_WHITE, COL_CPL_BLACK, COL_CPL_WHITE_2, COL_CPL_WHITE_3,
                              COL_CPL_BLACK_2, COL_CPL_BLACK_3, COL_ASSESS_WHITE, COL_ASSESS_BLACK,
                              COL_BEST_WHITE, COL_BEST_BLACK, COL_BEST_WHITE_2, COL_BEST_WHITE_3,
                              COL_BEST_BLACK_2, COL_BEST_BLACK_3, COL_WHITE_IS_TOP3, COL_BLACK_IS_TOP3,
                              COL_WHITE_DEPTH, COL_BLACK_DEPTH, COL_ECO, COL_OPENING, COL_COMMENT,
                              COL_WHITE_CAPTURE, COL_BLACK_CAPTURE, COL_WHITE_MATERIAL, COL_BLACK_MATERIAL]
            
            for profile_name, profile_data in self._settings["moves_list_profiles"].items():
                if "columns" not in profile_data:
                    profile_data["columns"] = {}
                
                # Ensure all columns exist and have width parameters
                for col_name in all_column_names:
                    if col_name not in profile_data["columns"]:
                        # Column missing, add from defaults if available, otherwise use defaults
                        if col_name in default_columns:
                            profile_data["columns"][col_name] = default_columns[col_name].copy()
                        else:
                            # New column not in default profile yet - use default values
                            profile_data["columns"][col_name] = {"visible": False, "width": 100}
                    elif "width" not in profile_data["columns"][col_name]:
                        # Column exists but missing width, add width from defaults
                        default_col = default_columns.get(col_name, {})
                        if "width" in default_col:
                            profile_data["columns"][col_name]["width"] = default_col["width"]
                        else:
                            # Fallback to a reasonable default if not in defaults
                            profile_data["columns"][col_name]["width"] = 100
            
            # Ensure active_profile exists
            if "active_profile" not in self._settings:
                self._settings["active_profile"] = DEFAULT_PROFILE_NAME
            
            # Ensure board_visibility exists
            if "board_visibility" not in self._settings:
                self._settings["board_visibility"] = self.DEFAULT_SETTINGS["board_visibility"]
            
            # Ensure pgn_visibility exists
            if "pgn_visibility" not in self._settings:
                self._settings["pgn_visibility"] = self.DEFAULT_SETTINGS["pgn_visibility"]
            else:
                # Ensure all required keys exist in pgn_visibility
                pgn_visibility = self._settings["pgn_visibility"]
                default_pgn_visibility = self.DEFAULT_SETTINGS["pgn_visibility"]
                for key in default_pgn_visibility:
                    if key not in pgn_visibility:
                        pgn_visibility[key] = default_pgn_visibility[key]
            
            # Ensure engines exists
            if "engines" not in self._settings:
                self._settings["engines"] = self.DEFAULT_SETTINGS["engines"]
            
            # Ensure engine_assignments exists
            if "engine_assignments" not in self._settings:
                self._settings["engine_assignments"] = self.DEFAULT_SETTINGS["engine_assignments"]
            
            # Ensure annotations exists
            if "annotations" not in self._settings:
                self._settings["annotations"] = self.DEFAULT_SETTINGS["annotations"]
            else:
                # Ensure all required keys exist in annotations
                annotations = self._settings["annotations"]
                default_annotations = self.DEFAULT_SETTINGS["annotations"]
                for key in default_annotations:
                    if key not in annotations:
                        annotations[key] = default_annotations[key]
            
            # Ensure AI summary settings exist and remain mutually exclusive
            ai_summary_defaults = self.DEFAULT_SETTINGS.get("ai_summary", {})
            ai_summary_settings = self._settings.setdefault("ai_summary", ai_summary_defaults.copy())
            for key, value in ai_summary_defaults.items():
                ai_summary_settings.setdefault(key, value)
            self._normalize_ai_summary_settings(ai_summary_settings)
            
            # Ensure AI model settings include required keys
            ai_models_defaults = self.DEFAULT_SETTINGS.get("ai_models", {})
            ai_models_settings = self._settings.setdefault("ai_models", self._deep_copy(ai_models_defaults))
            for provider_key, provider_defaults in ai_models_defaults.items():
                provider_settings = ai_models_settings.setdefault(provider_key, {})
                for setting_key, default_value in provider_defaults.items():
                    if setting_key not in provider_settings:
                        provider_settings[setting_key] = self._deep_copy(default_value) if isinstance(default_value, (dict, list)) else default_value
                if not isinstance(provider_settings.get("models"), list):
                    provider_settings["models"] = []
            
            # Save migrated settings back to file (to persist new columns)
            # This ensures that the next time the application starts, all columns are already present
            try:
                self.save()
            except Exception:
                # If save fails, continue anyway - migration will happen again next time
                pass
            
            return self._settings
        except (json.JSONDecodeError, IOError) as e:
            # If file is corrupted or can't be read, use defaults
            print(f"Warning: Failed to load user settings: {e}. Using defaults.", file=sys.stderr)
            self._settings = self._deep_copy(self.DEFAULT_SETTINGS)
            return self._settings
    
    def save(self) -> bool:
        """Save current settings state to file.
        
        Persists the current internal state to user_settings.json.
        
        Returns:
            True if save was successful, False otherwise.
        """
        try:
            # Ensure directory exists
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write to a temporary file first, then rename (atomic operation)
            temp_path = self.settings_path.with_suffix('.tmp')
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2, ensure_ascii=False)
            
            # Atomic rename
            temp_path.replace(self.settings_path)
            
            return True
        except IOError as e:
            print(f"Error: Failed to save user settings: {e}", file=sys.stderr)
            return False
    
    def get_settings(self) -> Dict[str, Any]:
        """Get current settings.
        
        Returns:
            Current settings dictionary (read-only access).
        """
        return self._settings
    
    def update_board_visibility(self, visibility: Dict[str, bool]) -> None:
        """Update board visibility settings.
        
        Args:
            visibility: Dictionary with board visibility settings.
        """
        if "board_visibility" not in self._settings:
            self._settings["board_visibility"] = {}
        self._settings["board_visibility"].update(visibility)
    
    def update_pgn_visibility(self, visibility: Dict[str, bool]) -> None:
        """Update PGN visibility settings.
        
        Args:
            visibility: Dictionary with PGN visibility settings.
        """
        if "pgn_visibility" not in self._settings:
            self._settings["pgn_visibility"] = {}
        self._settings["pgn_visibility"].update(visibility)
    
    def update_game_analysis(self, settings: Dict[str, Any]) -> None:
        """Update game analysis settings (menu toggles).
        
        Args:
            settings: Dictionary with game analysis settings.
        """
        if "game_analysis" not in self._settings:
            self._settings["game_analysis"] = {}
        self._settings["game_analysis"].update(settings)
    
    def update_game_analysis_settings(self, settings: Dict[str, Any]) -> None:
        """Update game analysis classification settings.
        
        Args:
            settings: Dictionary with classification settings (assessment_thresholds, brilliant_criteria).
                     If empty dict, clears the section.
        """
        if not settings:
            # Clear the section if empty dict is passed
            if "game_analysis_settings" in self._settings:
                del self._settings["game_analysis_settings"]
        else:
            if "game_analysis_settings" not in self._settings:
                self._settings["game_analysis_settings"] = {}
            self._settings["game_analysis_settings"].update(settings)
    
    def update_manual_analysis(self, settings: Dict[str, Any]) -> None:
        """Update manual analysis settings.
        
        Args:
            settings: Dictionary with manual analysis settings.
        """
        if "manual_analysis" not in self._settings:
            self._settings["manual_analysis"] = {}
        self._settings["manual_analysis"].update(settings)
    
    def update_annotations(self, settings: Dict[str, Any]) -> None:
        """Update annotation preferences.
        
        Args:
            settings: Dictionary with annotation settings (preset_colors, text_font_family, text_font_size).
        """
        if "annotations" not in self._settings:
            self._settings["annotations"] = {}
        self._settings["annotations"].update(settings)
    
    def update_engines(self, engines: list) -> None:
        """Update engine list.
        
        Args:
            engines: List of engine dictionaries.
        """
        self._settings["engines"] = engines
    
    def update_engine_assignments(self, assignments: Dict[str, Optional[str]]) -> None:
        """Update engine assignments.
        
        Args:
            assignments: Dictionary mapping engine roles to engine IDs.
        """
        if "engine_assignments" not in self._settings:
            self._settings["engine_assignments"] = {}
        self._settings["engine_assignments"].update(assignments)
    
    def update_ai_model_settings(self, settings: Dict[str, Any]) -> None:
        """Update AI model settings.
        
        Args:
            settings: Dictionary with AI model settings (openai, anthropic).
        """
        if "ai_models" not in self._settings:
            self._settings["ai_models"] = {}
        self._settings["ai_models"].update(settings)
    
    def update_ai_summary_settings(self, settings: Dict[str, Any]) -> None:
        """Update AI summary provider settings.
        
        Args:
            settings: Dictionary with provider toggles (use_openai_models, use_anthropic_models).
        """
        ai_summary = self._settings.setdefault("ai_summary", self.DEFAULT_SETTINGS["ai_summary"].copy())
        ai_summary.update(settings)
        self._normalize_ai_summary_settings(ai_summary)
    
    def update_moves_list_profiles(self, profiles: Dict[str, Any]) -> None:
        """Update moves list profiles.
        
        Args:
            profiles: Dictionary of profile data.
        """
        if "moves_list_profiles" not in self._settings:
            self._settings["moves_list_profiles"] = {}
        self._settings["moves_list_profiles"].update(profiles)
    
    def update_active_profile(self, profile_name: str) -> None:
        """Update active profile name.
        
        Args:
            profile_name: Name of the active profile.
        """
        self._settings["active_profile"] = profile_name

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
        self._settings["profile_order"] = order
    
    
    def _deep_copy(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a deep copy of a dictionary.
        
        Args:
            data: Dictionary to copy.
            
        Returns:
            Deep copy of the dictionary.
        """
        return json.loads(json.dumps(data))

