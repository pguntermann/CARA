CARA - Phase Detection and Endgame Classification Implementation

1. Overview

CARA implements a sophisticated three-phase game classification system (Opening, Middlegame, Endgame) based on chess theory and material composition. The phase detection logic is implemented in `app/services/game_summary_service.py` and provides accurate game phase boundaries and detailed endgame type classification.

2. Phase Detection Architecture

2.1 Phase Boundaries

The game is divided into three phases:
- Opening: Initial phase of the game, typically involving development and opening theory
- Middlegame: Middle phase where tactical and strategic play dominates
- Endgame: Final phase characterized by reduced material and specific endgame patterns

Phase boundaries are determined at the game level (same for both players) and stored as move numbers:
- `opening_end`: Move number where the opening phase ends
- `middlegame_end`: Move number where the middlegame phase ends (endgame begins)

2.2 Implementation Flow

The phase detection process follows this flow:

1. `calculate_summary()` is called with a list of moves and total move count
2. `_determine_phase_boundaries()` calculates `opening_end` and `middlegame_end`
3. For endgame classification, all moves from `middlegame_end` onwards are checked
4. The most specific endgame type found is used (specific rules override catch-all)
5. Phase statistics are calculated for each player based on these boundaries

3. Opening Phase Detection

3.1 Opening End Detection Logic

The opening phase ends when one of the following conditions is met:

1. Last Book Move Detection
   - Scans all moves to find the last move classified as "Book Move" (from polyglot opening book)
   - Checks both white and black moves
   - Tracks the highest move number with a book move

2. First Non-Pawn Capture Detection
   - Scans all moves to find the first capture of a non-pawn piece (rook, knight, bishop, or queen)
   - Checks both white and black captures
   - Uses the `white_capture` and `black_capture` fields in MoveData

3. Opening End Calculation
   - If a non-pawn capture exists:
     - Opening ends at: `max(last_book_move_number + 1, first_non_pawn_capture_move_number)`
   - If no non-pawn capture exists:
     - Opening ends at: `opening_moves` (configurable threshold, default 15)

3.2 Rationale

This approach respects opening theory:
- If a position is still in the opening book, it remains in the opening phase
- Non-pawn captures typically indicate the transition from opening to middlegame
- The maximum of these two ensures both conditions are satisfied

4. Middlegame Phase Detection

4.1 Middlegame End Detection Logic

The middlegame phase ends when an endgame is detected. The system scans moves sequentially and stops at the first move that matches any endgame classification rule.

4.2 Endgame Detection Process

For each move in the game:
1. `_classify_endgame_type()` is called with the move's piece counts
2. If the position matches any endgame rule, `middlegame_end` is set to that move number
3. The scan stops at the first match (any endgame type triggers the transition)

5. Endgame Classification System

5.1 Classification Method

The `_classify_endgame_type()` method analyzes piece counts from MoveData to determine the specific endgame type. It uses a hierarchical rule system where more specific rules are checked before general ones.

5.2 Material Calculation

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

5.3 Endgame Type Selection

After determining `middlegame_end`, the system checks all moves from that point onwards to find the most specific endgame type:

1. All moves from `middlegame_end` to the end of the game are evaluated
2. The most specific type found is used (specific rules override catch-all)
3. If a specific type is found, it is kept even if later moves only match the catch-all
4. This ensures the most accurate classification for the endgame phase

6. Endgame Classification Rules

The following rules are checked in order of specificity (most specific first). Each rule returns immediately when matched, so order is critical.

6.1 Rule 1: Pawn-Only Endgame

Priority: Highest (most specific)

Conditions:
- Both sides have no queens, no rooks, no bishops, no knights
- Only pawns remain (possibly none)

Return Value: "Pawn"

Purpose: Identifies pure pawn endgames, the simplest endgame type.

6.2 Rule 2: Minor Piece Endgame

Priority: High

Conditions:
- No queens, no rooks
- Each side has ≤ 1 minor piece (bishop or knight)
- Total non-pawn material ≤ 6 points per side

Return Value: "Minor Piece"

Purpose: Catches basic minor piece endgames (bishop vs knight, single minor vs single minor).

