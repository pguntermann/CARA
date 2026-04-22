"""Bulk tag service for adding and removing tags from database games."""

import os
import chess
import chess.pgn
from io import StringIO
from typing import Dict, Any, Optional, List, Callable, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed

from app.models.database_model import DatabaseModel
from app.services.bulk_operation_stats import BulkOperationStats, BulkProcessingOutcome
from app.services.pgn_service import PgnService
from app.services.logging_service import LoggingService
from app.utils.concurrency_utils import get_process_pool_max_workers


def _process_game_for_add_tag(
    game_pgn: str,
    tag_name: str,
    tag_value: Optional[str],
    source_tag: Optional[str]
) -> Tuple[Optional[str], Optional[str], BulkProcessingOutcome]:
    """Process a single game for tag addition (for parallel execution)."""
    try:
        pgn_io = StringIO(game_pgn)
        chess_game = chess.pgn.read_game(pgn_io)
        
        if not chess_game:
            return (None, None, BulkProcessingOutcome.FAILED)
        
        if tag_name in chess_game.headers:
            return (None, None, BulkProcessingOutcome.SKIPPED)
        
        if source_tag is not None:
            new_value = chess_game.headers.get(source_tag, "")
        elif tag_value is not None and tag_value.strip():
            new_value = tag_value
        else:
            new_value = ""
        
        chess_game.headers[tag_name] = new_value
        new_pgn = PgnService.export_game_to_pgn(chess_game)
        
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
            "TimeControl": "time_control",
        }
        
        field_value = new_value if tag_name in tag_to_field_mapping else None
        return (new_pgn, field_value, BulkProcessingOutcome.UPDATED)
        
    except Exception:
        return (None, None, BulkProcessingOutcome.FAILED)


def _process_game_for_remove_tags(
    game_pgn: str,
    tag_names: List[str],
) -> Tuple[Optional[str], Optional[Dict[str, str]], BulkProcessingOutcome]:
    """Process a single game for removing multiple tags (for parallel execution)."""
    try:
        pgn_io = StringIO(game_pgn)
        chess_game = chess.pgn.read_game(pgn_io)

        if not chess_game:
            return (None, None, BulkProcessingOutcome.FAILED)

        removed_any = False
        for tag_name in tag_names:
            if tag_name in chess_game.headers:
                del chess_game.headers[tag_name]
                removed_any = True

        if not removed_any:
            return (None, None, BulkProcessingOutcome.SKIPPED)

        new_pgn = PgnService.export_game_to_pgn(chess_game)

        # Provide updated field values for known GameData-mapped tags (set to empty when removed).
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
            "TimeControl": "time_control",
        }
        cleared_fields: Dict[str, str] = {}
        for tag_name in tag_names:
            field_name = tag_to_field_mapping.get(tag_name)
            if field_name:
                cleared_fields[field_name] = ""

        return (new_pgn, cleared_fields, BulkProcessingOutcome.UPDATED)

    except Exception:
        return (None, None, BulkProcessingOutcome.FAILED)


