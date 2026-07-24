"""Annotation model for storing chessboard annotations."""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Dict, List, Optional, Any, Sequence, Union
from dataclasses import dataclass
from enum import Enum

from app.utils.pgn_variation_path import (
    encode_path,
    mainline_path_for_ply,
)


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


AnnotationKey = str  # encode_path(...) — "" = starting position, "0.1.0" = variation path


def normalize_annotation_key(path_or_key: Union[str, int, Sequence[int], None]) -> AnnotationKey:
    """Normalize a path, legacy ply index, or encoded key to an annotation storage key."""
    if path_or_key is None:
        return ""
    if isinstance(path_or_key, str):
        return path_or_key
    if isinstance(path_or_key, int):
        return encode_path(mainline_path_for_ply(path_or_key))
    return encode_path(tuple(int(i) for i in path_or_key))


class AnnotationModel(QObject):
    """Model for storing chessboard annotations per variation path.
    
    This model holds annotation state and emits
    signals when annotations change. Views observe these signals to update
    the UI automatically.
    """
    
    # Signals emit the encoded path key ("" = start, "0.1.0" = sideline, etc.)
    annotations_changed = pyqtSignal(str)
    annotation_added = pyqtSignal(str, str)  # path_key, annotation_id
    annotation_removed = pyqtSignal(str, str)  # path_key, annotation_id
    annotations_cleared = pyqtSignal(str)  # path_key
    annotations_visibility_changed = pyqtSignal(bool)
    
    def __init__(self) -> None:
        """Initialize the annotation model."""
        super().__init__()
        # Store annotations per path key: {encode_path(path): [Annotation, ...]}
        self._annotations: Dict[AnnotationKey, List[Annotation]] = {}
        self._show_annotations: bool = True
    
    def get_annotations(self, path_or_key: Union[str, int, Sequence[int]]) -> List[Annotation]:
        """Get annotations for a variation path (or legacy ply index)."""
        key = normalize_annotation_key(path_or_key)
        return self._annotations.get(key, [])
    
    def add_annotation(
        self, path_or_key: Union[str, int, Sequence[int]], annotation: Annotation
    ) -> None:
        """Add an annotation for a variation path."""
        key = normalize_annotation_key(path_or_key)
        if key not in self._annotations:
            self._annotations[key] = []
        
        self._annotations[key].append(annotation)
        self.annotation_added.emit(key, annotation.annotation_id)
        self.annotations_changed.emit(key)
    
    def remove_annotation(
        self, path_or_key: Union[str, int, Sequence[int]], annotation_id: str
    ) -> bool:
        """Remove an annotation by ID for a variation path."""
        key = normalize_annotation_key(path_or_key)
        if key not in self._annotations:
            return False
        
        annotations = self._annotations[key]
        for i, ann in enumerate(annotations):
            if ann.annotation_id == annotation_id:
                annotations.pop(i)
                self.annotation_removed.emit(key, annotation_id)
                self.annotations_changed.emit(key)
                return True
        
        return False
    
    def clear_annotations(self, path_or_key: Union[str, int, Sequence[int]]) -> None:
        """Clear all annotations for a variation path."""
        key = normalize_annotation_key(path_or_key)
        if key in self._annotations:
            self._annotations[key] = []
            self.annotations_cleared.emit(key)
            self.annotations_changed.emit(key)
    
    def clear_all_annotations(self) -> None:
        """Clear all annotations for all paths."""
        for key in list(self._annotations.keys()):
            self.clear_annotations(key)
    
    def set_annotations(
        self, path_or_key: Union[str, int, Sequence[int]], annotations: List[Annotation]
    ) -> None:
        """Set annotations for a variation path (replaces existing)."""
        key = normalize_annotation_key(path_or_key)
        self._annotations[key] = annotations.copy()
        self.annotations_changed.emit(key)
    
    def get_all_annotations(self) -> Dict[AnnotationKey, List[Annotation]]:
        """Get all annotations keyed by encoded path."""
        return {key: anns.copy() for key, anns in self._annotations.items()}
    
    def set_all_annotations(
        self, annotations: Dict[Union[str, int], List[Annotation]]
    ) -> None:
        """Set all annotations (replaces existing). Keys may be path strings or legacy plies."""
        self._annotations = {
            normalize_annotation_key(key): anns.copy()
            for key, anns in annotations.items()
        }
        for key in self._annotations.keys():
            self.annotations_changed.emit(key)
    
    @property
    def show_annotations(self) -> bool:
        """Get whether annotations are visible."""
        return self._show_annotations
    
    def set_show_annotations(self, show: bool) -> None:
        """Set annotation layer visibility."""
        self._show_annotations = show
        self.annotations_visibility_changed.emit(show)
    
    def toggle_annotations_visibility(self) -> None:
        """Toggle annotation layer visibility."""
        self.set_show_annotations(not self._show_annotations)
