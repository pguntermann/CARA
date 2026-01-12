"""Service for formatting PGN text to HTML with colors and styles."""

import re
import io
from typing import Dict, Any, Tuple, List, Optional
from app.services.logging_service import LoggingService


# NAG (Numeric Annotation Glyph) mapping
# Based on PGN standard: https://wimnij.home.xs4all.nl/euwe/NAGS.html
NAG_MEANINGS: Dict[int, str] = {
    0: "null annotation",
    1: "good move",
    2: "poor move",
    3: "very good move",
    4: "very poor move",
    5: "speculative move",
    6: "questionable move",
    7: "forced move",
    8: "singular move",
    9: "worst move",
    10: "drawish position",
    11: "equal chances, quiet position",
    12: "equal chances, active position",
    13: "unclear position",
    14: "White has a slight advantage",
    15: "Black has a slight advantage",
    16: "White has a moderate advantage",
    17: "Black has a moderate advantage",
    18: "White has a decisive advantage",
    19: "Black has a decisive advantage",
    20: "White has a crushing advantage (Black should resign)",
    21: "Black has a crushing advantage (White should resign)",
    22: "White is in zugzwang",
    23: "Black is in zugzwang",
    24: "White has a slight space advantage",
    25: "Black has a slight space advantage",
    26: "White has a moderate space advantage",
    27: "Black has a moderate space advantage",
    28: "White has a decisive space advantage",
    29: "Black has a decisive space advantage",
    30: "White has a slight time (development) advantage",
    31: "Black has a slight time (development) advantage",
    32: "White has a moderate time (development) advantage",
    33: "Black has a moderate time (development) advantage",
    34: "White has a decisive time (development) advantage",
    35: "Black has a decisive time (development) advantage",
    36: "White has the initiative",
    37: "Black has the initiative",
    38: "White has a lasting initiative",
    39: "Black has a lasting initiative",
    40: "White has the attack",
    41: "Black has the attack",
    42: "White has insufficient compensation for material deficit",
    43: "Black has insufficient compensation for material deficit",
    44: "White has sufficient compensation for material deficit",
    45: "Black has sufficient compensation for material deficit",
    46: "White has more than adequate compensation for material deficit",
    47: "Black has more than adequate compensation for material deficit",
    48: "White has a slight center control advantage",
    49: "Black has a slight center control advantage",
    50: "White has a moderate center control advantage",
    51: "Black has a moderate center control advantage",
    52: "White has a decisive center control advantage",
    53: "Black has a decisive center control advantage",
    54: "White has a slight kingside control advantage",
    55: "Black has a slight kingside control advantage",
    56: "White has a moderate kingside control advantage",
    57: "Black has a moderate kingside control advantage",
    58: "White has a decisive kingside control advantage",
    59: "Black has a decisive kingside control advantage",
    60: "White has a slight queenside control advantage",
    61: "Black has a slight queenside control advantage",
    62: "White has a moderate queenside control advantage",
    63: "Black has a moderate queenside control advantage",
    64: "White has a decisive queenside control advantage",
    65: "Black has a decisive queenside control advantage",
    66: "White has a vulnerable first rank",
    67: "Black has a vulnerable first rank",
    68: "White has a well protected first rank",
    69: "Black has a well protected first rank",
    70: "White has a poorly protected king",
    71: "Black has a poorly protected king",
    72: "White has a well protected king",
    73: "Black has a well protected king",
    74: "White has a poorly placed king",
    75: "Black has a poorly placed king",
    76: "White has a well placed king",
    77: "Black has a well placed king",
    78: "White has a very weak pawn structure",
    79: "Black has a very weak pawn structure",
    80: "White has a moderately weak pawn structure",
    81: "Black has a moderately weak pawn structure",
    82: "White has a moderately strong pawn structure",
    83: "Black has a moderately strong pawn structure",
    84: "White has a very strong pawn structure",
    85: "Black has a very strong pawn structure",
    86: "White has poor knight placement",
    87: "Black has poor knight placement",
    88: "White has good knight placement",
    89: "Black has good knight placement",
    90: "White has poor bishop placement",
    91: "Black has poor bishop placement",
    92: "White has good bishop placement",
    93: "Black has good bishop placement",
    94: "White has poor rook placement",
    95: "Black has poor rook placement",
    96: "White has good rook placement",
    97: "Black has good rook placement",
    98: "White has poor queen placement",
    99: "Black has poor queen placement",
    100: "White has good queen placement",
    101: "Black has good queen placement",
    102: "White has poor piece coordination",
    103: "Black has poor piece coordination",
    104: "White has good piece coordination",
    105: "Black has good piece coordination",
    106: "White has played the opening very poorly",
    107: "Black has played the opening very poorly",
    108: "White has played the opening poorly",
    109: "Black has played the opening poorly",
    110: "White has played the opening well",
    111: "Black has played the opening well",
    112: "White has played the opening very well",
    113: "Black has played the opening very well",
    114: "White has played the middlegame very poorly",
    115: "Black has played the middlegame very poorly",
    116: "White has played the middlegame poorly",
    117: "Black has played the middlegame poorly",
    118: "White has played the middlegame well",
    119: "Black has played the middlegame well",
    120: "White has played the middlegame very well",
    121: "Black has played the middlegame very well",
    122: "White has played the ending very poorly",
    123: "Black has played the ending very poorly",
    124: "White has played the ending poorly",
    125: "Black has played the ending poorly",
    126: "White has played the ending well",
    127: "Black has played the ending well",
    128: "White has played the ending very well",
    129: "Black has played the ending very well",
    130: "White has slight counterplay",
    131: "Black has slight counterplay",
    132: "White has moderate counterplay",
    133: "Black has moderate counterplay",
    134: "White has decisive counterplay",
    135: "Black has decisive counterplay",
    136: "White has moderate time control pressure",
    137: "Black has moderate time control pressure",
    138: "White has severe time control pressure",
    139: "Black has severe time control pressure",
    146: "Novelty",
}

# Mapping from NAG numbers to their symbol equivalents
# These are the common move annotations that have symbol representations
NAG_TO_SYMBOL: Dict[int, str] = {
    1: "!",      # good move
    2: "?",      # poor move
    3: "!!",     # very good move
    4: "??",     # very poor move
    5: "!?",     # speculative move
    6: "?!",     # questionable move
}


def get_nag_text(nag_number: int) -> str:
    """Get NAG text meaning, or fallback format for unknown NAGs.
    
    Args:
        nag_number: The NAG number (e.g., 1, 2, 146)
        
    Returns:
        The NAG meaning if found in NAG_MEANINGS, otherwise "NAG {number}"
    """
    nag_text = NAG_MEANINGS.get(nag_number)
    if not nag_text or not nag_text.strip():
        return f"NAG {nag_number}"
    return nag_text


