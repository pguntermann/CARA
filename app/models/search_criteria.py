"""Search criteria model for database search functionality."""

from dataclasses import dataclass
from typing import Optional, List, Any
from enum import Enum


class SearchField(Enum):
    """Available search fields."""
    WHITE = "white"
    BLACK = "black"
    WHITE_ELO = "white_elo"
    BLACK_ELO = "black_elo"
    RESULT = "result"
    DATE = "date"
    EVENT = "event"
    SITE = "site"
    ECO = "eco"
    ANALYZED = "analyzed"
    ANNOTATED = "annotated"
    CUSTOM_TAG = "custom_tag"  # For PGN tags not in standard columns


class SearchOperator(Enum):
    """Search operators."""
    # Text operators
    CONTAINS = "contains"
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    IS_EMPTY = "is_empty"
    IS_NOT_EMPTY = "is_not_empty"
    
    # Numeric operators
    EQUALS_NUM = "equals_num"
    NOT_EQUALS_NUM = "not_equals_num"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    
    # Date operators
    DATE_EQUALS = "date_equals"
    DATE_NOT_EQUALS = "date_not_equals"
    DATE_BEFORE = "date_before"
    DATE_AFTER = "date_after"
    DATE_CONTAINS = "date_contains"  # For partial date matching (e.g., "2025" matches "2025.11.09")
    
    # Boolean operators
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"


class LogicOperator(Enum):
    """Logic operators for combining criteria."""
    AND = "and"
    OR = "or"


@dataclass
class SearchCriteria:
    """Represents a single search criterion."""
    field: SearchField
    operator: SearchOperator
    value: Any  # Can be str, int, bool, or None
    logic_operator: Optional[LogicOperator] = None  # AND/OR connector to previous criterion
    custom_tag_name: Optional[str] = None  # For CUSTOM_TAG field
    is_group_start: bool = False  # True if this starts a group
    is_group_end: bool = False  # True if this ends a group
    group_level: int = 0  # Nesting level (0 = top level)


@dataclass
class SearchQuery:
    """Complete search query with all criteria."""
    scope: str  # "active" or "all"
    criteria: List[SearchCriteria]

