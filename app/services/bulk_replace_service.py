"""Bulk replacement service for database operations."""

import os
import re
import chess
import chess.pgn
from io import StringIO
from pathlib import Path
from typing import Dict, Any, Optional, List, Callable, Tuple
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, as_completed

from app.models.database_model import DatabaseModel, GameData
from app.services.uci_communication_service import UCICommunicationService
from app.services.opening_service import OpeningService
from app.services.pgn_service import PgnService


@dataclass
class BulkReplaceResult:
    """Result of a bulk replace operation."""
    success: bool
    games_processed: int
    games_updated: int
    games_failed: int
    games_skipped: int
    error_message: Optional[str] = None


def _process_game_for_replace_tag(
    game_pgn: str,
    tag_name: str,
    find_text: str,
    replace_text: str,
    case_sensitive: bool,
    use_regex: bool,
    overwrite_all: bool
) -> Tuple[Optional[str], Optional[str], bool]:
    """Process a single game for tag replacement (for parallel execution).
    
    Args:
        game_pgn: PGN string of the game.
        tag_name: PGN tag name to replace.
        find_text: Text to find.
        replace_text: Text to replace with.
        case_sensitive: If True, match case exactly.
        use_regex: If True, treat find_text as regex pattern.
        overwrite_all: If True, replace any value with replace_text.
        
    Returns:
        Tuple of (new_pgn, new_field_value, updated) or (None, None, False) if failed/skipped.
    """
    try:
        # Parse PGN
        pgn_io = StringIO(game_pgn)
        chess_game = chess.pgn.read_game(pgn_io)
        
        if not chess_game:
            return (None, None, False)
        
        # Get current tag value
        current_value = chess_game.headers.get(tag_name, "")
        
        # Prepare replacement function and match check
        if overwrite_all:
            new_value = replace_text
            should_update = True
        elif use_regex:
            try:
                pattern = re.compile(find_text, 0 if case_sensitive else re.IGNORECASE)
                if pattern.search(current_value):
                    new_value = pattern.sub(replace_text, current_value)
                    should_update = True
                else:
                    should_update = False
                    new_value = current_value
            except re.error:
                return (None, None, False)
        else:
            if case_sensitive:
                if find_text in current_value:
                    new_value = current_value.replace(find_text, replace_text)
                    should_update = True
                else:
                    should_update = False
                    new_value = current_value
            else:
                pattern = re.compile(re.escape(find_text), re.IGNORECASE)
                if pattern.search(current_value):
                    new_value = pattern.sub(replace_text, current_value)
                    should_update = True
                else:
                    should_update = False
                    new_value = current_value
        
        if should_update:
            # For overwrite_all, always update (even if value is same, to ensure tag exists)
            # For normal replacement, only update if value changed
            if overwrite_all or new_value != current_value:
                # Update tag
                chess_game.headers[tag_name] = new_value
                
                # Regenerate PGN
                new_pgn = PgnService.export_game_to_pgn(chess_game)
                
                # Get field value if tag maps to a field
                tag_to_field_mapping = {
                    "White": "white",
                    "Black": "black",
                    "Result": "result",
                    "Date": "date",
                    "ECO": "eco",
                    "Event": "event",
                    "Site": "site",
                    "WhiteElo": "white_elo",
                    "BlackElo": "black_elo",
                }
                
                field_value = new_value if tag_name in tag_to_field_mapping else None
                
                return (new_pgn, field_value, True)
        
        return (None, None, False)
        
    except Exception:
        return (None, None, False)


