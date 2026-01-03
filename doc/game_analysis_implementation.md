# CARA - Game Analysis Implementation

## Overview

The Game Analysis feature analyzes all moves in a chess game using a UCI engine, calculating evaluations, Centipawn Loss (CPL), move assessments, best moves, and material tracking for each position. The system processes moves sequentially, analyzing each position before and after the move to determine move quality. Analysis results can be stored in PGN tags for persistence.

## Architecture

The game analysis system follows a **Controller-Service-Thread** pattern with **persistent engine communication**:

### Component Responsibilities

**GameAnalysisController** (`app/controllers/game_analysis_controller.py`):
- Orchestrates game analysis operations
- Manages `GameAnalysisEngineService` and `MovesListModel`
- Extracts moves from active game
- Processes analysis results and updates move data
- Calculates CPL, assessments, and material tracking
- Handles book move detection
- Manages progress reporting and error handling
- Supports post-game brilliancy refinement

**GameAnalysisEngineService** (`app/services/game_analysis_engine_service.py`):
- Manages persistent engine thread for analyzing multiple positions
- Queues analysis requests for sequential processing
- Handles engine lifecycle (start, stop, cleanup)
- Provides thread interface for signal connections

**GameAnalysisEngineThread** (`app/services/game_analysis_engine_service.py`):
- Persistent QThread for UCI engine communication
- Processes queue of position analysis requests
- Parses UCI info lines for depth, score, PV, MultiPV
- Emits progress updates and completion signals
- Handles MultiPV (PV1, PV2, PV3) extraction

**AnalysisDataStorageService** (`app/services/analysis_data_storage_service.py`):
- Serializes analysis data to JSON
- Compresses and stores data in PGN tag `[CARAAnalysisData "..."]`
- Stores metadata in `[CARAAnalysisInfo "..."]` and checksum in `[CARAAnalysisChecksum "..."]`
- Loads and validates stored analysis data
- Handles corrupted data cleanup

**BookMoveService** (`app/services/book_move_service.py`):
- Detects if moves are in opening book
- Integrates with `OpeningService` for book move detection
- Used to skip best move storage for book moves

**MoveAnalysisService** (`app/services/move_analysis_service.py`):
- Calculates CPL (Centipawn Loss) for moves
- Assesses move quality (Brilliant, Best Move, Good Move, Inaccuracy, Mistake, Blunder)
- Normalizes move notation for comparison
- Detects if played move is in top 3 alternatives

### Component Interactions

**Analysis Start Flow**:
1. User initiates game analysis
2. Controller validates active game and engine assignment
3. Controller extracts moves from game PGN
4. Controller initializes `GameAnalysisEngineService` with engine parameters
5. Service starts persistent engine thread
6. Controller begins analyzing first move

**Move Analysis Flow**:
1. Controller calls `_analyze_next_move()` for current move
2. Controller updates board position to show move being analyzed
3. Controller analyzes position BEFORE move (to get best alternative)
4. Engine thread processes position and emits `analysis_complete` signal
5. Controller stores best move (PV1, PV2, PV3) from position before
6. Controller analyzes position AFTER move (to get evaluation)
7. Engine thread processes position and emits `analysis_complete` signal
8. Controller calculates CPL using `MoveAnalysisService`
9. Controller assesses move quality using configurable thresholds
10. Controller updates `MovesListModel` with evaluation, CPL, assessment, best moves
11. Controller tracks material balance and piece counts
12. Controller moves to next move and repeats

**Progress Reporting Flow**:
1. Engine thread emits `progress_update` signals during analysis
2. Controller tracks progress depth, centipawns, elapsed time
3. Controller uses `QTimer` to emit periodic progress updates
4. Progress service displays move number, estimated remaining time
5. Progress bar shows percentage based on moves completed

**Analysis Completion Flow**:
1. Controller detects all moves analyzed
2. If post-game brilliancy refinement enabled, performs secondary pass
3. Controller sets `is_game_analyzed` flag in `GameModel`
4. If storage enabled, `AnalysisDataStorageService` stores results in PGN tag
5. Controller marks database as unsaved if game was updated
6. Controller emits `analysis_completed` signal

**Error Handling Flow**:
1. Engine thread emits `error_occurred` signal on errors
2. Controller tracks consecutive errors
3. Critical errors (process termination, initialization failure) stop analysis
4. Non-critical errors skip to next move and continue
5. Progress service displays error messages

## Analysis Process

### Move Extraction

The controller extracts moves from the active game's PGN:
- Parses PGN using `chess.pgn.read_game()`
- Iterates through mainline moves
- For each move, stores:
  - Move number, side to move, SAN notation
  - FEN before and after move
  - Board positions (for material calculation)

### Two-Position Analysis

Each move requires analyzing two positions:

