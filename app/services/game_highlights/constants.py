"""Constants for game highlight detection."""

# Piece values in centipawns
PIECE_VALUES = {
    "q": 900,
    "r": 500,
    "b": 300,
    "n": 300,
    "p": 100
}

# Central squares
CENTRAL_SQUARES = [
    27, 28, 35, 36,  # d4, d5, e4, e5
    19, 20, 43, 44   # c4, c5, f4, f5
]

# Thresholds
MATERIAL_SACRIFICE_THRESHOLD = 200  # Minimum centipawns for forcing combination
EVALUATION_IMPROVEMENT_THRESHOLD = 100  # Minimum centipawns improvement
EVALUATION_SWING_THRESHOLD = 200  # Minimum centipawns for large swing
MOMENTUM_SHIFT_THRESHOLD = 200  # Minimum centipawns for momentum shift
PAWN_STORM_WINDOW = 4  # Number of moves to check for pawn storm

# Note: CPL thresholds (good_move_max_cpl, inaccuracy_max_cpl, mistake_max_cpl) are now
# obtained from MoveClassificationModel via RuleContext, not from hardcoded constants.
# This allows users to customize thresholds in the UI.

# Material loss thresholds for blundered pieces
BLUNDERED_QUEEN_MIN_LOSS = 800
BLUNDERED_ROOK_MIN_LOSS = 400
BLUNDERED_QUEEN_EVAL_DROP = 300
BLUNDERED_ROOK_EVAL_DROP = 200

# Defensive resource thresholds
DEFENSIVE_THREAT_MIN_CPL = 100  # Minimum CPL for opponent's threat to require unique defense
DEFENSIVE_EVAL_IMPROVEMENT_THRESHOLD = 20  # Maximum evaluation deterioration allowed for defense

