CARA - Engine Implementation and Configuration System

1. Overview

CARA integrates UCI (Universal Chess Interface) chess engines for position analysis, game evaluation, and manual analysis. The implementation follows a layered architecture with clear separation between UCI protocol communication, engine-specific logic, and configuration management.

2. Architecture

2.1 Service Layers

The engine implementation is organized into three main layers:

• UCI Communication Layer (UCICommunicationService)
  - Low-level UCI protocol communication
  - Process spawning and management
  - Command sending and response reading
  - Debug logging of all UCI interactions
  - Automatic filtering of zero-value parameters (depth=0, movetime=0)

• Specialized Engine Services
  - EvaluationEngineService: Continuous position evaluation for evaluation bar
  - GameAnalysisEngineService: Batch analysis of all moves in a game
  - ManualAnalysisEngineService: Continuous analysis with MultiPV support

• Configuration Management
  - EngineParametersService: Persistence of engine-specific parameters
  - EngineConfigurationService: Validation and recommended defaults
  - EngineValidationService: Engine discovery and option parsing

2.2 Threading Model

All engine operations run in separate QThread instances to keep the UI responsive:

• EvaluationEngineThread: Runs continuous evaluation for the evaluation bar
• GameAnalysisEngineThread: Persistent thread for analyzing multiple positions
• ManualAnalysisEngineThread: Runs continuous analysis with MultiPV support

Each thread manages its own UCICommunicationService instance and handles engine lifecycle (spawn, initialize, search, stop, quit).

3. UCI Communication Layer

3.1 UCICommunicationService

The UCICommunicationService provides a unified interface for UCI protocol communication:

• Process Management
  - spawn_process(): Spawns engine process as subprocess
  - is_process_alive(): Checks if process is running
  - get_process_pid(): Returns process PID for debugging
  - cleanup(): Terminates process and cleans up resources

• UCI Protocol
  - initialize_uci(): Sends "uci" command and waits for "uciok"
  - set_option(): Sets engine options (Threads, Hash, etc.)
  - set_position(): Sets position using FEN notation
  - start_search(): Starts search with depth/movetime parameters
  - stop_search(): Sends "stop" command
  - quit_engine(): Sends "quit" command

• Search Command Logic
  - start_search(depth=0, movetime=0, **kwargs)
  - Automatically omits parameters with value 0
  - If both depth and movetime are 0, sends "go infinite"
  - Otherwise builds command: "go depth X movetime Y" (only non-zero params)

• Debug Support
  - Module-level debug flags for outbound/inbound/lifecycle events
  - Timestamped console output with thread IDs
  - Identifier strings for tracking different engine instances

3.2 Parameter Filtering

The UCI layer automatically filters out zero-value parameters:

• depth=0: Not sent to engine (unlimited depth)
• movetime=0: Not sent to engine (unlimited time)
• Both 0: Sends "go infinite" instead
• This ensures engines only receive meaningful constraints

4. Engine Configuration System

4.1 Configuration Storage

Engine parameters are stored in engine_parameters.json in the app root directory:

• Structure:
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

• Common Parameters (per task):
  - threads: Number of CPU threads (1-512)
  - depth: Maximum search depth (0 = unlimited)
  - movetime: Maximum time per move in milliseconds (0 = unlimited)

• Engine-Specific Options:
  - All other options parsed from engine (Hash, Ponder, MultiPV, etc.)
  - Stored per task for task-specific configuration

4.2 EngineParametersService

Singleton service for managing engine parameter persistence:

• Singleton Pattern
  - Single instance across application
  - Thread-safe file operations using locks
  - Cached parameters to avoid repeated file I/O

• Methods:
  - load(): Loads parameters from engine_parameters.json
  - save(): Saves parameters to file
  - reload(): Forces reload from disk (for external file changes)
  - get_task_parameters(engine_path, task): Gets parameters for specific task
  - set_task_parameters(engine_path, task, parameters): Sets parameters
  - set_all_task_parameters(engine_path, tasks_parameters): Sets all tasks at once
  - remove_engine_options(engine_path): Removes engine configuration

• Static Helper:
  - get_task_parameters_for_engine(engine_path, task, config)
  - Loads from engine_parameters.json with fallback to config.json defaults
  - Returns recommended defaults if engine not configured

4.3 EngineConfigurationService

Service for managing recommended defaults and validation:

• Recommended Defaults (from config.json):
  - Evaluation: threads=6, depth=0 (infinite), movetime=0
  - Game Analysis: threads=8, depth=0, movetime=1000
  - Manual Analysis: threads=6, depth=0, movetime=0