def _process_game_for_copy_tag(
    game_pgn: str,
    target_tag: str,
    source_tag: str
) -> Tuple[Optional[str], Optional[str], bool]:
    """Process a single game for tag copying (for parallel execution).
    
    Args:
        game_pgn: PGN string of the game.
        target_tag: PGN tag name to update.
        source_tag: PGN tag name to copy from.
        
    Returns:
        Tuple of (new_pgn, new_field_value, updated) or (None, None, False) if failed/skipped.
    """
    try:
        # Parse PGN
        pgn_io = StringIO(game_pgn)
        chess_game = chess.pgn.read_game(pgn_io)
        
        if not chess_game:
            return (None, None, False)
        
        # Get source tag value
        source_value = chess_game.headers.get(source_tag, "")
        
        # Get current target tag value
        current_value = chess_game.headers.get(target_tag, "")
        
        # Only update if source has a value and it's different from current
        if source_value and source_value != current_value:
            # Update target tag
            chess_game.headers[target_tag] = source_value
            
            # Regenerate PGN
            new_pgn = PgnService.export_game_to_pgn(chess_game)
            
            # Get field value if tag maps to a field
            tag_to_field_mapping = {
                "White": "white",
                "Black": "black",
                "Result": "result",
                "Date": "date",
                "ECO": "eco",
            }
            
            field_value = source_value if target_tag in tag_to_field_mapping else None
            
            return (new_pgn, field_value, True)
        
        return (None, None, False)
        
    except Exception:
        return (None, None, False)


