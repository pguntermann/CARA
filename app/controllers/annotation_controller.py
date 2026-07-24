"""Controller for managing chessboard annotations."""

from typing import Dict, Any, Optional, List
import uuid

from app.models.annotation_model import (
    AnnotationModel,
    Annotation,
    AnnotationType,
    AnnotationKey,
)
from app.models.game_model import GameModel
from app.models.database_model import GameData
from app.services.annotation_storage_service import AnnotationStorageService
from app.services.logging_service import LoggingService
from app.utils.pgn_variation_path import encode_path
from app.views.widgets.chessboard_widget import ChessBoardWidget


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
        self.game_model.active_path_changed.connect(self._on_active_path_changed)
        
        # Board widget reference (set by view)
        self._board_widget: Optional[ChessBoardWidget] = None

    def _active_path_key(self) -> AnnotationKey:
        return encode_path(self.game_model.get_active_path())
    
    def set_board_widget(self, board_widget: ChessBoardWidget) -> None:
        """Set the chessboard widget for drawing annotations."""
        self._board_widget = board_widget
        if board_widget:
            board_widget.set_annotation_model(self.annotation_model)
    
    def get_annotation_model(self) -> AnnotationModel:
        """Get the annotation model."""
        return self.annotation_model
    
    def toggle_annotations_visibility(self) -> None:
        """Toggle annotation layer visibility."""
        self.annotation_model.toggle_annotations_visibility()
    
    def _on_active_game_changed(self, game: Optional[GameData]) -> None:
        """Handle active game change."""
        if game:
            annotations = AnnotationStorageService.load_annotations(game)
            if annotations:
                self.annotation_model.set_all_annotations(annotations)
            else:
                self.annotation_model.clear_all_annotations()
        else:
            self.annotation_model.clear_all_annotations()
    
    def _on_active_path_changed(self, path: object) -> None:
        """Handle active variation path change (board/views refresh via path)."""
        pass
    
    def _find_existing_arrow(
        self, path_key: AnnotationKey, from_square: str, to_square: str, color: list[int]
    ) -> Optional[str]:
        annotations = self.annotation_model.get_annotations(path_key)
        for annotation in annotations:
            if (annotation.annotation_type == AnnotationType.ARROW and
                annotation.from_square == from_square and
                annotation.to_square == to_square and
                annotation.color == color):
                return annotation.annotation_id
        return None
    
    def _find_existing_square(
        self, path_key: AnnotationKey, square: str, color: list[int]
    ) -> Optional[str]:
        annotations = self.annotation_model.get_annotations(path_key)
        for annotation in annotations:
            if (annotation.annotation_type == AnnotationType.SQUARE and
                annotation.square == square and
                annotation.color == color):
                return annotation.annotation_id
        return None
    
    def _find_existing_circle(
        self, path_key: AnnotationKey, square: str, color: list[int]
    ) -> Optional[str]:
        annotations = self.annotation_model.get_annotations(path_key)
        for annotation in annotations:
            if (annotation.annotation_type == AnnotationType.CIRCLE and
                annotation.square == square and
                annotation.color == color):
                return annotation.annotation_id
        return None
    
    def add_arrow(self, from_square: str, to_square: str, color: list[int], color_index: int, size: float = 1.0, shadow: bool = False) -> Optional[str]:
        """Add or toggle an arrow annotation for the active path."""
        if not self.game_model.active_game:
            return None
        
        path_key = self._active_path_key()
        
        existing_id = self._find_existing_arrow(path_key, from_square, to_square, color)
        if existing_id:
            self.annotation_model.remove_annotation(path_key, existing_id)
            return None
        
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
        
        self.annotation_model.add_annotation(path_key, annotation)
        
        return annotation_id
    
    def add_square(self, square: str, color: list[int], color_index: int, size: float = 1.0, shadow: bool = False) -> Optional[str]:
        """Add or toggle a square highlight for the active path."""
        if not self.game_model.active_game:
            return None
        
        path_key = self._active_path_key()
        
        existing_id = self._find_existing_square(path_key, square, color)
        if existing_id:
            self.annotation_model.remove_annotation(path_key, existing_id)
            return None
        
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
        
        self.annotation_model.add_annotation(path_key, annotation)
        
        return annotation_id
    
    def add_circle(self, square: str, color: list[int], color_index: int, size: float = 1.0, shadow: bool = False) -> Optional[str]:
        """Add or toggle a circle annotation for the active path."""
        if not self.game_model.active_game:
            return None
        
        path_key = self._active_path_key()
        
        existing_id = self._find_existing_circle(path_key, square, color)
        if existing_id:
            self.annotation_model.remove_annotation(path_key, existing_id)
            return None
        
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
        
        self.annotation_model.add_annotation(path_key, annotation)
        
        return annotation_id
    
    def add_text(self, square: str, text: str, color: list[int], color_index: int,
                 text_x: float = 0.5, text_y: float = 0.5,
                 text_size: float = 12.0, text_rotation: float = 0.0,
                 size: float = 1.0, shadow: bool = False) -> Optional[str]:
        """Add a text annotation for the active path."""
        if not self.game_model.active_game:
            return None
        
        path_key = self._active_path_key()
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
        
        self.annotation_model.add_annotation(path_key, annotation)
        
        return annotation_id
    
    def update_text_annotation(self, annotation_id: str, text: Optional[str] = None,
                               text_x: Optional[float] = None, text_y: Optional[float] = None,
                               text_size: Optional[float] = None, text_rotation: Optional[float] = None) -> bool:
        """Update text annotation properties on the active path."""
        if not self.game_model.active_game:
            return False
        
        path_key = self._active_path_key()
        annotations = self.annotation_model.get_annotations(path_key)
        
        for annotation in annotations:
            if annotation.annotation_id == annotation_id and annotation.annotation_type == AnnotationType.TEXT:
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
                
                self.annotation_model.annotations_changed.emit(path_key)
                return True
        
        return False
    
    def remove_annotation(self, annotation_id: str) -> bool:
        """Remove an annotation by ID from the active path."""
        if not self.game_model.active_game:
            return False
        
        path_key = self._active_path_key()
        return self.annotation_model.remove_annotation(path_key, annotation_id)
    
    def clear_current_annotations(self) -> None:
        """Clear all annotations for the current variation path."""
        if not self.game_model.active_game:
            return
        
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        path_key = self._active_path_key()
        self.annotation_model.clear_annotations(path_key)
        
        progress_service.set_status("Cleared annotations for current move")
    
    def clear_all_annotations(self) -> None:
        """Clear all annotations for all paths."""
        if not self.game_model.active_game:
            return
        
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        self.annotation_model.clear_all_annotations()
        
        progress_service.set_status("Cleared all annotations")
    
    def save_annotations(self) -> bool:
        """Save annotations to the active game's PGN tag."""
        if not self.game_model.active_game:
            return False
        
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        game = self.game_model.active_game
        annotations = self.annotation_model.get_all_annotations()
        
        total_count = sum(len(anns) for anns in annotations.values())
        
        success = AnnotationStorageService.store_annotations(game, annotations, self.config)
        
        if success:
            logging_service = LoggingService.get_instance()
            logging_service.info(f"Annotations saved: game_count=1, annotation_count={total_count}")
        
        if success:
            self.game_model.metadata_updated.emit()
            
            if self.database_controller:
                database_model = self.database_controller.find_database_model_for_game(game)
                if database_model:
                    database_model.update_game(game)
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
        database_model = self.database_controller.find_database_model_for_game(game)
        if database_model:
            self.database_controller.mark_database_unsaved(database_model)
    
    def get_square_from_coords(self, x: float, y: float) -> Optional[str]:
        """Convert board coordinates to chess square."""
        if not self._board_widget:
            return None
        return None
