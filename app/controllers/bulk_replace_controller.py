"""Bulk replace controller for managing bulk replacement operations."""

import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List
from PyQt6.QtCore import QObject, pyqtSignal

from app.models.database_model import DatabaseModel, GameData
from app.services.bulk_operation_stats import BulkOperationStats
from app.services.bulk_replace_service import BulkReplaceService
from app.services.progress_service import ProgressService
from app.services.engine_parameters_service import EngineParametersService
from app.services.opening_service import OpeningService


def _pgn_fingerprint(pgn: str) -> bytes:
    """Compact digest for comparing PGN before/after multi-step bulk replace (low collision risk)."""
    return hashlib.blake2b(pgn.encode("utf-8"), digest_size=16).digest()


def _combine_multi_step_bulk_stats(
    step_results: List[BulkOperationStats],
    games_in_scope: List[GameData],
    initial_fingerprints: Dict[int, bytes],
) -> BulkOperationStats:
    """Single summary for multiple bulk-replace phases: unique games via PGN fingerprint delta."""
    if not step_results:
        return BulkOperationStats(True, 0, 0, 0, 0)
    if len(step_results) == 1:
        return step_results[0]
    n = len(games_in_scope)
    modified = sum(
        1 for g in games_in_scope if _pgn_fingerprint(g.pgn) != initial_fingerprints[id(g)]
    )
    failed_sum = sum(r.games_failed for r in step_results)
    return BulkOperationStats(
        success=True,
        games_processed=n,
        games_updated=modified,
        games_failed=failed_sum,
        games_skipped=n - modified,
    )


