"""Merge shared ``ui.pdf`` chrome with report-specific PDF config blocks."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Mapping, Optional


def deep_merge_dicts(base: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``override`` onto a copy of ``base`` (dicts only)."""
    result: Dict[str, Any] = deepcopy(dict(base))
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, Mapping)
        ):
            result[key] = deep_merge_dicts(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def resolve_pdf_report_config(
    config: Mapping[str, Any],
    report_cfg: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Return merged PDF settings: ``ui.pdf`` defaults + report-specific overrides."""
    shared = config.get("ui", {}).get("pdf", {}) if isinstance(config, Mapping) else {}
    if not isinstance(shared, Mapping):
        shared = {}
    report = report_cfg if isinstance(report_cfg, Mapping) else {}
    return deep_merge_dicts(shared, report)
