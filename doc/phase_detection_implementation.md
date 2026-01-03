# CARA - Phase Detection and Endgame Classification Implementation

## Overview

CARA implements a three-phase game classification system (Opening, Middlegame, Endgame) based on chess theory and material composition. The phase detection logic is implemented in `app/services/game_summary_service.py` and provides game phase boundaries and endgame type classification.

## Architecture

The phase detection system follows a **stateless service pattern**:

- **GameSummaryService**: Stateless service that calculates phase boundaries and endgame classification from move data. Accepts configuration and optional `MoveClassificationModel` for assessment thresholds. Returns `GameSummary` objects with calculated statistics.

- **GameSummaryController**: Orchestrates summary calculations by observing `GameModel` and `MovesListModel` changes. Calls `GameSummaryService.calculate_summary()` when games are analyzed and emits signals for view updates.

- **Integration**: The service receives `MoveData` instances from `MovesListModel` (which contains piece counts, captures, and assessments). Phase detection results are used by views for statistics display, evaluation graphs, and game highlights.

### Phase Boundaries

The game is divided into three phases:

- **Opening**: Initial phase involving development and opening theory
- **Middlegame**: Middle phase where tactical and strategic play dominates
- **Endgame**: Final phase characterized by reduced material and specific endgame patterns

Phase boundaries are determined at the game level (same for both players) and stored as move numbers:

- `opening_end`: Move number where the opening phase ends
- `middlegame_end`: Move number where the middlegame phase ends (endgame begins)

### Calculation Process

The phase detection process:

1. `GameSummaryService.calculate_summary()` receives move data and total move count
2. `_determine_phase_boundaries()` calculates `opening_end` and `middlegame_end` using opening detection and endgame detection logic
3. For endgame classification, all moves from `middlegame_end` onwards are evaluated to find the most specific endgame type (see "Endgame Type Selection" in Implementation Details)
4. Phase statistics are calculated for each player based on these boundaries

## Opening Phase Detection

### Opening End Detection Logic

The opening phase ends when one of the following conditions is met:

1. **Last Book Move Detection**
   - Scans all moves to find the last move classified as "Book Move" (from polyglot opening book)
   - Checks both white and black moves
   - Tracks the highest move number with a book move

2. **First Non-Pawn Capture Detection**
   - Scans all moves to find the first capture of a non-pawn piece (rook, knight, bishop, or queen)
   - Checks both white and black captures
   - Uses the `white_capture` and `black_capture` fields in MoveData

3. **Opening End Calculation**
   - If a non-pawn capture exists:
     - Opening ends at: `max(last_book_move_number + 1, first_non_pawn_capture_move_number)`
   - If no non-pawn capture exists:
     - Opening ends at: `opening_moves` (configurable threshold, default 15)

### Rationale

This approach respects opening theory:

- If a position is still in the opening book, it remains in the opening phase
- Non-pawn captures typically indicate the transition from opening to middlegame
- The maximum of these two ensures both conditions are satisfied

## Middlegame Phase Detection

### Middlegame End Detection Logic

The middlegame phase ends when an endgame is detected. The system scans moves sequentially and stops at the first move that matches any endgame classification rule.

### Endgame Detection Process

For each move in the game:

1. `_classify_endgame_type()` is called with the move's piece counts
2. If the position matches any endgame rule, `middlegame_end` is set to that move number
3. The scan stops at the first match (any endgame type triggers the transition)

## Endgame Classification System

### Classification Method

The `_classify_endgame_type()` method analyzes piece counts from MoveData to determine the specific endgame type. It uses a hierarchical rule system where more specific rules are checked before general ones.

### Material Calculation

Piece values used for material calculations:

- Queen: 9 points
- Rook: 5 points
- Bishop: 3 points
- Knight: 3 points
- Pawn: 1 point (not included in non-pawn material)

Non-pawn material is calculated as:

- `w_non_pawn = w_q * 9 + w_r * 5 + w_b * 3 + w_n * 3`
- `b_non_pawn = b_q * 9 + b_r * 5 + b_b * 3 + b_n * 3`

