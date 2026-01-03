# CARA - Annotation System Implementation

## Overview

The Annotation System allows users to add visual annotations (arrows, squares, circles, text) to chessboard positions. Annotations are stored per move (ply) and can be saved to PGN tags for persistence. The system supports multiple annotation types with customizable colors, sizes, and styling options. Annotations are displayed on the chessboard and can be toggled on/off.

## Architecture

The annotation system follows a **Model-Controller-Service-View** pattern with **per-ply storage**:

### Component Responsibilities

**AnnotationController** (`app/controllers/annotation_controller.py`):
- Orchestrates annotation operations
- Manages `AnnotationModel` and `AnnotationStorageService`
- Handles annotation creation (arrow, square, circle, text)
- Implements toggle behavior (add/remove identical annotations)
- Manages annotation visibility
- Handles game and move changes (loads annotations per game)
- Saves annotations to PGN tags
- Marks databases as unsaved when annotations are saved

**AnnotationModel** (`app/models/annotation_model.py`):
- Stores annotations per ply: `{ply_index: [Annotation, ...]}`
- Emits signals when annotations change
- Manages annotation layer visibility
- Provides methods to add, remove, clear annotations
- QObject-based model for signal/slot communication

**AnnotationStorageService** (`app/services/annotation_storage_service.py`):
- Serializes annotations to JSON
- Compresses and stores data in PGN tag `[CARAAnnotations "..."]`
- Stores metadata in `[CARAAnnotationsInfo "..."]` and checksum in `[CARAAnnotationsChecksum "..."]`
- Loads and validates stored annotations
- Handles corrupted data cleanup

**ChessBoardWidget** (`app/views/chessboard_widget.py`):
- Renders annotations on chessboard
- Observes `AnnotationModel` signals for updates
- Draws arrows, squares, circles, text based on annotation data
- Handles annotation layer visibility toggle

### Component Interactions

**Annotation Creation Flow**:
1. User interacts with chessboard (e.g., drags to create arrow)
2. View calls controller method (e.g., `add_arrow()`)
3. Controller gets current ply index from `GameModel`
4. Controller checks if identical annotation exists (toggle behavior)
5. If exists, controller removes it (toggle off)
6. If not exists, controller creates new `Annotation` with unique ID
7. Controller calls `AnnotationModel.add_annotation()`
8. Model stores annotation and emits `annotation_added` signal
9. View observes signal and redraws chessboard
10. Database is marked as unsaved (if auto-save enabled)

**Game Change Flow**:
1. User switches to different game
2. `GameModel` emits `active_game_changed` signal
3. Controller observes signal and calls `_on_active_game_changed()`
4. Controller calls `AnnotationStorageService.load_annotations()`
5. Service loads annotations from game's PGN tag
6. Controller calls `AnnotationModel.set_all_annotations()`
7. Model stores annotations and emits signals for all affected plies
8. View observes signals and updates chessboard display

**Move Navigation Flow**:
1. User navigates to different move
2. `GameModel` emits `active_move_changed` signal
3. Controller observes signal (annotations are automatically shown for current ply)
4. View observes `AnnotationModel` and displays annotations for current ply
5. No explicit controller action needed (model/view handle it)

**Annotation Save Flow**:
1. User saves annotations (or auto-save triggers)
2. Controller calls `save_annotations()`
3. Controller gets all annotations from model
4. Controller calls `AnnotationStorageService.store_annotations()`
5. Service serializes, compresses, and stores in PGN tag
6. Service updates game's PGN text
7. Controller emits `metadata_updated` signal on `GameModel`
8. Controller updates database model and marks as unsaved
9. Progress service displays success message

**Annotation Visibility Toggle Flow**:
1. User toggles annotation layer visibility
2. Controller calls `toggle_annotations_visibility()`
3. Controller calls `AnnotationModel.toggle_annotations_visibility()`
4. Model emits `annotations_visibility_changed` signal
5. View observes signal and shows/hides annotation layer

## Annotation Types

