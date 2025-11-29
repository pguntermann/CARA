"""Annotation model for storing chessboard annotations."""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum


class AnnotationType(Enum):
    """Types of annotations."""
    ARROW = "arrow"
    SQUARE = "square"
    CIRCLE = "circle"
    TEXT = "text"


@dataclass
class Annotation:
    """Represents a single annotation on the chessboard."""
    annotation_id: str  # Unique identifier
    annotation_type: AnnotationType
    color: List[int]  # RGB color [r, g, b] (computed from color_index and palette)
    color_index: Optional[int]  # Index into color palette
    # For arrow: from_square and to_square
    # For square/circle: square
    # For text: square, text, position, size, rotation
    from_square: Optional[str] = None  # Chess square (e.g., "e2")
    to_square: Optional[str] = None  # Chess square (e.g., "e4")
    square: Optional[str] = None  # Chess square for square/circle/text
    text: Optional[str] = None  # Text content
    text_x: Optional[float] = None  # Text position X (0-1 relative to square)
    text_y: Optional[float] = None  # Text position Y (0-1 relative to square)
    text_size: Optional[float] = None  # Text size
    text_rotation: Optional[float] = None  # Text rotation in degrees
    size: Optional[float] = None  # Size multiplier for arrows, circles, and text (0.5-2.0, default 1.0)
    shadow: Optional[bool] = None  # Whether to add black shadow for readability (default False)


class AnnotationModel(QObject):
    """Model for storing chessboard annotations per move.
    
    This model holds annotation state and emits
    signals when annotations change. Views observe these signals to update
    the UI automatically.
    """
    
    # Signals emitted when annotations change
    annotations_changed = pyqtSignal(int)  # Emitted when annotations change for a ply (ply_index)
    annotation_added = pyqtSignal(int, str)  # Emitted when annotation is added (ply_index, annotation_id)
    annotation_removed = pyqtSignal(int, str)  # Emitted when annotation is removed (ply_index, annotation_id)
    annotations_cleared = pyqtSignal(int)  # Emitted when all annotations cleared for a ply (ply_index)
    annotations_visibility_changed = pyqtSignal(bool)  # Emitted when annotation layer visibility changes
    
    def __init__(self) -> None:
        """Initialize the annotation model."""
        super().__init__()
        # Store annotations per ply: {ply_index: [Annotation, ...]}
        self._annotations: Dict[int, List[Annotation]] = {}
        # Visibility state for annotation layer
        self._show_annotations: bool = True  # Default to showing annotations
    
    def get_annotations(self, ply_index: int) -> List[Annotation]:
        """Get annotations for a specific ply.
        
        Args:
            ply_index: Ply index (0 = starting position, 1 = after first move, etc.).
            
        Returns:
            List of annotations for the ply, empty list if none.
        """
        return self._annotations.get(ply_index, [])
    
    def add_annotation(self, ply_index: int, annotation: Annotation) -> None:
        """Add an annotation for a specific ply.
        
        Args:
            ply_index: Ply index (0 = starting position, 1 = after first move, etc.).
            annotation: Annotation to add.
        """
        if ply_index not in self._annotations:
            self._annotations[ply_index] = []
        
        self._annotations[ply_index].append(annotation)
        self.annotation_added.emit(ply_index, annotation.annotation_id)
        self.annotations_changed.emit(ply_index)
    
    def remove_annotation(self, ply_index: int, annotation_id: str) -> bool:
        """Remove an annotation by ID.
        
        Args:
            ply_index: Ply index.
            annotation_id: ID of annotation to remove.
            
        Returns:
            True if annotation was found and removed, False otherwise.
        """
        if ply_index not in self._annotations:
            return False
        
        annotations = self._annotations[ply_index]
        for i, ann in enumerate(annotations):
            if ann.annotation_id == annotation_id:
                annotations.pop(i)
                self.annotation_removed.emit(ply_index, annotation_id)
                self.annotations_changed.emit(ply_index)
                return True
        
        return False
    
    def clear_annotations(self, ply_index: int) -> None:
        """Clear all annotations for a specific ply.
        
        Args:
            ply_index: Ply index.
        """
        if ply_index in self._annotations:
            self._annotations[ply_index] = []
            self.annotations_cleared.emit(ply_index)
            self.annotations_changed.emit(ply_index)
    
    def clear_all_annotations(self) -> None:
        """Clear all annotations for all plies."""
        for ply_index in list(self._annotations.keys()):
            self.clear_annotations(ply_index)
    
    def set_annotations(self, ply_index: int, annotations: List[Annotation]) -> None:
        """Set annotations for a specific ply (replaces existing).
        
        Args:
            ply_index: Ply index.
            annotations: List of annotations to set.
        """
        self._annotations[ply_index] = annotations.copy()
        self.annotations_changed.emit(ply_index)
    
    def get_all_annotations(self) -> Dict[int, List[Annotation]]:
        """Get all annotations for all plies.
        
        Returns:
            Dictionary mapping ply_index to list of annotations.
        """
        return {ply: anns.copy() for ply, anns in self._annotations.items()}
    
    def set_all_annotations(self, annotations: Dict[int, List[Annotation]]) -> None:
        """Set all annotations (replaces existing).
        
        Args:
            annotations: Dictionary mapping ply_index to list of annotations.
        """
        self._annotations = {ply: anns.copy() for ply, anns in annotations.items()}
        # Emit signal for all affected plies
        for ply_index in self._annotations.keys():
            self.annotations_changed.emit(ply_index)
    
    @property
    def show_annotations(self) -> bool:
        """Get whether annotations are visible.
        
        Returns:
            True if annotations are visible, False otherwise.
        """
        return self._show_annotations
    
    def set_show_annotations(self, show: bool) -> None:
        """Set annotation layer visibility.
        
        Args:
            show: True to show annotations, False to hide them.
        """
        # Always update the value and emit signal, even if same value
        # This ensures views are updated when model is connected
        self._show_annotations = show
        self.annotations_visibility_changed.emit(show)
    
    def toggle_annotations_visibility(self) -> None:
        """Toggle annotation layer visibility."""
        self.set_show_annotations(not self._show_annotations)