1. **Position BEFORE move**:
   - Purpose: Get best alternative move (PV1) and evaluation after playing best move
   - Used for: CPL calculation, best move storage, top 3 detection
   - MultiPV: Always uses MultiPV=3 to get PV1, PV2, PV3

2. **Position AFTER move**:
   - Purpose: Get evaluation after the actual move
   - Used for: CPL calculation, move assessment, material tracking
   - MultiPV: Uses MultiPV=3 to get PV2 and PV3 scores for CPL calculation

### CPL Calculation

CPL (Centipawn Loss) measures how much evaluation is lost by playing a move instead of the best move:

- **Normal positions**: `CPL = eval_after_best_move - eval_after_played_move`
- **Mate positions**: Uses special handling based on mate distance changes
  - If checkmate achieved: CPL = 0 (perfect move)
  - If creating checkmate: CPL reflects mate distance improvement
  - If allowing checkmate: CPL reflects mate distance loss
  - If both positions are mate: CPL reflects mate distance comparison

CPL calculation is handled by `MoveAnalysisService.calculate_cpl()` with proper handling for mate positions and side-to-move perspective.

### Move Assessment

Move quality is assessed using configurable thresholds:

- **Book Move**: Detected via `BookMoveService` (no assessment)
- **Brilliant**: Requires material sacrifice, eval swing, and other criteria
- **Best Move**: CPL ≤ `good_move_max_cpl` (default: 50)
- **Good Move**: CPL ≤ `good_move_max_cpl` (default: 50)
- **Inaccuracy**: CPL ≤ `inaccuracy_max_cpl` (default: 100)
- **Mistake**: CPL ≤ `mistake_max_cpl` (default: 200)
- **Blunder**: CPL > `mistake_max_cpl` (default: 200)

All thresholds are configurable via `MoveClassificationModel` and can be customized in application settings or `config.json`.

### Material Tracking

Material balance is calculated after each move:
- Tracks material count for both sides (using piece values)
- Tracks piece counts (queens, rooks, bishops, knights, pawns)
- Updates `MovesListModel` with material data for each move
- Used for material sacrifice detection in brilliancy assessment

### Best Moves Storage

For each move, the system stores:
- **Best Move (PV1)**: Best alternative from position before move
- **PV2**: Second-best alternative from position before move
- **PV3**: Third-best alternative from position before move
- **Top 3 Detection**: Checks if played move matches any of top 3 alternatives
- **Depth**: Engine depth used for analysis

Book moves do not store best moves (empty strings).

### Post-Game Brilliancy Refinement

Optional secondary pass that re-checks all moves for brilliancy using multi-ply look-ahead for material sacrifice detection. This can catch sacrifices that aren't immediately recaptured:

- Uses `material_sacrifice_lookahead_plies` (default: 3) to look ahead multiple plies
- Re-calculates material sacrifice for each move
- Re-assesses brilliancy with refined material sacrifice values
- Updates assessments if moves are now brilliant

## Configuration

Game analysis is configured via `config.json`:

```json
{
  "game_analysis": {
    "max_depth": 18,
    "time_limit_per_move_ms": 3000,
    "max_threads": 6,
    "progress_update_interval_ms": 500,
    "assessment_thresholds": {
      "good_move_max_cpl": 50,
      "inaccuracy_max_cpl": 100,
      "mistake_max_cpl": 200
    },
    "brilliant_criteria": {
      "min_eval_swing": 50,
      "min_material_sacrifice": 300,
      "max_eval_before": 500,
      "exclude_already_winning": true,
      "material_sacrifice_lookahead_plies": 3
    },
    "store_analysis_results_in_pgn_tag": false
  }
}
```

Engine-specific parameters can be configured per-engine in `engine_parameters.json`:
- `depth`: Maximum search depth
- `movetime`: Time limit per move (milliseconds)
- `threads`: Number of CPU threads
- Other engine-specific options

## Analysis Data Storage

Analysis results can be stored in PGN tags for persistence:

- **Tag**: `[CARAAnalysisData "..."]` - Compressed, base64-encoded JSON
- **Metadata**: `[CARAAnalysisInfo "..."]` - App version and creation datetime
- **Checksum**: `[CARAAnalysisChecksum "..."]` - SHA256 hash for data integrity

Storage format:
- JSON serialization of all `MoveData` fields
- Gzip compression (level 9)
- Base64 encoding for PGN tag compatibility
- Checksum validation on load

If storage is enabled and analysis completes, the system automatically stores results and marks the database as unsaved.

## Code Locations

- **Controller**: `app/controllers/game_analysis_controller.py`
- **Service**: `app/services/game_analysis_engine_service.py`
- **Storage**: `app/services/analysis_data_storage_service.py`
- **Book Moves**: `app/services/book_move_service.py`
- **Move Analysis**: `app/services/move_analysis_service.py`
- **Model Updates**: `app/models/moveslist_model.py` (MoveData class)
- **Configuration**: `app/config/config.json` (game_analysis section)

