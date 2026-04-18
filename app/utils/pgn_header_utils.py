"""Helpers for PGN header tag names (Seven Tag Roster style, ASCII token names)."""

from __future__ import annotations

import re

# Tag pair syntax is [TagName "value"]; the name must be a single token (no spaces,
# brackets, or quotes). Allow letters, digits, underscore — same family as standard tags
# (Event, WhiteElo, CARAGameTags, etc.).
_PGN_HEADER_TAG_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")

# Allows empty string while typing; only complete strings matching _PGN_HEADER_TAG_NAME are valid.
_PGN_HEADER_TAG_NAME_INPUT = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)?$")


def is_valid_pgn_header_tag_name(name: str) -> bool:
    """Return True if *name* is a non-empty PGN-safe header tag name."""
    return bool(name) and _PGN_HEADER_TAG_NAME.fullmatch(name) is not None


def pgn_header_tag_name_input_pattern() -> str:
    """Regular expression string for QLineEdit validators (allows empty intermediate state)."""
    return _PGN_HEADER_TAG_NAME_INPUT.pattern
