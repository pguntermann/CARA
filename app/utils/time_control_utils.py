"""Utilities for interpreting PGN TimeControl and mapping to TC Type labels."""

import re
from typing import Any, Dict, Optional


# Default thresholds (seconds): base time per player
# Bullet < 180, Blitz < 600, Rapid < 3600, Classical >= 3600
_DEFAULT_BULLET_MAX = 180
_DEFAULT_BLITZ_MAX = 600
_DEFAULT_RAPID_MAX = 3600


def _parse_base_seconds(time_control: str) -> Optional[int]:
    """Parse TimeControl string and return base time in seconds, or None if unparseable.

    Handles:
    - "N" or "N+0" -> N seconds
    - "N+inc" -> N seconds (increment ignored for classification)
    - "M/N" (moves in N seconds) -> N seconds total, so N/M per move (use N as period)
    - "M/N+K" or "M/N+K+inc" -> N seconds for M moves, so N/M per move (use N)
    - "?" or "-" or "" -> None
    """
    s = (time_control or "").strip()
    if not s or s in ("?", "-"):
        return None

    # Predefined string mapping (e.g. "Blitz") - no numeric value
    if s[0].isalpha():
        return None

    # Integer only: "300", "600"
    if re.match(r"^\d+$", s):
        return int(s)

    # N+inc: "300+3", "180+2"
    m = re.match(r"^(\d+)\+\d*$", s)
    if m:
        return int(m.group(1))

    # Moves/Time: "40/9000", "40/7200+60", "40/9000:900+30"
    m = re.match(r"^(\d+)/(\d+)", s)
    if m:
        moves = int(m.group(1))
        seconds = int(m.group(2))
        if moves > 0:
            # Base time per "period" of moves -> use full period in seconds
            return seconds
    return None


def get_tc_type(time_control: str, tc_type_config: Optional[Dict[str, Any]] = None) -> str:
    """Map a PGN TimeControl value to a TC Type label (e.g. Bullet, Blitz, Rapid, Classical).

    tc_type_config is the tc_type subsection (e.g. from ui.panels.database.tc_type) and may contain:
    - bullet_max_seconds, blitz_max_seconds, rapid_max_seconds
    - string_map: dict mapping literal TimeControl strings to labels (e.g. "Blitz" -> "Blitz")

    Returns empty string for missing/unknown time control; "Unknown" for unparseable non-empty.
    """
    cfg = tc_type_config or {}
    s = (time_control or "").strip()

    if not s or s in ("?", "-"):
        return ""

    # Optional string map from config (e.g. "Blitz" -> "Blitz")
    string_map = cfg.get("string_map") or {}
    if isinstance(string_map, dict) and s in string_map:
        return str(string_map[s]).strip() or ""

    seconds = _parse_base_seconds(s)
    if seconds is None:
        return "Unknown"

    bullet_max = int(cfg.get("bullet_max_seconds", _DEFAULT_BULLET_MAX))
    blitz_max = int(cfg.get("blitz_max_seconds", _DEFAULT_BLITZ_MAX))
    rapid_max = int(cfg.get("rapid_max_seconds", _DEFAULT_RAPID_MAX))

    if seconds <= bullet_max:
        return "Bullet"
    if seconds <= blitz_max:
        return "Blitz"
    if seconds <= rapid_max:
        return "Rapid"
    return "Classical"
