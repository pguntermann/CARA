"""Database controller for managing game database operations."""

import os
from typing import Dict, Any, Optional, List, Tuple
from collections import Counter
from datetime import datetime
import chess.pgn
from io import StringIO
from concurrent.futures import ProcessPoolExecutor, as_completed

from app.models.database_model import DatabaseModel, GameData
from app.models.database_panel_model import DatabasePanelModel
from app.services.pgn_service import PgnService


# Module-level translation table for PUA characters (Private Use Area: U+E000-U+F8FF)
# Created once for efficiency - these are ChessBase font characters that appear as blue boxes
_PUA_TRANSLATE_TABLE = str.maketrans('', '', ''.join(chr(i) for i in range(0xE000, 0xF900)))


def _read_pgn_file_with_encoding_detection(file_path: str, strip_pua_characters: bool = False) -> str:
    """Read a PGN file with automatic encoding detection.
    
    Uses charset-normalizer to detect the file encoding automatically,
    with fallback to UTF-8 if detection fails or confidence is low.
    
    Args:
        file_path: Path to the PGN file.
        strip_pua_characters: If True, removes Unicode Private Use Area characters
                             (U+E000-U+F8FF) which are ChessBase font symbols that
                             appear as blue boxes when fonts don't support them.
        
    Returns:
        File contents as a string.
        
    Raises:
        UnicodeDecodeError: If file cannot be decoded with detected or fallback encoding.
    """
    from charset_normalizer import from_bytes
    
    # Read file in binary mode
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    
    # Detect encoding using charset-normalizer
    detected = from_bytes(raw_data)
    
    decoded_text = None
    
    if detected and len(detected) > 0:
        # Get the best match (first result is the most confident)
        best_match = detected[0]
        encoding = best_match.encoding
        coherence = best_match.coherence
        
        # Use detected encoding if coherence is reasonable (>= 0.5)
        # Coherence ranges from 0.0 to 1.0, where higher values indicate better confidence
        # Otherwise fall back to UTF-8
        if coherence >= 0.5:
            try:
                decoded_text = raw_data.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                # If detected encoding fails, fall back to UTF-8
                pass
    
    # Fallback to UTF-8 with error handling
    if decoded_text is None:
        try:
            decoded_text = raw_data.decode('utf-8')
        except UnicodeDecodeError:
            # Last resort: try with error replacement to avoid complete failure
            decoded_text = raw_data.decode('utf-8', errors='replace')
    
    # Strip PUA characters if enabled
    if strip_pua_characters:
        decoded_text = decoded_text.translate(_PUA_TRANSLATE_TABLE)
    
    return decoded_text


def _read_and_parse_pgn_file(file_path: str, strip_pua_characters: bool = False) -> Tuple[str, bool, str, Optional[List[Dict[str, Any]]]]:
    """Read and parse a PGN file (must be top-level for pickling).
    
    Args:
        file_path: Path to the PGN file.
        strip_pua_characters: If True, removes Unicode Private Use Area characters
                             (U+E000-U+F8FF) which are ChessBase font symbols.
        
    Returns:
        Tuple of (file_path, success, message, games).
        If success is True, games is a list of parsed game dictionaries.
        If success is False, games is None and message contains error description.
    """
    try:
        # Read file with encoding detection
        pgn_text = _read_pgn_file_with_encoding_detection(file_path, strip_pua_characters=strip_pua_characters)
        
        # Parse PGN (no progress callback in parallel context)
        parse_result = PgnService.parse_pgn_text(pgn_text, progress_callback=None)
        
        if not parse_result.success:
            return (file_path, False, parse_result.error_message, None)
        
        if not parse_result.games or len(parse_result.games) == 0:
            return (file_path, False, "No valid PGN games found in file", None)
        
        return (file_path, True, "", parse_result.games)
    except Exception as e:
        return (file_path, False, f"Error reading/parsing file: {str(e)}", None)


