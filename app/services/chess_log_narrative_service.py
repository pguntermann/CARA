"""Chess Log narrative summary service.

Assembles a prompt from:
  - Per-preset CLAMP glossary (verbatim definitions; prevents LLM letter-expansion errors)
  - Per-preset category counts binned over time (4 trend bins via chess_log_stats_service)
  - Why-notes (all non-empty entry["why"] values, no cap)
  - Whole-game notes (CARANotes header) for all games that have them, no cap

No input truncation is applied. At typical tagging rates the full prompt stays well
within 5–10% of the context window; the API's own error handling is the real
constraint if a library ever grows large enough to matter.

Calls AIService.send_message and parses the LLM response into a narrative string.
The shallow-note flagging step has been removed from the prompt; _parse_response
always returns an empty flags list for backward compatibility with callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.models.database_model import GameData
from app.services.ai_service import AIService, TokenUsage
from app.services.chess_log_stats_service import ChessLogPresetSeries, aggregate
from app.services.chess_log_storage_service import ChessLogStorageService
from app.services.notes_storage_service import NotesStorageService
from app.utils.chess_log_color_scoping import own_moves_paths
from app.utils.player_matcher import game_matches_player_color as _game_matches_player_color







def sanitize_narrative_markdown(text: str) -> str:
    """Drop presentational noise from LLM narrative markdown before rendering.

    Two classes of garbage are removed so that both the on-screen QTextEdit
    (setMarkdown path) and the PDF renderer receive identical clean input:

    1. Bare thematic-break lines (---/***/___ alone on a line): presentational
       noise that Qt renders as a subtle HR anyway; ## headings already give
       visual separation so the loss is imperceptible in the PDF.
    2. Pipe-table rows where any cell is empty after stripping: defense in
       depth for blank Strategic Impact cells the model occasionally emits
       despite explicit prompt instructions to the contrary.

    Table separator rows (| --- | --- | --- |) have 2+ pipe-delimited cells
    and are not matched by the thematic-break rule, so they are preserved.
    """
    def _is_separator(line: str) -> bool:
        stripped = line.strip().strip("|")
        if not stripped:
            return False
        cells = [c.strip() for c in stripped.split("|")]
        if len(cells) < 2:
            return False
        return all(c and all(ch in "-: " for ch in c) for c in cells)

    out = []
    for line in text.split("\n"):
        stripped = line.strip()
        # 1. Thematic break: 3+ identical chars from -/*/_, no pipe character.
        if (
            len(stripped) >= 3
            and stripped[0] in "-*_"
            and all(ch == stripped[0] for ch in stripped)
            and "|" not in stripped
        ):
            continue
        # 2. Pipe-table row with any empty cell (separators are preserved above).
        if stripped.startswith("|") and not _is_separator(stripped):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if any(not c for c in cells):
                continue
        out.append(line)
    return "\n".join(out)


def build_prompt(
    games: List[GameData],
    player: str = "",
    color_filter: str = "both",
    config: Optional[Dict[str, Any]] = None,
    *,
    get_tags_for_game: Callable,
) -> str:
    """Assemble the LLM prompt from the given games.

    Args:
        games:            Games to draw data from (already filtered to the desired scope).
        player:           Player name for scoping (empty = all players).
        color_filter:     "white" / "black" / "both".
        config:           App config dict; must contain prompts.chess_log.* keys.
        get_tags_for_game: Called to read moments for each game.  Pass a
                          main-thread snapshot so the background worker never
                          reads the controller cache directly across threads.
                          Use ``ChessLogStorageService.load_resolved_paths`` for
                          disk-based reads (tests, CLI tools).

    Returns:
        Formatted prompt string ready to send as the user message.
    """
    # Placeholders in narrative_preamble (authoritative names — ConfigLoader
    # validator checks these at startup):
    #   {glossary_section}       — preset glossary block, empty string for 3x3
    #   {category_counts_block}  — per-preset category-count table
    #   {why_notes_block}        — player's own why-notes, one per line
    #   {game_notes_block}       — whole-game notes, or "(no whole-game notes)"
    cl_prompts = (config or {}).get("prompts", {}).get("chess_log") or {}
    if not cl_prompts:
        raise ValueError(
            "Chess Log prompts are missing from config.json — reinstall or restore the file."
        )
    player_cf = (player or "").casefold().strip()

    preset_names: Set[str] = set()
    flat_counts: Dict[str, Dict[str, int]] = {}   # fallback when aggregate returns empty
    why_notes: List[Tuple[str, str]] = []
    game_notes: List[str] = []

    for game in games:
        if not _game_matches_player_color(game, player_cf, color_filter):
            continue

        paths_data = own_moves_paths(game, get_tags_for_game(game), player_cf)
        if paths_data:
            for entries in paths_data.values():
                has_3x3_notes = any(
                    e.get("preset") == "3x3" and (e.get("why") or "").strip()
                    for e in entries
                )
                if has_3x3_notes:
                    why_notes.append((_3X3_MOMENT_SENTINEL, ""))
                for entry in entries:
                    preset = entry.get("preset", "")
                    cat = entry.get("cat", "") or ""
                    why = (entry.get("why") or "").strip()
                    if preset:
                        preset_names.add(preset)
                        counts = flat_counts.setdefault(preset, {})
                        counts[cat] = counts.get(cat, 0) + 1
                    if why:
                        label = f"{preset}/{cat}" if cat else f"{preset}/uncategorized"
                        why_notes.append((label, why))

        if getattr(game, "has_notes", False):
            note_text = NotesStorageService.load_notes(game)
            if note_text and note_text.strip():
                game_notes.append(note_text.strip())

    # Trend-binned counts — 4 bins so the model can discuss early vs recent patterns.
    series_map = aggregate(
        games,
        player=player or "",
        color_filter=color_filter,
        chart_cfg={"target_progression_bins": 4, "min_games_per_ordinal_bin": 1},
        get_tags_for_game=get_tags_for_game,
    ).series

    glossary_block = _format_glossary(preset_names, cl_prompts["narrative_glossaries"])
    threexthree_block = _format_3x3_structure(preset_names, cl_prompts["narrative_3x3_structure"])
    combined = "\n\n".join(b for b in (glossary_block, threexthree_block) if b)
    glossary_section = f"\n{combined}\n\n" if combined else "\n"

    if series_map:
        category_counts_block = _format_trend_counts(series_map)
    elif flat_counts:
        category_counts_block = (
            "(trend data unavailable — insufficient dated games)\n\n"
            + _format_category_counts(flat_counts)
        )
    else:
        category_counts_block = "(no moments tagged)"

    why_notes_block = _format_why_notes(why_notes, cl_prompts["narrative_3x3_moment_framing"])
    game_notes_block = _format_game_notes(game_notes)

    preamble = cl_prompts["narrative_preamble"].format(
        glossary_section=glossary_section,
        category_counts_block=category_counts_block,
        why_notes_block=why_notes_block,
        game_notes_block=game_notes_block,
    )
    return preamble + cl_prompts["narrative_step"]


@dataclass(frozen=True)
class NarrativeResult:
    success: bool
    text: str
    shallow_flags: List[str]
    usage: Optional[TokenUsage]
    model: str


def generate_narrative(
    games: List[GameData],
    provider: str,
    model: str,
    api_key: str,
    base_url_override: Optional[str],
    player: str = "",
    color_filter: str = "both",
    config: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 60,
    token_limit: Optional[int] = None,
    *,
    get_tags_for_game: Callable,
) -> NarrativeResult:
    """Generate a narrative summary from the given games.

    Args:
        games:              Games in scope (already filtered to the desired Data Source).
        provider:           AIProvider string ("openai", "anthropic", "custom").
        model:              Model ID.
        api_key:            API key.
        base_url_override:  Custom endpoint base URL (None for OpenAI/Anthropic).
        player:             Player filter (empty = all players).
        color_filter:       "white" / "black" / "both".
        config:             Optional config dict forwarded to AIService.
        timeout_seconds:    Request timeout passed to AIService.send_message.
        token_limit:        Max tokens passed to AIService.send_message (None = AIService default).
        get_tags_for_game:  Called to read moments for each game.  Pass a
                            main-thread snapshot so the background worker never
                            reads the controller cache directly across threads.
                            Use ``ChessLogStorageService.load_resolved_paths`` for
                            disk-based reads (tests, CLI tools).

    Returns:
        NarrativeResult with success, text, shallow_flags (always []), usage, and model.
        On failure: success=False, text=error_message.
    """
    player_cf = (player or "").casefold().strip()
    has_data = any(
        bool(own_moves_paths(g, get_tags_for_game(g), player_cf))
        for g in games
        if _game_matches_player_color(g, player_cf, color_filter)
    )
    if not has_data:
        return NarrativeResult(
            success=False,
            text="No Chess Log data found to summarise.",
            shallow_flags=[],
            usage=None,
            model=model,
        )

    cl_prompts = (config or {}).get("prompts", {}).get("chess_log") or {}
    if not cl_prompts:
        return NarrativeResult(
            success=False,
            text="Chess Log prompts are missing from config.json — reinstall or restore the file.",
            shallow_flags=[],
            usage=None,
            model=model,
        )

    prompt = build_prompt(
        games,
        player=player,
        color_filter=color_filter,
        config=config,
        get_tags_for_game=get_tags_for_game,
    )

    thinking = AIService.disable_thinking_for(model)
    system_prompt = cl_prompts["narrative_system"]

    service = AIService(config=config)
    messages = [{"role": "user", "content": prompt}]
    result = service.send_message(
        provider=provider,
        model=model,
        api_key=api_key,
        messages=messages,
        system_prompt=system_prompt,
        base_url_override=base_url_override,
        token_limit=token_limit,
        timeout_seconds=timeout_seconds,
        thinking=thinking,
    )
    if not result.success:
        return NarrativeResult(
            success=False,
            text=result.error or "Unknown error",
            shallow_flags=[],
            usage=result.usage,
            model=result.model,
        )

    narrative, shallow_flags = _parse_response(result.text)
    return NarrativeResult(
        success=True,
        text=narrative,
        shallow_flags=shallow_flags,
        usage=result.usage,
        model=result.model,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _format_glossary(preset_names: Set[str], preset_glossaries: Dict[str, str]) -> str:
    """Emit glossary blocks for presets that appear in the data and have a glossary entry."""
    blocks = []
    for preset in sorted(preset_names):
        text = preset_glossaries.get(preset, "")
        if text:
            blocks.append(f"## Glossary — {preset}\n\n{text}")
    return "\n\n".join(blocks)


def _format_3x3_structure(preset_names: Set[str], structure_block: str) -> str:
    """Emit the 3x3 Why-questions block iff 3x3 data is present in the filtered data."""
    return structure_block if "3x3" in preset_names else ""


def _bin_month_label(lab0: str, lab1: str) -> str:
    """Convert an ISO date pair to a natural calendar label.

    Same-month: "June 2025".  Same-year span: "June-July 2025".
    Cross-year: "Dec 2025-Jan 2026".  Falls back to raw strings on parse failure.
    """
    from datetime import date as _date

    _FULL = [
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ]
    _SHORT = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    def _parse(s: str) -> Optional[_date]:
        try:
            return _date.fromisoformat(s)
        except (ValueError, TypeError):
            return None

    d0, d1 = _parse(lab0), _parse(lab1)
    if d0 is None or d1 is None:
        return f"{lab0} to {lab1}"

    m0, y0, m1, y1 = d0.month, d0.year, d1.month, d1.year
    if y0 == y1:
        if m0 == m1:
            return f"{_FULL[m0 - 1]} {y0}"
        return f"{_FULL[m0 - 1]}-{_FULL[m1 - 1]} {y0}"
    return f"{_SHORT[m0 - 1]} {y0}-{_SHORT[m1 - 1]} {y1}"


def _format_trend_counts(series_map: Dict[str, ChessLogPresetSeries]) -> str:
    """Format trend-binned category percentages as a prompt block.

    Each bin shows category % of that bin's total (same denominator as the chart
    Y-axis).  A lifetime average (total-weighted, not average-of-percentages) is
    prepended per preset so the model has a single anchor value per category.
    """
    lines = []
    for preset in sorted(series_map):
        series = series_map[preset]
        lines.append(f"### {preset}")

        # Lifetime totals for total-weighted average
        lifetime_total = sum(b.total for b in series.bins)
        lifetime_counts: Dict[str, int] = {}
        for bin_ in series.bins:
            for cat, count in bin_.counts.items():
                lifetime_counts[cat] = lifetime_counts.get(cat, 0) + count

        if lifetime_total > 0:
            avg_parts = []
            for cat in series.categories:
                count = lifetime_counts.get(cat, 0)
                if count > 0:
                    pct = round(count * 100 / lifetime_total)
                    label = cat if cat else "uncategorized"
                    avg_parts.append(f"{label} {pct}%")
            if avg_parts:
                lines.append(f"Overall average: {', '.join(avg_parts)}")

        for bin_ in series.bins:
            month_label = _bin_month_label(bin_.lab0, bin_.lab1)
            if bin_.total == 0:
                lines.append(f"{month_label}: (no moments)")
                continue
            parts = []
            for cat in series.categories:
                count = bin_.counts.get(cat, 0)
                if count > 0:
                    pct = round(count * 100 / bin_.total)
                    label = cat if cat else "uncategorized"
                    parts.append(f"{label} {pct}%")
            if not parts:
                parts.append("(no moments)")
            lines.append(f"{month_label} ({bin_.total} moments): {', '.join(parts)}")
    return "\n".join(lines)


def _format_category_counts(
    category_counts: Dict[str, Dict[str, int]],
) -> str:
    """Flat (non-trend) category counts — used as fallback when aggregate returns empty."""
    if not category_counts:
        return "(no moments tagged)"
    lines = []
    for preset in sorted(category_counts):
        lines.append(f"**{preset}**")
        counts = category_counts[preset]
        named = sorted((k, v) for k, v in counts.items() if k)
        for cat, count in named:
            lines.append(f"  - {cat}: {count}")
        if "" in counts:
            lines.append(f"  - (uncategorized): {counts['']}")
    return "\n".join(lines)


_3X3_MOMENT_SENTINEL = "__3x3_moment__"



def _format_why_notes(why_notes: List[Tuple[str, str]], moment_framing: str) -> str:
    if not why_notes:
        return "(no notes written)"
    lines = []
    for label, note in why_notes:
        if label == _3X3_MOMENT_SENTINEL:
            lines.append(f"\n{moment_framing}")
        else:
            lines.append(f"- [{label}] {note}")
    return "\n".join(lines)


def _format_game_notes(game_notes: List[str]) -> str:
    if not game_notes:
        return "(no whole-game notes)"
    return "\n\n---\n\n".join(game_notes)


def _parse_response(response: str) -> Tuple[str, List[str]]:
    """Return (narrative, []).

    Shallow-note flagging has been removed from the prompt; flags are always
    empty. The sentinel split is intentionally gone — if an old-model response
    happens to include "## Also flagged", it becomes part of the narrative text
    rather than being silently discarded.
    """
    return response.strip(), []
