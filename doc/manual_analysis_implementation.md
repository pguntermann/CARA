# CARA - Manual Analysis Implementation

## Overview

The Manual Analysis feature provides continuous engine analysis of chess positions with MultiPV support, allowing users to explore multiple candidate moves simultaneously. The system supports an arbitrary number of PV lines, though only the first three (PV1, PV2, PV3) are integrated with board visualization (arrows) and piece trajectory exploration. A key feature is the **Piece Trajectory Exploration** system, which visualizes how pieces move through engine-recommended sequences by displaying colored trajectory lines on the chessboard. The system integrates with the evaluation bar, board visualization, and supports PV hover board previews.

## Architecture

The manual analysis system follows a **Model-Controller-Service-View** pattern with **thread-based engine communication**:

### Component Responsibilities

**ManualAnalysisController** (`app/controllers/manual_analysis_controller.py`):
- Orchestrates manual analysis operations
- Manages `ManualAnalysisModel` and `ManualAnalysisEngineService`
- Handles position updates with debouncing (100ms delay)
- Coordinates trajectory exploration via `PvPlanParserService`
- Updates `BoardModel` with best moves and positional plans
- Coordinates with `EvaluationController` for evaluation bar integration

**ManualAnalysisModel** (`app/models/manual_analysis_model.py`):
- `QObject`-based model managing analysis state
- Stores `AnalysisLine` instances for each MultiPV line
- Emits signals: `analysis_changed`, `lines_changed`, `is_analyzing_changed`
- Tracks analysis state, MultiPV count, and miniature preview setting
- Provides typed accessors for analysis lines

**ManualAnalysisEngineService** (`app/services/manual_analysis_engine_service.py`):
- Manages `ManualAnalysisEngineThread` (see `engine_implementation.md`)
- Handles continuous analysis with MultiPV support
- Emits `line_update` signals with analysis data
- Updates position without restarting thread
- Supports dynamic MultiPV changes
- Throttles UI updates to prevent flooding (configurable via `update_interval_ms`)
- Implements race condition prevention for position and MultiPV updates

**PvPlanParserService** (`app/services/pv_plan_parser_service.py`):
- Stateless service for parsing PV strings and extracting piece trajectories
- Tracks piece movements through PV sequences
- Identifies most-moved pieces (up to 3)
- Handles piece identification (unique vs. non-unique pieces, promotions)
- Returns `PieceTrajectory` objects with square sequences

**DetailManualAnalysisView** (`app/views/detail_manual_analysis_view.py`):
- UI widget displaying analysis lines
- Observes `ManualAnalysisModel` signals for updates
- Creates `HoverablePvLabel` instances for PV hover preview (see `pv_hover_board_preview.md`)
- Displays evaluation, depth, PV moves, and statistics
- Provides controls for starting/stopping analysis and adjusting MultiPV

**BoardModel** (`app/models/board_model.py`):
- Stores positional plans (`List[PieceTrajectory]`)
- Tracks active PV plan for trajectory exploration (0 = none, 1-3 = PV1-PV3)
- Emits `positional_plan_changed` signal
- Manages arrow visibility (hides arrows when trajectories are shown)
- Note: Only PV1-PV3 are integrated with board visualization; additional PV lines are displayed in the UI but do not have board arrows

### Component Interactions

**Analysis Start Flow**:
1. User clicks "Start Analysis" button in `DetailManualAnalysisView`
2. View calls `ManualAnalysisController.start_analysis()`
3. Controller resets and initializes `ManualAnalysisModel` (creates default lines)
4. Controller gets engine assignment from `EngineController`
5. Controller calls `ManualAnalysisEngineService.start_analysis()` with FEN and MultiPV
6. Service creates `ManualAnalysisEngineThread` (see `engine_implementation.md`)
7. Thread spawns engine process and starts UCI analysis
8. Thread emits `line_update` signals as analysis progresses
9. Controller receives signals and updates model via `update_line()`
10. Model emits `analysis_changed` signal
11. View observes signal and updates UI display
12. Controller updates `BoardModel` with best moves for PV1, PV2, PV3 (only these three lines are integrated with board visualization)

**Analysis Update Flow**:
1. `ManualAnalysisEngineThread` receives UCI info output
2. Thread parses evaluation, depth, PV, and applies update throttling
3. Thread checks if `update_interval_ms` (default: 100ms) has elapsed since last update
4. If throttled, update is stored in `_pending_updates` for later emission
5. If not throttled, thread emits `line_update` signal with analysis data
6. Controller's `_on_line_update()` receives signal
7. Controller validates update matches expected FEN (filters stale updates)
8. Controller calls `model.update_line()` to update `AnalysisLine`
9. Model emits `analysis_changed` signal
10. Controller's `_on_analysis_changed()` extracts first moves from PV1, PV2, PV3
11. Controller updates `BoardModel` with best moves for arrows (only PV1-PV3 are integrated with board)
12. Controller calls `_update_positional_plan()` if trajectory exploration is active (only works with PV1-PV3)
13. View observes `analysis_changed` and updates display (debounced)

