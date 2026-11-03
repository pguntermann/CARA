"""Aggregation service for Chess Log charting.

Walks CARAChessLog payloads across a list of GameData objects, filters by
player and color, and produces per-preset binned time series ready for
ChessLogCategoryChartWidget.

Presets CLAMP and CCT share the same {category + optional why} entry shape,
so one generic pipeline covers both.  3x3 is excluded: its Why1/2/3/4 entries
aren't a comparable category axis.

Reuses from player_stats_service:
- _game_date_ordinal_for_trends   (date → ordinal with partial-date fallbacks)
- _ordinal_target_bin_count       (bin count from target_progression_bins config)
- _ordinal_fallback_mode          (quantile vs equal_width strategy)
- _calendar_bin_center_time_pct   (X-axis position for a bin's calendar range)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from app.models.database_model import GameData
from app.services.chess_log_storage_service import ChessLogStorageService
from app.utils.chess_log_color_scoping import color_from_path_key
from app.utils.player_matcher import game_matches_player_color
from app.services.player_stats_service import (
    _calendar_bin_center_time_pct,
    _game_date_ordinal_for_trends,
    _ordinal_fallback_mode,
    _ordinal_target_bin_count,
)
from app.utils.chess_log_preset_order import CLAMP_ORDER, CCT_ORDER, order_categories

# Presets included in the charting pipeline
CHARTED_PRESETS: frozenset[str] = frozenset({"CLAMP", "CCT"})

# Sentinel for uncategorized moments (cat="" from the zero-category-save feature)
UNCATEGORIZED: str = ""


@dataclass
class ChessLogCategoryBin:
    """One time bin's category-frequency counts for a single preset."""

    time_pct: float          # 0–100, X position on the chart
    total: int               # total moments in this bin
    lab0: str                # ISO date of the earliest game in the bin
    lab1: str                # ISO date of the latest game in the bin
    counts: Dict[str, int]   # category → moment count; "" key = uncategorized


@dataclass
class ChessLogPresetSeries:
    """Complete time-series data for one preset.

    Binning fields (set by aggregate):
        preset, categories, bins

    Rendering fields (set by ChessLogAggregationWorker after aggregate,
    threaded from controller's live instance fields):
        progression_x_axis_mode, compress_gap_max_segment_days,
        progression_line_style, progression_line_smooth_strength
    """

    preset: str
    categories: List[str]             # canonical order per preset, then "" last
    bins: List[ChessLogCategoryBin]
    progression_x_axis_mode: str = "uniform_bins"    # "uniform_bins" / "gap_compressed" / "calendar_linear"
    compress_gap_max_segment_days: int = 28
    progression_line_style: str = "smooth"             # "smooth" or "straight"
    progression_line_smooth_strength: float = 1.0
    t_min: Optional[int] = None           # day ordinal of the earliest game; None on legacy call sites
    t_max: Optional[int] = None           # day ordinal of the latest game


@dataclass
class AggregateResult:
    """Return type from aggregate().

    Wraps the per-preset series dict plus skip-count metadata.
    """

    series: Dict[str, ChessLogPresetSeries] = field(default_factory=dict)
    n_undated_clamp_cct: int = 0   # CLAMP/CCT games skipped because Date is undatable
    has_3x3: bool = False           # any 3x3 moment seen in the filtered games


