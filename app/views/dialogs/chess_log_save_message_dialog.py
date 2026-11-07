"""Themed message dialog with Save and Cancel (Chess Log's own; MessageDialog only has OK).

Reuses MessageDialog's themed layout and restyles its single button as Save, adding
Cancel.  Closing the window or pressing Esc rejects, exactly like Cancel.
"""

from __future__ import annotations

from typing import Any, Dict

from PyQt6.QtWidgets import QHBoxLayout, QPushButton

from app.views.dialogs.message_dialog import MessageDialog
from app.views.style.style_manager import StyleManager


class SaveCancelMessageDialog(MessageDialog):
    """MessageDialog whose buttons are Cancel and Save; ``exec()`` is Accepted only for Save."""

    SAVE_LABEL = "Save"
    CANCEL_LABEL = "Cancel"

    def __init__(self, config: Dict[str, Any], title: str, message: str, parent=None) -> None:
        super().__init__(config, title, message, "information", parent)
        ok_button = next(b for b in self.findChildren(QPushButton) if b.text() == "OK")
        ok_button.setText(self.SAVE_LABEL)
        self.save_button = ok_button
        self.cancel_button = QPushButton(self.CANCEL_LABEL)
        self.cancel_button.clicked.connect(self.reject)
        button_row = next(
            item.layout() for item in (self.layout().itemAt(i) for i in range(self.layout().count()))
            if isinstance(item.layout(), QHBoxLayout)
        )
        button_row.insertWidget(button_row.indexOf(ok_button), self.cancel_button)

        dialog_config = config.get("ui", {}).get("dialogs", {}).get("message_dialog", {})
        buttons_config = dialog_config.get("buttons", {})
        bg = dialog_config.get("background_color", [40, 40, 45])
        border = buttons_config.get("border_color", [60, 60, 65])
        StyleManager.style_buttons(
            [self.cancel_button, ok_button],
            config,
            [bg[0], bg[1], bg[2]],
            [border[0], border[1], border[2]],
            min_width=buttons_config.get("width", 120),
            min_height=buttons_config.get("height", 30),
        )

    @staticmethod
    def ask(config: Dict[str, Any], title: str, message: str, parent=None) -> bool:
        """Show the dialog; True only when the user clicked Save."""
        from PyQt6.QtWidgets import QDialog
        return SaveCancelMessageDialog(config, title, message, parent).exec() == QDialog.DialogCode.Accepted
