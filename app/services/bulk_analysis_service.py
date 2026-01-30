"""Service for bulk game analysis without requiring games to be active."""

import io
import os
import chess
import chess.pgn
import time
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from app.models.database_model import GameData
from app.models.engine_model import EngineModel
from app.models.move_classification_model import MoveClassificationModel
from app.models.moveslist_model import MoveData
from app.services.game_analysis_engine_service import GameAnalysisEngineService
from app.services.move_analysis_service import MoveAnalysisService
from app.services.book_move_service import BookMoveService
from app.services.opening_service import OpeningService
from app.services.analysis_data_storage_service import AnalysisDataStorageService
from app.services.engine_parameters_service import EngineParametersService
from app.services.logging_service import LoggingService
from app.utils.material_tracker import (
    get_captured_piece_letter,
    calculate_material_count,
    count_pieces
)


class BulkAnalysisService(QObject):
    """Service for analyzing multiple games in bulk without making them active."""
    
    def __init__(self, config: Dict[str, Any], engine_model: EngineModel,
                 opening_service: OpeningService, book_move_service: BookMoveService,
                 classification_model: Optional[MoveClassificationModel] = None,
                 threads_override: Optional[int] = None,
                 movetime_override: Optional[int] = None) -> None:
        """Initialize bulk analysis service.
        
        Args:
            config: Configuration dictionary.
            engine_model: EngineModel instance.
            opening_service: OpeningService instance.
            book_move_service: BookMoveService instance.
            classification_model: Optional MoveClassificationModel instance for classification settings.
            threads_override: Optional override for engine threads (used for parallel analysis).
        """
        super().__init__()
        self.config = config
        self.engine_model = engine_model
        self.opening_service = opening_service
        self.book_move_service = book_move_service
        self.classification_model = classification_model
        self._cancelled = False
        self._engine_service: Optional[GameAnalysisEngineService] = None
        self._threads_override = threads_override
        self._movetime_override = movetime_override
        
        # Note: Opening service should be loaded before creating BulkAnalysisService instances
        # to avoid blocking during analysis. We don't load it here to avoid blocking worker threads.
        
        # Get game analysis configuration
        game_analysis_config = config.get("game_analysis", {})
        self.max_depth = game_analysis_config.get("max_depth", 18)
        self.time_limit_ms = game_analysis_config.get("time_limit_per_move_ms", 3000)
        self.max_threads = game_analysis_config.get("max_threads", 6)
        self.progress_update_interval_ms = game_analysis_config.get("progress_update_interval_ms", 500)
        
        # Load classification thresholds
        self._load_classification_thresholds()
    
    @staticmethod
    def calculate_parallel_resources(max_parallel_games: int = 4, 
                                     max_total_threads: Optional[int] = None) -> Tuple[int, List[int]]:
        """Calculate optimal number of parallel games and thread distribution per engine.
        
        This method intelligently splits available CPU resources across multiple
        engine instances for parallel game analysis. It distributes threads dynamically
        to maximize utilization, using only the max_total_threads setting from the
        bulk analysis dialog, ignoring the engine's normal thread configuration.
        
        Args:
            max_parallel_games: Maximum number of parallel games to allow (default: 4).
            max_total_threads: Optional maximum total threads to use across all parallel games (None = unlimited).
            
        Returns:
            Tuple of (parallel_games, threads_per_engine_list).
            - parallel_games: Number of games to analyze in parallel
            - threads_per_engine_list: List of thread counts, one per parallel game (may vary to use all threads)
        """
        # Get available CPU cores
        # If max_total_threads is provided, use it instead of available cores
        if max_total_threads is not None:
            available_cores = max_total_threads
        else:
            available_cores = os.cpu_count() or 4  # Fallback to 4 if detection fails
        
        # Determine number of parallel games (limited by max_parallel_games)
        max_parallel = min(max_parallel_games, available_cores)
        
        # Ensure at least 1 parallel game
        if max_parallel < 1:
            max_parallel = 1
        
        # Distribute threads dynamically to use all available cores
        # Some games may get more threads than others if cores don't divide evenly
        threads_per_engine_list = []
        base_threads = available_cores // max_parallel
        remainder = available_cores % max_parallel
        
        # Distribute base threads to all games
        for i in range(max_parallel):
            threads = base_threads
            # Distribute remainder threads to first 'remainder' games
            if i < remainder:
                threads += 1
            threads_per_engine_list.append(threads)
        
        return (max_parallel, threads_per_engine_list)
    
    def _load_classification_thresholds(self) -> None:
        """Load classification thresholds from model or config."""
        if self.classification_model:
            self.good_move_max_cpl = self.classification_model.good_move_max_cpl
            self.inaccuracy_max_cpl = self.classification_model.inaccuracy_max_cpl
            self.mistake_max_cpl = self.classification_model.mistake_max_cpl
            self.min_eval_swing = self.classification_model.min_eval_swing
            self.min_material_sacrifice = self.classification_model.min_material_sacrifice
            self.max_eval_before = self.classification_model.max_eval_before
            self.exclude_already_winning = self.classification_model.exclude_already_winning
            self.material_sacrifice_lookahead_plies = self.classification_model.material_sacrifice_lookahead_plies
        else:
            # Fallback to config defaults
            classification_config = self.config.get("game_analysis", {}).get("move_classification", {})
            self.good_move_max_cpl = classification_config.get("good_move_max_cpl", 50)
            self.inaccuracy_max_cpl = classification_config.get("inaccuracy_max_cpl", 100)
            self.mistake_max_cpl = classification_config.get("mistake_max_cpl", 200)
            self.min_eval_swing = classification_config.get("min_eval_swing", 200)
            self.min_material_sacrifice = classification_config.get("min_material_sacrifice", 100)
            self.max_eval_before = classification_config.get("max_eval_before", 500)
            self.exclude_already_winning = classification_config.get("exclude_already_winning", True)
            self.material_sacrifice_lookahead_plies = classification_config.get("material_sacrifice_lookahead_plies", 3)
    
    def cancel(self) -> None:
        """Cancel the current analysis."""
        self._cancelled = True
        if self._engine_service:
            self._engine_service.stop_analysis()
            # Note: cleanup() is called in finally block, not here
    
    def cleanup(self) -> None:
        """Cleanup engine service after analysis completes normally."""
        if self._engine_service:
            self._engine_service.cleanup()
            self._engine_service = None
    
    def analyze_game(self, game: GameData, progress_callback=None) -> bool:
        """Analyze a single game without making it active.
        
        Args:
            game: GameData instance to analyze.
            progress_callback: Optional callback function(game_move_index, total_moves, current_move_number, is_white_move, status_message, engine_info).
                              game_move_index: 0-based index of current move being analyzed
                              total_moves: Total number of moves in game
                              current_move_number: Current move number (1, 2, 3, etc.)
                              is_white_move: True if analyzing white move, False for black
                              status_message: Status message string
                              engine_info: Optional dict with engine info (depth, centipawns, engine_name, threads, elapsed_ms)
            
        Returns:
            True if analysis succeeded, False otherwise.
        """
        if self._cancelled:
            return False
        
        try:
            # Extract moves from game
            moves_data = self._extract_moves_for_analysis(game)
            if not moves_data:
                if progress_callback:
                    progress_callback(0, 0, 0, True, "No moves found in game")
                return False
            
            total_moves = len(moves_data)
            
            # Initialize engine service if needed
            if not self._engine_service or not self._engine_service.analysis_thread or not self._engine_service.analysis_thread.isRunning():
                if not self._initialize_engine_service():
                    if progress_callback:
                        progress_callback(0, total_moves, 0, True, "Failed to initialize engine")
                    return False
            
            # Analyze each move
            analyzed_moves: List[MoveData] = []
            previous_eval = 0.0
            previous_is_mate = False
            previous_mate_moves = 0
            
            # Store best move info from previous position analysis (position after move N = position before move N+1)
            cached_best_move_info = None  # (best_move_eval, best_move_is_mate, best_mate_moves, best_move_san, pv2_move_san, pv3_move_san, pv2_score, pv3_score, pv2_score_black, pv3_score_black, depth)
            
            # Track opening information (for repeat indicator)
            last_known_eco = None
            last_known_opening_name = None
            previous_move_eco = None
            previous_move_opening_name = None
            opening_repeat_indicator = self.config.get('resources', {}).get('opening_repeat_indicator', '*')
            
            for move_index, move_info in enumerate(moves_data):
                if self._cancelled:
                    return False
                
                move_number = move_info["move_number"]
                is_white_move = move_info["is_white_move"]
                
                # Update progress (will be updated with engine info when analysis starts)
                if progress_callback:
                    status = f"Analyzing move {move_index + 1}/{total_moves} (Move {move_number}{'W' if is_white_move else 'B'})"
                    progress_callback(move_index, total_moves, move_number, is_white_move, status, None)
                
                # Get best move info: reuse from previous analysis if available, otherwise analyze position before move
                if cached_best_move_info is not None:
                    # Reuse best move info from previous position analysis (position after move N-1 = position before move N)
                    best_move_eval, best_move_is_mate, best_mate_moves, best_move_san, pv2_move_san, pv3_move_san, \
                        pv2_score, pv3_score, pv2_score_black, pv3_score_black, depth, seldepth = cached_best_move_info
                else:
                    # First move: analyze position before move to get best move
                    best_move_result = self._analyze_position(
                        move_info["fen_before"],
                        move_number,
                        is_white_move,
                        progress_callback,
                        move_index,
                        total_moves
                    )
                    
                    if not best_move_result:
                        continue
                    
                    best_move_eval, best_move_is_mate, best_mate_moves, best_move_san, pv2_move_san, pv3_move_san, \
                        pv2_score, pv3_score, pv2_score_black, pv3_score_black, depth, seldepth = best_move_result
                
                # Analyze position after move (to get evaluation AND best move for next iteration)
                eval_result = self._analyze_position(
                    move_info["fen_after"],
                    move_number,
                    is_white_move,
                    progress_callback,
                    move_index,
                    total_moves
                )
                
                if not eval_result:
                    continue
                
                # Extract both evaluation (for current move) and best move info (for next move)
                eval_after, is_mate, mate_moves, best_move_san_next, pv2_move_san_next, pv3_move_san_next, \
                    pv2_score_next, pv3_score_next, pv2_score_black_next, pv3_score_black_next, depth_after, seldepth_after = eval_result
                
                # Cache best move info for next iteration (position after move N = position before move N+1)
                cached_best_move_info = (
                    eval_after, is_mate, mate_moves, best_move_san_next, pv2_move_san_next, pv3_move_san_next,
                    pv2_score_next, pv3_score_next, pv2_score_black_next, pv3_score_black_next, depth_after, seldepth_after
                )
                
                # Calculate CPL
                played_move_san = move_info["move_san"]
                moves_match = MoveAnalysisService.normalize_move(played_move_san) == MoveAnalysisService.normalize_move(best_move_san) if best_move_san else False
                
                cpl = MoveAnalysisService.calculate_cpl(
                    eval_before=previous_eval,
                    eval_after=eval_after,
                    eval_after_best_move=best_move_eval,
                    is_white_move=is_white_move,
                    is_mate=is_mate,
                    is_mate_before=previous_is_mate,
                    is_mate_after_best=best_move_is_mate,
                    mate_moves=mate_moves,
                    mate_moves_before=previous_mate_moves,
                    mate_moves_after_best=best_mate_moves,
                    moves_match=moves_match
                )
                
                # Check if book move
                is_book_move = self.book_move_service.is_book_move(move_info["board_before"], move_info["move"])
                
                # Calculate material sacrifice for brilliant detection
                material_sacrifice = MoveAnalysisService.calculate_material_sacrifice(
                    move_info, moves_data, move_index, lookahead_plies=1
                )
                
                # Assess move quality
                classification_thresholds = {
                    "good_move_max_cpl": self.good_move_max_cpl,
                    "inaccuracy_max_cpl": self.inaccuracy_max_cpl,
                    "mistake_max_cpl": self.mistake_max_cpl,
                    "min_eval_swing": self.min_eval_swing,
                    "min_material_sacrifice": self.min_material_sacrifice,
                    "max_eval_before": self.max_eval_before,
                    "exclude_already_winning": self.exclude_already_winning,
                    "best_move_is_mate": best_move_is_mate
                }
                
                if is_book_move:
                    assess = "Book Move"
                else:
                    assess = MoveAnalysisService.assess_move_quality(
                        cpl, previous_eval, eval_after, move_info, best_move_san, moves_match,
                        classification_thresholds, material_sacrifice
                    )
                
                # Calculate PV CPL
                cpl_2_str = ""
                cpl_3_str = ""
                if not is_book_move:
                    if is_white_move:
                        if pv2_score != 0.0:
                            cpl_2 = MoveAnalysisService.calculate_pv_cpl(pv2_score, eval_after)
                            cpl_2_str = MoveAnalysisService.format_cpl(cpl_2)
                        if pv3_score != 0.0:
                            cpl_3 = MoveAnalysisService.calculate_pv_cpl(pv3_score, eval_after)
                            cpl_3_str = MoveAnalysisService.format_cpl(cpl_3)
                    else:
                        if pv2_score_black != 0.0:
                            cpl_2 = MoveAnalysisService.calculate_pv_cpl(pv2_score_black, eval_after)
                            cpl_2_str = MoveAnalysisService.format_cpl(cpl_2)
                        if pv3_score_black != 0.0:
                            cpl_3 = MoveAnalysisService.calculate_pv_cpl(pv3_score_black, eval_after)
                            cpl_3_str = MoveAnalysisService.format_cpl(cpl_3)
                
                # Format evaluation and CPL
                eval_str = MoveAnalysisService.format_evaluation(eval_after, is_mate, mate_moves, is_white_move)
                cpl_str = MoveAnalysisService.format_cpl(cpl) if not is_book_move else ""
                
                # Check if move is in top 3
                played_normalized = MoveAnalysisService.normalize_move(played_move_san)
                is_top3 = MoveAnalysisService.is_move_in_top3(
                    played_normalized, best_move_san, pv2_move_san, pv3_move_san
                ) if not is_book_move else False
                
                # Calculate material and captures
                board_before = move_info["board_before"]
                board_after = move_info["board_after"]
                move = move_info["move"]
                
                white_material_after = calculate_material_count(board_after, is_white=True)
                black_material_after = calculate_material_count(board_after, is_white=False)
                white_pieces = count_pieces(board_after, is_white=True)
                black_pieces = count_pieces(board_after, is_white=False)
                
                # Look up opening information for this position (after the move)
                fen_after = move_info["fen_after"]
                eco, opening_name = None, None
                if self.opening_service:
                    try:
                        # Only lookup if service is loaded (should be pre-loaded before analysis starts)
                        if self.opening_service.is_loaded():
                            eco, opening_name = self.opening_service.get_opening_info(fen_after)
                        # If not loaded, skip lookup to avoid blocking (opening info will be None)
                    except Exception as e:
                        # If opening lookup fails, continue without opening info
                        logging_service = LoggingService.get_instance()
                        logging_service.warning(f"Opening lookup failed: {e}", exc_info=e)
                        eco, opening_name = None, None
                
                # If we found an opening, update our tracking variables
                if eco:
                    last_known_eco = eco
                if opening_name:
                    last_known_opening_name = opening_name
                
                # Use the found opening, or fall back to last known opening if not found
                display_eco = eco if eco else (last_known_eco if last_known_eco else "")
                display_opening_name = opening_name if opening_name else (last_known_opening_name if last_known_opening_name else "")
                
                # Check if this opening is the same as the previous move's opening
                # Compare actual opening values (not display values) to determine if they match
                actual_eco = eco if eco else (last_known_eco if last_known_eco else "")
                actual_opening_name = opening_name if opening_name else (last_known_opening_name if last_known_opening_name else "")
                
                if actual_eco and actual_opening_name and previous_move_eco and previous_move_opening_name:
                    if actual_eco == previous_move_eco and actual_opening_name == previous_move_opening_name:
                        # Same as previous - use repeat indicator
                        display_eco = opening_repeat_indicator
                        display_opening_name = opening_repeat_indicator
                
                # Update previous move tracking for next iteration (use actual values, not display values)
                previous_move_eco = actual_eco if actual_eco else None
                previous_move_opening_name = actual_opening_name if actual_opening_name else None
                
                # Get or create MoveData for this move number
                row_index = move_number - 1
                while len(analyzed_moves) <= row_index:
                    analyzed_moves.append(MoveData(len(analyzed_moves) + 1))
                
                move_data = analyzed_moves[row_index]
                
                # Set opening information
                move_data.eco = display_eco
                move_data.opening_name = display_opening_name
                
                # Update move data
                if is_white_move:
                    move_data.white_move = move_info["move_san"]
                    move_data.eval_white = eval_str
                    move_data.cpl_white = cpl_str
                    move_data.cpl_white_2 = cpl_2_str
                    move_data.cpl_white_3 = cpl_3_str
                    move_data.assess_white = assess
                    if not is_book_move:
                        move_data.best_white = best_move_san
                        move_data.best_white_2 = pv2_move_san
                        move_data.best_white_3 = pv3_move_san
                        move_data.white_depth = depth
                        move_data.white_seldepth = seldepth
                        move_data.white_is_top3 = is_top3
                    else:
                        move_data.best_white = ""
                        move_data.best_white_2 = ""
                        move_data.best_white_3 = ""
                        move_data.white_depth = 0
                        move_data.white_seldepth = 0
                        move_data.white_is_top3 = False
                    move_data.white_capture = get_captured_piece_letter(board_before, move)
                    move_data.white_material = white_material_after
                    move_data.black_material = black_material_after
                    move_data.white_queens = white_pieces[chess.QUEEN]
                    move_data.white_rooks = white_pieces[chess.ROOK]
                    move_data.white_bishops = white_pieces[chess.BISHOP]
                    move_data.white_knights = white_pieces[chess.KNIGHT]
                    move_data.white_pawns = white_pieces[chess.PAWN]
                    move_data.black_queens = black_pieces[chess.QUEEN]
                    move_data.black_rooks = black_pieces[chess.ROOK]
                    move_data.black_bishops = black_pieces[chess.BISHOP]
                    move_data.black_knights = black_pieces[chess.KNIGHT]
                    move_data.black_pawns = black_pieces[chess.PAWN]
                    move_data.fen_white = board_after.fen()
                else:
                    move_data.black_move = move_info["move_san"]
                    move_data.eval_black = eval_str
                    move_data.cpl_black = cpl_str
                    move_data.cpl_black_2 = cpl_2_str
                    move_data.cpl_black_3 = cpl_3_str
                    move_data.assess_black = assess
                    if not is_book_move:
                        move_data.best_black = best_move_san
                        move_data.best_black_2 = pv2_move_san
                        move_data.best_black_3 = pv3_move_san
                        move_data.black_depth = depth
                        move_data.black_seldepth = seldepth
                        move_data.black_is_top3 = is_top3
                    else:
                        move_data.best_black = ""
                        move_data.best_black_2 = ""
                        move_data.best_black_3 = ""
                        move_data.black_depth = 0
                        move_data.black_seldepth = 0
                        move_data.black_is_top3 = False
                    move_data.black_capture = get_captured_piece_letter(board_before, move)
                    move_data.white_material = white_material_after
                    move_data.black_material = black_material_after
                    move_data.white_queens = white_pieces[chess.QUEEN]
                    move_data.white_rooks = white_pieces[chess.ROOK]
                    move_data.white_bishops = white_pieces[chess.BISHOP]
                    move_data.white_knights = white_pieces[chess.KNIGHT]
                    move_data.white_pawns = white_pieces[chess.PAWN]
                    move_data.black_queens = black_pieces[chess.QUEEN]
                    move_data.black_rooks = black_pieces[chess.ROOK]
                    move_data.black_bishops = black_pieces[chess.BISHOP]
                    move_data.black_knights = black_pieces[chess.KNIGHT]
                    move_data.black_pawns = black_pieces[chess.PAWN]
                    move_data.fen_black = board_after.fen()
                
                # Update previous evaluation for next move
                previous_eval = eval_after
                previous_is_mate = is_mate
                previous_mate_moves = mate_moves
            
            # Store analysis results
            if analyzed_moves:
                # Update game ECO from the last move with opening information (excluding repeat indicator)
                # This matches the logic in GameController.get_game_info()
                for move in reversed(analyzed_moves):
                    if move.opening_name and move.opening_name != opening_repeat_indicator:
                        if move.eco and move.eco != opening_repeat_indicator:
                            game.eco = move.eco
                        break
                
                success = AnalysisDataStorageService.store_analysis_data(
                    game,
                    analyzed_moves,
                    self.config
                )
                
                if success:
                    game.analyzed = True
                    if progress_callback:
                        progress_callback(total_moves, total_moves, 0, True, f"Analysis complete: {total_moves} moves analyzed", None)
                    return True
                else:
                    if progress_callback:
                        progress_callback(total_moves, total_moves, 0, True, "Failed to store analysis results", None)
                    return False
            else:
                if progress_callback:
                    progress_callback(0, total_moves, 0, True, "No moves analyzed", None)
                return False
        
        except Exception as e:
            if progress_callback:
                progress_callback(0, 0, 0, True, f"Error during analysis: {str(e)}", None)
            return False
    
    def _extract_moves_for_analysis(self, game_data: GameData) -> List[Dict[str, Any]]:
        """Extract moves from game data for analysis.
        
        Args:
            game_data: GameData instance.
            
        Returns:
            List of move dictionaries with position info.
        """
        moves_list = []
        
        try:
            pgn_text = game_data.pgn
            pgn_io = io.StringIO(pgn_text)
            game = chess.pgn.read_game(pgn_io)
            
            if game is None:
                return []
            
            board = game.board()
            move_number = 1
            
            # Iterate through mainline moves
            node = game
            while node.variations:
                # Get the next move in the mainline
                node = node.variation(0)
                move = node.move
                
                if move is None:
                    break
                
                is_white_move = board.turn == chess.WHITE
                
                # Get position before move
                fen_before = board.fen()
                board_before = board.copy()
                
                # Make move
                board.push(move)
                fen_after = board.fen()
                board_after = board.copy()
                
                # Get move SAN
                board.pop()
                move_san = board.san(move)
                board.push(move)
                
                # Store move info
                move_info = {
                    "move_number": move_number,
                    "is_white_move": is_white_move,
                    "move_san": move_san,
                    "move": move,
                    "fen_before": fen_before,
                    "fen_after": fen_after,
                    "board_before": board_before,
                    "board_after": board_after,
                }
                
                moves_list.append(move_info)
                
                # Update move number after black moves
                if not is_white_move:
                    move_number += 1
            
            return moves_list
        
        except Exception as e:
            return []
    
    def _initialize_engine_service(self) -> bool:
        """Initialize the engine service for analysis.
        
        Returns:
            True if initialized successfully, False otherwise.
        """
        # Get engine assignment
        engine_assignment = self.engine_model.get_assignment(EngineModel.TASK_GAME_ANALYSIS)
        if engine_assignment is None:
            return False
        
        engine = self.engine_model.get_engine(engine_assignment)
        if engine is None or not engine.is_valid:
            return False
        
        # Get task-specific parameters
        engine_path = Path(engine.path) if not isinstance(engine.path, Path) else engine.path
        
        task_params = EngineParametersService.get_task_parameters_for_engine(
            engine_path,
            "game_analysis",
            self.config
        )
        
        max_depth = task_params.get("depth", self.max_depth)
        
        # Use movetime override if provided (for bulk analysis), otherwise use normal setting
        if self._movetime_override is not None:
            time_limit_ms = self._movetime_override
        else:
            time_limit_ms = task_params.get("movetime", self.time_limit_ms)
        
        # Use threads override if provided (for parallel analysis), otherwise use normal setting
        if self._threads_override is not None:
            max_threads = self._threads_override
        else:
            max_threads = task_params.get("threads", self.max_threads)
        
        engine_options = {}
        for key, value in task_params.items():
            if key not in ["threads", "depth", "movetime"]:
                engine_options[key] = value
        
        # Initialize engine service
        self._engine_service = GameAnalysisEngineService(
            engine_path,
            max_depth,
            time_limit_ms,
            max_threads,
            engine.name,
            engine_options
        )
        
        if not self._engine_service.start_engine():
            return False
        
        return True
    
    def _analyze_position(self, fen: str, move_number: int, is_white_move: bool, 
                          progress_callback=None, game_move_index: int = 0, total_moves: int = 0) -> Optional[tuple]:
        """Analyze a position and return evaluation.
        
        Args:
            fen: FEN string of position to analyze.
            move_number: Move number for progress reporting.
            is_white_move: True if analyzing white move, False for black.
            progress_callback: Optional callback for progress updates.
            game_move_index: Current move index in game (for progress callback).
            total_moves: Total moves in game (for progress callback).
            
        Returns:
            Tuple of (eval, is_mate, mate_moves, best_move_san, pv2_move_san, pv3_move_san,
                     pv2_score, pv3_score, pv2_score_black, pv3_score_black, depth) or None if failed.
        """
        if not self._engine_service:
            return None
        
        # Queue analysis request
        analysis_thread = self._engine_service.analyze_position(fen, move_number, self.progress_update_interval_ms)
        if not analysis_thread:
            return None
        
        # Wait for analysis to complete using signals
        result_container = {"result": None, "completed": False}
        last_progress_info = {"depth": 0, "seldepth": 0, "centipawns": 0.0, "engine_name": "", "threads": 0, "elapsed_ms": 0.0}
        last_progress_time = {"value": None}  # Use dict to allow modification in nested function
        first_progress_received = {"value": False}  # Track if we've received at least one progress update
        
        def on_progress_update(depth, seldepth, centipawns, elapsed_ms, engine_name, threads, move_num, nps):
            """Handle progress update from engine."""
            last_progress_info["depth"] = depth
            last_progress_info["seldepth"] = seldepth
            last_progress_info["centipawns"] = float(centipawns)
            last_progress_info["engine_name"] = engine_name
            last_progress_info["threads"] = threads
            last_progress_info["elapsed_ms"] = elapsed_ms
            last_progress_info["nps"] = nps if nps > 0 else 0
            last_progress_time["value"] = time.time()  # Update progress timestamp
            first_progress_received["value"] = True  # Mark that we've received progress
            
            # Forward to progress callback if provided
            if progress_callback:
                engine_info = {
                    "depth": depth,
                    "seldepth": seldepth,
                    "centipawns": float(centipawns),
                    "engine_name": engine_name,
                    "threads": threads,
                    "elapsed_ms": elapsed_ms,
                    "nps": nps if nps > 0 else 0
                }
                status = f"Analyzing move {game_move_index + 1}/{total_moves} (Move {move_number}{'W' if is_white_move else 'B'})"
                progress_callback(game_move_index, total_moves, move_number, is_white_move, status, engine_info)
        
        def on_complete(centipawns, is_mate, mate_moves, best_move_san, pv1_string, pv2_move_san, pv3_move_san,
                       pv2_score, pv3_score, pv2_score_black, pv3_score_black, depth, seldepth, nps, engine_name):
            result_container["result"] = (
                centipawns, is_mate, mate_moves, best_move_san, pv2_move_san, pv3_move_san,
                pv2_score, pv3_score, pv2_score_black, pv3_score_black, depth, seldepth
            )
            result_container["completed"] = True
        
        def on_error(error_message: str):
            result_container["completed"] = True
        
        # Connect signals
        analysis_thread.progress_update.connect(on_progress_update)
        analysis_thread.analysis_complete.connect(on_complete)
        analysis_thread.error_occurred.connect(on_error)
        
        # Wait for completion with progress-based timeout
        start_time = time.time()
        
        # Get actual movetime from engine service (which has the override applied)
        actual_time_limit_ms = self._engine_service.time_limit_ms if self._engine_service else self.time_limit_ms
        
        # Calculate timeouts: progress timeout (no progress for 2x movetime) and absolute max (safety net)
        movetime_seconds = actual_time_limit_ms / 1000.0
        # Progress timeout: no progress for 2x movetime, but minimum 10 seconds to allow engine startup
        # This prevents false timeouts when engines take time to send first progress update
        progress_timeout_seconds = max(movetime_seconds * 2.0, 10.0)
        timeout_buffer_seconds = max(movetime_seconds * 0.2, 5.0)
        absolute_max_timeout_seconds = movetime_seconds + timeout_buffer_seconds
        
        # Log timeout configuration for debugging
        # if hasattr(self._engine_service, 'analysis_thread') and self._engine_service.analysis_thread:
        #     if hasattr(self._engine_service.analysis_thread, 'uci') and self._engine_service.analysis_thread.uci:
        #         self._engine_service.analysis_thread.uci._debug_lifecycle(
        #             "TIMEOUT_CONFIG",
        #             f" (movetime: {actual_time_limit_ms}ms, progress_timeout: {progress_timeout_seconds:.1f}s, absolute_max: {absolute_max_timeout_seconds:.1f}s)"
        #         )
        
        timeout_occurred = False
        
        # Process events until complete
        while not result_container["completed"] and not self._cancelled:
            elapsed = time.time() - start_time
            
            # Only check progress timeout if we've received at least one progress update
            # Engines may take time to send the first progress update, which is normal
            # Also wait a minimum time after first progress before checking (engines may have gaps between updates)
            if first_progress_received["value"] and last_progress_time["value"]:
                time_since_progress = time.time() - last_progress_time["value"]
                time_since_first_progress = elapsed  # Time since we started waiting
                
                # Only check progress timeout if:
                # 1. We've waited at least 5 seconds since start (allow engine to settle)
                # 2. No progress for extended period (2x movetime, min 10s)
                if time_since_first_progress >= 5.0 and time_since_progress > progress_timeout_seconds:
                    timeout_occurred = True
                    # Log timeout to debug lifecycle if available
                    if hasattr(self._engine_service, 'analysis_thread') and self._engine_service.analysis_thread:
                        if hasattr(self._engine_service.analysis_thread, 'uci') and self._engine_service.analysis_thread.uci:
                            self._engine_service.analysis_thread.uci._debug_lifecycle(
                                "TIMEOUT",
                                f" (progress timeout: no progress for {time_since_progress:.1f}s, elapsed: {elapsed:.1f}s)"
                            )
                    self._engine_service.stop_current_analysis()
                    break
            
            # Check for absolute maximum timeout (safety net)
            if elapsed > absolute_max_timeout_seconds:
                timeout_occurred = True
                # Log timeout to debug lifecycle if available
                if hasattr(self._engine_service, 'analysis_thread') and self._engine_service.analysis_thread:
                    if hasattr(self._engine_service.analysis_thread, 'uci') and self._engine_service.analysis_thread.uci:
                        self._engine_service.analysis_thread.uci._debug_lifecycle(
                            "TIMEOUT",
                            f" (absolute max timeout: {elapsed:.1f}s > {absolute_max_timeout_seconds:.1f}s)"
                        )
                self._engine_service.stop_current_analysis()
                break
            
            QApplication.processEvents()
            time.sleep(0.01)
        
        # Grace period: give signal a chance to be delivered (Qt event processing delay)
        if timeout_occurred and not result_container["completed"]:
            grace_period = 0.5  # 500ms grace period
            grace_start = time.time()
            while (time.time() - grace_start) < grace_period:
                QApplication.processEvents()
                if result_container["completed"]:
                    # Signal arrived during grace period - not a real timeout
                    timeout_occurred = False
                    break
                time.sleep(0.01)
        
        # Disconnect signals
        try:
            analysis_thread.progress_update.disconnect(on_progress_update)
            analysis_thread.analysis_complete.disconnect(on_complete)
            analysis_thread.error_occurred.disconnect(on_error)
        except TypeError:
            pass
        
        if self._cancelled:
            return None
        
        # If timeout occurred, try to use partial results
        if timeout_occurred:
            # Check if we have partial results from progress updates
            if last_progress_info["depth"] > 0:
                # Use partial results instead of failing
                # Note: We don't have best move info from progress updates, so use empty strings
                partial_result = (
                    last_progress_info["centipawns"],
                    False,  # is_mate (unknown from partial data)
                    0,      # mate_moves
                    "",     # best_move_san (unknown)
                    "",     # pv2_move_san
                    "",     # pv3_move_san
                    0.0,    # pv2_score
                    0.0,    # pv3_score
                    0.0,    # pv2_score_black
                    0.0,    # pv3_score_black
                    last_progress_info["depth"],
                    last_progress_info["seldepth"]
                )
                return partial_result
            else:
                # No progress data available - return None
                return None
        
        return result_container["result"]
