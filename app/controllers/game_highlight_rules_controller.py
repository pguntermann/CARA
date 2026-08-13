"""Controller for the Manage Game Highlight Rules dialog."""

from __future__ import annotations

from typing import List, Optional, Sequence

from PyQt6.QtCore import QObject

from app.services.game_highlight_rules_service import (
    EffectiveHighlightRule,
    GameHighlightRulesService,
    HighlightComposerSettings,
)
from app.services.game_highlights.rule_catalog import ALL_PHASES, clamp_phases


class GameHighlightRulesController(QObject):
    """Orchestrates listing and saving highlight rule preferences."""

    def __init__(
        self,
        parent: Optional[QObject] = None,
        *,
        default_max_per_phase: Optional[int] = None,
    ) -> None:
        super().__init__(parent)
        self._service = GameHighlightRulesService.get_instance()
        self._default_max_per_phase = default_max_per_phase

    def list_rules(self) -> List[EffectiveHighlightRule]:
        """Return all rules with effective settings (priority order)."""
        return self._service.list_effective_rules()

    def default_priority_order(self) -> List[str]:
        return self._service.default_priority_order()

    def priority_for_order_index(self, index: int) -> int:
        return self._service.priority_for_order_index(index)

    def get_composer_settings(self) -> HighlightComposerSettings:
        return self._service.get_composer_settings(
            default_max_per_phase=self._default_max_per_phase
        )

    def default_composer_settings(self) -> HighlightComposerSettings:
        return self._service.default_composer_settings(
            default_max_per_phase=self._default_max_per_phase
        )

    def filter_rules(
        self,
        rules: Sequence[EffectiveHighlightRule],
        query: str,
    ) -> List[EffectiveHighlightRule]:
        """Filter by category, name, or description (case-insensitive)."""
        needle = (query or "").strip().lower()
        if not needle:
            return list(rules)
        matched: List[EffectiveHighlightRule] = []
        for rule in rules:
            haystacks = (
                rule.category_label,
                rule.display_name,
                rule.description,
                rule.rule_id,
            )
            if any(needle in (h or "").lower() for h in haystacks):
                matched.append(rule)
        return matched

    def status_summary(
        self,
        *,
        visible_count: int,
        total_count: int,
        rules: Sequence[EffectiveHighlightRule],
        filter_active: bool,
    ) -> str:
        enabled = sum(1 for r in rules if r.enabled)
        base = (
            f"{total_count} rules · {enabled} enabled"
            if visible_count == total_count
            else f"Showing {visible_count} of {total_count} rules · {enabled} enabled"
        )
        if filter_active:
            return f"{base} — clear filter to reorder by priority"
        return f"{base} — drag to set priority (highest at top)"

    def save_rules(
        self,
        rules: Sequence[EffectiveHighlightRule],
        priority_order: Sequence[str],
        composer: Optional[HighlightComposerSettings] = None,
    ) -> None:
        """Persist sparse overrides, priority order, and composer settings."""
        overrides = self._service.overrides_from_effective(rules)
        self._service.save_preferences(
            overrides,
            priority_order,
            composer,
            default_max_per_phase=self._default_max_per_phase,
        )

    def with_enabled(
        self,
        rule: EffectiveHighlightRule,
        enabled: bool,
    ) -> EffectiveHighlightRule:
        return EffectiveHighlightRule(
            rule_id=rule.rule_id,
            display_name=rule.display_name,
            description=rule.description,
            category_id=rule.category_id,
            category_label=rule.category_label,
            enabled=bool(enabled),
            priority=rule.priority,
            phases=rule.phases,
            applicable_phases=rule.applicable_phases,
            default_enabled=rule.default_enabled,
            default_priority=rule.default_priority,
            default_phases=rule.default_phases,
            priority_overridden=rule.priority_overridden,
        )

    def with_phase(
        self,
        rule: EffectiveHighlightRule,
        phase: str,
        allowed: bool,
    ) -> EffectiveHighlightRule:
        if phase not in rule.applicable_phases:
            return rule
        current = set(rule.phases)
        if allowed:
            current.add(phase)
        else:
            if phase in current and len(current) <= 1:
                return rule
            current.discard(phase)
        phases = clamp_phases(
            tuple(p for p in ALL_PHASES if p in current),
            rule.applicable_phases,
        )
        return EffectiveHighlightRule(
            rule_id=rule.rule_id,
            display_name=rule.display_name,
            description=rule.description,
            category_id=rule.category_id,
            category_label=rule.category_label,
            enabled=rule.enabled,
            priority=rule.priority,
            phases=phases,
            applicable_phases=rule.applicable_phases,
            default_enabled=rule.default_enabled,
            default_priority=rule.default_priority,
            default_phases=rule.default_phases,
            priority_overridden=rule.priority_overridden,
        )