**Position Update Flow**:
1. User navigates to different position in game
2. `GameModel.active_move_changed` signal fires
3. Controller's `_on_active_move_changed()` receives signal
4. Controller gets FEN from game tree (position after active move)
5. Controller calls `update_position()` which debounces updates (100ms)
6. After debounce, controller calls `_do_position_update()`
7. Controller clears old lines and sets expected FEN
8. Controller calls `service.update_position()` with new FEN
9. Service thread sets `_search_just_started` flag and `_search_start_time` timestamp
10. Thread updates position without restarting engine (sends stop → position fen → go infinite)
11. Thread ignores `bestmove` messages (infinite search never completes naturally)
12. Thread clears flags only after search is established (depth >= 1 or 2+ info lines after 100ms)
13. New analysis data arrives and updates model

**Trajectory Exploration Flow**:
1. User enables trajectory exploration via menu (e.g., "Explore PV1 Positional Plans")
2. `MainWindow` calls `controller.set_explore_pv_plan(pv_number)` where pv_number is 1-3
3. Controller sets `_active_pv_plan` and calls `_update_positional_plan()`
4. Controller gets PV line from `ManualAnalysisModel` (only PV1-PV3 support trajectory exploration)
5. Controller calls `PvPlanParserService.extract_plan()` with PV string, FEN, max_pieces
6. Parser tracks piece movements through PV sequence
7. Parser identifies most-moved pieces (up to max_pieces, default 1)
8. Parser returns `PieceTrajectory` objects
9. Controller limits trajectories to `max_exploration_depth` (default 2 moves)
10. Controller calls `BoardModel.set_positional_plans()` with trajectories
11. `BoardModel` emits `positional_plan_changed` signal
12. `ChessboardWidget` observes signal and renders trajectory lines
13. Board hides arrows when trajectories are active

## Manual Analysis System

### Analysis Lines

Each analysis line (`AnalysisLine` dataclass) contains:
- `multipv`: Line number (1-based, 1 = best line)
- `centipawns`: Evaluation in centipawns
- `is_mate`: True if mate score
- `mate_moves`: Mate moves (positive for white, negative for black)
- `depth`: Current search depth
- `pv`: Principal variation as space-separated moves (e.g., "Nf3 d5 Nc3")
- `nps`: Nodes per second (-1 if not available)
- `hashfull`: Hash table usage 0-1000 (-1 if not available)

### MultiPV Support

The system supports analyzing an arbitrary number of candidate moves simultaneously:
- User can add/remove analysis lines (unlimited number of lines)
- Each line is analyzed independently by the engine
- Lines are sorted by evaluation (best first)
- UI displays all active lines with distinct styling
- **Board integration**: Only PV1, PV2, and PV3 are integrated with board visualization (arrows)
- **Trajectory exploration**: Only PV1-PV3 support piece trajectory exploration
- Additional PV lines (PV4, PV5, etc.) are displayed in the UI but do not have board arrows or trajectory visualization

### Position Updates

Position updates are debounced to prevent excessive engine restarts:
- 100ms debounce delay (configurable)
- Only updates if FEN actually changes
- Clears old lines before updating position
- Filters stale updates using expected FEN tracking
- Engine thread updates position without restart (efficient)

**Bestmove Handling**:
- Uses infinite search (`go infinite`) when depth=0 and movetime=0 (default configuration)
- Ignores `bestmove` messages (similar to evaluation service)
- `bestmove` messages only occur after `stop` command or when movetime expires
- Position updates handle restarting the search when needed
- No automatic restart on `bestmove` (infinite search never completes naturally)

**Race Condition Prevention**:
- Thread uses `_search_just_started` flag and `_search_start_time` timestamp for tracking search state
- Flags are cleared only after search is established (depth >= 1 or 2+ info lines received after 100ms elapsed)
- Prevents handling stale messages from previous searches

**Update Throttling**:
- Engine thread throttles `line_update` signal emissions using `update_interval_ms` (default: 100ms, configurable in config.json)
- Updates are only emitted if at least `update_interval_ms` milliseconds have passed since last update for that MultiPV line
- Pending updates are stored in `_pending_updates` and the latest update is emitted when throttling period expires
- Prevents excessive signal emissions when engines send many info lines rapidly (some engines can send 50-100+ info lines per second)
- Without throttling, each info line would trigger: signal emission → model update → controller processing (PV parsing, BoardModel updates, trajectory parsing) → board redraws
- The view also has its own debounce timer, but controller work (including board updates) happens on every signal
- Configurable via `ui.panels.detail.manual_analysis.update_interval_ms` in config.json

