# CARA - Engine Implementation and Configuration System

## Overview

CARA integrates UCI (Universal Chess Interface) chess engines for position analysis, game evaluation, and manual analysis. The implementation follows a layered architecture with clear separation between UCI protocol communication, engine-specific logic, and configuration management.

## Architecture

### Service Layers

The engine implementation is organized into three main layers:

- **UCI Communication Layer (UCICommunicationService)**
  - Low-level UCI protocol communication
  - Process spawning and management
  - Command sending and response reading
  - Debug logging of all UCI interactions
  - Automatic filtering of zero-value parameters (depth=0, movetime=0)

- **Specialized Engine Services**
  - EvaluationEngineService: Continuous position evaluation for evaluation bar
  - GameAnalysisEngineService: Batch analysis of all moves in a game
  - ManualAnalysisEngineService: Continuous analysis with MultiPV support

- **Configuration Management**
  - EngineParametersService: Persistence of engine-specific parameters
  - EngineConfigurationService: Validation and recommended defaults
  - EngineValidationService: Engine discovery and option parsing

### Threading Model

All engine operations run in separate QThread instances to keep the UI responsive:

- **EvaluationEngineThread**: Runs continuous evaluation for the evaluation bar
- **GameAnalysisEngineThread**: Persistent thread for analyzing multiple positions
- **ManualAnalysisEngineThread**: Runs continuous analysis with MultiPV support

Each thread manages its own UCICommunicationService instance and handles engine lifecycle (spawn, initialize, search, stop, quit).

## UCI Communication Layer

### UCICommunicationService

The UCICommunicationService provides a unified interface for UCI protocol communication:

- **Process Management**
  - `spawn_process()`: Spawns engine process as subprocess
    - Uses binary mode (`text=False`) to avoid Windows text mode blocking issues
    - Uses unbuffered mode (`bufsize=0`) for immediate data availability
    - Initializes binary read buffer for manual line splitting
  - `is_process_alive()`: Checks if process is running
  - `get_process_pid()`: Returns process PID for debugging
  - `cleanup()`: Terminates process and cleans up resources

- **UCI Protocol**
  - `initialize_uci()`: Sends "uci" command and waits for "uciok"
  - `set_option()`: Sets engine options (Threads, Hash, etc.)
  - `set_position()`: Sets position using FEN notation
  - `start_search()`: Starts search with depth/movetime parameters
  - `stop_search()`: Sends "stop" command
  - `quit_engine()`: Sends "quit" command
  - `read_line(timeout)`: Reads a line from engine stdout
    - Uses binary mode with manual line buffering
    - Reads chunks from stdout and buffers them
    - Splits on newline characters (`\n`) to extract complete lines
    - Decodes bytes to UTF-8 strings
    - Implements fast path for already-buffered lines (zero latency)
    - Non-blocking read with timeout support
    - Required timeout parameter ensures responsive behavior

- **Search Command Logic**
  - `start_search(depth=0, movetime=0, **kwargs)`
  - Automatically omits parameters with value 0
  - If both depth and movetime are 0, sends "go infinite"
  - Otherwise builds command: "go depth X movetime Y" (only non-zero params)

- **Debug Support**
  - Module-level debug flags for outbound/inbound/lifecycle events
  - Timestamped console output with thread IDs
  - Identifier strings for tracking different engine instances

### Parameter Filtering

The UCI layer automatically filters out zero-value parameters:

- `depth=0`: Not sent to engine (unlimited depth)
- `movetime=0`: Not sent to engine (unlimited time)
- Both 0: Sends "go infinite" instead
- This ensures engines only receive meaningful constraints

## Engine Configuration System

### Configuration Storage

Engine parameters are stored in `engine_parameters.json` in the app root directory:

```json
{
  "engine_path": {
    "options": [...],  // Parsed engine options from UCI
    "tasks": {
      "evaluation": { "threads": 6, "depth": 40, "movetime": 0, ... },
      "game_analysis": { "threads": 8, "depth": 0, "movetime": 1000, ... },
      "manual_analysis": { "threads": 6, "depth": 0, "movetime": 0, ... }
    }
  }
}
```

- **Common Parameters (per task)**:
  - `threads`: Number of CPU threads (1-512)
  - `depth`: Maximum search depth (0 = unlimited)
  - `movetime`: Maximum time per move in milliseconds (0 = unlimited)

- **Engine-Specific Options**:
  - All other options parsed from engine (Hash, Ponder, MultiPV, etc.)
  - Stored per task for task-specific configuration

### EngineParametersService

Singleton service for managing engine parameter persistence:

