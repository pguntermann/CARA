"""Utility for matching and comparing PGN date strings with partial dates."""

from typing import Optional, Tuple
import re


class DateMatcher:
    """Utility class for matching and comparing PGN date strings.
    
    PGN dates can be partial, e.g., "2025.??.??", "2025.11.??", "2025.11.09"
    This class handles parsing, normalization, and comparison of such dates.
    """
    
    @staticmethod
    def parse_date(date_str: str) -> Optional[Tuple[Optional[int], Optional[int], Optional[int]]]:
        """Parse a PGN date string into (year, month, day) tuple.
        
        Args:
            date_str: Date string in format "YYYY.MM.DD", "YYYY.MM.??", "YYYY.??.??", etc.
            
        Returns:
            Tuple of (year, month, day) with None for unknown components, or None if invalid.
        """
        if not date_str or not isinstance(date_str, str):
            return None
        
        # Remove whitespace
        date_str = date_str.strip()
        
        # Split by dot
        parts = date_str.split('.')
        if len(parts) != 3:
            return None
        
        # Parse each component
        year = DateMatcher._parse_component(parts[0])
        month = DateMatcher._parse_component(parts[1])
        day = DateMatcher._parse_component(parts[2])
        
        return (year, month, day)
    
    @staticmethod
    def _parse_component(component: str) -> Optional[int]:
        """Parse a date component (year, month, or day).
        
        Args:
            component: String component, can be "??", "?", or a number.
            
        Returns:
            Integer value if valid, None if unknown/wildcard.
        """
        component = component.strip()
        
        # Wildcards
        if component == "??" or component == "?":
            return None
        
        # Try to parse as integer
        try:
            return int(component)
        except ValueError:
            return None
    
    @staticmethod
    def date_contains(date_str: str, pattern: str) -> bool:
        """Check if a date string contains a pattern (substring match).
        
        Args:
            date_str: Date string to check.
            pattern: Pattern to search for (e.g., "2025" matches "2025.11.09").
            
        Returns:
            True if pattern is found in date string.
        """
        if not date_str or not pattern:
            return False
        return pattern.lower() in date_str.lower()
    
    @staticmethod
    def date_equals(date_str: str, pattern: str) -> bool:
        """Check if a date string equals a pattern (handling wildcards).
        
        Args:
            date_str: Date string to check.
            pattern: Pattern to match (can contain "??" wildcards).
            
        Returns:
            True if dates match (wildcards in pattern match any value).
        """
        date_parsed = DateMatcher.parse_date(date_str)
        pattern_parsed = DateMatcher.parse_date(pattern)
        
        if date_parsed is None or pattern_parsed is None:
            return False
        
        year1, month1, day1 = date_parsed
        year2, month2, day2 = pattern_parsed
        
        # Compare components (None in pattern matches any value)
        if year2 is not None and year1 != year2:
            return False
        if month2 is not None and month1 != month2:
            return False
        if day2 is not None and day1 != day2:
            return False
        
        return True
    
    @staticmethod
    def date_before(date_str: str, pattern: str) -> bool:
        """Check if a date is before a pattern date.
        
        Args:
            date_str: Date string to check.
            pattern: Pattern date to compare against.
            
        Returns:
            True if date_str is before pattern (conservative comparison for partial dates).
        """
        date_parsed = DateMatcher.parse_date(date_str)
        pattern_parsed = DateMatcher.parse_date(pattern)
        
        if date_parsed is None or pattern_parsed is None:
            return False
        
        year1, month1, day1 = date_parsed
        year2, month2, day2 = pattern_parsed
        
        # Compare year
        if year1 is not None and year2 is not None:
            if year1 < year2:
                return True
            if year1 > year2:
                return False
        elif year1 is None or year2 is None:
            # If either is unknown, can't determine - return False (conservative)
            return False
        
        # Years equal, compare month
        if month1 is not None and month2 is not None:
            if month1 < month2:
                return True
            if month1 > month2:
                return False
        elif month1 is None or month2 is None:
            # If either is unknown, can't determine - return False (conservative)
            return False
        
        # Years and months equal, compare day
        if day1 is not None and day2 is not None:
            return day1 < day2
        elif day1 is None or day2 is None:
            # If either is unknown, can't determine - return False (conservative)
            return False
        
        return False  # Dates are equal
    
    @staticmethod
    def date_after(date_str: str, pattern: str) -> bool:
        """Check if a date is after a pattern date.
        
        Args:
            date_str: Date string to check.
            pattern: Pattern date to compare against.
            
        Returns:
            True if date_str is after pattern (conservative comparison for partial dates).
        """
        date_parsed = DateMatcher.parse_date(date_str)
        pattern_parsed = DateMatcher.parse_date(pattern)
        
        if date_parsed is None or pattern_parsed is None:
            return False
        
        year1, month1, day1 = date_parsed
        year2, month2, day2 = pattern_parsed
        
        # Compare year
        if year1 is not None and year2 is not None:
            if year1 > year2:
                return True
            if year1 < year2:
                return False
        elif year1 is None or year2 is None:
            # If either is unknown, can't determine - return False (conservative)
            return False
        
        # Years equal, compare month
        if month1 is not None and month2 is not None:
            if month1 > month2:
                return True
            if month1 < month2:
                return False
        elif month1 is None or month2 is None:
            # If either is unknown, can't determine - return False (conservative)
            return False
        
        # Years and months equal, compare day
        if day1 is not None and day2 is not None:
            return day1 > day2
        elif day1 is None or day2 is None:
            # If either is unknown, can't determine - return False (conservative)
            return False
        
        return False  # Dates are equal

