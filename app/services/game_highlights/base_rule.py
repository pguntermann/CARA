"""Base rule interface for game highlight detection rules."""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from app.models.moveslist_model import MoveData


@dataclass
class RuleContext:
    """Context passed to rules during evaluation."""
    move_index: int
    total_moves: int
    opening_end: int
    middlegame_end: int
    prev_move: Optional[MoveData]
    next_move: Optional[MoveData]
    prev_white_bishops: int
    prev_black_bishops: int
    prev_white_knights: int
    prev_black_knights: int
    prev_white_queens: int
    prev_black_queens: int
    prev_white_rooks: int
    prev_black_rooks: int
    prev_white_pawns: int
    prev_black_pawns: int
    prev_white_material: int
    prev_black_material: int
    last_book_move_number: int
    theory_departed: bool
    # Classification thresholds (from MoveClassificationModel or config fallback)
    good_move_max_cpl: int
    inaccuracy_max_cpl: int
    mistake_max_cpl: int
    # Shared state for rules that need cross-move tracking
    shared_state: Dict[str, Any]
    # Full moves list for rules that need to look back (e.g., pawn storm)
    moves: List[MoveData]


@dataclass
class GameHighlight:
    """Represents a game highlight (key moment or fact)."""
    move_number: int  # Primary move number (for multi-move highlights, this is the first move)
    is_white: bool  # True if this is a white move, False if black
    move_notation: str  # Move notation to display (e.g., "12. Nxc3" or "18-19. Rooks were exchanged")
    description: str  # Description text (e.g., "White secured the bishop pair")
    move_number_end: Optional[int] = None  # End move number for multi-move highlights (e.g., "18-19")
    priority: int = 0  # Priority score for sorting (higher = more interesting)
    rule_type: str = ""  # Rule type identifier for deduplication (e.g., "battery", "fork", "decoy")


class HighlightRule(ABC):
    """Abstract base class for all game highlight detection rules.
    
    Each rule evaluates a move in context and returns highlights.
    Rules are independent, testable, and configurable.
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the rule with configuration.
        
        Args:
            config: Rule-specific configuration dictionary.
        """
        self.config = config
        self.enabled = config.get('enabled', True)
        self.name = config.get('name', self.__class__.__name__)
        self.description = config.get('description', '')
    
    @abstractmethod
    def evaluate(self, move: MoveData, context: RuleContext) -> List[GameHighlight]:
        """Evaluate move and return highlights.
        
        Args:
            move: Current move data.
            context: Rule context with move history and state.
        
        Returns:
            List of GameHighlight instances (empty list if no highlights).
        """
        pass
    
    def get_name(self) -> str:
        """Get rule name.
        
        Returns:
            Rule name string.
        """
        return self.name
    
    def get_description(self) -> str:
        """Get rule description.
        
        Returns:
            Rule description string.
        """
        return self.description
    
    def is_enabled(self) -> bool:
        """Check if rule is enabled.
        
        Returns:
            True if rule is enabled, False otherwise.
        """
        return self.enabled