### Arrow Annotations

- **Purpose**: Show move directions or piece trajectories
- **Properties**:
  - `from_square`: Starting square (e.g., "e2")
  - `to_square`: Ending square (e.g., "e4")
  - `color`: RGB color [r, g, b]
  - `color_index`: Index into color palette
  - `size`: Size multiplier (0.5-2.0, default: 1.0)
  - `shadow`: Whether to add black shadow for readability

### Square Annotations

- **Purpose**: Highlight squares
- **Properties**:
  - `square`: Square to highlight (e.g., "e4")
  - `color`: RGB color [r, g, b]
  - `color_index`: Index into color palette
  - `size`: Size multiplier (0.5-2.0, default: 1.0)
  - `shadow`: Whether to add black shadow for readability

### Circle Annotations

- **Purpose**: Circle squares
- **Properties**:
  - `square`: Square to circle (e.g., "e4")
  - `color`: RGB color [r, g, b]
  - `color_index`: Index into color palette
  - `size`: Size multiplier (0.5-2.0, default: 1.0)
  - `shadow`: Whether to add black shadow for readability

### Text Annotations

- **Purpose**: Add text labels to squares
- **Properties**:
  - `square`: Square to place text on (e.g., "e4")
  - `text`: Text content
  - `color`: RGB color [r, g, b]
  - `color_index`: Index into color palette
  - `text_x`: X position relative to square (0-1, default: 0.5)
  - `text_y`: Y position relative to square (0-1, default: 0.5)
  - `text_size`: Text size in points (default: 12.0)
  - `text_rotation`: Text rotation in degrees (default: 0.0)
  - `size`: Size multiplier (0.5-2.0, default: 1.0)
  - `shadow`: Whether to add black shadow for readability

## Toggle Behavior

Annotations support toggle behavior:
- **Adding identical annotation**: If an annotation with same type, squares/position, and color exists, it is removed (toggle off)
- **Adding different annotation**: Creates new annotation (toggle on)
- **Purpose**: Allows users to easily add/remove annotations by repeating the same action

Toggle behavior is implemented in controller methods:
- `_find_existing_arrow()`: Checks for identical arrow
- `_find_existing_square()`: Checks for identical square
- `_find_existing_circle()`: Checks for identical circle

## Annotation Storage

Annotations are stored in PGN tags for persistence:

- **Tag**: `[CARAAnnotations "..."]` - Compressed, base64-encoded JSON
- **Metadata**: `[CARAAnnotationsInfo "..."]` - App version and creation datetime
- **Checksum**: `[CARAAnnotationsChecksum "..."]` - SHA256 hash for data integrity

Storage format:
- JSON serialization: `{ply_index: [annotation_dict, ...]}`
- Each annotation dict includes: id, type, color, color_index, and type-specific properties
- Gzip compression (level 9)
- Base64 encoding for PGN tag compatibility
- Checksum validation on load

If annotations cannot be decompressed or checksum validation fails, corrupted tags are automatically removed from the game's PGN.

## Per-Ply Storage

Annotations are stored per ply (move):
- **Ply index 0**: Starting position
- **Ply index 1**: After white's first move
- **Ply index 2**: After black's first move
- **Ply index N**: After N-th half-move

This allows:
- Different annotations for each position in the game
- Annotations persist when navigating through moves
- Annotations are automatically shown/hidden based on current move

## Visibility Management

Annotation layer visibility can be toggled:
- **Show annotations**: All annotations are visible on chessboard
- **Hide annotations**: All annotations are hidden (but not deleted)
- **Toggle**: Users can show/hide annotations without losing them
- **Per-game**: Visibility state is managed per game session

## Code Locations

- **Controller**: `app/controllers/annotation_controller.py`
- **Model**: `app/models/annotation_model.py`
- **Storage**: `app/services/annotation_storage_service.py`
- **View**: `app/views/chessboard_widget.py` (annotation rendering)
- **Data Classes**: `app/models/annotation_model.py` (Annotation, AnnotationType)

