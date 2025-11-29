"""Database panel model for tracking active database and all databases."""

from PyQt6.QtCore import QObject, pyqtSignal
from typing import Optional, Dict, List
from dataclasses import dataclass

from app.models.database_model import DatabaseModel


@dataclass
class DatabaseInfo:
    """Information about a database."""
    model: DatabaseModel
    file_path: Optional[str]  # None for clipboard DB
    identifier: str  # Unique identifier (file path or "clipboard")
    has_unsaved_changes: bool = False  # True if database has unsaved changes


class DatabasePanelModel(QObject):
    """Model for tracking database panel state (active database, all databases).
    
    This follows the same pattern as GameModel - tracks domain objects,
    not UI indices. The view maps databases to tabs.
    
    This model holds the panel state and emits
    signals when that state changes. Views observe these signals to update
    the UI automatically.
    """
    
    # Signals emitted when panel state changes
    active_database_changed = pyqtSignal(object)  # Emitted when active database changes (DatabaseModel or None)
    database_added = pyqtSignal(str, object)  # identifier, DatabaseInfo
    database_removed = pyqtSignal(str)  # identifier
    database_unsaved_changed = pyqtSignal(str, bool)  # identifier, has_unsaved
    
    def __init__(self) -> None:
        """Initialize the database panel model."""
        super().__init__()
        self._active_database: Optional[DatabaseModel] = None
        self._databases: Dict[str, DatabaseInfo] = {}  # identifier -> DatabaseInfo
    
    @property
    def active_database(self) -> Optional[DatabaseModel]:
        """Get the currently active database.
        
        Returns:
            The active DatabaseModel instance, or None if no database is active.
        """
        return self._active_database
    
    def set_active_database(self, database: Optional[DatabaseModel]) -> None:
        """Set the active database.
        
        Args:
            database: DatabaseModel instance to set as active, or None to clear.
        """
        if self._active_database != database:
            self._active_database = database
            self.active_database_changed.emit(database)
    
    def get_active_database(self) -> Optional[DatabaseModel]:
        """Get the currently active database.
        
        Returns:
            The active DatabaseModel instance, or None.
        """
        return self._active_database
    
    def add_database(self, model: DatabaseModel, file_path: Optional[str] = None) -> str:
        """Add a database to the panel.
        
        Args:
            model: DatabaseModel instance to add.
            file_path: Optional file path (None for clipboard DB).
            
        Returns:
            Unique identifier for this database.
        """
        # Generate identifier: file path for file-based, "clipboard" for clipboard
        identifier = file_path if file_path else "clipboard"
        
        info = DatabaseInfo(
            model=model,
            file_path=file_path,
            identifier=identifier,
            has_unsaved_changes=False
        )
        
        self._databases[identifier] = info
        self.database_added.emit(identifier, info)
        return identifier
    
    def remove_database(self, identifier: str) -> bool:
        """Remove a database from the panel.
        
        Args:
            identifier: Database identifier.
            
        Returns:
            True if database was removed, False if not found.
        """
        if identifier not in self._databases:
            return False
        
        # If this was the active database, clear it
        info = self._databases[identifier]
        if self._active_database == info.model:
            self.set_active_database(None)
        
        del self._databases[identifier]
        self.database_removed.emit(identifier)
        return True
    
    def get_database(self, identifier: str) -> Optional[DatabaseInfo]:
        """Get database info by identifier.
        
        Args:
            identifier: Database identifier.
            
        Returns:
            DatabaseInfo or None if not found.
        """
        return self._databases.get(identifier)
    
    def get_all_databases(self) -> Dict[str, DatabaseInfo]:
        """Get all databases.
        
        Returns:
            Dictionary mapping identifiers to DatabaseInfo.
        """
        return self._databases.copy()
    
    def get_all_database_models(self) -> List[DatabaseModel]:
        """Get all database model instances.
        
        Returns:
            List of all DatabaseModel instances.
        """
        return [info.model for info in self._databases.values()]
    
    def find_database_by_model(self, model: DatabaseModel) -> Optional[str]:
        """Find database identifier by model instance.
        
        Args:
            model: DatabaseModel instance to find.
            
        Returns:
            Identifier or None if not found.
        """
        for identifier, info in self._databases.items():
            if info.model is model:
                return identifier
        return None
    
    def get_database_by_identifier(self, identifier: str) -> Optional[DatabaseModel]:
        """Get database model by identifier.
        
        Args:
            identifier: Database identifier.
            
        Returns:
            DatabaseModel instance or None if not found.
        """
        info = self._databases.get(identifier)
        return info.model if info else None
    
    def update_database_file_path(self, model: DatabaseModel, new_file_path: str) -> bool:
        """Update the file path for a database.
        
        Args:
            model: DatabaseModel instance to update.
            new_file_path: New file path for the database.
            
        Returns:
            True if database was found and updated, False otherwise.
        """
        identifier = self.find_database_by_model(model)
        if identifier is None:
            return False
        
        # Only update if it's not the clipboard database
        if identifier == "clipboard":
            return False
        
        # Get the old info
        old_info = self._databases.get(identifier)
        if old_info is None:
            return False
        
        # Remove old entry
        del self._databases[identifier]
        
        # Create new entry with new file path
        new_identifier = new_file_path
        new_info = DatabaseInfo(
            model=model,
            file_path=new_file_path,
            identifier=new_identifier,
            has_unsaved_changes=old_info.has_unsaved_changes  # Preserve unsaved status
        )
        
        self._databases[new_identifier] = new_info
        # Emit signal to notify view of change
        self.database_removed.emit(identifier)
        self.database_added.emit(new_identifier, new_info)
        
        return True
    
    def mark_database_unsaved(self, model: DatabaseModel) -> None:
        """Mark a database as having unsaved changes.
        
        Args:
            model: DatabaseModel instance to mark as unsaved.
        """
        identifier = self.find_database_by_model(model)
        if identifier is None:
            return
        
        info = self._databases.get(identifier)
        if info and not info.has_unsaved_changes:
            info.has_unsaved_changes = True
            self.database_unsaved_changed.emit(identifier, True)
    
    def mark_database_saved(self, model: DatabaseModel) -> None:
        """Mark a database as saved (clear unsaved changes flag).
        
        Args:
            model: DatabaseModel instance to mark as saved.
        """
        identifier = self.find_database_by_model(model)
        if identifier is None:
            return
        
        info = self._databases.get(identifier)
        if info and info.has_unsaved_changes:
            info.has_unsaved_changes = False
            self.database_unsaved_changed.emit(identifier, False)