class BulkTagService:
    """Service for bulk tag operations on databases."""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
    
    def add_tag(
        self,
        database: DatabaseModel,
        tag_name: str,
        tag_value: Optional[str] = None,
        source_tag: Optional[str] = None,
        game_indices: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancellation_check: Optional[Callable[[], bool]] = None
    ) -> BulkOperationStats:
        games = database.get_all_games()
        
        if game_indices is not None:
            games_to_process = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            games_to_process = games
        
        total_games = len(games_to_process)
        
        if total_games == 0:
            if progress_callback:
                progress_callback(0, 0, "No games to process")
            return BulkOperationStats(
                success=True,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0
            )
        
        max_workers = get_process_pool_max_workers(os.cpu_count(), self.config)
        
        updated_games = []
        games_updated = 0
        games_failed = 0
        games_skipped = 0
        
        executor = None
        completed = 0
        try:
            executor = ProcessPoolExecutor(max_workers=max_workers)
            
            future_to_game = {
                executor.submit(
                    _process_game_for_add_tag,
                    game.pgn,
                    tag_name,
                    tag_value,
                    source_tag
                ): game
                for game in games_to_process
            }
            
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
                "TimeControl": "time_control",
            }
            
            for future in as_completed(future_to_game):
                if cancellation_check and cancellation_check():
                    for f in future_to_game:
                        if f != future:
                            f.cancel()
                    break
                
                game = future_to_game[future]
                completed += 1
                
                if progress_callback:
                    progress_callback(completed, total_games, f"Processing game {completed}/{total_games}")
                
                try:
                    new_pgn, new_field_value, outcome = future.result()
                    
                    if outcome == BulkProcessingOutcome.UPDATED:
                        if new_pgn:
                            game.pgn = new_pgn
                            if tag_name in tag_to_field_mapping and new_field_value is not None:
                                field_name = tag_to_field_mapping[tag_name]
                                setattr(game, field_name, new_field_value)
                            updated_games.append(game)
                            games_updated += 1
                        else:
                            games_failed += 1
                    elif outcome == BulkProcessingOutcome.SKIPPED:
                        games_skipped += 1
                    else:
                        games_failed += 1
                except Exception:
                    games_failed += 1
        
        finally:
            if executor:
                executor.shutdown(wait=True)
        
        if updated_games:
            database.batch_update_games(updated_games)
        
        database._add_tags_to_cache({tag_name})
        
        logging_service = LoggingService.get_instance()
        logging_service.info(
            f"Bulk tag operation completed: tag={tag_name}, games_processed={completed}, "
            f"games_updated={games_updated}, games_failed={games_failed}, games_skipped={games_skipped}"
        )
        
        return BulkOperationStats(
            success=True,
            games_processed=completed,
            games_updated=games_updated,
            games_failed=games_failed,
            games_skipped=games_skipped
        )
    
    def remove_tags(
        self,
        database: DatabaseModel,
        tag_names: List[str],
        game_indices: Optional[List[int]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        cancellation_check: Optional[Callable[[], bool]] = None,
    ) -> BulkOperationStats:
        games = database.get_all_games()

        if game_indices is not None:
            games_to_process = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            games_to_process = games

        total_games = len(games_to_process)
        if total_games == 0:
            if progress_callback:
                progress_callback(0, 0, "No games to process")
            return BulkOperationStats(
                success=True,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0,
            )

        max_workers = get_process_pool_max_workers(os.cpu_count(), self.config)

        updated_games = []
        games_updated = 0
        games_failed = 0
        games_skipped = 0

        executor = None
        completed = 0
        try:
            executor = ProcessPoolExecutor(max_workers=max_workers)

            future_to_game = {
                executor.submit(
                    _process_game_for_remove_tags,
                    game.pgn,
                    tag_names,
                ): game
                for game in games_to_process
            }

            for future in as_completed(future_to_game):
                if cancellation_check and cancellation_check():
                    for f in future_to_game:
                        if f != future:
                            f.cancel()
                    break

                game = future_to_game[future]
                completed += 1

                if progress_callback:
                    progress_callback(completed, total_games, f"Processing game {completed}/{total_games}")

                try:
                    new_pgn, cleared_fields, outcome = future.result()

                    if outcome == BulkProcessingOutcome.UPDATED:
                        if new_pgn:
                            game.pgn = new_pgn
                            if cleared_fields:
                                for field_name, field_value in cleared_fields.items():
                                    setattr(game, field_name, field_value)
                            updated_games.append(game)
                            games_updated += 1
                        else:
                            games_failed += 1
                    elif outcome == BulkProcessingOutcome.SKIPPED:
                        games_skipped += 1
                    else:
                        games_failed += 1
                except Exception:
                    games_failed += 1

        finally:
            if executor:
                executor.shutdown(wait=True)

        if updated_games:
            database.batch_update_games(updated_games)

        logging_service = LoggingService.get_instance()
        logging_service.info(
            f"Bulk tag operation completed: tags_removed={len(tag_names)}, games_processed={completed}, "
            f"games_updated={games_updated}, games_failed={games_failed}, games_skipped={games_skipped}"
        )

        return BulkOperationStats(
            success=True,
            games_processed=completed,
            games_updated=games_updated,
            games_failed=games_failed,
            games_skipped=games_skipped,
        )
