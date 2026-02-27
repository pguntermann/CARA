"""Controller for managing database search operations."""

from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path

from app.models.database_model import DatabaseModel, GameData
from app.models.search_criteria import SearchQuery
from app.services.database_search_service import DatabaseSearchService
from app.services.progress_service import ProgressService
from app.services.logging_service import LoggingService


class SearchController:
    """Controller for orchestrating database search operations.
    
    This controller handles the business logic for searching games across
    databases, creating search results models, and formatting status messages.
    """
    
    def __init__(self, config: Dict[str, Any], database_controller) -> None:
        """Initialize the search controller.
        
        Args:
            config: Configuration dictionary.
            database_controller: DatabaseController instance for accessing databases.
        """
        self.config = config
        self.database_controller = database_controller
        self.progress_service = ProgressService.get_instance()
    
    def perform_search(self, search_query: SearchQuery, active_database: Optional[DatabaseModel]) -> Tuple[Optional[DatabaseModel], str]:
        """Perform a search operation and create a search results model.
        
        Args:
            search_query: SearchQuery with scope and criteria.
            active_database: Currently active database (for "active" scope).
            
        Returns:
            Tuple of (search_results_model, status_message).
            If search fails or no results, model is None and status_message explains why.
        """
        logging_service = LoggingService.get_instance()
        search_scope = search_query.scope if search_query else "unknown"
        
        if not search_query or not search_query.criteria:
            logging_service.debug(f"Search failed: scope={search_scope}, reason=no_criteria")
            return None, "No search criteria provided"
        
        # Determine which databases to search
        databases_to_search, database_names = self._get_databases_to_search(
            search_query.scope,
            active_database
        )
        
        if not databases_to_search:
            logging_service.debug(f"Search failed: scope={search_scope}, reason=no_databases")
            return None, "No database available for search"
        
        # Perform search using service
        matching_results = DatabaseSearchService.search_databases(
            databases_to_search,
            search_query.criteria,
            database_names
        )
        
        # Format status message
        num_games = len(matching_results)
        num_databases = len(databases_to_search)
        status_message = self._format_search_status_message(num_games, num_databases)
        
        # Create search results model
        search_results_model = self._create_search_results_model(matching_results)
        
        # Debug log: search success
        logging_service.debug(f"Search completed: scope={search_scope}, games_found={num_games}, success=true")
        
        return search_results_model, status_message

    def create_search_results_model(self, matching_results: List[Tuple[GameData, str]]) -> DatabaseModel:
        """Create a DatabaseModel for search results from a list of (game, source_name) tuples.

        Used when opening pattern games in a Search Results tab (e.g. from Player Stats).
        """
        return self._create_search_results_model(matching_results)

    def _get_databases_to_search(
        self,
        scope: str,
        active_database: Optional[DatabaseModel]
    ) -> Tuple[List[DatabaseModel], List[str]]:
        """Determine which databases to search based on scope.
        
        Args:
            scope: Search scope ("active" or "all").
            active_database: Currently active database.
            
        Returns:
            Tuple of (databases_to_search, database_names).
        """
        panel_model = self.database_controller.get_panel_model()
        
        if scope == "active":
            if not active_database:
                return [], []
            
            # Get database name from panel model
            identifier = panel_model.find_database_by_model(active_database)
            if identifier:
                database_name = self._get_database_name_from_identifier(identifier)
            else:
                database_name = "Active Database"
            
            return [active_database], [database_name]
        else:
            # Search all databases
            all_databases = []
            database_names = []
            
            for identifier, db_info in panel_model.get_all_databases().items():
                all_databases.append(db_info.model)
                database_names.append(self._get_database_name_from_identifier(identifier))
            
            return all_databases, database_names
    
    def _get_database_name_from_identifier(self, identifier: str) -> str:
        """Get a display name for a database identifier.
        
        Args:
            identifier: Database identifier (file path or "clipboard").
            
        Returns:
            Display name for the database.
        """
        if identifier == "clipboard":
            return "Clipboard"
        else:
            return Path(identifier).stem
    
    def _format_search_status_message(self, num_games: int, num_databases: int) -> str:
        """Format the search status message.
        
        Args:
            num_games: Number of games found.
            num_databases: Number of databases searched.
            
        Returns:
            Formatted status message.
        """
        if num_games == 1:
            return f"1 game found across {num_databases} database{'s' if num_databases > 1 else ''} matching the search criteria"
        else:
            return f"{num_games} games found across {num_databases} database{'s' if num_databases > 1 else ''} matching the search criteria"
    
    def _create_search_results_model(self, matching_results: List[Tuple[GameData, str]]) -> DatabaseModel:
        """Create a DatabaseModel for search results.
        
        Args:
            matching_results: List of tuples (GameData, database_name) from search.
            
        Returns:
            DatabaseModel populated with search results.
        """
        search_results_model = DatabaseModel()
        
        for game, db_name in matching_results:
            # Create a copy of the game with source database info
            game_copy = GameData(
                game_number=0,  # Will be set by model
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
                source_database=db_name,
                file_position=0  # Search results don't have file position
            )
            
            # Extract tags from existing game's PGN (game is being copied for search results)
            tags = search_results_model._extract_tags_from_game(game_copy)
            search_results_model.add_game(game_copy, tags=tags)
        
        return search_results_model

