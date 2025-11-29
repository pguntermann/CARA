"""Controller for managing chessboard annotations."""

from typing import Dict, Any, Optional
import uuid
import chess

from app.models.annotation_model import AnnotationModel, Annotation, AnnotationType
from app.models.game_model import GameModel
from app.models.database_model import GameData
from app.services.annotation_storage_service import AnnotationStorageService
from app.views.chessboard_widget import ChessBoardWidget


class AnnotationController:
    """Controller for managing chessboard annotations.
    
    This controller orchestrates annotation operations.
    It coordinates between the annotation model, storage service, and views.
    """
    
    def __init__(self, config: Dict[str, Any], game_model: GameModel,
                 database_controller=None) -> None:
        """Initialize the annotation controller.
        
        Args:
            config: Configuration dictionary.
            game_model: GameModel instance for tracking active game and move.
            database_controller: Optional DatabaseController for marking databases as unsaved.
        """
        self.config = config
        self.game_model = game_model
        self.database_controller = database_controller
        
        # Initialize annotation model
        self.annotation_model = AnnotationModel()
        
        # Connect to game model signals
        self.game_model.active_game_changed.connect(self._on_active_game_changed)
        self.game_model.active_move_changed.connect(self._on_active_move_changed)
        
        # Board widget reference (set by view)
        self._board_widget: Optional[ChessBoardWidget] = None
    
    def set_board_widget(self, board_widget: ChessBoardWidget) -> None:
        """Set the chessboard widget for drawing annotations.
        
        Args:
            board_widget: ChessBoardWidget instance.
        """
        self._board_widget = board_widget
        if board_widget:
            board_widget.set_annotation_model(self.annotation_model)
    
    def get_annotation_model(self) -> AnnotationModel:
        """Get the annotation model.
        
        Returns:
            The AnnotationModel instance for observing annotation state.
        """
        return self.annotation_model
    
    def toggle_annotations_visibility(self) -> None:
        """Toggle annotation layer visibility."""
        self.annotation_model.toggle_annotations_visibility()
    
    def _on_active_game_changed(self, game: Optional[GameData]) -> None:
        """Handle active game change.
        
        Args:
            game: New active game or None.
        """
        if game:
            # Load annotations from game
            annotations = AnnotationStorageService.load_annotations(game)
            if annotations:
                self.annotation_model.set_all_annotations(annotations)
            else:
                self.annotation_model.clear_all_annotations()
        else:
            self.annotation_model.clear_all_annotations()
    
    def _on_active_move_changed(self, ply_index: int) -> None:
        """Handle active move change (annotations are shown per move).
        
        Args:
            ply_index: New active ply index.
        """
        # Annotations are automatically shown for current ply via model signals
        # The board widget observes the model and updates accordingly
        pass
    
    def _find_existing_arrow(self, ply_index: int, from_square: str, to_square: str, color: list[int]) -> Optional[str]:
        """Find an existing arrow annotation matching the given parameters.
        
        Args:
            ply_index: Ply index.
            from_square: Starting square.
            to_square: Ending square.
            color: RGB color [r, g, b].
            
        Returns:
            Annotation ID if found, None otherwise.
        """
        annotations = self.annotation_model.get_annotations(ply_index)
        for annotation in annotations:
            if (annotation.annotation_type == AnnotationType.ARROW and
                annotation.from_square == from_square and
                annotation.to_square == to_square and
                annotation.color == color):
                return annotation.annotation_id
        return None
    
    def _find_existing_square(self, ply_index: int, square: str, color: list[int]) -> Optional[str]:
        """Find an existing square annotation matching the given parameters.
        
        Args:
            ply_index: Ply index.
            square: Square name.
            color: RGB color [r, g, b].
            
        Returns:
            Annotation ID if found, None otherwise.
        """
        annotations = self.annotation_model.get_annotations(ply_index)
        for annotation in annotations:
            if (annotation.annotation_type == AnnotationType.SQUARE and
                annotation.square == square and
                annotation.color == color):
                return annotation.annotation_id
        return None
    
    def _find_existing_circle(self, ply_index: int, square: str, color: list[int]) -> Optional[str]:
        """Find an existing circle annotation matching the given parameters.
        
        Args:
            ply_index: Ply index.
            square: Square name.
            color: RGB color [r, g, b].
            
        Returns:
            Annotation ID if found, None otherwise.
        """
        annotations = self.annotation_model.get_annotations(ply_index)
        for annotation in annotations:
            if (annotation.annotation_type == AnnotationType.CIRCLE and
                annotation.square == square and
                annotation.color == color):
                return annotation.annotation_id
        return None
    
    def add_arrow(self, from_square: str, to_square: str, color: list[int], color_index: int, size: float = 1.0, shadow: bool = False) -> Optional[str]:
        """Add or toggle an arrow annotation.
        
        If an identical arrow already exists, it will be removed (toggle behavior).
        
        Args:
            from_square: Starting square (e.g., "e2").
            to_square: Ending square (e.g., "e4").
            color: RGB color [r, g, b].
            color_index: Index into color palette.
            size: Size multiplier (default 1.0).
            shadow: Whether to add black shadow for readability (default False).
            
        Returns:
            Annotation ID if added, None if removed or failed.
        """
        if not self.game_model.active_game:
            return None
        
        ply_index = self.game_model.get_active_move_ply()
        
        # Check if identical arrow exists - if so, remove it (toggle)
        existing_id = self._find_existing_arrow(ply_index, from_square, to_square, color)
        if existing_id:
            self.annotation_model.remove_annotation(ply_index, existing_id)
            return None
        
        # Add new arrow
        annotation_id = str(uuid.uuid4())
        annotation = Annotation(
            annotation_id=annotation_id,
            annotation_type=AnnotationType.ARROW,
            color=color,
            color_index=color_index,
            from_square=from_square,
            to_square=to_square,
            size=size,
            shadow=shadow if shadow else None
        )
        
        self.annotation_model.add_annotation(ply_index, annotation)
        
        return annotation_id
    
    def add_square(self, square: str, color: list[int], color_index: int, size: float = 1.0, shadow: bool = False) -> Optional[str]:
        """Add or toggle a square highlight annotation.
        
        If an identical square already exists, it will be removed (toggle behavior).
        
        Args:
            square: Square to highlight (e.g., "e4").
            color: RGB color [r, g, b].
            color_index: Index into color palette.
            size: Size multiplier (default 1.0).
            shadow: Whether to add black shadow for readability (default False).
            
        Returns:
            Annotation ID if added, None if removed or failed.
        """
        if not self.game_model.active_game:
            return None
        
        ply_index = self.game_model.get_active_move_ply()
        
        # Check if identical square exists - if so, remove it (toggle)
        existing_id = self._find_existing_square(ply_index, square, color)
        if existing_id:
            self.annotation_model.remove_annotation(ply_index, existing_id)
            return None
        
        # Add new square
        annotation_id = str(uuid.uuid4())
        annotation = Annotation(
            annotation_id=annotation_id,
            annotation_type=AnnotationType.SQUARE,
            color=color,
            color_index=color_index,
            square=square,
            size=size,
            shadow=shadow if shadow else None
        )
        
        self.annotation_model.add_annotation(ply_index, annotation)
        
        return annotation_id
    
    def add_circle(self, square: str, color: list[int], color_index: int, size: float = 1.0, shadow: bool = False) -> Optional[str]:
        """Add or toggle a circle annotation.
        
        If an identical circle already exists, it will be removed (toggle behavior).
        
        Args:
            square: Square to circle (e.g., "e4").
            color: RGB color [r, g, b].
            color_index: Index into color palette.
            size: Size multiplier (default 1.0).
            shadow: Whether to add black shadow for readability (default False).
            
        Returns:
            Annotation ID if added, None if removed or failed.
        """
        if not self.game_model.active_game:
            return None
        
        ply_index = self.game_model.get_active_move_ply()
        
        # Check if identical circle exists - if so, remove it (toggle)
        existing_id = self._find_existing_circle(ply_index, square, color)
        if existing_id:
            self.annotation_model.remove_annotation(ply_index, existing_id)
            return None
        
        # Add new circle
        annotation_id = str(uuid.uuid4())
        annotation = Annotation(
            annotation_id=annotation_id,
            annotation_type=AnnotationType.CIRCLE,
            color=color,
            color_index=color_index,
            square=square,
            size=size,
            shadow=shadow if shadow else None
        )
        
        self.annotation_model.add_annotation(ply_index, annotation)
        
        return annotation_id
    
    def add_text(self, square: str, text: str, color: list[int], color_index: int,
                 text_x: float = 0.5, text_y: float = 0.5,
                 text_size: float = 12.0, text_rotation: float = 0.0,
                 size: float = 1.0, shadow: bool = False) -> Optional[str]:
        """Add a text annotation.
        
        Args:
            square: Square to place text on (e.g., "e4").
            text: Text content.
            color: RGB color [r, g, b].
            color_index: Index into color palette.
            text_x: X position relative to square (0-1).
            text_y: Y position relative to square (0-1).
            text_size: Text size in points.
            text_rotation: Text rotation in degrees.
            size: Size multiplier (default 1.0).
            shadow: Whether to add black shadow for readability (default False).
            
        Returns:
            Annotation ID if successful, None otherwise.
        """
        if not self.game_model.active_game:
            return None
        
        ply_index = self.game_model.get_active_move_ply()
        annotation_id = str(uuid.uuid4())
        
        annotation = Annotation(
            annotation_id=annotation_id,
            annotation_type=AnnotationType.TEXT,
            color=color,
            color_index=color_index,
            square=square,
            text=text,
            text_x=text_x,
            text_y=text_y,
            text_size=text_size,
            text_rotation=text_rotation,
            size=size,
            shadow=shadow if shadow else None
        )
        
        self.annotation_model.add_annotation(ply_index, annotation)
        
        return annotation_id
    
    def update_text_annotation(self, annotation_id: str, text: Optional[str] = None,
                               text_x: Optional[float] = None, text_y: Optional[float] = None,
                               text_size: Optional[float] = None, text_rotation: Optional[float] = None) -> bool:
        """Update text annotation properties.
        
        Args:
            annotation_id: ID of text annotation to update.
            text: New text content, None to keep current.
            text_x: New X position (0-1 relative to square), None to keep current.
            text_y: New Y position (0-1 relative to square), None to keep current.
            text_size: New text size in points, None to keep current.
            text_rotation: New rotation in degrees, None to keep current.
            
        Returns:
            True if annotation was updated, False otherwise.
        """
        if not self.game_model.active_game:
            return False
        
        ply_index = self.game_model.get_active_move_ply()
        annotations = self.annotation_model.get_annotations(ply_index)
        
        for annotation in annotations:
            if annotation.annotation_id == annotation_id and annotation.annotation_type == AnnotationType.TEXT:
                # Update properties
                if text is not None:
                    annotation.text = text
                if text_x is not None:
                    annotation.text_x = text_x
                if text_y is not None:
                    annotation.text_y = text_y
                if text_size is not None:
                    annotation.text_size = text_size
                if text_rotation is not None:
                    annotation.text_rotation = text_rotation
                
                # Emit signal to update view
                self.annotation_model.annotations_changed.emit(ply_index)
                return True
        
        return False
    
    def remove_annotation(self, annotation_id: str) -> bool:
        """Remove an annotation by ID.
        
        Args:
            annotation_id: ID of annotation to remove.
            
        Returns:
            True if annotation was found and removed, False otherwise.
        """
        if not self.game_model.active_game:
            return False
        
        ply_index = self.game_model.get_active_move_ply()
        success = self.annotation_model.remove_annotation(ply_index, annotation_id)
        
        return success
    
    def clear_current_annotations(self) -> None:
        """Clear all annotations for the current move."""
        if not self.game_model.active_game:
            return
        
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        ply_index = self.game_model.get_active_move_ply()
        self.annotation_model.clear_annotations(ply_index)
        
        progress_service.set_status("Cleared annotations for current move")
    
    def clear_all_annotations(self) -> None:
        """Clear all annotations for all moves."""
        if not self.game_model.active_game:
            return
        
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        self.annotation_model.clear_all_annotations()
        
        progress_service.set_status("Cleared all annotations")
    
    def save_annotations(self) -> bool:
        """Save annotations to the active game's PGN tag.
        
        Returns:
            True if save was successful, False otherwise.
        """
        if not self.game_model.active_game:
            return False
        
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        game = self.game_model.active_game
        annotations = self.annotation_model.get_all_annotations()
        
        # Count total annotations
        total_count = sum(len(anns) for anns in annotations.values())
        
        success = AnnotationStorageService.store_annotations(game, annotations, self.config)
        
        if success:
            # Emit metadata_updated signal to notify views (e.g., PGN view, metadata view)
            # This must be done FIRST, matching the exact pattern used by CARA analysis
            self.game_model.metadata_updated.emit()
            
            # Update database model to persist the change and mark as unsaved
            if self.database_controller:
                # Find the database model that contains this game
                database_model = self._find_database_model_for_game(game)
                if database_model:
                    # Update the game in the database model
                    database_model.update_game(game)
                    # Mark database as having unsaved changes
                    self.database_controller.mark_database_unsaved(database_model)
            
            progress_service.set_status(f"Saved {total_count} annotation(s) to game")
        else:
            progress_service.set_status("Failed to save annotations")
        
        return success
    
    def _mark_database_unsaved(self) -> None:
        """Mark the database containing the active game as unsaved."""
        if not self.game_model.active_game or not self.database_controller:
            return
        
        game = self.game_model.active_game
        database_model = self._find_database_model_for_game(game)
        if database_model:
            self.database_controller.mark_database_unsaved(database_model)
    
    def _find_database_model_for_game(self, game: GameData) -> Optional[Any]:
        """Find the database model that contains the given game.
        
        Args:
            game: GameData instance to find.
            
        Returns:
            DatabaseModel that contains the game, or None if not found.
        """
        if not self.database_controller or not game:
            return None
        
        # First try the active database
        active_database = self.database_controller.get_active_database()
        if active_database and active_database.find_game(game) is not None:
            return active_database
        
        # If not found, search through all databases in the panel model
        panel_model = self.database_controller.get_panel_model()
        if panel_model:
            all_databases = panel_model.get_all_databases()
            for identifier, info in all_databases.items():
                if info.model.find_game(game) is not None:
                    return info.model
        
        return None
    
    def get_square_from_coords(self, x: float, y: float) -> Optional[str]:
        """Convert board coordinates to chess square.
        
        Args:
            x: X coordinate (0-1 relative to board).
            y: Y coordinate (0-1 relative to board).
            
        Returns:
            Chess square (e.g., "e4") or None if invalid.
        """
        if not self._board_widget:
            return None
        
        # Get board dimensions and calculate square
        # This will be implemented when we update ChessBoardWidget
        # For now, return None - will be implemented in board widget update
        return None

