"""PGN parsing service for processing chess games from PGN text."""

import chess.pgn
import io
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime


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


class PgnService:
    """Service for parsing PGN text into game data.
    
    This service handles parsing PGN text using python-chess and extracting
    game metadata and move data.
    """
    
    @staticmethod
    def parse_pgn_text(pgn_text: str, progress_callback: Optional[Callable[[int, str], None]] = None) -> PgnParseResult:
        """Parse PGN text and extract game data.
        
        Args:
            pgn_text: PGN text string (can contain multiple games).
            
        Returns:
            PgnParseResult with parsed game data or error message.
        """
        if not pgn_text or not pgn_text.strip():
            return PgnParseResult(False, error_message="Empty PGN text")
        
        try:
            # Strip trailing whitespace/newlines to avoid parsing empty games
            pgn_text = pgn_text.rstrip()
            
            # Remove zero-width spaces and other invisible unicode characters that might interfere
            import re
            pgn_text = re.sub(r'[\u200B-\u200D\uFEFF]', '', pgn_text)
            
            # Normalize blank lines in PGN to prevent python-chess from splitting games incorrectly
            # Python-chess can misinterpret multiple blank lines as game separators
            # Strategy: Remove blank lines between headers and moves, but keep one blank line between games
            # Also: Insert blank lines when headers appear directly after moves (missing game separators)
            lines = pgn_text.split('\n')
            normalized_lines = []
            in_headers = True
            in_moves = False  # Track if we're currently in move notation
            last_was_header = False
            last_was_blank = False
            
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                is_blank = not line_stripped
                is_header = line_stripped.startswith('[')
                is_move_line = line_stripped and (line_stripped[0].isdigit() or line_stripped.startswith('*'))
                
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
                    if last_was_header:
                        # Blank line after headers - skip it (don't add)
                        pass
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
            
            # Join back with single newlines
            normalized_pgn = '\n'.join(normalized_lines)
            
            # Create a StringIO object from the normalized PGN text
            pgn_io = io.StringIO(normalized_pgn)
            
            games = []
            
            # Parse games one by one (python-chess can parse multiple games)
            while True:
                # Save current position before reading
                pos_before = pgn_io.tell()
                
                # Check if we're at the end or only whitespace remains before reading
                peek_content = pgn_io.read(1)
                if not peek_content:
                    # End of file
                    break
                # Seek back to read the full game
                pgn_io.seek(pos_before)
                
                # Check if only whitespace remains by reading ahead
                peek_ahead = pgn_io.read(100)
                pgn_io.seek(pos_before)
                if not peek_ahead.strip():
                    # Only whitespace remains, stop parsing
                    break
                
                game = chess.pgn.read_game(pgn_io)
                if game is None:
                    # No more games
                    break
                
                # Check position after reading - if we didn't advance, something is wrong
                pos_after = pgn_io.tell()
                if pos_after == pos_before:
                    # Stream didn't advance, break to avoid infinite loop
                    break
                
                # Extract game data (this will filter out empty/invalid games)
                game_data = PgnService._extract_game_data(game)
                if game_data:
                    games.append(game_data)
                    # Call progress callback if provided
                    if progress_callback:
                        progress_callback(len(games), f"Parsed {len(games)} game(s)...")
                    # Continue to next game - don't break early
                    # python-chess will handle the blank line between games
                else:
                    # Game was filtered out as invalid
                    # Continue parsing in case there are more valid games
                    pass
            
            if len(games) == 0:
                return PgnParseResult(False, error_message="No valid games found in PGN text")
            
            return PgnParseResult(True, games=games)
            
        except Exception as e:
            return PgnParseResult(False, error_message=f"Error parsing PGN: {str(e)}")
    
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
            exporter = chess.pgn.StringExporter(headers=True, variations=True, comments=True)
            game_pgn = game.accept(exporter).strip()
            
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