def aggregate(
    games: List[GameData],
    player: str,
    color_filter: str = "both",       # "white", "black", or "both"
    chart_cfg: Optional[Dict[str, Any]] = None,
    get_tags_for_game: Optional[Callable[[Any], Dict[str, Any]]] = None,
) -> "AggregateResult":
    """Aggregate Chess Log moments into per-preset time series.

    Args:
        games:            Games to scan (from Data Source selection).
        player:           Player name to scope to (case-insensitive). Empty string
                          skips player filtering — all moments in all games.
        color_filter:     "white" / "black" / "both" — further scope to games where
                          the player had that color.
        chart_cfg:        Optional config dict with ``target_progression_bins`` and
                          ``ordinal_fallback_mode`` (same keys as Player Stats).
                          Build via ``chart_cfg_with_chess_log_charts_overrides`` so
                          the user's ``target_bins`` and ``binning_mode`` are applied.
        get_tags_for_game: When provided, called instead of
                          ``ChessLogStorageService.load_resolved_paths`` to read
                          moments for each game.  Pass a main-thread snapshot so
                          the background worker never reads the controller cache
                          directly across threads.

    Returns:
        AggregateResult with series mapping preset name → ChessLogPresetSeries
        (one entry per preset with at least one dated moment), plus
        n_undated_clamp_cct (games with CLAMP/CCT moments but no date) and
        has_3x3 (any 3x3 moment seen in the filtered games).
        Rendering fields (progression_x_axis_mode, etc.) are at their defaults; the caller
        (ChessLogAggregationWorker) sets them from live controller fields before
        emitting.
    """
    chart_cfg = chart_cfg or {}
    player_cf = (player or "").casefold().strip()

    raw: List[Tuple[int, str, str]] = []  # (ordinal, preset, cat)
    n_undated_clamp_cct: int = 0
    has_3x3: bool = False

    for game in games:
        if get_tags_for_game is None and not getattr(game, "has_chess_log_tags", False):
            continue

        if not game_matches_player_color(game, player_cf, color_filter):
            continue

        if get_tags_for_game is not None:
            paths_data = get_tags_for_game(game)
        else:
            paths_data = ChessLogStorageService.load_resolved_paths(game)
        ordinal = _game_date_ordinal_for_trends(game.date or "")

        game_has_clamp_cct = False
        for entries in paths_data.values():
            for entry in entries:
                preset = entry.get("preset", "")
                if preset in CHARTED_PRESETS:
                    game_has_clamp_cct = True
                    if ordinal is not None:
                        cat = entry.get("cat", "")
                        raw.append((ordinal, preset, cat))
                elif preset == "3x3":
                    has_3x3 = True

        if ordinal is None and game_has_clamp_cct:
            n_undated_clamp_cct += 1

    if not raw:
        return AggregateResult(series={}, n_undated_clamp_cct=n_undated_clamp_cct, has_3x3=has_3x3)

    result: Dict[str, ChessLogPresetSeries] = {}
    presets_in_data: Set[str] = {r[1] for r in raw}

    for preset in sorted(presets_in_data):
        samples = [(o, c) for o, p, c in raw if p == preset]
        result[preset] = _bin_preset(preset, samples, chart_cfg)

    return AggregateResult(series=result, n_undated_clamp_cct=n_undated_clamp_cct, has_3x3=has_3x3)


def get_all_players(
    games: List[GameData],
    get_tags_for_game: Optional[Callable[[Any], Dict[str, Any]]] = None,
) -> List[Tuple[str, int]]:
    """Return (name, tagged_game_count) for players with >= 2 games sharing the same preset.

    A player qualifies when any single preset (CLAMP, CCT, 3x3) has at
    least 2 games where that player personally tagged moments with that preset.
    Requiring 2 of the same type prevents a 1-CLAMP + 1-3x3 combination from
    surfacing a player who has no useful data for any chart or narrative.

    The count shown in the dropdown is the total across all presets (not the
    per-preset maximum) so it reflects how many games the player has tagged overall.

    Only games where the player's OWN COLOR has at least one tagged path are
    credited — this avoids crediting both players equally for a game where only
    one side tagged moments.

    Args:
        games:            Games to scan.
        get_tags_for_game: When provided, called instead of
                          ``ChessLogStorageService.load_resolved_paths`` to read
                          moments for each game.  Pass a main-thread snapshot so
                          the background worker never reads the controller cache
                          directly across threads.

    Cost: one ChessLogStorageService.load_tags() call per tagged game. Runs in
    a background worker; acceptable for typical datasets.
    """
    # per_preset_counts[player][preset] = number of games with that preset
    per_preset_counts: Dict[str, Dict[str, int]] = {}
    total_counts: Dict[str, int] = {}

    for game in games:
        if get_tags_for_game is None and not getattr(game, "has_chess_log_tags", False):
            continue
        if get_tags_for_game is not None:
            paths_data = get_tags_for_game(game)
        else:
            paths_data = ChessLogStorageService.load_resolved_paths(game)
        if not paths_data:
            continue

        # Determine which (color, preset) pairs appear in this game.
        color_preset_pairs: Set[Tuple[str, str]] = set()
        for path_key, entries in paths_data.items():
            color = color_from_path_key(path_key)
            if not color:
                continue
            for entry in entries:
                preset = entry.get("preset", "")
                if preset:
                    color_preset_pairs.add((color, preset))

        # Credit the player whose color appears, once per (player, preset) per game.
        seen_player_preset: Set[Tuple[str, str]] = set()
        for name, color in ((game.white, "white"), (game.black, "black")):
            if not (name and name.strip()):
                continue
            n = name.strip()
            for cp_color, preset in color_preset_pairs:
                if cp_color != color:
                    continue
                if (n, preset) not in seen_player_preset:
                    seen_player_preset.add((n, preset))
                    per_preset_counts.setdefault(n, {})
                    per_preset_counts[n][preset] = per_preset_counts[n].get(preset, 0) + 1
                    total_counts[n] = total_counts.get(n, 0) + 1

    qualified = [
        (name, total_counts[name])
        for name, preset_map in per_preset_counts.items()
        if any(count >= 2 for count in preset_map.values())
    ]
    qualified.sort(key=lambda x: (-x[1], x[0]))
    return qualified


