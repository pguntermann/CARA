"""Metadata model for holding game header data."""

from PyQt6.QtCore import QAbstractTableModel, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from typing import Optional, List, Tuple, Dict, Any


class MetadataModel(QAbstractTableModel):
    """Model representing metadata table data (Name-Value pairs).
    
    This model holds the metadata state and emits
    signals when that state changes. Views observe these signals to update
    the UI automatically.
    """
    
    # Signals emitted when metadata changes
    value_changed = pyqtSignal(str, str)  # Emitted when a tag value is edited (tag_name, new_value)
    tag_added = pyqtSignal(str, str)  # Emitted when a new tag is added (tag_name, tag_value)
    tag_removed = pyqtSignal(str)  # Emitted when a tag is removed (tag_name)
    
    # Column indices
    COL_NAME = 0
    COL_VALUE = 1
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the metadata model.
        
        Args:
            config: Optional configuration dictionary for styling.
        """
        super().__init__()
        self._metadata: List[Tuple[str, str]] = []  # List of (name, value) tuples
        self._config = config or {}
        self._standard_tags: set = set()  # Will be set from STANDARD_TAGS_ORDER
        
        # Load standard tags list from metadata_controller
        try:
            from app.controllers.metadata_controller import STANDARD_TAGS_ORDER
            self._standard_tags = set(STANDARD_TAGS_ORDER)
        except ImportError:
            # Fallback if import fails
            self._standard_tags = set()
    
    def rowCount(self, parent=None) -> int:
        """Get number of rows in the model.
        
        Args:
            parent: Parent index (unused for table models).
            
        Returns:
            Number of rows.
        """
        return len(self._metadata)
    
    def columnCount(self, parent=None) -> int:
        """Get number of columns in the model.
        
        Args:
            parent: Parent index (unused for table models).
            
        Returns:
            Number of columns (2: Name, Value).
        """
        return 2
    
    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        """Get data for a given index and role.
        
        Args:
            index: Model index (row, column).
            role: Data role (DisplayRole, BackgroundRole, ForegroundRole, etc.).
            
        Returns:
            Data value or None.
        """
        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()
        
        if row < 0 or row >= len(self._metadata):
            return None
        
        name, value = self._metadata[row]
        is_standard_tag = name in self._standard_tags
        
        # Handle different roles
        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.COL_NAME:
                return name
            elif col == self.COL_VALUE:
                return value
        elif role == Qt.ItemDataRole.BackgroundRole and is_standard_tag:
            # Highlight standard tags with background color
            metadata_config = self._config.get('ui', {}).get('panels', {}).get('detail', {}).get('metadata', {})
            standard_tag_config = metadata_config.get('standard_tag', {})
            bg_color = standard_tag_config.get('background_color', None)
            if bg_color:
                return QColor(bg_color[0], bg_color[1], bg_color[2])
        elif role == Qt.ItemDataRole.ForegroundRole and is_standard_tag:
            # Highlight standard tags with text color
            metadata_config = self._config.get('ui', {}).get('panels', {}).get('detail', {}).get('metadata', {})
            standard_tag_config = metadata_config.get('standard_tag', {})
            text_color = standard_tag_config.get('text_color', None)
            if text_color:
                return QColor(text_color[0], text_color[1], text_color[2])
        
        return None
    
    def flags(self, index):
        """Get item flags for a given index.
        
        Args:
            index: Model index (row, column).
            
        Returns:
            Item flags.
        """
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        
        # Get tag name for this row
        row = index.row()
        is_read_only = False
        if 0 <= row < len(self._metadata):
            tag_name = self._metadata[row][0]
            
            # CARA analysis and annotation tags are read-only
            read_only_tags = {
                "CARAAnalysisData", "CARAAnalysisInfo", "CARAAnalysisChecksum",
                "CARAAnnotations", "CARAAnnotationsInfo", "CARAAnnotationsChecksum"
            }
            is_read_only = tag_name in read_only_tags
        
        # Make value column editable (unless read-only tag), name column read-only
        if index.column() == self.COL_VALUE:
            if is_read_only:
                return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            else:
                return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable
        else:
            return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
    
    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        """Set data for a given index and role.
        
        Args:
            index: Model index (row, column).
            value: New value to set.
            role: Data role (EditRole, etc.).
            
        Returns:
            True if data was set successfully, False otherwise.
        """
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        
        row = index.row()
        col = index.column()
        
        if row < 0 or row >= len(self._metadata):
            return False
        
        # Only allow editing value column
        if col != self.COL_VALUE:
            return False
        
        # Validate value
        name, old_value = self._metadata[row]
        
        # CARA analysis and annotation tags are read-only and cannot be edited
        read_only_tags = {
            "CARAAnalysisData", "CARAAnalysisInfo", "CARAAnalysisChecksum",
            "CARAAnnotations", "CARAAnnotationsInfo", "CARAAnnotationsChecksum"
        }
        if name in read_only_tags:
            return False
        
        new_value = str(value).strip()
        
        # Validate based on tag name
        if not self._validate_value(name, new_value):
            return False
        
        # Update the value
        self._metadata[row] = (name, new_value)
        
        # Emit dataChanged signal
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
        
        # Emit custom signal for value change (to update game PGN)
        self.value_changed.emit(name, new_value)
        
        return True
    
    def _validate_value(self, tag_name: str, value: str) -> bool:
        """Validate a tag value based on its name.
        
        Args:
            tag_name: Name of the tag.
            value: Value to validate.
            
        Returns:
            True if value is valid, False otherwise.
        """
        # Validate Result tag (must be valid PGN result)
        if tag_name == "Result":
            return value in ["1-0", "0-1", "1/2-1/2", "*"]
        
        # Validate Date tag (should be in YYYY.MM.DD format or similar)
        if tag_name == "Date":
            # Allow empty or valid date formats
            if not value:
                return True
            # Basic validation: should contain dots or hyphens for date format
            if '.' in value or '-' in value or '??' in value:
                return True
            return False
        
        # Validate Elo tags (should be numeric or empty)
        if tag_name in ["WhiteElo", "BlackElo"]:
            if not value:
                return True
            try:
                int(value)
                return True
            except ValueError:
                return False
        
        # For other tags, allow any non-empty value
        # Empty values are allowed (some tags might be optional)
        return True
    
    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        """Get header data for a column or row.
        
        Args:
            section: Section index (column or row).
            orientation: Qt.Orientation.Horizontal or Qt.Orientation.Vertical.
            role: Data role.
            
        Returns:
            Header text or None.
        """
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        
        if orientation == Qt.Orientation.Horizontal:
            headers = ["Name", "Value"]
            if 0 <= section < len(headers):
                return headers[section]
        
        return None
    
    def set_metadata(self, metadata: List[Tuple[str, str]]) -> None:
        """Set metadata from a list of (name, value) tuples.
        
        Args:
            metadata: List of (name, value) tuples.
        """
        # Clear existing metadata
        if len(self._metadata) > 0:
            self.beginRemoveRows(self.index(0, 0).parent(), 0, len(self._metadata) - 1)
            self._metadata.clear()
            self.endRemoveRows()
        
        # Add new metadata
        if len(metadata) > 0:
            self.beginInsertRows(self.index(0, 0).parent(), 0, len(metadata) - 1)
            self._metadata = metadata.copy()
            self.endInsertRows()
    
    def clear(self) -> None:
        """Clear all metadata from the model."""
        if len(self._metadata) > 0:
            self.beginRemoveRows(self.index(0, 0).parent(), 0, len(self._metadata) - 1)
            self._metadata.clear()
            self.endRemoveRows()
    
    def get_metadata(self) -> List[Tuple[str, str]]:
        """Get all metadata in the model.
        
        Returns:
            List of (name, value) tuples.
        """
        return self._metadata.copy()
    
    def add_tag(self, tag_name: str, tag_value: str) -> bool:
        """Add a new tag to the metadata.
        
        Args:
            tag_name: Name of the tag to add.
            tag_value: Value of the tag to add.
            
        Returns:
            True if tag was added successfully, False if tag already exists or validation failed.
        """
        # Validate tag name
        if not tag_name or not tag_name.strip():
            return False
        
        tag_name = tag_name.strip()
        tag_value = tag_value.strip() if tag_value else ""
        
        # Check if tag already exists
        for name, _ in self._metadata:
            if name == tag_name:
                return False
        
        # Validate value based on tag name
        if not self._validate_value(tag_name, tag_value):
            return False
        
        # Determine insertion position
        # Standard tags should be inserted in their predefined order
        # Non-standard tags should be inserted alphabetically after standard tags
        from app.controllers.metadata_controller import STANDARD_TAGS_ORDER
        standard_tags_set = set(STANDARD_TAGS_ORDER)
        is_standard = tag_name in standard_tags_set
        
        insert_index = len(self._metadata)
        
        if is_standard:
            # Find the correct position for standard tags
            for i, (name, _) in enumerate(self._metadata):
                if name in standard_tags_set:
                    # Check if this standard tag should come after the new tag
                    try:
                        current_index = STANDARD_TAGS_ORDER.index(name)
                        new_index = STANDARD_TAGS_ORDER.index(tag_name)
                        if new_index < current_index:
                            insert_index = i
                            break
                    except ValueError:
                        pass
                else:
                    # We've reached non-standard tags, insert before them
                    insert_index = i
                    break
        else:
            # Find the correct alphabetical position for non-standard tags
            for i, (name, _) in enumerate(self._metadata):
                if name not in standard_tags_set:
                    # We're in the non-standard section
                    if tag_name < name:
                        insert_index = i
                        break
        
        # Insert the new tag
        self.beginInsertRows(self.index(0, 0).parent(), insert_index, insert_index)
        self._metadata.insert(insert_index, (tag_name, tag_value))
        self.endInsertRows()
        
        # Emit signal for tag addition
        self.tag_added.emit(tag_name, tag_value)
        
        return True
    
    def remove_tag(self, tag_name: str) -> bool:
        """Remove a tag from the metadata.
        
        Args:
            tag_name: Name of the tag to remove.
            
        Returns:
            True if tag was removed successfully, False if tag was not found.
        """
        # Find the tag in the metadata
        for i, (name, _) in enumerate(self._metadata):
            if name == tag_name:
                # Remove the tag
                self.beginRemoveRows(self.index(0, 0).parent(), i, i)
                self._metadata.pop(i)
                self.endRemoveRows()
                
                # Emit signal for tag removal
                self.tag_removed.emit(tag_name)
                
                return True
        
        return False