class BulkReplaceController(QObject):
    """Controller for bulk replace operations.
    
    This controller orchestrates bulk replacement operations and manages
    the bulk replace service.
    """
    
    # Signal emitted when operation completes
    operation_complete = pyqtSignal(BulkOperationStats)  # result
    
    def __init__(self, config: Dict[str, Any], database_controller, engine_controller, evaluation_controller, game_controller=None) -> None:
        """Initialize the bulk replace controller.
        
        Args:
            config: Configuration dictionary.
            database_controller: DatabaseController instance.
            engine_controller: EngineController instance.
            evaluation_controller: EvaluationController instance.
            game_controller: Optional GameController instance for refreshing active game.
        """
        super().__init__()
        self.config = config
        self.database_controller = database_controller
        self.engine_controller = engine_controller
        self.evaluation_controller = evaluation_controller
        self.game_controller = game_controller
        
        # Initialize service
        self.service = BulkReplaceService(config)
        
        # Get progress service
        self.progress_service = ProgressService.get_instance()
        
        # Track cancellation
        self._cancelled = False
    
    def get_active_database(self) -> Optional[DatabaseModel]:
        """Get the currently active database.
        
        Returns:
            The active DatabaseModel instance, or None.
        """
        return self.database_controller.get_active_database()
    
    def replace_metadata_tag(
        self,
        database: DatabaseModel,
        tag_name: str,
        find_text: str,
        replace_text: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
        overwrite_all: bool = False,
        game_indices: Optional[List[int]] = None
    ) -> BulkOperationStats:
        """Replace text in metadata tags.
        
        Args:
            database: DatabaseModel instance to process.
            tag_name: PGN tag name to replace.
            find_text: Text to find.
            replace_text: Text to replace with.
            case_sensitive: If True, match case exactly.
            use_regex: If True, treat find_text as regex pattern.
            game_indices: Optional list of game indices to process (None = all games).
            
        Returns:
            BulkOperationStats with operation statistics.
        """
        self._cancelled = False
        
        # Show progress
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Bulk Replace: Starting...")
        
        # Progress callback
        def progress_callback(game_index: int, total: int, message: str) -> None:
            if self._cancelled:
                return
            percent = int((game_index / total) * 100) if total > 0 else 0
            self.progress_service.set_progress(percent)
            self.progress_service.set_status(f"Bulk Replace: {message}")
        
        # Cancel flag
        def cancel_flag() -> bool:
            return self._cancelled
        
        # Perform replacement
        result = self.service.replace_metadata_tag(
            database,
            tag_name,
            find_text,
            replace_text,
            case_sensitive,
            use_regex,
            overwrite_all,
            game_indices,
            progress_callback,
            cancel_flag
        )
        
        # Hide progress
        self.progress_service.hide_progress()
        
        # If active game was updated, refresh it to update metadata view
        if self.game_controller and result.success:
            self._refresh_active_game_if_updated(database, game_indices)
        
        # Mark database as having unsaved changes if operation was successful
        if result.success and result.games_updated > 0:
            self.database_controller.mark_database_unsaved(database)
        
        # Emit signal
        self.operation_complete.emit(result)
        
        return result
    
    def replace_metadata_tags(
        self,
        database: DatabaseModel,
        tag_names: List[str],
        find_text: str,
        replace_text: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
        overwrite_all: bool = False,
        game_indices: Optional[List[int]] = None
    ) -> BulkOperationStats:
        """Replace text in multiple metadata tags in a single pass.
        
        This method processes each game once and updates all selected tags,
        which is more efficient than calling replace_metadata_tag multiple times.
        
        Args:
            database: DatabaseModel instance to process.
            tag_names: List of PGN tag names to replace.
            find_text: Text to find.
            replace_text: Text to replace with.
            case_sensitive: If True, match case exactly.
            use_regex: If True, treat find_text as regex pattern.
            overwrite_all: If True, replace any value with replace_text, ignoring find_text.
            game_indices: Optional list of game indices to process (None = all games).
            
        Returns:
            BulkOperationStats with operation statistics.
        """
        self._cancelled = False
        
        # Show progress
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Bulk Replace: Starting...")
        
        # Progress callback
        def progress_callback(game_index: int, total: int, message: str) -> None:
            if self._cancelled:
                return
            percent = int((game_index / total) * 100) if total > 0 else 0
            self.progress_service.set_progress(percent)
            self.progress_service.set_status(f"Bulk Replace: {message}")
        
        # Cancel flag
        def cancel_flag() -> bool:
            return self._cancelled
        
        # Perform replacement
        result = self.service.replace_metadata_tags(
            database,
            tag_names,
            find_text,
            replace_text,
            case_sensitive,
            use_regex,
            overwrite_all,
            game_indices,
            progress_callback,
            cancel_flag
        )
        
        # Hide progress
        self.progress_service.hide_progress()
        
        # If active game was updated, refresh it to update metadata view
        if self.game_controller and result.success:
            self._refresh_active_game_if_updated(database, game_indices)
        
        # Mark database as having unsaved changes if operation was successful
        if result.success and result.games_updated > 0:
            self.database_controller.mark_database_unsaved(database)
        
        # Emit signal
        self.operation_complete.emit(result)
        
        return result
    
    def copy_metadata_tags(
        self,
        database: DatabaseModel,
        target_tags: List[str],
        source_tag: str,
        game_indices: Optional[List[int]] = None
    ) -> BulkOperationStats:
        """Copy value from one metadata tag to multiple target tags in a single pass.
        
        This method processes each game once and updates all selected tags,
        which is more efficient than calling copy_metadata_tag multiple times.
        
        Args:
            database: DatabaseModel instance to process.
            target_tags: List of PGN tag names to update.
            source_tag: PGN tag name to copy from.
            game_indices: Optional list of game indices to process (None = all games).
            
        Returns:
            BulkOperationStats with operation statistics.
        """
        self._cancelled = False
        
        # Show progress
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Bulk Replace: Starting...")
        
        # Progress callback
        def progress_callback(game_index: int, total: int, message: str) -> None:
            if self._cancelled:
                return
            percent = int((game_index / total) * 100) if total > 0 else 0
            self.progress_service.set_progress(percent)
            self.progress_service.set_status(f"Bulk Replace: {message}")
        
        # Cancel flag
        def cancel_flag() -> bool:
            return self._cancelled
        
        # Perform copy
        result = self.service.copy_metadata_tags(
            database,
            target_tags,
            source_tag,
            game_indices,
            progress_callback,
            cancel_flag
        )
        
        # Hide progress
        self.progress_service.hide_progress()
        
        # If active game was updated, refresh it to update metadata view
        if self.game_controller and result.success:
            self._refresh_active_game_if_updated(database, game_indices)
        
        # Mark database as having unsaved changes if operation was successful
        if result.success and result.games_updated > 0:
            self.database_controller.mark_database_unsaved(database)
        
        # Emit signal
        self.operation_complete.emit(result)
        
        return result
    
    def copy_metadata_tag(
        self,
        database: DatabaseModel,
        target_tag: str,
        source_tag: str,
        game_indices: Optional[List[int]] = None
    ) -> BulkOperationStats:
        """Copy value from one metadata tag to another.
        
        Args:
            database: DatabaseModel instance to process.
            target_tag: PGN tag name to update (e.g., "EventDate").
            source_tag: PGN tag name to copy from (e.g., "Date").
            game_indices: Optional list of game indices to process (None = all games).
            
        Returns:
            BulkOperationStats with operation statistics.
        """
        self._cancelled = False
        
        # Show progress
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Bulk Replace: Starting...")
        
        # Progress callback
        def progress_callback(game_index: int, total: int, message: str) -> None:
            if self._cancelled:
                return
            percent = int((game_index / total) * 100) if total > 0 else 0
            self.progress_service.set_progress(percent)
            self.progress_service.set_status(f"Bulk Replace: {message}")
        
        # Cancel flag
        def cancel_flag() -> bool:
            return self._cancelled
        
        # Perform copy
        result = self.service.copy_metadata_tag(
            database,
            target_tag,
            source_tag,
            game_indices,
            progress_callback,
            cancel_flag
        )
        
        # Hide progress
        self.progress_service.hide_progress()
        
        # If active game was updated, refresh it to update metadata view
        if self.game_controller and result.success:
            self._refresh_active_game_if_updated(database, game_indices)
        
        # Mark database as having unsaved changes if operation was successful
        if result.success and result.games_updated > 0:
            self.database_controller.mark_database_unsaved(database)
        
        # Emit signal
        self.operation_complete.emit(result)
        
        return result
    
    def update_result_tags(
        self,
        database: DatabaseModel,
        game_indices: Optional[List[int]] = None
    ) -> BulkOperationStats:
        """Update Result tags based on final position evaluation.
        
        Args:
            database: DatabaseModel instance to process.
            game_indices: Optional list of game indices to process (None = all games).
            
        Returns:
            BulkOperationStats with operation statistics.
        """
        self._cancelled = False
        
        # Get evaluation engine
        from app.controllers.engine_controller import TASK_EVALUATION
        engine_id = self.engine_controller.get_engine_assignment(TASK_EVALUATION)
        if not engine_id:
            return BulkOperationStats(
                success=False,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0,
                error_message="No evaluation engine configured"
            )
        
        # Get engine data
        engine = self.engine_controller.get_engine_model().get_engine(engine_id)
        if not engine:
            return BulkOperationStats(
                success=False,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0,
                error_message="Evaluation engine not found"
            )
        
        engine_path = Path(engine.path)
        
        # Get engine parameters (uses current evaluation engine settings)
        task_params = EngineParametersService.get_task_parameters_for_engine(
            engine_path,
            "evaluation",
            self.config
        )
        
        # Use task-specific parameters if available, otherwise use config.json defaults
        eval_bar_config = self.config.get("ui", {}).get("panels", {}).get("main", {}).get("board", {}).get("evaluation_bar", {})
        max_depth = task_params.get("depth", eval_bar_config.get("max_depth_evaluation", 0))
        time_limit_ms = task_params.get("movetime", 0)  # Evaluation uses infinite analysis by default
        max_threads = task_params.get("threads", eval_bar_config.get("max_threads", None))
        
        # Extract engine-specific options
        engine_options = {}
        for key, value in task_params.items():
            if key not in ["threads", "depth", "movetime"]:
                engine_options[key] = value
        
        # If depth is 0 (infinite), use a reasonable default for bulk operations
        if max_depth == 0:
            max_depth = 12  # Default depth for bulk operations
        
        # If time_limit_ms is 0 (infinite), use a reasonable default for bulk operations
        if time_limit_ms == 0:
            time_limit_ms = 500  # Default 500ms per position for bulk operations
        
        # Show progress
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Bulk Replace: Starting result update...")
        
        # Progress callback
        def progress_callback(game_index: int, total: int, message: str) -> None:
            if self._cancelled:
                return
            percent = int((game_index / total) * 100) if total > 0 else 0
            self.progress_service.set_progress(percent)
            self.progress_service.set_status(f"Bulk Replace: {message}")
        
        # Cancel flag
        def cancel_flag() -> bool:
            return self._cancelled
        
        # Perform update
        result = self.service.update_result_tags(
            database,
            engine_path,
            max_depth,
            time_limit_ms,
            max_threads,
            engine_options,
            game_indices,
            progress_callback,
            cancel_flag
        )
        
        # Hide progress
        self.progress_service.hide_progress()
        
        # If active game was updated, refresh it to update metadata view
        if self.game_controller and result.success:
            self._refresh_active_game_if_updated(database, game_indices)
        
        # Mark database as having unsaved changes if operation was successful
        if result.success and result.games_updated > 0:
            self.database_controller.mark_database_unsaved(database)
        
        # Emit signal
        self.operation_complete.emit(result)
        
        return result
    
    def update_eco_tags(
        self,
        database: DatabaseModel,
        game_indices: Optional[List[int]] = None
    ) -> BulkOperationStats:
        """Update ECO tags based on opening analysis of game moves.
        
        Args:
            database: DatabaseModel instance to process.
            game_indices: Optional list of game indices to process (None = all games).
            
        Returns:
            BulkOperationStats with operation statistics.
        """
        self._cancelled = False
        
        # Create new instance of OpeningService
        opening_service = OpeningService(self.config)
        opening_service.load()
        
        # Show progress
        self.progress_service.show_progress()
        self.progress_service.set_progress(0)
        self.progress_service.set_status("Bulk Replace: Starting ECO update...")
        
        # Progress callback
        def progress_callback(game_index: int, total: int, message: str) -> None:
            if self._cancelled:
                return
            percent = int((game_index / total) * 100) if total > 0 else 0
            self.progress_service.set_progress(percent)
            self.progress_service.set_status(f"Bulk Replace: {message}")
        
        # Cancel flag
        def cancel_flag() -> bool:
            return self._cancelled
        
        # Perform update
        result = self.service.update_eco_tags(
            database,
            opening_service,
            game_indices,
            progress_callback,
            cancel_flag
        )
        
        # Hide progress
        self.progress_service.hide_progress()
        
        # If active game was updated, refresh it to update metadata view
        if self.game_controller and result.success:
            self._refresh_active_game_if_updated(database, game_indices)
        
        # Mark database as having unsaved changes if operation was successful
        if result.success and result.games_updated > 0:
            self.database_controller.mark_database_unsaved(database)
        
        # Emit signal
        self.operation_complete.emit(result)
        
        return result
    
    def _refresh_active_game_if_updated(self, database: DatabaseModel, game_indices: Optional[List[int]]) -> None:
        """Refresh the active game if it was among the updated games.
        
        Args:
            database: DatabaseModel instance that was updated.
            game_indices: Optional list of game indices that were processed (None = all games).
        """
        if not self.game_controller:
            return
        
        game_model = self.game_controller.get_game_model()
        active_game = game_model.active_game
        if not active_game:
            return
        
        # Get all games from database
        games = database.get_all_games()
        
        # Determine which games were updated
        if game_indices is not None:
            updated_games = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            updated_games = games
        
        # Check if active game is in the updated games
        # Compare by reference since GameData objects are the same instances
        if active_game in updated_games:
            # Refresh active game to update metadata view
            game_model.refresh_active_game()
    
    def cancel_operation(self) -> None:
        """Cancel the current operation."""
        self._cancelled = True
    
    def execute_bulk_replace_operations(
        self,
        database: DatabaseModel,
        is_copy_mode: bool,
        overwrite_all: bool,
        has_find_text: bool,
        has_replace_text: bool,
        selected_tags: List[str],
        source_tag: Optional[str],
        find_text: str,
        replace_text: str,
        case_sensitive: bool,
        use_regex: bool,
        has_result_update: bool,
        has_eco_update: bool,
        game_indices: Optional[List[int]]
    ) -> BulkOperationStats:
        """Execute bulk replace operations with validation and result aggregation.
        
        This method validates inputs, executes operations, and aggregates results.
        All business logic is centralized here, keeping the view simple.
        
        Args:
            database: DatabaseModel instance to process.
            is_copy_mode: True if copying from source tag.
            overwrite_all: True if overwriting all values.
            has_find_text: True if find text is provided.
            has_replace_text: True if replace text is provided.
            selected_tags: List of selected tag names.
            source_tag: Source tag name for copy mode.
            find_text: Text to find.
            replace_text: Text to replace with.
            case_sensitive: True if case-sensitive matching.
            use_regex: True if using regex.
            has_result_update: True if updating result tags.
            has_eco_update: True if updating ECO tags.
            game_indices: Optional list of game indices to process.
            
        Returns:
            BulkOperationStats with aggregated operation statistics.
        """
        # Validate at least one operation is selected
        has_replace = is_copy_mode or overwrite_all or (has_find_text and has_replace_text)
        if not has_replace and not has_result_update and not has_eco_update:
            return BulkOperationStats(
                success=False,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0,
                error_message="Please select at least one operation"
            )
        
        # Validate game selection
        if game_indices is not None and len(game_indices) == 0:
            return BulkOperationStats(
                success=False,
                games_processed=0,
                games_updated=0,
                games_failed=0,
                games_skipped=0,
                error_message="No games selected"
            )
        
        # Validate replace/copy operation
        if has_replace:
            if not selected_tags:
                return BulkOperationStats(
                    success=False,
                    games_processed=0,
                    games_updated=0,
                    games_failed=0,
                    games_skipped=0,
                    error_message="Please select at least one tag"
                )
            
            if is_copy_mode:
                if not source_tag or not source_tag.strip():
                    return BulkOperationStats(
                        success=False,
                        games_processed=0,
                        games_updated=0,
                        games_failed=0,
                        games_skipped=0,
                        error_message="Please enter a source tag name"
                    )
                
                if source_tag in selected_tags:
                    return BulkOperationStats(
                        success=False,
                        games_processed=0,
                        games_updated=0,
                        games_failed=0,
                        games_skipped=0,
                        error_message="Source tag cannot be in the target tags list"
                    )
        
        games = database.get_all_games()
        if game_indices is not None:
            games_in_scope = [games[i] for i in game_indices if 0 <= i < len(games)]
        else:
            games_in_scope = list(games)
        initial_fingerprints = {id(g): _pgn_fingerprint(g.pgn) for g in games_in_scope}
        
        step_results: List[BulkOperationStats] = []
        
        if has_replace:
            if is_copy_mode:
                meta_result = self.copy_metadata_tags(
                    database,
                    selected_tags,
                    source_tag,
                    game_indices
                )
            else:
                meta_result = self.replace_metadata_tags(
                    database,
                    selected_tags,
                    find_text,
                    replace_text,
                    case_sensitive,
                    use_regex,
                    overwrite_all,
                    game_indices
                )
            if not meta_result.success:
                return meta_result
            step_results.append(meta_result)
        
        if has_result_update:
            result_update = self.update_result_tags(database, game_indices)
            if not result_update.success:
                return result_update
            step_results.append(result_update)
        
        if has_eco_update:
            eco_result = self.update_eco_tags(database, game_indices)
            if not eco_result.success:
                return eco_result
            step_results.append(eco_result)
        
        return _combine_multi_step_bulk_stats(step_results, games_in_scope, initial_fingerprints)

