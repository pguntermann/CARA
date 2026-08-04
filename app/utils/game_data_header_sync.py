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

    return updates


def apply_game_data_updates(game: Any, updates: Dict[str, Any]) -> None:
    """Apply attribute updates produced by ``game_data_updates_for_header_tag``."""
    if not updates:
        return
    for attr, value in updates.items():
        setattr(game, attr, value)
