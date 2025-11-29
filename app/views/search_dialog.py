"""Search dialog for searching games in databases."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QPushButton,
    QGroupBox,
    QRadioButton,
    QButtonGroup,
    QSizePolicy,
    QWidget,
    QScrollArea,
    QSpacerItem,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from PyQt6.QtGui import QPalette, QColor, QFont, QShowEvent
from typing import Optional, Dict, Any, List

from app.models.search_criteria import SearchCriteria, SearchField, SearchOperator, LogicOperator, SearchQuery
from app.models.database_model import DatabaseModel


class NoWheelComboBox(QComboBox):
    """QComboBox that ignores mouse wheel events."""
    
    def wheelEvent(self, event) -> None:
        event.ignore()


class CriteriaRowWidget(QWidget):
    """Widget representing a single search criterion row."""
    
    removed = pyqtSignal()  # Emitted when remove button is clicked
    
    def __init__(self, config: Dict[str, Any], parent=None) -> None:
        """Initialize criteria row widget.
        
        Args:
            config: Configuration dictionary.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self._load_config()
        self._setup_ui()
        self._apply_styling()
    
    def _load_config(self) -> None:
        """Load configuration values."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {})
        
        # Inputs
        inputs_config = dialog_config.get("inputs", {})
        self.input_font_family = inputs_config.get("font_family", "Cascadia Mono")
        self.input_font_size = inputs_config.get("font_size", 11)
        self.input_text_color = QColor(*inputs_config.get("text_color", [240, 240, 240]))
        self.input_bg_color = QColor(*inputs_config.get("background_color", [30, 30, 35]))
        self.input_border_color = QColor(*inputs_config.get("border_color", [60, 60, 65]))
        self.input_border_radius = inputs_config.get("border_radius", 3)
        self.input_padding = inputs_config.get("padding", [8, 6])
        
        # Buttons
        buttons_config = dialog_config.get("buttons", {})
        self.button_height = buttons_config.get("height", 30)
        self.small_button_width = buttons_config.get("small_width", 80)
        
        # Labels
        labels_config = dialog_config.get("labels", {})
        self.label_font_family = labels_config.get("font_family", "Helvetica Neue")
        self.label_font_size = labels_config.get("font_size", 11)
        self.label_text_color = QColor(*labels_config.get("text_color", [200, 200, 200]))
    
    def _setup_ui(self) -> None:
        """Setup the criteria row UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(8)
        
        # Logic connector (AND/OR) - hidden for first row
        self.logic_combo = NoWheelComboBox()
        self.logic_combo.addItems(["AND", "OR"])
        self.logic_combo.setCurrentText("AND")
        self.logic_combo.setFixedWidth(70)
        self.logic_combo.setVisible(False)  # Hidden by default
        layout.addWidget(self.logic_combo)
        
        # Field selector
        self.field_combo = NoWheelComboBox()
        self.field_combo.addItems([
            "White", "Black", "WhiteElo", "BlackElo", "Result", "Date", 
            "Event", "Site", "ECO", "Analyzed", "Annotated", "Custom PGN Tag"
        ])
        self.field_combo.setFixedWidth(120)
        self.field_combo.currentTextChanged.connect(self._on_field_changed)
        layout.addWidget(self.field_combo)
        
        # Operator selector
        self.operator_combo = NoWheelComboBox()
        self.operator_combo.addItems(["contains", "equals", "starts with", "ends with"])
        self.operator_combo.setFixedWidth(140)  # Increased from 100
        layout.addWidget(self.operator_combo)
        
        # Value input
        self.value_input = QLineEdit()
        self.value_input.setPlaceholderText("Value...")
        self.value_input.setMinimumWidth(100)  # Reduced from 150
        self.value_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.value_input)
        
        # Custom tag name input (hidden by default)
        self.custom_tag_input = QLineEdit()
        self.custom_tag_input.setPlaceholderText("Tag name...")
        self.custom_tag_input.setFixedWidth(120)
        self.custom_tag_input.setVisible(False)
        layout.addWidget(self.custom_tag_input)
        
        # Remove button (smaller to match input field height)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self.removed.emit)
        layout.addWidget(self.remove_btn)
        
        # Initialize operators for the default field selection (after all widgets are created)
        self._on_field_changed(self.field_combo.currentText())
    
    def _on_field_changed(self, field_text: str) -> None:
        """Handle field selection change."""
        # Update operators based on field type
        self.operator_combo.clear()
        
        if field_text in ["Analyzed", "Annotated"]:
            self.operator_combo.addItems(["is", "is not"])
            # Keep value input visible but disable it for boolean fields
            self.value_input.setVisible(True)
            self.value_input.setEnabled(False)
            self.value_input.clear()
            self.value_input.setPlaceholderText("")
            self.custom_tag_input.setVisible(False)
        elif field_text in ["WhiteElo", "BlackElo"]:
            self.operator_combo.addItems([
                "equals", "not equals", "greater than", "less than", 
                "greater than or equal", "less than or equal"
            ])
            self.value_input.setVisible(True)
            self.value_input.setEnabled(True)
            self.value_input.setPlaceholderText("Value...")
            self.custom_tag_input.setVisible(False)
        elif field_text == "Date":
            self.operator_combo.addItems([
                "contains", "equals", "not equals", "before", "after"
            ])
            self.value_input.setPlaceholderText("YYYY.MM.DD (use ?? for unknown)")
            self.value_input.setVisible(True)
            self.value_input.setEnabled(True)
            self.custom_tag_input.setVisible(False)
        elif field_text == "Custom PGN Tag":
            self.operator_combo.addItems(["contains", "equals", "not equals", "starts with", "ends with"])
            self.value_input.setVisible(True)
            self.value_input.setEnabled(True)
            self.value_input.setPlaceholderText("Value...")
            self.custom_tag_input.setVisible(True)
        else:
            # Text fields
            self.operator_combo.addItems([
                "contains", "equals", "not equals", "starts with", "ends with", 
                "is empty", "is not empty"
            ])
            self.value_input.setPlaceholderText("Value...")
            self.value_input.setVisible(True)
            self.value_input.setEnabled(True)
            self.custom_tag_input.setVisible(False)
    
    def _apply_styling(self) -> None:
        """Apply styling to widgets."""
        # Get button styling config
        buttons_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {}).get("buttons", {})
        button_bg_offset = buttons_config.get("background_offset", 20)
        button_hover_offset = buttons_config.get("hover_background_offset", 30)
        button_pressed_offset = buttons_config.get("pressed_background_offset", 10)
        button_border_radius = buttons_config.get("border_radius", 3)
        button_padding = buttons_config.get("padding", 5)
        
        # Get dialog background color for button styling
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {})
        bg_color = dialog_config.get("background_color", [40, 40, 45])
        text_color = dialog_config.get("text_color", [200, 200, 200])
        font_family = dialog_config.get("font_family", "Helvetica Neue")
        font_size = dialog_config.get("font_size", 11)
        
        # Button styling (standardized pattern, but with reduced padding for inline button)
        # Use smaller padding for the Remove button to match input field height better
        inline_button_padding = 3  # Smaller padding for inline button
        button_style = (
            f"QPushButton {{"
            f"font-family: {font_family};"
            f"font-size: {font_size}pt;"
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"background-color: rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
            f"border: 1px solid rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
            f"border-radius: {button_border_radius}px;"
            f"padding: {inline_button_padding}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({bg_color[0] + button_hover_offset}, {bg_color[1] + button_hover_offset}, {bg_color[2] + button_hover_offset});"
            f"border-color: rgb({bg_color[0] + button_hover_offset}, {bg_color[1] + button_hover_offset}, {bg_color[2] + button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({bg_color[0] + button_pressed_offset}, {bg_color[1] + button_pressed_offset}, {bg_color[2] + button_pressed_offset});"
            f"border-color: rgb({bg_color[0] + button_pressed_offset}, {bg_color[1] + button_pressed_offset}, {bg_color[2] + button_pressed_offset});"
            f"}}"
        )
        self.remove_btn.setStyleSheet(button_style)
        
        # ComboBox styling
        combo_style = (
            f"QComboBox {{"
            f"font-family: {self.input_font_family};"
            f"font-size: {self.input_font_size}pt;"
            f"color: rgb({self.input_text_color.red()}, {self.input_text_color.green()}, {self.input_text_color.blue()});"
            f"background-color: rgb({self.input_bg_color.red()}, {self.input_bg_color.green()}, {self.input_bg_color.blue()});"
            f"border: 1px solid rgb({self.input_border_color.red()}, {self.input_border_color.green()}, {self.input_border_color.blue()});"
            f"border-radius: {self.input_border_radius}px;"
            f"padding: {self.input_padding[1]}px {self.input_padding[0]}px;"
            f"}}"
            f"QComboBox::drop-down {{"
            f"width: 0px;"
            f"height: 0px;"
            f"}}"
            f"QComboBox::down-arrow {{"
            f"width: 0px;"
            f"height: 0px;"
            f"}}"
        )
        self.field_combo.setStyleSheet(combo_style)
        self.operator_combo.setStyleSheet(combo_style)
        self.logic_combo.setStyleSheet(combo_style)
        
        # LineEdit styling
        input_style = (
            f"QLineEdit {{"
            f"font-family: {self.input_font_family};"
            f"font-size: {self.input_font_size}pt;"
            f"color: rgb({self.input_text_color.red()}, {self.input_text_color.green()}, {self.input_text_color.blue()});"
            f"background-color: rgb({self.input_bg_color.red()}, {self.input_bg_color.green()}, {self.input_bg_color.blue()});"
            f"border: 1px solid rgb({self.input_border_color.red()}, {self.input_border_color.green()}, {self.input_border_color.blue()});"
            f"border-radius: {self.input_border_radius}px;"
            f"padding: {self.input_padding[1]}px {self.input_padding[0]}px;"
            f"}}"
        )
        self.value_input.setStyleSheet(input_style)
        self.custom_tag_input.setStyleSheet(input_style)
        
        # Set Remove button height to match input field height
        # Use the combo box height as reference since it has the same styling
        self.field_combo.updateGeometry()
        combo_height = self.field_combo.sizeHint().height()
        if combo_height <= 0:
            # Fallback: calculate from font metrics
            from PyQt6.QtGui import QFontMetrics, QFont
            font = QFont(self.input_font_family, self.input_font_size)
            fm = QFontMetrics(font)
            text_height = fm.height()
            combo_height = text_height + (self.input_padding[1] * 2) + 2
        self.remove_btn.setFixedSize(self.small_button_width, combo_height)
    
    def get_criterion(self) -> Optional[SearchCriteria]:
        """Get SearchCriteria from this row.
        
        Returns:
            SearchCriteria instance or None if invalid.
        """
        field_text = self.field_combo.currentText()
        operator_text = self.operator_combo.currentText()
        value_text = self.value_input.text().strip()
        custom_tag = self.custom_tag_input.text().strip() if self.custom_tag_input.isVisible() else None
        logic_text = self.logic_combo.currentText()
        
        # Map field text to SearchField enum
        field_map = {
            "White": SearchField.WHITE,
            "Black": SearchField.BLACK,
            "WhiteElo": SearchField.WHITE_ELO,
            "BlackElo": SearchField.BLACK_ELO,
            "Result": SearchField.RESULT,
            "Date": SearchField.DATE,
            "Event": SearchField.EVENT,
            "Site": SearchField.SITE,
            "ECO": SearchField.ECO,
            "Analyzed": SearchField.ANALYZED,
            "Annotated": SearchField.ANNOTATED,
            "Custom PGN Tag": SearchField.CUSTOM_TAG,
        }
        field = field_map.get(field_text)
        if field is None:
            return None
        
        # Map operator text to SearchOperator enum
        operator_map = {
            "contains": SearchOperator.CONTAINS,
            "equals": SearchOperator.EQUALS,
            "not equals": SearchOperator.NOT_EQUALS,
            "starts with": SearchOperator.STARTS_WITH,
            "ends with": SearchOperator.ENDS_WITH,
            "is empty": SearchOperator.IS_EMPTY,
            "is not empty": SearchOperator.IS_NOT_EMPTY,
            "greater than": SearchOperator.GREATER_THAN,
            "less than": SearchOperator.LESS_THAN,
            "greater than or equal": SearchOperator.GREATER_THAN_OR_EQUAL,
            "less than or equal": SearchOperator.LESS_THAN_OR_EQUAL,
            "before": SearchOperator.DATE_BEFORE,
            "after": SearchOperator.DATE_AFTER,
            "is": SearchOperator.IS_TRUE,
            "is not": SearchOperator.IS_FALSE,
        }
        operator = operator_map.get(operator_text)
        if operator is None:
            return None
        
        # Map text "equals" to appropriate enum based on field type
        if operator == SearchOperator.EQUALS:
            if field in [SearchField.WHITE_ELO, SearchField.BLACK_ELO]:
                operator = SearchOperator.EQUALS_NUM
            elif field == SearchField.DATE:
                operator = SearchOperator.DATE_EQUALS
        
        # Map text "not equals" to appropriate enum based on field type
        if operator == SearchOperator.NOT_EQUALS:
            if field in [SearchField.WHITE_ELO, SearchField.BLACK_ELO]:
                operator = SearchOperator.NOT_EQUALS_NUM
            elif field == SearchField.DATE:
                operator = SearchOperator.DATE_NOT_EQUALS
        
        # Get value (handle special cases)
        if field in [SearchField.ANALYZED, SearchField.ANNOTATED]:
            value = True  # Value doesn't matter for boolean
        elif operator in [SearchOperator.IS_EMPTY, SearchOperator.IS_NOT_EMPTY]:
            value = None
        else:
            value = value_text
        
        # Get logic operator
        logic_op = LogicOperator.AND if logic_text == "AND" else LogicOperator.OR
        
        return SearchCriteria(
            field=field,
            operator=operator,
            value=value,
            logic_operator=logic_op,
            custom_tag_name=custom_tag if field == SearchField.CUSTOM_TAG else None
        )
    
    def set_group_start(self, is_start: bool, group_level: int = 0) -> None:
        """Mark this row as a group start.
        
        Args:
            is_start: True if this is a group start.
            group_level: Nesting level.
        """
        # Visual indication could be added here (indentation, background color)
        pass
    
    def set_criterion(self, criterion: SearchCriteria) -> None:
        """Set the criterion values from a SearchCriteria object.
        
        Args:
            criterion: SearchCriteria to populate this row with.
        """
        # Map SearchField enum to field text
        field_map = {
            SearchField.WHITE: "White",
            SearchField.BLACK: "Black",
            SearchField.WHITE_ELO: "WhiteElo",
            SearchField.BLACK_ELO: "BlackElo",
            SearchField.RESULT: "Result",
            SearchField.DATE: "Date",
            SearchField.EVENT: "Event",
            SearchField.SITE: "Site",
            SearchField.ECO: "ECO",
            SearchField.ANALYZED: "Analyzed",
            SearchField.ANNOTATED: "Annotated",
            SearchField.CUSTOM_TAG: "Custom PGN Tag",
        }
        field_text = field_map.get(criterion.field)
        if field_text:
            self.field_combo.setCurrentText(field_text)
            # Trigger field change to update operators
            self._on_field_changed(field_text)
        
        # Map SearchOperator enum to operator text
        operator_map = {
            SearchOperator.CONTAINS: "contains",
            SearchOperator.EQUALS: "equals",
            SearchOperator.NOT_EQUALS: "not equals",
            SearchOperator.STARTS_WITH: "starts with",
            SearchOperator.ENDS_WITH: "ends with",
            SearchOperator.IS_EMPTY: "is empty",
            SearchOperator.IS_NOT_EMPTY: "is not empty",
            SearchOperator.EQUALS_NUM: "equals",
            SearchOperator.NOT_EQUALS_NUM: "not equals",
            SearchOperator.GREATER_THAN: "greater than",
            SearchOperator.LESS_THAN: "less than",
            SearchOperator.GREATER_THAN_OR_EQUAL: "greater than or equal",
            SearchOperator.LESS_THAN_OR_EQUAL: "less than or equal",
            SearchOperator.DATE_EQUALS: "equals",
            SearchOperator.DATE_NOT_EQUALS: "not equals",
            SearchOperator.DATE_BEFORE: "before",
            SearchOperator.DATE_AFTER: "after",
            SearchOperator.DATE_CONTAINS: "contains",
            SearchOperator.IS_TRUE: "is",
            SearchOperator.IS_FALSE: "is not",
        }
        operator_text = operator_map.get(criterion.operator)
        if operator_text and operator_text in [self.operator_combo.itemText(i) for i in range(self.operator_combo.count())]:
            self.operator_combo.setCurrentText(operator_text)
        
        # Set value (if applicable)
        if criterion.value is not None and criterion.operator not in [SearchOperator.IS_EMPTY, SearchOperator.IS_NOT_EMPTY]:
            if criterion.field not in [SearchField.ANALYZED, SearchField.ANNOTATED]:
                self.value_input.setText(str(criterion.value))
        
        # Set custom tag if applicable
        if criterion.field == SearchField.CUSTOM_TAG and criterion.custom_tag_name:
            self.custom_tag_input.setText(criterion.custom_tag_name)
        
        # Set logic operator
        if criterion.logic_operator:
            logic_text = "AND" if criterion.logic_operator == LogicOperator.AND else "OR"
            self.logic_combo.setCurrentText(logic_text)
    
    def set_group_end(self, is_end: bool) -> None:
        """Mark this row as a group end.
        
        Args:
            is_end: True if this is a group end.
        """
        # Visual indication could be added here
        pass
    
    def set_indentation(self, level: int) -> None:
        """Set visual indentation level.
        
        Args:
            level: Indentation level (0 = no indent).
        """
        # Add left margin for indentation
        layout = self.layout()
        if layout:
            margins = layout.contentsMargins()
            layout.setContentsMargins(level * 20, margins.top(), margins.right(), margins.bottom())
            
            # Add visual indicator (vertical line) for indented rows
            if level > 0:
                # Create a visual separator widget if it doesn't exist
                if not hasattr(self, '_indent_widget'):
                    from PyQt6.QtWidgets import QFrame
                    self._indent_widget = QFrame(self)
                    self._indent_widget.setFrameShape(QFrame.Shape.VLine)
                    self._indent_widget.setFrameShadow(QFrame.Shadow.Sunken)
                    self._indent_widget.setStyleSheet("QFrame { color: rgba(100, 120, 160, 100); max-width: 2px; }")
                    self._indent_widget.setFixedWidth(2)
                    layout.insertWidget(0, self._indent_widget)
                self._indent_widget.setVisible(True)
            elif hasattr(self, '_indent_widget'):
                self._indent_widget.setVisible(False)


