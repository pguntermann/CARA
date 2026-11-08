"""Dialog for Chess Log settings: choose active preset."""

from __future__ import annotations

from typing import Any, Dict

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from app.views.style import StyleManager


_VALID_PRESETS = frozenset({"CLAMP", "CCT", "3x3"})


class ChessLogSettingsDialog(QDialog):
    """Settings dialog for Chess Log: active preset selection.

    Mirrors the AI Model Settings dialog constructor pattern:
    __init__(config, user_settings_service, parent=None).
    """

    _PRESETS = ["3x3", "CLAMP", "CCT"]
    _PRESET_DISPLAY_NAMES = {"3x3": "3x3 Method"}

    def __init__(self, config: Dict[str, Any], user_settings_service, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self._user_settings_service = user_settings_service

        chess_log = user_settings_service.get_chess_log()
        raw_preset = chess_log.get("active_preset", "3x3")
        self._active_preset: str = raw_preset if raw_preset in _VALID_PRESETS else "3x3"

        self._load_config()
        self._setup_ui()
        self._apply_styling()
        self._apply_size()
        self.setWindowTitle("Chess Log Settings")

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        dc = self.config.get("ui", {}).get("dialogs", {}).get("chess_log_settings", {})
        self._dialog_width = dc.get("width", 400)
        self._dialog_bg_rgb = dc.get("background_color", [40, 40, 45])
        self._dialog_border_rgb = dc.get("border_color", [60, 60, 65])
        self._button_width = dc.get("button_width", 100)
        self._button_height = dc.get("button_height", 28)

        try:
            from app.utils.font_utils import resolve_font_family, scale_font_size
            self._label_font = resolve_font_family(dc.get("label_font_family", "Helvetica Neue"))
            self._label_size = int(scale_font_size(dc.get("label_font_size", 11)))
        except Exception:
            self._label_font = "Helvetica Neue"
            self._label_size = 11

        self._label_color = QColor(*dc.get("text_color", [200, 200, 200]))

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        # --- Preset selection ---
        preset_group = QGroupBox("Active Preset")
        preset_group.setFont(QFont(self._label_font, self._label_size))
        preset_layout = QVBoxLayout(preset_group)
        preset_layout.setSpacing(6)

        self._preset_radio_group = QButtonGroup(self)
        self._radio_buttons: Dict[str, QRadioButton] = {}

        preset_descriptions = {
            "CLAMP": "Checks · Loose Pieces · Alignment · Mobility · Pawn Promotion",
            "CCT": "Checks · Captures · Threats",
            "3x3": "Four guided Whys per game moment",
        }

        preset_attributions = {
            "CLAMP": "Developed by Dr. Can Kabadayi",
            "3x3": "Developed by GM Noël Studer",
        }

        dim_color = (
            f"color: rgb({max(0, self._label_color.red()-40)},"
            f"{max(0, self._label_color.green()-40)},"
            f"{max(0, self._label_color.blue()-40)});"
        )
        attr_color = (
            f"color: rgb({max(0, self._label_color.red()-70)},"
            f"{max(0, self._label_color.green()-70)},"
            f"{max(0, self._label_color.blue()-70)}); font-style: italic;"
        )

        for preset in self._PRESETS:
            row = QHBoxLayout()
            rb = QRadioButton(self._PRESET_DISPLAY_NAMES.get(preset, preset))
            rb.setFont(QFont(self._label_font, self._label_size))
            rb.setChecked(preset == self._active_preset)
            self._preset_radio_group.addButton(rb)
            self._radio_buttons[preset] = rb
            row.addWidget(rb)
            desc = QLabel(preset_descriptions[preset])
            desc.setFont(QFont(self._label_font, max(9, self._label_size - 1)))
            desc.setStyleSheet(dim_color)
            row.addWidget(desc)
            row.addStretch(1)
            preset_layout.addLayout(row)
            if preset in preset_attributions:
                attr_row = QHBoxLayout()
                attr_row.addSpacing(20)
                attr_lbl = QLabel(preset_attributions[preset])
                attr_lbl.setFont(QFont(self._label_font, max(8, self._label_size - 2)))
                attr_lbl.setStyleSheet(attr_color)
                attr_row.addWidget(attr_lbl)
                attr_row.addStretch(1)
                preset_layout.addLayout(attr_row)

        root.addWidget(preset_group)

        # OK / Cancel
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setAutoDefault(False)
        self._cancel_btn.clicked.connect(self.reject)
        self._ok_btn = QPushButton("OK")
        self._ok_btn.setDefault(True)
        self._ok_btn.setAutoDefault(True)
        self._ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(self._ok_btn)
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _apply_styling(self) -> None:
        bg = QColor(*self._dialog_bg_rgb)
        palette = self.palette()
        palette.setColor(self.backgroundRole(), bg)
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        StyleManager.style_buttons(
            [self._ok_btn, self._cancel_btn],
            self.config,
            self._dialog_bg_rgb,
            self._dialog_border_rgb,
            min_width=self._button_width,
            min_height=self._button_height,
        )

        label_ss = (
            f"color: rgb({self._label_color.red()},{self._label_color.green()},{self._label_color.blue()});"
        )
        group_ss = (
            f"QGroupBox {{ color: rgb({self._label_color.red()},{self._label_color.green()},{self._label_color.blue()}); "
            f"border: 1px solid rgb({self._dialog_border_rgb[0]},{self._dialog_border_rgb[1]},{self._dialog_border_rgb[2]}); "
            f"border-radius: 4px; margin-top: 8px; padding-top: 8px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 8px; padding: 0 4px; }}"
        )
        for rb in self._radio_buttons.values():
            rb.setStyleSheet(label_ss)
        for w in [self.findChild(QGroupBox)]:
            if w:
                w.setStyleSheet(group_ss)

    def _apply_size(self) -> None:
        self.setMinimumWidth(int(self._dialog_width))

    # ------------------------------------------------------------------
    # Accept
    # ------------------------------------------------------------------

    def _on_ok(self) -> None:
        selected_preset = next(
            (name for name, rb in self._radio_buttons.items() if rb.isChecked()), "3x3"
        )
        self._user_settings_service.update_chess_log_settings({
            "active_preset": selected_preset,
        })
        self._user_settings_service.save()
        self.accept()