- **Singleton Pattern**
  - Single instance across application
  - Thread-safe file operations using locks
  - Cached parameters to avoid repeated file I/O

- **Methods**:
  - `load()`: Loads parameters from engine_parameters.json
  - `save()`: Saves parameters to file
  - `reload()`: Forces reload from disk (for external file changes)
  - `get_task_parameters(engine_path, task)`: Gets parameters for specific task
  - `set_task_parameters(engine_path, task, parameters)`: Sets parameters
  - `set_all_task_parameters(engine_path, tasks_parameters)`: Sets all tasks at once
  - `remove_engine_options(engine_path)`: Removes engine configuration

- **Static Helper**:
  - `get_task_parameters_for_engine(engine_path, task, config)`
  - Loads from engine_parameters.json with fallback to config.json defaults
  - Returns recommended defaults if engine not configured

### EngineConfigurationService

Service for managing recommended defaults and validation:

- **Recommended Defaults (from config.json)**:
  - Evaluation: threads=6, depth=0 (infinite), movetime=0
  - Game Analysis: threads=8, depth=0, movetime=1000
  - Manual Analysis: threads=6, depth=0, movetime=0

- **Validation Rules**:
  - Evaluation: depth and movetime are ignored (WARNING if set) - runs on infinite analysis
  - Game Analysis: movetime required (ERROR if 0), WARNING if both depth and movetime set
  - Manual Analysis: depth and movetime should be 0 (ERROR if >0)

- **ValidationResult**:
  - Contains list of ValidationIssue objects
  - Each issue has severity (ERROR, WARNING, INFO), parameter, message
  - UI dialog shows issues and allows "Save Anyway" or "Cancel"

### Engine Validation and Discovery

EngineValidationService handles engine discovery and option parsing:

- **validate_engine(engine_path, debug_callback=None, save_to_file=True)**:
  - Spawns engine and sends "uci" command
  - Parses "id name", "id author", and "option" lines
  - Stores parsed options to engine_parameters.json if save_to_file=True
  - Returns EngineValidationResult with validation status
  - Optional debug_callback for custom debug message handling

- **refresh_engine_options(engine_path, debug_callback=None, save_to_file=True)**:
  - Re-connects to engine and re-parses options
  - Useful for refreshing defaults or when options may have changed
  - Can update UI without saving to file (save_to_file=False)
  - Optional debug_callback for custom debug message handling

- **Option Parsing**:
  - Parses UCI option strings: "option name Threads type spin default 1 min 1 max 1024"
  - Extracts: name, type (spin/check/combo/string/button), default, min, max, var
  - Stores as structured JSON for UI generation

## Engine Services Implementation

### EvaluationEngineService

Provides continuous position evaluation for the evaluation bar:

- **Purpose**: Real-time evaluation display as user navigates through game
- **Thread**: EvaluationEngineThread (one per engine instance)
- **Configuration**: Reads depth and movetime from engine_parameters.json (but both are ignored)
- **Behavior**:
  - Always uses infinite search (depth=0, movetime=0) regardless of configured values
  - Continuously updates evaluation as engine analyzes
  - Stops when position changes or evaluation is stopped
  - Position updates send: stop → position fen → go infinite
  - Never restarts engine on position changes (only updates position)

- **UCI Protocol**:
  - Initial setup: uci → setoption (all parameters) → isready → position fen → go infinite
  - Position update: stop → position fen → go infinite
  - Uses depth=0 to send "go infinite" command (engine analyzes until stopped)
  - Does not handle "bestmove" to restart search (infinite search never completes)

- **Lifecycle**:
  - `start_evaluation(engine_path, fen)`: Creates thread and starts evaluation
  - `update_position(fen)`: Updates position without restarting thread
  - `stop_evaluation()`: Stops and cleans up thread (non-blocking, cleanup happens asynchronously)
  - `suspend_evaluation()`: Suspends search but keeps engine process alive for reuse
  - `resume(fen)`: Resumes evaluation with new position (requires engine process still alive)

### GameAnalysisEngineService

Analyzes all moves in a game sequentially:

- **Purpose**: Batch analysis of entire game for move quality assessment
- **Thread**: GameAnalysisEngineThread (persistent, reused for all positions)
- **Configuration**: Reads depth and movetime from engine_parameters.json
- **Behavior**:
  - Uses persistent thread to avoid engine restart overhead
  - Analyzes each position with configured depth/movetime
  - Respects configured depth and movetime (even if not recommended)

