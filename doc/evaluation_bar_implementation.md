# CARA - Evaluation Bar Implementation

## Overview

The Evaluation Bar provides continuous engine analysis of the current chess position, displaying evaluation, depth, and other metrics in real-time. The system supports both dedicated evaluation engines and integration with manual analysis, automatically switching between modes based on user activity. The bar displays evaluation graphically and updates continuously as the engine analyzes deeper.

## Architecture

The evaluation bar system follows a **Model-Controller-Service-Thread** pattern with **dynamic engine switching**:

### Component Responsibilities

**EvaluationController** (`app/controllers/evaluation_controller.py`):
- Orchestrates evaluation operations
- Manages `EvaluationModel` and `EvaluationEngineService`
- Handles position updates with debouncing
- Switches between evaluation engine and manual analysis data
- Manages progress bar updates and status messages
- Suspends/resumes evaluation when manual analysis uses same engine

**EvaluationModel** (`app/models/evaluation_model.py`):
- Stores evaluation state (centipawns, mate, depth)
- Emits `evaluation_changed` and `depth_changed` signals
- Provides normalized evaluation value for bar display
- Updates from evaluation engine or manual analysis data

**EvaluationEngineService** (`app/services/evaluation_engine_service.py`):
- Manages continuous evaluation engine thread
- Handles engine lifecycle (start, stop, suspend, resume)
- Updates position without restarting thread
- Throttles updates to avoid UI flooding

**EvaluationEngineThread** (`app/services/evaluation_engine_service.py`):
- QThread for continuous UCI engine communication
- Runs infinite search (depth=0) for continuous analysis
- Parses UCI info lines for depth, score, PV, NPS, hashfull
- Emits throttled progress updates
- Supports suspension (keeps process alive) and resumption

### Component Interactions

**Evaluation Start Flow**:
1. User navigates to a position or starts evaluation
2. Controller checks if manual analysis is running
3. If manual analysis active, switches to manual analysis data
4. If no manual analysis, gets evaluation engine assignment
5. Controller calls `EvaluationEngineService.start_evaluation()`
6. Service creates or resumes evaluation thread
7. Thread initializes UCI engine and starts infinite search
8. Thread emits progress updates as analysis deepens
9. Controller updates `EvaluationModel` with evaluation data
10. View observes model signals and updates bar display

**Position Update Flow**:
1. User navigates to different position
2. Controller calls `update_position()` with new FEN
3. If using manual analysis, position update is ignored (manual analysis handles it)
4. If using evaluation engine, service updates position in thread
5. Thread stops current search, sets new position, restarts infinite search
6. Thread resets depth tracking and begins new analysis
7. Progress updates resume for new position

**Manual Analysis Integration Flow**:
1. User starts manual analysis
2. Controller detects manual analysis is running
3. Controller calls `_switch_to_manual_analysis()`
4. Controller disconnects from evaluation service signals
5. If same engine, service suspends evaluation (keeps process alive)
6. If different engine, service stops evaluation normally
7. Controller connects to manual analysis model signals
8. Controller updates evaluation model from manual analysis best line
9. When manual analysis stops, controller switches back to evaluation engine

**Evaluation Update Flow**:
1. Engine thread parses UCI info lines during search
2. Thread extracts depth, score, PV, NPS, hashfull
3. Thread applies throttling (update_interval_ms, default 100ms)
4. Thread emits `score_update` signal with evaluation data
5. Service forwards signal to controller
6. Controller updates `EvaluationModel` properties
7. Model emits `evaluation_changed` signal
8. View observes signal and updates bar display

**Progress Bar Update Flow**:
1. Controller receives evaluation update from service
2. Controller formats evaluation value (centipawns or mate)
3. Controller builds status message with depth, eval, threads, NPS, hash, PV
4. Controller updates progress bar:
   - If max_depth > 0: Shows percentage based on depth/max_depth
   - If max_depth = 0: Shows indeterminate (pulsing) mode
5. Progress service displays status and progress bar

**Suspension/Resumption Flow**:
1. When manual analysis starts with same engine:
   - Service calls `suspend()` on thread
   - Thread stops search but keeps run loop alive
   - Process remains initialized and ready
2. When manual analysis stops:
   - Service calls `resume()` on thread
   - Thread verifies process is still alive
   - Thread updates position and restarts search
   - Evaluation resumes seamlessly

