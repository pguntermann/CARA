"""Service for automatically tagging games after analysis.

This runs as a post-processing phase after move analysis (manual or bulk) and assigns
predefined tags based on evaluation curve and phase boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import io
import chess.pgn

from app.models.moveslist_model import MoveData
from app.services.game_summary_service import GameSummaryService
from app.services.pgn_service import PgnService
from app.services.logging_service import LoggingService
from app.utils.game_tags_utils import (
    PGN_TAG_NAME_GAME_TAGS,
    format_game_tags,
    parse_game_tags,
)


AUTO_TAGS: Tuple[str, ...] = (
    "Blunder-decided",
    "Clean win",
    "Missed win",
    "Opening disaster",
    "Endgame grind",
    "Chaotic game",
)


@dataclass(frozen=True)
class AutoTaggingResult:
    detected_tags: List[str]
    reasons: Dict[str, str]


class GameAutoTaggingService:
    """Detect and apply auto-tags for a game given analyzed moves."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self._cfg = (config.get("game_analysis", {}) or {}).get("auto_game_tagging", {}) or {}

    def detect_tags(
        self,
        moves: Sequence[MoveData],
        *,
        game_result: Optional[str],
        enabled_tags: Optional[Sequence[str]] = None,
    ) -> AutoTaggingResult:
        """Return detected auto-tags based on evaluated move list."""
        if not moves:
            return AutoTaggingResult(detected_tags=[], reasons={})

        if enabled_tags is None:
            enabled_set = {t.casefold() for t in AUTO_TAGS}
        else:
            enabled_set = {str(t).casefold() for t in enabled_tags if str(t).strip()}

        summary_service = GameSummaryService(self.config)
        total_moves = len(moves)
        summary = summary_service.calculate_summary(list(moves), total_moves, game_result=game_result)

        # evaluation_data: list[(ply_index, eval_cp)] where eval is from White's perspective.
        eval_points = list(summary.evaluation_data or [])
        if not eval_points:
            return AutoTaggingResult(detected_tags=[], reasons={})

        eval_by_ply: Dict[int, float] = {int(ply): float(cp) for ply, cp in eval_points}
        plies_sorted = sorted(eval_by_ply.keys())

        def eval_at_or_after(ply: int) -> Optional[float]:
            for p in plies_sorted:
                if p >= ply:
                    return eval_by_ply[p]
            return None

        # Config (all thresholds in pawns, unless noted)
        win_eval_pawns = float(self._cfg.get("win_eval_pawns", 2.0))
        opening_disaster_pawns = float(self._cfg.get("opening_disaster_eval_pawns", 1.5))
        decisive_pawns = float(self._cfg.get("blunder_decided_decisive_eval_pawns", 3.0))
        never_recovered_pawns = float(self._cfg.get("blunder_decided_never_recovered_eval_pawns", 1.5))

        clean_win_large_adv_pawns = float(self._cfg.get("clean_win_large_advantage_pawns", 2.5))
        clean_win_allowed_dip_pawns = float(self._cfg.get("clean_win_allowed_dip_pawns", 0.5))
        clean_win_max_swing_pawns = float(self._cfg.get("clean_win_max_swing_pawns", 1.2))
        clean_win_min_plies = int(self._cfg.get("clean_win_min_plies_from_advantage", 10))

        chaotic_large_adv_pawns = float(self._cfg.get("chaotic_large_advantage_pawns", 2.0))
        chaotic_swing_pawns = float(self._cfg.get("chaotic_swing_pawns", 2.0))
        chaotic_min_swings = int(self._cfg.get("chaotic_min_swings", 6))

        grind_min_endgame_moves = int(self._cfg.get("endgame_grind_min_endgame_moves", 12))
        grind_stable_eval_pawns = float(self._cfg.get("endgame_grind_stable_eval_pawns", 0.8))
        grind_min_stable_plies = int(self._cfg.get("endgame_grind_min_stable_plies", 12))
        grind_resolution_eval_pawns = float(self._cfg.get("endgame_grind_resolution_eval_pawns", 2.0))

        reasons: Dict[str, str] = {}
        detected: List[str] = []

        # Helpers
        evals_cp = [eval_by_ply[p] for p in plies_sorted]
        max_eval_pawns = max(evals_cp) / 100.0
        min_eval_pawns = min(evals_cp) / 100.0

        def add(tag: str, reason: str) -> None:
            if tag.casefold() not in enabled_set:
                return
            if tag not in detected:
                detected.append(tag)
                reasons[tag] = reason

        # Missed win: someone had a winning advantage at any point but did not win.
        if game_result not in ("1-0", "0-1"):
            # draw/unknown: any winning advantage qualifies
            if max_eval_pawns >= win_eval_pawns or min_eval_pawns <= -win_eval_pawns:
                add("Missed win", f"Winning advantage reached (≥{win_eval_pawns:+.1f} pawns) but game not decisive")
        else:
            if max_eval_pawns >= win_eval_pawns and game_result != "1-0":
                add("Missed win", f"White reached ≥{win_eval_pawns:+.1f} but did not win")
            if min_eval_pawns <= -win_eval_pawns and game_result != "0-1":
                add("Missed win", f"Black reached ≤{-win_eval_pawns:+.1f} but did not win")

        # Opening disaster: evaluation already significant for one side at opening boundary.
        opening_end_move = int(getattr(summary, "opening_end", 0) or 0)
        if opening_end_move > 0:
            boundary_ply = opening_end_move * 2
            boundary_eval_cp = eval_at_or_after(boundary_ply)
            if boundary_eval_cp is not None:
                boundary_eval_pawns = boundary_eval_cp / 100.0
                if abs(boundary_eval_pawns) >= opening_disaster_pawns:
                    add("Opening disaster", f"Eval at opening end (move {opening_end_move}) is {boundary_eval_pawns:+.1f}")

        # Blunder-decided: first blunder flips to decisive advantage and never recovers meaningfully.
        first_blunder_ply: Optional[int] = None
        first_blunder_side: Optional[str] = None
        for m in moves:
            if getattr(m, "assess_white", "") == "Blunder":
                first_blunder_ply = int(m.move_number) * 2 - 1
                first_blunder_side = "white"
                break
            if getattr(m, "assess_black", "") == "Blunder":
                first_blunder_ply = int(m.move_number) * 2
                first_blunder_side = "black"
                break
        if first_blunder_ply is not None:
            after_cp = eval_by_ply.get(first_blunder_ply)
            before_cp = eval_by_ply.get(first_blunder_ply - 1, 0.0)
            if after_cp is not None:
                after_pawns = after_cp / 100.0
                before_pawns = before_cp / 100.0
                # Determine if blunder created decisive advantage for the *other* side.
                decisive_for_other = False
                if first_blunder_side == "white" and after_pawns <= -decisive_pawns:
                    decisive_for_other = True
                if first_blunder_side == "black" and after_pawns >= decisive_pawns:
                    decisive_for_other = True
                # If the other side was already decisively winning before the blunder,
                # don't treat the game as "blunder-decided" (the blunder only deepened an already lost position).
                already_decisive_before = False
                if first_blunder_side == "white" and before_pawns <= -decisive_pawns:
                    already_decisive_before = True
                if first_blunder_side == "black" and before_pawns >= decisive_pawns:
                    already_decisive_before = True

                if decisive_for_other and not already_decisive_before:
                    # Never recovered: evaluation never crosses back within a smaller band.
                    subsequent = [eval_by_ply[p] / 100.0 for p in plies_sorted if p >= first_blunder_ply]
                    if first_blunder_side == "white":
                        recovered = any(v > -never_recovered_pawns for v in subsequent)
                    else:
                        recovered = any(v < never_recovered_pawns for v in subsequent)
                    if not recovered:
                        add(
                            "Blunder-decided",
                            f"First blunder at ply {first_blunder_ply} caused decisive eval and was never recovered",
                        )

        # Clean win: winner kept a stable large advantage with limited swings.
        winner: Optional[str] = None
        if game_result == "1-0":
            winner = "white"
        elif game_result == "0-1":
            winner = "black"
        if winner:
            # Find first ply where winner advantage becomes "large".
            start_idx: Optional[int] = None
            for i, p in enumerate(plies_sorted):
                v = eval_by_ply[p] / 100.0
                if winner == "white" and v >= clean_win_large_adv_pawns:
                    start_idx = i
                    break
                if winner == "black" and v <= -clean_win_large_adv_pawns:
                    start_idx = i
                    break
            if start_idx is not None:
                segment = [eval_by_ply[p] / 100.0 for p in plies_sorted[start_idx:]]
                if len(segment) >= clean_win_min_plies:
                    # No significant dips below large advantage minus dip allowance.
                    if winner == "white":
                        min_seg = min(segment)
                        ok_floor = min_seg >= (clean_win_large_adv_pawns - clean_win_allowed_dip_pawns)
                    else:
                        max_seg = max(segment)
                        ok_floor = max_seg <= (-clean_win_large_adv_pawns + clean_win_allowed_dip_pawns)
                    # No big swings between consecutive points.
                    swings = [abs(segment[i] - segment[i - 1]) for i in range(1, len(segment))]
                    ok_swings = (max(swings) if swings else 0.0) <= clean_win_max_swing_pawns
                    if ok_floor and ok_swings:
                        add("Clean win", "Winner maintained large advantage with limited evaluation swings")

        # Endgame grind: long endgame with stable narrow eval before resolution.
        middlegame_end_move = int(getattr(summary, "middlegame_end", 0) or 0)
        if middlegame_end_move and middlegame_end_move <= total_moves:
            endgame_moves = total_moves - middlegame_end_move + 1
            if endgame_moves >= grind_min_endgame_moves:
                start_ply = (middlegame_end_move * 2) - 1
                endgame_vals = [(p, eval_by_ply[p] / 100.0) for p in plies_sorted if p >= start_ply]
                # Longest stable window where |eval| <= stable_eval.
                best_len = 0
                cur_len = 0
                for _, v in endgame_vals:
                    if abs(v) <= grind_stable_eval_pawns:
                        cur_len += 1
                        best_len = max(best_len, cur_len)
                    else:
                        cur_len = 0
                final_eval = (endgame_vals[-1][1] if endgame_vals else 0.0)
                if best_len >= grind_min_stable_plies and abs(final_eval) >= grind_resolution_eval_pawns:
                    add("Endgame grind", "Long endgame with extended stable eval band before resolution")

        # Chaotic game: both sides had big advantages and many swings.
        if max_eval_pawns >= chaotic_large_adv_pawns and min_eval_pawns <= -chaotic_large_adv_pawns:
            # Count swings across +/-chaotic_swing threshold by tracking state buckets.
            state = 0  # -1 black large, +1 white large, 0 neutral
            swings_count = 0
            for p in plies_sorted:
                v = eval_by_ply[p] / 100.0
                new_state = 0
                if v >= chaotic_swing_pawns:
                    new_state = 1
                elif v <= -chaotic_swing_pawns:
                    new_state = -1
                if state != 0 and new_state != 0 and new_state != state:
                    swings_count += 1
                if new_state != 0:
                    state = new_state
            if swings_count >= chaotic_min_swings:
                add("Chaotic game", f"{swings_count} large swings across threshold")

        return AutoTaggingResult(detected_tags=sorted(detected), reasons=reasons)

    def merge_with_existing_tags(self, existing_raw: str, detected: Iterable[str]) -> List[str]:
        """Replace any existing auto-tags with detected ones, keep all other tags."""
        existing = parse_game_tags(existing_raw or "")
        keep = [t for t in existing if t.casefold() not in {a.casefold() for a in AUTO_TAGS}]
        out: List[str] = keep[:]
        for t in detected:
            if t.casefold() not in {x.casefold() for x in out}:
                out.append(t)
        return out

    def apply_to_game_data(self, game: Any, tags: Sequence[str]) -> bool:
        """Apply CARAGameTags to a GameData-like object (updates game.pgn + tag fields)."""
        try:
            raw = format_game_tags(tags)
            pgn_io = io.StringIO(getattr(game, "pgn", "") or "")
            chess_game = chess.pgn.read_game(pgn_io)
            if not chess_game:
                return False
            if raw:
                chess_game.headers[PGN_TAG_NAME_GAME_TAGS] = raw
            else:
                if PGN_TAG_NAME_GAME_TAGS in chess_game.headers:
                    del chess_game.headers[PGN_TAG_NAME_GAME_TAGS]
            game.pgn = PgnService.export_game_to_pgn(chess_game)
            # Update cached fields on GameData (metadata_controller does this for active game)
            setattr(game, "game_tags_raw", raw)
            from app.utils.game_tags_utils import tags_display_text

            setattr(game, "game_tags", tags_display_text(parse_game_tags(raw)))
            return True
        except Exception as e:
            LoggingService.get_instance().warning(f"Auto-tagging: failed to apply tags: {e}", exc_info=e)
            return False