class DatabaseController:
    """Controller for managing game database operations.
    
    This controller orchestrates database-related operations and manages
    the database model.
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """Initialize the database controller.
        
        Args:
            config: Configuration dictionary.
        """
        self.config = config
        
        # Initialize database model (clipboard database)
        self.database_model = DatabaseModel()
        
        # Initialize database panel model
        self.panel_model = DatabasePanelModel()
        
        # Add clipboard database to panel model
        self.panel_model.add_database(self.database_model, file_path=None)
        self.panel_model.set_active_database(self.database_model)  # Clipboard is default active
    
    def get_database_model(self) -> DatabaseModel:
        """Get the database model (clipboard database).
        
        Returns:
            The DatabaseModel instance for observing database state.
        """
        return self.database_model
    
    def get_panel_model(self) -> DatabasePanelModel:
        """Get the database panel model.
        
        Returns:
            The DatabasePanelModel instance for observing panel state.
        """
        return self.panel_model
    
    def mark_database_unsaved(self, model: DatabaseModel) -> None:
        """Mark a database as having unsaved changes.
        
        Args:
            model: DatabaseModel instance to mark as unsaved.
        """
        self.panel_model.mark_database_unsaved(model)
    
    def get_active_database(self) -> Optional[DatabaseModel]:
        """Get the currently active database.
        
        Returns:
            The active DatabaseModel instance, or None.
        """
        return self.panel_model.get_active_database()
    
    def set_active_database(self, database: Optional[DatabaseModel]) -> None:
        """Set the active database.
        
        Args:
            database: DatabaseModel instance to set as active.
        """
        self.panel_model.set_active_database(database)
    
    def format_pgn_error_message(self, error_message: str) -> str:
        """Format error message for PGN parsing failures.
        
        Args:
            error_message: The raw error message.
            
        Returns:
            Formatted error message string for display.
        """
        return f"Error: {error_message}"
    
    def parse_pgn_from_text(self, pgn_text: str) -> tuple[bool, str, Optional[int], int]:
        """Parse PGN text and add games to the database model.
        
        Args:
            pgn_text: PGN text string (can contain multiple games).
            
        Returns:
            Tuple of (success: bool, message: str, first_game_index: Optional[int], games_added: int).
            If success is True, message contains number of games parsed, first_game_index
            is the row index of the first game added, and games_added is the count.
            If success is False, message contains error description, first_game_index is None,
            and games_added is 0.
        """
        return self.parse_pgn_to_model(pgn_text, self.database_model)
    
    def parse_pgn_to_model(self, pgn_text: str, model: DatabaseModel) -> tuple[bool, str, Optional[int], int]:
        """Parse PGN text and add games to a specific database model.
        
        Args:
            pgn_text: PGN text string (can contain multiple games).
            model: DatabaseModel instance to add games to.
            
        Returns:
            Tuple of (success: bool, message: str, first_game_index: Optional[int], games_added: int).
            If success is True, message contains number of games parsed, first_game_index
            is the row index of the first game added, and games_added is the count.
            If success is False, message contains error description, first_game_index is None,
            and games_added is 0.
        """
        # Parse PGN text using service
        result = PgnService.parse_pgn_text(pgn_text)
        
        if not result.success:
            return (False, result.error_message, None, 0)
        
        # Track the starting count to determine which games were just added
        start_count = model.rowCount()
        
        # Add parsed games to the model
        games_added = 0
        for game_dict in result.games:
            game_data = GameData(
                game_number=0,  # Will be set by model when adding
                white=game_dict.get("white", ""),
                black=game_dict.get("black", ""),
                result=game_dict.get("result", ""),
                date=game_dict.get("date", ""),
                moves=game_dict.get("moves", 0),
                eco=game_dict.get("eco", ""),
                pgn=game_dict.get("pgn", ""),
                event=game_dict.get("event", ""),
                site=game_dict.get("site", ""),
                white_elo=game_dict.get("white_elo", ""),
                black_elo=game_dict.get("black_elo", ""),
                analyzed=game_dict.get("analyzed", False),
                annotated=game_dict.get("annotated", False),
                file_position=0,  # Pasted games don't have file position
            )
            # Extract tags from parsed game dict (already available, no parsing needed)
            tags = game_dict.get("tags", [])
            if not tags:
                raise ValueError(f"Tags missing from parsed game dict. This indicates a bug in PgnService._extract_game_data().")
            model.add_game(game_data, tags=tags)
            games_added += 1
        
        # The first game added is at start_count index
        first_game_index = start_count if games_added > 0 else None
        
        # Mark database as having unsaved changes if games were added
        if games_added > 0:
            self.panel_model.mark_database_unsaved(model)
        
        if games_added == 1:
            message = f"Parsed 1 game from PGN"
        else:
            message = f"Parsed {games_added} games from PGN"
        
        return (True, message, first_game_index, games_added)
    
    def clear_database(self) -> None:
        """Clear all games from the database model."""
        self.database_model.clear()
        # Mark database as saved (no unsaved changes when database is empty)
        self.panel_model.mark_database_saved(self.database_model)
    
    def get_game_count(self) -> int:
        """Get the number of games in the database.
        
        Returns:
            Number of games in the database.
        """
        return self.database_model.rowCount()
    
    def save_pgn_to_file(self, model: DatabaseModel, file_path: str) -> tuple[bool, str]:
        """Save all games from a database model to a PGN file.
        
        Args:
            model: DatabaseModel instance to save.
            file_path: Path to save the PGN file.
            
        Returns:
            Tuple of (success: bool, message: str).
            If success is True, message indicates success.
            If success is False, message contains error description.
        """
        from app.services.progress_service import ProgressService
        from PyQt6.QtWidgets import QApplication
        progress_service = ProgressService.get_instance()
        
        try:
            # Get all games from model
            games = model.get_all_games()
            if not games:
                return (False, "Cannot save: Database is empty")
            
            # Sort games by game_number in ascending order before saving
            # This ensures games are saved in the correct order (by their game numbers)
            games.sort(key=lambda game: game.game_number)
            
            total_games = len(games)
            
            # Show progress
            progress_service.show_progress()
            progress_service.set_indeterminate(False)
            progress_service.set_progress(0)
            progress_service.set_status(f"Saving {total_games} game(s) to file...")
            QApplication.processEvents()  # Process events to show progress bar
            
            # Write games incrementally to avoid memory issues with large databases
            # This avoids building the entire PGN string in memory
            try:
                from app.services.pgn_service import PgnService
                
                # Get export configuration for fixed_width formatting
                use_fixed_width, fixed_width = PgnService._get_export_config()
                
                with open(file_path, 'w', encoding='utf-8') as f:
                    for i, game in enumerate(games):
                        if game.pgn:
                            # Apply safer normalization that preserves PGN structure
                            # This respects fixed_width while preserving comments and variations
                            formatted_pgn = PgnService._normalize_pgn_line_breaks(
                                game.pgn, use_fixed_width, fixed_width
                            )
                            f.write(formatted_pgn.strip())
                            f.write("\n\n")  # Blank lines between games
                        
                        # Update progress every 10 games or on last game
                        should_update = (
                            (i + 1) <= 10 or  # First 10 games for immediate feedback
                            (i + 1) % 10 == 0 or  # Every 10 games after that
                            (i + 1) == total_games  # Always on last game
                        )
                        
                        if should_update:
                            progress_percent = int(((i + 1) / total_games) * 90)  # Reserve 10% for finalizing
                            progress_service.report_progress(
                                f"Saving game {i + 1}/{total_games}...",
                                progress_percent
                            )
                            QApplication.processEvents()  # Process events to update progress bar
                
                # Update status for cleanup
                progress_service.set_status("Finalizing...")
                progress_service.set_progress(95)
                QApplication.processEvents()  # Process events to update status
                
                # Clear all per-game unsaved indicators
                # This can be slow for large databases, so process events
                try:
                    model.clear_all_unsaved()
                    QApplication.processEvents()  # Process events after clearing unsaved
                except Exception as e:
                    # Log error but don't fail the save - file is already written
                    import sys
                    print(f"Warning: Error clearing unsaved indicators: {e}", file=sys.stderr)
                
                # Mark database as saved (clear unsaved changes flag)
                try:
                    self.panel_model.mark_database_saved(model)
                    QApplication.processEvents()  # Process events after marking saved
                except Exception as e:
                    # Log error but don't fail the save - file is already written
                    import sys
                    print(f"Warning: Error marking database as saved: {e}", file=sys.stderr)
                
            except MemoryError:
                progress_service.hide_progress()
                return (False, "Error: Out of memory while saving database. Database may be too large.")
            except IOError as e:
                progress_service.hide_progress()
                return (False, f"Error writing to file: {str(e)}")
            except OSError as e:
                progress_service.hide_progress()
                return (False, f"Error writing to file: {str(e)}")
            
            # Hide progress
            progress_service.hide_progress()
            QApplication.processEvents()  # Process events to hide progress bar
            
            return (True, f"PGN database saved to {file_path}")
            
        except Exception as e:
            # Hide progress on error
            progress_service.hide_progress()
            return (False, f"Error saving PGN database: {str(e)}")
    
    def add_pgn_database(self, file_path: str, games: List[GameData], tags_list: Optional[List[List[str]]] = None) -> DatabaseModel:
        """Add a new PGN database from file.
        
        Args:
            file_path: Path to the PGN file.
            games: List of games to populate the database.
            tags_list: Optional list of tag lists, one per game (must match games length).
                      If None, tags will be extracted from each game's PGN.
            
        Returns:
            The new DatabaseModel instance.
        """
        # Create new model with file path
        model = DatabaseModel(file_path=file_path)
        # Use batch addition for better performance
        # Don't mark as unsaved when loading from file (games are already saved)
        model.add_games_batch(games, mark_unsaved=False, tags_list=tags_list)
        
        # Add to panel model
        self.panel_model.add_database(model, file_path=file_path)
        
        return model
    
    def remove_pgn_database(self, file_path: str) -> bool:
        """Remove a PGN database by file path.
        
        Args:
            file_path: Path to the PGN file.
            
        Returns:
            True if database was removed, False if not found.
        """
        return self.panel_model.remove_database(file_path)
    
    def _close_database_by_identifier(self, identifier: str) -> bool:
        """Close a database by identifier and handle active database switching.
        
        This is a helper method that can be used to close any database,
        not just the active one. It handles the business logic of determining
        which database should become active after removal.
        
        Args:
            identifier: Database identifier to close.
            
        Returns:
            True if database was closed, False if not found or cannot be closed.
        """
        if not identifier or identifier == "clipboard" or identifier == "search_results":
            return False
        
        # Determine which database should become active before removing
        new_active_model = self._determine_new_active_database(identifier)
        
        # Remove the database (this will set active_database to None in the model if it was active)
        removed = self.panel_model.remove_database(identifier)
        
        if removed:
            # Set the new active database (if one exists)
            if new_active_model is not None:
                self.panel_model.set_active_database(new_active_model)
            else:
                # No other database tabs exist - set Clipboard as active
                clipboard_model = self.panel_model.get_database_by_identifier("clipboard")
                if clipboard_model:
                    self.panel_model.set_active_database(clipboard_model)
                else:
                    # Fallback: set to None if clipboard doesn't exist (shouldn't happen)
                    self.panel_model.set_active_database(None)
        
        return removed
    
    def close_active_pgn_database(self) -> bool:
        """Close the currently active PGN database and switch to the previous one.
        
        This method handles the business logic of determining which database should
        become active when the current one is closed, following the pattern:
        - Switch to the previous database tab if one exists
        - Otherwise switch to the next database tab if one exists
        - Otherwise set active to None (will fall back to Clipboard)
        
        Returns:
            True if a PGN database was closed, False if no active PGN database to close.
        """
        active_database = self.panel_model.get_active_database()
        if not active_database:
            return False
        
        # Find identifier for the active database
        identifier = self.panel_model.find_database_by_model(active_database)
        if not identifier:
            return False
        
        return self._close_database_by_identifier(identifier)
    
    def close_all_pgn_databases(self) -> int:
        """Close all PGN databases except clipboard and search results.
        
        This method closes all file-based databases while preserving the clipboard
        and search results tabs. After closing all databases, the clipboard will
        be set as the active database.
        
        Returns:
            Number of databases closed.
        """
        # Get all databases
        all_databases = self.panel_model.get_all_databases()
        
        # Filter to only file-based databases (exclude clipboard and search_results)
        databases_to_close = [
            identifier for identifier, info in all_databases.items()
            if identifier != "clipboard" and identifier != "search_results"
        ]
        
        if not databases_to_close:
            return 0
        
        # Close each database (helper handles active database switching)
        closed_count = 0
        for identifier in databases_to_close:
            if self._close_database_by_identifier(identifier):
                closed_count += 1
        
        # Final state: ensure clipboard is active (in case all were closed)
        clipboard_model = self.panel_model.get_database_by_identifier("clipboard")
        if clipboard_model:
            self.panel_model.set_active_database(clipboard_model)
        
        return closed_count
    
    def _determine_new_active_database(self, removed_identifier: str) -> Optional[DatabaseModel]:
        """Determine which database should become active when a database is removed.
        
        Args:
            removed_identifier: Identifier of the database being removed.
            
        Returns:
            DatabaseModel instance to set as active, or None if no other database tabs exist.
        """
        # Get all databases (dict maintains insertion order in Python 3.7+)
        all_databases = self.panel_model.get_all_databases()
        
        # Filter out clipboard and the removed database, maintaining order
        database_identifiers = [
            identifier for identifier, info in all_databases.items()
            if identifier != "clipboard" and identifier != removed_identifier
        ]
        
        if not database_identifiers:
            # No other database tabs exist (only Clipboard)
            return None
        
        # Find the position of the removed database in the original list
        all_identifiers = list(all_databases.keys())
        try:
            removed_index = all_identifiers.index(removed_identifier)
        except ValueError:
            # Should not happen, but handle gracefully
            removed_index = -1
        
        # Try to find previous database (one that appears before removed in insertion order)
        previous_identifier = None
        for identifier in reversed(database_identifiers):
            # Check if this identifier appears before the removed one in the original order
            try:
                identifier_index = all_identifiers.index(identifier)
                if identifier_index < removed_index:
                    previous_identifier = identifier
                    break
            except ValueError:
                continue
        
        if previous_identifier is not None:
            # Found previous database - use it
            info = all_databases.get(previous_identifier)
            if info:
                return info.model
        
        # No previous database found - use the first remaining database
        if database_identifiers:
            first_identifier = database_identifiers[0]
            info = all_databases.get(first_identifier)
            if info:
                return info.model
        
        # No other database tabs exist
        return None
    
    def get_database_by_file_path(self, file_path: str) -> Optional[DatabaseModel]:
        """Get database model by file path.
        
        Args:
            file_path: Path to the PGN file.
            
        Returns:
            DatabaseModel instance or None if not found.
        """
        return self.panel_model.get_database_by_identifier(file_path)
    
    def open_pgn_database(self, file_path: str) -> tuple[bool, str, Optional[GameData]]:
        """Open a PGN database from file.
        
        This method handles reading the file, parsing PGN, converting to GameData,
        adding the database, and setting it as active.
        
        Args:
            file_path: Path to the PGN file to open.
            
        Returns:
            Tuple of (success: bool, message: str, first_game: Optional[GameData]).
            If success is True, message indicates success and first_game is the first
            game in the database (or None if no games).
            If success is False, message contains error description and first_game is None.
        """
        from app.services.progress_service import ProgressService
        from PyQt6.QtWidgets import QApplication
        progress_service = ProgressService.get_instance()
        
        try:
            # Show progress and status for reading file
            progress_service.show_progress()
            progress_service.set_indeterminate(True)
            progress_service.set_status(f"Reading PGN file: {file_path}")
            QApplication.processEvents()  # Process events to show the progress bar
            
            # Read config setting for PUA character stripping
            strip_pua = self.config.get('pgn', {}).get('import', {}).get('strip_pua_characters', True)
            
            # Read file with encoding detection
            pgn_text = _read_pgn_file_with_encoding_detection(file_path, strip_pua_characters=strip_pua)
            
            # Update status for parsing
            progress_service.set_status("Parsing PGN games...")
            QApplication.processEvents()  # Process events to update status
            
            # Define progress callback for parsing
            def parsing_progress(progress_value: int, message: str) -> None:
                """Update progress during parsing.
                
                Args:
                    progress_value: Progress percentage (0-100) for all phases.
                    message: Status message to display.
                """
                progress_service.set_status(message)
                # All phases now report percentage-based progress
                progress_service.set_progress(progress_value)
                progress_service.set_indeterminate(False)
                # Update UI periodically to avoid excessive processing
                # Update more frequently for early phases (normalization/boundary detection)
                # which report progress more often
                if progress_value <= 42 or progress_value % 5 == 0:
                    QApplication.processEvents()  # Process events to update status
            
            # Parse PGN with progress callback
            parse_result = PgnService.parse_pgn_text(pgn_text, progress_callback=parsing_progress)
            
            if not parse_result.success:
                progress_service.hide_progress()
                error_message = self.format_pgn_error_message(parse_result.error_message)
                return (False, error_message, None)
            
            # Verify at least one valid game was parsed
            if not parse_result.games or len(parse_result.games) == 0:
                progress_service.hide_progress()
                return (False, "Error: No valid PGN games found in file", None)
            
            total_games = len(parse_result.games)
            
            # Switch to determinate progress for converting games
            progress_service.set_indeterminate(False)
            progress_service.set_progress(0)
            progress_service.set_status(f"Processing {total_games} game(s)...")
            QApplication.processEvents()  # Process events to update status
            
            # Convert parsed games to GameData instances
            games = []
            tags_list = []  # Collect tags for batch addition
            for file_pos, game_dict in enumerate(parse_result.games, start=1):
                game_data = GameData(
                    game_number=0,  # Will be set by model when adding
                    white=game_dict.get("white", ""),
                    black=game_dict.get("black", ""),
                    result=game_dict.get("result", ""),
                    date=game_dict.get("date", ""),
                    moves=game_dict.get("moves", 0),
                    eco=game_dict.get("eco", ""),
                    pgn=game_dict.get("pgn", ""),
                    event=game_dict.get("event", ""),
                    site=game_dict.get("site", ""),
                    white_elo=game_dict.get("white_elo", ""),
                    black_elo=game_dict.get("black_elo", ""),
                    analyzed=game_dict.get("analyzed", False),
                    annotated=game_dict.get("annotated", False),
                    file_position=file_pos,  # Store original file position (1-based)
                )
                games.append(game_data)
                # Extract tags from parsed game dict (already available, no parsing needed)
                tags = game_dict.get("tags", [])
                tags_list.append(tags)
                
                # Update progress more frequently for better feedback
                # Update every 10 games, or every game for first 10, or on last game
                should_update = (
                    file_pos <= 10 or  # First 10 games for immediate feedback
                    file_pos % 10 == 0 or  # Every 10 games after that
                    file_pos == total_games  # Always on last game
                )
                
                if should_update:
                    progress_percent = int((file_pos / total_games) * 100)
                    progress_service.report_progress(
                        f"Processing game {file_pos}/{total_games}...",
                        progress_percent
                    )
                    QApplication.processEvents()  # Process events to update progress bar
            
            # Update status for adding to database
            progress_service.set_status("Adding games to database...")
            QApplication.processEvents()  # Process events to update status
            
            # Add database to panel model (pass tags to avoid re-parsing)
            new_model = self.add_pgn_database(file_path, games, tags_list=tags_list)
            
            # Set the new database as active
            self.set_active_database(new_model)
            
            # Hide progress
            progress_service.hide_progress()
            QApplication.processEvents()  # Process events to hide progress bar
            
            # Get first game for return
            first_game = games[0] if games else None
            
            # Create success message
            if len(games) == 1:
                status_message = f"Opened PGN database: 1 game"
            else:
                status_message = f"Opened PGN database: {len(games)} game(s)"
            
            return (True, status_message, first_game)
            
        except Exception as e:
            # Hide progress on error
            progress_service.hide_progress()
            return (False, f"Error opening PGN database: {str(e)}", None)
    
    def open_pgn_databases(self, file_paths: List[str]) -> Tuple[int, int, int, List[str], Optional[DatabaseModel], Optional[GameData]]:
        """Open multiple PGN databases from files with parallel processing.
        
        This method handles reading and parsing multiple files in parallel,
        then adds them to the database models sequentially (Qt operations must be in main thread).
        
        Args:
            file_paths: List of paths to PGN files to open.
            
        Returns:
            Tuple of (opened_count, skipped_count, failed_count, messages, last_database, last_first_game).
            - opened_count: Number of databases successfully opened
            - skipped_count: Number of databases skipped (already open)
            - failed_count: Number of databases that failed to open
            - messages: List of status messages for each file
            - last_database: Last successfully opened database (or None)
            - last_first_game: First game from last opened database (or None)
        """
        from app.services.progress_service import ProgressService
        from PyQt6.QtWidgets import QApplication
        from pathlib import Path
        
        opened_count = 0
        skipped_count = 0
        failed_count = 0
        last_successful_database = None
        last_first_game = None
        messages = []
        
        # Filter out already-open databases first
        files_to_open = []
        for file_path in file_paths:
            existing_db = self.get_database_by_file_path(file_path)
            if existing_db:
                skipped_count += 1
                file_name = Path(file_path).name
                messages.append(f"Skipped {file_name} (already open)")
            else:
                files_to_open.append(file_path)
        
        if not files_to_open:
            # All files were skipped
            return (opened_count, skipped_count, failed_count, messages, None, None)
        
        if len(files_to_open) == 1:
            # Single file - use existing method (has progress reporting)
            file_path = files_to_open[0]
            success, message, first_game = self.open_pgn_database(file_path)
            
            if success:
                opened_count += 1
                last_successful_database = self.get_database_by_file_path(file_path)
                last_first_game = first_game
                file_name = Path(file_path).name
                messages.append(f"Opened {file_name}")
            else:
                failed_count += 1
                file_name = Path(file_path).name
                messages.append(f"Failed {file_name}: {message}")
            
            return (opened_count, skipped_count, failed_count, messages, last_successful_database, last_first_game)
        
        # Multiple files - use parallel processing
        progress_service = ProgressService.get_instance()
        
        # Calculate number of worker processes (reserve 1-2 cores for UI)
        cpu_count = os.cpu_count() or 4
        max_workers = max(1, cpu_count - 2)
        
        # Show progress
        progress_service.show_progress()
        progress_service.set_indeterminate(True)
        progress_service.set_status(f"Opening {len(files_to_open)} database(s)...")
        QApplication.processEvents()
        
        # Read config setting for PUA character stripping
        strip_pua = self.config.get('pgn', {}).get('import', {}).get('strip_pua_characters', True)
        
        # Process files in parallel
        parse_results = {}
        executor = None
        try:
            executor = ProcessPoolExecutor(max_workers=max_workers)
            
            # Submit all files for processing
            future_to_path = {
                executor.submit(_read_and_parse_pgn_file, file_path, strip_pua): file_path
                for file_path in files_to_open
            }
            
            # Process results as they complete
            completed = 0
            total_games_parsed = 0
            for future in as_completed(future_to_path):
                file_path = future_to_path[future]
                completed += 1
                
                file_name = Path(file_path).name
                success = False
                games = None
                
                try:
                    result_file_path, success, message, games = future.result()
                    parse_results[result_file_path] = (success, message, games)
                    
                    # Track total games parsed
                    if success and games:
                        total_games_parsed += len(games)
                except Exception as e:
                    parse_results[file_path] = (False, f"Error: {str(e)}", None)
                
                # Update progress with file name and game count
                if success and games:
                    games_count = len(games)
                    progress_service.set_status(
                        f"Parsed {file_name}: {games_count} game(s) ({completed}/{len(files_to_open)} files, {total_games_parsed} total games)"
                    )
                else:
                    progress_service.set_status(
                        f"Parsing {file_name}... ({completed}/{len(files_to_open)} files)"
                    )
                
                # Update progress bar
                progress_percent = int((completed / len(files_to_open)) * 50)  # First 50% for parsing
                progress_service.set_progress(progress_percent)
                QApplication.processEvents()
        finally:
            if executor:
                executor.shutdown(wait=True)
            # Don't hide progress - continue to next phase
        
        # Add parsed databases to models (sequential - Qt operations must be in main thread)
        progress_service.set_indeterminate(False)
        progress_service.set_progress(50)  # Start at 50% (parsing is done)
        
        # Calculate total games to add
        total_games_to_add = sum(
            len(games) if success and games else 0
            for success, _, games in parse_results.values()
        )
        games_added = 0
        
        for idx, file_path in enumerate(files_to_open):
            success, message, games = parse_results.get(file_path, (False, "Unknown error", None))
            
            if success and games:
                # Update progress with file name and game count
                file_name = Path(file_path).name
                games_in_file = len(games)
                
                # Convert parsed games to GameData instances
                game_data_list = []
                tags_list = []  # Collect tags for batch addition
                for file_pos, game_dict in enumerate(games, start=1):
                    game_data = GameData(
                        game_number=0,  # Will be set by model when adding
                        white=game_dict.get("white", ""),
                        black=game_dict.get("black", ""),
                        result=game_dict.get("result", ""),
                        date=game_dict.get("date", ""),
                        moves=game_dict.get("moves", 0),
                        eco=game_dict.get("eco", ""),
                        pgn=game_dict.get("pgn", ""),
                        event=game_dict.get("event", ""),
                        site=game_dict.get("site", ""),
                        white_elo=game_dict.get("white_elo", ""),
                        black_elo=game_dict.get("black_elo", ""),
                        analyzed=game_dict.get("analyzed", False),
                        annotated=game_dict.get("annotated", False),
                        file_position=file_pos,
                    )
                    game_data_list.append(game_data)
                    # Extract tags from parsed game dict (already available, no parsing needed)
                    tags = game_dict.get("tags", [])
                    tags_list.append(tags)
                    games_added += 1
                    
                    # Update progress every 10 games or on last game of file
                    if file_pos % 10 == 0 or file_pos == games_in_file:
                        progress_service.set_status(
                            f"Adding {file_name}: {games_added}/{total_games_to_add} games ({idx + 1}/{len(files_to_open)} files)"
                        )
                        # Progress from 50% to 100% for adding databases
                        progress_percent = 50 + int((games_added / total_games_to_add) * 50) if total_games_to_add > 0 else 50
                        progress_service.set_progress(progress_percent)
                        QApplication.processEvents()
                
                # Add database to panel model (pass tags to avoid re-parsing)
                new_model = self.add_pgn_database(file_path, game_data_list, tags_list=tags_list)
                
                opened_count += 1
                last_successful_database = new_model
                last_first_game = game_data_list[0] if game_data_list else None
                file_name = Path(file_path).name
                messages.append(f"Opened {file_name}")
            else:
                failed_count += 1
                file_name = Path(file_path).name
                error_msg = message if message else "Unknown error"
                messages.append(f"Failed {file_name}: {error_msg}")
        
        progress_service.hide_progress()
        QApplication.processEvents()
        
        return (opened_count, skipped_count, failed_count, messages, last_successful_database, last_first_game)
    
    def reload_database_from_file(self, model: DatabaseModel, file_path: str) -> tuple[bool, str]:
        """Reload a database model from its file path, discarding unsaved changes.
        
        This method clears the model and repopulates it from the file on disk.
        
        Args:
            model: DatabaseModel instance to reload.
            file_path: Path to the PGN file to reload from.
            
        Returns:
            Tuple of (success: bool, message: str).
            If success is True, message indicates success.
            If success is False, message contains error description.
        """
        from app.services.progress_service import ProgressService
        from PyQt6.QtWidgets import QApplication
        progress_service = ProgressService.get_instance()
        
        try:
            # Show progress and status for reading file
            progress_service.show_progress()
            progress_service.set_indeterminate(True)
            progress_service.set_status(f"Reading PGN file: {file_path}")
            QApplication.processEvents()  # Process events to show the progress bar
            
            # Read config setting for PUA character stripping
            strip_pua = self.config.get('pgn', {}).get('import', {}).get('strip_pua_characters', True)
            
            # Read file with encoding detection
            pgn_text = _read_pgn_file_with_encoding_detection(file_path, strip_pua_characters=strip_pua)
            
            # Update status for parsing
            progress_service.set_status("Reloading PGN games...")
            QApplication.processEvents()  # Process events to update status
            
            # Define progress callback for parsing
            def parsing_progress(progress_value: int, message: str) -> None:
                """Update progress during parsing.
                
                Args:
                    progress_value: Progress percentage (0-100) for all phases.
                    message: Status message to display.
                """
                progress_service.set_status(message)
                # All phases now report percentage-based progress
                progress_service.set_progress(progress_value)
                progress_service.set_indeterminate(False)
                # Update UI periodically to avoid excessive processing
                # Update more frequently for early phases (normalization/boundary detection)
                # which report progress more often
                if progress_value <= 42 or progress_value % 5 == 0:
                    QApplication.processEvents()  # Process events to update status
            
            # Parse PGN with progress callback
            parse_result = PgnService.parse_pgn_text(pgn_text, progress_callback=parsing_progress)
            
            if not parse_result.success:
                progress_service.hide_progress()
                error_message = self.format_pgn_error_message(parse_result.error_message)
                return (False, error_message)
            
            # Verify at least one valid game was parsed
            if not parse_result.games or len(parse_result.games) == 0:
                progress_service.hide_progress()
                return (False, "Error: No valid PGN games found in file")
            
            total_games = len(parse_result.games)
            
            # Switch to determinate progress for converting games
            progress_service.set_indeterminate(False)
            progress_service.set_progress(50)
            progress_service.set_status(f"Processing {total_games} game(s)...")
            QApplication.processEvents()  # Process events to update status
            
            # Clear the model
            model.clear()
            
            # Convert parsed games to GameData instances first (before adding to model)
            # This allows us to batch add them for better performance
            games_data = []
            for file_pos, game_dict in enumerate(parse_result.games, start=1):
                game_data = GameData(
                    game_number=0,  # Will be set by model when adding
                    white=game_dict.get("white", ""),
                    black=game_dict.get("black", ""),
                    result=game_dict.get("result", ""),
                    date=game_dict.get("date", ""),
                    moves=game_dict.get("moves", 0),
                    eco=game_dict.get("eco", ""),
                    pgn=game_dict.get("pgn", ""),
                    event=game_dict.get("event", ""),
                    site=game_dict.get("site", ""),
                    white_elo=game_dict.get("white_elo", ""),
                    black_elo=game_dict.get("black_elo", ""),
                    analyzed=game_dict.get("analyzed", False),
                    annotated=game_dict.get("annotated", False),
                    file_position=file_pos,  # Store original file position (1-based)
                )
                games_data.append(game_data)
                
                # Update progress more frequently for better feedback
                # Update every 10 games, or every game for first 10, or on last game
                should_update = (
                    file_pos <= 10 or  # First 10 games for immediate feedback
                    file_pos % 10 == 0 or  # Every 10 games after that
                    file_pos == total_games  # Always on last game
                )
                
                if should_update:
                    # Progress from 50% to 90% for creating GameData objects
                    progress_percent = 50 + int((file_pos / total_games) * 40) if total_games > 0 else 50
                    progress_service.report_progress(
                        f"Processing game {file_pos}/{total_games}...",
                        progress_percent
                    )
                    QApplication.processEvents()  # Process events to update progress bar
            
            # Batch add all games to the model at once (much faster than adding one by one)
            # This triggers only one view update cycle instead of one per game
            progress_service.set_status(f"Adding {total_games} game(s) to database...")
            progress_service.set_progress(90)
            QApplication.processEvents()  # Process events to update status
            
            # Don't mark as unsaved when reloading from file (games are already saved)
            # Extract tags from parsed game dicts (already available, no parsing needed)
            tags_list = [game_dict.get("tags", []) for game_dict in parse_result.games]
            model.add_games_batch(games_data, mark_unsaved=False, tags_list=tags_list)
            
            # Final progress update
            progress_service.set_progress(95)
            QApplication.processEvents()  # Process events to update progress bar
            
            # Hide progress
            progress_service.hide_progress()
            QApplication.processEvents()  # Process events to hide progress bar
            
            # Create success message
            if len(parse_result.games) == 1:
                status_message = f"Reloaded PGN database: 1 game"
            else:
                status_message = f"Reloaded PGN database: {len(parse_result.games)} game(s)"
            
            return (True, status_message)
            
        except Exception as e:
            # Hide progress on error
            progress_service.hide_progress()
            return (False, f"Error reloading PGN database: {str(e)}")
    
    def save_pgn_database_as(self, model: DatabaseModel, file_path: str) -> tuple[bool, str]:
        """Save a PGN database to a new file and create a new database entry.
        
        This method handles file path validation, saving the database, creating
        a new database entry in the panel model, and reloading the original
        database from disk to discard unsaved changes.
        
        Args:
            model: DatabaseModel instance to save.
            file_path: Path to save the PGN file to.
            
        Returns:
            Tuple of (success: bool, message: str).
            If success is True, message indicates success.
            If success is False, message contains error description.
        """
        # Get the original database's file path before creating the new one
        original_identifier = self.panel_model.find_database_by_model(model)
        original_file_path = None
        if original_identifier and original_identifier != "clipboard":
            original_info = self.panel_model.get_database(original_identifier)
            if original_info:
                original_file_path = original_info.file_path
        
        from app.services.progress_service import ProgressService
        from PyQt6.QtWidgets import QApplication
        progress_service = ProgressService.get_instance()
        
        # Ensure .pgn extension
        if not file_path.lower().endswith('.pgn'):
            file_path += '.pgn'
        
        # Save to file (this will mark the model as saved)
        # Note: save_pgn_to_file already shows progress, so we don't need to show it here
        success, message = self.save_pgn_to_file(model, file_path)
        
        if success:
            # Show progress for post-save operations
            # Get games and sort by game_number (same order as saved to file)
            games = model.get_all_games()
            games.sort(key=lambda game: game.game_number)
            total_games = len(games)
            
            progress_service.show_progress()
            progress_service.set_indeterminate(False)
            progress_service.set_progress(0)
            progress_service.set_status("Creating new database entry...")
            QApplication.processEvents()  # Process events to show progress bar
            
            # Mark the original database (e.g., clipboard) as saved since we saved it
            # This is important for "Save As" on clipboard database
            self.panel_model.mark_database_saved(model)
            
            # Create a new database model with copied data
            new_model = DatabaseModel(file_path=file_path)
            
            # Copy all games from the original model to the new model
            # Set file_position based on their order in the newly saved file (1-based)
            for file_pos, game in enumerate(games, start=1):
                # Create a new GameData instance with the same data
                new_game = GameData(
                    game_number=0,  # Will be set by model when adding
                    white=game.white,
                    black=game.black,
                    result=game.result,
                    date=game.date,
                    moves=game.moves,
                    eco=game.eco,
                    pgn=game.pgn,
                    event=game.event,
                    site=game.site,
                    white_elo=game.white_elo,
                    black_elo=game.black_elo,
                    analyzed=game.analyzed,
                    annotated=getattr(game, "annotated", False),
                    file_position=file_pos,  # Set file position based on order in new file
                )
                # Extract tags from existing game's PGN (game is being copied, not parsed)
                tags = new_model._extract_tags_from_game(new_game)
                # Mark as saved since these games are being saved to the new file
                new_model.add_game(new_game, mark_unsaved=False, tags=tags)
                
                # Update progress every 10 games or on last game
                should_update = (
                    file_pos <= 10 or  # First 10 games for immediate feedback
                    file_pos % 10 == 0 or  # Every 10 games after that
                    file_pos == total_games  # Always on last game
                )
                
                if should_update:
                    progress_percent = int((file_pos / total_games) * 50)  # First 50% for copying
                    progress_service.report_progress(
                        f"Copying game {file_pos}/{total_games}...",
                        progress_percent
                    )
                    QApplication.processEvents()  # Process events to update progress bar
            
            # Add the new database to the panel model
            progress_service.set_status("Adding database to panel...")
            progress_service.set_progress(60)
            QApplication.processEvents()  # Process events to update status
            
            self.panel_model.add_database(new_model, file_path=file_path)
            
            # Reload the original database from disk to discard unsaved changes
            if original_file_path:
                progress_service.set_status("Reloading original database...")
                progress_service.set_progress(80)
                QApplication.processEvents()  # Process events to update status
                
                reload_success, reload_message = self.reload_database_from_file(model, original_file_path)
                if not reload_success:
                    # Log warning but don't fail the save operation
                    message += f" (Warning: {reload_message})"
            
            # Set the new database as active
            progress_service.set_status("Finalizing...")
            progress_service.set_progress(90)
            QApplication.processEvents()  # Process events to update status
            
            self.set_active_database(new_model)
            
            # Hide progress
            progress_service.hide_progress()
            QApplication.processEvents()  # Process events to hide progress bar
        
        return (success, message)
    
    def get_available_tags(self, model: DatabaseModel) -> List[str]:
        """Get available tags from database model cache.
        
        This method returns cached unique tags from the database model,
        which are extracted and maintained during database loading and game operations.
        
        Args:
            model: DatabaseModel instance to get tags from.
            
        Returns:
            List of tag names ordered by importance (same ordering as DatabaseModel.get_unique_tags()).
        """
        # Use cached tags from model (no scanning needed)
        return model.get_unique_tags()
    
    def import_online_games(
        self,
        platform: str,
        username: str,
        model: DatabaseModel,
        max_games: Optional[int] = None,
        since_date: Optional[datetime] = None,
        until_date: Optional[datetime] = None,
        perf_type: Optional[str] = None
    ) -> tuple[bool, str, Optional[int]]:
        """Import games from online platform (Lichess or Chess.com) and add to database model.
        
        Args:
            platform: Platform name ("lichess" or "chesscom").
            username: Username on the platform.
            model: DatabaseModel instance to add games to.
            max_games: Maximum number of games to import (None = all).
            since_date: Import games from this date onwards (None = no limit).
            until_date: Import games until this date (None = no limit).
            perf_type: Game type filter for Lichess (e.g., "blitz", "rapid", "classical", None = all).
            
        Returns:
            Tuple of (success: bool, message: str, first_game_index: Optional[int]).
            If success is True, message contains success info and first_game_index is the row index
            of the first game added.
            If success is False, message contains error description and first_game_index is None.
        """
        from app.services.online_import_service import OnlineImportService
        from app.services.progress_service import ProgressService
        from PyQt6.QtWidgets import QApplication
        from datetime import datetime
        
        progress_service = ProgressService.get_instance()
        
        try:
            # Show progress
            progress_service.show_progress()
            progress_service.set_indeterminate(False)
            progress_service.set_progress(0)
            
            # Progress callback for API service
            def progress_callback(status_message: str, progress_percent: int) -> None:
                """Update progress during API import."""
                progress_service.set_status(status_message)
                progress_service.set_progress(progress_percent)
                # Process events frequently to keep UI responsive
                QApplication.processEvents()
            
            # Get application version from config
            app_version = self.config.get("version", "2.4.0")
            
            # Import games from platform
            if platform.lower() == "lichess":
                success, message, pgn_list = OnlineImportService.import_lichess_games(
                    username=username,
                    max_games=max_games,
                    since_date=since_date,
                    until_date=until_date,
                    perf_type=perf_type,
                    progress_callback=progress_callback,
                    version=app_version
                )
            elif platform.lower() in ["chesscom", "chess.com"]:
                success, message, pgn_list = OnlineImportService.import_chesscom_games(
                    username=username,
                    max_games=max_games,
                    since_date=since_date,
                    until_date=until_date,
                    progress_callback=progress_callback,
                    version=app_version
                )
            else:
                progress_service.hide_progress()
                return (False, f"Unknown platform: {platform}", None)
            
            if not success:
                progress_service.hide_progress()
                return (False, message, None)
            
            if not pgn_list:
                progress_service.hide_progress()
                return (False, "No games found matching the criteria", None)
            
            # Update progress for parsing
            progress_service.set_status(f"Parsing {len(pgn_list)} game(s)...")
            progress_service.set_progress(90)
            QApplication.processEvents()
            
            # Combine all PGN strings with blank lines between games
            pgn_text = "\n\n".join(pgn_list)
            
            # Parse and add to model
            parse_success, parse_message, first_game_index, _ = self.parse_pgn_to_model(pgn_text, model)
            
            progress_service.hide_progress()
            QApplication.processEvents()
            
            if parse_success:
                return (True, message, first_game_index)
            else:
                return (False, f"Import succeeded but parsing failed: {parse_message}", None)
                
        except Exception as e:
            progress_service.hide_progress()
            QApplication.processEvents()
            return (False, f"Error importing games: {str(e)}", None)
    
    def highlight_rows(self, database: DatabaseModel, row_indices: List[int]) -> None:
        """Request highlighting of rows in the database panel.
        
        This follows the architecture pattern: Controller → Model → (Model emits signal) → View observes.
        The DatabasePanelModel emits a signal that DatabasePanel observes.
        
        Args:
            database: DatabaseModel instance.
            row_indices: List of row indices to highlight.
        """
        self.panel_model.request_highlight_rows(database, row_indices)

