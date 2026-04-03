"""Service for aggregating player statistics across multiple games."""

import calendar
import os
from datetime import date
from statistics import median
from typing import List, Dict, Any, Optional, Tuple, Callable, Sequence
from dataclasses import dataclass
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import math

from app.models.database_model import GameData, DatabaseModel
from app.services.date_matcher import DateMatcher
from app.models.moveslist_model import MoveData
from app.services.game_summary_service import GameSummary, PlayerStatistics, PhaseStatistics, GameSummaryService
from app.controllers.game_controller import GameController
from app.services.logging_service import LoggingService, init_worker_logging
from app.utils.concurrency_utils import get_process_pool_max_workers


def _process_game_for_stats(game_pgn: str, game_result: str, game_white: str, game_black: str,
                            game_eco: str, player_name: str, config: Dict[str, Any],
                            game_index: int = 0) -> Optional[Dict[str, Any]]:
    """Process a single game for statistics aggregation (must be top-level for pickling).

    game_index is used to preserve order of results when using as_completed().
    """
    try:
        # Extract moves from PGN
        from app.services.analysis_data_storage_service import AnalysisDataStorageService
        from app.models.database_model import GameData
        import io
        import chess.pgn
        
        # Create minimal GameData for analysis data loading
        game_data = GameData(
            game_number=0,
            white=game_white,
            black=game_black,
            result=game_result,
            date="",
            moves=0,
            eco=game_eco,
            pgn=game_pgn,
            event="",
            site="",
            white_elo="",
            black_elo="",
            time_control="",
            analyzed=True,
            annotated=False,
            file_position=0
        )
        
        # Try to load analysis data from PGN tag
        moves = None
        try:
            stored_moves = AnalysisDataStorageService.load_analysis_data(game_data)
            if stored_moves:
                moves = stored_moves
        except (ValueError, Exception):
            # Continue to parse PGN normally
            pass
        
        # If no stored moves, we can't process this game in parallel
        # (Games without analysis data in PGN tags need the controller to extract moves)
        if not moves:
            return None
        
        # Calculate game summary
        summary_service = GameSummaryService(config)
        game_summary = summary_service.calculate_summary(moves, len(moves), game_result)
        if not game_summary:
            return None
        
        # Determine if player is white or black
        is_white_game = (game_white == player_name)
        
        # Get player statistics for this game
        if is_white_game:
            game_stats = game_summary.white_stats
            game_opening = game_summary.white_opening
            game_middlegame = game_summary.white_middlegame
            game_endgame = game_summary.white_endgame
        else:
            game_stats = game_summary.black_stats
            game_opening = game_summary.black_opening
            game_middlegame = game_summary.black_middlegame
            game_endgame = game_summary.black_endgame
        
        # Determine opening phase end
        opening_end, _ = summary_service._determine_phase_boundaries(moves, len(moves))
        
        # Find opening ECO and name
        repeat_indicator = config.get('resources', {}).get('opening_repeat_indicator', '*')
        eco = "Unknown"
        opening_name = None
        for move in reversed(moves):
            if move.opening_name and move.opening_name != repeat_indicator:
                eco = move.eco if move.eco else "Unknown"
                opening_name = move.opening_name
                break
        
        if eco == "Unknown" and not opening_name:
            eco = game_eco if game_eco else "Unknown"
        
        # Collect opening CPL values
        game_cpl_field = 'cpl_white' if is_white_game else 'cpl_black'
        game_opening_cpls = []
        for move in moves:
            move_num = move.move_number
            if move_num <= opening_end:
                if is_white_game and move.white_move:
                    cpl_str = getattr(move, game_cpl_field, "")
                    if cpl_str:
                        try:
                            cpl = float(cpl_str)
                            game_opening_cpls.append(cpl)
                        except (ValueError, TypeError):
                            pass
                elif not is_white_game and move.black_move:
                    cpl_str = getattr(move, game_cpl_field, "")
                    if cpl_str:
                        try:
                            cpl = float(cpl_str)
                            game_opening_cpls.append(cpl)
                        except (ValueError, TypeError):
                            pass
        
        # Calculate average CPL for opening
        opening_avg_cpl = None
        if game_opening_cpls:
            CPL_CAP_FOR_AVERAGE = 500.0
            capped_cpl_values = [min(cpl, CPL_CAP_FOR_AVERAGE) for cpl in game_opening_cpls]
            opening_avg_cpl = sum(capped_cpl_values) / len(capped_cpl_values)
        
        # Collect moves for overall aggregation
        all_moves_white = []
        all_moves_black = []
        for move in moves:
            if is_white_game and move.white_move:
                all_moves_white.append(move)
            elif not is_white_game and move.black_move:
                all_moves_black.append(move)
        
        # Running accuracy by game progress (0%, 5%, ..., 100%) for chart
        player_moves_list = summary_service._extract_player_moves(moves, is_white_game)
        opponent_moves_list = summary_service._extract_player_moves(moves, not is_white_game)
        num_bins = 21  # 0, 5, 10, ..., 100
        accuracy_by_progress: List[Tuple[float, Optional[float]]] = []
        opponent_accuracy_by_progress: List[Tuple[float, Optional[float]]] = []
        for i in range(num_bins):
            pct = (i * 100.0) / (num_bins - 1) if num_bins > 1 else 100.0
            k = round((pct / 100.0) * len(player_moves_list)) if player_moves_list else 0
            prefix = player_moves_list[:k]
            if not prefix:
                accuracy_by_progress.append((pct, None))
            else:
                prefix_stats = summary_service._calculate_player_statistics(
                    prefix,
                    opening_moves=len(prefix),
                    middlegame_moves=0,
                    endgame_moves=0,
                    average_cpl_opening=0.0,
                    average_cpl_middlegame=0.0,
                    average_cpl_endgame=0.0,
                )
                accuracy_by_progress.append((pct, prefix_stats.accuracy))
            k_opp = round((pct / 100.0) * len(opponent_moves_list)) if opponent_moves_list else 0
            prefix_opp = opponent_moves_list[:k_opp]
            if not prefix_opp:
                opponent_accuracy_by_progress.append((pct, None))
            else:
                prefix_opp_stats = summary_service._calculate_player_statistics(
                    prefix_opp,
                    opening_moves=len(prefix_opp),
                    middlegame_moves=0,
                    endgame_moves=0,
                    average_cpl_opening=0.0,
                    average_cpl_middlegame=0.0,
                    average_cpl_endgame=0.0,
                )
                opponent_accuracy_by_progress.append((pct, prefix_opp_stats.accuracy))
        
        return {
            'index': game_index,
            'is_white': is_white_game,
            'game_result': game_result,
            'game_stats': game_stats,
            'game_opening': game_opening,
            'game_middlegame': game_middlegame,
            'game_endgame': game_endgame,
            'opening_key': (eco, opening_name),
            'opening_avg_cpl': opening_avg_cpl,
            'all_moves_white': all_moves_white,
            'all_moves_black': all_moves_black,
            'moves': moves,
            'game_summary': game_summary,
            'accuracy_by_progress': accuracy_by_progress,
            'opponent_accuracy_by_progress': opponent_accuracy_by_progress,
        }
    except Exception as e:
        # Log error but don't crash - return None to skip this game
        logging_service = LoggingService.get_instance()
        logging_service.error(f"Error processing game for stats: {e}", exc_info=e)
        return None


def _game_date_to_ordinal(date_str: str) -> Optional[int]:
    """Return proleptic Gregorian ordinal for a PGN [Date] string, or None if not fully specified."""
    if not date_str or not isinstance(date_str, str):
        return None
    parsed = DateMatcher.parse_date(date_str.strip())
    if not parsed:
        return None
    y, m, d = parsed
    if y is None or m is None or d is None:
        return None
    try:
        return date(y, m, d).toordinal()
    except ValueError:
        return None


def _game_date_ordinal_for_trends(date_str: str) -> Optional[int]:
    """Ordinal for time-series charts (accuracy, move quality, ACPL by phase).

    Fully specified PGN dates use the real calendar day. Partial dates use stable
    stand-ins so games still contribute to bins (otherwise long games with
    ``YYYY.??.??`` or ``YYYY.MM.??`` were dropped entirely while still showing
    full phase stats when opened individually).

    - Year only (``YYYY.??.??``): July 1 of that year
    - Year-month (``YYYY.MM.??``): 15th of that month (clamped to month length)
    """
    if not date_str or not isinstance(date_str, str):
        return None
    parsed = DateMatcher.parse_date(date_str.strip())
    if not parsed:
        return None
    y, m, d = parsed
    if y is None:
        return None
    try:
        if m is None:
            return date(y, 7, 1).toordinal()
        if d is None:
            last = calendar.monthrange(y, m)[1]
            d_use = min(15, last)
            return date(y, m, d_use).toordinal()
        return date(y, m, d).toordinal()
    except ValueError:
        return None