class PgnFormatterService:
    """Service for formatting PGN notation text to HTML with styling."""
    
    @staticmethod
    def filter_pgn_for_display(
        pgn_text: str,
        show_metadata: bool = True,
        show_comments: bool = True,
        show_variations: bool = True,
        show_annotations: bool = True,
        show_results: bool = True,
        show_non_standard_tags: bool = False
    ) -> str:
        """Filter PGN text based on visibility flags for display purposes.
        
        This method applies filtering to PGN text without modifying the original.
        The filtering is done before formatting to HTML.
        
        Args:
            pgn_text: Plain PGN text string.
            show_metadata: Whether to show metadata tags (headers).
            show_comments: Whether to show comments.
            show_variations: Whether to show variations.
            show_annotations: Whether to show annotations (!, ?, NAGs).
            show_results: Whether to show game results (1-0, 0-1, etc.).
            show_non_standard_tags: Whether to show non-standard tags like [%evp], [%mdl] in comments.
            
        Returns:
            Filtered PGN text ready for formatting.
        """
        if not pgn_text:
            return ""
        
        # Always exclude CARA analysis and annotation tags due to their length (even if metadata is shown)
        filtered_text = PgnFormatterService._remove_cara_tags(pgn_text)
        
        if not show_metadata:
            filtered_text = PgnFormatterService._remove_metadata_tags(filtered_text)
        
        if not show_comments:
            filtered_text = PgnFormatterService._remove_comments(filtered_text)
        elif not show_non_standard_tags:
            # If comments are visible but non-standard tags are hidden, remove them from comments
            filtered_text = PgnFormatterService._remove_non_standard_tags(filtered_text)
        
        if not show_variations:
            filtered_text = PgnFormatterService._remove_variations(filtered_text)
        
        if not show_annotations:
            filtered_text = PgnFormatterService._remove_annotations(filtered_text)
        
        if not show_results:
            filtered_text = PgnFormatterService._remove_results(filtered_text)
        
        return filtered_text
    
    @staticmethod
    def _remove_cara_tags(pgn_text: str) -> str:
        """Remove CARA analysis and annotation tags from PGN text.
        
        These tags are always excluded from PGN view due to their length.
        
        Args:
            pgn_text: PGN text with metadata tags.
            
        Returns:
            PGN text without CARA analysis and annotation tags.
        """
        # Remove CARA analysis and annotation tags using regex to handle tags on same line or separate lines
        # Pattern matches: 
        # - [CARAAnalysisData "..."] or [CARAAnalysisInfo "..."] or [CARAAnalysisChecksum "..."]
        # - [CARAAnnotations "..."] or [CARAAnnotationsInfo "..."] or [CARAAnnotationsChecksum "..."]
        # The pattern handles tags that may be on the same line as other tags
        cara_tag_pattern = re.compile(
            r'\[CARA(?:Analysis(?:Data|Info|Checksum)|Annotations(?:Info|Checksum)?)\s+"[^"]*"\]\s*'
        )
        result = cara_tag_pattern.sub('', pgn_text)
        
        # Clean up: remove double spaces that might be left after tag removal
        # But preserve single spaces and newlines to maintain PGN structure
        result = re.sub(r'  +', ' ', result)  # Replace multiple spaces (2+) with single space
        result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)  # Clean up multiple consecutive newlines
        result = re.sub(r' \n', '\n', result)  # Remove trailing spaces before newlines
        
        return result.strip()

    @staticmethod
    def remove_cara_tags(pgn_text: str) -> str:
        """Public helper to remove CARA analysis/annotation tags from PGN text.

        Args:
            pgn_text: PGN text that may include CARA tags.

        Returns:
            PGN text without CARA analysis/annotation tags.
        """
        return PgnFormatterService._remove_cara_tags(pgn_text)

    @staticmethod
    def remove_metadata_tags(pgn_text: str) -> str:
        """Public helper to remove metadata tags from PGN text.

        Args:
            pgn_text: PGN text that may include metadata headers.

        Returns:
            PGN text with metadata tags removed.
        """
        return PgnFormatterService._remove_metadata_tags(pgn_text)
    
    @staticmethod
    def _is_metadata_only_line(line: str) -> bool:
        """Check if a line contains only metadata tags (no move notation).
        
        Metadata tags are in the format [Key "Value"].
        Move notation starts with a small move number and dot (like "1. e4" or "1... e5").
        
        Args:
            line: Line of PGN text to check.
            
        Returns:
            True if line contains only metadata tags, False otherwise.
        """
        line_stripped = line.strip()
        
        if not line_stripped:
            return False
        
        # Check if line has actual metadata tags (not non-standard tags like [%evp])
        # Metadata tags are in format [Key "Value"] where Key starts with letter/digit
        # Non-standard tags are in format [%...] and appear inside comments
        metadata_tag_pattern = re.compile(r'\[([A-Za-z0-9][A-Za-z0-9_]*)\s+"([^"]*)"\]')
        has_metadata_tags = bool(metadata_tag_pattern.search(line_stripped))
        
        if not has_metadata_tags:
            return False
        
        # Check if line has move notation
        # Match move notation: small number (1-999) followed by dot and space or move
        # This excludes dates like "2025.11.01" which have 4-digit years
        has_move_notation = re.search(r'\b([1-9]\d{0,2}|0)\.(?:\.\.| |\w)', line_stripped) is not None
        
        # If it has metadata tags but no move notation, it's metadata-only
        return not has_move_notation
    
    @staticmethod
    def _is_position_inside_metadata_tag(text: str, position: int) -> bool:
        """Check if a character position is inside a metadata tag [Key "Value"].
        
        Args:
            text: PGN text line.
            position: Character position to check.
            
        Returns:
            True if position is inside a metadata tag, False otherwise.
        """
        # Find all metadata tags in the line
        # Pattern matches: [Key "Value"] where Key starts with letter/digit and Value is in quotes
        metadata_pattern = re.compile(r'\[([A-Za-z0-9][A-Za-z0-9_]*)\s+"([^"]*)"\]')
        
        for match in metadata_pattern.finditer(text):
            # Check if position is between the opening [ and closing ]
            if match.start() <= position < match.end():
                return True
        
        return False
    
    @staticmethod
    def _apply_regex_excluding_metadata(text: str, pattern: re.Pattern, replacement: str = '') -> str:
        """Apply regex substitution to text, excluding matches inside metadata tags.
        
        Args:
            text: Text to process.
            pattern: Compiled regex pattern to match.
            replacement: Replacement string (default empty string for removal).
            
        Returns:
            Text with regex substitutions applied, excluding metadata tag content.
        """
        result = []
        last_pos = 0
        
        # Find all matches
        for match in pattern.finditer(text):
            match_start = match.start()
            match_end = match.end()
            
            # Check if this match is inside a metadata tag
            if PgnFormatterService._is_position_inside_metadata_tag(text, match_start):
                # This match is inside a metadata tag - preserve it by including it in the result
                # Add text up to and including this match (preserving it)
                result.append(text[last_pos:match_end])
                last_pos = match_end
                continue
            
            # Add text before the match (this includes any skipped matches inside metadata)
            result.append(text[last_pos:match_start])
            
            # Add replacement (or skip if removing)
            if replacement:
                result.append(replacement)
            
            last_pos = match_end
        
        # Add remaining text
        result.append(text[last_pos:])
        
        return ''.join(result)
    
    @staticmethod
    def _remove_metadata_tags(pgn_text: str) -> str:
        """Remove metadata tags (headers) from PGN text.
        
        Args:
            pgn_text: PGN text with metadata tags.
            
        Returns:
            PGN text without metadata tags (only moves).
        """
        # Pattern to match metadata tags: [Key "Value"] where Key starts with letter/digit
        # This matches standard PGN metadata tags like [Event "..."], [Site "..."], etc.
        # It does NOT match non-standard tags like [%eval ...] which appear in comments
        metadata_tag_pattern = re.compile(r'\[([A-Za-z0-9][A-Za-z0-9_]*)\s+"([^"]*)"\]')
        
        # Remove metadata tags from the entire text (not just line-by-line)
        # This handles cases where multiple tags are on one line or tags appear inline with moves
        result = metadata_tag_pattern.sub('', pgn_text)
        
        # Clean up multiple consecutive spaces (but preserve newlines)
        # Replace multiple spaces/tabs with single space, but keep newlines
        result = re.sub(r'[ \t]+', ' ', result)
        
        # Split into lines and clean up
        lines = result.split('\n')
        filtered_lines = []
        
        for line in lines:
            stripped = line.strip()
            # Skip empty lines
            if stripped:
                filtered_lines.append(line)
        
        # Join lines back together
        result = '\n'.join(filtered_lines)
        
        # Clean up multiple consecutive newlines
        result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)
        
        return result.strip()
    
    @staticmethod
    def _remove_comments(pgn_text: str) -> str:
        """Remove comments from PGN text.
        
        Args:
            pgn_text: PGN text with comments.
            
        Returns:
            PGN text without comments.
        Note: Preserves metadata tags - does not process metadata-only lines.
        """
        result_chars: List[str] = []
        in_comment = False
        depth = 0
        
        for char in pgn_text:
            if char == '{':
                depth += 1
                in_comment = True
                continue
            if char == '}' and in_comment:
                depth -= 1
                if depth <= 0:
                    in_comment = False
                    depth = 0
                continue
            
            if not in_comment:
                result_chars.append(char)
        
        result_str = ''.join(result_chars)
        # Clean up spaces (preserve newlines)
        result_str = re.sub(r'[ \t]+', ' ', result_str)
        # Remove trailing spaces per line
        lines = result_str.split('\n')
        cleaned_lines = [line.rstrip() for line in lines]
        
        # Remove consecutive empty lines inside move notation
        final_lines = []
        in_move_notation = False
        for i, line in enumerate(cleaned_lines):
            stripped = line.strip()
            if not in_move_notation and stripped and not PgnFormatterService._is_metadata_only_line(line):
                if re.search(r'\b([1-9]\d{0,2}|0)\.(?:\.\.| |\w)', line):
                    in_move_notation = True
            if in_move_notation and not stripped:
                next_non_empty = None
                for j in range(i + 1, len(cleaned_lines)):
                    if cleaned_lines[j].strip():
                        next_non_empty = cleaned_lines[j]
                        break
                if next_non_empty and not PgnFormatterService._is_metadata_only_line(next_non_empty):
                    if re.search(r'\b([1-9]\d{0,2}|0)\.(?:\.\.| |\w)', next_non_empty) or any(c in next_non_empty for c in '()'):
                        continue
            final_lines.append(line)
        
        result_str = '\n'.join(final_lines)
        result_str = re.sub(r'\n\s*\n\s*\n+', '\n\n', result_str)
        return result_str.strip()
    
    @staticmethod
    def _remove_comments_preserving_lines(lines: list, line_indices: list) -> list:
        """Remove comments from lines while preserving line structure.
        
        This method processes lines individually, removing comments but preserving
        the original line structure. When a comment spans multiple lines, empty lines
        are left in place to maintain structure.
        
        Args:
            lines: List of lines to process.
            line_indices: Original line indices (for debugging, not currently used).
            
        Returns:
            List of processed lines with comments removed.
        """
        result_lines = []
        in_comment = False
        comment_depth = 0
        
        for line in lines:
            if not in_comment:
                # Not currently in a comment - process this line
                line_result = []
                i = 0
                while i < len(line):
                    if line[i] == '{':
                        # Start of comment
                        comment_depth = 1
                        in_comment = True
                        i += 1
                        # Find matching closing brace on this line
                        while i < len(line) and comment_depth > 0:
                            if line[i] == '{':
                                comment_depth += 1
                            elif line[i] == '}':
                                comment_depth -= 1
                            i += 1
                        if comment_depth == 0:
                            # Comment closed on this line - continue processing rest of line
                            in_comment = False
                    else:
                        # Regular character - add if not in comment
                        if not in_comment:
                            line_result.append(line[i])
                        i += 1
                
                # Add processed line
                processed_line = ''.join(line_result)
                result_lines.append(processed_line)
            else:
                # Currently in a comment from previous line - find closing brace
                line_result = []
                i = 0
                # Skip until we find the closing brace
                while i < len(line) and comment_depth > 0:
                    if line[i] == '{':
                        comment_depth += 1
                    elif line[i] == '}':
                        comment_depth -= 1
                        if comment_depth == 0:
                            # Comment closed - process rest of line
                            in_comment = False
                            i += 1
                            # Add remaining content after comment closes
                            while i < len(line):
                                line_result.append(line[i])
                                i += 1
                            break
                    i += 1
                
                # If comment is still open, this line was entirely within comment
                # Add empty line to preserve structure, or content if comment closed
                if comment_depth == 0:
                    processed_line = ''.join(line_result)
                    result_lines.append(processed_line)
                else:
                    # Comment still open - this line was entirely comment
                    # Add empty line to preserve line structure
                    result_lines.append('')
        
        return result_lines
    
    @staticmethod
    def _remove_non_standard_tags(pgn_text: str) -> str:
        """Remove non-standard tags (like [%evp], [%mdl], [%clk]) from comments.
        
        Non-standard tags are patterns like [%...] that appear inside comments.
        Examples: [%evp 6,32,67], [%mdl 8192], [%clk 0:05:32], etc.
        
        Args:
            pgn_text: PGN text with comments containing non-standard tags.
            
        Returns:
            PGN text with non-standard tags removed from comments.
        Note: Preserves metadata tags - does not process metadata-only lines.
        """
        # Pattern to match non-standard tags: [%...] where ... is anything except ]
        # This matches patterns like [%evp ...], [%mdl ...], [%clk ...], etc.
        non_standard_tag_pattern = re.compile(r'\[%[^\]]+\]')
        
        # Split into lines to preserve metadata-only lines
        lines = pgn_text.split('\n')
        result_lines = []
        
        # Process entire text as single string to handle multi-line comments
        # But we need to track which lines are metadata-only to preserve them
        metadata_line_indices = set()
        for idx, line in enumerate(lines):
            if PgnFormatterService._is_metadata_only_line(line):
                metadata_line_indices.add(idx)
        
        # Process the entire text as a single string
        result_parts = []
        i = 0
        comment_depth = 0
        comment_start = -1
        comment_content_parts = []
        opening_brace_index = -1  # Track where we added the opening brace
        
        while i < len(pgn_text):
            # Check if we're at the start of a metadata-only line
            # If so, skip processing and preserve the line as-is
            current_line_start = pgn_text.rfind('\n', 0, i) + 1
            current_line_num = pgn_text[:current_line_start].count('\n')
            
            if current_line_num in metadata_line_indices:
                # Find the end of this line
                line_end = pgn_text.find('\n', i)
                if line_end == -1:
                    line_end = len(pgn_text)
                # Copy the entire line as-is
                result_parts.append(pgn_text[i:line_end + 1])
                i = line_end + 1
                continue
            
            if pgn_text[i] == '{':
                if comment_depth == 0:
                    # Starting a new comment
                    comment_start = i
                    comment_content_parts = []
                    opening_brace_index = len(result_parts)  # Remember where we'll add the opening brace
                comment_depth += 1
                if comment_depth == 1:
                    # This is the opening brace of the outermost comment
                    result_parts.append('{')
                else:
                    # Nested comment - include the brace in content
                    comment_content_parts.append('{')
                i += 1
            elif pgn_text[i] == '}':
                comment_depth -= 1
                if comment_depth == 0:
                    # Closing the outermost comment
                    # Process the collected comment content
                    comment_content = ''.join(comment_content_parts)
                    
                    # Remove non-standard tags from comment content
                    cleaned_content = non_standard_tag_pattern.sub('', comment_content)
                    
                    # Clean up extra spaces left by removed tags
                    cleaned_content = re.sub(r'\s+', ' ', cleaned_content).strip()
                    
                    # If there's remaining content, keep the comment; otherwise remove it entirely
                    if cleaned_content:
                        result_parts.append(cleaned_content)
                        result_parts.append('}')
                    else:
                        # Comment is empty after removing tags - remove the opening brace we added
                        if opening_brace_index >= 0 and opening_brace_index < len(result_parts):
                            # Remove the opening brace we added earlier
                            result_parts.pop(opening_brace_index)
                    
                    comment_start = -1
                    comment_content_parts = []
                    opening_brace_index = -1
                else:
                    # Nested comment - include the brace in content
                    comment_content_parts.append('}')
                i += 1
            else:
                if comment_depth > 0:
                    # Inside a comment - collect content
                    comment_content_parts.append(pgn_text[i])
                else:
                    # Outside comments - preserve as-is
                    result_parts.append(pgn_text[i])
                i += 1
        
        # Handle unclosed comment at end of text
        if comment_depth > 0:
            # Add the unclosed comment content (without processing, as it's malformed)
            result_parts.append(''.join(comment_content_parts))
        
        result_str = ''.join(result_parts)
        # Clean up multiple consecutive spaces (but preserve newlines)
        # Replace multiple spaces/tabs with single space, but keep newlines
        result_str = re.sub(r'[ \t]+', ' ', result_str)
        # Clean up multiple consecutive newlines (but preserve at least one)
        result_str = re.sub(r'\n\s*\n\s*\n+', '\n\n', result_str)
        return result_str.strip()
    
    @staticmethod
    def _remove_variations(pgn_text: str) -> str:
        """Remove variations from PGN text.
        
        Args:
            pgn_text: PGN text with variations.
            
        Returns:
            PGN text without variations.
        Note: Preserves metadata tags - does not process metadata-only lines.
        """
        result_chars: List[str] = []
        variation_depth = 0
        comment_depth = 0
        in_comment = False
        
        i = 0
        while i < len(pgn_text):
            char = pgn_text[i]
            
            # Track comments first - parentheses inside comments should be ignored
            if char == '{':
                comment_depth += 1
                in_comment = True
                # Add opening brace if not in a variation (preserve comments outside variations)
                if variation_depth == 0:
                    result_chars.append(char)
                i += 1
                continue
            
            if char == '}' and in_comment:
                comment_depth -= 1
                if comment_depth <= 0:
                    in_comment = False
                    comment_depth = 0
                # Add closing brace if not in a variation (preserve comments outside variations)
                if variation_depth == 0:
                    result_chars.append(char)
                i += 1
                continue
            
            # Only process variation markers when NOT inside a comment
            # (parentheses inside comments are not variation markers)
            if not in_comment:
                if char == '(':
                    variation_depth += 1
                    i += 1
                    continue
                if char == ')' and variation_depth > 0:
                    variation_depth -= 1
                    i += 1
                    continue
                
                # Only add characters when not in a variation
                if variation_depth == 0:
                    result_chars.append(char)
            else:
                # Inside a comment - only add if not in a variation
                # (comments inside variations should be removed with the variation)
                if variation_depth == 0:
                    result_chars.append(char)
            
            i += 1
        
        # Validate that variation_depth is 0 at the end (all variations should be closed)
        if variation_depth != 0:
            # This indicates mismatched parentheses - log warning but continue
            # In this case, we may have removed too much or too little
            logging_service = LoggingService.get_instance()
            logging_service.warning(f"_remove_variations ended with variation_depth={variation_depth} (mismatched parentheses)")
        
        result_str = ''.join(result_chars)
        # Clean up spaces (preserve newlines)
        result_str = re.sub(r'[ \t]+', ' ', result_str)
        # Clean up multiple consecutive newlines
        result_str = re.sub(r'\n\s*\n\s*\n+', '\n\n', result_str)
        return result_str.strip()
    
    @staticmethod
    def _remove_annotations(pgn_text: str) -> str:
        """Remove annotations from PGN text.
        
        Args:
            pgn_text: PGN text with annotations.
            
        Returns:
            PGN text without annotations.
        Note: Only removes annotations from move notation, not from metadata tags.
        """
        # Split PGN into metadata tags and move notation
        # Metadata tags are lines like [Key "Value"] or multiple tags on one line
        lines = pgn_text.split('\n')
        result_lines = []
        in_move_notation = False
        
        for line in lines:
            # Always skip metadata-only lines to preserve them
            if PgnFormatterService._is_metadata_only_line(line):
                result_lines.append(line)
                continue
            
            line_stripped = line.strip()
            
            # Track when we enter move notation
            if line_stripped:
                # Check if this line has move notation (not metadata-only)
                has_move_notation = re.search(r'\b([1-9]\d{0,2}|0)\.(?:\.\.| |\w)', line_stripped) is not None
                if has_move_notation:
                    in_move_notation = True
            
            if in_move_notation:
                # Only remove annotations from move notation (excluding metadata tags)
                # Pattern to match annotations: !, !!, ?, ??, !?, ?!
                # These can appear after moves (like e4! or e5?)
                annotation_pattern = re.compile(r'[!?]{1,2}')
                filtered_line = PgnFormatterService._apply_regex_excluding_metadata(
                    line, annotation_pattern, ''
                )
                
                # Remove NAGs (Numeric Annotation Glyphs) in their original form
                # At this point, NAGs are still in their original form ($2, $4, etc.)
                # because filtering happens BEFORE formatting
                # Formatting converts $2 to " (poor move)" later, so we only need to remove $2 here
                nag_symbol_pattern = re.compile(r'\$\d+')
                filtered_line = PgnFormatterService._apply_regex_excluding_metadata(
                    filtered_line, nag_symbol_pattern, ''
                )
                
                result_lines.append(filtered_line)
            else:
                # Empty line or line before move notation starts - keep as-is
                result_lines.append(line)
        
        result = '\n'.join(result_lines)
        # Clean up multiple consecutive spaces (but preserve newlines)
        # Replace multiple spaces/tabs with single space, but keep newlines
        result = re.sub(r'[ \t]+', ' ', result)
        # Clean up multiple consecutive newlines (but preserve at least one)
        result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)
        return result.strip()
    
    @staticmethod
    def _remove_results(pgn_text: str) -> str:
        """Remove results from PGN text.
        
        Args:
            pgn_text: PGN text with results.
            
        Returns:
            PGN text without results.
        Note: Only removes results from move notation, not from metadata tags.
        """
        # Split PGN into metadata tags and move notation
        # Metadata tags are lines like [Key "Value"] or multiple tags on one line
        lines = pgn_text.split('\n')
        result_lines = []
        in_move_notation = False
        
        for line in lines:
            # Always skip metadata-only lines to preserve them
            if PgnFormatterService._is_metadata_only_line(line):
                result_lines.append(line)
                continue
            
            line_stripped = line.strip()
            
            # Track when we enter move notation
            if line_stripped:
                # Check if this line has move notation (not metadata-only)
                has_move_notation = re.search(r'\b([1-9]\d{0,2}|0)\.(?:\.\.| |\w)', line_stripped) is not None
                if has_move_notation:
                    in_move_notation = True
            
            if in_move_notation:
                # Only remove results from move notation (excluding metadata tags)
                # Pattern to match results: 1-0, 0-1, 1/2-1/2, *
                # Use word boundaries to avoid matching within tags
                result_pattern = re.compile(r'\b(1-0|0-1|1/2-1/2|\*)\b')
                filtered_line = PgnFormatterService._apply_regex_excluding_metadata(
                    line, result_pattern, ''
                )
                result_lines.append(filtered_line)
            else:
                # Empty line or line before move notation starts - keep as-is
                result_lines.append(line)
        
        result = '\n'.join(result_lines)
        # Clean up multiple consecutive spaces (but preserve newlines)
        # Replace multiple spaces/tabs with single space, but keep newlines
        result = re.sub(r'[ \t]+', ' ', result)
        # Clean up multiple consecutive newlines (but preserve at least one)
        result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)
        return result.strip()
    
    @staticmethod
    def format_pgn_to_html(pgn_text: str, config: Dict[str, Any], active_move_ply: int = 0) -> Tuple[str, List[Tuple[str, int, bool]]]:
        """Format plain PGN text to HTML with colors and styles.
        
        Args:
            pgn_text: Plain PGN text string.
            config: Configuration dictionary containing formatting settings.
            active_move_ply: Ply index of the active move to highlight (0 = starting position).
            
        Returns:
            Tuple of (formatted_html, move_info) where:
            - formatted_html: HTML formatted string with styling applied
            - move_info: List of (move_san, move_number, is_white) tuples for each ply,
              indexed by ply (0 = start, 1 = after first move, etc.)
        """
        if not pgn_text:
            return ("", [])
        
        # Parse PGN to identify moves
        parsed_moves = PgnFormatterService._extract_move_positions_from_pgn(pgn_text)
        
        # Get formatting config
        ui_config = config.get('ui', {})
        panel_config = ui_config.get('panels', {}).get('detail', {})
        pgn_config = panel_config.get('pgn_notation', {})
        formatting = pgn_config.get('formatting', {})
        
        # Get default text color
        default_color = pgn_config.get('text_color', [220, 220, 220])
        
        # Helper function to create HTML span
        def span(text: str, color: list, bold: bool = False, italic: bool = False) -> str:
            """Create HTML span with styling."""
            # Escape HTML special characters in text
            escaped_text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            style_parts = [f"color: rgb({color[0]}, {color[1]}, {color[2]})"]
            if bold:
                style_parts.append("font-weight: bold")
            if italic:
                style_parts.append("font-style: italic")
            style = "; ".join(style_parts)
            return f'<span style="{style}">{escaped_text}</span>'
        
        # Start with the PGN text
        formatted = pgn_text
        
        # Get variation move styling config
        variations_config = formatting.get('variations', {})
        variation_color = variations_config.get('color', [180, 180, 180])
        variation_italic = variations_config.get('italic', False)
        
        # ZERO: Convert NAGs (Numeric Annotation Glyphs) to symbols or readable text BEFORE other formatting
        # This ensures NAGs are converted even when they're in variations or comments
        # Common NAGs (1-6) can be converted to symbols (!, !!, ?, ??, !?, ?!) for annotation color formatting
        # or to readable text, depending on user preference
        # Other NAGs are converted to readable text
        nags_config = formatting.get('nags', {})
        show_nag_text = nags_config.get('show_text', True)  # Whether to show text or just symbol for non-symbol NAGs
        annotations_config = formatting.get('annotations', {})
        use_symbols_for_common_nags = annotations_config.get('use_symbols', True)  # Whether to convert common NAGs to symbols
        
        # Pattern to match NAGs: $ followed by one or more digits
        # But NOT in metadata tags - we need to skip headers
        nag_pattern = re.compile(r'\$(\d+)')
        
        # Process the entire text and convert NAGs
        # We need to be careful not to convert NAGs inside headers [Key "Value"]
        result_parts = []
        i = 0
        
        while i < len(formatted):
            # Check if we're at the start of a header
            if formatted[i] == '[':
                # Check if this is the start of a header [Key "Value"]
                # Headers are in format [Key "Value"] where Key starts with a letter
                header_match = re.match(r'\[([A-Za-z][A-Za-z0-9]*)\s+"([^"]+)"\]', formatted[i:])
                if header_match:
                    # Found a header - copy it as-is without processing NAGs
                    header_end = i + header_match.end()
                    result_parts.append(formatted[i:header_end])
                    i = header_end
                    continue
            
            # Check for NAGs (but not inside headers)
            if formatted[i] == '$' and i + 1 < len(formatted):
                # Try to match a NAG pattern starting at position i
                remaining_text = formatted[i:]
                match = nag_pattern.search(remaining_text)
                if match and match.start() == 0:
                    # Found a NAG - convert it to symbol or readable text
                    nag_number = int(match.group(1))
                    
                    # Check if this NAG has a symbol equivalent (common annotations)
                    if nag_number in NAG_TO_SYMBOL:
                        # Check if user wants symbols or text for common NAGs
                        if use_symbols_for_common_nags:
                            # Convert to symbol (e.g., "$1" becomes "!", "$2" becomes "?")
                            # These symbols will be colored by the annotation formatting step
                            nag_display = NAG_TO_SYMBOL[nag_number]
                        else:
                            # Convert to text format like other NAGs
                            nag_text = get_nag_text(nag_number)
                            
                            if show_nag_text:
                                nag_display = f" ({nag_text})"
                            else:
                                nag_display = match.group(0)
                    else:
                        # NAG doesn't have a symbol equivalent - convert to text
                        nag_text = get_nag_text(nag_number)
                        
                        if show_nag_text:
                            # Replace NAG with readable text (e.g., "$10" becomes " (drawish position)" or "$146" becomes " (unknown NAG 146)")
                            nag_display = f" ({nag_text})"
                        else:
                            # Keep the NAG symbol
                            nag_display = match.group(0)
                    
                    result_parts.append(nag_display)
                    i = i + match.end()
                    continue
            
            # Regular character - copy as-is
            result_parts.append(formatted[i])
            i += 1
        
        formatted = ''.join(result_parts)
        
        # FIRST: Format headers [Key "Value"] - format them completely first
        # This ensures headers are treated independently from moves
        headers_config = formatting.get('headers', {})
        header_color = headers_config.get('color', [100, 150, 255])
        header_bold = headers_config.get('bold', True)
        
        # Process headers - find them and wrap entire header in span
        # Headers must match the pattern: [Key "Value"] (with quotes around the value)
        # This excludes Lichess-style annotations like [%eval 21,29] or [%wdl 31,964,5]
        header_pattern = re.compile(r'\[([A-Za-z][A-Za-z0-9]*)\s+"([^"]+)"\]')
        result_parts = []
        i = 0
        while i < len(formatted):
            if formatted[i] == '[':
                # Check if this matches a header pattern
                match = header_pattern.match(formatted, i)
                if match:
                    # Found a valid header [Key "Value"]
                    header_text = match.group(0)
                    result_parts.append(span(header_text, header_color, header_bold))
                    i = match.end()
                else:
                    # Not a header, just a bracket - treat as regular character
                    result_parts.append(formatted[i])
                    i += 1
            else:
                # Regular character
                result_parts.append(formatted[i])
                i += 1
        
        formatted = ''.join(result_parts)
        
        # SECOND: Format comments (after headers, before other formatting)
        comments_config = formatting.get('comments', {})
        comment_color = comments_config.get('color', [180, 200, 255])
        comment_italic = comments_config.get('italic', True)
        
        # Build formatted text while processing comments
        result_parts = []
        i = 0
        in_header_span = False
        
        while i < len(formatted):
            if formatted[i] == '<':
                # Check if this is a header span opening or closing
                if i + 5 < len(formatted) and formatted[i:i+5] == '<span':
                    # Look ahead to see if this is a header span
                    tag_end = formatted.find('>', i)
                    if tag_end != -1:
                        tag_content = formatted[i:tag_end + 1]
                        # Check if it's a header span
                        if 'color: rgb(100, 150, 255)' in tag_content:
                            in_header_span = True
                            result_parts.append(formatted[i:tag_end + 1])
                            i = tag_end + 1
                            continue
                elif i + 7 < len(formatted) and formatted[i:i+7] == '</span>':
                    # This is a closing span tag
                    if in_header_span:
                        in_header_span = False
                    result_parts.append('</span>')
                    i += 7
                    continue
                
                # Skip other HTML tags
                tag_end = formatted.find('>', i)
                if tag_end != -1:
                    result_parts.append(formatted[i:tag_end + 1])
                    i = tag_end + 1
                    continue
                else:
                    result_parts.append(formatted[i])
                    i += 1
            elif formatted[i] == '{' and not in_header_span:
                # Format comment (but only if not inside header span)
                # Format comment
                start = i
                depth = 0
                found_end = False
                for j in range(i, len(formatted)):
                    if formatted[j] == '{':
                        depth += 1
                    elif formatted[j] == '}':
                        depth -= 1
                        if depth == 0:
                            end = j + 1
                            comment_text = formatted[start:end]
                            result_parts.append(span(comment_text, comment_color, italic=comment_italic))
                            i = end
                            found_end = True
                            break
                if not found_end:
                    # No closing brace found, treat as regular character
                    result_parts.append(formatted[i])
                    i += 1
            else:
                # Regular character (or comment inside header - just copy it)
                result_parts.append(formatted[i])
                i += 1
        
        formatted = ''.join(result_parts)
        
        # Style NAG text (already converted to readable text earlier) BEFORE formatting variations
        # This ensures NAG text is in its own span so variation formatter will skip it
        # This ensures NAG text is in its own span so move formatter will skip it
        # Common NAGs (1-6) were converted to symbols (!, !!, ?, ??, !?, ?!) and will be styled later
        # Other NAGs were converted from $10 to " (drawish position)" in the early step
        nags_config = formatting.get('nags', {})
        nag_color = nags_config.get('color', [200, 200, 255])
        nag_bold = nags_config.get('bold', False)
        nag_italic = nags_config.get('italic', True)
        show_nag_text = nags_config.get('show_text', True)
        
        if show_nag_text:
            # NAGs were converted to text like " (poor move)", " (good move)", etc.
            # We need to style these converted NAG texts
            # Since NAGs were converted earlier, we can match them by looking for the pattern
            # " (text)" where text is a known NAG meaning
            
            # Build a pattern that matches any NAG meaning text in parentheses
            # We'll match patterns like " (text)" where text is one of the NAG meanings
            # OR " (unknown NAG \d+)" for unknown NAGs
            nag_meanings_list = list(set(NAG_MEANINGS.values()))
            # Sort by length (longest first) to match more specific patterns first
            nag_meanings_list.sort(key=len, reverse=True)
            
            # Escape special regex characters in NAG meanings
            # Some meanings contain parentheses (like "Black should resign"), so we need to escape them
            # But we need to handle nested parentheses correctly
            escaped_meanings = []
            for meaning in nag_meanings_list:
                # Escape the meaning, but we need to handle parentheses specially
                # Meanings with nested parens like "White has a crushing advantage (Black should resign)"
                # need to be matched as a whole, so we escape everything including the nested parens
                escaped = re.escape(meaning)
                escaped_meanings.append(escaped)
            
            # Also add pattern for unknown NAGs: "unknown NAG \d+"
            # This matches patterns like "unknown NAG 146", "unknown NAG 200", etc.
            unknown_nag_pattern = r'unknown NAG \d+'
            
            # Combine known meanings and unknown NAG pattern
            all_patterns = escaped_meanings + [unknown_nag_pattern]
            
            # Only build pattern if we have patterns to match
            # This prevents issues with empty patterns that could match incorrectly
            if all_patterns:
                nag_meanings_pattern = '|'.join(all_patterns)
                
                # Pattern: one or more spaces, opening paren, NAG meaning (captured), closing paren
                # The space before the paren is important - NAGs are inserted as " (text)"
                # Note: We capture the entire meaning (group 1) which may contain nested parentheses
                # The pattern needs to match the full escaped meaning exactly
                # IMPORTANT: The pattern requires at least one non-whitespace character in the captured group
                # This prevents matching empty parentheses like " ()"
                nag_text_pattern = re.compile(r'\s+\((' + nag_meanings_pattern + r')\)')
            else:
                # No patterns to match - create a pattern that matches nothing
                nag_text_pattern = re.compile(r'(?!)')  # Negative lookahead that never matches
            
            result_parts = []
            i = 0
            in_tag = False
            in_header_span = False
            
            while i < len(formatted):
                if formatted[i] == '<':
                    in_tag = True
                    # Check if this is a header span opening tag
                    if i + 5 < len(formatted) and formatted[i:i+5] == '<span':
                        tag_end = formatted.find('>', i)
                        if tag_end != -1:
                            tag_content = formatted[i:tag_end+1]
                            # Check if this is a header span (blue color)
                            if 'color: rgb(100, 150, 255)' in tag_content:
                                in_header_span = True
                    # Check if this is a closing span tag (</span>)
                    elif i + 7 < len(formatted) and formatted[i:i+7] == '</span>':
                        # Found closing span tag - if we're in a header span, close it
                        if in_header_span:
                            in_header_span = False
                    
                    result_parts.append(formatted[i])
                    i += 1
                elif formatted[i] == '>':
                    in_tag = False
                    result_parts.append(formatted[i])
                    i += 1
                elif not in_tag and not in_header_span:
                    # Check if we're at a NAG text pattern
                    # We want to style NAGs everywhere except inside HTML tags and headers
                    # Look for NAG text pattern starting at position i
                    remaining_text = formatted[i:]
                    match = nag_text_pattern.search(remaining_text)
                    if match and match.start() == 0:
                        # Found potential NAG text - verify it captured the text correctly
                        captured_text = match.group(1)  # The NAG meaning text (group 1)
                        full_match = match.group(0)  # Full match including " (text)"
                        
                        # Verify we actually captured text (not empty)
                        # This prevents matching empty parentheses like " ()"
                        # Also verify the full match contains the parentheses and text
                        # Additional check: ensure the captured text is not just whitespace
                        if (captured_text and 
                            captured_text.strip() and 
                            len(captured_text.strip()) > 0 and
                            '(' in full_match and 
                            ')' in full_match and
                            full_match.count('(') == 1 and  # Ensure only one opening paren
                            full_match.count(')') == 1):   # Ensure only one closing paren
                            # This is a valid NAG text - style it
                            # The full_match should be like " (poor move)" or " (very poor move)"
                            nag_formatted = span(full_match, nag_color, nag_bold, nag_italic)
                            result_parts.append(nag_formatted)
                            i = i + match.end()
                            continue
                        # If captured_text is empty or invalid, it's not a NAG, continue normal processing
                    
                    result_parts.append(formatted[i])
                    i += 1
                else:
                    result_parts.append(formatted[i])
                    i += 1
            
            formatted = ''.join(result_parts)
        
        # Format variations: wrap parentheses and format moves within them
        # NAG text is already styled above, so variation formatter will skip it
        formatted = PgnFormatterService._format_variations_with_moves(
            formatted, variation_color, variation_italic, span, comment_color, nags_config
        )
        
        # Format move numbers (e.g., 1., 2., 12., etc.) - but skip if inside HTML tags, headers, or variations
        # Note: Variations are already formatted with move numbers, so we skip formatting move numbers
        # that are already inside variation spans
        move_numbers_config = formatting.get('move_numbers', {})
        move_number_color = move_numbers_config.get('color', [255, 255, 255])
        move_number_bold = move_numbers_config.get('bold', True)
        comment_color_css = f"color: rgb({comment_color[0]}, {comment_color[1]}, {comment_color[2]})"
        
        # Match move numbers outside HTML tags, header spans, and variation spans
        # Header spans have color rgb(100, 150, 255)
        # Variation spans have color rgb(180, 180, 180) and italic style
        # Pattern matches: optional whitespace, digit(s) followed by period and optional space, not preceded by a digit
        move_number_pattern = re.compile(r'(?<![0-9])(\s*\d+\.\s*)')
        result_parts = []
        i = 0
        in_tag = False
        in_variation_span = False
        in_header_span = False
        comment_span_depth = 0
        span_stack: List[str] = []
        
        def _recompute_span_flags() -> None:
            nonlocal in_variation_span, in_header_span, comment_span_depth
            in_header_span = any(span == 'header' for span in span_stack)
            in_variation_span = any(span == 'variation' for span in span_stack)
            comment_span_depth = sum(1 for span in span_stack if span == 'comment')
        
        while i < len(formatted):
            if formatted[i] == '<':
                # Check if this is a closing span tag first
                if i + 7 < len(formatted) and formatted[i:i+7] == '</span>':
                    # Closing span tag - update span stack/flags
                    in_tag = False
                    if span_stack:
                        span_stack.pop()
                        _recompute_span_flags()
                    result_parts.append('</span>')
                    i += 7
                    continue
                # Check if this is opening a span
                elif i + 5 < len(formatted) and formatted[i:i+5] == '<span':
                    in_tag = True
                    # Look ahead to see what type of span this is
                    tag_end = formatted.find('>', i)
                    span_type = 'other'
                    if tag_end != -1:
                        tag_content = formatted[i:tag_end+1]
                        if 'color: rgb(100, 150, 255)' in tag_content:
                            span_type = 'header'
                        elif comment_color_css in tag_content:
                            span_type = 'comment'
                        elif ('color: rgb(180, 180, 180)' in tag_content or 'font-style: italic' in tag_content):
                            span_type = 'variation'
                        span_stack.append(span_type)
                        _recompute_span_flags()
                        result_parts.append(formatted[i])
                        i += 1
                    else:
                        result_parts.append(formatted[i])
                        i += 1
                else:
                    # Other HTML tag
                    in_tag = True
                    result_parts.append(formatted[i])
                    i += 1
            elif formatted[i] == '>':
                in_tag = False
                result_parts.append(formatted[i])
                i += 1
            elif not in_tag and not in_variation_span and not in_header_span and comment_span_depth == 0:
                # Look for move number match starting at position i
                # Only format if we're not inside a variation or header span
                # Pattern includes optional whitespace, so it can match even if we're at a space
                match = move_number_pattern.match(formatted, i)
                if match:
                    # Found a match starting at position i
                    move_num_formatted = span(match.group(0), move_number_color, move_number_bold)
                    result_parts.append(move_num_formatted)
                    i = match.end()
                else:
                    result_parts.append(formatted[i])
                    i += 1
            else:
                result_parts.append(formatted[i])
                i += 1
        
        formatted = ''.join(result_parts)
        
        # Format mainline moves - style move SANs (but skip if inside HTML tags, headers, variations, or comments)
        moves_config = formatting.get('moves', {})
        move_color = moves_config.get('color', default_color)  # Default to text_color if not specified
        move_bold = moves_config.get('bold', False)
        
        # Pattern to match move SANs in mainline (not in variations, comments, or headers)
        # Move SAN pattern: piece (optional), source square (optional), capture (optional), destination, promotion (optional), check/mate (optional)
        # This matches moves like: e4, Nf3, O-O, Qxd1, e8=Q, e4+, e4#
        # Must be a word boundary to avoid matching parts of other text
        move_san_pattern = re.compile(
            r'\b('
            r'(?:[NBRQK]?[a-h]?[1-8]?[x\-]?[a-h][1-8]'  # Standard moves: piece, source, capture, dest
            r'(?:[=][NBRQ])?'  # Promotion
            r'(?:[+#]|e\.p\.)?'  # Check, mate, or en passant
            r')|'
            r'(?:O-O(?:-O)?)'  # Castling: O-O or O-O-O
            r')(?=\s|$|[!?])'  # Must be followed by space, end of string, or annotation symbol
        )
        
        result_parts = []
        i = 0
        in_tag = False
        in_variation_span = False
        in_header_span = False
        in_comment_span = False
        comment_span_depth = 0
        span_stack: List[str] = []
        
        def _recompute_move_span_flags() -> None:
            nonlocal in_variation_span, in_header_span, in_comment_span, comment_span_depth
            in_header_span = any(span == 'header' for span in span_stack)
            in_variation_span = any(span == 'variation' for span in span_stack)
            in_comment_span = any(span == 'comment' for span in span_stack)
            comment_span_depth = sum(1 for span in span_stack if span == 'comment')
        
        in_nag_span = False
        
        while i < len(formatted):
            if formatted[i] == '<':
                # Check if this is a closing span tag first
                if i + 7 < len(formatted) and formatted[i:i+7] == '</span>':
                    # Closing span tag - update span stack/flags
                    in_tag = False
                    if span_stack:
                        span_stack.pop()
                        _recompute_move_span_flags()
                    result_parts.append('</span>')
                    i += 7
                    continue
                # Check if this is opening a span
                elif i + 5 < len(formatted) and formatted[i:i+5] == '<span':
                    in_tag = True
                    # Look ahead to see what type of span this is
                    tag_end = formatted.find('>', i)
                    span_type = 'other'
                    if tag_end != -1:
                        tag_content = formatted[i:tag_end+1]
                        if 'color: rgb(100, 150, 255)' in tag_content:
                            span_type = 'header'
                        elif comment_color_css in tag_content:
                            span_type = 'comment'
                        elif ('color: rgb(180, 180, 180)' in tag_content or 'font-style: italic' in tag_content):
                            span_type = 'variation'
                        elif nag_color and f'color: rgb({nag_color[0]}, {nag_color[1]}, {nag_color[2]})' in tag_content:
                            span_type = 'nag'
                        span_stack.append(span_type)
                        _recompute_move_span_flags()
                        result_parts.append(formatted[i])
                        i += 1
                    else:
                        result_parts.append(formatted[i])
                        i += 1
                else:
                    # Other HTML tag
                    in_tag = True
                    result_parts.append(formatted[i])
                    i += 1
            elif formatted[i] == '>':
                in_tag = False
                result_parts.append(formatted[i])
                i += 1
            elif not in_tag and not in_variation_span and not in_header_span and comment_span_depth == 0:
                # Check if we're inside a NAG span (skip formatting moves inside NAG text)
                in_nag_span = any(span == 'nag' for span in span_stack)
                
                if in_nag_span:
                    # Skip formatting if inside NAG text span
                    result_parts.append(formatted[i])
                    i += 1
                    continue
                
                # Look for move SAN match starting at position i
                # Only format if we're not inside a variation, header, comment, or NAG span
                # Also skip if we're right after a move number (which is already formatted)
                # Check if previous character is part of a formatted move number span
                match = move_san_pattern.search(formatted, i)
                if match and match.start() == i:
                    # Found a potential move SAN - verify it's not part of already-formatted content
                    # Check if we're immediately after a closing span tag (could be a move number)
                    # We'll be conservative and only format if there's whitespace or start of line before
                    prev_char = formatted[i-1] if i > 0 else ' '
                    # Don't format if immediately after a digit (could be part of move number)
                    if not (i > 0 and formatted[i-1].isdigit()):
                        move_san = match.group(1)
                        move_formatted = span(move_san, move_color, move_bold)
                        result_parts.append(move_formatted)
                        i = match.end()
                    else:
                        result_parts.append(formatted[i])
                        i += 1
                else:
                    result_parts.append(formatted[i])
                    i += 1
            else:
                result_parts.append(formatted[i])
                i += 1
        
        formatted = ''.join(result_parts)
        
        # Format annotations (!, !!, ?, ??) - but skip if inside HTML tags or headers
        annotations_config = formatting.get('annotations', {})
        
        # Good moves (!, !!)
        good_config = annotations_config.get('good', {})
        good_color = good_config.get('color', [100, 255, 100])
        good_bold = good_config.get('bold', True)
        
        # Bad moves (?, ??)
        bad_config = annotations_config.get('bad', {})
        bad_color = bad_config.get('color', [255, 100, 100])
        bad_bold = bad_config.get('bold', True)
        
        # Interesting moves (!?)
        interesting_config = annotations_config.get('interesting', {})
        interesting_color = interesting_config.get('color', [255, 255, 100])
        interesting_bold = interesting_config.get('bold', False)
        
        # Dubious moves (?!)
        dubious_config = annotations_config.get('dubious', {})
        dubious_color = dubious_config.get('color', [255, 200, 100])
        dubious_bold = dubious_config.get('bold', False)
        
        # Process annotations outside HTML tags and header spans
        # Order matters: process more specific patterns first to avoid partial matches
        # For example, !? and ?! must be processed before ! and ? to avoid matching parts
        annotation_patterns = [
            (r'(!\?)', interesting_color, interesting_bold),  # !? first (most specific, 2 chars)
            (r'(\?!)', dubious_color, dubious_bold),  # ?! second (most specific, 2 chars)
            (r'(\!{2})', good_color, good_bold),  # !! third (2 chars)
            (r'(\?{2})', bad_color, bad_bold),  # ?? fourth (2 chars)
            (r'(!)', good_color, good_bold),  # ! last (single char, after !! and !?)
            (r'(\?)', bad_color, bad_bold),  # ? last (single char, after ?? and ?!)
        ]
        
        # Process all patterns in a single pass to avoid re-processing already formatted annotations
        result_parts = []
        i = 0
        in_tag = False
        in_header_span = False
        in_comment_span = False
        in_variation_span = False
        in_annotation_span = False  # Track if we're inside an already-formatted annotation
        span_stack: List[str] = []
        
        def _recompute_annotation_span_flags() -> None:
            nonlocal in_header_span, in_comment_span, in_variation_span, in_annotation_span
            in_header_span = any(span == 'header' for span in span_stack)
            in_comment_span = any(span == 'comment' for span in span_stack)
            in_variation_span = any(span == 'variation' for span in span_stack)
            in_annotation_span = any(span == 'annotation' for span in span_stack)
        
        # Compile all patterns
        compiled_patterns = [(re.compile(pattern), color, is_bold) for pattern, color, is_bold in annotation_patterns]
        
        while i < len(formatted):
            if formatted[i] == '<':
                # Check if this is a closing span tag first
                if i + 7 < len(formatted) and formatted[i:i+7] == '</span>':
                    # Closing span tag - update span stack
                    if span_stack:
                        span_stack.pop()
                        _recompute_annotation_span_flags()
                    result_parts.append('</span>')
                    i += 7
                    continue
                # Check if this is opening a span
                elif i + 5 < len(formatted) and formatted[i:i+5] == '<span':
                    tag_end = formatted.find('>', i)
                    if tag_end != -1:
                        tag_content = formatted[i:tag_end+1]
                        # Determine span type
                        if 'color: rgb(100, 150, 255)' in tag_content:
                            span_stack.append('header')
                        elif comment_color_css in tag_content:
                            span_stack.append('comment')
                        elif ('color: rgb(180, 180, 180)' in tag_content or 'font-style: italic' in tag_content):
                            span_stack.append('variation')
                        # Check if this is an annotation span (has annotation colors)
                        elif (f'color: rgb({good_color[0]}, {good_color[1]}, {good_color[2]})' in tag_content or
                              f'color: rgb({bad_color[0]}, {bad_color[1]}, {bad_color[2]})' in tag_content or
                              f'color: rgb({interesting_color[0]}, {interesting_color[1]}, {interesting_color[2]})' in tag_content or
                              f'color: rgb({dubious_color[0]}, {dubious_color[1]}, {dubious_color[2]})' in tag_content):
                            span_stack.append('annotation')
                        _recompute_annotation_span_flags()
                        # Append the entire span tag
                        result_parts.append(formatted[i:tag_end+1])
                        i = tag_end + 1
                        continue
                    else:
                        # Malformed tag, just copy the character
                        result_parts.append(formatted[i])
                        i += 1
                else:
                    # Other HTML tag - find the closing >
                    tag_end = formatted.find('>', i)
                    if tag_end != -1:
                        result_parts.append(formatted[i:tag_end+1])
                        i = tag_end + 1
                    else:
                        result_parts.append(formatted[i])
                        i += 1
            elif formatted[i] == '>':
                in_tag = False
                result_parts.append(formatted[i])
                i += 1
            elif not in_tag and not in_header_span and not in_comment_span and not in_variation_span and not in_annotation_span:
                # Only format annotations outside of all HTML tags and special spans
                # Try patterns in order (most specific first) - stop at first match
                matched = False
                for compiled_pattern, color, is_bold in compiled_patterns:
                    match = compiled_pattern.match(formatted, i)
                    if match:
                        annotation_formatted = span(match.group(0), color, is_bold)
                        result_parts.append(annotation_formatted)
                        i = match.end()
                        matched = True
                        break
                
                if not matched:
                    result_parts.append(formatted[i])
                    i += 1
            else:
                result_parts.append(formatted[i])
                i += 1
        
        formatted = ''.join(result_parts)
        
        # Format results (1-0, 0-1, 1/2-1/2, *) - but skip if inside HTML tags, headers, or variations
        # Note: We need to track variation depth because results can be inside comment spans
        # that are themselves inside variation spans. Use a stack to track which spans are variation spans.
        results_config = formatting.get('results', {})
        result_color = results_config.get('color', [255, 255, 100])
        result_bold = results_config.get('bold', True)
        
        result_pattern = re.compile(r'\b(1-0|0-1|1/2-1/2|\*)\b')
        result_parts = []
        i = 0
        in_tag = False
        in_header_span = False
        span_stack = []  # Stack to track span types: True if variation span, False otherwise
        
        while i < len(formatted):
            if formatted[i] == '<':
                # Check if this is a closing span tag first
                if i + 7 < len(formatted) and formatted[i:i+7] == '</span>':
                    # Closing span tag - pop from stack
                    if span_stack:
                        span_stack.pop()
                    in_tag = False
                    in_header_span = False
                    result_parts.append('</span>')
                    i += 7
                    continue
                # Check if this is opening a span
                elif i + 5 < len(formatted) and formatted[i:i+5] == '<span':
                    in_tag = True
                    tag_end = formatted.find('>', i)
                    if tag_end != -1:
                        tag_content = formatted[i:tag_end+1]
                        # Check if it's a header span
                        if 'color: rgb(100, 150, 255)' in tag_content:
                            in_header_span = True
                            span_stack.append(False)  # Header span
                        # Check if it's a variation span (has variation color and italic, but not comment color)
                        elif ('color: rgb(180, 180, 180)' in tag_content or 'font-style: italic' in tag_content) and 'color: rgb(180, 200, 255)' not in tag_content:
                            span_stack.append(True)  # Variation span
                        # Check if it's a comment span with italic (comment inside variation)
                        elif 'color: rgb(180, 200, 255)' in tag_content and 'font-style: italic' in tag_content:
                            # Comment span with italic means it's inside a variation - treat as variation context
                            span_stack.append(True)  # Comment in variation - treat as variation
                        # Check if it's any span with italic style (means it's in a variation)
                        elif 'font-style: italic' in tag_content:
                            # Any span with italic is in a variation context
                            span_stack.append(True)
                        else:
                            # Other span (comment, move number, etc.) - keep existing variation context
                            # If we're already in a variation, this span is also in variation context
                            span_stack.append(True in span_stack if span_stack else False)
                    else:
                        span_stack.append(False)
                    result_parts.append(formatted[i])
                    i += 1
                else:
                    # Other HTML tag
                    in_tag = True
                    result_parts.append(formatted[i])
                    i += 1
            elif formatted[i] == '>':
                in_tag = False
                result_parts.append(formatted[i])
                i += 1
            elif not in_tag and not in_header_span and not (True in span_stack):
                # Only format results if we're not in a variation context (check stack)
                match = result_pattern.match(formatted, i)
                if match:
                    result_formatted = span(match.group(0), result_color, result_bold)
                    result_parts.append(result_formatted)
                    i = match.end()
                else:
                    result_parts.append(formatted[i])
                    i += 1
            else:
                result_parts.append(formatted[i])
                i += 1
        
        formatted = ''.join(result_parts)
        
        # Replace newlines with spaces for natural text flow
        # This allows the QTextEdit to handle word wrapping naturally
        formatted = formatted.replace('\n', ' ').replace('\r', ' ')
        
        # Clean up multiple consecutive spaces
        formatted = re.sub(r' +', ' ', formatted)
        
        # Add line break between last tag and first move if tags exist
        # Find where headers end and moves begin by looking for header closing bracket
        def add_break_after_last_tag(text: str) -> str:
            """Add <br> after last header tag before first move."""
            # Headers are formatted as: <span...>[Header]</span>
            # Find pattern: ]</span> (end of header) followed by move number span
            # This is more reliable than just </span> because it specifically identifies header spans
            pattern = r'(\]</span>)(\s*)(<span[^>]*>)(\s*)(\d+\.)'
            
            matches = list(re.finditer(pattern, text))
            if matches:
                # Use the LAST match (last header before first move)
                last_match = matches[-1]
                # Insert <br> right after the closing span of the header
                pos = last_match.end(1)
                return text[:pos] + '<br>' + text[pos:]
            
            # Fallback: Look for ]</span> followed by whitespace and then digit+period
            pattern2 = r'(\]</span>)(\s+)(\d+\.)'
            matches2 = list(re.finditer(pattern2, text))
            if matches2:
                # Use the LAST match
                last_match = matches2[-1]
                pos = last_match.end(1)
                return text[:pos] + '<br>' + text[pos:]
            
            # Additional fallback: any </span> followed by move number span (in case headers don't have ])
            pattern3 = r'(</span>)(\s*)(<span[^>]*>)(\s*)(\d+\.)'
            matches3 = list(re.finditer(pattern3, text))
            if matches3:
                # Use the LAST match
                last_match = matches3[-1]
                pos = last_match.end(1)
                return text[:pos] + '<br>' + text[pos:]
            
            return text
        
        formatted = add_break_after_last_tag(formatted)
        
        # Extract move information for each ply
        # This is used by the view to find moves in the rendered document
        move_info_list = []  # Store move information for each ply
        
        if not parsed_moves:
            return (formatted, [])
        
        # Build move_info list from parsed moves
        for ply_index, move_san, move_number, is_white in parsed_moves:
            move_info_list.append((move_san, move_number, is_white))
        
        # Return formatted HTML and move info
        return (formatted, move_info_list)
    
    @staticmethod
    def _format_variations_with_moves(
        formatted: str,
        variation_color: list,
        variation_italic: bool,
        span_func,
        comment_color: list,
        nags_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """Format variations by parsing individual moves within them.
        
        Args:
            formatted: PGN text with comments already formatted.
            variation_color: Color for variation moves and parentheses.
            variation_italic: Whether variation moves should be italic.
            span_func: Function to create HTML spans.
            comment_color: Color used for comment spans (to avoid reformatting comment content).
            
        Returns:
            Formatted text with variation moves individually styled.
        """
        result_parts = []
        i = 0
        in_header = False  # Track if we're inside a header [Key "Value"]
        in_header_span = False  # Track if we're inside a header span (already formatted)
        comment_color_css = f"color: rgb({comment_color[0]}, {comment_color[1]}, {comment_color[2]})"
        comment_span_depth = 0  # Track nesting of comment spans
        
        while i < len(formatted):
            # Check if we're inside an HTML tag - if so, skip it
            if formatted[i] == '<':
                # Check if this is a closing span tag
                if i + 7 < len(formatted) and formatted[i:i+7] == '</span>':
                    # If we were in a header span, exit it
                    if in_header_span:
                        in_header_span = False
                    if comment_span_depth > 0:
                        comment_span_depth -= 1
                    result_parts.append('</span>')
                    i += 7
                    continue
                # Check if this is an opening span tag
                elif i + 5 < len(formatted) and formatted[i:i+5] == '<span':
                    # Find the end of the HTML tag
                    tag_end = formatted.find('>', i)
                    if tag_end != -1:
                        tag_content = formatted[i:tag_end+1]
                        # Check if it's a header span (has header color)
                        if 'color: rgb(100, 150, 255)' in tag_content:
                            in_header_span = True
                        if comment_color_css in tag_content:
                            comment_span_depth += 1
                        # Copy the entire tag
                        result_parts.append(formatted[i:tag_end + 1])
                        i = tag_end + 1
                        continue
                    else:
                        # No closing > found, treat as regular character
                        result_parts.append(formatted[i])
                        i += 1
                else:
                    # Other HTML tag - find the end of the HTML tag
                    tag_end = formatted.find('>', i)
                    if tag_end != -1:
                        # Copy the entire tag
                        result_parts.append(formatted[i:tag_end + 1])
                        i = tag_end + 1
                        continue
                    else:
                        # No closing > found, treat as regular character
                        result_parts.append(formatted[i])
                        i += 1
            elif formatted[i] == '[':
                # Start of header - skip header content
                in_header = True
                result_parts.append(formatted[i])
                i += 1
            elif formatted[i] == ']':
                # End of header
                in_header = False
                result_parts.append(formatted[i])
                i += 1
            elif formatted[i] == '(' and not in_header and not in_header_span and comment_span_depth == 0:
                # Found potential start of variation
                
                # Found start of variation - need to check if it's inside HTML
                # Look backwards to see if we're inside a tag
                # Simple check: if we see '<' before the '(' without a '>', we're in a tag
                # But more reliably, we check if '(' is actually a raw character, not in HTML
                
                # Find the end of this variation, skipping HTML tags and headers
                start = i
                depth = 0
                found_end = False
                j = i
                
                while j < len(formatted):
                    if formatted[j] == '<':
                        # Skip to end of HTML tag
                        tag_end = formatted.find('>', j)
                        if tag_end != -1:
                            j = tag_end + 1
                            continue
                        else:
                            j += 1
                    elif formatted[j] == '[':
                        # Skip header content
                        header_end = formatted.find(']', j)
                        if header_end != -1:
                            j = header_end + 1
                            continue
                        else:
                            j += 1
                    elif formatted[j] == '(':
                        depth += 1
                        j += 1
                    elif formatted[j] == ')':
                        depth -= 1
                        if depth == 0:
                            end = j + 1
                            
                            # Extract variation content (without parentheses)
                            variation_content = formatted[start + 1:end - 1]
                            
                            # Check if this is actually NAG text (like " (poor move)" or " (unknown NAG 146)")
                            # NAG text has a space before the opening paren and contains NAG meaning text
                            # IMPORTANT: NAG text should be short and simple, not a full variation with moves
                            is_nag_text = False
                            
                            # Strip HTML tags to get plain text for comparison
                            content_without_html = re.sub(r'<[^>]+>', '', variation_content).strip()
                            
                            # Only check for NAG text if content is short (NAG text is typically < 50 chars)
                            # Variations with moves are much longer
                            if len(content_without_html) < 50 and start > 0 and formatted[start - 1] == ' ':
                                # Check if content matches NAG text patterns
                                # Build NAG patterns (same logic as in NAG text styling)
                                # Note: variation_content is the text INSIDE parentheses (without the parens)
                                nag_meanings_list = list(set(NAG_MEANINGS.values()))
                                nag_meanings_list.sort(key=len, reverse=True)
                                escaped_meanings = [re.escape(meaning) for meaning in nag_meanings_list]
                                unknown_nag_pattern = r'unknown NAG \d+'
                                all_patterns = escaped_meanings + [unknown_nag_pattern]
                                
                                if all_patterns:
                                    nag_meanings_pattern = '|'.join(all_patterns)
                                    # Match the content (without HTML, without parentheses) against NAG patterns
                                    nag_text_pattern = re.compile('^' + nag_meanings_pattern + '$')
                                    if nag_text_pattern.match(content_without_html):
                                        is_nag_text = True
                            
                            # Also check if content is already styled as NAG (has NAG color span)
                            # This handles the case where NAG text styling already happened before variations
                            # But only if content is short (to avoid false positives with variations)
                            if not is_nag_text and len(content_without_html) < 50 and nags_config:
                                nag_color = nags_config.get('color', [200, 200, 255])
                                nag_color_css = f'color: rgb({nag_color[0]}, {nag_color[1]}, {nag_color[2]})'
                                # Only treat as NAG if the content is mostly/entirely NAG text
                                # Check if content has moves (numbers followed by dots), it's not NAG text
                                if nag_color_css in variation_content:
                                    has_moves = re.search(r'\d+\.', content_without_html)
                                    if not has_moves:
                                        is_nag_text = True
                            
                            if is_nag_text:
                                # This is NAG text, not a variation - skip it (will be styled later)
                                result_parts.append(formatted[start:end])
                                i = end
                                found_end = True
                                break
                            
                            # Format the opening parenthesis with variation styling
                            result_parts.append(span_func('(', variation_color, italic=variation_italic))
                            
                            # Format moves within the variation
                            formatted_variation = PgnFormatterService._format_moves_in_variation(
                                variation_content, variation_color, variation_italic, span_func
                            )
                            
                            result_parts.append(formatted_variation)
                            
                            # Format the closing parenthesis with variation styling
                            result_parts.append(span_func(')', variation_color, italic=variation_italic))
                            
                            i = end
                            found_end = True
                            break
                        else:
                            j += 1
                    else:
                        j += 1
                
                if not found_end:
                    # No closing parenthesis found, treat as regular character
                    result_parts.append(formatted[i])
                    i += 1
            else:
                # Regular character (including inside headers)
                result_parts.append(formatted[i])
                i += 1
        
        return ''.join(result_parts)
    
    @staticmethod
    def _format_moves_in_variation(
        text: str,
        variation_color: list,
        variation_italic: bool,
        span_func
    ) -> str:
        """Format individual moves in variation text.
        
        Args:
            text: Text containing moves to format (within a variation).
                May already contain HTML spans from comments.
            variation_color: Color for variation moves.
            variation_italic: Whether variation moves should be italic.
            span_func: Function to create HTML spans.
            
        Returns:
            Formatted text with moves individually styled.
        """
        # Pattern to match moves in variations
        # Matches: optional move number (e.g., "13. " or "13... "), then move SAN, preserving whitespace after
        # Move SAN can include: piece, source square, capture, destination, promotion, check/mate, annotations
        move_pattern = re.compile(
            r'(?:(\d+\.\s+)|(\d+\.\.\.\s+))?'  # Optional move number like "13. " or "13... " (with space)
            r'([NBRQK]?[a-h]?[1-8]?[x\-]?[a-h][1-8]'  # Basic move pattern
            r'(?:[=][NBRQ])?'  # Promotion
            r'(?:[+#]|e\.p\.)?'  # Check, mate, or en passant
            r'[!?]{0,2})'  # Optional annotations
            r'(\s*)'  # Capture trailing whitespace
        )
        
        result_parts = []
        i = 0
        
        while i < len(text):
            # Check if we're currently inside HTML (between < and >)
            in_html = False
            last_open = text.rfind('<', 0, i)
            last_close = text.rfind('>', 0, i)
            if last_open != -1 and last_open > last_close:
                in_html = True
            
            if in_html:
                # We're inside HTML, just copy characters until we exit
                i += 1
                continue
            
            # Skip HTML tags entirely - don't format moves inside HTML
            if text[i] == '<':
                # Find the end of the HTML tag
                tag_end = text.find('>', i)
                if tag_end != -1:
                    # Copy everything from current position to end of tag (including content)
                    # But we need to find the matching closing tag
                    tag_start = i
                    tag_name_match = re.match(r'<(\w+)', text[i:tag_end + 1])
                    if tag_name_match:
                        tag_name = tag_name_match.group(1)
                        # Find the closing tag
                        closing_tag = f'</{tag_name}>'
                        closing_pos = text.find(closing_tag, tag_end + 1)
                        if closing_pos != -1:
                            # Copy the entire tag with its content
                            result_parts.append(text[tag_start:closing_pos + len(closing_tag)])
                            i = closing_pos + len(closing_tag)
                            continue
                    
                    # No closing tag found, or self-closing, just copy the tag
                    result_parts.append(text[i:tag_end + 1])
                    i = tag_end + 1
                    continue
                else:
                    # No closing > found, treat as regular character
                    result_parts.append(text[i])
                    i += 1
            else:
                # Try to match a move starting at position i
                match = move_pattern.match(text, i)
                if match:
                    # Add text before the match
                    if match.start() > i:
                        result_parts.append(text[i:match.start()])
                    
                    # Format the move with variation styling (including move number if present)
                    # The pattern captures: (white_move_number?), (black_move_number?), (move_san), (trailing_whitespace)
                    white_move_number = match.group(1)  # May be None
                    black_move_number = match.group(2)  # May be None
                    move_san = match.group(3)
                    trailing_whitespace = match.group(4) if match.lastindex >= 4 else ''
                    
                    # Format move number with variation styling if present
                    move_number = white_move_number or black_move_number
                    if move_number:
                        result_parts.append(span_func(move_number.rstrip(), variation_color, italic=variation_italic))
                        result_parts.append(' ')  # Add space after move number
                    
                    # Format move SAN with variation styling
                    result_parts.append(span_func(move_san, variation_color, italic=variation_italic))
                    
                    # Preserve trailing whitespace
                    if trailing_whitespace:
                        result_parts.append(trailing_whitespace)
                    
                    i = match.end()
                    continue
                
                # Not a match - preserve the character (could be NAG text, punctuation, etc.)
                result_parts.append(text[i])
                i += 1
        
        return ''.join(result_parts)
    
    @staticmethod
    def _extract_move_positions_from_pgn(pgn_text: str) -> List[Tuple[int, str, int, bool]]:
        """Extract move information from PGN text.
        
        Args:
            pgn_text: Plain PGN text string.
            
        Returns:
            List of (ply_index, move_san, move_number, is_white) tuples.
            ply_index: 1-based ply (1 = after first move, 2 = after second move, etc.)
            move_san: Move SAN notation
            move_number: Move number (1, 2, 3, etc.)
            is_white: True if white's move, False if black's move
        """
        moves = []
        
        try:
            import chess.pgn
            
            pgn_io = io.StringIO(pgn_text)
            chess_game = chess.pgn.read_game(pgn_io)
            
            if chess_game is None:
                return []
            
            # Traverse game tree to extract moves
            node = chess_game
            ply_index = 0
            
            while node.variations:
                next_node = node.variation(0)
                board_before = node.board()
                move_san = board_before.san(next_node.move)
                
                is_white = board_before.turn == chess.WHITE
                move_number = (ply_index + 1) // 2 + 1 if is_white else (ply_index + 1) // 2
                
                ply_index += 1
                moves.append((ply_index, move_san, move_number, is_white))
                
                node = next_node
        except Exception as e:
            # On any error, return empty list
            # Note: This is intentionally silent to avoid breaking formatting
            # if PGN parsing fails
            logging_service = LoggingService.get_instance()
            logging_service.warning(f"Failed to extract move positions from PGN: {e}", exc_info=e)
        
        return moves