class BulkReplaceService:
    """Service for bulk replacement operations on databases."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the bulk replace service.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config
    
    def replace_metadata_tag(
        self,
        database: DatabaseModel,
        tag_name: str,
        find_text: str,
        replace_text: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
        overwrite_all: bool = False,
        game_indices: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancellation_check: Optional[Callable[[], bool]] = None
    ) -> BulkReplaceResult:
        """Replace text in metadata tags.
        
        Args:
            database: DatabaseModel instance to process.
            tag_name: PGN tag name to replace (e.g., "White", "Black", "Result").
            find_text: Text to find.
            replace_text: Text to replace with.
            case_sensitive: If True, match case exactly.
            use_regex: If True, treat find_text as regex pattern.
            overwrite_all: If True, replace any value with replace_text, ignoring find_text.
            game_indices: Optional list of game indices to process (None = all games).
            progress_callback: Optional callback function(game_index, total, message).
            cancellation_check: Optional function that returns True if operation should be cancelled.
            
        Returns:
            BulkReplaceResult with operation statistics.
        """
        games = database.get_all_games()
        
        # Filter games if indices provided
        if game_indices is not None:
            games_to_process = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            games_to_process = games
        
        total_games = len(games_to_process)
        
        # If no games to process, return early
        if total_games == 0:
            if progress_callback:
                progress_callback(0, 0, "No games to process")
            return BulkReplaceResult(
                success=True,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0
            )
        
        # Validate regex pattern early if using regex
        if use_regex:
            try:
                re.compile(find_text, 0 if case_sensitive else re.IGNORECASE)
            except re.error as e:
                return BulkReplaceResult(
                    success=False,
                    games_processed=0,
                    games_updated=0,
                    games_failed=0,
                    games_skipped=0,
                    error_message=f"Invalid regex pattern: {str(e)}"
                )
        
        # Determine worker count (reserve 1-2 cores for UI)
        max_workers = max(1, os.cpu_count() - 2)
        
        # Collect all updated games for batch update
        updated_games = []
        games_updated = 0
        games_failed = 0
        
        executor = None
        try:
            executor = ProcessPoolExecutor(max_workers=max_workers)
            
            # Submit all games for processing
            future_to_game = {
                executor.submit(
                    _process_game_for_replace_tag,
                    game.pgn,
                    tag_name,
                    find_text,
                    replace_text,
                    case_sensitive,
                    use_regex,
                    overwrite_all
                ): game
                for game in games_to_process
            }
            
            # Process results as they complete
            completed = 0
            tag_to_field_mapping = {
                "White": "white",
                "Black": "black",
                "Result": "result",
                "Date": "date",
                "ECO": "eco",
                "Event": "event",
                "Site": "site",
                "WhiteElo": "white_elo",
                "BlackElo": "black_elo",
            }
            
            for future in as_completed(future_to_game):
                if cancellation_check and cancellation_check():
                    # Cancel remaining futures
                    for f in future_to_game:
                        if f != future:
                            f.cancel()
                    break
                
                game = future_to_game[future]
                completed += 1
                
                if progress_callback:
                    progress_callback(completed, total_games, f"Processing game {completed}/{total_games}")
                
                try:
                    new_pgn, new_field_value, updated = future.result()
                    
                    if updated and new_pgn:
                        # Update game data
                        game.pgn = new_pgn
                        
                        # Update corresponding GameData fields if tag maps to a field
                        if tag_name in tag_to_field_mapping and new_field_value is not None:
                            field_name = tag_to_field_mapping[tag_name]
                            setattr(game, field_name, new_field_value)
                        
                        # Collect game for batch update
                        updated_games.append(game)
                        games_updated += 1
                    elif new_pgn is None and updated is False:
                        # Processing failed
                        games_failed += 1
                except Exception:
                    games_failed += 1
        
        finally:
            if executor:
                executor.shutdown(wait=True)
        
        # Batch update all modified games with a single dataChanged signal
        if updated_games:
            database.batch_update_games(updated_games)
        
        return BulkReplaceResult(
            success=True,
            games_processed=total_games,
            games_updated=games_updated,
            games_failed=games_failed,
            games_skipped=0
        )
    
    def copy_metadata_tag(
        self,
        database: DatabaseModel,
        target_tag: str,
        source_tag: str,
        game_indices: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancellation_check: Optional[Callable[[], bool]] = None
    ) -> BulkReplaceResult:
        """Copy value from one metadata tag to another.
        
        Args:
            database: DatabaseModel instance to process.
            target_tag: PGN tag name to update (e.g., "EventDate").
            source_tag: PGN tag name to copy from (e.g., "Date").
            game_indices: Optional list of game indices to process (None = all games).
            progress_callback: Optional callback function(game_index, total, message).
            cancellation_check: Optional function that returns True if operation should be cancelled.
            
        Returns:
            BulkReplaceResult with operation statistics.
        """
        games = database.get_all_games()
        
        # Filter games if indices provided
        if game_indices is not None:
            games_to_process = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            games_to_process = games
        
        total_games = len(games_to_process)
        
        # If no games to process, return early
        if total_games == 0:
            if progress_callback:
                progress_callback(0, 0, "No games to process")
            return BulkReplaceResult(
                success=True,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0
            )
        
        # Determine worker count (reserve 1-2 cores for UI)
        max_workers = max(1, os.cpu_count() - 2)
        
        # Collect all updated games for batch update
        updated_games = []
        games_updated = 0
        games_failed = 0
        
        executor = None
        try:
            executor = ProcessPoolExecutor(max_workers=max_workers)
            
            # Submit all games for processing
            future_to_game = {
                executor.submit(
                    _process_game_for_copy_tag,
                    game.pgn,
                    target_tag,
                    source_tag
                ): game
                for game in games_to_process
            }
            
            # Process results as they complete
            completed = 0
            tag_to_field_mapping = {
                "White": "white",
                "Black": "black",
                "Result": "result",
                "Date": "date",
                "ECO": "eco",
            }
            
            for future in as_completed(future_to_game):
                if cancellation_check and cancellation_check():
                    # Cancel remaining futures
                    for f in future_to_game:
                        if f != future:
                            f.cancel()
                    break
                
                game = future_to_game[future]
                completed += 1
                
                if progress_callback:
                    progress_callback(completed, total_games, f"Processing game {completed}/{total_games}")
                
                try:
                    new_pgn, new_field_value, updated = future.result()
                    
                    if updated and new_pgn:
                        # Update game data
                        game.pgn = new_pgn
                        
                        # Update corresponding GameData fields if tag maps to a field
                        if target_tag in tag_to_field_mapping and new_field_value is not None:
                            field_name = tag_to_field_mapping[target_tag]
                            setattr(game, field_name, new_field_value)
                        
                        # Collect game for batch update
                        updated_games.append(game)
                        games_updated += 1
                    elif new_pgn is None and updated is False:
                        # Processing failed
                        games_failed += 1
                except Exception:
                    games_failed += 1
        
        finally:
            if executor:
                executor.shutdown(wait=True)
        
        # Batch update all modified games with a single dataChanged signal
        if updated_games:
            database.batch_update_games(updated_games)
        
        return BulkReplaceResult(
            success=True,
            games_processed=total_games,
            games_updated=games_updated,
            games_failed=games_failed,
            games_skipped=0
        )
    
    def update_result_tags(
        self,
        database: DatabaseModel,
        engine_path: Path,
        max_depth: int,
        time_limit_ms: int,
        max_threads: Optional[int] = None,
        engine_options: Optional[Dict[str, Any]] = None,
        game_indices: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_flag: Optional[Callable[[], bool]] = None
    ) -> BulkReplaceResult:
        """Update Result tags based on final position evaluation.
        
        Args:
            database: DatabaseModel instance to process.
            engine_path: Path to UCI engine executable.
            max_depth: Maximum depth for analysis.
            time_limit_ms: Maximum time per position in milliseconds.
            max_threads: Maximum number of threads (None = engine default).
            engine_options: Dictionary of engine-specific options.
            game_indices: Optional list of game indices to process (None = all games).
            progress_callback: Optional callback function(game_index, total, message).
            cancel_flag: Optional function that returns True if operation should be cancelled.
            
        Returns:
            BulkReplaceResult with operation statistics.
        """
        games = database.get_all_games()
        
        # Filter games if indices provided
        if game_indices is not None:
            games_to_process = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            games_to_process = games
        
        total_games = len(games_to_process)
        
        # If no games to process, return early
        if total_games == 0:
            if progress_callback:
                progress_callback(0, 0, "No games to process")
            return BulkReplaceResult(
                success=True,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0
            )
        
        games_updated = 0
        games_failed = 0
        games_skipped = 0
        
        # Initialize engine once and reuse across games
        uci = None
        try:
            # Create UCI communication service
            uci = UCICommunicationService(
                engine_path,
                identifier="BulkReplace"
            )
            
            # Spawn engine process
            if not uci.spawn_process():
                return BulkReplaceResult(
                    success=False,
                    games_processed=0,
                    games_updated=0,
                    games_failed=0,
                    games_skipped=0,
                    error_message="Failed to spawn engine process"
                )
            
            # Initialize UCI
            success, _ = uci.initialize_uci(timeout=5.0)
            if not success:
                uci.cleanup()
                return BulkReplaceResult(
                    success=False,
                    games_processed=0,
                    games_updated=0,
                    games_failed=0,
                    games_skipped=0,
                    error_message="Engine did not respond with uciok"
                )
            
            # Set options
            if max_threads is not None:
                uci.set_option("Threads", max_threads, wait_for_ready=False)
            
            if engine_options:
                for option_name, option_value in engine_options.items():
                    if option_name != "Threads":
                        uci.set_option(option_name, option_value, wait_for_ready=False)
            
            # Confirm engine is ready
            if not uci.confirm_ready():
                uci.cleanup()
                return BulkReplaceResult(
                    success=False,
                    games_processed=0,
                    games_updated=0,
                    games_failed=0,
                    games_skipped=0,
                    error_message="Engine did not respond with readyok"
                )
            
            # Collect all updated games for batch update
            updated_games = []
            
            # Process each game
            for idx, game in enumerate(games_to_process):
                if cancel_flag and cancel_flag():
                    break
                
                if progress_callback:
                    progress_callback(idx, total_games, f"Analyzing game {idx + 1}/{total_games}")
                
                try:
                    # Parse PGN to get final position
                    pgn_io = StringIO(game.pgn)
                    chess_game = chess.pgn.read_game(pgn_io)
                    
                    if not chess_game:
                        games_failed += 1
                        continue
                    
                    # Navigate to end of game
                    node = chess_game
                    while node.variations:
                        node = node.variation(0)
                    
                    # Get final position
                    board = node.board()
                    fen = board.fen()
                    
                    # Get existing result (if any)
                    existing_result = chess_game.headers.get("Result", "").strip()
                    
                    # Only update if result is indecisive (empty, "*", or "?")
                    # Preserve decisive results (1-0, 0-1, 1/2-1/2)
                    decisive_results = ["1-0", "0-1", "1/2-1/2"]
                    if existing_result in decisive_results:
                        games_skipped += 1
                        continue
                    
                    # Check if game already ended (checkmate, stalemate, etc.)
                    if board.is_checkmate():
                        # Game ended in checkmate - determine winner
                        result = "0-1" if board.turn == chess.WHITE else "1-0"
                    elif board.is_stalemate() or board.is_insufficient_material() or board.is_seventyfive_moves() or board.is_fivefold_repetition():
                        # Game ended in draw
                        result = "1/2-1/2"
                    else:
                        # Analyze position to determine result
                        try:
                            # Use synchronous analysis with UCI engine (reusing instance)
                            eval_result = self._analyze_position_sync_with_uci(
                                uci,
                                fen,
                                max_depth,
                                time_limit_ms
                            )
                            
                            if not eval_result:
                                games_skipped += 1
                                continue
                            
                            eval_centipawns, is_mate, mate_moves = eval_result
                            
                            # UCI engine returns evaluation from side-to-move perspective
                            # Flip to white's perspective if black is to move
                            is_white_to_move = board.turn == chess.WHITE
                            if not is_white_to_move:
                                # Flip evaluation: if engine returns +100 for black, it means black is winning
                                # but we want to show from white's perspective, so flip to -100
                                eval_centipawns = -eval_centipawns
                                if is_mate:
                                    mate_moves = -mate_moves
                            
                            # Determine result from evaluation
                            result = self._determine_result_from_evaluation(
                                eval_centipawns,
                                is_mate,
                                mate_moves,
                                is_white_to_move
                            )
                            
                        except Exception as e:
                            games_skipped += 1
                            continue
                    
                    # Update Result tag
                    chess_game.headers["Result"] = result
                    
                    # Regenerate PGN
                    new_pgn = PgnService.export_game_to_pgn(chess_game)
                    
                    # Update game data
                    game.pgn = new_pgn
                    game.result = result
                    
                    # Collect game for batch update
                    updated_games.append(game)
                    games_updated += 1
                    
                except Exception as e:
                    games_failed += 1
                    continue
            
            # Batch update all modified games with a single dataChanged signal
            if updated_games:
                database.batch_update_games(updated_games)
            
        finally:
            # Cleanup engine
            if uci:
                uci.cleanup()
        
        return BulkReplaceResult(
            success=True,
            games_processed=total_games,
            games_updated=games_updated,
            games_failed=games_failed,
            games_skipped=games_skipped
        )
    
    def _determine_result_from_evaluation(
        self,
        eval_centipawns: float,
        is_mate: bool,
        mate_moves: int,
        is_white_to_move: bool
    ) -> str:
        """Determine game result from final position evaluation.
        
        Args:
            eval_centipawns: Evaluation in centipawns (positive = white advantage).
            is_mate: True if mate was found.
            mate_moves: Number of moves to mate (positive = white winning, negative = black winning).
            is_white_to_move: True if white is to move.
            
        Returns:
            Game result string ("1-0", "0-1", "1/2-1/2", or "*").
        """
        if is_mate:
            if mate_moves == 0:
                # Checkmate achieved - determine winner from side to move
                return "0-1" if is_white_to_move else "1-0"
            elif mate_moves > 0:
                # Side to move can force mate - determine winner based on whose turn it is
                return "1-0" if is_white_to_move else "0-1"
            else:
                # Opponent can force mate - determine winner based on whose turn it is
                return "0-1" if is_white_to_move else "1-0"
        
        # Use thresholds for non-mate positions
        if eval_centipawns > 500:
            # White clearly winning (more than 5 pawns advantage)
            return "1-0"
        elif eval_centipawns < -500:
            # Black clearly winning (more than 5 pawns advantage)
            return "0-1"
        elif -100 <= eval_centipawns <= 100:
            # Draw (within 1 pawn)
            return "1/2-1/2"
        else:
            # Ambiguous - use threshold of ±300 centipawns
            if eval_centipawns > 300:
                return "1-0"
            elif eval_centipawns < -300:
                return "0-1"
            else:
                # Too close to call - mark as unknown
                return "*"
    
    def _analyze_position_sync_with_uci(
        self,
        uci: UCICommunicationService,
        fen: str,
        max_depth: int,
        time_limit_ms: int
    ) -> Optional[tuple[float, bool, int]]:
        """Analyze a position synchronously using an existing UCI instance.
        
        Args:
            uci: UCICommunicationService instance (already initialized).
            fen: FEN string of position to analyze.
            max_depth: Maximum depth for analysis.
            time_limit_ms: Maximum time per position in milliseconds.
            
        Returns:
            Tuple of (eval_centipawns, is_mate, mate_moves) or None if analysis failed.
        """
        try:
            # Set position
            if not uci.set_position(fen):
                return None
            
            # Start search
            if not uci.start_search(depth=max_depth, movetime=time_limit_ms):
                return None
            
            # Read analysis output
            import time
            start_time = time.time()
            timeout = (time_limit_ms / 1000.0) + 5.0  # Add 5 seconds buffer
            
            best_score = None
            best_is_mate = False
            best_mate_moves = 0
            
            while (time.time() - start_time) < timeout:
                line = uci.read_line(timeout=0.1)
                if not line:
                    continue
                
                # Parse info line
                if line.startswith("info"):
                    parts = line.split()
                    if "score" in parts:
                        score_idx = parts.index("score")
                        if score_idx + 1 < len(parts):
                            score_type = parts[score_idx + 1]
                            if score_type == "cp" and score_idx + 2 < len(parts):
                                try:
                                    best_score = float(parts[score_idx + 2])
                                    best_is_mate = False
                                except ValueError:
                                    pass
                            elif score_type == "mate" and score_idx + 2 < len(parts):
                                try:
                                    best_mate_moves = int(parts[score_idx + 2])
                                    best_is_mate = True
                                    # Convert mate moves to centipawns approximation
                                    # Positive for white winning, negative for black winning
                                    best_score = 10000.0 if best_mate_moves > 0 else -10000.0
                                except ValueError:
                                    pass
                
                # Check for bestmove (analysis complete)
                elif line.startswith("bestmove"):
                    break
            
            if best_score is not None:
                return (best_score, best_is_mate, best_mate_moves)
            else:
                return None
                
        except Exception:
            return None
    
    def update_eco_tags(
        self,
        database: DatabaseModel,
        opening_service: OpeningService,
        game_indices: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancel_flag: Optional[Callable[[], bool]] = None
    ) -> BulkReplaceResult:
        """Update ECO tags based on opening analysis of game moves.
        
        Args:
            database: DatabaseModel instance to process.
            opening_service: OpeningService instance for ECO lookup.
            game_indices: Optional list of game indices to process (None = all games).
            progress_callback: Optional callback function(game_index, total, message).
            cancel_flag: Optional function that returns True if operation should be cancelled.
            
        Returns:
            BulkReplaceResult with operation statistics.
        """
        games = database.get_all_games()
        
        # Filter games if indices provided
        if game_indices is not None:
            games_to_process = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            games_to_process = games
        
        total_games = len(games_to_process)
        
        # If no games to process, return early
        if total_games == 0:
            if progress_callback:
                progress_callback(0, 0, "No games to process")
            return BulkReplaceResult(
                success=True,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0
            )
        
        games_updated = 0
        games_failed = 0
        games_skipped = 0
        
        # Collect all updated games for batch update
        updated_games = []
        
        # Process each game
        for idx, game in enumerate(games_to_process):
            if cancel_flag and cancel_flag():
                break
            
            if progress_callback:
                progress_callback(idx, total_games, f"Processing game {idx + 1}/{total_games}")
            
            try:
                # Get final ECO code for this game
                eco_code = opening_service.get_final_eco_for_game(game.pgn)
                
                # If no ECO found, skip (don't overwrite existing tag)
                if eco_code is None:
                    games_skipped += 1
                    continue
                
                # Parse PGN to check current ECO tag
                pgn_io = StringIO(game.pgn)
                chess_game = chess.pgn.read_game(pgn_io)
                
                if not chess_game:
                    games_failed += 1
                    continue
                
                # Get current ECO tag from headers
                current_eco = chess_game.headers.get("ECO", "").strip()
                
                # If current ECO equals identified ECO, skip (no update needed)
                if current_eco == eco_code:
                    games_skipped += 1
                    continue
                
                # Update ECO tag (only if different)
                chess_game.headers["ECO"] = eco_code
                
                # Regenerate PGN
                new_pgn = PgnService.export_game_to_pgn(chess_game)
                
                # Update game data
                game.pgn = new_pgn
                game.eco = eco_code
                
                # Collect game for batch update
                updated_games.append(game)
                games_updated += 1
                
            except Exception:
                games_failed += 1
                continue
        
        # Batch update all modified games with a single dataChanged signal
        if updated_games:
            database.batch_update_games(updated_games)
        
        return BulkReplaceResult(
            success=True,
            games_processed=total_games,
            games_updated=games_updated,
            games_failed=games_failed,
            games_skipped=games_skipped
        )