def _ordinal_target_bin_count(chart_cfg: Dict[str, Any], n_samples: int) -> int:
    """Effective number of progression bins from ``target_progression_bins`` (capped by density and max)."""
    target = int(chart_cfg.get("target_progression_bins", 100))
    max_ord = int(chart_cfg.get("max_ordinal_bins", 120))
    if max_ord < 2:
        max_ord = 120
    min_per = max(1, int(chart_cfg.get("min_games_per_ordinal_bin", 3)))
    cap_samples = max(2, n_samples // min_per)
    return max(2, min(target, cap_samples, max_ord))


def _ordinal_fallback_mode(chart_cfg: Dict[str, Any]) -> str:
    """``quantile``: ~equal games per bin (more resolution in busy periods). ``equal_width``: equal calendar spans."""
    raw = str(chart_cfg.get("ordinal_fallback_mode", "quantile")).strip().lower()
    return "quantile" if raw == "quantile" else "equal_width"


def _calendar_bin_center_time_pct(lo_o: int, hi_o: int, t_min: int, t_max: int) -> float:
    """Map a bin's calendar range to 0–100 chart X (same linear scale as the date axis).

    Ordinal-quantile bins slice the game list by equal counts; their median accuracy still
    refers to real dates (``lab0``–``lab1``). Using rank index for ``time_pct`` placed points
    on the wrong calendar position when game density over time was uneven.
    """
    span = float(t_max - t_min)
    if span <= 0:
        return 50.0
    center = (float(lo_o) + float(hi_o)) / 2.0
    pct = (center - float(t_min)) / span * 100.0
    return max(0.0, min(100.0, pct))


def _accuracy_bin_row_from_chunk(
    chunk: List[Tuple[int, float, bool]],
    lo_o: int,
    hi_o: int,
    t_min: int,
    t_max: int,
) -> Tuple[float, float, float, float, int, str, str]:
    """One accuracy-over-time row: combined + white + black medians (nan if no games of that color)."""
    accs_all = [x[1] for x in chunk]
    accs_w = [x[1] for x in chunk if x[2]]
    accs_b = [x[1] for x in chunk if not x[2]]
    lo_o = max(lo_o, t_min)
    hi_o = min(hi_o, t_max)
    if lo_o > hi_o:
        lo_o, hi_o = hi_o, lo_o
    time_pct = _calendar_bin_center_time_pct(lo_o, hi_o, t_min, t_max)
    p_all = float(median(accs_all))
    p_w = float(median(accs_w)) if accs_w else float("nan")
    p_b = float(median(accs_b)) if accs_b else float("nan")
    cnt = len(accs_all)
    lab0 = date.fromordinal(lo_o).isoformat()
    lab1 = date.fromordinal(hi_o).isoformat()
    return (time_pct, p_all, p_w, p_b, cnt, lab0, lab1)


def _accuracy_series_ordinal_quantile_bins(
    samples: List[Tuple[int, float, bool]],
    n_bins: int,
    t_min: int,
    t_max: int,
) -> List[Tuple[float, float, float, float, int, str, str]]:
    sorted_s = sorted(samples, key=lambda x: x[0])
    n = len(sorted_s)
    n_bins = max(2, min(n_bins, n))
    rows: List[Tuple[float, float, float, float, int, str, str]] = []
    for b in range(n_bins):
        lo_i = b * n // n_bins
        hi_i = (b + 1) * n // n_bins if b < n_bins - 1 else n
        chunk = sorted_s[lo_i:hi_i]
        ords = [x[0] for x in chunk]
        lo_o = max(min(ords), t_min)
        hi_o = min(max(ords), t_max)
        rows.append(_accuracy_bin_row_from_chunk(chunk, lo_o, hi_o, t_min, t_max))
    rows.sort(key=lambda x: x[0])
    return rows


def _accuracy_series_equal_ordinal_width_bins(
    samples: List[Tuple[int, float, bool]],
    n_bins: int,
    t_min: int,
    t_max: int,
) -> List[Tuple[float, float, float, float, int, str, str]]:
    """Split ``[t_min, t_max]`` (inclusive calendar days) into equal-width ranges; median per bin.

    Omits bins with no games. X positions follow calendar time instead of equal counts per bin.
    """
    days = t_max - t_min + 1
    if days <= 1 or t_max <= t_min:
        ords = [x[0] for x in samples]
        lo_o, hi_o = (min(ords), max(ords)) if ords else (t_min, t_max)
        accs_all = [x[1] for x in samples]
        accs_w = [x[1] for x in samples if x[2]]
        accs_b = [x[1] for x in samples if not x[2]]
        return [
            (
                50.0,
                float(median(accs_all)) if accs_all else 0.0,
                float(median(accs_w)) if accs_w else float("nan"),
                float(median(accs_b)) if accs_b else float("nan"),
                len(accs_all),
                date.fromordinal(lo_o).isoformat(),
                date.fromordinal(hi_o).isoformat(),
            )
        ]

    n_bins = max(2, min(n_bins, days))
    rows: List[Tuple[float, float, float, float, int, str, str]] = []
    for b in range(n_bins):
        lo_o = t_min + (days * b) // n_bins
        hi_o = t_min + (days * (b + 1)) // n_bins - 1
        chunk = [x for x in samples if lo_o <= x[0] <= hi_o]
        if not chunk:
            continue
        ords = [x[0] for x in chunk]
        lo_g = min(ords)
        hi_g = max(ords)
        rows.append(_accuracy_bin_row_from_chunk(chunk, lo_g, hi_g, t_min, t_max))
    rows.sort(key=lambda x: x[0])
    return rows


def _move_quality_bins_equal_ordinal_width(
    samples_vec: List[Tuple[int, Tuple[float, ...]]],
    n_bins: int,
    n_series: int,
    t_min: int,
    t_max: int,
) -> List[Tuple[float, int, str, str, Tuple[float, ...]]]:
    days = t_max - t_min + 1
    if days <= 1 or t_max <= t_min:
        vecs = [x[1] for x in samples_vec]
        ords = [x[0] for x in samples_vec]
        lo_o, hi_o = (min(ords), max(ords)) if ords else (t_min, t_max)
        medians_list: List[float] = []
        for i in range(n_series):
            col = [v[i] for v in vecs]
            medians_list.append(float(median(col)) if col else 0.0)
        return [(50.0, len(vecs), date.fromordinal(lo_o).isoformat(), date.fromordinal(hi_o).isoformat(), tuple(medians_list))]

    n_bins = max(2, min(n_bins, days))
    bins_out: List[Tuple[float, int, str, str, Tuple[float, ...]]] = []
    for b in range(n_bins):
        lo_o = t_min + (days * b) // n_bins
        hi_o = t_min + (days * (b + 1)) // n_bins - 1
        chunk = [(o, v) for o, v in samples_vec if lo_o <= o <= hi_o]
        if not chunk:
            continue
        ords = [x[0] for x in chunk]
        vecs = [x[1] for x in chunk]
        lo_g, hi_g = min(ords), max(ords)
        time_pct = _calendar_bin_center_time_pct(lo_g, hi_g, t_min, t_max)
        medians_list = []
        for i in range(n_series):
            col = [v[i] for v in vecs]
            medians_list.append(float(median(col)) if col else 0.0)
        bins_out.append(
            (
                time_pct,
                len(chunk),
                date.fromordinal(lo_g).isoformat(),
                date.fromordinal(hi_g).isoformat(),
                tuple(medians_list),
            )
        )
    bins_out.sort(key=lambda x: x[0])
    return bins_out


def _acpl_phase_bins_equal_ordinal_width(
    samples_vec: List[Tuple[int, Tuple[Optional[float], Optional[float], Optional[float]]]],
    n_bins: int,
    t_min: int,
    t_max: int,
) -> List[Tuple[float, int, str, str, Tuple[float, ...]]]:
    days = t_max - t_min + 1
    if days <= 1 or t_max <= t_min:
        triples = [x[1] for x in samples_vec]
        ords = [x[0] for x in samples_vec]
        lo_o, hi_o = (min(ords), max(ords)) if ords else (t_min, t_max)
        medians_list: List[float] = []
        for i_phase in range(3):
            col = [
                float(t[i_phase])
                for t in triples
                if t[i_phase] is not None and math.isfinite(float(t[i_phase]))
            ]
            medians_list.append(float(median(col)) if col else float("nan"))
        return [
            (
                50.0,
                len(triples),
                date.fromordinal(lo_o).isoformat(),
                date.fromordinal(hi_o).isoformat(),
                tuple(medians_list),
            )
        ]

    n_bins = max(2, min(n_bins, days))
    bins_out: List[Tuple[float, int, str, str, Tuple[float, ...]]] = []
    for b in range(n_bins):
        lo_o = t_min + (days * b) // n_bins
        hi_o = t_min + (days * (b + 1)) // n_bins - 1
        chunk = [(o, t) for o, t in samples_vec if lo_o <= o <= hi_o]
        if not chunk:
            continue
        ords = [x[0] for x in chunk]
        triples = [x[1] for x in chunk]
        lo_g, hi_g = min(ords), max(ords)
        time_pct = _calendar_bin_center_time_pct(lo_g, hi_g, t_min, t_max)
        medians_list = []
        for i_phase in range(3):
            col = [
                float(t[i_phase])
                for t in triples
                if t[i_phase] is not None and math.isfinite(float(t[i_phase]))
            ]
            medians_list.append(float(median(col)) if col else float("nan"))
        bins_out.append(
            (
                time_pct,
                len(chunk),
                date.fromordinal(lo_g).isoformat(),
                date.fromordinal(hi_g).isoformat(),
                tuple(medians_list),
            )
        )
    bins_out.sort(key=lambda x: x[0])
    return bins_out


def _move_quality_bins_ordinal_quantile(
    samples_vec: List[Tuple[int, Tuple[float, ...]]],
    n_bins: int,
    n_series: int,
    t_min: int,
    t_max: int,
) -> List[Tuple[float, int, str, str, Tuple[float, ...]]]:
    sorted_s = sorted(samples_vec, key=lambda x: x[0])
    n = len(sorted_s)
    n_bins = max(2, min(n_bins, n))
    bins_out: List[Tuple[float, int, str, str, Tuple[float, ...]]] = []
    for b in range(n_bins):
        lo_i = b * n // n_bins
        hi_i = (b + 1) * n // n_bins if b < n_bins - 1 else n
        chunk = sorted_s[lo_i:hi_i]
        ords = [x[0] for x in chunk]
        vecs = [x[1] for x in chunk]
        lo_o = max(min(ords), t_min)
        hi_o = min(max(ords), t_max)
        if lo_o > hi_o:
            lo_o, hi_o = hi_o, lo_o
        time_pct = _calendar_bin_center_time_pct(lo_o, hi_o, t_min, t_max)
        medians_list: List[float] = []
        for i in range(n_series):
            col = [v[i] for v in vecs]
            medians_list.append(float(median(col)) if col else 0.0)
        cnt = len(vecs)
        lab0 = date.fromordinal(lo_o).isoformat()
        lab1 = date.fromordinal(hi_o).isoformat()
        bins_out.append((time_pct, cnt, lab0, lab1, tuple(medians_list)))
    bins_out.sort(key=lambda x: x[0])
    return bins_out


def _acpl_phase_bins_ordinal_quantile(
    samples_vec: List[Tuple[int, Tuple[Optional[float], Optional[float], Optional[float]]]],
    n_bins: int,
    t_min: int,
    t_max: int,
) -> List[Tuple[float, int, str, str, Tuple[float, ...]]]:
    sorted_s = sorted(samples_vec, key=lambda x: x[0])
    n = len(sorted_s)
    n_bins = max(2, min(n_bins, n))
    bins_out: List[Tuple[float, int, str, str, Tuple[float, ...]]] = []
    for b in range(n_bins):
        lo_i = b * n // n_bins
        hi_i = (b + 1) * n // n_bins if b < n_bins - 1 else n
        chunk = sorted_s[lo_i:hi_i]
        ords = [x[0] for x in chunk]
        triples = [x[1] for x in chunk]
        lo_o = max(min(ords), t_min)
        hi_o = min(max(ords), t_max)
        if lo_o > hi_o:
            lo_o, hi_o = hi_o, lo_o
        time_pct = _calendar_bin_center_time_pct(lo_o, hi_o, t_min, t_max)
        medians_list: List[float] = []
        for i_phase in range(3):
            col = [
                float(t[i_phase])
                for t in triples
                if t[i_phase] is not None and math.isfinite(float(t[i_phase]))
            ]
            medians_list.append(float(median(col)) if col else float("nan"))
        cnt = len(triples)
        lab0 = date.fromordinal(lo_o).isoformat()
        lab1 = date.fromordinal(hi_o).isoformat()
        bins_out.append((time_pct, cnt, lab0, lab1, tuple(medians_list)))
    bins_out.sort(key=lambda x: x[0])
    return bins_out


def _ordinal_fallback_subcaption_suffix(chart_cfg: Dict[str, Any]) -> str:
    return str(chart_cfg.get("ordinal_fallback_subcaption_suffix", "")).strip()


def _trend_axis_ordinals_for_quantile_bins(
    bin_edges_iso: Sequence[Tuple[str, str]],
    t_min: int,
    t_max: int,
) -> Tuple[int, int]:
    """Chart X extent for ordinal-quantile bins.

    Each bin stores min/max game dates in the slice (``lab0``/``lab1``); the UI draws the point
    at the midpoint ordinal. Using the global ``t_min``/``t_max`` for the axis then leaves a
    large empty margin when the first or last bin spans many calendar days. Match the axis to
    the span of those midpoints (with padding), clamped to the sample range.
    """
    centers: List[int] = []
    for lab0, lab1 in bin_edges_iso:
        try:
            o0 = date.fromisoformat(str(lab0).strip()).toordinal()
            o1 = date.fromisoformat(str(lab1).strip()).toordinal()
            centers.append((o0 + o1) // 2)
        except (ValueError, TypeError, AttributeError):
            continue
    if not centers:
        return t_min, t_max
    c_min = min(centers)
    c_max = max(centers)
    span = c_max - c_min
    if span <= 0:
        pad = 7
    else:
        pad = max(1, min(14, max(3, span // 10)))
    axis_min = max(t_min, c_min - pad)
    axis_max = min(t_max, c_max + pad)
    if axis_max <= axis_min:
        return t_min, t_max
    return axis_min, axis_max


def _collect_trends_dated_player_stats(
    game_results: List[Dict[str, Any]],
    analyzed_games: List[GameData],
) -> List[Tuple[int, PlayerStatistics]]:
    """(game_date_ordinal, game_stats) for analyzed games with a usable PGN date (see trends ordinal)."""
    out: List[Tuple[int, PlayerStatistics]] = []
    for result in game_results:
        idx = result.get("index", 0)
        if idx < 0 or idx >= len(analyzed_games):
            continue
        g = analyzed_games[idx]
        ord_val = _game_date_ordinal_for_trends(g.date)
        if ord_val is None:
            continue
        gs = result.get("game_stats")
        if gs is None:
            continue
        out.append((ord_val, gs))
    return out


def _collect_trends_dated_accuracy_with_color(
    game_results: List[Dict[str, Any]],
    analyzed_games: List[GameData],
) -> List[Tuple[int, float, bool]]:
    """(ordinal, accuracy, is_white) for dated games; same eligibility as dated player stats."""
    out: List[Tuple[int, float, bool]] = []
    for result in game_results:
        idx = result.get("index", 0)
        if idx < 0 or idx >= len(analyzed_games):
            continue
        g = analyzed_games[idx]
        ord_val = _game_date_ordinal_for_trends(g.date)
        if ord_val is None:
            continue
        gs = result.get("game_stats")
        if gs is None:
            continue
        is_w = bool(result.get("is_white", False))
        out.append((ord_val, float(gs.accuracy), is_w))
    return out


def merged_player_stats_time_series_chart_cfg(
    player_stats: Dict[str, Any],
    chart_key: str,
) -> Dict[str, Any]:
    """Merge shared ``time_series`` with per-chart settings.

    ``accuracy_over_time_chart`` uses ``time_series`` then its own block. Move-quality,
    top-move, and ACPL-phase charts also layer ``accuracy_over_time_chart`` in between so
    legacy configs that only defined binning under accuracy still apply to those charts.
    """
    ts = dict(player_stats.get("time_series") or {})
    acc = dict(player_stats.get("accuracy_over_time_chart") or {})
    own = dict(player_stats.get(chart_key) or {})
    if chart_key == "accuracy_over_time_chart":
        return {**ts, **own}
    if chart_key in (
        "move_quality_over_time_chart",
        "acpl_phase_over_time_chart",
        "top_move_over_time_chart",
    ):
        return {**ts, **acc, **own}
    return {**ts, **own}


def _merge_move_quality_chart_cfg(ps: Dict[str, Any]) -> Dict[str, Any]:
    return merged_player_stats_time_series_chart_cfg(ps, "move_quality_over_time_chart")


def _merge_top_move_chart_cfg(ps: Dict[str, Any]) -> Dict[str, Any]:
    return merged_player_stats_time_series_chart_cfg(ps, "top_move_over_time_chart")


def _merge_acpl_phase_chart_cfg(ps: Dict[str, Any]) -> Dict[str, Any]:
    return merged_player_stats_time_series_chart_cfg(ps, "acpl_phase_over_time_chart")


def _phase_acpl_for_trends(phase: Optional[PhaseStatistics]) -> Optional[float]:
    """Per-phase average CPL for time-series aggregation; None if phase unused or non-finite."""
    if phase is None or phase.moves <= 0:
        return None
    v = float(phase.average_cpl)
    return v if math.isfinite(v) else None


def _collect_trends_dated_phase_acpl_triples(
    game_results: List[Dict[str, Any]],
    analyzed_games: List[GameData],
) -> List[Tuple[int, Tuple[Optional[float], Optional[float], Optional[float]]]]:
    """Per game with full date: median ACPL per phase (None if no moves in that phase)."""
    out: List[Tuple[int, Tuple[Optional[float], Optional[float], Optional[float]]]] = []
    for result in game_results:
        idx = result.get("index", 0)
        if idx < 0 or idx >= len(analyzed_games):
            continue
        g = analyzed_games[idx]
        ord_val = _game_date_ordinal_for_trends(g.date)
        if ord_val is None:
            continue
        go = result.get("game_opening")
        gm = result.get("game_middlegame")
        ge = result.get("game_endgame")
        o = _phase_acpl_for_trends(go)
        m = _phase_acpl_for_trends(gm)
        e = _phase_acpl_for_trends(ge)
        if o is None and m is None and e is None:
            continue
        out.append((ord_val, (o, m, e)))
    return out


_MQ_STAT_TO_ATTR = {
    "book": "book_moves",
    "brilliant": "brilliant_moves",
    "best": "best_moves",
    "good": "good_moves",
    "inaccuracy": "inaccuracies",
    "mistake": "mistakes",
    "miss": "misses",
    "blunder": "blunders",
}


def _player_move_quality_pct_vector(gs: PlayerStatistics, stat_ids: List[str]) -> Optional[Tuple[float, ...]]:
    """Per-game percentages of total moves for each stat id; None if no moves."""
    tm = gs.total_moves
    if tm <= 0:
        return None
    vec: List[float] = []
    for sid in stat_ids:
        attr = _MQ_STAT_TO_ATTR.get(sid)
        if not attr:
            return None
        n = int(getattr(gs, attr, 0) or 0)
        vec.append(100.0 * n / tm)
    return tuple(vec)


def _parse_move_quality_series_config(chart_cfg: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Enabled series as (stat_id, label)."""
    raw = chart_cfg.get("series")
    if not isinstance(raw, list):
        return []
    out: List[Tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not item.get("enabled", True):
            continue
        sid = str(item.get("id", "")).strip()
        if sid not in _MQ_STAT_TO_ATTR:
            continue
        lbl = str(item.get("label", sid))
        out.append((sid, lbl))
    return out


_TOP_MOVE_STAT_TO_ATTR = {
    "best_move": "best_move_percentage",
    "top3_move": "top3_move_percentage",
    "blunder_rate": "blunder_rate",
}


def _player_top_move_pct_vector(gs: PlayerStatistics, stat_ids: List[str]) -> Optional[Tuple[float, ...]]:
    """Per-game Best / Top3 / Blunder % (already percentages on ``PlayerStatistics``)."""
    if gs.total_moves <= 0:
        return None
    vec: List[float] = []
    for sid in stat_ids:
        attr = _TOP_MOVE_STAT_TO_ATTR.get(sid)
        if not attr:
            return None
        vec.append(float(getattr(gs, attr, 0.0)))
    return tuple(vec)


def _parse_top_move_series_config(chart_cfg: Dict[str, Any]) -> List[Tuple[str, str]]:
    """Enabled top-move progression series as (stat_id, label)."""
    raw = chart_cfg.get("series")
    if not isinstance(raw, list):
        return []
    out: List[Tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if not item.get("enabled", True):
            continue
        sid = str(item.get("id", "")).strip()
        if sid not in _TOP_MOVE_STAT_TO_ATTR:
            continue
        lbl = str(item.get("label", sid))
        out.append((sid, lbl))
    return out


def _build_accuracy_over_time_series(
    game_results: List[Dict[str, Any]],
    analyzed_games: List[GameData],
    config: Dict[str, Any],
    analyzed_count: int,
) -> Tuple[
    List[Tuple[float, float, float, float, int, str, str]],
    str,
    int,
    int,
    str,
]:
    """Median accuracy over time using ``target_progression_bins`` (quantile or equal-width; see config).

    Uses ``GameData.date`` and per-game stats from ``game_results``. X positions follow real dates;
    ``calendar_mode`` is left empty so the axis picks tick density from the date span.

    Returns:
        (series, subcaption, ordinal_min, ordinal_max, calendar_mode).
        Series tuples: (time_pct, median_all, median_white, median_black, count, lab0, lab1).
    """
    ui = config.get("ui", {})
    detail = ui.get("panels", {}).get("detail", {})
    ps = detail.get("player_stats", {})
    chart_cfg = merged_player_stats_time_series_chart_cfg(ps, "accuracy_over_time_chart")
    if not chart_cfg.get("enabled", True):
        return [], "", 0, 0, ""

    min_games = int(chart_cfg.get("min_games_with_full_date", 4))
    min_span_days = int(chart_cfg.get("min_span_days", 14))
    min_populated_bins = int(chart_cfg.get("min_populated_bins", 1))

    samples: List[Tuple[int, float, bool]] = _collect_trends_dated_accuracy_with_color(
        game_results, analyzed_games
    )

    dated_count = len(samples)
    template = str(
        chart_cfg.get(
            "subcaption_template",
            "Based on {dated} dated games (of {analyzed} analyzed).",
        )
    )
    subcaption = template.format(dated=dated_count, analyzed=analyzed_count)

    if dated_count < min_games:
        return [], subcaption, 0, 0, ""

    ordinals = [s[0] for s in samples]
    t_min = min(ordinals)
    t_max = max(ordinals)
    span_days = t_max - t_min
    if span_days > 0 and span_days < min_span_days:
        return [], subcaption, 0, 0, ""

    nqb = _ordinal_target_bin_count(chart_cfg, len(samples))
    use_tight_quantile_axis = False
    mode = ""
    if _ordinal_fallback_mode(chart_cfg) == "quantile":
        series = _accuracy_series_ordinal_quantile_bins(samples, nqb, t_min, t_max)
        use_tight_quantile_axis = True
    else:
        series = _accuracy_series_equal_ordinal_width_bins(samples, nqb, t_min, t_max)
    suf = _ordinal_fallback_subcaption_suffix(chart_cfg)
    if suf:
        subcaption = f"{subcaption} {suf}"

    if len(series) < min_populated_bins:
        return [], subcaption, 0, 0, ""

    series.sort(key=lambda x: x[0])
    ord_lo, ord_hi = t_min, t_max
    if series and use_tight_quantile_axis:
        ord_lo, ord_hi = _trend_axis_ordinals_for_quantile_bins([(r[5], r[6]) for r in series], t_min, t_max)
    return series, subcaption, ord_lo, ord_hi, mode


def _build_move_quality_over_time_series(
    game_results: List[Dict[str, Any]],
    analyzed_games: List[GameData],
    config: Dict[str, Any],
    analyzed_count: int,
) -> Tuple[
    List[Tuple[float, int, str, str, Tuple[float, ...]]],
    List[str],
    List[str],
    str,
    int,
    int,
    str,
]:
    """Median move-type % over time; same progression binning as accuracy (``target_progression_bins``).

    Returns:
        (bins, series_labels, series_ids, subcaption, ordinal_min, ordinal_max, calendar_mode).
        Each bin: (time_pct, games_in_bin, start_iso, end_iso, (median_pct per series)).
    """
    ui = config.get("ui", {})
    detail = ui.get("panels", {}).get("detail", {})
    ps = detail.get("player_stats", {})
    chart_cfg = _merge_move_quality_chart_cfg(ps)
    mq_block = ps.get("move_quality_over_time_chart", {})
    if not mq_block.get("enabled", True):
        return [], [], [], "", 0, 0, ""

    series_defs = _parse_move_quality_series_config(chart_cfg)
    if not series_defs:
        return [], [], [], "", 0, 0, ""

    stat_ids = [s for s, _ in series_defs]
    labels = [lb for _, lb in series_defs]

    min_games = int(chart_cfg.get("min_games_with_full_date", 4))
    min_span_days = int(chart_cfg.get("min_span_days", 14))
    min_populated_bins = int(chart_cfg.get("min_populated_bins", 1))

    dated = _collect_trends_dated_player_stats(game_results, analyzed_games)
    samples_vec: List[Tuple[int, Tuple[float, ...]]] = []
    for ord_val, gs in dated:
        vec = _player_move_quality_pct_vector(gs, stat_ids)
        if vec is None:
            continue
        samples_vec.append((ord_val, vec))

    dated_count = len(samples_vec)
    template = str(
        chart_cfg.get(
            "subcaption_template",
            "Based on {dated} dated games (of {analyzed} analyzed).",
        )
    )
    subcaption = template.format(dated=dated_count, analyzed=analyzed_count)

    if dated_count < min_games:
        return [], [], [], subcaption, 0, 0, ""

    ordinals = [s[0] for s in samples_vec]
    t_min = min(ordinals)
    t_max = max(ordinals)
    span_days = t_max - t_min
    if span_days > 0 and span_days < min_span_days:
        return [], [], [], subcaption, 0, 0, ""

    n_series = len(stat_ids)
    nqb = _ordinal_target_bin_count(chart_cfg, len(samples_vec))
    use_tight_quantile_axis = False
    mode = ""
    if _ordinal_fallback_mode(chart_cfg) == "quantile":
        bins_out = _move_quality_bins_ordinal_quantile(samples_vec, nqb, n_series, t_min, t_max)
        use_tight_quantile_axis = True
    else:
        bins_out = _move_quality_bins_equal_ordinal_width(samples_vec, nqb, n_series, t_min, t_max)
    suf = _ordinal_fallback_subcaption_suffix(chart_cfg)
    if suf:
        subcaption = f"{subcaption} {suf}"

    if len(bins_out) < min_populated_bins:
        return [], [], [], subcaption, 0, 0, ""

    bins_out.sort(key=lambda x: x[0])
    ord_lo, ord_hi = t_min, t_max
    if bins_out and use_tight_quantile_axis:
        ord_lo, ord_hi = _trend_axis_ordinals_for_quantile_bins([(r[2], r[3]) for r in bins_out], t_min, t_max)
    return bins_out, labels, stat_ids, subcaption, ord_lo, ord_hi, mode


def _build_top_move_over_time_series(
    game_results: List[Dict[str, Any]],
    analyzed_games: List[GameData],
    config: Dict[str, Any],
    analyzed_count: int,
) -> Tuple[
    List[Tuple[float, int, str, str, Tuple[float, ...]]],
    List[str],
    List[str],
    str,
    int,
    int,
    str,
]:
    """Median best-move %, top-3 %, and blunder % vs game date (same binning as move quality)."""
    ui = config.get("ui", {})
    detail = ui.get("panels", {}).get("detail", {})
    ps = detail.get("player_stats", {})
    chart_cfg = _merge_top_move_chart_cfg(ps)
    tm_block = ps.get("top_move_over_time_chart", {})
    if not tm_block.get("enabled", True):
        return [], [], [], "", 0, 0, ""

    series_defs = _parse_top_move_series_config(chart_cfg)
    if not series_defs:
        return [], [], [], "", 0, 0, ""

    stat_ids = [s for s, _ in series_defs]
    labels = [lb for _, lb in series_defs]

    min_games = int(chart_cfg.get("min_games_with_full_date", 4))
    min_span_days = int(chart_cfg.get("min_span_days", 14))
    min_populated_bins = int(chart_cfg.get("min_populated_bins", 1))

    dated = _collect_trends_dated_player_stats(game_results, analyzed_games)
    samples_vec: List[Tuple[int, Tuple[float, ...]]] = []
    for ord_val, gs in dated:
        vec = _player_top_move_pct_vector(gs, stat_ids)
        if vec is None:
            continue
        samples_vec.append((ord_val, vec))

    dated_count = len(samples_vec)
    template = str(
        chart_cfg.get(
            "subcaption_template",
            "Based on {dated} dated games (of {analyzed} analyzed).",
        )
    )
    subcaption = template.format(dated=dated_count, analyzed=analyzed_count)

    if dated_count < min_games:
        return [], [], [], subcaption, 0, 0, ""

    ordinals = [s[0] for s in samples_vec]
    t_min = min(ordinals)
    t_max = max(ordinals)
    span_days = t_max - t_min
    if span_days > 0 and span_days < min_span_days:
        return [], [], [], subcaption, 0, 0, ""

    n_series = len(stat_ids)
    nqb = _ordinal_target_bin_count(chart_cfg, len(samples_vec))
    use_tight_quantile_axis = False
    mode = ""
    if _ordinal_fallback_mode(chart_cfg) == "quantile":
        bins_out = _move_quality_bins_ordinal_quantile(samples_vec, nqb, n_series, t_min, t_max)
        use_tight_quantile_axis = True
    else:
        bins_out = _move_quality_bins_equal_ordinal_width(samples_vec, nqb, n_series, t_min, t_max)
    suf = _ordinal_fallback_subcaption_suffix(chart_cfg)
    if suf:
        subcaption = f"{subcaption} {suf}"

    if len(bins_out) < min_populated_bins:
        return [], [], [], subcaption, 0, 0, ""

    bins_out.sort(key=lambda x: x[0])
    ord_lo, ord_hi = t_min, t_max
    if bins_out and use_tight_quantile_axis:
        ord_lo, ord_hi = _trend_axis_ordinals_for_quantile_bins([(r[2], r[3]) for r in bins_out], t_min, t_max)
    return bins_out, labels, stat_ids, subcaption, ord_lo, ord_hi, mode


def _build_acpl_phase_over_time_series(
    game_results: List[Dict[str, Any]],
    analyzed_games: List[GameData],
    config: Dict[str, Any],
    analyzed_count: int,
) -> Tuple[
    List[Tuple[float, int, str, str, Tuple[float, ...]]],
    List[str],
    List[str],
    str,
    int,
    int,
    str,
]:
    """Median phase ACPL over time; same progression binning as accuracy (``target_progression_bins``).

    Missing phase in a bin yields ``nan`` for that series at that bin.
    """
    ui = config.get("ui", {})
    detail = ui.get("panels", {}).get("detail", {})
    ps = detail.get("player_stats", {})
    chart_cfg = _merge_acpl_phase_chart_cfg(ps)
    ap_block = ps.get("acpl_phase_over_time_chart", {})
    if not ap_block.get("enabled", True):
        return [], [], [], "", 0, 0, ""

    labels = ["Opening", "Middlegame", "Endgame"]
    stat_ids = ["opening", "middlegame", "endgame"]

    min_games = int(chart_cfg.get("min_games_with_full_date", 4))
    min_span_days = int(chart_cfg.get("min_span_days", 14))
    min_populated_bins = int(chart_cfg.get("min_populated_bins", 1))

    samples_vec = _collect_trends_dated_phase_acpl_triples(game_results, analyzed_games)
    dated_count = len(samples_vec)
    template = str(
        chart_cfg.get(
            "subcaption_template",
            "Median ACPL per phase; {dated} dated games (of {analyzed} analyzed). Lower is better.",
        )
    )
    subcaption = template.format(dated=dated_count, analyzed=analyzed_count)

    if dated_count < min_games:
        return [], [], [], subcaption, 0, 0, ""

    ordinals = [s[0] for s in samples_vec]
    t_min = min(ordinals)
    t_max = max(ordinals)
    span_days = t_max - t_min
    if span_days > 0 and span_days < min_span_days:
        return [], [], [], subcaption, 0, 0, ""

    nqb = _ordinal_target_bin_count(chart_cfg, len(samples_vec))
    use_tight_quantile_axis = False
    mode = ""
    if _ordinal_fallback_mode(chart_cfg) == "quantile":
        bins_out = _acpl_phase_bins_ordinal_quantile(samples_vec, nqb, t_min, t_max)
        use_tight_quantile_axis = True
    else:
        bins_out = _acpl_phase_bins_equal_ordinal_width(samples_vec, nqb, t_min, t_max)
    suf = _ordinal_fallback_subcaption_suffix(chart_cfg)
    if suf:
        subcaption = f"{subcaption} {suf}"

    if len(bins_out) < min_populated_bins:
        return [], [], [], subcaption, 0, 0, ""

    bins_out.sort(key=lambda x: x[0])

    any_finite = False
    for row in bins_out:
        for v in row[4]:
            if not math.isnan(v):
                any_finite = True
                break
        if any_finite:
            break
    if not any_finite:
        return [], [], [], "", 0, 0, ""

    ord_lo, ord_hi = t_min, t_max
    if bins_out and use_tight_quantile_axis:
        ord_lo, ord_hi = _trend_axis_ordinals_for_quantile_bins([(r[2], r[3]) for r in bins_out], t_min, t_max)
    return bins_out, labels, stat_ids, subcaption, ord_lo, ord_hi, mode


@dataclass
class AggregatedPlayerStats:
    """Aggregated statistics for a player across multiple games."""
    total_games: int
    analyzed_games: int
    wins: int
    draws: int
    losses: int
    win_rate: float
    player_stats: PlayerStatistics
    opening_stats: PhaseStatistics
    middlegame_stats: PhaseStatistics
    endgame_stats: PhaseStatistics
    top_openings: List[Tuple[str, Optional[str], int]]  # List of (ECO, opening_name, count) tuples
    worst_accuracy_openings: List[Tuple[str, Optional[str], float, int]]  # List of (ECO, opening_name, avg_cpl, count) tuples
    best_accuracy_openings: List[Tuple[str, Optional[str], float, int]]  # List of (ECO, opening_name, avg_cpl, count) tuples
    # Additional aggregate accuracy / CPL / Top3 Move % information across games
    min_accuracy: float
    max_accuracy: float
    min_acpl: float
    max_acpl: float
    min_top3_move_pct: float
    max_top3_move_pct: float
    min_best_move_pct: float
    max_best_move_pct: float
    min_blunder_rate: float
    max_blunder_rate: float
    # Per-game accuracy samples for distribution visualizations
    accuracy_values: List[float]
    # Running accuracy by game progress (0–100%): list of (progress_pct, avg_accuracy) for chart
    accuracy_by_progress: List[Tuple[float, float]]
    # Opponents' average running accuracy by game progress (same bins) for chart reference line
    opponent_accuracy_by_progress: List[Tuple[float, float]]
    # Performance by endgame type:
    # (display_label, endgame_accuracy_pct, game_count, game_accuracy_pct), sorted by game_count descending.
    accuracy_by_endgame_type: List[Tuple[str, float, int, float]]
    # Endgame tree (expandable in UI):
    # (group_key, group_display, group_endgame_accuracy, group_game_accuracy,
    #  group_count, group_white, group_black,
    #  [(raw_type, type_display, type_endgame_accuracy, type_game_accuracy,
    #    type_count, type_white, type_black), ...]), sorted by group_count descending.
    accuracy_by_endgame_type_grouped: List[
        Tuple[str, str, float, float, int, int, int, List[Tuple[str, str, float, float, int, int, int]]]
    ]
    # Median accuracy vs game date (binned). Empty if eligibility thresholds are not met.
    # Tuple: (time_pct, median_all, median_white, median_black, games_in_bin, lab0, lab1).
    # White/black medians are nan when that color has no games in the bin.
    accuracy_over_time: List[Tuple[float, float, float, float, int, str, str]]
    trends_subcaption: str
    trends_ordinal_min: int
    trends_ordinal_max: int
    # Empty: x-axis infers tick density from date span. Legacy day|week|month|year when set.
    trends_calendar_mode: str
    # Median per-game % of moves per classification vs game date (progression bins). Parallel labels/ids.
    move_quality_over_time: List[Tuple[float, int, str, str, Tuple[float, ...]]]
    move_quality_series_labels: List[str]
    move_quality_series_ids: List[str]
    move_quality_subcaption: str
    move_quality_ordinal_min: int
    move_quality_ordinal_max: int
    move_quality_calendar_mode: str
    # Median best / top-3 / blunder % vs game date (progression bins).
    top_move_over_time: List[Tuple[float, int, str, str, Tuple[float, ...]]]
    top_move_series_labels: List[str]
    top_move_series_ids: List[str]
    top_move_subcaption: str
    top_move_ordinal_min: int
    top_move_ordinal_max: int
    top_move_calendar_mode: str
    # Median phase ACPL vs game date (calendar bins); tuple may contain nan per phase.
    acpl_phase_over_time: List[Tuple[float, int, str, str, Tuple[float, ...]]]
    acpl_phase_series_labels: List[str]
    acpl_phase_series_ids: List[str]
    acpl_phase_subcaption: str
    acpl_phase_ordinal_min: int
    acpl_phase_ordinal_max: int
    acpl_phase_calendar_mode: str


class PlayerStatsService:
    """Service for aggregating player statistics across games."""
    
    def __init__(self, config: Dict[str, Any], game_controller: Optional[GameController] = None):
        """Initialize the player stats service.
        
        Args:
            config: Configuration dictionary.
            game_controller: Optional GameController for extracting moves from games.
        """
        self.config = config
        self.game_controller = game_controller
        self.summary_service = GameSummaryService(config)
    
    def get_player_games(self, player_name: str, databases: List[DatabaseModel], 
                        only_analyzed: bool = True) -> Tuple[List[GameData], int]:
        """Get all games for a player from the given databases.
        
        Args:
            player_name: Player name to search for.
            databases: List of DatabaseModel instances to search.
            only_analyzed: If True, only return analyzed games.
            
        Returns:
            Tuple of (list of GameData, total_count_including_unanalyzed).
        """
        player_games: List[GameData] = []
        total_count = 0
        
        for database in databases:
            games = database.get_all_games()
            for game in games:
                # Check if player is white or black
                # Use exact matching to preserve whitespace and special characters
                # This ensures players with trailing/leading whitespace are correctly matched
                is_player = False
                if game.white and game.white == player_name:
                    is_player = True
                elif game.black and game.black == player_name:
                    is_player = True
                
                if is_player:
                    total_count += 1
                    if not only_analyzed or game.analyzed:
                        player_games.append(game)
        
        return (player_games, total_count)
    
    def aggregate_player_statistics(self, player_name: str, games: List[GameData],
                                   game_controller: Optional[GameController] = None,
                                   progress_callback: Optional[Callable[[int, str], None]] = None,
                                   cancellation_check: Optional[Callable[[], bool]] = None) -> Tuple[Optional[AggregatedPlayerStats], List[GameSummary]]:
        """Aggregate statistics for a player across multiple games.
        
        Args:
            player_name: Player name.
            games: List of GameData instances for this player.
            game_controller: Optional GameController for extracting moves (used for fallback).
            progress_callback: Optional callback function(completed: int, status: str) for progress updates.
            cancellation_check: Optional function() -> bool to check if operation should be cancelled.
            
        Returns:
            Tuple of (AggregatedPlayerStats instance, List[GameSummary]) or (None, []) if no analyzed games found.
        """
        logging_service = LoggingService.get_instance()
        
        if not games:
            return (None, [])
        
        # Separate analyzed and unanalyzed games
        analyzed_games = [g for g in games if g.analyzed]
        if not analyzed_games:
            return (None, [])
        
        total_games = len(analyzed_games)
        logging_service.debug(f"Starting player stats aggregation: player={player_name}, games={total_games}")
        
        # Worker count from config (reserved_cores + max_workers_cap)
        max_workers = get_process_pool_max_workers(os.cpu_count(), self.config)
        
        # Process games in parallel
        game_results: List[Dict[str, Any]] = []
        completed_count = 0
        
        executor = None
        try:
            log_queue = LoggingService.get_queue()
            executor = ProcessPoolExecutor(
                max_workers=max_workers,
                initializer=init_worker_logging,
                initargs=(log_queue,)
            )
            # Submit all games for processing (pass index so results can be restored to input order)
            future_to_game = {
                executor.submit(
                    _process_game_for_stats,
                    game.pgn,
                    game.result,
                    game.white,
                    game.black,
                    game.eco if game.eco else "",
                    player_name,
                    self.config,
                    idx,
                ): game
                for idx, game in enumerate(analyzed_games)
            }
            
            # Process results as they complete
            for future in as_completed(future_to_game):
                # Check for cancellation
                if cancellation_check and cancellation_check():
                    # Cancel remaining futures
                    for f in future_to_game:
                        f.cancel()
                    break
                
                try:
                    result = future.result()
                    if result:
                        game_results.append(result)
                    
                    # Update progress
                    completed_count += 1
                    if progress_callback:
                        progress_percent = 50 + int((completed_count / total_games) * 40)
                        progress_callback(
                            progress_percent,
                            f"Analyzing game {completed_count}/{total_games}..."
                        )
                except Exception as e:
                    # Skip cancelled futures silently (they're expected when cancelling)
                    from concurrent.futures import CancelledError
                    if isinstance(e, CancelledError):
                        continue
                    # Log other errors but continue processing other games
                    logging_service = LoggingService.get_instance()
                    logging_service.error(f"Error processing game: {e}", exc_info=e)
        finally:
            # Ensure executor is properly shut down
            # This waits for all processes to finish, even if cancelled
            # This is important to prevent "QThread destroyed while running" errors
            if executor:
                executor.shutdown(wait=True)
        
        if not game_results:
            logging_service.debug(f"Player stats aggregation completed: player={player_name}, games_processed=0, no_results")
            return (None, [])
        
        # Restore input order (as_completed returns in completion order)
        game_results.sort(key=lambda r: r.get('index', 0))
        
        # Extract game summaries for return
        game_summaries: List[GameSummary] = []
        for result in game_results:
            if 'game_summary' in result and result['game_summary']:
                game_summaries.append(result['game_summary'])
        
        # Aggregate results from parallel processing
        wins = 0
        draws = 0
        losses = 0
        
        all_moves_white: List[MoveData] = []
        all_moves_black: List[MoveData] = []
        
        white_games_count = 0
        black_games_count = 0
        
        elo_values: List[float] = []
        accuracy_values: List[float] = []
        accuracy_by_progress_bins: Dict[float, List[float]] = {}  # progress_pct -> list of accuracies
        opponent_accuracy_by_progress_bins: Dict[float, List[float]] = {}  # progress_pct -> list of opponent accuracies
        overall_cpl_values: List[float] = []
        overall_top3_pct_values: List[float] = []
        overall_best_move_pct_values: List[float] = []
        overall_blunder_rate_values: List[float] = []
        opening_accuracy_values = []
        middlegame_accuracy_values = []
        endgame_accuracy_values = []
        
        opening_moves_total = 0
        middlegame_moves_total = 0
        endgame_moves_total = 0
        opening_cpl_sum = 0.0
        middlegame_cpl_sum = 0.0
        endgame_cpl_sum = 0.0
        opening_cpl_count = 0
        middlegame_cpl_count = 0
        endgame_cpl_count = 0
        
        opening_book_moves = 0
        opening_brilliant_moves = 0
        opening_best_moves = 0
        opening_good_moves = 0
        opening_inaccuracies = 0
        opening_mistakes = 0
        opening_misses = 0
        opening_blunders = 0
        
        middlegame_book_moves = 0
        middlegame_brilliant_moves = 0
        middlegame_best_moves = 0
        middlegame_good_moves = 0
        middlegame_inaccuracies = 0
        middlegame_mistakes = 0
        middlegame_misses = 0
        middlegame_blunders = 0
        
        endgame_book_moves = 0
        endgame_brilliant_moves = 0
        endgame_best_moves = 0
        endgame_good_moves = 0
        endgame_inaccuracies = 0
        endgame_mistakes = 0
        endgame_misses = 0
        endgame_blunders = 0
        
        opening_counter = Counter()
        opening_cpl_data: Dict[Tuple[str, Optional[str]], List[float]] = {}
        # raw_type -> [(endgame_phase_accuracy, is_white, game_accuracy), ...]
        endgame_type_data: Dict[str, List[Tuple[float, bool, float]]] = {}
        
        for result in game_results:
            is_white_game = result['is_white']
            game_result = result['game_result']
            game_stats = result['game_stats']
            game_opening = result['game_opening']
            game_middlegame = result['game_middlegame']
            game_endgame = result['game_endgame']
            opening_key = result['opening_key']
            opening_avg_cpl = result['opening_avg_cpl']
            
            # Count results
            if (is_white_game and game_result == "1-0") or \
               (not is_white_game and game_result == "0-1"):
                wins += 1
            elif game_result == "1/2-1/2":
                draws += 1
            else:
                losses += 1
            
            # Track color distribution
            if is_white_game:
                white_games_count += 1
            else:
                black_games_count += 1
            
            # Collect moves for overall aggregation
            all_moves_white.extend(result['all_moves_white'])
            all_moves_black.extend(result['all_moves_black'])
            
            # Collect per-game values for averaging / distribution
            elo_values.append(game_stats.estimated_elo)
            accuracy_values.append(game_stats.accuracy)
            overall_cpl_values.append(game_stats.average_cpl)
            top3_pct = game_stats.top3_move_percentage if game_stats.top3_move_percentage is not None else 0.0
            overall_top3_pct_values.append(top3_pct)
            best_pct = game_stats.best_move_percentage if game_stats.best_move_percentage is not None else 0.0
            overall_best_move_pct_values.append(best_pct)
            blunder_rate = game_stats.blunder_rate if game_stats.blunder_rate is not None else 0.0
            overall_blunder_rate_values.append(blunder_rate)
            opening_accuracy_values.append(game_opening.accuracy)
            middlegame_accuracy_values.append(game_middlegame.accuracy)
            endgame_accuracy_values.append(game_endgame.accuracy)
            
            # Collect running accuracy by progress for chart
            for pct, acc in result.get('accuracy_by_progress', []):
                if acc is not None:
                    accuracy_by_progress_bins.setdefault(pct, []).append(acc)
            for pct, acc in result.get('opponent_accuracy_by_progress', []):
                if acc is not None:
                    opponent_accuracy_by_progress_bins.setdefault(pct, []).append(acc)
            
            # Collect phase statistics for aggregation
            opening_moves_total += game_opening.moves
            middlegame_moves_total += game_middlegame.moves
            endgame_moves_total += game_endgame.moves
            
            # Accumulate CPL for weighted average
            if game_opening.moves > 0:
                opening_cpl_sum += game_opening.average_cpl * game_opening.moves
                opening_cpl_count += game_opening.moves
            if game_middlegame.moves > 0:
                middlegame_cpl_sum += game_middlegame.average_cpl * game_middlegame.moves
                middlegame_cpl_count += game_middlegame.moves
            if game_endgame.moves > 0:
                endgame_cpl_sum += game_endgame.average_cpl * game_endgame.moves
                endgame_cpl_count += game_endgame.moves
            
            # Aggregate move classification counts for each phase
            opening_book_moves += game_opening.book_moves
            opening_brilliant_moves += game_opening.brilliant_moves
            opening_best_moves += game_opening.best_moves
            opening_good_moves += game_opening.good_moves
            opening_inaccuracies += game_opening.inaccuracies
            opening_mistakes += game_opening.mistakes
            opening_misses += game_opening.misses
            opening_blunders += game_opening.blunders
            
            middlegame_book_moves += game_middlegame.book_moves
            middlegame_brilliant_moves += game_middlegame.brilliant_moves
            middlegame_best_moves += game_middlegame.best_moves
            middlegame_good_moves += game_middlegame.good_moves
            middlegame_inaccuracies += game_middlegame.inaccuracies
            middlegame_mistakes += game_middlegame.mistakes
            middlegame_misses += game_middlegame.misses
            middlegame_blunders += game_middlegame.blunders
            
            endgame_book_moves += game_endgame.book_moves
            endgame_brilliant_moves += game_endgame.brilliant_moves
            endgame_best_moves += game_endgame.best_moves
            endgame_good_moves += game_endgame.good_moves
            endgame_inaccuracies += game_endgame.inaccuracies
            endgame_mistakes += game_endgame.mistakes
            endgame_misses += game_endgame.misses
            endgame_blunders += game_endgame.blunders
            
            # Collect accuracy by endgame type (for games that have a classified endgame type),
            # storing both endgame-phase accuracy and overall game accuracy, plus color.
            game_summary = result.get('game_summary')
            if game_summary and game_summary.endgame_type:
                endgame_type_data.setdefault(game_summary.endgame_type, []).append(
                    (game_endgame.accuracy, is_white_game, game_stats.accuracy)
                )
            
            # Track opening usage and CPL
            opening_counter[opening_key] += 1
            if opening_avg_cpl is not None:
                if opening_key not in opening_cpl_data:
                    opening_cpl_data[opening_key] = []
                opening_cpl_data[opening_key].append(opening_avg_cpl)
        
        # Aggregate stats over all of the player's moves (both colors), color-agnostic
        player_moves_white = self.summary_service._extract_player_moves(all_moves_white, is_white=True)
        player_moves_black = self.summary_service._extract_player_moves(all_moves_black, is_white=False)
        all_player_moves = player_moves_white + player_moves_black
        if not all_player_moves:
            return (None, [])

        aggregated_stats = self.summary_service._calculate_player_statistics(
            all_player_moves,
            has_won=0,
            has_drawn=0,
        )

        # Average the results (per-game metrics unchanged)
        if elo_values:
            averaged_elo = sum(elo_values) / len(elo_values)
            averaged_accuracy = sum(accuracy_values) / len(accuracy_values)
        else:
            averaged_elo = 0
            averaged_accuracy = 0.0

        # Override ELO and accuracy with per-game averaged values (same as before)
        aggregated_stats.estimated_elo = int(averaged_elo)
        aggregated_stats.accuracy = averaged_accuracy

        # Per-game min/max accuracy and ACPL (for display and distributions)
        if accuracy_values:
            min_accuracy = min(accuracy_values)
            max_accuracy = max(accuracy_values)
        else:
            min_accuracy = 0.0
            max_accuracy = 0.0

        if overall_cpl_values:
            min_acpl = min(overall_cpl_values)
            max_acpl = max(overall_cpl_values)
        else:
            min_acpl = 0.0
            max_acpl = 0.0

        if overall_top3_pct_values:
            min_top3_move_pct = min(overall_top3_pct_values)
            max_top3_move_pct = max(overall_top3_pct_values)
        else:
            min_top3_move_pct = 0.0
            max_top3_move_pct = 0.0

        if overall_best_move_pct_values:
            min_best_move_pct = min(overall_best_move_pct_values)
            max_best_move_pct = max(overall_best_move_pct_values)
        else:
            min_best_move_pct = 0.0
            max_best_move_pct = 0.0

        if overall_blunder_rate_values:
            min_blunder_rate = min(overall_blunder_rate_values)
            max_blunder_rate = max(overall_blunder_rate_values)
        else:
            min_blunder_rate = 0.0
            max_blunder_rate = 0.0
        
        # Average phase accuracies
        if opening_accuracy_values:
            averaged_opening_accuracy = sum(opening_accuracy_values) / len(opening_accuracy_values)
        else:
            averaged_opening_accuracy = 0.0
        
        if middlegame_accuracy_values:
            averaged_middlegame_accuracy = sum(middlegame_accuracy_values) / len(middlegame_accuracy_values)
        else:
            averaged_middlegame_accuracy = 0.0
        
        if endgame_accuracy_values:
            averaged_endgame_accuracy = sum(endgame_accuracy_values) / len(endgame_accuracy_values)
        else:
            averaged_endgame_accuracy = 0.0
        
        # Calculate weighted average CPL for each phase
        average_cpl_opening = (opening_cpl_sum / opening_cpl_count) if opening_cpl_count > 0 else 0.0
        average_cpl_middlegame = (middlegame_cpl_sum / middlegame_cpl_count) if middlegame_cpl_count > 0 else 0.0
        average_cpl_endgame = (endgame_cpl_sum / endgame_cpl_count) if endgame_cpl_count > 0 else 0.0
        
        # Create phase statistics with averaged accuracy values
        opening_stats = PhaseStatistics(
            moves=opening_moves_total,
            average_cpl=average_cpl_opening,
            accuracy=averaged_opening_accuracy,
            book_moves=opening_book_moves,
            brilliant_moves=opening_brilliant_moves,
            best_moves=opening_best_moves,
            good_moves=opening_good_moves,
            inaccuracies=opening_inaccuracies,
            mistakes=opening_mistakes,
            misses=opening_misses,
            blunders=opening_blunders
        )
        
        middlegame_stats = PhaseStatistics(
            moves=middlegame_moves_total,
            average_cpl=average_cpl_middlegame,
            accuracy=averaged_middlegame_accuracy,
            book_moves=middlegame_book_moves,
            brilliant_moves=middlegame_brilliant_moves,
            best_moves=middlegame_best_moves,
            good_moves=middlegame_good_moves,
            inaccuracies=middlegame_inaccuracies,
            mistakes=middlegame_mistakes,
            misses=middlegame_misses,
            blunders=middlegame_blunders
        )
        
        endgame_stats = PhaseStatistics(
            moves=endgame_moves_total,
            average_cpl=average_cpl_endgame,
            accuracy=averaged_endgame_accuracy,
            book_moves=endgame_book_moves,
            brilliant_moves=endgame_brilliant_moves,
            best_moves=endgame_best_moves,
            good_moves=endgame_good_moves,
            inaccuracies=endgame_inaccuracies,
            mistakes=endgame_mistakes,
            misses=endgame_misses,
            blunders=endgame_blunders
        )
        
        # Calculate win rate
        total_games = len(analyzed_games)
        win_rate = (wins / total_games * 100) if total_games > 0 else 0.0
        
        # Get top 3 most played openings
        top_openings = opening_counter.most_common(3)
        top_openings_list = [(eco, opening_name, count) for (eco, opening_name), count in top_openings]
        
        # Calculate average CPL for each opening across all games
        opening_avg_cpl: List[Tuple[Tuple[str, Optional[str]], float, int]] = []
        for opening_key, game_avg_cpls in opening_cpl_data.items():
            if game_avg_cpls:
                overall_avg_cpl = sum(game_avg_cpls) / len(game_avg_cpls)
                count = opening_counter[opening_key]
                opening_avg_cpl.append((opening_key, overall_avg_cpl, count))
        
        # Sort by average CPL (worst = highest CPL, best = lowest CPL)
        opening_avg_cpl.sort(key=lambda x: x[1], reverse=True)  # Highest CPL first (worst)
        worst_openings = [opening for opening in opening_avg_cpl if opening[1] > 0.0][:3]  # Top 3 worst, excluding 0 CPL
        worst_openings_list = [(eco, opening_name, avg_cpl, count) for (eco, opening_name), avg_cpl, count in worst_openings]
        
        opening_avg_cpl.sort(key=lambda x: x[1])  # Lowest CPL first (best)
        best_openings = opening_avg_cpl[:3]  # Top 3 best
        best_openings_list = [(eco, opening_name, avg_cpl, count) for (eco, opening_name), avg_cpl, count in best_openings]

        # Average running accuracy by progress for chart
        accuracy_by_progress_list: List[Tuple[float, float]] = []
        for pct in sorted(accuracy_by_progress_bins.keys()):
            values = accuracy_by_progress_bins[pct]
            if values:
                accuracy_by_progress_list.append((pct, sum(values) / len(values)))
        opponent_accuracy_by_progress_list: List[Tuple[float, float]] = []
        for pct in sorted(opponent_accuracy_by_progress_bins.keys()):
            values = opponent_accuracy_by_progress_bins[pct]
            if values:
                opponent_accuracy_by_progress_list.append((pct, sum(values) / len(values)))

        # Performance by endgame type (flat):
        # (display_label, endgame_accuracy_pct, game_count, game_accuracy_pct),
        # sorted by game_count descending.
        accuracy_by_endgame_type_list: List[Tuple[str, float, int, float]] = []
        for raw_type, data in endgame_type_data.items():
            if data:
                endgame_accuracies = [a for a, _, _ in data]
                game_accuracies = [g for _, _, g in data]
                display_name = self.summary_service.get_endgame_type_display_name(raw_type)
                avg_endgame_accuracy = sum(endgame_accuracies) / len(endgame_accuracies)
                avg_game_accuracy = sum(game_accuracies) / len(game_accuracies)
                accuracy_by_endgame_type_list.append(
                    (display_name, avg_endgame_accuracy, len(data), avg_game_accuracy)
                )
        accuracy_by_endgame_type_list.sort(key=lambda x: x[2], reverse=True)

        # Endgame tree grouped:
        # (group_key, group_display, group_endgame_accuracy, group_game_accuracy,
        #  group_count, group_white, group_black,
        #  [(raw_type, type_display, type_endgame_accuracy, type_game_accuracy,
        #    type_count, type_white, type_black), ...])
        group_to_types: Dict[str, List[Tuple[str, str, float, float, int, int, int]]] = {}
        for raw_type, data in endgame_type_data.items():
            if not data:
                continue
            endgame_accuracies = [a for a, _, _ in data]
            game_accuracies = [g for _, _, g in data]
            white_count = sum(1 for _, w, _ in data if w)
            black_count = sum(1 for _, w, _ in data if not w)
            count = len(data)
            avg_endgame_accuracy = sum(endgame_accuracies) / count
            avg_game_accuracy = sum(game_accuracies) / count
            group_key = self.summary_service.get_endgame_type_group(raw_type)
            display_name = self.summary_service.get_endgame_type_display_name(raw_type)
            group_to_types.setdefault(group_key, []).append(
                (raw_type, display_name, avg_endgame_accuracy, avg_game_accuracy, count, white_count, black_count)
            )
        accuracy_by_endgame_type_grouped_list: List[
            Tuple[str, str, float, float, int, int, int, List[Tuple[str, str, float, float, int, int, int]]]
        ] = []
        for group_key, types_list in group_to_types.items():
            group_count = sum(c for _, _, _, _, c, _, _ in types_list)
            group_white = sum(w for _, _, _, _, _, w, _ in types_list)
            group_black = sum(b for _, _, _, _, _, _, b in types_list)
            group_endgame_accuracy_sum = sum(acc * c for _, _, acc, _, c, _, _ in types_list)
            group_game_accuracy_sum = sum(acc_g * c for _, _, _, acc_g, c, _, _ in types_list)
            group_endgame_accuracy = group_endgame_accuracy_sum / group_count if group_count else 0.0
            group_game_accuracy = group_game_accuracy_sum / group_count if group_count else 0.0
            types_list_sorted = sorted(types_list, key=lambda x: x[4], reverse=True)
            group_display = self.summary_service.get_endgame_type_group_display_name(group_key)
            accuracy_by_endgame_type_grouped_list.append(
                (
                    group_key,
                    group_display,
                    group_endgame_accuracy,
                    group_game_accuracy,
                    group_count,
                    group_white,
                    group_black,
                    types_list_sorted,
                )
            )
        accuracy_by_endgame_type_grouped_list.sort(key=lambda x: x[4], reverse=True)

        over_time, trends_sub, ord_min, ord_max, trends_cal_mode = _build_accuracy_over_time_series(
            game_results,
            analyzed_games,
            self.config,
            len(analyzed_games),
        )
        if not over_time:
            ord_min = 0
            ord_max = 0
            trends_cal_mode = ""

        mq_bins, mq_labels, mq_ids, mq_sub, mq_omin, mq_omax, mq_cal_mode = _build_move_quality_over_time_series(
            game_results,
            analyzed_games,
            self.config,
            len(analyzed_games),
        )
        if not mq_bins:
            mq_omin = 0
            mq_omax = 0
            mq_cal_mode = ""
            mq_labels = []
            mq_ids = []

        tm_bins, tm_labels, tm_ids, tm_sub, tm_omin, tm_omax, tm_cal_mode = _build_top_move_over_time_series(
            game_results,
            analyzed_games,
            self.config,
            len(analyzed_games),
        )
        if not tm_bins:
            tm_omin = 0
            tm_omax = 0
            tm_cal_mode = ""
            tm_labels = []
            tm_ids = []

        ap_bins, ap_labels, ap_ids, ap_sub, ap_omin, ap_omax, ap_cal_mode = _build_acpl_phase_over_time_series(
            game_results,
            analyzed_games,
            self.config,
            len(analyzed_games),
        )
        if not ap_bins:
            ap_omin = 0
            ap_omax = 0
            ap_cal_mode = ""
            ap_labels = []
            ap_ids = []

        aggregated_stats = AggregatedPlayerStats(
            total_games=total_games,
            analyzed_games=len(analyzed_games),
            wins=wins,
            draws=draws,
            losses=losses,
            win_rate=win_rate,
            player_stats=aggregated_stats,
            opening_stats=opening_stats,
            middlegame_stats=middlegame_stats,
            endgame_stats=endgame_stats,
            top_openings=top_openings_list,
            worst_accuracy_openings=worst_openings_list,
            best_accuracy_openings=best_openings_list,
            min_accuracy=min_accuracy,
            max_accuracy=max_accuracy,
            min_acpl=min_acpl,
            max_acpl=max_acpl,
            min_top3_move_pct=min_top3_move_pct,
            max_top3_move_pct=max_top3_move_pct,
            min_best_move_pct=min_best_move_pct,
            max_best_move_pct=max_best_move_pct,
            min_blunder_rate=min_blunder_rate,
            max_blunder_rate=max_blunder_rate,
            accuracy_values=accuracy_values,
            accuracy_by_progress=accuracy_by_progress_list,
            opponent_accuracy_by_progress=opponent_accuracy_by_progress_list,
            accuracy_by_endgame_type=accuracy_by_endgame_type_list,
            accuracy_by_endgame_type_grouped=accuracy_by_endgame_type_grouped_list,
            accuracy_over_time=over_time,
            trends_subcaption=trends_sub,
            trends_ordinal_min=ord_min,
            trends_ordinal_max=ord_max,
            trends_calendar_mode=trends_cal_mode,
            move_quality_over_time=mq_bins,
            move_quality_series_labels=mq_labels,
            move_quality_series_ids=mq_ids,
            move_quality_subcaption=mq_sub,
            move_quality_ordinal_min=mq_omin,
            move_quality_ordinal_max=mq_omax,
            move_quality_calendar_mode=mq_cal_mode,
            top_move_over_time=tm_bins,
            top_move_series_labels=tm_labels,
            top_move_series_ids=tm_ids,
            top_move_subcaption=tm_sub,
            top_move_ordinal_min=tm_omin,
            top_move_ordinal_max=tm_omax,
            top_move_calendar_mode=tm_cal_mode,
            acpl_phase_over_time=ap_bins,
            acpl_phase_series_labels=ap_labels,
            acpl_phase_series_ids=ap_ids,
            acpl_phase_subcaption=ap_sub,
            acpl_phase_ordinal_min=ap_omin,
            acpl_phase_ordinal_max=ap_omax,
            acpl_phase_calendar_mode=ap_cal_mode,
        )
        
        logging_service.debug(f"Completed player stats aggregation: player={player_name}, games={total_games}, wins={wins}, draws={draws}, losses={losses}, win_rate={win_rate:.1f}%")
        
        return (aggregated_stats, game_summaries)