def shallow_flag_label(has_3x3: bool) -> str:
    """Return 'Shallow/Vague' if any counted moment is 3x3, else 'Shallow'."""
    return "Shallow/Vague" if has_3x3 else "Shallow"


def compute_narrative_counts(
    games: List[GameData],
    player: str,
    color_filter: str,
    get_tags_fn: Callable[[GameData], Dict[str, Any]],
) -> Tuple[int, int, int, int, bool]:
    """Return (n_games, g_with_moments, m_moments, s_flagged, has_3x3) for the narrative scope.

    - n_games:        games in scope (match player + color_filter)
    - g_with_moments: games where the player has at least one logged moment
    - m_moments:      total (path_key, preset) moments for the player in those games
    - s_flagged:      moments with any Shallow or Vague flag (Ignored flags count)
    - has_3x3:        True if any counted moment uses the 3x3 preset

    Only path_keys whose color matches the player's own color in each game are
    counted; opponent-tagged moves are excluded.  Never-checked moments (no
    is_shallow/is_vague) are not counted in s_flagged.
    """
    player_cf = (player or "").casefold().strip()
    n = g = m = s = 0
    has_3x3 = False

    for game in games:
        if not game_matches_player_color(game, player_cf, color_filter):
            continue
        n += 1

        if not getattr(game, "has_chess_log_tags", False):
            continue

        # Determine which color is the player in this game.
        white_cf = (game.white or "").casefold().strip()
        black_cf = (game.black or "").casefold().strip()
        if player_cf and white_cf == player_cf:
            player_color: Optional[str] = "white"
        elif player_cf and black_cf == player_cf:
            player_color = "black"
        else:
            player_color = None

        tags = get_tags_fn(game)
        game_has_moment = False

        for path_key, entries in tags.items():
            if not entries:
                continue
            # Exclude opponent's path_keys (skip when color is known and mismatched).
            if player_color is not None:
                pk_color = color_from_path_key(path_key)
                if pk_color is not None and pk_color != player_color:
                    continue

            # Group entries by preset — each (path_key, preset) pair = one moment.
            by_preset: Dict[str, List[Dict[str, Any]]] = {}
            for e in entries:
                p = e.get("preset", "")
                if p:
                    by_preset.setdefault(p, []).append(e)

            for preset, preset_entries in by_preset.items():
                m += 1
                game_has_moment = True
                if preset == "3x3":
                    has_3x3 = True
                if _moment_has_flag(preset_entries):
                    s += 1

        if game_has_moment:
            g += 1

    return n, g, m, s, has_3x3


