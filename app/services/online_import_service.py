"""Service for importing games from online chess platforms (Lichess, Chess.com)."""

import requests
from typing import Optional, List, Dict, Any, Tuple, Callable
from datetime import datetime, timedelta
from io import StringIO
import json
from app.services.logging_service import LoggingService


class OnlineImportService:
    """Service for importing games from online chess platforms."""
    
    # Lichess API endpoints
    LICHESS_API_BASE = "https://lichess.org/api"
    LICHESS_GAMES_ENDPOINT = f"{LICHESS_API_BASE}/games/user"
    
    # Chess.com API endpoints
    CHESSCOM_API_BASE = "https://api.chess.com/pub"
    CHESSCOM_ARCHIVES_ENDPOINT = f"{CHESSCOM_API_BASE}/player"
    
    # Rate limiting
    LICHESS_RATE_LIMIT = 200  # requests per 10 seconds
    CHESSCOM_RATE_LIMIT = 10000  # requests per day (informal)
    
    # Required headers for API requests
    # Both APIs require User-Agent header to prevent 403 errors
    # Version is dynamically set based on config
    @staticmethod
    def _get_headers(version: str = "2.4.0") -> Dict[str, str]:
        """Get HTTP headers for API requests.
        
        Args:
            version: Application version string (defaults to 2.4.0 if not provided).
            
        Returns:
            Dictionary of HTTP headers.
        """
        return {
            "User-Agent": f"CARA/{version}",
            "Accept": "application/json, application/x-ndjson"
        }
    
    @staticmethod
    def import_lichess_games(
        username: str,
        max_games: Optional[int] = None,
        since_date: Optional[datetime] = None,
        until_date: Optional[datetime] = None,
        perf_type: Optional[str] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        version: str = "2.4.0"
    ) -> Tuple[bool, str, List[str]]:
        """Import games from Lichess.
        
        Args:
            username: Lichess username.
            max_games: Maximum number of games to import (None = all).
            since_date: Import games from this date onwards (None = no limit).
            until_date: Import games until this date (None = no limit).
            perf_type: Game type filter (e.g., "blitz", "rapid", "classical", None = all).
            progress_callback: Optional callback function(status_message: str, progress_percent: int).
            
        Returns:
            Tuple of (success: bool, message: str, pgn_list: List[str]).
            If success is True, message contains success info and pgn_list contains PGN strings.
            If success is False, message contains error description and pgn_list is empty.
        """
        try:
            if progress_callback:
                progress_callback("Connecting to Lichess API...", 0)
            
            # Build request parameters
            params = {
                "max": max_games if max_games else 999999,  # Large number for "all"
                "pgnInJson": True,  # Get JSON format with PGN field (easier to parse)
                "tags": True,
                "clocks": True,
                "evals": False,
                "opening": True,
                "moves": True
            }
            
            # Add date filters
            if since_date:
                params["since"] = int(since_date.timestamp() * 1000)  # Lichess uses milliseconds
            if until_date:
                params["until"] = int(until_date.timestamp() * 1000)
            if perf_type:
                params["perfType"] = perf_type
            
            # Make API request
            url = f"{OnlineImportService.LICHESS_GAMES_ENDPOINT}/{username}"
            
            if progress_callback:
                progress_callback(f"Fetching games from Lichess for user '{username}'...", 10)
            
            # Log Lichess API call
            logging_service = LoggingService.get_instance()
            filter_str = f", max={max_games}" if max_games else ""
            filter_str += f", since={since_date}" if since_date else ""
            filter_str += f", until={until_date}" if until_date else ""
            filter_str += f", perf_type={perf_type}" if perf_type else ""
            logging_service.info(f"Lichess API call: username={username}{filter_str}")
            
            response = requests.get(
                url,
                params=params,
                headers=OnlineImportService._get_headers(version),
                stream=True,
                timeout=30
            )
            response.raise_for_status()
            
            # Read NDJSON response (newline-delimited JSON)
            # Each line is a JSON object with a "pgn" field
            pgn_list = []
            line_count = 0
            
            if progress_callback:
                progress_callback("Parsing game data...", 30)
            
            for line in response.iter_lines(decode_unicode=True):
                if not line.strip():
                    continue
                
                try:
                    game_data = json.loads(line)
                    if "pgn" in game_data:
                        pgn_list.append(game_data["pgn"])
                        line_count += 1
                        
                        # Update progress
                        if progress_callback and line_count % 10 == 0:
                            progress = min(90, 30 + int((line_count / (max_games or 1000)) * 60))
                            progress_callback(f"Parsed {line_count} game(s)...", progress)
                except json.JSONDecodeError:
                    # Skip invalid JSON lines
                    continue
                except Exception as e:
                    # Log but continue
                    logging_service = LoggingService.get_instance()
                    logging_service.warning(f"Error parsing game line: {e}", exc_info=e)
                    continue
            
            if progress_callback:
                progress_callback("Import complete", 100)
            
            if not pgn_list:
                return (False, f"No games found for user '{username}'", [])
            
            # Log Lichess import result
            logging_service = LoggingService.get_instance()
            logging_service.info(f"Lichess import completed: username={username}, {len(pgn_list)} game(s) fetched")
            
            return (True, f"Successfully imported {len(pgn_list)} game(s) from Lichess", pgn_list)
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error connecting to Lichess API: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
                if status_code == 404:
                    error_msg = f"User '{username}' not found on Lichess"
                elif status_code == 403:
                    error_msg = "Access forbidden. This may be due to rate limiting or API restrictions."
                elif status_code == 429:
                    error_msg = "Rate limit exceeded. Please try again later."
            elif "404" in str(e):
                error_msg = f"User '{username}' not found on Lichess"
            elif "403" in str(e) or "Forbidden" in str(e):
                error_msg = "Access forbidden. This may be due to rate limiting or API restrictions."
            elif "429" in str(e):
                error_msg = "Rate limit exceeded. Please try again later."
            return (False, error_msg, [])
        except Exception as e:
            return (False, f"Unexpected error importing from Lichess: {str(e)}", [])
    
    @staticmethod
    def import_chesscom_games(
        username: str,
        max_games: Optional[int] = None,
        since_date: Optional[datetime] = None,
        until_date: Optional[datetime] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        version: str = "2.4.0"
    ) -> Tuple[bool, str, List[str]]:
        """Import games from Chess.com.
        
        Args:
            username: Chess.com username.
            max_games: Maximum number of games to import (None = all).
            since_date: Import games from this date onwards (None = no limit).
            until_date: Import games until this date (None = no limit).
            progress_callback: Optional callback function(status_message: str, progress_percent: int).
            
        Returns:
            Tuple of (success: bool, message: str, pgn_list: List[str]).
            If success is True, message contains success info and pgn_list contains PGN strings.
            If success is False, message contains error description and pgn_list is empty.
        """
        try:
            if progress_callback:
                progress_callback("Connecting to Chess.com API...", 0)
            
            # Get list of available archives
            archives_url = f"{OnlineImportService.CHESSCOM_ARCHIVES_ENDPOINT}/{username}/games/archives"
            
            if progress_callback:
                progress_callback(f"Fetching archive list for user '{username}'...", 5)
            
            # Log Chess.com API call
            logging_service = LoggingService.get_instance()
            filter_str = f", max={max_games}" if max_games else ""
            filter_str += f", since={since_date}" if since_date else ""
            filter_str += f", until={until_date}" if until_date else ""
            logging_service.info(f"Chess.com API call: username={username}{filter_str}")
            
            archives_response = requests.get(
                archives_url,
                headers=OnlineImportService._get_headers(version),
                timeout=30
            )
            archives_response.raise_for_status()
            
            archives_data = archives_response.json()
            if "archives" not in archives_data:
                return (False, f"User '{username}' not found on Chess.com or has no games", [])
            
            archives = archives_data["archives"]
            
            if progress_callback:
                progress_callback(f"Found {len(archives)} monthly archive(s)...", 10)
            
            # Filter archives by date range if specified
            if since_date or until_date:
                filtered_archives = []
                for archive_url in archives:
                    # Extract year/month from URL (format: .../games/YYYY/MM)
                    parts = archive_url.split("/")
                    if len(parts) >= 2:
                        try:
                            year = int(parts[-2])
                            month = int(parts[-1])
                            archive_date = datetime(year, month, 1)
                            
                            # Check if within date range
                            if since_date:
                                # Archive date is first day of month, check if month is before since_date
                                next_month = archive_date + timedelta(days=32)
                                next_month = next_month.replace(day=1)
                                if next_month <= since_date:
                                    continue
                            if until_date:
                                # Check if archive month starts after until_date
                                if archive_date > until_date:
                                    continue
                            
                            filtered_archives.append(archive_url)
                        except (ValueError, IndexError):
                            # Skip invalid URLs
                            continue
                archives = filtered_archives
            
            if not archives:
                return (False, "No archives found in the specified date range", [])
            
            # Fetch games from each archive
            pgn_list = []
            total_archives = len(archives)
            games_imported = 0
            
            for idx, archive_url in enumerate(archives):
                if max_games and games_imported >= max_games:
                    break
                
                if progress_callback:
                    # Progress based on archives processed (10-80% range)
                    progress = 10 + int((idx / total_archives) * 70)
                    progress_callback(f"Fetching archive {idx + 1}/{total_archives} (found {games_imported} games so far)...", progress)
                
                try:
                    archive_response = requests.get(
                        archive_url,
                        headers=OnlineImportService._get_headers(version),
                        timeout=60  # Increased timeout for large archives
                    )
                    archive_response.raise_for_status()
                    
                    # Process events after fetching archive to keep UI responsive
                    if progress_callback:
                        # Call processEvents through callback if possible
                        # The callback in database_controller already calls processEvents
                        pass
                    
                    archive_data = archive_response.json()
                    if "games" not in archive_data:
                        continue
                    
                    archive_games = archive_data["games"]
                    archive_game_count = len(archive_games)
                    
                    if progress_callback:
                        progress_callback(f"Processing archive {idx + 1}/{total_archives} ({archive_game_count} games, {games_imported} total so far)...", 
                                        min(90, 10 + int(((idx + 0.5) / total_archives) * 70)))
                    
                    # Process games in the archive
                    for game_idx, game in enumerate(archive_games):
                        if max_games and games_imported >= max_games:
                            break
                        
                        # Check date filters for individual games (only if needed)
                        if since_date or until_date:
                            # More efficient date extraction - check PGN string directly
                            pgn_text = game.get("pgn", "")
                            if pgn_text:
                                # Find Date tag in PGN (format: [Date "YYYY.MM.DD"] or other formats)
                                date_start = pgn_text.find('[Date "')
                                if date_start != -1:
                                    date_start += 7  # Skip '[Date "'
                                    date_end = pgn_text.find('"]', date_start)
                                    if date_end != -1:
                                        date_str = pgn_text[date_start:date_end]
                                        if date_str and date_str != "???":
                                            # Parse date using same logic as database model (handles multiple formats)
                                            game_date = OnlineImportService._parse_pgn_date(date_str)
                                            if game_date:
                                                # Date successfully parsed - apply filters
                                                if since_date and game_date < since_date:
                                                    continue
                                                if until_date and game_date >= until_date:
                                                    continue
                                            else:
                                                # Date parsing failed - skip game to be safe
                                                continue
                                else:
                                    # No Date tag found - skip game when filtering by date
                                    continue
                        
                        # Extract PGN from game data
                        if "pgn" in game:
                            pgn_list.append(game["pgn"])
                            games_imported += 1
                            
                            # Update progress more frequently for better responsiveness
                            # This is critical to prevent UI freezing on large archives
                            if progress_callback:
                                # Update every game for first 100, then every 10-25 games depending on archive size
                                # For large archives (>100 games), update every 10 games
                                # For smaller archives, update every 25 games
                                update_frequency = 10 if archive_game_count > 100 else 25
                                should_update = (
                                    games_imported <= 100 or
                                    games_imported % update_frequency == 0 or
                                    (game_idx + 1) == archive_game_count or  # Always update at end of archive
                                    (game_idx + 1) % 50 == 0  # Also update every 50 games regardless
                                )
                                
                                if should_update:
                                    # Progress calculation: 10-85% for archives and games
                                    # Since we don't know total games, use archive progress + incremental
                                    archive_progress = 10 + int((idx / total_archives) * 70)
                                    # Add small increment based on games in current archive
                                    archive_completion = (game_idx + 1) / archive_game_count if archive_game_count > 0 else 0
                                    game_progress_increment = int(archive_completion * 5)  # Up to 5% per archive
                                    progress = min(95, archive_progress + game_progress_increment)
                                    progress_callback(f"Imported {games_imported} game(s) from archive {idx + 1}/{total_archives}...", progress)
                
                except requests.exceptions.RequestException as e:
                    # Log but continue with other archives
                    logging_service = LoggingService.get_instance()
                    logging_service.warning(f"Error fetching archive {archive_url}: {e}", exc_info=e)
                    if progress_callback:
                        progress_callback(f"Warning: Error fetching archive {idx + 1}/{total_archives}, continuing...", 
                                        min(90, 10 + int((idx / total_archives) * 70)))
                    continue
                except Exception as e:
                    logging_service = LoggingService.get_instance()
                    logging_service.warning(f"Error processing archive {archive_url}: {e}", exc_info=e)
                    if progress_callback:
                        progress_callback(f"Warning: Error processing archive {idx + 1}/{total_archives}, continuing...", 
                                        min(90, 10 + int((idx / total_archives) * 70)))
                    continue
            
            if progress_callback:
                progress_callback("Import complete", 100)
            
            if not pgn_list:
                return (False, f"No games found for user '{username}' in the specified criteria", [])
            
            # Log Chess.com import result
            logging_service = LoggingService.get_instance()
            logging_service.info(f"Chess.com import completed: username={username}, {len(pgn_list)} game(s) fetched")
            
            return (True, f"Successfully imported {len(pgn_list)} game(s) from Chess.com", pgn_list)
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Error connecting to Chess.com API: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                status_code = e.response.status_code
                if status_code == 404:
                    error_msg = f"User '{username}' not found on Chess.com"
                elif status_code == 403:
                    error_msg = "Access forbidden. Chess.com requires a User-Agent header. Please ensure your application includes proper headers."
                elif status_code == 429:
                    error_msg = "Rate limit exceeded. Please try again later."
            elif "404" in str(e):
                error_msg = f"User '{username}' not found on Chess.com"
            elif "403" in str(e) or "Forbidden" in str(e):
                error_msg = "Access forbidden. Chess.com requires a User-Agent header. Please ensure your application includes proper headers."
            elif "429" in str(e):
                error_msg = "Rate limit exceeded. Please try again later."
            return (False, error_msg, [])
        except Exception as e:
            return (False, f"Unexpected error importing from Chess.com: {str(e)}", [])
    
    @staticmethod
    def _parse_pgn_date(date_str: str) -> Optional[datetime]:
        """Parse a PGN date string into a datetime object.
        
        PGN dates can be in various formats:
        - "YYYY.MM.DD" (year.month.day - most common)
        - "DD.MM.YYYY" (day.month.year - European format)
        - "YYYY.DD.MM" (year.day.month - alternative format)
        - "YYYY.MM" (year and month)
        - "YYYY" (year only)
        
        The method attempts to auto-detect the format by analyzing the values.
        
        Args:
            date_str: Date string from PGN Date tag.
            
        Returns:
            datetime object if parsing successful, None otherwise.
        """
        if not date_str or not date_str.strip():
            return None
        
        # Remove whitespace
        date_str = date_str.strip()
        
        # Split by dots
        parts = date_str.split('.')
        
        try:
            # Parse all parts as integers
            part1 = int(parts[0]) if len(parts) > 0 and parts[0] else 0
            part2 = int(parts[1]) if len(parts) > 1 and parts[1] else 0
            part3 = int(parts[2]) if len(parts) > 2 and parts[2] else 0
            
            # Auto-detect format based on values
            if len(parts) == 3:
                # Three-part date - try to detect format
                if part1 > 31 or part1 > 1900:
                    # First part is likely year (YYYY.MM.DD or YYYY.DD.MM)
                    if part2 <= 12 and part3 <= 31:
                        # YYYY.MM.DD format (most common)
                        return datetime(part1, part2, part3)
                    elif part2 <= 31 and part3 <= 12:
                        # YYYY.DD.MM format
                        return datetime(part1, part3, part2)
                    elif part2 > 12 and part3 <= 12:
                        # part2 > 12 can't be month, so likely YYYY.DD.MM
                        return datetime(part1, part3, part2)
                    else:
                        # Ambiguous - try YYYY.MM.DD and validate
                        try:
                            return datetime(part1, part2, part3)
                        except ValueError:
                            # Invalid date - return None
                            return None
                elif part3 > 31 or part3 > 1900:
                    # Third part is likely year (DD.MM.YYYY format)
                    return datetime(part3, part2, part1)
                else:
                    # Can't clearly identify - try YYYY.MM.DD
                    try:
                        return datetime(part1, part2, part3)
                    except ValueError:
                        return None
            elif len(parts) == 2:
                # Two-part date - assume YYYY.MM
                if part1 > 31 or part1 > 1900:
                    try:
                        return datetime(part1, part2, 1)
                    except ValueError:
                        return None
                else:
                    # Could be MM.YYYY - try that
                    try:
                        return datetime(part2, part1, 1)
                    except ValueError:
                        return None
            elif len(parts) == 1:
                # Single part - assume year
                try:
                    return datetime(part1, 1, 1)
                except ValueError:
                    return None
            else:
                return None
        except (ValueError, IndexError, TypeError):
            return None