Minor pieces are counted as:

- `w_minors = w_b + w_n`
- `b_minors = b_b + b_n`


## Endgame Classification Rules

The following rules are checked in order of specificity (most specific first). Each rule returns immediately when matched, so order is critical. See "Rule Hierarchy and Order of Application" section for the complete ordered list.

### Rule 1: Pawn-Only Endgame
**Priority**: Highest | **Returns**: "Pawn"

**Conditions**: Both sides have no queens, rooks, bishops, or knights. Only pawns remain (possibly none).

### Rule 2: Minor Piece Endgame
**Priority**: High | **Returns**: "Minor Piece"

**Conditions**: No queens or rooks. Each side has ≤ 1 minor piece. Total non-pawn material ≤ 6 points per side.

### Rule 2.75: Two Minor Piece Endgame
**Priority**: High | **Returns**: "Two Minor Piece"

**Conditions**: No queens or rooks. Each side has exactly 2 minor pieces (any combination: 2 bishops, 2 knights, or 1 bishop + 1 knight). Total non-pawn material ≤ 6 points per side.

### Rule 2.95: Rook + Two Minor Piece Endgame (Symmetric)
**Priority**: High | **Returns**: "Rook + Two Minor Piece"

**Conditions**: No queens. Exactly 1 rook per side. Exactly 2 minor pieces per side (any combination). Total non-pawn material ≤ 11 points per side.

### Rule 2.97: Rook vs Rook (Unequal Minors) Endgame
**Priority**: High | **Returns**: "Rook vs Rook (Unequal Minors)"

**Conditions**: No queens. Exactly 1 rook per side. One side has exactly 2 minor pieces, the other has exactly 1 minor piece. Material thresholds: side with 2 minors ≤14 points, side with 1 minor ≤10 points.

### Rule 2.5: Rook vs Minor Piece Endgame
**Priority**: Medium-High | **Returns**: "Rook vs Minor Piece"

**Conditions**: No queens. One side has exactly 1 rook, the other has no rooks but exactly 1 minor piece. Total non-pawn material ≤ 8 points per side.

### Rule 3: Rook Endgame
**Priority**: Medium | **Returns**: "Rook"

**Conditions**: No queens. At least one rook remains. Each side has ≤ 1 minor piece. Total non-pawn material ≤ 10 points per side.

### Rule 3.25: Double Rook Endgame
**Priority**: Medium | **Returns**: "Double Rook"

**Conditions**: No queens. Exactly 2 rooks per side. Each side has ≤ 1 minor piece. Total non-pawn material ≤ 15 points per side.

### Rule 3.5: Rook + Minor Piece Endgame
**Priority**: Medium | **Returns**: "Rook + Minor Piece"

**Conditions**: No queens. At least one rook remains. Each side has ≤ 1 minor piece. Total non-pawn material ≤ 13 points per side.

### Rule 3.75: Heavy Piece Endgame (Symmetric)
**Priority**: Medium | **Returns**: "Heavy Piece"

**Conditions**: At least one queen and one rook per side. Each side has ≤ 1 minor piece. Symmetric minors (both sides have the same minor count). Total non-pawn material ≤ 15 points per side.

### Rule 3.7: Asymmetric Heavy Piece Endgame
**Priority**: Medium | **Returns**: "Asymmetric Heavy Piece"

**Conditions**: At least one queen per side. Each side has ≤ 1 minor piece. Either: (1) Both sides have rooks with asymmetric minors (one side has 0 minors, the other ≤1 minor) - thresholds: no minors ≤14 points, ≤1 minor ≤17 points; or (2) Only one side has rooks - queen only (no rooks) ≤12 points, queen + rook ≤14 points (no minors) or ≤17 points (with minor).

### Rule 4: Queen Endgame
**Priority**: Medium | **Returns**: "Queen"