def _moment_has_flag(entries: List[Dict[str, Any]]) -> bool:
    """Return True if any entry in this moment has a Shallow or Vague flag.

    Delegates to ChessLogStorageService.entry_has_flag — the same predicate used
    by get_shallow_vague_keys (Show Shallow/Vague Logs), so both code paths agree.
    """
    return any(ChessLogStorageService.entry_has_flag(e) for e in entries)


# ---------------------------------------------------------------------------
# Internal binning helpers
# ---------------------------------------------------------------------------

def _bin_preset(
    preset: str,
    samples: List[Tuple[int, str]],  # (ordinal, cat)
    chart_cfg: Dict[str, Any],
) -> ChessLogPresetSeries:
    seed_cats: Set[str] = set(CLAMP_ORDER) if preset == "CLAMP" else set(CCT_ORDER)
    all_cats: Set[str] = seed_cats | {cat for _, cat in samples}
    categories = order_categories(preset, list(all_cats))

    ordinals = [o for o, _ in samples]
    t_min, t_max = min(ordinals), max(ordinals)
    n_bins = _ordinal_target_bin_count(chart_cfg, len(samples))
    mode = _ordinal_fallback_mode(chart_cfg)
    bins = (
        _count_bins_quantile(samples, n_bins, t_min, t_max)
        if mode == "quantile"
        else _count_bins_equal_width(samples, n_bins, t_min, t_max)
    )

    return ChessLogPresetSeries(preset=preset, categories=categories, bins=bins,
                               t_min=t_min, t_max=t_max)


def _make_bin(
    chunk: List[Tuple[int, str]],
    lo_o: int,
    hi_o: int,
    t_min: int,
    t_max: int,
) -> ChessLogCategoryBin:
    time_pct = _calendar_bin_center_time_pct(lo_o, hi_o, t_min, t_max)
    counts: Dict[str, int] = {}
    for _, cat in chunk:
        counts[cat] = counts.get(cat, 0) + 1
    return ChessLogCategoryBin(
        time_pct=time_pct,
        total=len(chunk),
        lab0=date.fromordinal(lo_o).isoformat(),
        lab1=date.fromordinal(hi_o).isoformat(),
        counts=counts,
    )


def _count_bins_equal_width(
    samples: List[Tuple[int, str]],
    n_bins: int,
    t_min: int,
    t_max: int,
) -> List[ChessLogCategoryBin]:
    days = t_max - t_min + 1
    if days <= 1 or t_max <= t_min:
        return [_make_bin(samples, t_min, t_max, t_min, t_max)]
    n_bins = max(2, min(n_bins, days))
    result: List[ChessLogCategoryBin] = []
    for b in range(n_bins):
        lo_o = t_min + (days * b) // n_bins
        hi_o = t_min + (days * (b + 1)) // n_bins - 1
        chunk = [(o, c) for o, c in samples if lo_o <= o <= hi_o]
        if not chunk:
            continue
        ords = [x[0] for x in chunk]
        result.append(_make_bin(chunk, min(ords), max(ords), t_min, t_max))
    result.sort(key=lambda b: b.time_pct)
    return result


def _count_bins_quantile(
    samples: List[Tuple[int, str]],
    n_bins: int,
    t_min: int,
    t_max: int,
) -> List[ChessLogCategoryBin]:
    sorted_s = sorted(samples, key=lambda x: x[0])
    n = len(sorted_s)
    if n == 0:
        return []
    n_bins = max(2, min(n_bins, n))
    result: List[ChessLogCategoryBin] = []
    for b in range(n_bins):
        lo_i = b * n // n_bins
        hi_i = (b + 1) * n // n_bins if b < n_bins - 1 else n
        chunk = sorted_s[lo_i:hi_i]
        if not chunk:
            continue
        ords = [x[0] for x in chunk]
        lo_o = max(min(ords), t_min)
        hi_o = min(max(ords), t_max)
        if lo_o > hi_o:
            lo_o, hi_o = hi_o, lo_o
        result.append(_make_bin(chunk, lo_o, hi_o, t_min, t_max))
    result.sort(key=lambda b: b.time_pct)
    return result
