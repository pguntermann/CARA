"""Regex presets for bulk find/replace — loaded from config.json."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence


@dataclass(frozen=True)
class BulkRegexPreset:
    """One find/replace template the UI can apply when Use regex is on."""

    id: str
    label: str
    find: str
    replace: str
    tooltip: str = ""
    # Optional substring of ``find`` to select in the Find field after applying.
    select_text: str = ""


# Empty id = "Custom…" (user-authored pattern; do not overwrite fields).
CUSTOM_PRESET_ID = ""


def load_bulk_regex_presets(config: Dict[str, Any]) -> List[BulkRegexPreset]:
    """Load presets from ``ui.dialogs.bulk_operations.regex_presets``.

    Raises:
        ValueError: If the config section is missing or any preset is invalid.
    """
    raw = (
        ((config.get("ui") or {}).get("dialogs") or {})
        .get("bulk_operations", {})
        .get("regex_presets")
    )
    if not isinstance(raw, list) or not raw:
        raise ValueError(
            "ui.dialogs.bulk_operations.regex_presets must be a non-empty list in config.json"
        )

    presets: List[BulkRegexPreset] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(
                f"ui.dialogs.bulk_operations.regex_presets[{index}] must be an object"
            )
        preset_id = str(item.get("id", ""))
        label = str(item.get("label", "")).strip()
        find = str(item.get("find", ""))
        replace = str(item.get("replace", ""))
        tooltip = str(item.get("tooltip", "") or "")
        select_text = str(item.get("select_text", "") or "")
        if not label:
            raise ValueError(
                f"ui.dialogs.bulk_operations.regex_presets[{index}] is missing label"
            )
        if preset_id in seen_ids:
            raise ValueError(
                f"Duplicate regex preset id {preset_id!r} at index {index}"
            )
        seen_ids.add(preset_id)
        if select_text and select_text not in find:
            raise ValueError(
                f"select_text {select_text!r} for preset {preset_id!r} "
                f"must be a substring of find"
            )
        if preset_id:
            try:
                re.compile(find)
            except re.error as exc:
                raise ValueError(
                    f"Invalid find regex for preset {preset_id!r}: {exc}"
                ) from exc
        presets.append(
            BulkRegexPreset(
                id=preset_id,
                label=label,
                find=find,
                replace=replace,
                tooltip=tooltip,
                select_text=select_text,
            )
        )
    return presets


def find_preset_by_id(
    presets: Sequence[BulkRegexPreset], preset_id: str
) -> Optional[BulkRegexPreset]:
    for preset in presets:
        if preset.id == preset_id:
            return preset
    return None


def match_preset_id(
    presets: Sequence[BulkRegexPreset], find_text: str, replace_text: str
) -> str:
    """Return preset id if find/replace exactly match a template, else Custom."""
    for preset in presets:
        if not preset.id:
            continue
        if preset.find == find_text and preset.replace == replace_text:
            return preset.id
    return CUSTOM_PRESET_ID
