"""Bulk analysis dialog for analyzing multiple games."""

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QCheckBox,
    QGroupBox,
    QProgressBar,
    QSizePolicy,
    QApplication,
    QSpinBox,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPalette, QColor, QShowEvent, QResizeEvent
from typing import Dict, Any, Optional, List
from pathlib import Path
import os

from app.models.database_model import DatabaseModel, GameData


class BulkAnalysisDialog(QDialog):
    """Dialog for bulk game analysis."""
    
    def __init__(self, config: Dict[str, Any], database_model: Optional[DatabaseModel],
                 bulk_analysis_controller, database_panel=None, parent=None) -> None:
        """Initialize the bulk analysis dialog.
        
        Args:
            config: Configuration dictionary.
            database_model: DatabaseModel instance for the active database.
            bulk_analysis_controller: BulkAnalysisController instance.
            database_panel: Optional DatabasePanel instance for getting selected games.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config = config
        self.database_model = database_model
        self.controller = bulk_analysis_controller
        self.database_panel = database_panel
        
        # Set database panel in controller
        if database_panel:
            self.controller.set_database_panel(database_panel)
        self.selected_games: List[GameData] = []
        
        # Connect to controller signals
        self.controller.progress_updated.connect(self._on_progress_updated)
        self.controller.status_update_requested.connect(self._on_status_update_requested)
        self.controller.game_analyzed.connect(self._on_game_analyzed)
        self.controller.finished.connect(self._on_analysis_finished)
        
        # Store fixed size
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {})
        width = dialog_config.get('width', 550)
        height = dialog_config.get('height', 400)
        self._fixed_size = QSize(width, height)
        
        # Set fixed size
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
        self._setup_ui()
        self._apply_styling()
        self.setWindowTitle("Bulk Analyze Database")
        self.setModal(True)
    
    def showEvent(self, event: QShowEvent) -> None:
        """Handle show event to enforce fixed size."""
        super().showEvent(event)
        self.setFixedSize(self._fixed_size)
        self.setMinimumSize(self._fixed_size)
        self.setMaximumSize(self._fixed_size)
    
    def sizeHint(self) -> QSize:
        """Return the fixed size as the size hint."""
        return self._fixed_size
    
    def minimumSizeHint(self) -> QSize:
        """Return the fixed size as the minimum size hint."""
        return self._fixed_size
    
    def resizeEvent(self, event: QResizeEvent) -> None:
        """Handle resize event to prevent resizing."""
        super().resizeEvent(event)
        if event.size() != self._fixed_size:
            self.blockSignals(True)
            current_pos = self.pos()
            self.setGeometry(current_pos.x(), current_pos.y(), self._fixed_size.width(), self._fixed_size.height())
            self.setFixedSize(self._fixed_size)
            self.setMinimumSize(self._fixed_size)
            self.setMaximumSize(self._fixed_size)
            self.blockSignals(False)
    
    def _setup_ui(self) -> None:
        """Setup the dialog UI."""
        from app.utils.font_utils import scale_font_size
        
        dialog_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {})
        layout_config = dialog_config.get('layout', {})
        layout_spacing = layout_config.get('spacing', 15)
        layout_margins = layout_config.get('margins', [25, 25, 25, 25])
        spacing_config = dialog_config.get('spacing', {})
        section_spacing = spacing_config.get('section', 15)
        
        layout = QVBoxLayout(self)
        # Set spacing to 0 to disable automatic spacing - we'll use explicit spacing instead
        layout.setSpacing(0)
        layout.setContentsMargins(layout_margins[0], layout_margins[1], layout_margins[2], layout_margins[3])
        
        # Game selection group
        selection_group = QGroupBox("Game Selection")
        selection_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        selection_layout = QVBoxLayout(selection_group)
        groups_config = dialog_config.get('groups', {})
        group_margins = groups_config.get('content_margins', [10, 20, 10, 15])
        selection_layout.setContentsMargins(group_margins[0], group_margins[1], group_margins[2], group_margins[3])
        selection_layout.setSpacing(section_spacing)
        
        # Radio buttons for selection
        self.selection_button_group = QButtonGroup()
        self.selected_games_radio = QRadioButton("Selected games only")
        self.all_games_radio = QRadioButton("All games")
        
        # Ensure radio buttons have proper size policy to prevent truncation
        self.selected_games_radio.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        self.all_games_radio.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed)
        
        self.selection_button_group.addButton(self.selected_games_radio, 0)
        self.selection_button_group.addButton(self.all_games_radio, 1)
        
        # Default to selected games if any are selected, otherwise all games
        if self.controller.has_selected_games(self.database_model):
            self.selected_games_radio.setChecked(True)
            self._update_selected_games()
        else:
            self.all_games_radio.setChecked(True)
        
        self.selected_games_radio.toggled.connect(self._on_selection_changed)
        self.all_games_radio.toggled.connect(self._on_selection_changed)
        
        # Radio buttons in a vertical layout
        selection_layout.addWidget(self.selected_games_radio)
        selection_layout.addWidget(self.all_games_radio)
        
        layout.addWidget(selection_group)
        
        layout.addSpacing(section_spacing)
        
        # Options group
        options_group = QGroupBox("Options")
        options_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(group_margins[0], group_margins[1], group_margins[2], group_margins[3])
        options_layout.setSpacing(section_spacing)
        
        # Re-analyze checkbox row
        self.re_analyze_checkbox = QCheckBox("Re-analyze already analyzed games")
        self.re_analyze_checkbox.setChecked(False)
        self.re_analyze_checkbox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        options_layout.addWidget(self.re_analyze_checkbox)
        
        # Controls row: parallel games and max_threads on same row
        controls_row_layout = QHBoxLayout()
        controls_row_layout.setSpacing(spacing_config.get('controls_row', 20))
        
        # Parallel games input
        parallel_games_row_layout = QHBoxLayout()
        parallel_games_row_layout.setSpacing(spacing_config.get('label_spinbox', 8))
        
        # Get parallel games config
        parallel_games_config = dialog_config.get('parallel_games_spinbox', {})
        parallel_games_min = parallel_games_config.get('min_value', 1)
        parallel_games_max = parallel_games_config.get('max_value', 16)
        threading_config = dialog_config.get('threading', {})
        parallel_games_default = threading_config.get('default_parallel_games', 4)
        parallel_games_step = parallel_games_config.get('single_step', 1)
        parallel_games_suffix = parallel_games_config.get('suffix', '')
        
        # Store original max for "all games" mode
        self._parallel_games_max_all = parallel_games_max
        
        # Parallel games label (set fixed width to align with move time)
        labels_config = dialog_config.get('labels', {})
        parallel_games_label = QLabel("Parallel games:")
        parallel_games_label.setStyleSheet(
            f"font-size: {scale_font_size(labels_config.get('font_size', 11))}pt; "
            f"color: rgb({labels_config.get('text_color', [200, 200, 200])[0]}, "
            f"{labels_config.get('text_color', [200, 200, 200])[1]}, "
            f"{labels_config.get('text_color', [200, 200, 200])[2]});"
        )
        # Set fixed width to match "Move Time (ply):" label for vertical alignment
        label_fixed_width = labels_config.get('fixed_width', 110)
        parallel_games_label.setFixedWidth(label_fixed_width)
        parallel_games_row_layout.addWidget(parallel_games_label)
        
        # Parallel games spinbox
        self.parallel_games_spinbox = QSpinBox()
        self.parallel_games_spinbox.setMinimum(parallel_games_min)
        self.parallel_games_spinbox.setMaximum(parallel_games_max)
        self.parallel_games_spinbox.setSingleStep(parallel_games_step)
        self.parallel_games_spinbox.setValue(parallel_games_default)
        if parallel_games_suffix:
            self.parallel_games_spinbox.setSuffix(parallel_games_suffix)
        parallel_games_row_layout.addWidget(self.parallel_games_spinbox)
        
        controls_row_layout.addLayout(parallel_games_row_layout, 0)  # Stretch factor 0 to prevent stretching
        
        # Add stretch to push max threads to the right
        controls_row_layout.addStretch()
        
        # Max threads input (on same row as parallel games, aligned to the right)
        max_threads_row_layout = QHBoxLayout()
        max_threads_row_layout.setSpacing(spacing_config.get('label_spinbox', 8))
        
        # Get max threads config
        max_threads_config = dialog_config.get('max_threads_spinbox', {})
        max_threads_min = max_threads_config.get('min_value', 0)
        max_threads_max = max_threads_config.get('max_value', 128)
        max_threads_default = max_threads_config.get('default_value', 0)
        max_threads_step = max_threads_config.get('single_step', 1)
        max_threads_suffix = max_threads_config.get('suffix', '')
        max_threads_special_text = max_threads_config.get('special_value_text', 'Unlimited')
        
        # Use available cores as maximum if not specified or if specified max is too high
        cpu_count_fallback = threading_config.get('cpu_count_fallback', 4)
        available_cores = os.cpu_count() or cpu_count_fallback
        if max_threads_max > available_cores:
            max_threads_max = available_cores
        
        # Max threads label
        max_threads_label = QLabel("Max threads:")
        max_threads_label.setStyleSheet(
            f"font-size: {scale_font_size(labels_config.get('font_size', 11))}pt; "
            f"color: rgb({labels_config.get('text_color', [200, 200, 200])[0]}, "
            f"{labels_config.get('text_color', [200, 200, 200])[1]}, "
            f"{labels_config.get('text_color', [200, 200, 200])[2]});"
        )
        max_threads_row_layout.addWidget(max_threads_label)
        
        # Max threads spinbox
        self.max_threads_spinbox = QSpinBox()
        self.max_threads_spinbox.setMinimum(max_threads_min)
        self.max_threads_spinbox.setMaximum(max_threads_max)
        self.max_threads_spinbox.setSingleStep(max_threads_step)
        self.max_threads_spinbox.setValue(max_threads_default)
        if max_threads_suffix:
            self.max_threads_spinbox.setSuffix(max_threads_suffix)
        if max_threads_special_text and max_threads_min == 0:
            self.max_threads_spinbox.setSpecialValueText(max_threads_special_text)
        max_threads_row_layout.addWidget(self.max_threads_spinbox)
        
        controls_row_layout.addLayout(max_threads_row_layout, 0)  # Stretch factor 0 to prevent stretching
        
        options_layout.addLayout(controls_row_layout)
        
        # Time per move row (below parallel games and max threads)
        movetime_row_layout = QHBoxLayout()
        movetime_row_layout.setSpacing(spacing_config.get('label_spinbox', 8))
        
        movetime_label = QLabel("Move Time (ply):")
        movetime_label.setStyleSheet(
            f"font-size: {scale_font_size(labels_config.get('font_size', 11))}pt; "
            f"color: rgb({labels_config.get('text_color', [200, 200, 200])[0]}, "
            f"{labels_config.get('text_color', [200, 200, 200])[1]}, "
            f"{labels_config.get('text_color', [200, 200, 200])[2]});"
        )
        # Set same fixed width as parallel games label for vertical alignment
        movetime_label.setFixedWidth(label_fixed_width)
        movetime_row_layout.addWidget(movetime_label)
        
        # Get movetime spinbox config
        movetime_config = dialog_config.get('movetime_spinbox', {})
        movetime_min = movetime_config.get('min_value', 100)
        movetime_max = movetime_config.get('max_value', 60000)
        movetime_step = movetime_config.get('single_step', 100)
        movetime_suffix = movetime_config.get('suffix', ' ms')
        movetime_fallback_default = movetime_config.get('fallback_default', 1000)
        
        # Get default movetime from controller
        default_movetime = self.controller.get_default_movetime(movetime_fallback_default)
        
        self.movetime_spinbox = QSpinBox()
        self.movetime_spinbox.setMinimum(movetime_min)
        self.movetime_spinbox.setMaximum(movetime_max)
        self.movetime_spinbox.setSingleStep(movetime_step)
        self.movetime_spinbox.setValue(default_movetime)
        self.movetime_spinbox.setSuffix(movetime_suffix)
        movetime_row_layout.addWidget(self.movetime_spinbox)
        
        # Set fixed width for all spinboxes (after all are created)
        spinboxes_config = dialog_config.get('spinboxes', {})
        spinbox_fixed_width = spinboxes_config.get('fixed_width', 80)
        self.parallel_games_spinbox.setFixedWidth(spinbox_fixed_width)
        self.max_threads_spinbox.setFixedWidth(spinbox_fixed_width)
        self.movetime_spinbox.setFixedWidth(spinbox_fixed_width)
        
        movetime_row_layout.addStretch()
        
        options_layout.addLayout(movetime_row_layout)
        
        layout.addWidget(options_group)
        
        layout.addSpacing(section_spacing)
        
        # Progress group (always visible)
        self.progress_group = QGroupBox("Progress")
        self.progress_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        progress_layout = QVBoxLayout(self.progress_group)
        progress_layout.setContentsMargins(group_margins[0], group_margins[1], group_margins[2], group_margins[3])
        progress_layout.setSpacing(section_spacing)
        
        # Get progress config first
        progress_config = dialog_config.get('progress', {})
        status_font_size = progress_config.get('status_font_size', 10)
        status_text_color = progress_config.get('status_text_color', [150, 150, 150])
        
        # Progress bar with percentage label
        progress_bar_layout = QHBoxLayout()
        progress_bar_layout.setSpacing(spacing_config.get('progress_bar', 8))
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)  # Hide text inside progress bar since we have a label
        progress_bar_layout.addWidget(self.progress_bar)
        
        # Percentage label
        progress_display_config = dialog_config.get('progress_display', {})
        decimal_precision = progress_display_config.get('decimal_precision', 4)
        percent_label_min_width = progress_display_config.get('percent_label_min_width', 80)
        initial_progress_str = f"0.{'0' * decimal_precision}%"
        self.progress_percent_label = QLabel(initial_progress_str)
        self.progress_percent_label.setStyleSheet(
            f"font-size: {status_font_size}pt; "
            f"color: rgb({status_text_color[0]}, {status_text_color[1]}, {status_text_color[2]});"
        )
        self.progress_percent_label.setMinimumWidth(percent_label_min_width)
        progress_bar_layout.addWidget(self.progress_percent_label)
        
        progress_layout.addLayout(progress_bar_layout)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet(
            f"font-size: {status_font_size}pt; "
            f"color: rgb({status_text_color[0]}, {status_text_color[1]}, {status_text_color[2]});"
        )
        progress_layout.addWidget(self.status_label)
        
        layout.addWidget(self.progress_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        buttons_config = dialog_config.get('buttons', {})
        button_spacing = buttons_config.get('spacing', 10)
        button_layout.setSpacing(button_spacing)
        button_layout.addStretch()
        
        self.start_button = QPushButton("Start Analysis")
        self.start_button.clicked.connect(self._start_analysis)
        button_layout.addWidget(self.start_button)
        
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self._on_cancel)
        button_layout.addWidget(self.cancel_button)
        
        # Add spacing before buttons
        layout.addSpacing(section_spacing)
        layout.addLayout(button_layout)
        
        # Initialize parallel games limit based on current selection
        self._update_parallel_games_limit()
    
    def _on_selection_changed(self) -> None:
        """Handle selection radio button change."""
        if self.selected_games_radio.isChecked():
            self._update_selected_games()
            # Disable start button if no games selected
            if not self.selected_games:
                self.start_button.setEnabled(False)
            else:
                self.start_button.setEnabled(True)
            # Update parallel games max limit
            self._update_parallel_games_limit()
        else:
            self.start_button.setEnabled(True)
            # Reset parallel games max to config value
            self._update_parallel_games_limit()
    
    def _update_selected_games(self) -> None:
        """Update the list of selected games."""
        if self.database_model:
            self.selected_games = self.controller.get_selected_games(self.database_model)
            # Update parallel games limit if in selected games mode
            if self.selected_games_radio.isChecked():
                self._update_parallel_games_limit()
    
    def _update_parallel_games_limit(self) -> None:
        """Update the maximum value of the parallel games spinbox based on selection mode."""
        # Check if spinbox exists (may be called during initialization)
        if not hasattr(self, 'parallel_games_spinbox'):
            return
        
        if self.selected_games_radio.isChecked():
            # Limit to number of selected games (but not less than minimum)
            num_selected = len(self.selected_games)
            current_min = self.parallel_games_spinbox.minimum()
            new_max = max(current_min, num_selected)
            self.parallel_games_spinbox.setMaximum(new_max)
            # If current value exceeds new max, adjust it
            if self.parallel_games_spinbox.value() > new_max:
                self.parallel_games_spinbox.setValue(new_max)
        else:
            # Use config max value for "all games" mode
            self.parallel_games_spinbox.setMaximum(self._parallel_games_max_all)
    
    def _start_analysis(self) -> None:
        """Start the bulk analysis."""
        # Validate engine using controller
        is_valid, error_title, error_message = self.controller.validate_engine_for_analysis()
        if not is_valid:
            from app.views.message_dialog import MessageDialog
            dialog = MessageDialog(
                self.config,
                error_title,
                error_message,
                message_type="warning",
                parent=self
            )
            dialog.exec()
            return
        
        # Get games to analyze using controller
        selection_mode = "selected" if self.selected_games_radio.isChecked() else "all"
        games_to_analyze, error_title, error_message = self.controller.get_games_to_analyze(
            selection_mode,
            self.database_model,
            self.selected_games
        )
        
        if games_to_analyze is None:
            from app.views.message_dialog import MessageDialog
            message_type = "warning" if error_title == "No Games Selected" else "information"
            dialog = MessageDialog(
                self.config,
                error_title,
                error_message,
                message_type=message_type,
                parent=self
            )
            dialog.exec()
            return
        
        # Update progress group (always visible)
        progress_display_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {}).get('progress_display', {})
        decimal_precision = progress_display_config.get('decimal_precision', 4)
        initial_progress_str = f"0.{'0' * decimal_precision}%"
        self.progress_bar.setValue(0)
        self.progress_percent_label.setText(initial_progress_str)
        self.status_label.setText(f"Preparing to analyze {len(games_to_analyze)} games...")
        
        # Disable controls
        self.selected_games_radio.setEnabled(False)
        self.all_games_radio.setEnabled(False)
        self.re_analyze_checkbox.setEnabled(False)
        self.movetime_spinbox.setEnabled(False)
        self.parallel_games_spinbox.setEnabled(False)
        self.max_threads_spinbox.setEnabled(False)
        self.start_button.setEnabled(False)
        self.cancel_button.setText("Cancel")
        
        # Prepare services using controller (with status updates)
        def status_callback(message: str) -> None:
            self.status_label.setText(message)
            QApplication.processEvents()  # Allow UI to update
        
        self.controller.prepare_services_for_analysis(status_callback)
        
        # Get analysis parameters from UI
        re_analyze = self.re_analyze_checkbox.isChecked()
        movetime_override = self.movetime_spinbox.value()  # Get value from spinbox
        
        # Get max_threads_override (0 means unlimited, convert to None)
        max_threads_value = self.max_threads_spinbox.value()
        max_threads_override = None if max_threads_value == 0 else max_threads_value
        
        # Get parallel_games_override (use value from spinbox)
        parallel_games_override = self.parallel_games_spinbox.value()
        
        # Show progress service in status bar through controller
        self.controller.show_progress()
        self.controller.set_progress_value(0)
        
        # Start analysis via controller
        self.controller.start_analysis(
            games_to_analyze,
            re_analyze=re_analyze,
            movetime_override=movetime_override,
            max_threads_override=max_threads_override,
            parallel_games_override=parallel_games_override
        )
    
    def _on_progress_updated(self, progress_percent: float, status_message: str, progress_percent_str: str) -> None:
        """Handle progress update from analysis thread."""
        # QProgressBar uses int, but we display the float value in the label next to it
        self.progress_bar.setValue(int(progress_percent))
        self.progress_percent_label.setText(progress_percent_str)
        self.status_label.setText(status_message)
        QApplication.processEvents()
    
    def _on_status_update_requested(self) -> None:
        """Handle status update request from analysis thread (called from main thread)."""
        # Check if cancelled and update status accordingly
        if self.controller.is_cancelled():
            # Show "Cancelling..." only if thread is still running
            # Once thread finishes, _on_analysis_finished will show "Cancelled by user"
            if self.controller.is_thread_running():
                self.controller.set_progress_status("Bulk Analysis: Cancelling...")
                self.status_label.setText("Cancelling...")
            else:
                self.controller.set_progress_status("Bulk Analysis: Cancelled by user")
                self.status_label.setText("Cancelled by user")
        else:
            self.controller.update_status()
    
    def _on_game_analyzed(self, game: GameData) -> None:
        """Handle game analyzed signal."""
        # Update database model through controller
        self.controller.update_game_in_database(game, self.database_model)
        QApplication.processEvents()
    
    def _on_analysis_finished(self, success: bool, message: str) -> None:
        """Handle analysis finished signal."""
        if success:
            progress_display_config = self.config.get('ui', {}).get('dialogs', {}).get('bulk_analysis_dialog', {}).get('progress_display', {})
            decimal_precision = progress_display_config.get('decimal_precision', 4)
            final_progress_str = f"100.{'0' * decimal_precision}%"
            self.progress_bar.setValue(100)
            self.progress_percent_label.setText(final_progress_str)
            self.status_label.setText(message)
            # Update status bar through controller
            self.controller.set_progress_status(f"Bulk Analysis: {message}")
            self.cancel_button.setText("Close")
            self.cancel_button.clicked.disconnect()
            self.cancel_button.clicked.connect(self.accept)
        else:
            # Check if this is a cancellation
            if "cancelled" in message.lower():
                status_message = "Bulk Analysis: Cancelled by user"
                self.status_label.setText("Cancelled by user")
            else:
                status_message = f"Bulk Analysis: Error - {message}"
                self.status_label.setText(f"Error: {message}")
            
            # Update status bar through controller - ALWAYS set status BEFORE hiding progress
            # This ensures the status is visible even if this is called after _on_cancel
            self.controller.set_progress_status(status_message)
            QApplication.processEvents()  # Ensure status bar updates
            
            # Re-enable controls for retry
            self.selected_games_radio.setEnabled(True)
            self.all_games_radio.setEnabled(True)
            self.re_analyze_checkbox.setEnabled(True)
            self.movetime_spinbox.setEnabled(True)
            self.parallel_games_spinbox.setEnabled(True)
            self.max_threads_spinbox.setEnabled(True)
            self.start_button.setEnabled(True)
            self.cancel_button.setText("Cancel")
        
        # Hide progress service at the end (after status is set and processed)
        self.controller.hide_progress()
    
    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        if self.controller.is_analysis_running():
            self.controller.cancel_analysis()
            self.status_label.setText("Cancelling...")
            self.cancel_button.setEnabled(False)
            
            # Update status bar immediately through controller
            self.controller.set_progress_status("Bulk Analysis: Cancelling...")
            QApplication.processEvents()  # Ensure UI updates
            
            # Wait for thread to finish
            self.controller.wait_for_analysis()
            
            # Ensure status bar is updated with cancellation message through controller
            # Set status BEFORE hiding progress to ensure it's visible
            self.controller.set_progress_status("Bulk Analysis: Cancelled by user")
            self.status_label.setText("Cancelled by user")
            QApplication.processEvents()  # Ensure UI updates
            
            # Hide progress service AFTER setting status
            self.controller.hide_progress()
        else:
            # Thread not running, just hide progress
            self.controller.hide_progress()
        
        self.reject()
    
    def _apply_styling(self) -> None:
        """Apply styling to UI elements based on configuration."""
        ui_config = self.config.get('ui', {})
        dialog_config = ui_config.get('dialogs', {}).get('bulk_analysis_dialog', {})
        
        # Dialog background color
        bg_color = dialog_config.get('background_color', [40, 40, 45])
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), QColor(bg_color[0], bg_color[1], bg_color[2]))
        palette.setColor(QPalette.ColorRole.Window, QColor(bg_color[0], bg_color[1], bg_color[2]))
        self.setPalette(palette)
        
        # Labels styling
        labels_config = dialog_config.get('labels', {})
        from app.utils.font_utils import resolve_font_family, scale_font_size
        label_font_family = resolve_font_family(labels_config.get('font_family', 'Helvetica Neue'))
        label_font_size = scale_font_size(labels_config.get('font_size', 11))
        label_text_color = labels_config.get('text_color', [200, 200, 200])
        
        label_style = (
            f"QLabel {{"
            f"font-family: {label_font_family}; "
            f"font-size: {label_font_size}pt; "
            f"color: rgb({label_text_color[0]}, {label_text_color[1]}, {label_text_color[2]});"
            f"margin: 0px;"
            f"padding: 0px;"
            f"}}"
        )
        
        for label in self.findChildren(QLabel):
            label.setStyleSheet(label_style)
        
        # Group box styling - use StyleManager
        groups_config = dialog_config.get('groups', {})
        group_border_color = groups_config.get('border_color', [60, 60, 65])
        group_border_width = groups_config.get('border_width', 1)
        group_border_radius = groups_config.get('border_radius', 5)
        group_bg_color = groups_config.get('background_color')  # None = use unified default
        group_title_color = groups_config.get('title_color', [240, 240, 240])
        group_title_font_family_raw = groups_config.get('title_font_family', 'Helvetica Neue')
        from app.utils.font_utils import resolve_font_family, scale_font_size
        from app.views.style import StyleManager
        group_title_font_family = resolve_font_family(group_title_font_family_raw)
        group_title_font_size = scale_font_size(groups_config.get('title_font_size', 11))
        group_margin_top = groups_config.get('margin_top', 10)
        group_padding_top = groups_config.get('padding_top', 5)
        group_title_left = groups_config.get('title_left', 10)
        group_title_padding = groups_config.get('title_padding', [0, 5])
        
        group_boxes = list(self.findChildren(QGroupBox))
        if group_boxes:
            StyleManager.style_group_boxes(
                group_boxes,
                self.config,
                border_color=group_border_color,
                border_width=group_border_width,
                border_radius=group_border_radius,
                bg_color=group_bg_color,
                margin_top=group_margin_top,
                padding_top=group_padding_top,
                title_font_family=group_title_font_family,
                title_font_size=group_title_font_size,
                title_color=group_title_color,
                title_left=group_title_left,
                title_padding=group_title_padding
            )
        
        # Apply checkbox styling using StyleManager
        from app.views.style import StyleManager
        
        # Get checkmark icon path
        project_root = Path(__file__).parent.parent.parent
        checkmark_path = project_root / "app" / "resources" / "icons" / "checkmark.svg"
        
        # Use input border and background colors for checkbox indicator
        input_border_color = dialog_config.get('border_color', [60, 60, 65])
        input_bg_color = [bg_color[0] + 5, bg_color[1] + 5, bg_color[2] + 5]
        
        # Get all checkboxes and apply styling
        checkboxes = self.findChildren(QCheckBox)
        StyleManager.style_checkboxes(
            checkboxes,
            self.config,
            label_text_color,
            label_font_family,
            label_font_size,
            input_bg_color,
            input_border_color,
            checkmark_path
        )
        
        # Apply radio button styling using StyleManager (uses unified config)
        from app.views.style import StyleManager
        radio_buttons = list(self.findChildren(QRadioButton))
        if radio_buttons:
            StyleManager.style_radio_buttons(radio_buttons, self.config)
        
        # SpinBox styling (use input widget colors) - use StyleManager
        input_bg_color = dialog_config.get('background_color', [40, 40, 45])
        input_border = dialog_config.get('border_color', [60, 60, 65])
        input_text_color = dialog_config.get('text_color', [200, 200, 200])
        
        # Calculate background color with offset
        spinbox_bg_color = [
            min(255, input_bg_color[0] + 5),
            min(255, input_bg_color[1] + 5),
            min(255, input_bg_color[2] + 5)
        ]
        
        # Calculate focus border color with offset
        spinbox_focus_border_color = [
            min(255, input_border[0] + 20),
            min(255, input_border[1] + 20),
            min(255, input_border[2] + 20)
        ]
        
        # Apply unified spinbox styling using StyleManager
        spinboxes = list(self.findChildren(QSpinBox))
        if spinboxes:
            StyleManager.style_spinboxes(
                spinboxes,
                self.config,
                text_color=input_text_color,
                font_family=label_font_family,
                font_size=label_font_size,
                bg_color=spinbox_bg_color,
                border_color=input_border,
                focus_border_color=spinbox_focus_border_color,
                border_width=1,
                border_radius=3,
                padding=[6, 4]  # [horizontal, vertical]
            )
        
        # Apply button styling using StyleManager (uses unified config)
        buttons_config = dialog_config.get('buttons', {})
        button_width = buttons_config.get('width', 120)
        button_height = buttons_config.get('height', 30)
        border_color = dialog_config.get('border_color', [60, 60, 65])
        bg_color_list = [bg_color[0], bg_color[1], bg_color[2]]
        border_color_list = [border_color[0], border_color[1], border_color[2]]
        
        from app.views.style import StyleManager
        all_buttons = self.findChildren(QPushButton)
        StyleManager.style_buttons(
            all_buttons,
            self.config,
            bg_color_list,
            border_color_list,
            min_width=button_width,
            min_height=button_height
        )
        
        # Progress bar styling (use dedicated progress bar config)
        progress_bar_config = dialog_config.get('progress_bar', {})
        progress_bg_color = progress_bar_config.get('background_color', [30, 30, 35])
        progress_border_color = progress_bar_config.get('border_color', [60, 60, 65])
        progress_border_radius = progress_bar_config.get('border_radius', 3)
        progress_chunk_bg_color = progress_bar_config.get('chunk_background_color', [70, 90, 130])
        progress_chunk_border_radius = progress_bar_config.get('chunk_border_radius', 2)
        
        progress_bar_style = (
            f"QProgressBar {{"
            f"border: 1px solid rgb({progress_border_color[0]}, {progress_border_color[1]}, {progress_border_color[2]});"
            f"border-radius: {progress_border_radius}px;"
            f"text-align: center;"
            f"background-color: rgb({progress_bg_color[0]}, {progress_bg_color[1]}, {progress_bg_color[2]});"
            f"}}"
            f"QProgressBar::chunk {{"
            f"background-color: rgb({progress_chunk_bg_color[0]}, {progress_chunk_bg_color[1]}, {progress_chunk_bg_color[2]});"
            f"border-radius: {progress_chunk_border_radius}px;"
            f"}}"
        )
        
        self.progress_bar.setStyleSheet(progress_bar_style)

