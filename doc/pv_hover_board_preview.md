# PV Move Hover Board Preview Feature

## Overview

This feature displays a miniature chessboard preview when hovering over moves in Principal Variation (PV) lines in the Manual Analysis view. Each move in the PV is displayed as a separate hoverable label. When hovering over a move, a popup miniature board shows the position after that move. The feature is available in version 2.4.5+.

## Architecture

### Components

- **HoverablePvLabel** (`app/views/hoverable_pv_label.py`): A QLabel subclass representing a single move in a PV line. Shows a miniature board popup on hover.
- **MiniChessBoardWidget** (`app/views/mini_chessboard_widget.py`): A miniature chessboard widget displayed as a popup tooltip.
- **DetailManualAnalysisView**: Creates separate HoverablePvLabel instances for each move in the PV when the feature is enabled.

### Implementation Approach

The implementation uses separate QLabel widgets for each move in the PV line, rather than a single label with position mapping. This simplifies hover detection and avoids complex HTML parsing.

## Core Functionality

- When hovering over a move in a PV line, a miniature board popup displays showing the position after that move
- The position is calculated by applying all moves from the start of the PV up to and including the hovered move
- When the mouse leaves the move, the miniature board is hidden
- The feature works for all PV lines (PV1, PV2, PV3) displayed in the Manual Analysis view
- The feature can be toggled on/off via menu: Manual Analysis → Enable miniature preview

## User Experience

- **Debouncing**: Board updates are debounced (configurable delay, default 50ms) to prevent excessive updates during rapid mouse movement
- **Visual feedback**: Hovered moves are underlined, and a miniature board popup appears
- **Non-move exclusion**: Only hovering over move text triggers the preview (not spaces or prefixes)
- **Performance**: Updates are smooth and do not cause UI lag
- **Configuration**: Hover delay and miniature board appearance are configurable via config.json

## Technical Constraints

- Must not break existing PV line rendering (HTML formatting, trajectory highlighting)
- Must not interfere with existing click interactions or other mouse events
- Must preserve all existing styling and formatting
- Must work with truncated PV lines (with "..." suffix)

## Implementation Details

### HoverablePvLabel Class

Each move in the PV is displayed as a separate `HoverablePvLabel` instance. The class:

- Inherits from `QLabel` and displays a single move text
- Tracks hover state and shows/hides the miniature board popup
- Uses QTimer for debouncing hover events
- Applies underline styling when hovered
- Calculates position by applying moves from the start of the PV up to the hovered move

**Key methods**:
- `mouseMoveEvent()`: Detects hover and starts debounce timer
- `leaveEvent()`: Hides miniature board and removes underline
- `_on_hover_timeout()`: Shows miniature board with calculated position
- `_show_mini_board()`: Displays popup at cursor position with screen boundary checks
- `_hide_mini_board()`: Hides the popup

### MiniChessBoardWidget Class

A popup widget that displays a miniature chessboard:

- Displays only pieces (no coordinates, arrows by default)
- Matches main board orientation (flipped state)
- Can optionally show move arrows if "Show best move arrow" is enabled
- Positioned near cursor with screen boundary detection
- Uses ToolTip window flags for popup behavior

### Integration with DetailManualAnalysisView

In `_create_analysis_line_widget()`, when PV hover is enabled:

1. PV moves are split into individual move strings
2. A horizontal layout is created for the PV section
3. A " | PV: " prefix label is added
4. A `HoverablePvLabel` is created for each move
5. Labels are added to the layout with proper spacing
6. Truncation is handled if PV exceeds available width

### Position Calculation

When a move is hovered:

1. Start from the current analysis position (FEN)
2. Apply all moves from the start of the PV up to and including the hovered move
3. Parse moves using `chess.Board.parse_san()`
4. Calculate resulting FEN after applying moves
5. Display position in miniature board popup

### Debouncing

- Hover delay is configurable via `pv_hover.hover_delay_ms` (default: 50ms)
- Timer is cancelled if mouse moves to a different move
- Only updates after mouse stays over the same move for the delay period
- Prevents excessive updates during rapid mouse movement

## Configuration

The feature is configured in `config.json` under `ui.panels.detail.manual_analysis.pv_hover`:

```json
{
  "pv_hover": {
    "enabled": true,
    "hover_delay_ms": 50,
    "restore_on_leave": true,
    "mini_board": {
      "size": 160,
      "offset_x": 20,
      "offset_y": 20
    }
  }
}
```

**Configuration options**:
- `enabled`: Enable/disable the feature
- `hover_delay_ms`: Debounce delay in milliseconds (default: 50)
- `restore_on_leave`: Whether to hide preview when mouse leaves (always true)
- `mini_board.size`: Size of the miniature board in pixels (default: 160)
- `mini_board.offset_x`: Horizontal offset from cursor (default: 20)
- `mini_board.offset_y`: Vertical offset from cursor (default: 20)

## Edge Cases and Error Handling

### Invalid Moves

- If a move in the PV cannot be parsed or is invalid, the position update is aborted
- Miniature board is not shown for invalid moves
- Errors are handled silently (no user-facing error messages)

### PV Updates

- When PV updates (new analysis results), widgets are recreated
- Original FEN is updated to the new analysis position
- Frozen PV snapshot prevents updates during active hover

### Rapid Mouse Movement

- Debouncing prevents excessive updates
- Timer is cancelled if mouse moves to a different move
- Only updates after mouse stays over the same move for the delay period

### Screen Boundaries

- Miniature board position is adjusted to stay within screen boundaries
- Popup moves left/right or up/down if it would extend beyond screen edges
- Y position is stabilized during hover to prevent flickering

## Code Location

Implementation files:

- `app/views/hoverable_pv_label.py`: HoverablePvLabel class implementation
- `app/views/mini_chessboard_widget.py`: MiniChessBoardWidget class implementation
- `app/views/detail_manual_analysis_view.py`: Integration in `_create_analysis_line_widget()` method
- `app/controllers/manual_analysis_controller.py`: Provides access to BoardController
- `app/config/config.json`: Configuration under `ui.panels.detail.manual_analysis.pv_hover`

## Usage

To use the feature:

1. Enable the feature: Manual Analysis → Enable miniature preview (or set `enabled: true` in config.json)
2. Start manual analysis on any position
3. Hover over moves in the PV lines to see miniature board previews
4. The preview shows the position after the hovered move
5. Move the mouse away to hide the preview