## Piece Trajectory Exploration System

### Overview

The trajectory exploration feature visualizes how pieces move through engine-recommended sequences by:
- Parsing PV strings to extract piece movements
- Identifying the most-moved pieces (up to 3)
- Displaying colored trajectory lines on the chessboard
- Showing numbered markers at each square the piece visits
- Hiding normal arrows when trajectories are active

### PieceTrajectory Data Structure

```python
@dataclass
class PieceTrajectory:
    piece_type: str          # 'p', 'r', 'n', 'b', 'q', 'k'
    piece_color: bool        # True for white, False for black
    squares: List[int]        # List of square indices the piece visits
    ply_indices: List[int]    # Ply indices when piece moves to each square
    starting_square: int     # Starting square (for marker display)
```

### Configuration

Trajectory exploration is configured via:
- **Active PV Plan**: Which PV line to explore (0 = none, 1-3 = PV1-PV3). Note: Only PV1-PV3 support trajectory exploration, even if more PV lines are being analyzed.
- **Max Pieces**: Maximum number of pieces to track (1-3, default: 1)
- **Max Depth**: Maximum moves to show in trajectory (2-4, default: 2)
- **Min Moves**: Minimum moves required for a trajectory (default: 2)

Settings are stored in `user_settings.json` under `manual_analysis`:
```json
{
  "max_pieces_to_explore": 1,
  "max_exploration_depth": 2
}
```

## PV Plan Parsing Algorithm

### Overview

The `PvPlanParserService.extract_plan()` method parses PV strings and extracts piece trajectories:

1. **Parse PV Moves**: Converts space-separated move strings to `chess.Move` objects
2. **Track Piece Movements**: For each move, identify which piece moved and where
3. **Find Most-Moved Pieces**: Select pieces that move most frequently (up to max_pieces)
4. **Create Trajectories**: Build `PieceTrajectory` objects with square sequences

### Piece Identification

The algorithm handles complex piece identification scenarios:

**Unique Pieces (King, Queen)**:
- Only one per side, identified by type and color
- Starting square found by searching initial position

**Non-Unique Pieces (Pawns, Rooks, Bishops, Knights)**:
- Multiple per side, identified by type, color, and starting square
- Starting square determined by tracing piece position through moves
- Handles cases where pieces of same type are on different files/ranks

**Promoted Pieces**:
- Tracks pawn promotions separately
- Promotion square becomes the piece's "starting square"
- Subsequent moves of promoted piece are tracked

**Piece Tracking Logic**:
1. For each move in PV, determine if it's for the side being tracked
2. Get piece from `from_square` in board state before move
3. Check if piece is already being tracked:
   - Look for tracked piece currently on `from_square`
   - Check if `from_square` appears in any existing trajectory
   - For unique pieces, check if any piece of same type/color is tracked
4. If not tracked, find starting square:
   - For unique pieces: search initial position
   - For non-unique: trace position through previous moves
   - For promoted pieces: use promotion square
5. Add move to trajectory (append `to_square` and ply index)

### Most-Moved Piece Selection

After tracking all piece movements:
1. Count moves per piece (excluding starting position)
2. Filter pieces with at least `min_moves_for_plan` moves (default: 2)
3. Deduplicate pieces:
   - Unique pieces: use (type, color) as key
   - Non-unique pieces: use (type, color, starting_square) as key
   - If same piece tracked multiple times, keep trajectory with most moves
4. Sort by move count (descending)
5. Return top `max_pieces` trajectories

### Trajectory Limiting

After extraction, trajectories are limited to `max_exploration_depth`:
- Truncates `squares` and `ply_indices` lists
- Only includes trajectories that still have at least `min_moves_for_plan` moves after limiting
- This allows users to focus on near-term piece movements

## Integration with Board Visualization

### BoardModel Integration

`BoardModel` stores and manages positional plans:
- `positional_plans`: List of `PieceTrajectory` objects
- `active_pv_plan`: Which PV is being explored (0 = none, 1-3 = PV1-PV3). Only PV1-PV3 support trajectory exploration.
- `set_positional_plans()`: Updates plans and emits signal
- `positional_plan_changed` signal: Notifies views of changes

### ChessboardWidget Rendering

`ChessboardWidget` renders trajectory lines:
- Observes `BoardModel.positional_plan_changed` signal
- For each trajectory, draws colored line connecting squares
- Displays numbered markers at each square (showing move order)
- Uses distinct colors for each trajectory (matches PV line colors)
- Hides normal arrows when trajectories are active (via `hide_other_arrows_during_plan_exploration`)