**Conditions**: At least one queen remains. No rooks. Each side has ≤ 1 minor piece. Total non-pawn material ≤ 12 points per side.

### Rule 4.5: Queen + Two Minor Piece Endgame
**Priority**: Medium | **Returns**: "Queen + Two Minor Piece"

**Conditions**: At least one queen per side. No rooks. Exactly 2 minor pieces per side (any combination). Total non-pawn material ≤ 15 points per side.

### Rule 4.75: Strong Material Imbalance Endgame
**Priority**: Medium | **Returns**: "Strong Material Imbalance"

**Conditions**: One side has very low material (≤8 points) while the other side has moderate material (≤30 points).

### Rule 5: Material Threshold Catch-All
**Priority**: Lowest | **Returns**: "Endgame" (if no queens) or "Transitional" (if queens present)

**Conditions**: Regardless of piece types, if non-pawn material ≤ 15 points per side. Only applies if none of the more specific rules above match.

## Rule Hierarchy and Order of Application

The endgame classification rules are checked in the following order (most specific to least specific). This order is critical because rules return immediately when matched, so more specific rules must be checked before general ones:

1. Rule 1: Pawn-Only Endgame
2. Rule 2: Minor Piece Endgame
3. Rule 2.75: Two Minor Piece Endgame
4. Rule 2.95: Rook + Two Minor Piece Endgame (Symmetric)
5. Rule 2.97: Rook vs Rook (Unequal Minors) Endgame
6. Rule 2.5: Rook vs Minor Piece Endgame
7. Rule 3: Rook Endgame
8. Rule 3.25: Double Rook Endgame
9. Rule 3.5: Rook + Minor Piece Endgame
10. Rule 3.75: Heavy Piece Endgame (Symmetric)
11. Rule 3.7: Asymmetric Heavy Piece Endgame
12. Rule 4: Queen Endgame
13. Rule 4.5: Queen + Two Minor Piece Endgame
14. Rule 4.75: Strong Material Imbalance Endgame
15. Rule 5: Material Threshold Catch-All

### Why Order Matters

The order is critical because:

- Rules are checked sequentially and return immediately when matched
- More specific rules must be checked before general ones
- For example, Rule 2.97 (Rook vs Rook with Unequal Minors) must come before Rule 3 (general Rook Endgame) to catch asymmetric cases
- The catch-all (Rule 5) must be last to ensure it only applies when no specific rule matches

## Implementation Details

### Data Requirements

The phase detection system requires MoveData instances with the following fields:

- `move_number`: Move number in the game
- `white_move`, `black_move`: Move notation strings
- `assess_white`, `assess_black`: Move assessments (including "Book Move")
- `white_capture`, `black_capture`: Captured piece letters (p, r, n, b, q)
- `white_queens`, `white_rooks`, `white_bishops`, `white_knights`, `white_pawns`: Piece counts
- `black_queens`, `black_rooks`, `black_bishops`, `black_knights`, `black_pawns`: Piece counts

### Endgame Type Selection Algorithm

After determining `middlegame_end`, the system uses a selection algorithm to classify the endgame phase:

1. Scan all moves from `middlegame_end` onwards
2. For each move, classify its endgame type using `_classify_endgame_type()`
3. Track the most specific type found:
   - If no type found yet, use the first one found
   - If current type is catch-all ("Endgame" or "Transitional") and new type is specific, upgrade to specific
   - If current type is specific and new type is catch-all, keep the specific type
4. This ensures the most specific classification for the entire endgame phase, even if later moves only match the catch-all rule

### Configuration

The following configuration values affect phase detection:

- `opening_moves`: Default threshold for opening end when no non-pawn capture exists (default: 15)
- These are defined in `app/config/config.json` and loaded via `GameSummaryService.__init__()`

## Usage in Game Summary

The phase detection results are used in:

- Game summary statistics display
- Phase-specific accuracy and ACPL calculations
- Endgame type display (e.g., "Endgame (Rook vs Rook (Unequal Minors))")
- Evaluation graph phase transition indicators
