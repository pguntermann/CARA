"""Classification settings dialog for configuring move assessment thresholds and brilliancy criteria."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QCheckBox,
    QPushButton,
    QScrollArea,
    QWidget,
    QGroupBox,
    QFormLayout,
    QSizePolicy,
    QApplication,
    QFrame,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QShowEvent, QColor, QPalette, QPainter, QPen, QFont, QFontMetrics
from typing import Optional, Dict, Any, Tuple

from app.controllers.move_classification_controller import MoveClassificationController
from app.utils.font_utils import resolve_font_family, scale_font_size


class CPLScaleWidget(QWidget):
    """Widget for displaying a visual CPL scale with threshold markers."""
    
    def __init__(self, config: Dict[str, Any], thresholds: Dict[str, int], parent=None) -> None:
        """Initialize the CPL scale widget.
        
        Args:
            config: Configuration dictionary.
            thresholds: Dictionary with threshold values.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.thresholds = thresholds
        
        # Get scale config
        dialog_config = config.get('ui', {}).get('dialogs', {}).get('classification_settings', {})
        scale_config = dialog_config.get('cpl_scale', {})
        
        self.scale_height = scale_config.get('height', 80)
        self.padding = scale_config.get('padding', [10, 10, 10, 10])
        self.scale_max = scale_config.get('scale_max', 500)
        self.blunder_compression_enabled = scale_config.get('blunder_compression_enabled', True)
        self.blunder_compression_factor = scale_config.get('blunder_compression_factor', 0.4)
        self.background_color = QColor(*scale_config.get('background_color', [40, 40, 45]))
        self.scale_line_color = QColor(*scale_config.get('scale_line_color', [150, 150, 150]))
        self.tick_color = QColor(*scale_config.get('tick_color', [200, 200, 200]))
        self.text_color = QColor(*scale_config.get('text_color', [220, 220, 220]))
        self.font_size = scale_font_size(scale_config.get('font_size', 9))
        font_family_raw = scale_config.get('font_family', 'Helvetica Neue')
        self.font_family = resolve_font_family(font_family_raw)
        self.scale_config = scale_config  # Store for use in paintEvent
        
        # Threshold colors
        self.colors = {
            'best_move': QColor(*scale_config.get('best_move_color', [100, 255, 100])),
            'good_move': QColor(*scale_config.get('good_move_color', [150, 255, 150])),
            'inaccuracy': QColor(*scale_config.get('inaccuracy_color', [255, 255, 100])),
            'mistake': QColor(*scale_config.get('mistake_color', [255, 200, 100])),
            'blunder': QColor(*scale_config.get('blunder_color', [255, 100, 100])),
        }
        
        self.setMinimumHeight(self.scale_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    
    def update_thresholds(self, thresholds: Dict[str, int]) -> None:
        """Update threshold values and redraw.
        
        Args:
            thresholds: Dictionary with threshold values.
        """
        self.thresholds = thresholds
        self.update()
    
    def paintEvent(self, event) -> None:
        """Paint the CPL scale."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        width = self.width()
        height = self.height()
        
        # Draw background
        painter.fillRect(0, 0, width, height, self.background_color)
        
        # Calculate drawing area
        left = self.padding[0]
        right = width - self.padding[2]
        top = self.padding[1]
        bottom = height - self.padding[3]
        scale_width = right - left
        scale_height = bottom - top
        
        # Draw colored sections for each threshold range
        good = self.thresholds.get("good_move_max_cpl", 50)
        inaccuracy = self.thresholds.get("inaccuracy_max_cpl", 100)
        mistake = self.thresholds.get("mistake_max_cpl", 200)
        
        # Calculate positions with optional non-linear compression for blunders
        def cpl_to_x(cpl: int) -> float:
            if not self.blunder_compression_enabled or cpl <= mistake:
                # Linear scale for all values or values up to mistake threshold
                return left + (cpl / self.scale_max) * scale_width
            else:
                # Non-linear compression for blunders (above mistake threshold)
                # Calculate how much space the linear portion (0 to mistake) should take
                # We want the linear portion to use more space, and blunders to be compressed
                linear_portion_ratio = mistake / self.scale_max
                # Allocate more space to linear portion, less to blunders
                # If compression_factor = 0.4, blunders use 40% of what they would in linear scale
                blunder_portion_ratio = (self.scale_max - mistake) / self.scale_max
                compressed_blunder_ratio = blunder_portion_ratio * self.blunder_compression_factor
                
                # Total ratio should be 1.0, so adjust linear portion to fill remaining space
                total_ratio = linear_portion_ratio + compressed_blunder_ratio
                if total_ratio > 0:
                    # Normalize so it fills the full width
                    linear_portion_width = scale_width * (linear_portion_ratio / total_ratio)
                    blunder_portion_width = scale_width * (compressed_blunder_ratio / total_ratio)
                else:
                    linear_portion_width = scale_width
                    blunder_portion_width = 0
                
                # Position of mistake threshold
                mistake_x = left + linear_portion_width
                
                # Map CPL from mistake to scale_max onto the compressed blunder width
                blunder_cpl_range = self.scale_max - mistake
                blunder_cpl = cpl - mistake
                compressed_x = mistake_x + (blunder_cpl / blunder_cpl_range) * blunder_portion_width
                
                return compressed_x
        
        font = QFont(self.font_family, self.font_size)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        
        # Calculate vertical positions: numbers at top, colored bar in middle, scale line, labels at bottom (two rows)
        number_height_offset = self.scale_config.get('number_height_offset', 4)
        section_height = self.scale_config.get('section_height', 12)
        scale_line_offset = self.scale_config.get('scale_line_offset', 8)
        label_row_spacing = self.scale_config.get('label_row_spacing', 15)
        label_y_offset_row1 = self.scale_config.get('label_y_offset_row1', 20)
        
        number_height = metrics.height() + number_height_offset  # Space for numbers at top
        scale_line_y = top + number_height + section_height + scale_line_offset  # Position of main scale line
        label_y_offset_row2 = label_y_offset_row1 + metrics.height() + label_row_spacing  # Space for second row
        
        # Draw scale numbers at regular intervals (at top, above colored bar)
        painter.setPen(QPen(self.text_color, 1))
        
        # Draw numbers up to mistake threshold (linear)
        for i in range(0, mistake + 1, 50):
            if i > mistake:
                break
            x = cpl_to_x(i)
            # Draw number
            number_text = str(i)
            number_width = metrics.horizontalAdvance(number_text)
            painter.drawText(int(x - number_width / 2), int(top + metrics.ascent() + 2), number_text)
        
        # Draw numbers in blunder range (compressed)
        if self.blunder_compression_enabled:
            # Show only the end of the scale, omit all intermediate values
            x = cpl_to_x(self.scale_max)
            number_text = str(self.scale_max)
            number_width = metrics.horizontalAdvance(number_text)
            painter.drawText(int(x - number_width / 2), int(top + metrics.ascent() + 2), number_text)
        else:
            # Linear scale: draw all numbers
            for i in range(mistake + 50, self.scale_max + 1, 50):
                if i > self.scale_max:
                    break
                x = cpl_to_x(i)
                # Draw number
                number_text = str(i)
                number_width = metrics.horizontalAdvance(number_text)
                painter.drawText(int(x - number_width / 2), int(top + metrics.ascent() + 2), number_text)
        
        # Draw colored sections (below numbers)
        section_y = top + number_height + 2
        
        # Good Move (0 to good)
        if good > 0:
            painter.fillRect(int(left), int(section_y), int(cpl_to_x(good) - left), int(section_height), self.colors['good_move'])
        
        # Inaccuracy (good to inaccuracy)
        if inaccuracy > good:
            painter.fillRect(int(cpl_to_x(good)), int(section_y), int(cpl_to_x(inaccuracy) - cpl_to_x(good)), int(section_height), self.colors['inaccuracy'])
        
        # Mistake (inaccuracy to mistake)
        if mistake > inaccuracy:
            painter.fillRect(int(cpl_to_x(inaccuracy)), int(section_y), int(cpl_to_x(mistake) - cpl_to_x(inaccuracy)), int(section_height), self.colors['mistake'])
        
        # Blunder (mistake to scale_max)
        if self.scale_max > mistake:
            painter.fillRect(int(cpl_to_x(mistake)), int(section_y), int(right - cpl_to_x(mistake)), int(section_height), self.colors['blunder'])
        
        # Draw main scale line (below colored bar)
        painter.setPen(QPen(self.scale_line_color, 2))
        painter.drawLine(int(left), int(scale_line_y), int(right), int(scale_line_y))
        
        # Draw threshold markers and labels (distribute across two rows to avoid overlap)
        marker_height = self.scale_config.get('marker_height', 8)
        painter.setPen(QPen(self.tick_color, 1))
        
        thresholds_to_draw = [
            (good, "Good"),
            (inaccuracy, "Inaccuracy"),
            (mistake, "Mistake"),
        ]
        
        # Distribute labels across two rows in alternating order
        # Row 1: Good, Mistake
        # Row 2: Inaccuracy
        for idx, (cpl, label) in enumerate(thresholds_to_draw):
            x = cpl_to_x(cpl)
            # Draw tick mark
            painter.drawLine(int(x), int(scale_line_y), int(x), int(scale_line_y + marker_height))
            
            label_width = metrics.horizontalAdvance(label)
            label_x = x - label_width / 2
            
            # Alternate rows: index 0 (Good) -> row 1, index 1 (Inaccuracy) -> row 2, 
            # index 2 (Mistake) -> row 1
            use_row2 = (idx % 2 == 1)
            
            if use_row2:
                label_y = scale_line_y + marker_height + label_y_offset_row2
            else:
                label_y = scale_line_y + marker_height + label_y_offset_row1
            
            painter.setPen(QPen(self.text_color, 1))
            painter.drawText(int(label_x), int(label_y), label)
            painter.setPen(QPen(self.tick_color, 1))
        
        # Draw small ticks for scale numbers
        painter.setPen(QPen(self.tick_color, 1))
        
        # Draw ticks up to mistake threshold (linear)
        for i in range(0, mistake + 1, 50):
            if i > mistake:
                break
            x = cpl_to_x(i)
            # Draw small tick on scale line
            painter.drawLine(int(x), int(scale_line_y), int(x), int(scale_line_y + 4))
        
        # Draw ticks in blunder range (compressed)
        if self.blunder_compression_enabled:
            # Show only the end of the scale, omit all intermediate values
            x = cpl_to_x(self.scale_max)
            painter.drawLine(int(x), int(scale_line_y), int(x), int(scale_line_y + 4))
        else:
            # Linear scale: draw all ticks
            for i in range(mistake + 50, self.scale_max + 1, 50):
                if i > self.scale_max:
                    break
                x = cpl_to_x(i)
                # Draw small tick on scale line
                painter.drawLine(int(x), int(scale_line_y), int(x), int(scale_line_y + 4))


class ClassificationSettingsDialog(QDialog):
    """Dialog for configuring move classification settings."""
    
    def __init__(self, config: Dict[str, Any], classification_controller: MoveClassificationController, parent=None) -> None:
        """Initialize the classification settings dialog.
        
        Args:
            config: Configuration dictionary.
            classification_controller: MoveClassificationController instance.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.classification_controller = classification_controller
        
        # Get current values from model
        classification_model = classification_controller.get_classification_model()
        self.current_thresholds = classification_model.get_assessment_thresholds()
        self.current_brilliant = classification_model.get_brilliant_criteria()
        
        # Get defaults from config for reset functionality
        game_analysis_config = config.get("game_analysis", {})
        self.default_thresholds = game_analysis_config.get("assessment_thresholds", {})
        self.default_brilliant = game_analysis_config.get("brilliant_criteria", {})
        
        # Store fixed size - set it BEFORE layout is set up
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('classification_settings', {})
        width = dialog_config.get('width', 600)
        height = dialog_config.get('height', 700)
        self._fixed_size = QSize(width, height)
        
        # Set fixed size BEFORE UI setup
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        self._setup_ui()
        self._apply_styling()
        self.setWindowTitle("Classification Settings")
    
    def showEvent(self, event: QShowEvent) -> None:
        """Handle show event to enforce fixed size and refresh values from model."""
        super().showEvent(event)
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        
        # Refresh values from model in case they were changed elsewhere
        classification_model = self.classification_controller.get_classification_model()
        self.current_thresholds = classification_model.get_assessment_thresholds()
        self.current_brilliant = classification_model.get_brilliant_criteria()
        
        # Update UI with current values
        self.good_move_spinbox.setValue(self.current_thresholds.get("good_move_max_cpl", 50))
        self.inaccuracy_spinbox.setValue(self.current_thresholds.get("inaccuracy_max_cpl", 100))
        self.mistake_spinbox.setValue(self.current_thresholds.get("mistake_max_cpl", 200))
        
        self.material_sacrifice_spinbox.setValue(self.current_brilliant.get("min_material_sacrifice", 300))
        self.eval_swing_spinbox.setValue(self.current_brilliant.get("min_eval_swing", 50))
        self.exclude_winning_check.setChecked(self.current_brilliant.get("exclude_already_winning", True))
        self.max_eval_before_spinbox.setValue(self.current_brilliant.get("max_eval_before", 500))
        self.lookahead_plies_spinbox.setValue(self.current_brilliant.get("material_sacrifice_lookahead_plies", 3))
        
        # Update enabled state and styling for max_eval_before
        self._on_exclude_winning_toggled(self.exclude_winning_check.isChecked())
        
        # Update CPL scale
        self._update_cpl_scale()
    
    def sizeHint(self) -> QSize:
        """Return the fixed size as the size hint."""
        return self._fixed_size
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        # Get layout spacing and margins from config
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('classification_settings', {})
        layout_config = dialog_config.get('layout', {})
        buttons_config = dialog_config.get('buttons', {})
        layout_spacing = layout_config.get('spacing', 15)
        layout_margins = layout_config.get('margins', [20, 20, 20, 20])
        section_spacing = layout_config.get('section_spacing', 20)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(layout_spacing)
        layout.setContentsMargins(layout_margins[0], layout_margins[1], layout_margins[2], layout_margins[3])
        
        # Create scroll area for form
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.Shape.NoFrame)  # Remove border on macOS
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(section_spacing)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        
        # Move Quality Thresholds group
        thresholds_group = self._create_thresholds_group()
        scroll_layout.addWidget(thresholds_group)
        
        # CPL Scale visualization
        self.cpl_scale_widget = self._create_cpl_scale_widget()
        scroll_layout.addWidget(self.cpl_scale_widget)
        
        # Brilliant Move Criteria group
        brilliant_group = self._create_brilliant_group()
        scroll_layout.addWidget(brilliant_group)
        
        scroll_layout.addStretch()
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_spacing = buttons_config.get('spacing', 10)
        button_layout.setSpacing(button_spacing)
        
        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.clicked.connect(self._reset_to_defaults)
        button_layout.addWidget(self.reset_button)
        
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_button)
        
        layout.addLayout(button_layout)
    
    def _create_thresholds_group(self) -> QGroupBox:
        """Create the Move Quality Thresholds group box."""
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('classification_settings', {})
        groups_config = dialog_config.get('groups', {})
        fields_config = dialog_config.get('fields', {})
        
        group = QGroupBox("Move Quality Thresholds")
        
        form_layout = QFormLayout()
        form_layout.setSpacing(fields_config.get('spacing', 8))
        # Set alignment for macOS compatibility (left-align labels and form)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        input_width = fields_config.get('input_width', 100)
        label_width = fields_config.get('label_width', 200)
        right_padding = fields_config.get('right_padding', 20)
        
        # Helper to create aligned label
        def create_label(text: str) -> QLabel:
            label = QLabel(text)
            label.setFixedWidth(label_width)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return label
        
        # Helper to wrap input in a right-aligned container with padding
        def create_input_widget(input_widget: QSpinBox) -> QWidget:
            container = QWidget()
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(0, 0, right_padding, 0)
            container_layout.setSpacing(0)
            container_layout.addStretch()
            container_layout.addWidget(input_widget)
            return container
        
        # Good Move Max CPL
        self.good_move_spinbox = QSpinBox()
        self.good_move_spinbox.setRange(0, 1000)
        self.good_move_spinbox.setValue(self.current_thresholds.get("good_move_max_cpl", 50))
        self.good_move_spinbox.setToolTip("Maximum CPL (centipawns) for a move to be considered 'Good Move'")
        self.good_move_spinbox.setFixedWidth(input_width)
        self.good_move_spinbox.setMinimumHeight(25)
        self.good_move_spinbox.valueChanged.connect(self._on_good_move_changed)
        form_layout.addRow(create_label("Good Move Max CPL:"), create_input_widget(self.good_move_spinbox))
        
        # Inaccuracy Max CPL
        self.inaccuracy_spinbox = QSpinBox()
        self.inaccuracy_spinbox.setRange(0, 1000)
        self.inaccuracy_spinbox.setValue(self.current_thresholds.get("inaccuracy_max_cpl", 100))
        self.inaccuracy_spinbox.setToolTip("Maximum CPL (centipawns) for a move to be considered 'Inaccuracy'")
        self.inaccuracy_spinbox.setFixedWidth(input_width)
        self.inaccuracy_spinbox.setMinimumHeight(25)
        self.inaccuracy_spinbox.valueChanged.connect(self._on_inaccuracy_changed)
        form_layout.addRow(create_label("Inaccuracy Max CPL:"), create_input_widget(self.inaccuracy_spinbox))
        
        # Mistake Max CPL
        self.mistake_spinbox = QSpinBox()
        self.mistake_spinbox.setRange(0, 1000)
        self.mistake_spinbox.setValue(self.current_thresholds.get("mistake_max_cpl", 200))
        self.mistake_spinbox.setToolTip("Maximum CPL (centipawns) for a move to be considered 'Mistake'")
        self.mistake_spinbox.setFixedWidth(input_width)
        self.mistake_spinbox.setMinimumHeight(25)
        self.mistake_spinbox.valueChanged.connect(self._on_mistake_changed)
        form_layout.addRow(create_label("Mistake Max CPL:"), create_input_widget(self.mistake_spinbox))
        
        # Initialize spinbox ranges after all spinboxes are created
        self._update_spinbox_ranges()
        
        group.setLayout(form_layout)
        return group
    
    def _create_cpl_scale_widget(self) -> CPLScaleWidget:
        """Create the CPL scale visualization widget."""
        return CPLScaleWidget(self.config, self.current_thresholds)
    
    def _get_threshold_values(self) -> Dict[str, int]:
        """Get current threshold values from spinboxes."""
        return {
            "good_move_max_cpl": self.good_move_spinbox.value(),
            "inaccuracy_max_cpl": self.inaccuracy_spinbox.value(),
            "mistake_max_cpl": self.mistake_spinbox.value()
        }
    
    def _update_cpl_scale(self) -> None:
        """Update the CPL scale widget when threshold values change."""
        thresholds = self._get_threshold_values()
        self.cpl_scale_widget.update_thresholds(thresholds)
    
    def _update_spinbox_ranges(self) -> None:
        """Update spinbox ranges to prevent invalid combinations."""
        good_value = self.good_move_spinbox.value()
        inaccuracy_value = self.inaccuracy_spinbox.value()
        mistake_value = self.mistake_spinbox.value()
        
        # Good Move Max CPL: 0 to Inaccuracy Max CPL
        self.good_move_spinbox.setMaximum(inaccuracy_value)
        
        # Inaccuracy Max CPL: Good Move Max CPL to Mistake Max CPL
        self.inaccuracy_spinbox.setMinimum(good_value)
        self.inaccuracy_spinbox.setMaximum(mistake_value)
        
        # Mistake Max CPL: Inaccuracy Max CPL to 1000
        self.mistake_spinbox.setMinimum(inaccuracy_value)
    
    def _on_good_move_changed(self, value: int) -> None:
        """Handle Good Move Max CPL spinbox change with auto-adjustment."""
        inaccuracy_value = self.inaccuracy_spinbox.value()
        
        # If Good exceeds Inaccuracy, increase Inaccuracy (and all following thresholds)
        if value > inaccuracy_value:
            # Update Inaccuracy first
            self.inaccuracy_spinbox.blockSignals(True)
            self.inaccuracy_spinbox.setValue(value)
            self.inaccuracy_spinbox.blockSignals(False)
            
            # Then update Mistake if needed
            mistake_value = self.mistake_spinbox.value()
            if value > mistake_value:
                self.mistake_spinbox.blockSignals(True)
                self.mistake_spinbox.setValue(value)
                self.mistake_spinbox.blockSignals(False)
                mistake_value = value
        
        # Update ranges based on new values
        self._update_spinbox_ranges()
        self._update_cpl_scale()
    
    def _on_inaccuracy_changed(self, value: int) -> None:
        """Handle Inaccuracy Max CPL spinbox change with auto-adjustment."""
        good_value = self.good_move_spinbox.value()
        mistake_value = self.mistake_spinbox.value()
        
        # If Inaccuracy is less than Good, decrease Good
        if value < good_value:
            self.good_move_spinbox.blockSignals(True)
            self.good_move_spinbox.setValue(value)
            self.good_move_spinbox.blockSignals(False)
        
        # If Inaccuracy exceeds Mistake, increase Mistake
        if value > mistake_value:
            # Update Mistake
            self.mistake_spinbox.blockSignals(True)
            self.mistake_spinbox.setValue(value)
            self.mistake_spinbox.blockSignals(False)
        
        # Update ranges based on new values
        self._update_spinbox_ranges()
        self._update_cpl_scale()
    
    def _on_mistake_changed(self, value: int) -> None:
        """Handle Mistake Max CPL spinbox change with auto-adjustment."""
        inaccuracy_value = self.inaccuracy_spinbox.value()
        
        # If Mistake is less than Inaccuracy, decrease Inaccuracy (and all preceding thresholds)
        if value < inaccuracy_value:
            self.inaccuracy_spinbox.blockSignals(True)
            self.inaccuracy_spinbox.setValue(value)
            self.inaccuracy_spinbox.blockSignals(False)
            
            # Also decrease Good if needed
            good_value = self.good_move_spinbox.value()
            if value < good_value:
                self.good_move_spinbox.blockSignals(True)
                self.good_move_spinbox.setValue(value)
                self.good_move_spinbox.blockSignals(False)
        
        # Update ranges based on new values
        self._update_spinbox_ranges()
        self._update_cpl_scale()
    
    def _create_brilliant_group(self) -> QGroupBox:
        """Create the Brilliant Move Criteria group box."""
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('classification_settings', {})
        groups_config = dialog_config.get('groups', {})
        fields_config = dialog_config.get('fields', {})
        
        group = QGroupBox("Brilliant Move Criteria")
        
        form_layout = QFormLayout()
        form_layout.setSpacing(fields_config.get('spacing', 8))
        # Set alignment for macOS compatibility (left-align labels and form)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        input_width = fields_config.get('input_width', 100)
        label_width = fields_config.get('label_width', 200)
        right_padding = fields_config.get('right_padding', 20)
        
        # Helper to create aligned label
        def create_label(text: str) -> QLabel:
            label = QLabel(text)
            label.setFixedWidth(label_width)
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return label
        
        # Helper to wrap input in a right-aligned container with padding
        def create_input_widget(input_widget: QSpinBox) -> QWidget:
            container = QWidget()
            container_layout = QHBoxLayout(container)
            container_layout.setContentsMargins(0, 0, right_padding, 0)
            container_layout.setSpacing(0)
            container_layout.addStretch()
            container_layout.addWidget(input_widget)
            return container
        
        # Helper to wrap checkbox to align with left edge of input fields
        def create_checkbox_widget(checkbox: QCheckBox) -> QWidget:
            container = QWidget()
            container_layout = QHBoxLayout(container)
            # Add extra right margin to prevent checkbox border truncation
            container_layout.setContentsMargins(0, 0, right_padding + 2, 0)
            container_layout.setSpacing(0)
            # Use the same stretch as input fields to position checkbox indicator at the same horizontal start position
            container_layout.addStretch()
            # Add checkbox - this aligns the checkbox indicator's left edge with input field left edge
            container_layout.addWidget(checkbox)
            return container
        
        # Material Sacrifice
        self.material_sacrifice_spinbox = QSpinBox()
        self.material_sacrifice_spinbox.setRange(0, 10000)
        self.material_sacrifice_spinbox.setValue(self.current_brilliant.get("min_material_sacrifice", 300))
        self.material_sacrifice_spinbox.setFixedWidth(input_width)
        self.material_sacrifice_spinbox.setMinimumHeight(25)
        self.material_sacrifice_spinbox.setToolTip("Minimum material sacrifice (centipawns) required for brilliancy")
        form_layout.addRow(create_label("Min Material Sacrifice:"), create_input_widget(self.material_sacrifice_spinbox))
        
        # Eval Swing
        self.eval_swing_spinbox = QSpinBox()
        self.eval_swing_spinbox.setRange(0, 10000)
        self.eval_swing_spinbox.setValue(self.current_brilliant.get("min_eval_swing", 50))
        self.eval_swing_spinbox.setFixedWidth(input_width)
        self.eval_swing_spinbox.setMinimumHeight(25)
        self.eval_swing_spinbox.setToolTip("Minimum evaluation swing (centipawns) required for brilliancy")
        form_layout.addRow(create_label("Min Eval Swing:"), create_input_widget(self.eval_swing_spinbox))
        
        # Exclude Already Winning (must come before Max Eval Before to show dependency)
        self.exclude_winning_check = QCheckBox()
        self.exclude_winning_check.setChecked(self.current_brilliant.get("exclude_already_winning", True))
        self.exclude_winning_check.setToolTip("Exclude moves from already winning positions. When enabled, uses 'Max Eval Before' threshold to determine if position is already winning.")
        form_layout.addRow(create_label("Exclude Already Winning:"), create_checkbox_widget(self.exclude_winning_check))
        
        # Max Eval Before (only used when Exclude Already Winning is enabled)
        self.max_eval_before_spinbox = QSpinBox()
        self.max_eval_before_spinbox.setRange(-10000, 10000)
        self.max_eval_before_spinbox.setValue(self.current_brilliant.get("max_eval_before", 500))
        self.max_eval_before_spinbox.setFixedWidth(input_width)
        self.max_eval_before_spinbox.setMinimumHeight(25)
        self.max_eval_before_spinbox.setToolTip("Maximum evaluation before move (centipawns). Only used when 'Exclude Already Winning' is enabled. Moves from positions with eval above this threshold are excluded from brilliancy.")
        # Connect checkbox to enable/disable this field and update styling
        self.exclude_winning_check.toggled.connect(self._on_exclude_winning_toggled)
        self.max_eval_before_spinbox.setEnabled(self.exclude_winning_check.isChecked())
        form_layout.addRow(create_label("Max Eval Before:"), create_input_widget(self.max_eval_before_spinbox))
        
        # Material Sacrifice Lookahead Plies
        self.lookahead_plies_spinbox = QSpinBox()
        self.lookahead_plies_spinbox.setRange(1, 5)
        self.lookahead_plies_spinbox.setValue(self.current_brilliant.get("material_sacrifice_lookahead_plies", 3))
        self.lookahead_plies_spinbox.setFixedWidth(input_width)
        self.lookahead_plies_spinbox.setMinimumHeight(25)
        self.lookahead_plies_spinbox.setToolTip("Number of plies to look ahead when detecting material sacrifice. This setting is relevant only if 'Post-Game Brilliancy Refinement' is enabled. Higher values can catch delayed sacrifices but may also attribute opponent mistakes to brilliance.")
        form_layout.addRow(create_label("Material Sacrifice Lookahead:"), create_input_widget(self.lookahead_plies_spinbox))
        
        group.setLayout(form_layout)
        return group
    
    def _apply_styling(self) -> None:
        """Apply styling from config."""
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('classification_settings', {})
        groups_config = dialog_config.get('groups', {})
        fields_config = dialog_config.get('fields', {})
        buttons_config = dialog_config.get('buttons', {})
        
        # Dialog background
        bg_color = groups_config.get('background_color', [40, 40, 45])
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(bg_color[0], bg_color[1], bg_color[2]))
        self.setPalette(palette)
        
        # Group boxes
        border_color = groups_config.get('border_color', [60, 60, 65])
        border_radius = groups_config.get('border_radius', 5)
        title_color = groups_config.get('title_color', [240, 240, 240])
        title_font_family = resolve_font_family(groups_config.get('title_font_family', 'Helvetica Neue'))
        title_font_size = scale_font_size(groups_config.get('title_font_size', 11))
        margin_top = groups_config.get('margin_top', 10)
        padding_top = groups_config.get('padding_top', 10)
        title_left = groups_config.get('title_left', 10)
        title_padding = groups_config.get('title_padding', [0, 5])
        
        group_style = (
            f"QGroupBox {{"
            f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
            f"border-radius: {border_radius}px;"
            f"margin-top: {margin_top}px;"
            f"padding-top: {padding_top}px;"
            f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
            f"}}"
            f"QGroupBox::title {{"
            f"font-family: \"{title_font_family}\";"
            f"font-size: {title_font_size}pt;"
            f"color: rgb({title_color[0]}, {title_color[1]}, {title_color[2]});"
            f"subcontrol-origin: margin;"
            f"left: {title_left}px;"
            f"padding: {title_padding[0]} {title_padding[1]}px;"
            f"}}"
        )
        
        for group in self.findChildren(QGroupBox):
            group.setStyleSheet(group_style)
        
        # Labels
        text_color = fields_config.get('text_color', [220, 220, 220])
        font_size = scale_font_size(fields_config.get('font_size', 10))
        
        label_style = (
            f"QLabel {{"
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"font-size: {font_size}pt;"
            f"}}"
        )
        
        for label in self.findChildren(QLabel):
            if not isinstance(label.parent(), QGroupBox) or label.text() in ["Move Quality Thresholds", "Brilliant Move Criteria"]:
                continue
            label.setStyleSheet(label_style)
        
        # Spin boxes (numeric inputs)
        # Hide the up/down buttons - users can type values directly
        disabled_bg_color = fields_config.get('disabled_background_color', [35, 35, 40])
        input_border_radius = fields_config.get('input_border_radius', 3)
        input_padding = fields_config.get('input_padding', 3)
        input_background_offset = fields_config.get('input_background_offset', 10)
        
        input_style = (
            f"QSpinBox {{"
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"font-size: {font_size}pt;"
            f"background-color: rgb({bg_color[0] + input_background_offset}, {bg_color[1] + input_background_offset}, {bg_color[2] + input_background_offset});"
            f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
            f"border-radius: {input_border_radius}px;"
            f"padding: {input_padding}px;"
            f"}}"
            f"QSpinBox::up-button, QSpinBox::down-button {{"
            f"width: 0px;"
            f"}}"
            f"QSpinBox:disabled {{"
            f"background-color: rgb({disabled_bg_color[0]}, {disabled_bg_color[1]}, {disabled_bg_color[2]});"
            f"color: rgb({text_color[0] // 2 + 64}, {text_color[1] // 2 + 64}, {text_color[2] // 2 + 64});"
            f"}}"
        )
        
        for spinbox in self.findChildren(QSpinBox):
            spinbox.setStyleSheet(input_style)
        
        # Store disabled background color for max_eval_before_spinbox updates
        self._disabled_bg_color = disabled_bg_color
        self._enabled_bg_color = [bg_color[0] + input_background_offset, bg_color[1] + input_background_offset, bg_color[2] + input_background_offset]
        self._text_color = text_color
        self._border_color = border_color
        
        # Apply initial styling to max_eval_before_spinbox based on enabled state
        if hasattr(self, 'max_eval_before_spinbox') and hasattr(self, 'exclude_winning_check'):
            self._on_exclude_winning_toggled(self.exclude_winning_check.isChecked())
        
        # Check boxes
        checkboxes_config = dialog_config.get('checkboxes', {})
        checkbox_spacing = checkboxes_config.get('spacing', 5)
        indicator_config = checkboxes_config.get('indicator', {})
        checkbox_indicator_width = indicator_config.get('width', 16)
        checkbox_indicator_height = indicator_config.get('height', 16)
        checkbox_indicator_border_radius = indicator_config.get('border_radius', 3)
        checked_config = checkboxes_config.get('checked', {})
        checkbox_checked_bg_color = checked_config.get('background_color', [70, 90, 130])
        checkbox_checked_border_color = checked_config.get('border_color', [100, 120, 160])
        checkbox_hover_border_offset = checkboxes_config.get('hover_border_offset', 20)
        
        # Get checkmark icon path
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent
        checkmark_path = project_root / "app" / "resources" / "icons" / "checkmark.svg"
        checkmark_url = str(checkmark_path).replace("\\", "/") if checkmark_path.exists() else ""
        
        # Use input border and background colors for checkbox indicator
        input_border_color = border_color
        input_bg_color = [bg_color[0] + input_background_offset, bg_color[1] + input_background_offset, bg_color[2] + input_background_offset]
        
        checkbox_style = (
            f"QCheckBox {{"
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"font-size: {font_size}pt;"
            f"spacing: {checkbox_spacing}px;"
            f"}}"
            f"QCheckBox::indicator {{"
            f"width: {checkbox_indicator_width}px;"
            f"height: {checkbox_indicator_height}px;"
            f"border-radius: {checkbox_indicator_border_radius}px;"
            f"border: 1px solid rgb({input_border_color[0]}, {input_border_color[1]}, {input_border_color[2]});"
            f"background-color: rgb({input_bg_color[0]}, {input_bg_color[1]}, {input_bg_color[2]});"
            f"}}"
            f"QCheckBox::indicator:checked {{"
            f"background-color: rgb({checkbox_checked_bg_color[0]}, {checkbox_checked_bg_color[1]}, {checkbox_checked_bg_color[2]});"
            f"border-color: rgb({checkbox_checked_border_color[0]}, {checkbox_checked_border_color[1]}, {checkbox_checked_border_color[2]});"
            f"image: url({checkmark_url});"
            f"}}"
            f"QCheckBox::indicator:hover {{"
            f"border-color: rgb({input_border_color[0] + checkbox_hover_border_offset}, {input_border_color[1] + checkbox_hover_border_offset}, {input_border_color[2] + checkbox_hover_border_offset});"
            f"}}"
        )
        
        for checkbox in self.findChildren(QCheckBox):
            checkbox.setStyleSheet(checkbox_style)
        
        # Buttons
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        button_border_radius = buttons_config.get('border_radius', 3)
        button_padding = buttons_config.get('padding', 5)
        button_bg_offset = buttons_config.get('background_offset', 20)
        button_hover_offset = buttons_config.get('hover_background_offset', 30)
        button_pressed_offset = buttons_config.get('pressed_background_offset', 10)
        
        button_style = (
            f"QPushButton {{"
            f"min-width: {button_width}px;"
            f"min-height: {button_height}px;"
            f"background-color: rgb({bg_color[0] + button_bg_offset}, {bg_color[1] + button_bg_offset}, {bg_color[2] + button_bg_offset});"
            f"border: 1px solid rgb({border_color[0]}, {border_color[1]}, {border_color[2]});"
            f"border-radius: {button_border_radius}px;"
            f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
            f"font-size: {font_size}pt;"
            f"padding: {button_padding}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"background-color: rgb({bg_color[0] + button_hover_offset}, {bg_color[1] + button_hover_offset}, {bg_color[2] + button_hover_offset});"
            f"}}"
            f"QPushButton:pressed {{"
            f"background-color: rgb({bg_color[0] + button_pressed_offset}, {bg_color[1] + button_pressed_offset}, {bg_color[2] + button_pressed_offset});"
            f"}}"
        )
        
        for button in self.findChildren(QPushButton):
            button.setStyleSheet(button_style)
    
    def _validate_thresholds(self) -> Tuple[bool, str]:
        """Validate that CPL thresholds are in order.
        
        Returns:
            Tuple of (is_valid, error_message).
        """
        thresholds = self._get_threshold_values()
        good = thresholds["good_move_max_cpl"]
        inaccuracy = thresholds["inaccuracy_max_cpl"]
        mistake = thresholds["mistake_max_cpl"]
        
        if not (good <= inaccuracy <= mistake):
            return False, "CPL thresholds must be in order: Good ≤ Inaccuracy ≤ Mistake"
        
        return True, ""
    
    def _reset_to_defaults(self) -> None:
        """Reset all settings to defaults from config."""
        # Get progress service for status updates
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        # Show progress and set status
        progress_service.show_progress()
        progress_service.set_status("Resetting classification settings to defaults...")
        QApplication.processEvents()  # Process events to show the status
        
        # Reset via controller
        if not self.classification_controller.reset_to_defaults():
            progress_service.hide_progress()
            progress_service.set_status("Failed to reset settings")
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Reset Failed",
                "Failed to reset settings. Please check file permissions.",
                self
            )
            return
        
        # Update UI with default values from model
        classification_model = self.classification_controller.get_classification_model()
        thresholds = classification_model.get_assessment_thresholds()
        brilliant = classification_model.get_brilliant_criteria()
        
        # Temporarily disconnect signals to avoid triggering auto-adjustment during reset
        self.good_move_spinbox.valueChanged.disconnect()
        self.inaccuracy_spinbox.valueChanged.disconnect()
        self.mistake_spinbox.valueChanged.disconnect()
        
        # Set values
        good_value = thresholds.get("good_move_max_cpl", 50)
        inaccuracy_value = thresholds.get("inaccuracy_max_cpl", 100)
        mistake_value = thresholds.get("mistake_max_cpl", 200)
        
        self.good_move_spinbox.setValue(good_value)
        self.inaccuracy_spinbox.setValue(inaccuracy_value)
        self.mistake_spinbox.setValue(mistake_value)
        
        # Update spinbox ranges after setting values
        self._update_spinbox_ranges()
        
        # Reconnect signals
        self.good_move_spinbox.valueChanged.connect(self._on_good_move_changed)
        self.inaccuracy_spinbox.valueChanged.connect(self._on_inaccuracy_changed)
        self.mistake_spinbox.valueChanged.connect(self._on_mistake_changed)
        
        # Update scale
        self._update_cpl_scale()
        
        self.material_sacrifice_spinbox.setValue(brilliant.get("min_material_sacrifice", 300))
        self.eval_swing_spinbox.setValue(brilliant.get("min_eval_swing", 50))
        self.exclude_winning_check.setChecked(brilliant.get("exclude_already_winning", True))
        self.max_eval_before_spinbox.setValue(brilliant.get("max_eval_before", 500))
        self.lookahead_plies_spinbox.setValue(brilliant.get("material_sacrifice_lookahead_plies", 3))
        # Update enabled state and styling based on checkbox
        self._on_exclude_winning_toggled(self.exclude_winning_check.isChecked())
        
        # Hide progress bar and set final status
        progress_service.hide_progress()
        progress_service.set_status("Classification settings reset to defaults")
        QApplication.processEvents()  # Process events to update status
    
    def _on_exclude_winning_toggled(self, checked: bool) -> None:
        """Handle exclude winning checkbox toggle."""
        self.max_eval_before_spinbox.setEnabled(checked)
        # Update styling to show disabled state
        if hasattr(self, '_disabled_bg_color') and hasattr(self, '_enabled_bg_color'):
            if checked:
                bg_color = self._enabled_bg_color
                text_color = self._text_color
            else:
                bg_color = self._disabled_bg_color
                text_color = [self._text_color[0] // 2 + 64, self._text_color[1] // 2 + 64, self._text_color[2] // 2 + 64]
            
            # Get scaled font size for disabled style
            fields_config = self.config.get('ui', {}).get('dialogs', {}).get('classification_settings', {}).get('fields', {})
            disabled_font_size = scale_font_size(fields_config.get('font_size', 10))
            disabled_style = (
                f"QSpinBox {{"
                f"color: rgb({text_color[0]}, {text_color[1]}, {text_color[2]});"
                f"font-size: {disabled_font_size}pt;"
                f"background-color: rgb({bg_color[0]}, {bg_color[1]}, {bg_color[2]});"
                f"border: 1px solid rgb({self._border_color[0]}, {self._border_color[1]}, {self._border_color[2]});"
                f"border-radius: 3px;"
                f"padding: 3px;"
                f"}}"
                f"QSpinBox::up-button, QSpinBox::down-button {{"
                f"width: 0px;"
                f"}}"
            )
            self.max_eval_before_spinbox.setStyleSheet(disabled_style)
    
    def _on_save(self) -> None:
        """Handle save button click."""
        # Validate thresholds
        is_valid, error_msg = self._validate_thresholds()
        if not is_valid:
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Invalid Settings",
                error_msg,
                self
            )
            return
        
        # Get progress service for status updates
        from app.services.progress_service import ProgressService
        progress_service = ProgressService.get_instance()
        
        # Show progress and set status
        progress_service.show_progress()
        progress_service.set_status("Saving classification settings...")
        QApplication.processEvents()  # Process events to show the status
        
        # Collect values from UI
        thresholds = self._get_threshold_values()
        
        brilliant = {
                "min_material_sacrifice": self.material_sacrifice_spinbox.value(),
                "min_eval_swing": self.eval_swing_spinbox.value(),
                "max_eval_before": self.max_eval_before_spinbox.value(),
                "exclude_already_winning": self.exclude_winning_check.isChecked(),
                "material_sacrifice_lookahead_plies": self.lookahead_plies_spinbox.value()
        }
        
        # Save via controller
        if not self.classification_controller.update_all_settings(thresholds, brilliant):
            progress_service.hide_progress()
            progress_service.set_status("Failed to save settings")
            from app.views.message_dialog import MessageDialog
            MessageDialog.show_warning(
                self.config,
                "Save Failed",
                "Failed to save settings. Please check file permissions.",
                self
            )
            return
        
        # Hide progress bar and set final status
        progress_service.hide_progress()
        progress_service.set_status("Classification settings saved")
        QApplication.processEvents()  # Process events to update status
        
        self.accept()