• Validation Rules:
  - Evaluation: depth and movetime are ignored (WARNING if set) - runs on infinite analysis
  - Game Analysis: movetime required (ERROR if 0), WARNING if both depth and movetime set
  - Manual Analysis: depth and movetime should be 0 (ERROR if >0)

• ValidationResult:
  - Contains list of ValidationIssue objects
  - Each issue has severity (ERROR, WARNING, INFO), parameter, message
  - UI dialog shows issues and allows "Save Anyway" or "Cancel"

4.4 Engine Validation and Discovery

EngineValidationService handles engine discovery and option parsing:

• validate_engine(engine_path, save_to_file=True):
  - Spawns engine and sends "uci" command
  - Parses "id name", "id author", and "option" lines
  - Stores parsed options to engine_parameters.json if save_to_file=True
  - Returns EngineValidationResult with validation status

• refresh_engine_options(engine_path, save_to_file=True):
  - Re-connects to engine and re-parses options
  - Useful for refreshing defaults or when options may have changed
  - Can update UI without saving to file (save_to_file=False)

• Option Parsing:
  - Parses UCI option strings: "option name Threads type spin default 1 min 1 max 1024"
  - Extracts: name, type (spin/check/combo/string/button), default, min, max, var
  - Stores as structured JSON for UI generation

5. Engine Services Implementation

5.1 EvaluationEngineService

Provides continuous position evaluation for the evaluation bar:

• Purpose: Real-time evaluation display as user navigates through game
• Thread: EvaluationEngineThread (one per engine instance)
• Configuration: Reads depth and movetime from engine_parameters.json (but both are ignored)
• Behavior:
  - Always uses infinite search (depth=0, movetime=0) regardless of configured values
  - Continuously updates evaluation as engine analyzes
  - Stops when position changes or evaluation is stopped
  - Position updates send: stop → position fen → go infinite
  - Never restarts engine on position changes (only updates position)

• UCI Protocol:
  - Initial setup: uci → setoption (all parameters) → isready → position fen → go infinite
  - Position update: stop → position fen → go infinite
  - Uses depth=0 to send "go infinite" command (engine analyzes until stopped)
  - Does not handle "bestmove" to restart search (infinite search never completes)

• Lifecycle:
  - start_evaluation(engine_path, fen): Creates thread and starts evaluation
  - update_position(fen): Updates position without restarting thread
  - stop_evaluation(): Stops and cleans up thread

5.2 GameAnalysisEngineService

Analyzes all moves in a game sequentially:

• Purpose: Batch analysis of entire game for move quality assessment
• Thread: GameAnalysisEngineThread (persistent, reused for all positions)
• Configuration: Reads depth and movetime from engine_parameters.json
• Behavior:
  - Uses persistent thread to avoid engine restart overhead
  - Analyzes each position with configured depth/movetime
  - Respects configured depth and movetime (even if not recommended)

• Lifecycle:
  - start_engine(): Creates and starts persistent thread
  - analyze_position(fen, move_number): Queues position for analysis
  - Thread processes queue sequentially
  - stop(): Stops thread and cleans up

5.3 ManualAnalysisEngineService

Provides continuous analysis with MultiPV support:

• Purpose: Manual position analysis with multiple candidate moves
• Thread: ManualAnalysisEngineThread (one per engine instance)
• Configuration: Reads depth and movetime from engine_parameters.json
• Behavior:
  - Supports MultiPV for showing multiple analysis lines
  - Continuously analyzes current position
  - Respects configured depth and movetime (even if not recommended)

• Lifecycle:
  - start_analysis(engine_path, fen, multipv): Creates thread and starts analysis
  - update_position(fen): Updates position without restarting thread
  - update_multipv(multipv): Changes number of analysis lines
  - stop_analysis(): Stops and cleans up thread

6. Configuration Flow

6.1 Engine Addition

When a user adds an engine:

1. User selects engine executable in Add Engine dialog
2. EngineValidationService.validate_engine() is called with save_to_file=False
   - Validates engine is UCI-compliant
   - Parses engine options
   - Does NOT save to engine_parameters.json yet
3. User clicks "Add Engine" button
4. EngineValidationService.refresh_engine_options() is called with save_to_file=True
   - Re-parses options and saves to engine_parameters.json
5. EngineConfigurationService.get_recommended_defaults() is called for each task
6. EngineParametersService.set_all_task_parameters() saves recommended defaults
7. Engine is added to EngineModel

6.2 Engine Configuration

When a user configures engine parameters:

