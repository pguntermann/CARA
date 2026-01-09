"""PGN parsing service for processing chess games from PGN text."""

import chess.pgn
import io
import json
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable, Tuple
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed


class PgnParseResult:
    """Result of parsing PGN text."""
    
    def __init__(self, success: bool, games: List[Dict[str, Any]] = None, error_message: str = "") -> None:
        """Initialize parse result.
        
        Args:
            success: True if parsing was successful, False otherwise.
            games: List of parsed game data dictionaries.
            error_message: Error message if parsing failed.
        """
        self.success = success
        self.games = games if games is not None else []
        self.error_message = error_message


def _parse_game_chunk(game_chunk: str) -> Optional[Dict[str, Any]]:
    """Parse a single game chunk and extract game data (must be top-level for pickling).
    
    Args:
        game_chunk: PGN text string for a single game.
        
    Returns:
        Dictionary with game data or None if parsing fails or game is invalid.
    """
    try:
        pgn_io = io.StringIO(game_chunk)
        game = chess.pgn.read_game(pgn_io)
        
        if game is None:
            return None
        
        return PgnService._extract_game_data(game)
    except Exception:
        return None


class PgnService:
    """Service for parsing PGN text into game data.
    
    This service handles parsing PGN text using python-chess and extracting
    game metadata and move data.
    """
    
    # Cache for PGN export configuration (loaded lazily on first use)
    _export_config_cache: Optional[Tuple[bool, int]] = None
    
    @staticmethod
    def _normalize_pgn_text(pgn_text: str, progress_callback: Optional[Callable[[int, str], None]] = None, 
                            progress_start: int = 0, progress_end: int = 20) -> str:
        """Normalize PGN text for parsing.
        
        This method handles normalization that must run sequentially before parallel parsing.
        It normalizes blank lines, removes invisible characters, and ensures proper game separators.
        
        Args:
            pgn_text: Raw PGN text string.
            progress_callback: Optional callback function(progress: int, message: str) for progress updates.
                             Progress is reported as percentage (0-100) within the progress_start to progress_end range.
            progress_start: Starting progress percentage for this phase (default: 0).
            progress_end: Ending progress percentage for this phase (default: 20).
            
        Returns:
            Normalized PGN text string.
        """
        # Strip trailing whitespace/newlines to avoid parsing empty games
        pgn_text = pgn_text.rstrip()
        
        # Remove zero-width spaces and other invisible unicode characters that might interfere
        pgn_text = re.sub(r'[\u200B-\u200D\uFEFF]', '', pgn_text)
        
        # Normalize blank lines in PGN to prevent python-chess from splitting games incorrectly
        # Python-chess can misinterpret multiple blank lines as game separators
        # Strategy: Remove blank lines inside comments, but preserve blank lines between headers
        # Also: Insert blank lines when headers appear directly after moves (missing game separators)
        lines = pgn_text.split('\n')
        total_lines = len(lines)
        normalized_lines = []
        in_headers = True
        in_moves = False  # Track if we're currently in move notation
        last_was_header = False
        last_was_blank = False
        comment_depth = 0  # Track nesting depth of comments (count of { minus })
        
        # Progress update frequency: update every N lines or at key milestones
        # For large files, update every 1% of lines or every 1000 lines, whichever is more frequent
        update_interval = max(1, min(1000, total_lines // 100)) if total_lines > 0 else 1000
        
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            is_blank = not line_stripped
            is_header = line_stripped.startswith('[')
            is_move_line = line_stripped and (line_stripped[0].isdigit() or line_stripped.startswith('*'))
            
            # Check comment depth BEFORE processing this line
            inside_comment = comment_depth > 0
            # Count comment braces to track if we're inside a comment
            comment_depth += line.count('{') - line.count('}')
            
            # If we see a header, we're in header section
            if is_header:
                # If we were in moves and this header appears without a blank line, insert one
                # This handles files that don't have blank lines between games
                if in_moves and not last_was_blank:
                    # We're transitioning from moves to a new game's headers
                    # Insert a blank line to help python-chess recognize the game boundary
                    if normalized_lines and normalized_lines[-1] != '':
                        normalized_lines.append('')
                
                in_headers = True
                in_moves = False
                last_was_header = True
                last_was_blank = False
                # If we just had a blank line before this header, it's a game separator - keep it
                # But don't add duplicate blank lines
                if last_was_blank and normalized_lines and normalized_lines[-1] == '':
                    # Keep the blank line before the header (game separator)
                    normalized_lines.append(line)
                else:
                    # Normal header line
                    normalized_lines.append(line)
            # If we see a move notation (starts with number), we're past headers
            elif is_move_line:
                in_headers = False
                in_moves = True
                last_was_header = False
                last_was_blank = False
                normalized_lines.append(line)
            # For blank lines
            elif is_blank:
                last_was_blank = True
                if inside_comment:
                    # Blank line inside comment - skip it (prevents game splitting)
                    pass
                elif in_headers:
                    # Blank line between headers - keep it (helps python-chess parse headers correctly)
                    # Only add if previous line wasn't blank (avoid consecutive blanks)
                    if normalized_lines and normalized_lines[-1] != '':
                        normalized_lines.append('')
                elif in_moves:
                    # Blank line after moves - might be game separator
                    # Only add if previous line wasn't blank (avoid consecutive blanks)
                    if normalized_lines and normalized_lines[-1] != '':
                        normalized_lines.append('')
            else:
                # Other content (comments, etc.)
                # If it's not a header and not a move, we're likely in moves section
                # (comments, annotations, etc. appear within move notation)
                in_headers = False
                if not is_blank:
                    # Non-blank content that's not a header or move is likely part of move notation
                    in_moves = True
                last_was_header = False
                last_was_blank = False
                normalized_lines.append(line)
            
            # Report progress periodically
            if progress_callback and (i == 0 or i == total_lines - 1 or i % update_interval == 0):
                # Calculate progress percentage within this phase's range
                if total_lines > 0:
                    line_progress = (i + 1) / total_lines
                    progress_percent = progress_start + int(line_progress * (progress_end - progress_start))
                    progress_percent = min(progress_end, max(progress_start, progress_percent))
                else:
                    progress_percent = progress_start
                
                progress_callback(
                    progress_percent,
                    f"Normalizing PGN text... ({i + 1}/{total_lines} lines)"
                )
        
        # Join back with single newlines
        return '\n'.join(normalized_lines)
    
    @staticmethod
    def _detect_game_boundaries(normalized_pgn: str, progress_callback: Optional[Callable[[int, str], None]] = None,
                                progress_start: int = 20, progress_end: int = 40) -> List[Tuple[int, int]]:
        """Detect game boundaries in normalized PGN text using pattern-based detection.
        
        This method uses pattern matching to detect game boundaries by scanning for:
        - Header tags: [Tag "value"] format
        - Move notation: Numbered moves (1., 2., etc.) or game termination markers
        - Game termination: 1-0, 0-1, 1/2-1/2, or *
        
        Handles games with headers, games without headers, comments, variations, and edge cases.
        Much faster than full parsing while maintaining accuracy.
        
        Args:
            normalized_pgn: Normalized PGN text string.
            progress_callback: Optional callback function(progress: int, message: str) for progress updates.
                             Progress is reported as percentage (0-100) within the progress_start to progress_end range.
            progress_start: Starting progress percentage for this phase (default: 20).
            progress_end: Ending progress percentage for this phase (default: 40).
            
        Returns:
            List of (start_index, end_index) tuples for each game (line indices).
        """
        boundaries = []
        lines = normalized_pgn.split('\n')
        total_lines = len(lines)
        
        if total_lines == 0:
            return boundaries
        
        # Patterns for detection
        # Header pattern: [Tag "value"] or [Tag 'value'] - must be at start of line (after whitespace)
        header_pattern = re.compile(r'^\s*\[([A-Za-z][A-Za-z0-9_]*)\s+"[^"]*"\]\s*$')
        # Alternative header format with single quotes (less common but valid)
        header_pattern_alt = re.compile(r"^\s*\[([A-Za-z][A-Za-z0-9_]*)\s+'[^']*'\]\s*$")
        
        # Move notation pattern: starts with number followed by dot (1., 2., etc.)
        # Must not be inside a comment or variation
        move_pattern = re.compile(r'\b([1-9]\d{0,2}|0)\.(?:\.\.| |\w)')
        
        # Game termination markers: 1-0, 0-1, 1/2-1/2, or *
        # These must appear at the end of move notation (not in comments/variations)
        termination_pattern = re.compile(r'\b(1-0|0-1|1/2-1/2|\*)\b')
        
        # State tracking
        game_start_line = None
        in_headers = False
        in_moves = False
        comment_depth = 0  # Track nested comments { }
        variation_depth = 0  # Track nested variations ( )
        game_count = 0
        
        # Optimized line position tracking: build cumulative line lengths
        # This avoids the expensive character-to-line mapping
        line_lengths = [len(line) + 1 for line in lines]  # +1 for newline
        cumulative_lengths = [0]
        for length in line_lengths:
            cumulative_lengths.append(cumulative_lengths[-1] + length)
        
        for line_idx, line in enumerate(lines):
            line_stripped = line.strip()
            is_blank = not line_stripped
            
            # Track comment and variation depth
            # Count braces and parentheses to know if we're inside comments/variations
            # We need to check depth BEFORE updating to know if we're entering/exiting comments/variations
            inside_comment_before = comment_depth > 0
            inside_variation_before = variation_depth > 0
            
            # Update depth
            comment_depth += line.count('{') - line.count('}')
            variation_depth += line.count('(') - line.count(')')
            
            # Ensure depth never goes negative (handles malformed PGN)
            comment_depth = max(0, comment_depth)
            variation_depth = max(0, variation_depth)
            
            # Check if we're inside a comment or variation AFTER updating depth
            # This handles cases where comments/variations open and close on the same line
            inside_comment = comment_depth > 0
            inside_variation = variation_depth > 0
            
            # Detect header line
            is_header = bool(header_pattern.match(line) or header_pattern_alt.match(line))
            
            # Detect move notation (only if not inside comment/variation)
            # Check both before and after to handle comments that span lines
            has_move_notation = False
            if not inside_comment and not inside_variation:
                has_move_notation = bool(move_pattern.search(line_stripped))
            
            # Detect termination marker (only if not inside comment/variation and in moves section)
            # IMPORTANT: We need to check that we're not inside a comment/variation
            # AND that the termination marker is not inside a comment/variation on this line
            # To do this properly, we need to check if the termination is actually outside comments/variations
            has_termination = False
            if in_moves and not inside_comment and not inside_variation:
                # Check if termination marker exists in the line
                termination_match = termination_pattern.search(line_stripped)
                if termination_match:
                    # Verify the termination marker is not inside a comment or variation
                    # by checking the position relative to braces/parentheses
                    term_pos = termination_match.start()
                    # Count braces and parentheses before the termination marker
                    before_term = line_stripped[:term_pos]
                    comment_count_before = before_term.count('{') - before_term.count('}')
                    variation_count_before = before_term.count('(') - before_term.count(')')
                    # If we're not inside a comment/variation and counts are balanced, it's valid
                    if comment_count_before == 0 and variation_count_before == 0:
                        has_termination = True
            
            # Game start detection
            if game_start_line is None:
                # Start a new game if we see:
                # 1. A header line (game with headers)
                # 2. Move notation (game without headers)
                if is_header:
                    game_start_line = line_idx
                    in_headers = True
                    in_moves = False
                elif has_move_notation:
                    # Game without headers - starts directly with moves
                    game_start_line = line_idx
                    in_headers = False
                    in_moves = True
            elif in_headers and is_header:
                # We're already in headers and see another header
                # This could be:
                # 1. Continuation of current game's headers (normal case)
                # 2. Start of next game if previous game had only headers
                # Check if there was a blank line separator or if we're transitioning
                # For now, treat as continuation (will be handled by blank line detection)
                pass
            
            # State transitions
            elif in_headers:
                # We're in headers section
                if is_header:
                    # Continue in headers
                    pass
                elif has_move_notation:
                    # Transition from headers to moves
                    in_headers = False
                    in_moves = True
                elif is_blank:
                    # Blank line in headers - might be separator, but continue current game
                    # (normalization should have handled this, but be safe)
                    # If next line is a header, we'll detect it as a new game start
                    pass
            
            elif in_moves:
                # We're in moves section
                if has_termination:
                    # Found game termination marker - end this game AT THIS LINE (include termination)
                    boundaries.append((game_start_line, line_idx))
                    game_count += 1
                    
                    # Report progress
                    if progress_callback:
                        if total_lines > 0:
                            line_progress = (line_idx + 1) / total_lines
                            progress_percent = progress_start + int(line_progress * (progress_end - progress_start))
                            progress_percent = min(progress_end, max(progress_start, progress_percent))
                        else:
                            progress_percent = progress_start
                        
                        if game_count <= 5 or game_count % 10 == 0:
                            progress_callback(
                                progress_percent,
                                f"Detecting game boundaries... (found {game_count} game(s))"
                            )
                    
                    # Reset for next game - IMPORTANT: Skip blank line check for this iteration
                    game_start_line = None
                    in_headers = False
                    in_moves = False
                    # Continue to next iteration - don't process blank lines or headers this iteration
                    continue
                elif is_header:
                    # Header appears directly while in moves (no blank line separator)
                    # This means previous game ended without termination marker
                    # End current game at previous line (before this header)
                    if game_start_line is not None:
                        # Find last non-blank line before this header
                        end_line = line_idx - 1
                        while end_line >= game_start_line and not lines[end_line].strip():
                            end_line -= 1
                        
                        if end_line >= game_start_line:
                            boundaries.append((game_start_line, end_line))
                            game_count += 1
                            
                            # Report progress
                            if progress_callback:
                                if total_lines > 0:
                                    line_progress = line_idx / total_lines
                                    progress_percent = progress_start + int(line_progress * (progress_end - progress_start))
                                    progress_percent = min(progress_end, max(progress_start, progress_percent))
                                else:
                                    progress_percent = progress_start
                                
                                if game_count <= 5 or game_count % 10 == 0:
                                    progress_callback(
                                        progress_percent,
                                        f"Detecting game boundaries... (found {game_count} game(s))"
                                    )
                    
                    # Start new game with this header
                    game_start_line = line_idx
                    in_headers = True
                    in_moves = False
                    # Continue to next iteration - don't process blank lines this iteration
                    continue
            
            # Handle edge case: blank line between games (header appears on next line)
            # This handles games ending without termination marker, followed by blank line + header
            # Only check if we haven't already processed termination or header in this iteration
            if is_blank and game_start_line is not None and not has_termination:
                # Check if next non-blank line is a header (indicates next game)
                if line_idx + 1 < total_lines:
                    # Find next non-blank line
                    next_non_blank_idx = line_idx + 1
                    while next_non_blank_idx < total_lines and not lines[next_non_blank_idx].strip():
                        next_non_blank_idx += 1
                    
                    if next_non_blank_idx < total_lines:
                        next_line = lines[next_non_blank_idx].strip()
                        is_next_header = bool(header_pattern.match(next_line) or header_pattern_alt.match(next_line))
                        
                        if is_next_header:
                            # Next game starts - end current game at last non-blank line
                            # Find last non-blank line before this blank line
                            end_line = line_idx - 1
                            while end_line >= game_start_line and not lines[end_line].strip():
                                end_line -= 1
                            
                            if end_line >= game_start_line:
                                boundaries.append((game_start_line, end_line))
                                game_count += 1
                                
                                # Report progress
                                if progress_callback:
                                    if total_lines > 0:
                                        line_progress = (line_idx + 1) / total_lines
                                        progress_percent = progress_start + int(line_progress * (progress_end - progress_start))
                                        progress_percent = min(progress_end, max(progress_start, progress_percent))
                                    else:
                                        progress_percent = progress_start
                                    
                                    if game_count <= 5 or game_count % 10 == 0:
                                        progress_callback(
                                            progress_percent,
                                            f"Detecting game boundaries... (found {game_count} game(s))"
                                        )
                            
                            # Will start new game when we reach next_non_blank_idx
                            game_start_line = None
                            in_headers = False
                            in_moves = False
        
        # Handle last game if file doesn't end with termination marker
        if game_start_line is not None:
            # Last game ends at last line
            boundaries.append((game_start_line, total_lines - 1))
            game_count += 1
            
            # Final progress update
            if progress_callback:
                progress_callback(
                    progress_end,
                    f"Detecting game boundaries... (found {game_count} game(s))"
                )
        
        return boundaries
    
    @staticmethod
    def _split_into_chunks(normalized_pgn: str, boundaries: List[Tuple[int, int]]) -> List[str]:
        """Split normalized PGN into individual game chunks.
        
        Args:
            normalized_pgn: Normalized PGN text string.
            boundaries: List of (start_index, end_index) tuples from _detect_game_boundaries.
            
        Returns:
            List of game PGN strings, one per chunk.
        """
        lines = normalized_pgn.split('\n')
        chunks = []
        
        for start_idx, end_idx in boundaries:
            chunk_lines = lines[start_idx:end_idx + 1]
            chunk = '\n'.join(chunk_lines)
            chunks.append(chunk)
        
        return chunks
    
    @staticmethod
    def parse_pgn_text(pgn_text: str, progress_callback: Optional[Callable[[int, str], None]] = None) -> PgnParseResult:
        """Parse PGN text and extract game data using parallel processing.
        
        This method normalizes the PGN text sequentially, then splits it into game chunks
        and parses them in parallel using ProcessPoolExecutor.
        
        Args:
            pgn_text: PGN text string (can contain multiple games).
            progress_callback: Optional callback function(progress: int, message: str) for progress updates.
                             Progress is reported as percentage (0-100) across all phases:
                             - Normalization: 0-20%
                             - Boundary Detection: 20-40%
                             - Splitting: 40-42%
                             - Parsing: 42-100%
            
        Returns:
            PgnParseResult with parsed game data or error message.
        """
        if not pgn_text or not pgn_text.strip():
            return PgnParseResult(False, error_message="Empty PGN text")
        
        try:
            # Allocate progress percentages across phases:
            # Phase 1 (Normalization): 0-20%
            # Phase 2 (Boundary Detection): 20-40%
            # Phase 3 (Splitting): 40-42% (quick phase)
            # Phase 4 (Parsing): 42-100%
            
            # Phase 1: Normalize PGN text (sequential, required)
            normalized_pgn = PgnService._normalize_pgn_text(
                pgn_text, 
                progress_callback=progress_callback,
                progress_start=0,
                progress_end=20
            )
            
            # Phase 2: Detect game boundaries (sequential, fast)
            boundaries = PgnService._detect_game_boundaries(
                normalized_pgn,
                progress_callback=progress_callback,
                progress_start=20,
                progress_end=40
            )
            
            if not boundaries:
                return PgnParseResult(False, error_message="No valid games found in PGN text")
            
            # Phase 3: Split into chunks (sequential, fast)
            if progress_callback:
                progress_callback(41, f"Splitting into {len(boundaries)} game(s)...")
            
            chunks = PgnService._split_into_chunks(normalized_pgn, boundaries)
            
            if progress_callback:
                progress_callback(42, f"Prepared {len(chunks)} game(s) for parsing...")
            
            # Phase 4: Parse chunks in parallel
            total_games = len(chunks)
            
            # Calculate number of worker processes (reserve 1-2 cores for UI)
            cpu_count = os.cpu_count() or 4
            max_workers = max(1, cpu_count - 2)
            
            games: List[Optional[Dict[str, Any]]] = [None] * total_games
            completed_count = 0
            
            executor = None
            try:
                executor = ProcessPoolExecutor(max_workers=max_workers)
                
                # Submit all chunks for processing
                future_to_index = {
                    executor.submit(_parse_game_chunk, chunk): i
                    for i, chunk in enumerate(chunks)
                }
                
                # Process results as they complete
                for future in as_completed(future_to_index):
                    index = future_to_index[future]
                    
                    try:
                        game_data = future.result()
                        games[index] = game_data
                    except Exception as e:
                        # Skip failed games
                        games[index] = None
                    
                    completed_count += 1
                    if progress_callback:
                        # Progress from 42% to 100% for parsing phase
                        # Reserve 42% for normalization/boundary detection/splitting
                        parsing_progress = 42 + int((completed_count / total_games) * 58) if total_games > 0 else 42
                        parsing_progress = min(100, max(42, parsing_progress))
                        progress_callback(
                            parsing_progress,
                            f"Parsed {completed_count}/{total_games} game(s)..."
                        )
            finally:
                # Ensure executor is properly shut down
                if executor:
                    executor.shutdown(wait=True)
            
            # Filter out None values (failed/invalid games) and maintain order
            valid_games = [g for g in games if g is not None]
            
            if len(valid_games) == 0:
                return PgnParseResult(False, error_message="No valid games found in PGN text")
            
            return PgnParseResult(True, games=valid_games)
            
        except Exception as e:
            return PgnParseResult(False, error_message=f"Error parsing PGN: {str(e)}")
    
    @staticmethod
    def _get_export_config() -> Tuple[bool, int]:
        """Get PGN export configuration from config.json (cached).
        
        Returns:
            Tuple of (use_fixed_width: bool, fixed_width: int).
        """
        if PgnService._export_config_cache is None:
            try:
                # Read config file directly without validation to avoid potential issues
                config_dir = Path(__file__).parent.parent / "config"
                config_path = config_dir / "config.json"
                
                if config_path.exists():
                    with open(config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    pgn_config = config.get('pgn', {}).get('export', {})
                    use_fixed_width = pgn_config.get('use_fixed_width', True)
                    fixed_width = pgn_config.get('fixed_width', 80)
                    PgnService._export_config_cache = (use_fixed_width, fixed_width)
                else:
                    # Config file doesn't exist - use defaults
                    PgnService._export_config_cache = (True, 80)
            except Exception:
                # Any error reading config - use defaults
                PgnService._export_config_cache = (True, 80)
        return PgnService._export_config_cache
    
    @staticmethod
    def _normalize_pgn_line_breaks(pgn_text: str, use_fixed_width: bool, fixed_width: int) -> str:
        """Normalize line breaks in PGN move notation.
        
        Args:
            pgn_text: PGN text from StringExporter.
            use_fixed_width: If True, enforce fixed width; if False, single line.
            fixed_width: Character width limit when use_fixed_width is True.
            
        Returns:
            Normalized PGN text with line breaks adjusted.
        """
        try:
            # Split into headers and move notation
            parts = pgn_text.split('\n\n', 1)
            if len(parts) < 2:
                return pgn_text  # No move section, return as-is
            
            headers = parts[0]
            moves = parts[1]
            
            if not use_fixed_width:
                # Single line: remove all line breaks in move notation
                moves_normalized = moves.replace('\n', ' ').replace('  ', ' ').strip()
            else:
                # Fixed width: remove premature line breaks (before width limit)
                # First, remove all line breaks and rebuild with proper width enforcement
                moves_single_line = moves.replace('\n', ' ').replace('  ', ' ').strip()
                
                # Now rebuild with proper line breaks at width limit
                normalized_lines = []
                words = moves_single_line.split(' ')
                current_line = ''
                
                for word in words:
                    if not word:
                        continue
                    
                    # Check if adding this word would exceed width
                    if current_line:
                        test_line = current_line + ' ' + word
                    else:
                        test_line = word
                    
                    if len(test_line) <= fixed_width:
                        # Can add to current line
                        if current_line:
                            current_line += ' ' + word
                        else:
                            current_line = word
                    else:
                        # Would exceed width - start new line
                        if current_line:
                            normalized_lines.append(current_line)
                        current_line = word
                
                # Add the last line if it exists
                if current_line:
                    normalized_lines.append(current_line)
                
                # Join normalized lines back together
                moves_normalized = '\n'.join(normalized_lines)
            
            # Rejoin headers and moves
            return headers + '\n\n' + moves_normalized
        except Exception:
            # If normalization fails for any reason, return original text
            return pgn_text
    
    @staticmethod
    def export_game_to_pgn(chess_game: chess.pgn.Game) -> str:
        """Export chess.pgn.Game to PGN string with consistent formatting.
        
        This method centralizes PGN export logic to ensure consistent formatting
        across the application. All StringExporter usage should go through this method
        to enable future formatting fixes (e.g., line break handling).
        
        Args:
            chess_game: chess.pgn.Game instance to export.
            
        Returns:
            PGN string representation of the game.
        """
        # Get cached export configuration
        use_fixed_width, fixed_width = PgnService._get_export_config()
        
        # Export with appropriate column setting
        if use_fixed_width:
            exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True, columns=fixed_width)
        else:
            exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True, columns=None)
        
        pgn_text = chess_game.accept(exporter).strip()
        
        # Normalize line breaks based on configuration
        return PgnService._normalize_pgn_line_breaks(pgn_text, use_fixed_width, fixed_width)
    
    @staticmethod
    def _extract_game_data(game: chess.pgn.Game) -> Optional[Dict[str, Any]]:
        """Extract game data from a chess.pgn.Game object.
        
        Args:
            game: chess.pgn.Game instance.
            
        Returns:
            Dictionary with game data or None if extraction fails or game is empty.
        """
        try:
            # Extract metadata from game headers
            headers = game.headers
            
            # Check if this is an empty game (no headers and no moves)
            # If there are no headers at all and no variations, it's likely an empty/invalid game
            if not headers and not game.variations:
                return None
            
            white = headers.get("White", "")
            black = headers.get("Black", "")
            result = headers.get("Result", "")
            date = headers.get("Date", "")
            eco = headers.get("ECO", "")
            event = headers.get("Event", "")
            site = headers.get("Site", "")
            white_elo = headers.get("WhiteElo", "")
            black_elo = headers.get("BlackElo", "")
            
            # Count moves (main line only)
            # Count half-moves (plies) in the main line
            move_count = 0
            node = game
            while node.variations:
                # Follow main line (first variation)
                node = node.variation(0)
                move_count += 1
            # Convert plies to moves (divide by 2, round up)
            # A full move = white move + black move = 2 plies
            move_count = (move_count + 1) // 2
            
            # Note: PlyCount header might be incorrect in some PGNs
            # We rely on actual move counting rather than trusting the header
            # The PlyCount header is informational and may not always be accurate
            
            # Extract PGN text for this game
            # Export the game as PGN string
            game_pgn = PgnService.export_game_to_pgn(game)
            
            # Check if CARAAnalysisData tag exists (check both headers and exported PGN for robustness)
            # Check headers first (most reliable)
            analyzed = "CARAAnalysisData" in headers
            if not analyzed:
                analyzed = "[CARAAnalysisData" in game_pgn
            
            annotated = "CARAAnnotations" in headers
            if not annotated:
                annotated = "[CARAAnnotations" in game_pgn
            
            # Validate that we have meaningful game data
            # If the PGN is empty or too short, skip it
            # But be lenient - some valid games might be short (e.g., just headers)
            if not game_pgn:
                return None
            # Only filter out extremely short PGNs that are likely empty
            if len(game_pgn.strip()) < 5:
                return None
            
            # Simple filter: if a game has 0 moves, filter it out
            # Games without moves are incomplete/empty
            has_moves = move_count > 0
            
            if not has_moves:
                # No moves - filter out empty/incomplete games
                return None
            
            # Additional validation: if a game claims to have moves, verify the PGN contains move notation
            # This helps catch cases where python-chess parsed something but it's not a real game
            if has_moves:
                pgn_has_move_notation = '1.' in game_pgn or '1-0' in game_pgn or '0-1' in game_pgn or '1/2-1/2' in game_pgn
                
                # If we think we have moves but the PGN string doesn't contain move notation, something's wrong
                if not pgn_has_move_notation:
                    # Inconsistency - we counted moves but no move notation in PGN
                    # This indicates an invalid game where move counting failed
                    return None
            
            return {
                "white": white,
                "black": black,
                "result": result,
                "date": date,
                "moves": move_count,
                "eco": eco,
                "pgn": game_pgn,
                "event": event,
                "site": site,
                "white_elo": white_elo,
                "black_elo": black_elo,
                "analyzed": analyzed,
                "annotated": annotated
            }
            
        except Exception:
            # If extraction fails, return None (this game will be skipped)
            return None