- **Lifecycle**:
  - `start_engine()`: Creates and starts persistent thread
  - `analyze_position(fen, move_number)`: Queues position for analysis
  - Thread processes queue sequentially
  - `stop_analysis()`: Stops current analysis and clears queue
  - `shutdown()`: Shuts down engine process and thread (non-blocking, cleanup happens asynchronously)
  - `cleanup()`: Calls shutdown to clean up resources

### ManualAnalysisEngineService

Provides continuous analysis with MultiPV support:

- **Purpose**: Manual position analysis with multiple candidate moves
- **Thread**: ManualAnalysisEngineThread (one per engine instance)
- **Configuration**: Reads depth and movetime from engine_parameters.json
- **Behavior**:
  - Supports MultiPV for showing multiple analysis lines
  - Continuously analyzes current position
  - Respects configured depth and movetime (even if not recommended)
  - Throttles UI updates (default: 100ms interval)
  - Implements race condition prevention for position and MultiPV updates

- **Bestmove Handling**:
  - Uses infinite search (`go infinite`) when depth=0 and movetime=0
  - Ignores `bestmove` messages (similar to evaluation service)
  - `bestmove` messages only occur after `stop` command or when movetime expires
  - Position updates handle restarting the search when needed
  - No automatic restart on `bestmove` (infinite search never completes naturally)

- **Race Condition Prevention**:
  - Uses `_search_just_started` flag and `_search_start_time` timestamp for tracking search state
  - Flags are cleared after search is established (depth >= 1 or 2+ info lines after 100ms)
  - Prevents handling stale messages from previous searches

- **Update Throttling**:
  - Engine thread throttles `line_update` signal emissions using `update_interval_ms` (default: 100ms)
  - Updates are only emitted if at least `update_interval_ms` milliseconds have passed since last update for that MultiPV line
  - Pending updates are stored in `_pending_updates` and the latest update is emitted when throttling period expires
  - Prevents excessive signal emissions when engines send many info lines rapidly (some engines can send 50-100+ info lines per second)
  - Without throttling, each info line would trigger: signal emission → model update → controller processing (PV parsing, BoardModel updates, trajectory parsing) → board redraws
  - The view also has its own debounce timer, but controller work (including board updates) happens on every signal
  - Configurable via `config.json` under `ui.panels.detail.manual_analysis.update_interval_ms`