class SearchDialog(QDialog):
    """Dialog for searching games in databases."""
    
    # Class variable to store last search query in memory (session-only)
    _last_search_query: Optional[SearchQuery] = None
    
    def __init__(self, config: Dict[str, Any], 
                 active_database: Optional[DatabaseModel],
                 all_databases: List[DatabaseModel],
                 parent=None) -> None:
        """Initialize the search dialog.
        
        Args:
            config: Configuration dictionary.
            active_database: Currently active database (None if none).
            all_databases: List of all open databases.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.active_database = active_database
        self.all_databases = all_databases
        self.search_query: Optional[SearchQuery] = None
        
        # Store fixed size
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('search', {})
        width = dialog_config.get('width', 800)
        height = dialog_config.get('height', 600)
        self._fixed_size = QSize(width, height)
        
        # Set fixed size
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        self._load_config()
        self._setup_ui()
        self._apply_styling()
        self.setWindowTitle("Search Games")
    
    def _load_config(self) -> None:
        """Load configuration values from config.json."""
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {})
        
        # Dialog dimensions
        self.dialog_width = dialog_config.get("width", 800)
        self.dialog_height = dialog_config.get("height", 600)
        
        # Background color
        bg_color = dialog_config.get("background_color", [40, 40, 45])
        self.bg_color = QColor(bg_color[0], bg_color[1], bg_color[2])
        
        # Text color
        text_color = dialog_config.get("text_color", [200, 200, 200])
        self.text_color = QColor(text_color[0], text_color[1], text_color[2])
        
        # Font
        font_size = dialog_config.get("font_size", 11)
        self.font_family = dialog_config.get("font_family", "Helvetica Neue")
        self.font_size = font_size
        
        # Layout
        layout_config = dialog_config.get("layout", {})
        self.layout_margins = layout_config.get("margins", [25, 25, 25, 25])
        self.layout_spacing = layout_config.get("spacing", 15)
        
        # Spacing
        spacing_config = dialog_config.get("spacing", {})
        self.section_spacing = spacing_config.get("section", 15)
        
        # Buttons
        buttons_config = dialog_config.get("buttons", {})
        self.button_width = buttons_config.get("width", 120)
        self.button_height = buttons_config.get("height", 30)
        self.button_spacing = buttons_config.get("spacing", 10)
        self.small_button_width = buttons_config.get("small_width", 100)
        
        # Labels
        labels_config = dialog_config.get("labels", {})
        self.label_font_family = labels_config.get("font_family", "Helvetica Neue")
        self.label_font_size = labels_config.get("font_size", 11)
        self.label_text_color = QColor(*labels_config.get("text_color", [200, 200, 200]))
        
        # Groups
        groups_config = dialog_config.get("groups", {})
        self.group_bg_color = QColor(*groups_config.get("background_color", [45, 45, 50]))
        self.group_border_color = QColor(*groups_config.get("border_color", [60, 60, 65]))
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(self.layout_spacing)
        main_layout.setContentsMargins(
            self.layout_margins[0],
            self.layout_margins[1],
            self.layout_margins[2],
            self.layout_margins[3]
        )
        
        # Search Scope section
        scope_group = QGroupBox("Search Scope")
        scope_layout = QHBoxLayout()
        scope_layout.setSpacing(8)
        
        self.scope_button_group = QButtonGroup(self)
        self.active_radio = QRadioButton("Active database")
        self.all_radio = QRadioButton("All open databases")
        self.scope_button_group.addButton(self.active_radio, 0)
        self.scope_button_group.addButton(self.all_radio, 1)
        
        # Set default based on availability
        if self.active_database:
            self.active_radio.setChecked(True)
        else:
            self.all_radio.setChecked(True)
            self.active_radio.setEnabled(False)
        
        scope_layout.addWidget(self.active_radio)
        scope_layout.addWidget(self.all_radio)
        scope_layout.addStretch()
        scope_group.setLayout(scope_layout)
        main_layout.addWidget(scope_group)
        
        # Search Criteria section
        criteria_group = QGroupBox("Search Criteria")
        criteria_layout = QVBoxLayout()
        criteria_layout.setSpacing(8)
        
        # Scroll area for criteria rows
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.criteria_container = QWidget()
        self.criteria_layout = QVBoxLayout(self.criteria_container)
        self.criteria_layout.setSpacing(5)
        self.criteria_layout.setContentsMargins(5, 5, 5, 5)
        self.criteria_layout.addStretch()
        
        scroll_area.setWidget(self.criteria_container)
        criteria_layout.addWidget(scroll_area)
        
        # Buttons for managing criteria
        criteria_buttons_layout = QHBoxLayout()
        criteria_buttons_layout.addStretch()
        
        self.start_group_btn = QPushButton("Start Group")
        self.start_group_btn.setFixedSize(self.button_width, self.button_height)
        self.start_group_btn.clicked.connect(self._on_start_group_clicked)
        criteria_buttons_layout.addWidget(self.start_group_btn)
        
        self.end_group_btn = QPushButton("End Group")
        self.end_group_btn.setFixedSize(self.button_width, self.button_height)
        self.end_group_btn.clicked.connect(self._on_end_group_clicked)
        criteria_buttons_layout.addWidget(self.end_group_btn)
        
        self.add_criterion_btn = QPushButton("Add Criterion")
        self.add_criterion_btn.setFixedSize(self.button_width, self.button_height)
        self.add_criterion_btn.clicked.connect(self._add_criterion_row)
        criteria_buttons_layout.addWidget(self.add_criterion_btn)
        
        criteria_layout.addLayout(criteria_buttons_layout)
        criteria_group.setLayout(criteria_layout)
        main_layout.addWidget(criteria_group)
        
        # Buttons at bottom
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()
        
        self.search_btn = QPushButton("Search")
        self.search_btn.clicked.connect(self._on_search_clicked)
        buttons_layout.addWidget(self.search_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_btn)
        
        main_layout.addLayout(buttons_layout)
        
        # Track criteria rows
        self.criteria_rows: List[CriteriaRowWidget] = []
        self.group_starts: List[int] = []  # Track which rows are group starts
        self.group_ends: List[int] = []  # Track which rows are group ends
        self.group_levels: Dict[int, int] = {}  # Track group nesting levels
        
        # Add initial group start (which includes a criterion row) after dialog is fully initialized
        # This ensures proper layout and sizing, and makes combinations work correctly
        # If there's a last search query, restore it instead
        from PyQt6.QtCore import QTimer
        if SearchDialog._last_search_query is not None:
            QTimer.singleShot(0, self._restore_last_search)
        else:
            QTimer.singleShot(0, lambda: self._add_criterion_row(is_group_start=True))
    
    def _add_criterion_row(self, is_group_start: bool = False) -> None:
        """Add a new criterion row.
        
        Args:
            is_group_start: If True, mark this row as a group start.
        """
        row = CriteriaRowWidget(self.config, self)
        row.removed.connect(lambda: self._remove_criterion_row(row))
        
        # Insert before stretch
        count = self.criteria_layout.count()
        self.criteria_layout.insertWidget(count - 1, row)
        idx = len(self.criteria_rows)
        self.criteria_rows.append(row)
        
        # Mark as group start if requested
        if is_group_start:
            # Calculate group level (count how many groups we're nested in)
            group_level = 0
            for start_idx in sorted(self.group_starts):
                if start_idx < idx:
                    group_level = self.group_levels.get(start_idx, 0) + 1
                else:
                    break
            self.group_starts.append(idx)
            self.group_levels[idx] = group_level
        
        # Show logic connector for all rows except first
        if len(self.criteria_rows) > 1:
            row.logic_combo.setVisible(True)
        
        # Update visual indicators
        self._update_group_indentation()
    
    def _remove_criterion_row(self, row: CriteriaRowWidget) -> None:
        """Remove a criterion row.
        
        Args:
            row: CriteriaRowWidget to remove.
        """
        if row in self.criteria_rows:
            idx = self.criteria_rows.index(row)
            self.criteria_rows.remove(row)
            self.criteria_layout.removeWidget(row)
            row.deleteLater()
            
            # Remove from group tracking
            if idx in self.group_starts:
                self.group_starts.remove(idx)
                if idx in self.group_levels:
                    del self.group_levels[idx]
            if idx in self.group_ends:
                self.group_ends.remove(idx)
            
            # Update indices for remaining groups
            new_group_starts = []
            new_group_ends = []
            new_group_levels = {}
            for old_idx in self.group_starts:
                if old_idx < idx:
                    new_group_starts.append(old_idx)
                    if old_idx in self.group_levels:
                        new_group_levels[old_idx] = self.group_levels[old_idx]
                elif old_idx > idx:
                    new_group_starts.append(old_idx - 1)
                    if old_idx in self.group_levels:
                        new_group_levels[old_idx - 1] = self.group_levels[old_idx]
            for old_idx in self.group_ends:
                if old_idx < idx:
                    new_group_ends.append(old_idx)
                elif old_idx > idx:
                    new_group_ends.append(old_idx - 1)
            
            self.group_starts = new_group_starts
            self.group_ends = new_group_ends
            self.group_levels = new_group_levels
            
            # Update logic connector visibility
            if len(self.criteria_rows) > 0:
                self.criteria_rows[0].logic_combo.setVisible(False)
                if len(self.criteria_rows) > 1:
                    self.criteria_rows[1].logic_combo.setVisible(True)
            
            # Update visual indicators
            self._update_group_indentation()
    
    def _on_start_group_clicked(self) -> None:
        """Handle Start Group button click - adds a new criterion row marked as group start."""
        self._add_criterion_row(is_group_start=True)
    
    def _on_end_group_clicked(self) -> None:
        """Handle End Group button click - marks the last criterion as group end."""
        if not self.criteria_rows:
            return
        
        idx = len(self.criteria_rows) - 1
        
        # Find matching group start (most recent start before this end)
        matching_start = None
        
        for start_idx in sorted(self.group_starts, reverse=True):
            if start_idx < idx:
                # Check if there's already an end for this start
                has_end = any(end_idx > start_idx and end_idx <= idx for end_idx in self.group_ends)
                if not has_end:
                    matching_start = start_idx
                    break
        
        if matching_start is not None:
            # Add group end marker
            if idx not in self.group_ends:
                self.group_ends.append(idx)
        
        # Update visual indicators
        self.update_group_visuals()
    
    def _update_group_indentation(self) -> None:
        """Update visual indentation for grouped rows."""
        self.update_group_visuals()
    
    def update_group_visuals(self) -> None:
        """Update all visual indicators for groups."""
        # Calculate indentation for each row based on group nesting
        for i, row in enumerate(self.criteria_rows):
            # Calculate how many groups this row is nested in
            indent_level = 0
            current_group_start = None
            
            for start_idx in sorted(self.group_starts):
                if start_idx <= i:
                    # Find matching end for this start
                    matching_end = None
                    for end_idx in sorted(self.group_ends):
                        if end_idx > start_idx:
                            # Check if there's a nested start between start_idx and end_idx
                            has_nested_start = any(s > start_idx and s < end_idx for s in self.group_starts)
                            if not has_nested_start:
                                matching_end = end_idx
                                break
                    
                    # If this row is between start and end (or end not found yet), it's in this group
                    if matching_end is None or matching_end >= i:
                        if start_idx < i:
                            indent_level += 1
                        if start_idx == i:
                            current_group_start = start_idx
                else:
                    break
            
            # Apply indentation
            row.set_indentation(indent_level)
            
            # Visual indicator: add background color and border for grouped rows
            base_style = ""
            if i in self.group_starts:
                # Group start: left border
                base_style += "QWidget { border-left: 3px solid rgba(100, 150, 255, 150); padding-left: 5px; }"
            if i in self.group_ends:
                # Group end: right border
                base_style += "QWidget { border-right: 3px solid rgba(100, 150, 255, 150); padding-right: 5px; }"
            if indent_level > 0:
                # Nested rows: subtle background
                base_style += "QWidget { background-color: rgba(70, 90, 130, 20); }"
            
            if base_style:
                row.setStyleSheet(base_style)
            else:
                row.setStyleSheet("")
    
    def _apply_styling(self) -> None:
        """Apply styling from config.json."""
        # Background color
        palette = self.palette()
        palette.setColor(self.backgroundRole(), self.bg_color)
        self.setPalette(palette)
        self.setAutoFillBackground(True)
        
        # Group box styling (matching bulk replace dialog)
        dialog_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {})
        groups_config = dialog_config.get("groups", {})
        dialog_bg = dialog_config.get("background_color", [40, 40, 45])
        dialog_border = dialog_config.get("border_color", [60, 60, 65])
        
        group_bg_color = groups_config.get("background_color", dialog_bg) if "background_color" in groups_config else dialog_bg
        group_border_color = groups_config.get("border_color", dialog_border) if "border_color" in groups_config else dialog_border
        group_border_radius = groups_config.get("border_radius", 5)
        group_title_font_family = groups_config.get("title_font_family", "Helvetica Neue")
        group_title_font_size = groups_config.get("title_font_size", 11)
        group_title_color = groups_config.get("title_color", [240, 240, 240])
        group_content_margins = groups_config.get("content_margins", [10, 20, 10, 15])
        group_margin_top = groups_config.get("margin_top", 10)
        group_padding_top = groups_config.get("padding_top", 5)
        
        group_title_left = groups_config.get("title_left", 10)
        group_title_padding = groups_config.get("title_padding", [0, 5])
        
        group_style = (
            f"QGroupBox {{"
            f"background-color: rgb({group_bg_color[0]}, {group_bg_color[1]}, {group_bg_color[2]});"
            f"border: 1px solid rgb({group_border_color[0]}, {group_border_color[1]}, {group_border_color[2]});"
            f"border-radius: {group_border_radius}px;"
            f"margin-top: {group_margin_top}px;"
            f"padding-top: {group_padding_top}px;"
            f"}}"
            f"QGroupBox::title {{"
            f"subcontrol-origin: margin;"
            f"subcontrol-position: top left;"
            f"left: {group_title_left}px;"
            f"padding: {group_title_padding[0]} {group_title_padding[1]}px;"
            f"font-family: {group_title_font_family};"
            f"font-size: {group_title_font_size}pt;"
            f"color: rgb({group_title_color[0]}, {group_title_color[1]}, {group_title_color[2]});"
            f"}}"
        )
        
        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(group_style)
            layout = group.layout()
            if layout:
                layout.setContentsMargins(
                    group_content_margins[0],
                    group_content_margins[1],
                    group_content_margins[2],
                    group_content_margins[3]
                )
        
        # Radio button styling
        radio_style = (
            f"QRadioButton {{"
            f"font-family: {self.label_font_family};"
            f"font-size: {self.label_font_size}pt;"
            f"color: rgb({self.label_text_color.red()}, {self.label_text_color.green()}, {self.label_text_color.blue()});"
            f"spacing: 5px;"
            f"}}"
        )
        for radio in self.findChildren(QRadioButton):
            radio.setStyleSheet(radio_style)
        
        # Button styling (standardized pattern)
        buttons_config = self.config.get("ui", {}).get("dialogs", {}).get("search", {}).get("buttons", {})
        button_bg_offset = buttons_config.get("background_offset", 20)
        button_hover_offset = buttons_config.get("hover_background_offset", 30)
        button_pressed_offset = buttons_config.get("pressed_background_offset", 10)
        button_border_radius = buttons_config.get("border_radius", 3)
        button_padding = buttons_config.get("padding", 5)
        
        button_style = (
            f"QPushButton {{"
            f"min-width: {self.button_width}px;"
            f"min-height: {self.button_height}px;"
            f"font-family: {self.font_family};"
            f"font-size: {self.font_size}pt;"
            f"color: rgb({self.text_color.red()}, {self.text_color.green()}, {self.text_color.blue()});"
            f"background-color: rgb({self.bg_color.red() + button_bg_offset}, {self.bg_color.green() + button_bg_offset}, {self.bg_color.blue() + button_bg_offset});"
            f"border: 1px solid rgb({self.bg_color.red() + button_bg_offset}, {self.bg_color.green() + button_bg_offset}, {self.bg_color.blue() + button_bg_offset});"
            f"border-radius: {button_border_radius}px;"
            f"padding: {button_padding}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({self.bg_color.red() + button_hover_offset}, {self.bg_color.green() + button_hover_offset}, {self.bg_color.blue() + button_hover_offset});"
            f"border-color: rgb({self.bg_color.red() + button_hover_offset}, {self.bg_color.green() + button_hover_offset}, {self.bg_color.blue() + button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({self.bg_color.red() + button_pressed_offset}, {self.bg_color.green() + button_pressed_offset}, {self.bg_color.blue() + button_pressed_offset});"
            f"border-color: rgb({self.bg_color.red() + button_pressed_offset}, {self.bg_color.green() + button_pressed_offset}, {self.bg_color.blue() + button_pressed_offset});"
            f"}}"
        )
        
        for button in self.findChildren(QPushButton):
            button.setStyleSheet(button_style)
    
    def _on_search_clicked(self) -> None:
        """Handle search button click."""
        # Automatically close the last unclosed group if needed
        if self.criteria_rows and self.group_starts:
            # Find the last group start that doesn't have a corresponding end
            last_unclosed_start = None
            for start_idx in sorted(self.group_starts, reverse=True):
                # Check if this start has an end
                has_end = any(end_idx > start_idx for end_idx in self.group_ends)
                if not has_end:
                    last_unclosed_start = start_idx
                    break
            
            # If there's an unclosed group, close it at the last row
            if last_unclosed_start is not None:
                last_row_idx = len(self.criteria_rows) - 1
                if last_row_idx not in self.group_ends:
                    self.group_ends.append(last_row_idx)
                # Update visual indicators
                self.update_group_visuals()
        
        # Collect criteria from rows
        criteria: List[SearchCriteria] = []
        
        # Collect all criteria and mark group starts/ends
        for i, row in enumerate(self.criteria_rows):
            criterion = row.get_criterion()
            if criterion is None:
                continue
            
            # Check if this row is a group start
            if i in self.group_starts:
                criterion.is_group_start = True
                criterion.group_level = self.group_levels.get(i, 0)
            
            # Check if this row is a group end
            if i in self.group_ends:
                criterion.is_group_end = True
                # Find matching group start to get level
                for start_idx in sorted(self.group_starts, reverse=True):
                    if start_idx < i:
                        criterion.group_level = self.group_levels.get(start_idx, 0)
                        break
            
            criteria.append(criterion)
        
        # Determine scope
        scope = "active" if self.active_radio.isChecked() else "all"
        
        # Create search query
        self.search_query = SearchQuery(scope=scope, criteria=criteria)
        
        # Save to memory for next time
        SearchDialog._last_search_query = self.search_query
        
        self.accept()
    
    def get_search_query(self) -> Optional[SearchQuery]:
        """Get the search query.
        
        Returns:
            SearchQuery instance or None if dialog was cancelled.
        """
        return self.search_query
    
    def _restore_last_search(self) -> None:
        """Restore the last search query from memory."""
        if SearchDialog._last_search_query is None:
            return
        
        query = SearchDialog._last_search_query
        
        # Restore scope
        if query.scope == "active":
            self.active_radio.setChecked(True)
        else:
            self.all_radio.setChecked(True)
        
        # Clear existing criteria rows
        for row in self.criteria_rows[:]:
            self._remove_criterion_row(row)
        
        # Clear group tracking
        self.group_starts.clear()
        self.group_ends.clear()
        self.group_levels.clear()
        
        # Rebuild criteria rows from saved query
        for i, criterion in enumerate(query.criteria):
            # Add row (will be at index i)
            is_group_start = criterion.is_group_start
            self._add_criterion_row(is_group_start=is_group_start)
            
            # Restore group level if this is a group start
            if is_group_start:
                self.group_levels[i] = criterion.group_level
            
            # Set the criterion values
            row = self.criteria_rows[i]
            row.set_criterion(criterion)
            
            # Show logic connector for all rows except first
            if i > 0:
                row.logic_combo.setVisible(True)
            
            # Mark group end if needed
            if criterion.is_group_end:
                self.group_ends.append(i)
        
        # Update visual indicators
        self._update_group_indentation()