## Evaluation Display

### Bar Visualization

The evaluation bar displays:
- **Graphical bar**: Shows evaluation as colored bar (white advantage = positive, black advantage = negative)
- **Scale**: Configurable maximum scale (default: ±10 pawns)
- **Center line**: Solid horizontal line at 0.00 (even position)
- **Division marks**: Dashed horizontal lines at default values of 1, 2, 3, 5, and 10 pawns (both positive and negative)

The division marks help users read the evaluation scale by providing visual reference points. They are drawn as dashed lines across the bar at the specified pawn values, appearing both above the center (white advantage) and below the center (black advantage).

Note: The numeric evaluation value and depth are displayed in the status bar (progress bar), not on the evaluation bar itself.

### Evaluation Formatting

The status bar displays formatted evaluation values:
- **Centipawn scores**: Converted to pawns and formatted (e.g., "+1.50", "-0.75")
- **Mate scores**: Displayed as "M{N}" where N is moves to mate

For the graphical bar display:
- **Normalization**: Values clamped to scale_max for bar visualization
- **Mate handling**: Mate positions use scale_max or -scale_max for bar

### Status Bar Information

The progress bar displays:
- Engine name
- Current depth
- Evaluation value (formatted)
- Thread count (if configured)
- Nodes per second (NPS) if available
- Hash table usage percentage if available
- Principal variation (PV) if available

## Configuration

Evaluation bar is configured via `config.json`:

```json
{
  "ui": {
    "panels": {
      "main": {
        "board": {
          "evaluation_bar": {
            "max_depth_evaluation": 40,
            "update_interval_ms": 100,
            "max_threads": null,
            "scale_max": 10.0,
            "divisions": [1, 2, 3, 5, 10]
          }
        }
      }
    }
  }
}
```

- **max_depth_evaluation**: Maximum depth for progress calculation (0 = infinite/unlimited)
- **update_interval_ms**: Minimum time between UI updates (default: 100ms = 10 updates/sec)
- **max_threads**: Number of CPU threads (null = use engine default)
- **scale_max**: Maximum scale value in pawns (default: 10.0, represents ±10 pawns)
- **divisions**: List of pawn values where division marks are drawn (default: [1, 2, 3, 5, 10])

Engine-specific parameters can be configured per-engine in `engine_parameters.json`:
- `depth`: Maximum search depth (0 = infinite)
- `movetime`: Time limit per move (0 = unlimited)
- `threads`: Number of CPU threads
- Other engine-specific options

## Thread Management

### Persistent Thread

The evaluation thread is persistent:
- Created once when evaluation starts
- Reused for all position updates
- Only destroyed when evaluation stops or engine changes
- Supports suspension/resumption for manual analysis integration

### Position Updates

Position updates do not restart the thread:
- Thread receives new FEN via `_update_position()`
- Thread stops current search, sets new position, restarts search
- No process restart required (efficient)
- Thread tracks last sent FEN to avoid redundant updates

### Suspension/Resumption

When manual analysis uses the same engine:
- Thread is suspended (search stopped, process alive)
- Thread run loop continues but doesn't process search
- When manual analysis stops, thread resumes seamlessly
- No process restart required (fast switching)

## Manual Analysis Integration

The evaluation bar automatically integrates with manual analysis:

- **Automatic switching**: When manual analysis starts, bar uses its data
- **Same engine optimization**: If same engine, evaluation is suspended (not stopped)
- **Different engine**: If different engine, evaluation is stopped normally
- **Seamless transition**: When manual analysis stops, evaluation resumes
- **Data source**: Bar displays best line from manual analysis model

This integration ensures users always see the most relevant evaluation without duplicate engine processes.

## Error Handling

Error handling in evaluation system:

- **Process termination**: Thread detects if engine process dies, emits error
- **Initialization failure**: If UCI initialization fails, emits error
- **Position update failure**: If position update fails, emits error
- **Error recovery**: Controller can restart evaluation on position update if thread is invalid
- **Status display**: Errors are displayed in progress bar status

## Code Locations

- **Controller**: `app/controllers/evaluation_controller.py`
- **Model**: `app/models/evaluation_model.py`
- **Service**: `app/services/evaluation_engine_service.py`
- **View**: `app/views/evaluation_bar_widget.py` (if exists)
- **Configuration**: `app/config/config.json` (ui.panels.main.board.evaluation_bar section)