1. User opens "Engine Configuration" dialog from engine menu
2. Dialog loads current parameters from engine_parameters.json
3. User modifies parameters in UI (common + engine-specific)
4. User clicks "Save Changes"
5. EngineConfigurationService.validate_parameters() validates all tasks
6. If validation issues found, shows dialog with errors/warnings/info
7. User can "Save Anyway" or "Cancel"
8. If saved, EngineParametersService.set_all_task_parameters() persists changes

6.3 Engine Usage

When an engine is used for a task:

1. Service/Controller calls EngineParametersService.get_task_parameters_for_engine()
2. Service loads parameters from engine_parameters.json
3. If not found, falls back to config.json recommended defaults
4. Service passes parameters to engine thread constructor
5. Thread passes depth and movetime to UCICommunicationService.start_search()
6. UCI layer filters out zero values and sends appropriate "go" command

7. Parameter Application

7.1 Common Parameters

Common parameters (threads, depth, movetime) are applied as follows:

• Threads:
  - Set via set_option("Threads", value) before search
  - Applied once during engine initialization
  - Confirmed with isready/readyok after all options are set

• Depth:
  - Passed to start_search(depth=value)
  - UCI layer sends "go depth X" if value > 0
  - Omitted if value is 0

• Movetime:
  - Passed to start_search(movetime=value)
  - UCI layer sends "go movetime X" if value > 0
  - Omitted if value is 0

7.2 Engine-Specific Options

Engine-specific options are applied during engine initialization:

• Set via set_option(name, value) for each option
• Applied after common parameters (Threads, MultiPV)
• All options set with wait_for_ready=False
• Single confirm_ready() call after all options are set
• This is more efficient than waiting for readyok after each option

8. Thread Safety

8.1 Singleton Pattern

EngineParametersService uses singleton pattern with thread safety:

• Class-level _instance variable
• Threading.Lock for file operations
• All load() and save() operations are locked
• Ensures consistent state across multiple threads

8.2 Engine Thread Isolation

Each engine thread has its own UCICommunicationService instance:

• No shared state between threads
• Each thread manages its own process
• Thread-safe signal/slot communication with UI
• Proper cleanup on thread termination

9. Debug Support

9.1 Debug Flags

Module-level debug flags in UCICommunicationService:

• _debug_outbound_enabled: Log all commands sent to engine
• _debug_inbound_enabled: Log all responses from engine
• _debug_lifecycle_enabled: Log engine lifecycle events (STARTED, STOPPED, QUIT, CRASHED)

9.2 Debug Output

Debug output includes:
• Timestamp with milliseconds
• Identifier string (e.g., "Evaluation", "GameAnalysis-EngineName")
• Thread ID (OS thread ID if available)
• Message content

9.3 Debug Menu

Debug menu items (if show_debug_menu is enabled in config.json):
• "Debug UCI Outbound": Toggle outbound command logging
• "Debug UCI Inbound": Toggle inbound response logging
• "Debug UCI Lifecycle": Toggle lifecycle event logging

10. Error Handling

10.1 Engine Process Errors

• Process spawn failures: Emitted via error_occurred signal
• UCI initialization timeout: Emitted via error_occurred signal
• Engine crashes: Logged via lifecycle debug, emitted via error_occurred signal
• Process termination: Detected and handled gracefully

10.2 Configuration Errors

• Missing engine_parameters.json: Uses recommended defaults from config.json
• Corrupted JSON: Falls back to defaults, logs warning
• Invalid parameter values: Validated by EngineConfigurationService
• Validation issues: Shown to user in dialog before saving

11. Best Practices

11.1 Parameter Configuration

• Always use recommended defaults when adding engines
• Validate parameters before saving
• Respect user overrides even if not recommended
• Never hardcode limits in specialized engine threads

11.2 Engine Usage

• Reuse persistent threads when possible (GameAnalysisEngineThread)
• Clean up threads properly on shutdown
• Handle engine crashes gracefully
• Provide clear error messages to users

11.3 Configuration Management

• Use EngineParametersService singleton for all parameter access
• Always provide fallback to config.json defaults
• Validate parameters before applying
• Persist changes only when user explicitly saves

12. File Locations

• engine_parameters.json: App root directory
  - Stores engine-specific parameters per task
  - Created automatically when first engine is added
  - Updated when user configures engine parameters

• config.json: app/config/config.json
  - Contains recommended defaults for each task
  - Contains validation rules
  - Contains UI styling for engine configuration dialog

13. Future Enhancements

Potential improvements to the engine implementation:

• Engine option caching: Cache parsed options to avoid re-parsing
• Parameter presets: Allow users to save/load parameter presets
• Engine profiles: Support multiple parameter sets per engine
• Performance monitoring: Track engine performance metrics
• Engine comparison: Compare analysis from multiple engines