6.3 Rule 2.75: Two Minor Piece Endgame

Priority: High

Conditions:
- No queens, no rooks
- Each side has exactly 2 minor pieces (any combination: 2 bishops, 2 knights, or 1 bishop + 1 knight)
- Total non-pawn material ≤ 6 points per side

Return Value: "Two Minor Piece"

Purpose: Distinguishes two-minor endgames from single-minor endgames. Examples: bishop pair vs bishop pair, knight pair vs knight pair, bishop + knight vs bishop + knight.

6.4 Rule 2.95: Rook + Two Minor Piece Endgame (Symmetric)

Priority: High

Conditions:
- No queens
- Exactly 1 rook per side
- Exactly 2 minor pieces per side (any combination: 2 bishops, 2 knights, or 1 bishop + 1 knight)
- Total non-pawn material ≤ 11 points per side

Return Value: "Rook + Two Minor Piece"

Purpose: Catches symmetric rook + two minor piece endgames. Examples: rook + bishop + knight vs rook + bishop + knight, rook + 2 knights vs rook + 2 knights.

6.5 Rule 2.97: Rook vs Rook (Unequal Minors) Endgame

Priority: High

Conditions:
- No queens
- Exactly 1 rook per side
- One side has exactly 2 minor pieces, the other side has exactly 1 minor piece
- Material thresholds:
  - Side with 2 minors: ≤14 non-pawn points
  - Side with 1 minor: ≤10 non-pawn points

Return Value: "Rook vs Rook (Unequal Minors)"

Purpose: Catches asymmetric rook endgames where one side has two minors and the other has one. Examples: rook + bishop + knight vs rook + knight, rook + two knights vs rook + bishop.

6.6 Rule 2.5: Rook vs Minor Piece Endgame

Priority: Medium-High

Conditions:
- No queens
- One side has exactly 1 rook, the other side has no rooks but exactly 1 minor piece
- Total non-pawn material ≤ 8 points per side

Return Value: "Rook vs Minor Piece"

Purpose: Catches positions where one side has a rook and the other has only a minor piece. Examples: rook + pawns vs bishop + pawns, rook + pawns vs knight + pawns.

6.7 Rule 3: Rook Endgame

Priority: Medium

Conditions:
- No queens
- At least one rook remains on the board
- Each side has ≤ 1 minor piece
- Total non-pawn material ≤ 10 points per side

Return Value: "Rook"

Purpose: General rook endgame catch-all. Examples: rook + bishop vs rook + knight, rook + pawns vs rook + pawns, single rook vs single rook.

6.8 Rule 3.25: Double Rook Endgame

Priority: Medium

Conditions:
- No queens
- Exactly 2 rooks per side
- Each side has ≤ 1 minor piece
- Total non-pawn material ≤ 15 points per side

Return Value: "Double Rook"

Purpose: Identifies double rook endgames specifically. Examples: two rooks vs two rooks, two rooks + one minor vs two rooks + one minor.

6.9 Rule 3.5: Rook + Minor Piece Endgame

Priority: Medium

Conditions:
- No queens
- At least one rook remains
- Each side has ≤ 1 minor piece
- Total non-pawn material ≤ 13 points per side

Return Value: "Rook + Minor Piece"

Purpose: Catches rook + minor piece endgames that don't match Rule 3.25. Examples: rook + bishop vs rook + knight (with pawns), two rooks + one minor vs two rooks + one minor.

6.10 Rule 3.75: Heavy Piece Endgame (Symmetric)

Priority: Medium

Conditions:
- At least one queen per side
- At least one rook per side
- Each side has ≤ 1 minor piece
- Total non-pawn material ≤ 14 points per side

Return Value: "Heavy Piece"

Purpose: Identifies symmetric heavy piece endgames (queen + rook vs queen + rook). Examples: queen + rook vs queen + rook + pawns.

6.11 Rule 3.7: Asymmetric Heavy Piece Endgame

Priority: Medium

