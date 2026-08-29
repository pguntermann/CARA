"""User settings model for managing application-wide user preferences."""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Dict, Any, Optional, List


class UserSettingsModel(QObject):
    """Model representing user settings state.
    
    This model holds user preferences and emits signals when settings change.
    Views observe these signals to update the UI automatically.
    """
    
    # Signals emitted when settings change
    settings_changed = pyqtSignal()  # Emitted when any setting changes
    moves_list_profiles_changed = pyqtSignal()  # Emitted when column profiles change
    active_profile_changed = pyqtSignal(str)  # Emitted when active profile changes (profile_name)
    player_stats_profiles_changed = pyqtSignal()  # Emitted when Player Stats profiles change
    player_stats_active_profile_changed = pyqtSignal(str)  # Emitted when active Player Stats profile changes
    board_visibility_changed = pyqtSignal()  # Emitted when board visibility settings change
    pgn_visibility_changed = pyqtSignal()  # Emitted when PGN visibility settings change
    pgn_notation_changed = pyqtSignal()  # Emitted when PGN notation settings change
    game_analysis_changed = pyqtSignal()  # Emitted when game analysis settings change
    manual_analysis_changed = pyqtSignal()  # Emitted when manual analysis settings change
    annotations_changed = pyqtSignal()  # Emitted when annotation settings change
    ai_settings_changed = pyqtSignal()  # Emitted when AI settings change
    player_stats_time_series_changed = pyqtSignal()  # Player Stats time-series binning / display prefs
    player_stats_activity_heatmap_changed = pyqtSignal()  # Player Stats activity heatmap display prefs
    player_stats_accuracy_distribution_changed = pyqtSignal()  # Player Stats accuracy histogram prefs
    player_stats_error_patterns_changed = pyqtSignal()  # Player Stats error-pattern coverage cutoff

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the user settings model.
        
        Args:
            settings: Initial settings dictionary. If None, uses empty dict.
        """
        super().__init__()
        self._settings: Dict[str, Any] = settings.copy() if settings else {}
    
    def get_settings(self) -> Dict[str, Any]:
        """Get all settings.
        
        Returns:
            Complete settings dictionary.
        """
        return self._settings.copy()
    
    def get_moves_list_profiles(self) -> Dict[str, Any]:
        """Get moves list profiles.
        
        Returns:
            Dictionary of profile data.
        """
        return self._settings.get("moves_list_profiles", {}).copy()
    
    def set_moves_list_profiles(self, profiles: Dict[str, Any]) -> None:
        """Set moves list profiles.
        
        Args:
            profiles: Dictionary of profile data.
        """
        self._settings["moves_list_profiles"] = profiles.copy()
        self.moves_list_profiles_changed.emit()
        self.settings_changed.emit()
    
    def get_active_profile(self) -> str:
        """Get active profile name.
        
        Returns:
            Active profile name.
        """
        return self._settings.get("active_profile", "Default")
    
    def set_active_profile(self, profile_name: str) -> None:
        """Set active profile.
        
        Args:
            profile_name: Name of the active profile.
        """
        if self._settings.get("active_profile") != profile_name:
            self._settings["active_profile"] = profile_name
            self.active_profile_changed.emit(profile_name)
            self.settings_changed.emit()
    
    def get_profile_order(self) -> list:
        """Get profile order.
        
        Returns:
            List of profile names in order.
        """
        return self._settings.get("profile_order", []).copy()
    
    def set_profile_order(self, order: list) -> None:
        """Set profile order.
        
        Args:
            order: List of profile names in order.
        """
        self._settings["profile_order"] = order.copy()
        self.moves_list_profiles_changed.emit()
        self.settings_changed.emit()
    
    def get_board_visibility(self) -> Dict[str, Any]:
        """Get board visibility settings.
        
        Returns:
            Dictionary of board visibility settings.
        """
        return self._settings.get("board_visibility", {}).copy()
    
    def set_board_visibility(self, settings: Dict[str, Any]) -> None:
        """Set board visibility settings.
        
        Args:
            settings: Dictionary of board visibility settings.
        """
        self._settings["board_visibility"] = settings.copy()
        self.board_visibility_changed.emit()
        self.settings_changed.emit()

    def get_detail_panel_visibility(self) -> Dict[str, bool]:
        """Per-unit visibility for detail tabs / related menus (missing id => True)."""
        from app.services.detail_panel_visibility import normalize_detail_panel_visibility

        raw = self._settings.get("detail_panel_visibility")
        return normalize_detail_panel_visibility(raw if isinstance(raw, dict) else None)

    def set_detail_panel_visibility(self, visibility: Dict[str, bool]) -> None:
        """Replace stored detail-panel visibility map."""
        from app.services.detail_panel_visibility import normalize_detail_panel_visibility

        self._settings["detail_panel_visibility"] = normalize_detail_panel_visibility(
            visibility
        )
        self.settings_changed.emit()

    def update_detail_panel_visibility(self, unit_id: str, visible: bool) -> None:
        """Set one detail-panel unit's visibility."""
        cur = self.get_detail_panel_visibility()
        cur[str(unit_id)] = bool(visible)
        self.set_detail_panel_visibility(cur)

    def get_database_table_columns(self) -> Dict[str, Any]:
        """Global default column layout for the database pane table."""
        from app.services.database_table_columns import normalize_database_table_columns

        raw = self._settings.get("database_table_columns")
        return normalize_database_table_columns(raw if isinstance(raw, dict) else None)

    def set_database_table_columns(self, layout: Dict[str, Any]) -> None:
        """Replace the global database-table column layout."""
        from app.services.database_table_columns import normalize_database_table_columns

        self._settings["database_table_columns"] = normalize_database_table_columns(
            layout if isinstance(layout, dict) else None
        )
        self.settings_changed.emit()

    def get_database_table_columns_by_path(self) -> Dict[str, Dict[str, Any]]:
        """Per-file database-table column layout overrides (keyed by absolute path)."""
        from app.services.database_table_columns import (
            normalize_database_table_columns_by_path,
        )

        raw = self._settings.get("database_table_columns_by_path")
        return normalize_database_table_columns_by_path(
            raw if isinstance(raw, dict) else None
        )

    def set_database_table_columns_by_path(
        self, by_path: Dict[str, Dict[str, Any]]
    ) -> None:
        """Replace the per-file database-table column layout map."""
        from app.services.database_table_columns import (
            normalize_database_table_columns_by_path,
        )

        self._settings["database_table_columns_by_path"] = (
            normalize_database_table_columns_by_path(
                by_path if isinstance(by_path, dict) else None
            )
        )
        self.settings_changed.emit()

    def set_database_table_columns_for_path(
        self, file_path: str, layout: Dict[str, Any]
    ) -> None:
        """Set or replace the column layout override for one file path."""
        from app.services.database_table_columns import (
            canonical_database_table_path,
            normalize_database_table_columns,
        )

        path = canonical_database_table_path(str(file_path or "").strip())
        if not path or path in ("clipboard", "search_results"):
            return
        by_path = self.get_database_table_columns_by_path()
        # Drop any non-canonical aliases for the same file before writing.
        target = path
        for key in list(by_path.keys()):
            if key != target and canonical_database_table_path(key) == target:
                del by_path[key]
        by_path[path] = normalize_database_table_columns(
            layout if isinstance(layout, dict) else None
        )
        self.set_database_table_columns_by_path(by_path)

    def remove_database_table_columns_for_path(self, file_path: str) -> bool:
        """Remove a per-file column layout override. Returns True if one existed."""
        from app.services.database_table_columns import canonical_database_table_path

        raw = str(file_path or "").strip()
        if not raw:
            return False
        target = canonical_database_table_path(raw)
        by_path = self.get_database_table_columns_by_path()
        removed = False
        for key in list(by_path.keys()):
            if key == raw or key == target or canonical_database_table_path(key) == target:
                del by_path[key]
                removed = True
        if removed:
            self.set_database_table_columns_by_path(by_path)
        return removed

    def remap_database_table_columns_path(self, old_path: str, new_path: str) -> None:
        """Move a per-file column layout override when a database file path changes."""
        from app.services.database_table_columns import (
            canonical_database_table_path,
            lookup_database_table_columns_for_path,
        )

        old_key = str(old_path or "").strip()
        new_key = canonical_database_table_path(str(new_path or "").strip())
        if not old_key or not new_key or canonical_database_table_path(old_key) == new_key:
            return
        by_path = self.get_database_table_columns_by_path()
        layout = lookup_database_table_columns_for_path(by_path, old_key)
        if layout is None:
            return
        # Remove all aliases for the old path, then store under the new canonical key.
        old_canon = canonical_database_table_path(old_key)
        for key in list(by_path.keys()):
            if key == old_key or canonical_database_table_path(key) == old_canon:
                del by_path[key]
        by_path[new_key] = layout
        self.set_database_table_columns_by_path(by_path)
    
    def get_pgn_visibility(self) -> Dict[str, Any]:
        """Get PGN visibility settings.
        
        Returns:
            Dictionary of PGN visibility settings.
        """
        return self._settings.get("pgn_visibility", {}).copy()
    
    def set_pgn_visibility(self, settings: Dict[str, Any]) -> None:
        """Set PGN visibility settings.
        
        Args:
            settings: Dictionary of PGN visibility settings.
        """
        self._settings["pgn_visibility"] = settings.copy()
        self.pgn_visibility_changed.emit()
        self.settings_changed.emit()
    
    def get_pgn_notation(self) -> Dict[str, Any]:
        """Get PGN notation settings.
        
        Returns:
            Dictionary of PGN notation settings.
        """
        return self._settings.get("pgn_notation", {}).copy()
    
    def set_pgn_notation(self, settings: Dict[str, Any]) -> None:
        """Set PGN notation settings.
        
        Args:
            settings: Dictionary of PGN notation settings.
        """
        self._settings["pgn_notation"] = settings.copy()
        self.pgn_notation_changed.emit()
        self.settings_changed.emit()
    
    def get_game_analysis(self) -> Dict[str, Any]:
        """Get game analysis settings.
        
        Returns:
            Dictionary of game analysis settings.
        """
        return self._settings.get("game_analysis", {}).copy()
    
    def set_game_analysis(self, settings: Dict[str, Any]) -> None:
        """Set game analysis settings.
        
        Args:
            settings: Dictionary of game analysis settings.
        """
        self._settings["game_analysis"] = settings.copy()
        self.game_analysis_changed.emit()
        self.settings_changed.emit()
    
    def get_game_analysis_settings(self) -> Dict[str, Any]:
        """Get game analysis configuration settings.
        
        Returns:
            Dictionary of game analysis configuration settings.
        """
        return self._settings.get("game_analysis_settings", {}).copy()
    
    def set_game_analysis_settings(self, settings: Dict[str, Any]) -> None:
        """Set game analysis configuration settings.
        
        Args:
            settings: Dictionary of game analysis configuration settings.
        """
        self._settings["game_analysis_settings"] = settings.copy()
        self.game_analysis_changed.emit()
        self.settings_changed.emit()
    
    def get_manual_analysis(self) -> Dict[str, Any]:
        """Get manual analysis settings.
        
        Returns:
            Dictionary of manual analysis settings.
        """
        return self._settings.get("manual_analysis", {}).copy()
    
    def set_manual_analysis(self, settings: Dict[str, Any]) -> None:
        """Set manual analysis settings.
        
        Args:
            settings: Dictionary of manual analysis settings.
        """
        self._settings["manual_analysis"] = settings.copy()
        self.manual_analysis_changed.emit()
        self.settings_changed.emit()
    
    def get_annotations(self) -> Dict[str, Any]:
        """Get annotation settings.
        
        Returns:
            Dictionary of annotation settings.
        """
        return self._settings.get("annotations", {}).copy()
    
    def set_annotations(self, settings: Dict[str, Any]) -> None:
        """Set annotation settings.
        
        Args:
            settings: Dictionary of annotation settings.
        """
        self._settings["annotations"] = settings.copy()
        self.annotations_changed.emit()
        self.settings_changed.emit()
    
    def get_engines(self) -> list:
        """Get engines list.
        
        Returns:
            List of engine data.
        """
        return self._settings.get("engines", []).copy()
    
    def set_engines(self, engines: list) -> None:
        """Set engines list.
        
        Args:
            engines: List of engine data.
        """
        self._settings["engines"] = engines.copy()
        self.settings_changed.emit()
    
    def get_engine_assignments(self) -> Dict[str, Optional[str]]:
        """Get engine assignments.
        
        Returns:
            Dictionary mapping task to engine_id.
        """
        return self._settings.get("engine_assignments", {}).copy()
    
    def set_engine_assignments(self, assignments: Dict[str, Optional[str]]) -> None:
        """Set engine assignments.
        
        Args:
            assignments: Dictionary mapping task to engine_id.
        """
        self._settings["engine_assignments"] = assignments.copy()
        self.settings_changed.emit()
    
    def get_ai_models(self) -> Dict[str, Any]:
        """Get AI model settings.
        
        Returns:
            Dictionary of AI model settings.
        """
        return self._settings.get("ai_models", {}).copy()
    
    def set_ai_models(self, settings: Dict[str, Any]) -> None:
        """Set AI model settings.
        
        Args:
            settings: Dictionary of AI model settings.
        """
        self._settings["ai_models"] = settings.copy()
        self.ai_settings_changed.emit()
        self.settings_changed.emit()
    
    def get_ai_summary(self) -> Dict[str, Any]:
        """Get AI summary settings.
        
        Returns:
            Dictionary of AI summary settings.
        """
        return self._settings.get("ai_summary", {}).copy()
    
    def set_ai_summary(self, settings: Dict[str, Any]) -> None:
        """Set AI summary settings.
        
        Args:
            settings: Dictionary of AI summary settings.
        """
        self._settings["ai_summary"] = settings.copy()
        self.ai_settings_changed.emit()
        self.settings_changed.emit()
    
    def get_player_stats_section_visibility(self) -> Dict[str, bool]:
        """Per-section visibility for the Player Stats detail tab (missing id => default True).

        Valid ids are those in ``PLAYER_STATS_MENU_SECTIONS`` (``detail_player_stats_view``).
        New keys may be added from ``user_settings.json.template`` when settings are merged.
        """
        raw = self._settings.get("player_stats_section_visibility", {})
        if not isinstance(raw, dict):
            return {}
        out: Dict[str, bool] = {}
        for k, v in raw.items():
            if isinstance(v, bool):
                out[str(k)] = v
        return out

    def set_player_stats_section_visibility(self, visibility: Dict[str, bool]) -> None:
        """Replace stored Player Stats section visibility map."""
        self._settings["player_stats_section_visibility"] = {str(k): bool(v) for k, v in visibility.items()}
        self.settings_changed.emit()

    def update_player_stats_section_visibility(self, section_id: str, visible: bool) -> None:
        """Set one section's visibility and persist with the rest of the map."""
        cur = self.get_player_stats_section_visibility()
        cur[str(section_id)] = bool(visible)
        self.set_player_stats_section_visibility(cur)

    def get_player_stats_time_series(self) -> Dict[str, Any]:
        """User overrides for Player Stats date-based trend charts (merged over app config time_series)."""
        from app.services.player_stats_time_series_user import normalize_player_stats_time_series_settings

        raw = self._settings.get("player_stats_time_series")
        return normalize_player_stats_time_series_settings(raw if isinstance(raw, dict) else None)

    def set_player_stats_time_series(self, settings: Dict[str, Any]) -> None:
        """Replace stored Player Stats time-series user settings."""
        from app.services.player_stats_time_series_user import normalize_player_stats_time_series_settings

        self._settings["player_stats_time_series"] = normalize_player_stats_time_series_settings(settings)
        self.player_stats_time_series_changed.emit()
        self.settings_changed.emit()

    def update_player_stats_time_series(self, partial: Dict[str, Any]) -> None:
        """Merge keys into Player Stats time-series settings."""
        cur = self.get_player_stats_time_series()
        cur.update(partial)
        self.set_player_stats_time_series(cur)

    def get_player_stats_activity_heatmap(self) -> Dict[str, Any]:
        """User overrides for Player Stats activity heatmap (merged at display time)."""
        from app.services.player_stats_activity_heatmap_user import (
            normalize_player_stats_activity_heatmap_settings,
        )

        raw = self._settings.get("player_stats_activity_heatmap")
        return normalize_player_stats_activity_heatmap_settings(
            raw if isinstance(raw, dict) else None
        )

    def set_player_stats_activity_heatmap(self, settings: Dict[str, Any]) -> None:
        """Replace stored Player Stats activity heatmap user settings."""
        from app.services.player_stats_activity_heatmap_user import (
            normalize_player_stats_activity_heatmap_settings,
        )

        self._settings["player_stats_activity_heatmap"] = normalize_player_stats_activity_heatmap_settings(settings)
        self.player_stats_activity_heatmap_changed.emit()
        self.settings_changed.emit()

    def update_player_stats_activity_heatmap(self, partial: Dict[str, Any]) -> None:
        """Merge keys into Player Stats activity heatmap settings."""
        cur = self.get_player_stats_activity_heatmap()
        cur.update(partial)
        self.set_player_stats_activity_heatmap(cur)

    def get_player_stats_accuracy_distribution(self) -> Dict[str, Any]:
        """User overrides for Player Stats accuracy distribution chart."""
        from app.services.player_stats_accuracy_distribution_user import (
            normalize_player_stats_accuracy_distribution_settings,
        )

        raw = self._settings.get("player_stats_accuracy_distribution")
        return normalize_player_stats_accuracy_distribution_settings(
            raw if isinstance(raw, dict) else None
        )

    def set_player_stats_accuracy_distribution(self, settings: Dict[str, Any]) -> None:
        """Replace stored Player Stats accuracy distribution user settings."""
        from app.services.player_stats_accuracy_distribution_user import (
            normalize_player_stats_accuracy_distribution_settings,
        )

        self._settings["player_stats_accuracy_distribution"] = normalize_player_stats_accuracy_distribution_settings(settings)
        self.player_stats_accuracy_distribution_changed.emit()
        self.settings_changed.emit()

    def get_player_stats_error_patterns(self) -> Dict[str, Any]:
        """User overrides for Player Stats error-pattern display (coverage cutoff)."""
        from app.services.error_pattern_service import normalize_player_stats_error_patterns_settings

        raw = self._settings.get("player_stats_error_patterns")
        return normalize_player_stats_error_patterns_settings(
            raw if isinstance(raw, dict) else None
        )

    def set_player_stats_error_patterns(self, settings: Dict[str, Any]) -> None:
        """Replace stored Player Stats error-pattern display settings."""
        from app.services.error_pattern_service import normalize_player_stats_error_patterns_settings

        self._settings["player_stats_error_patterns"] = normalize_player_stats_error_patterns_settings(
            settings if isinstance(settings, dict) else None
        )
        self.player_stats_error_patterns_changed.emit()
        self.settings_changed.emit()

    def update_player_stats_error_patterns(self, partial: Dict[str, Any]) -> None:
        """Merge keys into Player Stats error-pattern display settings."""
        cur = self.get_player_stats_error_patterns()
        if isinstance(partial, dict):
            cur.update(partial)
        self.set_player_stats_error_patterns(cur)

    def get_player_stats_profiles(self) -> Dict[str, Any]:
        """Get persisted Player Stats profiles map (name -> profile dict)."""
        raw = self._settings.get("player_stats_profiles", {})
        return raw.copy() if isinstance(raw, dict) else {}

    def set_player_stats_profiles(self, profiles: Dict[str, Any]) -> None:
        """Replace Player Stats profiles map."""
        self._settings["player_stats_profiles"] = profiles.copy()
        self.player_stats_profiles_changed.emit()
        self.settings_changed.emit()

    def get_player_stats_active_profile(self) -> str:
        """Active Player Stats profile name."""
        name = self._settings.get("player_stats_active_profile", "Default")
        return str(name) if isinstance(name, str) and name.strip() else "Default"

    def set_player_stats_active_profile(self, profile_name: str) -> None:
        """Set active Player Stats profile name (does not validate existence)."""
        new_name = str(profile_name or "").strip() or "Default"
        if self._settings.get("player_stats_active_profile") != new_name:
            self._settings["player_stats_active_profile"] = new_name
            self.player_stats_active_profile_changed.emit(new_name)
            self.settings_changed.emit()

    def get_player_stats_profile_order(self) -> list:
        """User-defined ordering of Player Stats profiles (excluding Default)."""
        raw = self._settings.get("player_stats_profile_order", [])
        return raw.copy() if isinstance(raw, list) else []

    def set_player_stats_profile_order(self, order: list) -> None:
        """Set ordering of Player Stats profiles (excluding Default)."""
        self._settings["player_stats_profile_order"] = order.copy() if isinstance(order, list) else []
        self.player_stats_profiles_changed.emit()
        self.settings_changed.emit()

    # Note: Player Stats profiles store snapshots under ``player_stats_profiles``.
    # The live UI settings are stored in the top-level Player Stats keys. Switching
    # profiles copies a snapshot into these top-level keys; saving writes them back
    # into the active profile. This matches Moves List "explicit save" semantics.

    def update_player_stats_accuracy_distribution(self, partial: Dict[str, Any]) -> None:
        """Merge keys into Player Stats accuracy distribution settings."""
        cur = self.get_player_stats_accuracy_distribution()
        cur.update(partial)
        self.set_player_stats_accuracy_distribution(cur)

    def get_opening_encyclopedia_dialog(self) -> Dict[str, Any]:
        """Get Opening Encyclopedia dialog preferences (size, text, miniature board)."""
        return self._settings.get("opening_encyclopedia_dialog", {}).copy()

    def set_opening_encyclopedia_dialog(self, settings: Dict[str, Any]) -> None:
        """Replace Opening Encyclopedia dialog preferences."""
        self._settings["opening_encyclopedia_dialog"] = settings.copy()
        self.settings_changed.emit()

    def update_opening_encyclopedia_dialog(self, partial: Dict[str, Any]) -> None:
        """Merge keys into Opening Encyclopedia dialog preferences."""
        cur = self.get_opening_encyclopedia_dialog()
        cur.update(partial)
        self.set_opening_encyclopedia_dialog(cur)

    def get_recent_pgn_databases(self) -> list:
        """Get recent PGN database file paths (most recent first)."""
        raw = self._settings.get("recent_pgn_databases", [])
        if not isinstance(raw, list):
            return []
        return [str(p) for p in raw if isinstance(p, str) and p.strip()]

    def set_recent_pgn_databases(self, paths: list) -> None:
        """Replace the recent PGN database list."""
        cleaned: list = []
        for p in paths:
            if isinstance(p, str) and p.strip():
                cleaned.append(p.strip())
        self._settings["recent_pgn_databases"] = cleaned
        self.settings_changed.emit()

    def get_bulk_operation_plans(self) -> Dict[str, Any]:
        """Get named bulk-operation plans (name → list of operation dicts)."""
        raw = self._settings.get("bulk_operation_plans", {})
        if not isinstance(raw, dict):
            return {}
        plans: Dict[str, Any] = {}
        for name, ops in raw.items():
            if isinstance(name, str) and name.strip() and isinstance(ops, list):
                plans[name.strip()] = [item for item in ops if isinstance(item, dict)]
        return plans

    def set_bulk_operation_plans(self, plans: Dict[str, Any]) -> None:
        """Replace the named bulk-operation plans map."""
        cleaned: Dict[str, Any] = {}
        if isinstance(plans, dict):
            for name, ops in plans.items():
                if isinstance(name, str) and name.strip() and isinstance(ops, list):
                    cleaned[name.strip()] = [item for item in ops if isinstance(item, dict)]
        self._settings["bulk_operation_plans"] = cleaned
        self.settings_changed.emit()

    def get_keyboard_shortcuts(self) -> Dict[str, Any]:
        """Get keyboard shortcut preferences (overrides map)."""
        raw = self._settings.get("keyboard_shortcuts", {})
        if not isinstance(raw, dict):
            return {"overrides": {}}
        overrides = raw.get("overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
        cleaned_overrides: Dict[str, str] = {}
        for key, value in overrides.items():
            if isinstance(key, str) and key.strip():
                cleaned_overrides[key.strip()] = "" if value is None else str(value)
        return {"overrides": cleaned_overrides}

    def set_keyboard_shortcuts(self, settings: Dict[str, Any]) -> None:
        """Replace keyboard shortcut preferences."""
        overrides_in = settings.get("overrides", {}) if isinstance(settings, dict) else {}
        cleaned: Dict[str, str] = {}
        if isinstance(overrides_in, dict):
            for key, value in overrides_in.items():
                if isinstance(key, str) and key.strip():
                    cleaned[key.strip()] = "" if value is None else str(value)
        self._settings["keyboard_shortcuts"] = {"overrides": cleaned}
        self.settings_changed.emit()

    def update_keyboard_shortcuts(self, partial: Dict[str, Any]) -> None:
        """Merge keys into keyboard shortcut preferences."""
        cur = self.get_keyboard_shortcuts()
        if isinstance(partial, dict):
            if "overrides" in partial and isinstance(partial["overrides"], dict):
                cur["overrides"] = partial["overrides"]
        self.set_keyboard_shortcuts(cur)

    def get_game_highlight_rules(self) -> Dict[str, Any]:
        """Get game highlight rule preferences (overrides + priority order + composer)."""
        raw = self._settings.get("game_highlight_rules", {})
        if not isinstance(raw, dict):
            return {"overrides": {}, "priority_order": [], "composer": {}}
        overrides = raw.get("overrides", {})
        if not isinstance(overrides, dict):
            overrides = {}
        cleaned: Dict[str, Any] = {}
        for key, value in overrides.items():
            if isinstance(key, str) and key.strip() and isinstance(value, dict):
                cleaned[key.strip()] = value
        order_raw = raw.get("priority_order", [])
        order: List[str] = []
        if isinstance(order_raw, list):
            for item in order_raw:
                if isinstance(item, str) and item.strip() and item.strip() not in order:
                    order.append(item.strip())
        composer_raw = raw.get("composer", {})
        composer: Dict[str, Any] = {}
        if isinstance(composer_raw, dict):
            composer = dict(composer_raw)
        return {
            "overrides": cleaned,
            "priority_order": order,
            "composer": composer,
        }

    def set_game_highlight_rules(self, settings: Dict[str, Any]) -> None:
        """Replace game highlight rule preferences."""
        overrides_in = settings.get("overrides", {}) if isinstance(settings, dict) else {}
        cleaned: Dict[str, Any] = {}
        if isinstance(overrides_in, dict):
            for key, value in overrides_in.items():
                if isinstance(key, str) and key.strip() and isinstance(value, dict):
                    cleaned[key.strip()] = value
        order_in = settings.get("priority_order", []) if isinstance(settings, dict) else []
        order: List[str] = []
        if isinstance(order_in, list):
            for item in order_in:
                if isinstance(item, str) and item.strip() and item.strip() not in order:
                    order.append(item.strip())
        composer_in = settings.get("composer", {}) if isinstance(settings, dict) else {}
        composer: Dict[str, Any] = {}
        if isinstance(composer_in, dict):
            composer = dict(composer_in)
        self._settings["game_highlight_rules"] = {
            "overrides": cleaned,
            "priority_order": order,
            "composer": composer,
        }
        self.settings_changed.emit()

    def update_from_dict(self, settings: Dict[str, Any]) -> None:
        """Update settings from a dictionary (used when loading from file).
        
        Args:
            settings: Settings dictionary to merge.
        """
        self._settings.update(settings)
        self.settings_changed.emit()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary (for saving to file).
        
        Returns:
            Complete settings dictionary.
        """
        return self._settings.copy()