### Arrow Visibility Management

When trajectory exploration is active:
- `BoardModel.set_active_pv_plan()` is called with PV number (1-3, only PV1-PV3 support exploration)
- Board automatically hides arrows for the active PV plan
- Other arrows (e.g., PV2 arrow when exploring PV1) remain visible
- When exploration is disabled, arrows are restored

## MultiPV Support

### Line Management

The system supports an arbitrary number of analysis lines:
- **PV1**: Best line (always available)
- **PV2**: Second-best line (optional)
- **PV3**: Third-best line (optional)
- **PV4, PV5, etc.**: Additional lines (optional, unlimited)

**Board Integration Limitation**: Only PV1, PV2, and PV3 are integrated with board visualization:
- Only these three lines have arrows displayed on the chessboard
- Only these three lines support piece trajectory exploration
- Additional PV lines (PV4+) are displayed in the UI but do not have board integration

### Adding/Removing Lines

- User clicks "Add Line" button to increase MultiPV (unlimited)
- User clicks "Remove Line" button to decrease MultiPV
- Controller calls `set_multipv()` which:
  - Updates model (filters/creates lines immediately)
  - Updates service thread (restarts analysis with new MultiPV)
  - UI updates reactively via signals

### Line Updates

Each line is updated independently:
- Engine sends separate info for each MultiPV line
- Controller updates corresponding `AnalysisLine` in model
- View displays all lines with distinct styling
- Board shows arrows only for PV1, PV2, PV3 (if those lines exist)

## Integration with Evaluation Bar

The manual analysis system can provide data for the evaluation bar:
- When evaluation bar is visible and manual analysis is running, `EvaluationController` switches to use manual analysis data
- `EvaluationController` observes `ManualAnalysisModel.analysis_changed` signal
- Updates `EvaluationModel` from best line (PV1) evaluation
- When manual analysis stops, evaluation bar switches back to evaluation engine

## Configuration

Manual analysis is configured in `config.json` under `ui.panels.detail.manual_analysis`:

```json
{
  "manual_analysis": {
    "max_depth": null,
    "max_threads": null,
    "multipv1_indicator": {
      "enabled": true,
      "width": 4
    },
    "multipv2_indicator": {
      "enabled": true,
      "width": 4
    },
    "multipv3_indicator": {
      "enabled": true,
      "width": 4
    },
    "statistics": {
      "enabled": true,
      "position": "top",
      "show_nps": true,
      "show_hash": true,
      "show_time": true
    },
    "trajectory_highlight": {
      "enabled": true,
      "font_weight": "bold",
      "background_alpha": 0.3
    },
    "pv_hover": {
      "enabled": true,
      "hover_delay_ms": 50
    }
  }
}
```

Trajectory visualization is configured in `ui.panels.main.board.positional_plans`:

```json
{
  "positional_plans": {
    "min_moves_for_plan": 2,
    "use_straight_lines": false,
    "trajectory": {
      "color": [255, 200, 0],
      "width": 3
    },
    "trajectory_2": {
      "color": [0, 255, 200],
      "width": 3
    },
    "trajectory_3": {
      "color": [200, 0, 255],
      "width": 3
    },
    "numbered_markers": {
      "enabled": true,
      "size": 16
    }
  }
}
```

## Error Handling

### Engine Errors

- Engine process failures: Emitted via `error_occurred` signal
- Controller attempts automatic restart after 1 second delay
- If restart fails, analysis stops and UI resets

### Stale Updates

- Controller tracks expected FEN for each position update
- Updates from previous positions are filtered out
- Prevents race conditions when navigating quickly

### Invalid Moves

- PV parsing stops at first invalid move
- Invalid moves in PV are handled gracefully (trajectory extraction continues with valid moves)
- Board arrows are cleared if PV move cannot be parsed

## Code Location

Implementation files:

- `app/controllers/manual_analysis_controller.py`: Controller orchestration
- `app/models/manual_analysis_model.py`: Analysis state model
- `app/services/manual_analysis_engine_service.py`: Engine service (see `engine_implementation.md`)
- `app/services/pv_plan_parser_service.py`: PV parsing and trajectory extraction
- `app/views/detail_manual_analysis_view.py`: UI view and display
- `app/models/board_model.py`: Positional plans storage
- `app/views/chessboard_widget.py`: Trajectory line rendering
- `app/config/config.json`: Configuration under `ui.panels.detail.manual_analysis` and `ui.panels.main.board.positional_plans`

## Related Documentation

- **Engine Implementation**: See `engine_implementation.md` for UCI communication, engine services, and threading model
- **PV Hover Board Preview**: See `pv_hover_board_preview.md` for miniature board preview on PV hover