Conditions:
- At least one queen per side
- Each side has ≤ 1 minor piece
- Either:
  - Case 1: Both sides have rooks (asymmetric minors)
    - One side has 0 minors, the other has ≤ 1 minor
    - Thresholds: side with no minors ≤14 points, side with ≤1 minor ≤17 points
  - Case 2: Only one side has rooks
    - Side with queen only (no rooks): ≤12 points
    - Side with queen + rook: ≤14 points (no minors) or ≤17 points (with minor)

Return Value: "Asymmetric Heavy Piece"

Purpose: Catches asymmetric heavy piece endgames. Examples: queen + rook vs queen + rook + minor, queen vs queen + rook.

6.12 Rule 4: Queen Endgame

Priority: Medium

Conditions:
- At least one queen remains
- No rooks
- Each side has ≤ 1 minor piece
- Total non-pawn material ≤ 12 points per side

Return Value: "Queen"

Purpose: Identifies queen endgames. Examples: queen + pawns vs queen + pawns, queen + bishop vs queen + knight.

6.13 Rule 4.5: Queen + Two Minor Piece Endgame

Priority: Medium

Conditions:
- At least one queen per side
- No rooks
- Exactly 2 minor pieces per side (any combination: 2 bishops, 2 knights, or 1 bishop + 1 knight)
- Total non-pawn material ≤ 15 points per side

Return Value: "Queen + Two Minor Piece"

Purpose: Catches queen + two minor piece endgames. Examples: queen + 2 bishops vs queen + 2 bishops, queen + bishop + knight vs queen + bishop + knight.

6.14 Rule 5: Material Threshold Catch-All

Priority: Lowest (least specific)

Conditions:
- Regardless of piece types, if non-pawn material ≤ 15 points per side
- Only applies if none of the more specific rules above match

Return Value: "Endgame"

Purpose: Ensures all positions with low material are classified as endgames, even if they don't match specific patterns. This is a safety net for borderline cases.

7. Rule Hierarchy and Order of Application

The rules are checked in the following order (most specific to least specific):

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
14. Rule 5: Material Threshold Catch-All

7.1 Why Order Matters

The order is critical because:
- Rules are checked sequentially and return immediately when matched
- More specific rules must be checked before general ones
- For example, Rule 2.97 (Rook vs Rook with Unequal Minors) must come before Rule 3 (general Rook Endgame) to catch asymmetric cases
- The catch-all (Rule 5) must be last to ensure it only applies when no specific rule matches

8. Implementation Details

8.1 Data Requirements

The phase detection system requires MoveData instances with the following fields:
- `move_number`: Move number in the game
- `white_move`, `black_move`: Move notation strings
- `assess_white`, `assess_black`: Move assessments (including "Book Move")
- `white_capture`, `black_capture`: Captured piece letters (p, r, n, b, q)
- `white_queens`, `white_rooks`, `white_bishops`, `white_knights`, `white_pawns`: Piece counts
- `black_queens`, `black_rooks`, `black_bishops`, `black_knights`, `black_pawns`: Piece counts

8.2 Endgame Type Selection Algorithm

After determining `middlegame_end`, the system uses a smart selection algorithm:

1. Scan all moves from `middlegame_end` onwards
2. For each move, classify its endgame type
3. Track the most specific type found:
   - If no type found yet, use the first one found
   - If current type is catch-all ("Endgame") and new type is specific, upgrade to specific
   - If current type is specific and new type is catch-all, keep the specific type
4. This ensures the most accurate classification for the entire endgame phase

8.3 Configuration

The following configuration values affect phase detection:
- `opening_moves`: Default threshold for opening end when no non-pawn capture exists (default: 15)
- These are defined in `app/config/config.json` and loaded via `GameSummaryService.__init__()`

9. Usage in Game Summary

The phase detection results are used in:
- Game summary statistics display
- Phase-specific accuracy and ACPL calculations
- Endgame type display (e.g., "Endgame (Rook vs Rook (Unequal Minors))")
- Evaluation graph phase transition indicators

10. Future Considerations

Potential improvements:
- Additional endgame types based on chess theory
- Configurable material thresholds
- Position-based endgame detection (beyond material counts)
- Opening phase detection refinements based on ECO codes

