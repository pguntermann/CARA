"""Sync GameData fields that mirror PGN headers after bulk header edits."""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.utils.game_tags_utils import (
    PGN_TAG_NAME_GAME_TAGS,
    parse_game_tags,
    tags_display_text,
)

# Standard PGN tags mirrored onto GameData string columns.
STANDARD_TAG_TO_FIELD = {
    "White": "white",
    "Black": "black",
    "Result": "result",
    "Date": "date",
    "ECO": "eco",
    "Event": "event",
    "Site": "site",
    "WhiteElo": "white_elo",
    "BlackElo": "black_elo",
    "TimeControl": "time_control",
}

# Heavy CARA payloads are never cached on GameData.header_values at parse time.
_HEAVY_HEADER_TAGS = frozenset(
    {
        "CARAAnalysisData",
        "CARAAnnotations",
        "CARANotes",
    }
)

# Nested key in update dicts for the header_values cache (dynamic table columns).
_HEADER_VALUES_KEY = "_header_values"


def game_data_updates_for_header_tag(
    tag_name: str,
    new_value: Optional[str] = None,
    *,
    removed: bool = False,
) -> Dict[str, Any]:
    """Return GameData attribute updates for one header tag mutation.

    Args:
        tag_name: PGN header tag name.
        new_value: New header value when not removed.
        removed: True when the header was deleted from the game.
    """
    updates: Dict[str, Any] = {}
    field = STANDARD_TAG_TO_FIELD.get(tag_name)
    if field:
        updates[field] = "" if removed else (new_value if new_value is not None else "")

    if tag_name == PGN_TAG_NAME_GAME_TAGS or tag_name.casefold() == PGN_TAG_NAME_GAME_TAGS.casefold():
        if removed:
            updates["game_tags_raw"] = ""
            updates["game_tags"] = ""
        else:
            raw = new_value or ""
            updates["game_tags_raw"] = raw
            updates["game_tags"] = tags_display_text(parse_game_tags(raw))
    elif tag_name == "CARAAnalysisData":
        updates["analyzed"] = False if removed else True
    elif tag_name == "CARAAnnotations":
        updates["annotated"] = False if removed else True
    elif tag_name == "CARANotes":
        updates["has_notes"] = False if removed else True
        if removed:
            updates["notes"] = None

    # Keep parse-time header_values cache in sync for dynamic database columns.
    if tag_name and tag_name not in _HEAVY_HEADER_TAGS:
        updates[_HEADER_VALUES_KEY] = {
            tag_name: None if removed else ("" if new_value is None else str(new_value))
        }

    return updates


def merge_game_data_updates(target: Dict[str, Any], extra: Dict[str, Any]) -> None:
    """Merge updates from ``game_data_updates_for_header_tag`` into ``target``.

    Nested ``_header_values`` patches are combined so multi-tag steps keep all tags.
    """
    if not extra:
        return
    for key, value in extra.items():
        if key == _HEADER_VALUES_KEY and isinstance(value, dict):
            bucket = target.setdefault(_HEADER_VALUES_KEY, {})
            if isinstance(bucket, dict):
                bucket.update(value)
            else:
                target[_HEADER_VALUES_KEY] = dict(value)
        else:
            target[key] = value


def apply_game_data_updates(game: Any, updates: Dict[str, Any]) -> None:
    """Apply attribute updates produced by ``game_data_updates_for_header_tag``."""
    if not updates:
        return
    header_patch = updates.get(_HEADER_VALUES_KEY)
    for attr, value in updates.items():
        if attr == _HEADER_VALUES_KEY:
            continue
        setattr(game, attr, value)

    if isinstance(header_patch, dict) and header_patch:
        hv = getattr(game, "header_values", None)
        if not isinstance(hv, dict):
            hv = {}
            setattr(game, "header_values", hv)
        for tag, value in header_patch.items():
            name = str(tag)
            if value is None:
                hv.pop(name, None)
            else:
                hv[name] = str(value)