- **Lifecycle**:
  - `start_analysis(engine_path, fen, multipv)`: Creates thread and starts analysis
  - `update_position(fen)`: Updates position without restarting thread
  - `set_multipv(multipv)`: Changes number of analysis lines
  - `stop_analysis(keep_engine_alive=False)`: Stops and cleans up thread
    - If `keep_engine_alive=True`: Stops analysis but keeps engine process alive for reuse by other services
    - If `keep_engine_alive=False`: Normal shutdown, engine process is terminated
    - Shutdown is non-blocking (cleanup happens asynchronously in thread's `finally` block)

## Configuration Flow

### Engine Addition

When a user adds an engine:

1. User selects engine executable in Add Engine dialog
2. `EngineValidationService.validate_engine()` is called with `save_to_file=False`
   - Validates engine is UCI-compliant
   - Parses engine options
   - Does NOT save to engine_parameters.json yet
3. User clicks "Add Engine" button
4. `EngineValidationService.refresh_engine_options()` is called with `save_to_file=True`
   - Re-parses options and saves to engine_parameters.json
5. `EngineConfigurationService.get_recommended_defaults()` is called for each task
6. `EngineParametersService.set_all_task_parameters()` saves recommended defaults
7. Engine is added to EngineModel

### Engine Configuration

When a user configures engine parameters:

1. User opens "Engine Configuration" dialog from engine menu
2. Dialog loads current parameters from engine_parameters.json
3. User modifies parameters in UI (common + engine-specific)
4. User clicks "Save Changes"
5. `EngineConfigurationService.validate_parameters()` validates all tasks
6. If validation issues found, shows dialog with errors/warnings/info
7. User can "Save Anyway" or "Cancel"
8. If saved, `EngineParametersService.set_all_task_parameters()` persists changes

### Engine Usage

When an engine is used for a task:

1. Service/Controller calls `EngineParametersService.get_task_parameters_for_engine()`
2. Service loads parameters from engine_parameters.json
3. If not found, falls back to config.json recommended defaults
4. Service passes parameters to engine thread constructor
5. Thread passes depth and movetime to `UCICommunicationService.start_search()`
6. UCI layer filters out zero values and sends appropriate "go" command

### Engine Shutdown

All engine services use **non-blocking shutdown** to keep the UI responsive:

- **Service shutdown methods** (`stop_analysis()`, `stop_evaluation()`, `shutdown()`):
  - Set flags to stop the thread (`running = False`, `_stop_requested = True`)
  - Send `stop_search()` command to engine
  - Disconnect signals to prevent pending updates
  - Return immediately without waiting for thread completion
  - Thread reference is set to `None` immediately

- **Thread cleanup**:
  - Thread's `run()` method checks stop flags and exits loop naturally
  - Thread's `finally` block handles cleanup automatically:
    - Calls `uci.cleanup()` which sends `quit` and terminates process
    - Cleanup happens asynchronously in background thread
    - No blocking waits on UI thread

- **Engine reuse** (`keep_engine_alive=True`):
  - Manual analysis service supports `stop_analysis(keep_engine_alive=True)`
  - Sets `_keep_engine_alive` flag in thread
  - Thread's `finally` block skips cleanup when flag is set
  - Allows evaluation service to reuse the same engine process
  - Used when switching between manual analysis and evaluation with same engine

## Parameter Application

### Common Parameters

Common parameters (threads, depth, movetime) are applied as follows:

- **Threads**:
  - Set via `set_option("Threads", value)` before search
  - Applied once during engine initialization
  - Confirmed with isready/readyok after all options are set

- **Depth**:
  - Passed to `start_search(depth=value)`
  - UCI layer sends "go depth X" if value > 0
  - Omitted if value is 0

- **Movetime**:
  - Passed to `start_search(movetime=value)`
  - UCI layer sends "go movetime X" if value > 0
  - Omitted if value is 0

### Engine-Specific Options

Engine-specific options are applied during engine initialization:

- Set via `set_option(name, value)` for each option
- Applied after common parameters (Threads, MultiPV)
- All options set with `wait_for_ready=False`
- Single `confirm_ready()` call after all options are set
- This is more efficient than waiting for readyok after each option

## Thread Safety

### Singleton Pattern

EngineParametersService uses singleton pattern with thread safety:

- Class-level `_instance` variable
- `Threading.Lock` for file operations
- All `load()` and `save()` operations are locked
- Ensures consistent state across multiple threads

### Engine Thread Isolation

Each engine thread has its own UCICommunicationService instance:

- No shared state between threads
- Each thread manages its own process
- Thread-safe signal/slot communication with UI
- Proper cleanup on thread termination

## Debug Support

### Debug Flags

Module-level debug flags in UCICommunicationService:

- `_debug_outbound_enabled`: Log all commands sent to engine
- `_debug_inbound_enabled`: Log all responses from engine
- `_debug_lifecycle_enabled`: Log engine lifecycle events (STARTED, STOPPED, QUIT, CRASHED)

### Debug Output

Debug output includes:
- Timestamp with milliseconds
- Identifier string (e.g., "Evaluation", "GameAnalysis-EngineName")
- Thread ID (OS thread ID if available)
- Message content

### Debug Menu

Debug menu items (if `show_debug_menu` is enabled in config.json):
- "Debug UCI Outbound": Toggle outbound command logging
- "Debug UCI Inbound": Toggle inbound response logging
- "Debug UCI Lifecycle": Toggle lifecycle event logging

## Error Handling

### Engine Process Errors

- Process spawn failures: Emitted via `error_occurred` signal
- UCI initialization timeout: Emitted via `error_occurred` signal
- Engine crashes: Logged via lifecycle debug, emitted via `error_occurred` signal
- Process termination: Detected and handled gracefully

### Configuration Errors

- Missing engine_parameters.json: Uses recommended defaults from config.json
- Corrupted JSON: Falls back to defaults, logs warning
- Invalid parameter values: Validated by EngineConfigurationService
- Validation issues: Shown to user in dialog before saving

## Best Practices

### Parameter Configuration

- Always use recommended defaults when adding engines
- Validate parameters before saving
- Respect user overrides even if not recommended
- Never hardcode limits in specialized engine threads

### Engine Usage

- Reuse persistent threads when possible (GameAnalysisEngineThread)
- Clean up threads properly on shutdown
- Handle engine crashes gracefully
- Provide clear error messages to users

### Configuration Management

- Use EngineParametersService singleton for all parameter access
- Always provide fallback to config.json defaults
- Validate parameters before applying
- Persist changes only when user explicitly saves

## File Locations

- **engine_parameters.json**: App root directory
  - Stores engine-specific parameters per task
  - Created automatically when first engine is added
  - Updated when user configures engine parameters

- **config.json**: `app/config/config.json`
  - Contains recommended defaults for each task
  - Contains validation rules
  - Contains UI styling for engine configuration dialog
