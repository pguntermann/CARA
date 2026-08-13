"""User-configurable game highlight rule settings (enable, order, phases)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.game_highlights.rule_catalog import (
    BuiltinRuleMeta,
    clamp_phases,
    get_category,
    get_rule_meta,
    list_builtin_rules,
    normalize_phases,
)
from app.services.user_settings_service import UserSettingsService

# Rank-based priorities when the user customizes order (top → highest).
_CUSTOM_PRIORITY_BASE = 100

# Built-in highlight output / deduplication defaults (match detector historically).
_DEFAULT_COMPOSER: Dict[str, Any] = {
    "max_per_phase": 7,
    "max_per_move": 2,
    "phase_dedupe_enabled": True,
    "cross_phase_penalty_enabled": True,
    "cross_phase_penalty": 8,
    "cross_phase_penalty_min_highlights": 7,
}


@dataclass(frozen=True)
class EffectiveHighlightRule:
    """Merged catalog defaults + user override for one rule."""

    rule_id: str
    display_name: str
    description: str
    category_id: str
    category_label: str
    enabled: bool
    priority: int
    phases: Tuple[str, ...]
    applicable_phases: Tuple[str, ...]
    default_enabled: bool
    default_priority: int
    default_phases: Tuple[str, ...]
    priority_overridden: bool


@dataclass(frozen=True)
class HighlightComposerSettings:
    """Settings for highlight list composition / deduplication."""

    max_per_phase: int
    max_per_move: int
    phase_dedupe_enabled: bool
    cross_phase_penalty_enabled: bool
    cross_phase_penalty: int
    cross_phase_penalty_min_highlights: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_per_phase": int(self.max_per_phase),
            "max_per_move": int(self.max_per_move),
            "phase_dedupe_enabled": bool(self.phase_dedupe_enabled),
            "cross_phase_penalty_enabled": bool(self.cross_phase_penalty_enabled),
            "cross_phase_penalty": int(self.cross_phase_penalty),
            "cross_phase_penalty_min_highlights": int(
                self.cross_phase_penalty_min_highlights
            ),
        }


class GameHighlightRulesService:
    """Load/save highlight rule overrides and build registry config."""

    _instance: Optional["GameHighlightRulesService"] = None

    def __init__(self) -> None:
        pass

    @classmethod
    def get_instance(cls) -> "GameHighlightRulesService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def default_priority_order(self) -> List[str]:
        """Built-in order: higher default priority first, then name."""
        metas = list(list_builtin_rules())
        metas.sort(key=lambda m: (-m.default_priority, m.display_name.lower()))
        return [m.id for m in metas]

    def get_overrides(self) -> Dict[str, Dict[str, Any]]:
        """Return cleaned per-rule overrides from user settings."""
        raw = UserSettingsService.get_instance().get_game_highlight_rules()
        overrides = raw.get("overrides", {}) if isinstance(raw, dict) else {}
        if not isinstance(overrides, dict):
            return {}
        cleaned: Dict[str, Dict[str, Any]] = {}
        for rule_id, value in overrides.items():
            if not isinstance(rule_id, str) or not rule_id.strip():
                continue
            if not isinstance(value, dict):
                continue
            entry = self._clean_override_entry(value)
            if entry:
                cleaned[rule_id.strip()] = entry
        return cleaned

    def get_priority_order(self) -> List[str]:
        """Effective priority order (top = highest). Always includes every rule."""
        default = self.default_priority_order()
        stored = self._stored_priority_order()
        if stored:
            return self._normalize_order(stored, default)
        # Legacy: derive order from per-rule numeric priority overrides if present
        legacy = self._order_from_legacy_priorities(default)
        if legacy is not None:
            return legacy
        return list(default)

    def has_custom_priority_order(self) -> bool:
        """True when the user has a saved custom order (or legacy priority ranks)."""
        if self._stored_priority_order():
            return self.get_priority_order() != self.default_priority_order()
        return self._order_from_legacy_priorities(self.default_priority_order()) is not None

    def default_composer_settings(
        self,
        *,
        default_max_per_phase: Optional[int] = None,
    ) -> HighlightComposerSettings:
        """Return built-in composer defaults (optionally override max_per_phase)."""
        base = dict(_DEFAULT_COMPOSER)
        if default_max_per_phase is not None:
            try:
                base["max_per_phase"] = max(1, int(default_max_per_phase))
            except (TypeError, ValueError):
                pass
        return self._parse_composer(base, defaults=base)

    def get_composer_settings(
        self,
        *,
        default_max_per_phase: Optional[int] = None,
    ) -> HighlightComposerSettings:
        """Effective composer settings (user overrides merged over defaults)."""
        defaults = self.default_composer_settings(
            default_max_per_phase=default_max_per_phase
        )
        raw = UserSettingsService.get_instance().get_game_highlight_rules()
        stored = raw.get("composer", {}) if isinstance(raw, dict) else {}
        if not isinstance(stored, dict):
            stored = {}
        return self._parse_composer(stored, defaults=defaults.to_dict())

    def save_preferences(
        self,
        overrides: Dict[str, Dict[str, Any]],
        priority_order: Sequence[str],
        composer: Optional[HighlightComposerSettings] = None,
        *,
        default_max_per_phase: Optional[int] = None,
    ) -> None:
        """Persist sparse per-rule overrides, priority order, and composer settings."""
        cleaned_overrides: Dict[str, Dict[str, Any]] = {}
        if isinstance(overrides, dict):
            for rule_id, value in overrides.items():
                if not isinstance(rule_id, str) or not rule_id.strip():
                    continue
                if not isinstance(value, dict):
                    continue
                meta = get_rule_meta(rule_id.strip())
                if meta is None:
                    continue
                entry = self._diff_from_defaults(meta, value)
                entry.pop("priority", None)
                if entry:
                    cleaned_overrides[rule_id.strip()] = entry

        default = self.default_priority_order()
        normalized = self._normalize_order(list(priority_order), default)
        order_to_store: List[str] = []
        if normalized != default:
            order_to_store = normalized

        if composer is None:
            composer = self.get_composer_settings(
                default_max_per_phase=default_max_per_phase
            )
        defaults = self.default_composer_settings(
            default_max_per_phase=default_max_per_phase
        )
        composer_to_store = self._composer_diff(composer, defaults)

        UserSettingsService.get_instance().update_game_highlight_rules(
            {
                "overrides": cleaned_overrides,
                "priority_order": order_to_store,
                "composer": composer_to_store,
            }
        )

    def set_overrides(self, overrides: Dict[str, Dict[str, Any]]) -> None:
        """Replace per-rule overrides; keep existing priority order and composer."""
        current_order = self._stored_priority_order()
        if not current_order and self.has_custom_priority_order():
            current_order = self.get_priority_order()
        self.save_preferences(overrides, current_order, self.get_composer_settings())

    def reset_to_defaults(self) -> None:
        """Clear all user overrides, custom priority order, and composer settings."""
        UserSettingsService.get_instance().update_game_highlight_rules(
            {"overrides": {}, "priority_order": [], "composer": {}}
        )

    def _parse_composer(
        self,
        value: Dict[str, Any],
        *,
        defaults: Dict[str, Any],
    ) -> HighlightComposerSettings:
        def _int(key: str, minimum: int = 0, maximum: int = 999) -> int:
            raw_val = value.get(key, defaults.get(key))
            try:
                parsed = int(raw_val)
            except (TypeError, ValueError):
                parsed = int(defaults.get(key, minimum))
            return max(minimum, min(maximum, parsed))

        penalty = _int("cross_phase_penalty", 0, 50)
        return HighlightComposerSettings(
            max_per_phase=_int("max_per_phase", 1, 50),
            max_per_move=_int("max_per_move", 1, 5),
            # Always on (not user-editable)
            phase_dedupe_enabled=True,
            # Implicit from penalty amount (0 disables down-ranking)
            cross_phase_penalty_enabled=penalty > 0,
            cross_phase_penalty=penalty,
            cross_phase_penalty_min_highlights=_int(
                "cross_phase_penalty_min_highlights", 0, 50
            ),
        )

    def _composer_diff(
        self,
        settings: HighlightComposerSettings,
        defaults: HighlightComposerSettings,
    ) -> Dict[str, Any]:
        """Sparse composer map: only keys that differ from defaults."""
        current = settings.to_dict()
        base = defaults.to_dict()
        # Bool flags are derived (always-on dedupe; penalty>0 enables down-rank)
        skip = {"phase_dedupe_enabled", "cross_phase_penalty_enabled"}
        out: Dict[str, Any] = {}
        for key, value in current.items():
            if key in skip:
                continue
            if value != base.get(key):
                out[key] = value
        return out

    def list_effective_rules(self) -> List[EffectiveHighlightRule]:
        """Return all built-in rules with effective settings, priority order."""
        overrides = self.get_overrides()
        order = self.get_priority_order()
        custom_order = self.has_custom_priority_order()
        by_id: Dict[str, EffectiveHighlightRule] = {}
        for meta in list_builtin_rules():
            by_id[meta.id] = self._effective_for(
                meta,
                overrides.get(meta.id, {}),
                order_index=None,
                custom_order=False,
            )
        result: List[EffectiveHighlightRule] = []
        for index, rule_id in enumerate(order):
            meta = get_rule_meta(rule_id)
            if meta is None:
                continue
            result.append(
                self._effective_for(
                    meta,
                    overrides.get(rule_id, {}),
                    order_index=index,
                    custom_order=custom_order,
                )
            )
        return result

    def build_registry_config(
        self,
        base_rules_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Merge config.json rule params with user overrides for RuleRegistry.

        Adds ``phases`` and optional ``priority_override`` for the detector.
        """
        base = base_rules_config if isinstance(base_rules_config, dict) else {}
        overrides = self.get_overrides()
        order = self.get_priority_order()
        custom_order = self.has_custom_priority_order()
        index_by_id = {rule_id: i for i, rule_id in enumerate(order)}

        merged: Dict[str, Any] = {}
        for meta in list_builtin_rules():
            rule_cfg = deepcopy(base.get(meta.id, {}))
            if not isinstance(rule_cfg, dict):
                rule_cfg = {}
            effective = self._effective_for(
                meta,
                overrides.get(meta.id, {}),
                order_index=index_by_id.get(meta.id),
                custom_order=custom_order,
            )
            rule_cfg["enabled"] = effective.enabled
            rule_cfg["name"] = effective.display_name
            rule_cfg["description"] = effective.description
            rule_cfg["phases"] = list(effective.phases)
            if effective.priority_overridden:
                rule_cfg["priority_override"] = int(effective.priority)
            else:
                rule_cfg.pop("priority_override", None)
            merged[meta.id] = rule_cfg
        for key, value in base.items():
            if key not in merged and isinstance(value, dict):
                merged[key] = deepcopy(value)
        return merged

    def overrides_from_effective(
        self,
        rules: Sequence[EffectiveHighlightRule],
    ) -> Dict[str, Dict[str, Any]]:
        """Build sparse override map (enabled/phases only) from edited rows."""
        out: Dict[str, Dict[str, Any]] = {}
        for row in rules:
            meta = get_rule_meta(row.rule_id)
            if meta is None:
                continue
            entry = self._diff_from_defaults(
                meta,
                {
                    "enabled": row.enabled,
                    "phases": list(row.phases),
                },
            )
            entry.pop("priority", None)
            if entry:
                out[row.rule_id] = entry
        return out

    def priority_for_order_index(self, index: int) -> int:
        """Priority value for a 0-based position when order is customized."""
        return int(_CUSTOM_PRIORITY_BASE - index)

    def _stored_priority_order(self) -> List[str]:
        raw = UserSettingsService.get_instance().get_game_highlight_rules()
        order = raw.get("priority_order", []) if isinstance(raw, dict) else []
        if not isinstance(order, list):
            return []
        cleaned: List[str] = []
        for item in order:
            if isinstance(item, str) and item.strip() and get_rule_meta(item.strip()):
                rid = item.strip()
                if rid not in cleaned:
                    cleaned.append(rid)
        return cleaned

    def _normalize_order(
        self,
        order: Sequence[str],
        default: Sequence[str],
    ) -> List[str]:
        known = set(default)
        result: List[str] = []
        for rule_id in order:
            if rule_id in known and rule_id not in result:
                result.append(rule_id)
        for rule_id in default:
            if rule_id not in result:
                result.append(rule_id)
        return result

    def _order_from_legacy_priorities(
        self,
        default: Sequence[str],
    ) -> Optional[List[str]]:
        """If old per-rule priority overrides exist, sort by those ranks."""
        raw = UserSettingsService.get_instance().get_game_highlight_rules()
        overrides = raw.get("overrides", {}) if isinstance(raw, dict) else {}
        if not isinstance(overrides, dict):
            return None
        has_priority = False
        scored: List[Tuple[int, str, str]] = []
        for rule_id in default:
            meta = get_rule_meta(rule_id)
            if meta is None:
                continue
            priority = meta.default_priority
            entry = overrides.get(rule_id)
            if isinstance(entry, dict) and "priority" in entry:
                try:
                    priority = int(entry["priority"])
                    has_priority = True
                except (TypeError, ValueError):
                    priority = meta.default_priority
            scored.append((-priority, meta.display_name.lower(), rule_id))
        if not has_priority:
            return None
        scored.sort()
        return [rule_id for _, _, rule_id in scored]

    def _effective_for(
        self,
        meta: BuiltinRuleMeta,
        override: Dict[str, Any],
        *,
        order_index: Optional[int],
        custom_order: bool,
    ) -> EffectiveHighlightRule:
        enabled = meta.default_enabled
        phases = meta.default_phases

        if isinstance(override, dict):
            if "enabled" in override:
                enabled = bool(override["enabled"])
            if "phases" in override:
                phases = normalize_phases(override.get("phases"))

        # Hard ceiling: never enable a phase the rule cannot run in.
        phases = clamp_phases(phases, meta.applicable_phases)

        if custom_order and order_index is not None:
            priority = self.priority_for_order_index(order_index)
            priority_overridden = True
        else:
            priority = meta.default_priority
            priority_overridden = False

        category = get_category(meta.category_id)
        return EffectiveHighlightRule(
            rule_id=meta.id,
            display_name=meta.display_name,
            description=meta.description,
            category_id=meta.category_id,
            category_label=category.label if category else meta.category_id,
            enabled=enabled,
            priority=priority,
            phases=phases,
            applicable_phases=meta.applicable_phases,
            default_enabled=meta.default_enabled,
            default_priority=meta.default_priority,
            default_phases=meta.default_phases,
            priority_overridden=priority_overridden,
        )

    def _clean_override_entry(self, value: Dict[str, Any]) -> Dict[str, Any]:
        entry: Dict[str, Any] = {}
        if "enabled" in value:
            entry["enabled"] = bool(value["enabled"])
        if "priority" in value:
            # Keep legacy priority only for migration reads; new saves omit it
            try:
                entry["priority"] = int(value["priority"])
            except (TypeError, ValueError):
                pass
        if "phases" in value:
            entry["phases"] = list(normalize_phases(value.get("phases")))
        return entry

    def _diff_from_defaults(
        self,
        meta: BuiltinRuleMeta,
        value: Dict[str, Any],
    ) -> Dict[str, Any]:
        entry: Dict[str, Any] = {}
        if "enabled" in value and bool(value["enabled"]) != meta.default_enabled:
            entry["enabled"] = bool(value["enabled"])
        if "phases" in value:
            phases = clamp_phases(value.get("phases"), meta.applicable_phases)
            if phases != normalize_phases(meta.default_phases):
                entry["phases"] = list(phases)
        return entry
