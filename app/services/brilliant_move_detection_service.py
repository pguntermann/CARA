"""Service for brilliant move detection. Shared logic used by game analysis and bulk analysis."""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.models.moveslist_model import MoveData
from app.services.brilliant_move_detection_analysis_service import BrilliantMoveDetectionAnalysisService
from app.services.move_analysis_service import MoveAnalysisService
from app.services.logging_service import LoggingService
from app.services.engine_parameters_service import EngineParametersService


def run_brilliant_move_detection(
    move_infos: List[Dict[str, Any]],
    get_move_data: Callable[[int], Optional[MoveData]],
    on_brilliant: Callable[[int, bool, str], None],
    shallow_depth_min: int,
    shallow_depth_max: int,
    min_depths_show_error: int,
    good_move_max_cpl: int,
    inaccuracy_max_cpl: int,
    mistake_max_cpl: int,
    engine_path: Path,
    time_limit_ms: int,
    max_threads: Optional[int],
    engine_name: str,
    engine_options: Dict[str, Any],
    config: Dict[str, Any],
    require_blunder_only: bool = False,
    candidate_selection: str = "best_move_only",
    on_progress: Optional[Callable[[str], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
) -> int:
    """Run brilliancy detection on a list of move infos and update assessments via callbacks.

    Candidates are moves classified as "Best Move" (or "Best Move" and "Good Move" if candidate_selection
    is "best_or_good_move") at full depth. For each candidate, positions are analyzed at shallow depths;
    if at least min_depths_show_error depths classify the move as Mistake/Blunder (or Blunder only if
    require_blunder_only=True), the move is marked brilliant.

    Args:
        move_infos: List of move info dicts (fen_before, move_san, board_before, eval_before,
            eval_after, is_mate_before, mate_moves_before, move_number, is_white_move).
        get_move_data: Callable(row_index) -> MoveData or None.
        on_brilliant: Callable(row_index, is_white_move, assessment_text) when a move is brilliant.
        shallow_depth_min: Minimum shallow depth to check.
        shallow_depth_max: Maximum shallow depth to check.
        min_depths_show_error: Minimum number of depths that must show Mistake/Blunder.
        good_move_max_cpl: CPL threshold for good move (classification).
        inaccuracy_max_cpl: CPL threshold for inaccuracy (classification).
        mistake_max_cpl: CPL threshold for mistake (classification).
        engine_path: Path to UCI engine.
        time_limit_ms: Time limit per position for shallow analysis.
        max_threads: Engine threads (optional).
        engine_name: Engine name for logging.
        engine_options: Engine options dict.
        config: App config dict.
        on_progress: Optional callback(message) for progress updates.
        is_cancelled: Optional callable() -> bool to check for cancellation.

    Returns:
        Number of moves marked brilliant.
    """
    if not move_infos:
        return 0
    logging_service = LoggingService.get_instance()
    _is_cancelled = is_cancelled if is_cancelled else lambda: False
    _on_progress = on_progress if on_progress else lambda _: None

    # Ensure min_depths_show_error is an int and cannot require more depths than we actually check
    total_depths_in_range = max(0, shallow_depth_max - shallow_depth_min + 1)
    min_depths_required = max(1, min(int(min_depths_show_error), total_depths_in_range)) if total_depths_in_range else 1

    shallow_time_limit_ms = max(500, time_limit_ms // 3)
    service: Optional[BrilliantMoveDetectionAnalysisService] = BrilliantMoveDetectionAnalysisService(
        engine_path,
        shallow_time_limit_ms,
        max_threads,
        engine_name,
        engine_options,
        config,
    )
    if not service.start_engine():
        logging_service.error("Brilliant move detection: Failed to start engine")
        return 0
    
    # Check if engine supports "Clear Hash" option
    engine_supports_clear_hash = False
    try:
        parameters_service = EngineParametersService.get_instance()
        parameters_service.load()
        engine_options_list = parameters_service.get_engine_options(str(engine_path))
        # Check if any option has name "Clear Hash" (case-insensitive check)
        engine_supports_clear_hash = any(
            opt.get("name", "").lower() == "clear hash" 
            for opt in engine_options_list
        )
        if engine_supports_clear_hash:
            logging_service.debug("Brilliant move detection: Engine supports 'Clear Hash' option")
        else:
            logging_service.debug("Brilliant move detection: Engine does not support 'Clear Hash' option, will use ucinewgame")
    except Exception as e:
        logging_service.debug(f"Brilliant move detection: Could not check for Clear Hash option: {e}, will use ucinewgame")
        engine_supports_clear_hash = False

    brilliant_count = 0
    candidates_checked = 0
    try:
        candidate_moves: List[Tuple[int, Dict[str, Any], MoveData, bool, int]] = []
        for i, move_info in enumerate(move_infos):
            if _is_cancelled():
                return brilliant_count
            move_number = move_info.get("move_number", 0)
            is_white_move = move_info.get("is_white_move", True)
            row_index = move_number - 1
            move_data = get_move_data(row_index)
            if move_data is None:
                continue
            current_assessment = move_data.assess_white if is_white_move else move_data.assess_black
            if candidate_selection == "best_or_good_move":
                if current_assessment in ["Best Move", "Good Move"]:
                    candidate_moves.append((i, move_info, move_data, is_white_move, row_index))
            else:  # best_move_only
                if current_assessment == "Best Move":
                    candidate_moves.append((i, move_info, move_data, is_white_move, row_index))

        total_candidates = len(candidate_moves)
        error_severity_text = "Blunder" if require_blunder_only else "Mistake or Blunder"
        candidate_text = "Best Move or Good Move" if candidate_selection == "best_or_good_move" else "Best Move only"
        brilliant_criteria_config = config.get("game_analysis", {}).get("brilliant_criteria", {})
        disable_skip_playedmove_match_bestmove = brilliant_criteria_config.get(
            "disable_skip_playedmove_match_bestmove", False
        )
        append_depthlevels = brilliant_criteria_config.get(
            "append_depthlevels_to_classification_text", False
        )
        logging_service.info(
            f"Brilliant move detection: Checking {total_candidates} candidate moves ({candidate_text}), "
            f"min_depths_required={min_depths_required} (depths {shallow_depth_min}-{shallow_depth_max}), "
            f"error_severity={error_severity_text}"
        )

        for candidate_idx, (move_idx, move_info, move_data, is_white_move, row_index) in enumerate(
            candidate_moves
        ):
            if _is_cancelled():
                return brilliant_count
            candidates_checked += 1
            fen_before = move_info.get("fen_before", "")
            played_move_san = move_info.get("move_san", "")
            if not fen_before or not played_move_san:
                continue

            move_number = move_info.get("move_number", 0)
            color = "white" if is_white_move else "black"
            logging_service.debug(
                f"Brilliant candidate: move {move_number} ({color}) {played_move_san}"
            )

            depths_show_error = 0
            brilliant_depths: List[int] = []
            previous_depth = None
            for depth in range(shallow_depth_min, shallow_depth_max + 1):
                if _is_cancelled():
                    return brilliant_count
                
                # Clear hash before each new depth search to prevent contamination from previous searches
                # This ensures each shallow depth analysis starts with a clean hash table
                if previous_depth is None or depth != previous_depth:
                    service.clear_hash(engine_supports_clear_hash)
                    logging_service.debug(f"  Cleared hash before depth {depth} analysis")
                
                previous_depth = depth
                analysis_result = _analyze_at_shallow_depth(
                    service, fen_before, move_info.get("move_number", 0), depth, shallow_time_limit_ms
                )
                if analysis_result is None:
                    logging_service.debug(
                        f"  depth {depth}: skip (analysis of position before move failed)"
                    )
                    continue
                shallow_eval, shallow_is_mate, shallow_mate_moves, shallow_best_move_san = analysis_result
                played_move_normalized = MoveAnalysisService.normalize_move(played_move_san)
                shallow_best_move_normalized = (
                    MoveAnalysisService.normalize_move(shallow_best_move_san)
                    if shallow_best_move_san
                    else ""
                )
                moves_match_at_shallow = bool(
                    shallow_best_move_normalized
                    and played_move_normalized == shallow_best_move_normalized
                )
                if moves_match_at_shallow and not disable_skip_playedmove_match_bestmove:
                    logging_service.debug(
                        f"  depth {depth}: skip (played move matches shallow best move {shallow_best_move_san})"
                    )
                    continue
                board_before = move_info.get("board_before")
                if board_before is None:
                    logging_service.debug(f"  depth {depth}: skip (board_before missing)")
                    continue
                if not shallow_best_move_san:
                    logging_service.debug(f"  depth {depth}: skip (no best move from shallow analysis)")
                    continue
                try:
                    # Analyze position after playing the best move (at shallow depth)
                    board_best = board_before.copy()
                    try:
                        best_move_uci = board_best.parse_san(shallow_best_move_san)
                        board_best.push(best_move_uci)
                        fen_after_best = board_best.fen()
                    except Exception:
                        logging_service.debug(
                            f"  depth {depth}: skip (failed to parse/play best move {shallow_best_move_san})"
                        )
                        continue
                    
                    best_result = _analyze_at_shallow_depth(
                        service, fen_after_best, move_info.get("move_number", 0), depth, shallow_time_limit_ms
                    )
                    if best_result is None:
                        logging_service.debug(
                            f"  depth {depth}: skip (analysis after best move {shallow_best_move_san} failed)"
                        )
                        continue
                    (
                        eval_after_best_shallow,
                        is_mate_after_best_shallow,
                        mate_moves_after_best_shallow,
                        _,
                    ) = best_result
                    
                    # Analyze position after playing the actual move (at shallow depth)
                    board_after = board_before.copy()
                    move_uci = board_after.parse_san(played_move_san)
                    board_after.push(move_uci)
                    fen_after = board_after.fen()
                    after_result = _analyze_at_shallow_depth(
                        service, fen_after, move_info.get("move_number", 0), depth, shallow_time_limit_ms
                    )
                    if after_result is None:
                        logging_service.debug(
                            f"  depth {depth}: skip (analysis after played move {played_move_san} failed)"
                        )
                        continue
                    (
                        eval_after_shallow,
                        is_mate_after_shallow,
                        mate_moves_after_shallow,
                        _,
                    ) = after_result
                    eval_before_normal = move_info.get("eval_before", 0.0)
                    is_mate_before_normal = move_info.get("is_mate_before", False)
                    mate_moves_before_normal = move_info.get("mate_moves_before", 0)
                    shallow_cpl = MoveAnalysisService.calculate_cpl(
                        eval_before=eval_before_normal,
                        eval_after=eval_after_shallow,
                        eval_after_best_move=eval_after_best_shallow,
                        is_white_move=is_white_move,
                        is_mate=is_mate_after_shallow,
                        is_mate_before=is_mate_before_normal,
                        is_mate_after_best=is_mate_after_best_shallow,
                        mate_moves=mate_moves_after_shallow,
                        mate_moves_before=mate_moves_before_normal,
                        mate_moves_after_best=mate_moves_after_best_shallow,
                        moves_match=moves_match_at_shallow,
                    )
                    classification_thresholds = {
                        "good_move_max_cpl": good_move_max_cpl,
                        "inaccuracy_max_cpl": inaccuracy_max_cpl,
                        "mistake_max_cpl": mistake_max_cpl,
                        "best_move_is_mate": False,
                    }
                    shallow_assessment = MoveAnalysisService.assess_move_quality(
                        shallow_cpl,
                        eval_before_normal,
                        eval_after_shallow,
                        move_info,
                        shallow_best_move_san,
                        moves_match_at_shallow,
                        classification_thresholds,
                        material_sacrifice=0,
                    )
                    if require_blunder_only:
                        counted = shallow_assessment == "Blunder"
                    else:
                        counted = shallow_assessment in ["Mistake", "Blunder"]
                    if counted:
                        depths_show_error += 1
                        brilliant_depths.append(depth)
                    logging_service.debug(
                        f"  depth {depth}: best={shallow_best_move_san} (eval={eval_after_best_shallow:.0f}), "
                        f"played={played_move_san} (eval={eval_after_shallow:.0f}), "
                        f"CPL={shallow_cpl:.0f} → {shallow_assessment} "
                        f"(counted={'yes' if counted else 'no'}, require_blunder_only={require_blunder_only})"
                    )
                except Exception as e:
                    logging_service.debug(
                        f"  depth {depth}: error analyzing {played_move_san} - {e}"
                    )
                    continue

            qualified = depths_show_error >= min_depths_required
            logging_service.debug(
                f"  => {depths_show_error}/{min_depths_required} depths show error "
                f"(depths: {sorted(brilliant_depths) if brilliant_depths else 'none'}), "
                f"qualified={'yes' if qualified else 'no'}"
            )

            if depths_show_error >= min_depths_required:
                current_assessment = move_data.assess_white if is_white_move else move_data.assess_black
                if not current_assessment.startswith("Brilliant"):
                    if append_depthlevels and brilliant_depths:
                        assessment_text = f"Brilliant ({','.join(map(str, sorted(brilliant_depths)))})"
                    else:
                        assessment_text = "Brilliant"
                    if is_white_move:
                        move_data.assess_white = assessment_text
                    else:
                        move_data.assess_black = assessment_text
                    on_brilliant(row_index, is_white_move, assessment_text)
                    brilliant_count += 1

            if (candidate_idx + 1) % 5 == 0 or candidate_idx == total_candidates - 1:
                _on_progress(
                    f"Detecting brilliant moves: {candidate_idx + 1}/{total_candidates} candidates checked ({brilliant_count} brilliant)"
                )
    finally:
        if service:
            service.cleanup()

    if brilliant_count > 0:
        logging_service.info(
            f"Brilliant move detection completed: {brilliant_count} brilliant move(s) detected from {candidates_checked} candidates"
        )
    else:
        logging_service.info(
            f"Brilliant move detection completed: No brilliant moves detected from {candidates_checked} candidates"
        )
    return brilliant_count


def _analyze_at_shallow_depth(
    service: BrilliantMoveDetectionAnalysisService,
    fen: str,
    move_number: int,
    depth: int,
    time_limit_ms: int,
) -> Optional[Tuple[float, bool, int, str]]:
    """Analyze a position at shallow depth synchronously."""
    from PyQt6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    result_container: Dict[str, Any] = {"result": None, "error": None}

    def on_analysis_complete(
        centipawns: float, is_mate: bool, mate_moves: int, best_move_san: str, analysis_depth: int
    ):
        if analysis_depth == depth:
            result_container["result"] = (centipawns, is_mate, mate_moves, best_move_san)
            loop.quit()

    def on_error(error_message: str):
        result_container["error"] = error_message
        loop.quit()

    analysis_thread = service.analyze_position(fen, move_number, depth)
    if not analysis_thread:
        return None
    analysis_thread.analysis_complete.connect(on_analysis_complete)
    analysis_thread.error_occurred.connect(on_error)
    timeout_timer = QTimer()
    timeout_timer.setSingleShot(True)
    timeout_timer.timeout.connect(loop.quit)
    timeout_timer.start(time_limit_ms * 2)
    loop.exec()
    try:
        analysis_thread.analysis_complete.disconnect(on_analysis_complete)
        analysis_thread.error_occurred.disconnect(on_error)
    except Exception:
        pass
    if result_container["error"]:
        LoggingService.get_instance().debug(
            f"Error analyzing at depth {depth}: {result_container['error']}"
        )
        return None
    return result_container["result"]
