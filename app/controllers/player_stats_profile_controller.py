"""Controller for managing Player Stats profiles (delegates to UserSettingsService)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

from app.services.user_settings_service import UserSettingsService
from app.services.logging_service import LoggingService


DEFAULT_PLAYER_STATS_PROFILE_NAME = "Default"


class PlayerStatsProfileController:
    """Business logic for Player Stats profiles.

    Responsibilities:
    - Maintain one in-memory working state (top-level Player Stats keys in UserSettingsModel)
    - Overwrite working state on profile switch
    - Persist snapshots only on explicit Save / Save As / Remove

    Persistence is performed via UserSettingsService (single owner of file I/O).
    """

    def __init__(self) -> None:
        self._settings_service = UserSettingsService.get_instance()

    def get_profile_names(self) -> List[str]:
        """Return profile names with Default first, then user order, then remaining alpha."""
        model = self._settings_service.get_model()
        profiles = model.get_player_stats_profiles()
        names = [n for n in profiles.keys() if isinstance(n, str)]

        if DEFAULT_PLAYER_STATS_PROFILE_NAME not in names:
            # Defensive: migration should ensure Default exists.
            names.insert(0, DEFAULT_PLAYER_STATS_PROFILE_NAME)

        order = model.get_player_stats_profile_order()
        ordered: List[str] = [DEFAULT_PLAYER_STATS_PROFILE_NAME]

        # Apply stored order (excluding Default).
        seen = {DEFAULT_PLAYER_STATS_PROFILE_NAME}
        for n in order:
            if isinstance(n, str) and n in names and n not in seen:
                ordered.append(n)
                seen.add(n)

        # Append remaining names alphabetically for stability.
        rest = sorted([n for n in names if n not in seen], key=lambda s: s.lower())
        ordered.extend(rest)
        return ordered

    def get_active_profile_name(self) -> str:
        return self._settings_service.get_model().get_player_stats_active_profile()

    def set_active_profile(self, profile_name: str) -> Tuple[bool, str]:
        name = str(profile_name or "").strip()
        if not name:
            return (False, "Profile name cannot be empty")

        model = self._settings_service.get_model()
        profiles = model.get_player_stats_profiles()
        LoggingService.get_instance().debug(
            f"[PlayerStatsProfile] switch requested={name!r} active_before={model.get_player_stats_active_profile()!r}"
        )

        if name not in profiles:
            return (False, f"Profile '{name}' not found")

        snap_any = profiles.get(name)
        snap = snap_any if isinstance(snap_any, dict) else {}
        default_any = profiles.get(DEFAULT_PLAYER_STATS_PROFILE_NAME)
        default_snap = default_any if isinstance(default_any, dict) else {}
        def _section_dict(key: str) -> Dict[str, Any]:
            v = snap.get(key)
            if isinstance(v, dict):
                return json.loads(json.dumps(v))
            v = default_snap.get(key)
            if isinstance(v, dict):
                return json.loads(json.dumps(v))
            return {}

        # Atomic overwrite of working state.
        try:
            model.blockSignals(True)
            vis = _section_dict("player_stats_section_visibility")
            ts = _section_dict("player_stats_time_series")
            ah = _section_dict("player_stats_activity_heatmap")
            ad = _section_dict("player_stats_accuracy_distribution")
            model.set_player_stats_section_visibility(vis)
            model.set_player_stats_time_series(ts)
            model.set_player_stats_activity_heatmap(ah)
            model.set_player_stats_accuracy_distribution(ad)
            model.set_player_stats_active_profile(name)
        finally:
            try:
                model.blockSignals(False)
            except Exception:
                pass

        # Refresh burst for menus/views.
        try:
            model.player_stats_active_profile_changed.emit(name)
        except Exception:
            pass
        try:
            model.player_stats_time_series_changed.emit()
        except Exception:
            pass
        try:
            model.player_stats_activity_heatmap_changed.emit()
        except Exception:
            pass
        try:
            model.player_stats_accuracy_distribution_changed.emit()
        except Exception:
            pass
        try:
            model.settings_changed.emit()
        except Exception:
            pass

        # Minimal summary.
        cur_vis = model.get_player_stats_section_visibility()
        LoggingService.get_instance().debug(
            f"[PlayerStatsProfile] switch applied active={model.get_player_stats_active_profile()!r} "
            f"hidden={sum(1 for v in cur_vis.values() if not bool(v))}"
        )

        return (True, f"Player Stats profile '{name}' activated")

    def save_active_profile(self) -> Tuple[bool, str]:
        name = self.get_active_profile_name() or DEFAULT_PLAYER_STATS_PROFILE_NAME
        model = self._settings_service.get_model()
        profiles = model.get_player_stats_profiles()

        pdata = profiles.get(name)
        if not isinstance(pdata, dict):
            pdata = {}
            profiles[name] = pdata

        pdata["player_stats_section_visibility"] = model.get_player_stats_section_visibility()
        pdata["player_stats_time_series"] = model.get_player_stats_time_series()
        pdata["player_stats_activity_heatmap"] = model.get_player_stats_activity_heatmap()
        pdata["player_stats_accuracy_distribution"] = model.get_player_stats_accuracy_distribution()

        model.set_player_stats_profiles(profiles)
        model.set_player_stats_active_profile(name)

        ok = bool(self._settings_service.save_player_stats_profiles_only())
        return (ok, f"Profile '{name}' saved" if ok else f"Failed to save profile '{name}'")

    def save_profile_as(self, profile_name: str) -> Tuple[bool, str]:
        name = str(profile_name or "").strip()
        if not name:
            return (False, "Profile name cannot be empty")
        if len(name) < 3:
            return (False, "Profile name must be at least 3 characters")

        model = self._settings_service.get_model()
        profiles = model.get_player_stats_profiles()
        if name in profiles:
            return (False, f"Profile '{name}' already exists")

        profiles[name] = {
            "player_stats_section_visibility": model.get_player_stats_section_visibility(),
            "player_stats_time_series": model.get_player_stats_time_series(),
            "player_stats_activity_heatmap": model.get_player_stats_activity_heatmap(),
            "player_stats_accuracy_distribution": model.get_player_stats_accuracy_distribution(),
        }
        model.set_player_stats_profiles(profiles)
        LoggingService.get_instance().debug(f"[PlayerStatsProfile] save_as created={name!r}")

        order = model.get_player_stats_profile_order()
        if name not in order:
            order.append(name)
            model.set_player_stats_profile_order(order)

        model.set_player_stats_active_profile(name)

        ok = bool(self._settings_service.save_player_stats_profiles_only())
        return (ok, f"Profile '{name}' saved" if ok else f"Failed to save profile '{name}'")

    def remove_profile(self, profile_name: str) -> Tuple[bool, str]:
        name = str(profile_name or "").strip()
        if not name:
            return (False, "Profile name cannot be empty")
        if name == DEFAULT_PLAYER_STATS_PROFILE_NAME:
            return (False, "Cannot remove default profile")

        model = self._settings_service.get_model()
        profiles = model.get_player_stats_profiles()
        if name not in profiles:
            return (False, f"Profile '{name}' not found")

        profiles.pop(name, None)
        model.set_player_stats_profiles(profiles)

        order = model.get_player_stats_profile_order()
        if name in order:
            order = [n for n in order if n != name]
            model.set_player_stats_profile_order(order)

        # Always fall back to Default working state after removal.
        # This mirrors the Moves List "switch to a known profile after delete" behavior.
        self.set_active_profile(DEFAULT_PLAYER_STATS_PROFILE_NAME)

        ok = bool(self._settings_service.save_player_stats_profiles_only())
        return (ok, f"Profile '{name}' removed" if ok else f"Failed to remove profile '{name}'")

    def reset_to_defaults(self) -> Tuple[bool, str]:
        """Reset the stored Default profile from the template and activate it.

        Important: the template is read only via UserSettingsService; this controller never reads it directly.
        Persistence is isolated to Player Stats profile keys only.
        """
        model = self._settings_service.get_model()
        snap = self._settings_service.get_player_stats_default_profile_from_template()
        if not isinstance(snap, dict):
            return (False, "Could not load Default profile from template")

        profiles = model.get_player_stats_profiles()
        if not isinstance(profiles, dict):
            profiles = {}

        profiles[DEFAULT_PLAYER_STATS_PROFILE_NAME] = snap
        model.set_player_stats_profiles(profiles)

        # Ensure Default is the active profile and working state matches it.
        ok_switch, _msg = self.set_active_profile(DEFAULT_PLAYER_STATS_PROFILE_NAME)
        if not ok_switch:
            return (False, "Failed to activate Default profile after reset")

        ok = bool(self._settings_service.save_player_stats_profiles_only())
        return (ok, "Player Stats reset to defaults" if ok else "Failed to persist Player Stats defaults")

