"""Feedback / issue report dialog for Opening Encyclopedia entries."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple
from urllib.parse import quote

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QColor, QFont, QShowEvent
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from app.services.opening_encyclopedia_service import EncyclopediaEntry
from app.utils.external_open import open_url
from app.utils.font_utils import resolve_font_family, scale_font_size
from app.views.dialogs.message_dialog import MessageDialog
from app.views.dialogs.opening_encyclopedia_dialog import (
    build_encyclopedia_tag_chip,
)
from app.views.style import StyleManager

_DEFAULT_CATEGORIES = [
    "Factually wrong content",
    "Image license / attribution issue",
    "Suggest Image (PD/CC0)",
    "Typo / wording",
    "Improvement suggestion",
    "Other",
]

_DELIVERY_MAILTO = "mailto"
_DELIVERY_GMAIL = "gmail"
_DELIVERY_CLIPBOARD = "clipboard"


def _rgb(value: Any, default: List[int]) -> List[int]:
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return [int(value[0]), int(value[1]), int(value[2])]
    return list(default)


_DEFAULT_DELIVERY_ITEMS = [
    {
        "id": _DELIVERY_MAILTO,
        "label": "Use local mail client - mailto:",
        "hint": "Send Report using your local installed E-Mail client",
    },
    {
        "id": _DELIVERY_GMAIL,
        "label": "Open in Google-Mail",
        "hint": "Opens Gmail compose in your browser. Requires a Google account.",
    },
    {
        "id": _DELIVERY_CLIPBOARD,
        "label": "Copy to clipboard",
        "hint": "Copies the report to the clipboard.",
    },
]

_DEFAULT_MSG_DESCRIPTION_TOO_SHORT = (
    "Feedback too short, please describe the issue in more detail"
)
_DEFAULT_MSG_CATEGORY_REQUIRED = "Please select a category"



class OpeningEncyclopediaFeedbackDialog(QDialog):
    """Collect category + free-text feedback and deliver via a chosen method."""

    def __init__(
        self,
        config: Dict[str, Any],
        entry: EncyclopediaEntry,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self._entry = entry

        dialog_config = (
            (config.get("ui") or {})
            .get("dialogs", {})
            .get("opening_encyclopedia_feedback_dialog", {})
        )
        if not isinstance(dialog_config, dict):
            dialog_config = {}
        self._dialog_config = dialog_config

        layout_config = dialog_config.get("layout", {})
        title_config = dialog_config.get("title", {})
        label_config = dialog_config.get("label", {})
        entry_config = dialog_config.get("entry", {})
        category_config = dialog_config.get("category", {})
        description_config = dialog_config.get("description", {})
        delivery_config = dialog_config.get("delivery", {})
        hint_config = dialog_config.get("hint", {})
        buttons_config = dialog_config.get("buttons", {})

        self.setWindowTitle(str(dialog_config.get("window_title", "Report feedback")))
        self.dialog_width = int(dialog_config.get("width", 500))
        self.dialog_minimum_height = int(dialog_config.get("minimum_height", 420))
        self.bottom_button_top_padding = int(
            dialog_config.get("bottom_button_top_padding", 50)
        )
        self._min_description_chars = max(
            1, int(dialog_config.get("min_description_chars", 25))
        )

        bg = _rgb(dialog_config.get("background_color"), [40, 40, 45])
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor(*bg))
        self.setPalette(pal)

        root = QVBoxLayout(self)
        margins = layout_config.get("margins", [25, 25, 25, 25])
        if isinstance(margins, (list, tuple)) and len(margins) >= 4:
            root.setContentsMargins(
                int(margins[0]), int(margins[1]), int(margins[2]), int(margins[3])
            )
        root.setSpacing(int(layout_config.get("spacing", 10)))

        title_color = _rgb(
            title_config.get("text_color"),
            dialog_config.get("text_color", [240, 240, 240]),
        )
        title = QLabel(str(title_config.get("text", "Report feedback")))
        title.setFont(
            QFont(
                resolve_font_family(title_config.get("font_family", "Helvetica Neue")),
                int(scale_font_size(title_config.get("font_size", 14))),
                QFont.Weight.Bold,
            )
        )
        title.setStyleSheet(
            f"color: rgb({title_color[0]}, {title_color[1]}, {title_color[2]}); "
            f"background: transparent; padding: 0px;"
        )
        root.addWidget(title)
        root.addSpacing(int(title_config.get("spacing_after", 4)))

        label_color = _rgb(label_config.get("text_color"), [200, 200, 200])
        label_size = int(scale_font_size(label_config.get("font_size", 11)))
        label_family = resolve_font_family(
            label_config.get("font_family", "Helvetica Neue")
        )

        oid = (self._entry.opening_id or "").strip()
        if oid:
            tags_cfg = (
                (config.get("ui") or {})
                .get("dialogs", {})
                .get("opening_encyclopedia_dialog", {})
                .get("tags", {})
            )
            if not isinstance(tags_cfg, dict):
                tags_cfg = {}
            pad = tags_cfg.get("padding", [2, 6, 2, 6])
            if not isinstance(pad, (list, tuple)) or len(pad) < 4:
                pad = [2, 6, 2, 6]
            entry_row = QHBoxLayout()
            entry_row.setContentsMargins(0, 0, 0, 0)
            entry_row.setSpacing(8)
            entry_row.addWidget(
                build_encyclopedia_tag_chip(
                    "ID",
                    oid,
                    bg=_rgb(tags_cfg.get("id_background"), [55, 55, 62]),
                    fg=_rgb(tags_cfg.get("id_text_color"), [180, 180, 190]),
                    font_size=int(scale_font_size(tags_cfg.get("font_size", 8))),
                    border_radius=int(tags_cfg.get("border_radius", 4)),
                    padding=list(pad),
                ),
                0,
                Qt.AlignmentFlag.AlignVCenter,
            )
            entry_row.addStretch(1)
            root.addLayout(entry_row)
            root.addSpacing(int(entry_config.get("spacing_after", 8)))

        cat_label = QLabel(str(category_config.get("label", "Category")))
        cat_label.setStyleSheet(
            f"color: rgb({label_color[0]}, {label_color[1]}, {label_color[2]}); "
            f"font-family: \"{label_family}\"; font-size: {label_size}pt; background: transparent;"
        )
        root.addWidget(cat_label)

        self._category = QComboBox()
        categories = category_config.get("items", _DEFAULT_CATEGORIES)
        if not isinstance(categories, list) or not categories:
            categories = list(_DEFAULT_CATEGORIES)
        self._category.addItem(str(category_config.get("placeholder", "Select a category…")), "")
        for item in categories:
            text = str(item).strip()
            if text:
                self._category.addItem(text, text)
        self._category.setCurrentIndex(0)
        StyleManager.style_comboboxes([self._category], config)
        root.addWidget(self._category)
        root.addSpacing(int(category_config.get("spacing_after", 8)))

        desc_label = QLabel(str(description_config.get("label", "Description")))
        desc_label.setStyleSheet(
            f"color: rgb({label_color[0]}, {label_color[1]}, {label_color[2]}); "
            f"font-family: \"{label_family}\"; font-size: {label_size}pt; background: transparent;"
        )
        root.addWidget(desc_label)

        self._description = QPlainTextEdit()
        self._description.setPlaceholderText(
            str(
                description_config.get(
                    "placeholder",
                    "Describe the issue or suggestion…",
                )
            )
        )
        desc_h = int(description_config.get("minimum_height", 100))
        self._description.setFixedHeight(desc_h)
        self._description.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._style_description(description_config)
        root.addWidget(self._description)
        root.addSpacing(int(description_config.get("spacing_after", 8)))

        delivery_label = QLabel(str(delivery_config.get("label", "How to report")))
        delivery_label.setStyleSheet(
            f"color: rgb({label_color[0]}, {label_color[1]}, {label_color[2]}); "
            f"font-family: \"{label_family}\"; font-size: {label_size}pt; background: transparent;"
        )
        root.addWidget(delivery_label)

        self._delivery = QComboBox()
        self._delivery_hints: Dict[str, str] = {}
        delivery_items = delivery_config.get("items", _DEFAULT_DELIVERY_ITEMS)
        if not isinstance(delivery_items, list) or not delivery_items:
            delivery_items = list(_DEFAULT_DELIVERY_ITEMS)
        default_hints = {
            item["id"]: str(item.get("hint") or "") for item in _DEFAULT_DELIVERY_ITEMS
        }
        for item in delivery_items:
            if isinstance(item, dict):
                item_id = str(item.get("id") or "").strip()
                item_label = str(item.get("label") or item_id).strip()
                item_hint = str(item.get("hint") or "").strip()
            else:
                item_id = str(item).strip()
                item_label = item_id
                item_hint = ""
            if item_id and item_label:
                self._delivery.addItem(item_label, item_id)
                self._delivery_hints[item_id] = item_hint or default_hints.get(
                    item_id, ""
                )
        if self._delivery.count() == 0:
            for item in _DEFAULT_DELIVERY_ITEMS:
                self._delivery.addItem(item["label"], item["id"])
                self._delivery_hints[item["id"]] = str(item.get("hint") or "")
        StyleManager.style_comboboxes([self._delivery], config)
        self._restore_delivery_selection()
        root.addWidget(self._delivery)
        root.addSpacing(int(delivery_config.get("spacing_after", 4)))

        messages_config = dialog_config.get("messages", {})
        if not isinstance(messages_config, dict):
            messages_config = {}
        self._msg_description_too_short = str(
            messages_config.get(
                "description_too_short", _DEFAULT_MSG_DESCRIPTION_TOO_SHORT
            )
        )
        self._msg_category_required = str(
            messages_config.get("category_required", _DEFAULT_MSG_CATEGORY_REQUIRED)
        )

        hint_color = _rgb(hint_config.get("text_color"), [150, 150, 155])
        self._hint = QLabel("")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet(
            f"color: rgb({hint_color[0]}, {hint_color[1]}, {hint_color[2]}); "
            f"font-family: \"{label_family}\"; "
            f"font-size: {int(scale_font_size(hint_config.get('font_size', 9)))}pt; "
            f"background: transparent;"
        )
        root.addWidget(self._hint)

        root.addSpacing(self.bottom_button_top_padding)

        button_row = QHBoxLayout()
        button_row.setSpacing(int(buttons_config.get("spacing", 10)))

        cancel_btn = QPushButton(str(buttons_config.get("cancel_label", "Cancel")))
        cancel_btn.clicked.connect(self.reject)

        self._create_btn = QPushButton(
            str(buttons_config.get("create_label", "Create Report"))
        )
        self._create_btn.clicked.connect(self._create_report)

        button_row.addStretch(1)
        button_row.addWidget(cancel_btn)
        button_row.addWidget(self._create_btn)

        border = _rgb(buttons_config.get("border_color"), [60, 60, 65])
        btn_w = int(buttons_config.get("width", 120))
        create_w = int(buttons_config.get("create_width", btn_w))
        btn_h = int(buttons_config.get("height", 30))
        StyleManager.style_buttons(
            [cancel_btn],
            config,
            bg,
            border,
            min_width=btn_w,
            min_height=btn_h,
        )
        StyleManager.style_buttons(
            [self._create_btn],
            config,
            bg,
            border,
            min_width=create_w,
            min_height=btn_h,
        )
        root.addLayout(button_row)

        self._category.currentIndexChanged.connect(self._update_send_enabled)
        self._description.textChanged.connect(self._update_send_enabled)
        self._delivery.currentIndexChanged.connect(self._update_send_enabled)
        self._update_send_enabled()

        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._apply_configured_dialog_size()

    def _style_description(self, description_config: Dict[str, Any]) -> None:
        styles = (self.config.get("ui") or {}).get("styles", {})
        line_edit = styles.get("line_edit", {}) if isinstance(styles, dict) else {}
        fg = _rgb(
            description_config.get("text_color"),
            line_edit.get("text_color", [220, 220, 225]),
        )
        bg = _rgb(
            description_config.get("background_color"),
            line_edit.get("background_color", [30, 30, 35]),
        )
        border = _rgb(
            description_config.get("border_color"),
            line_edit.get("border_color", [60, 60, 65]),
        )
        focus_border = _rgb(
            description_config.get("focus_border_color"),
            line_edit.get("focus_border_color", border),
        )
        radius = int(description_config.get("border_radius", 3))
        pad = description_config.get("padding", [6, 8, 6, 8])
        if not isinstance(pad, (list, tuple)) or len(pad) < 4:
            pad = [6, 8, 6, 8]
        family = resolve_font_family(
            description_config.get(
                "font_family", line_edit.get("font_family", "Helvetica Neue")
            )
        )
        size = int(
            scale_font_size(
                description_config.get("font_size", line_edit.get("font_size", 11))
            )
        )
        self._description.setFont(QFont(family, size))
        self._description.setStyleSheet(
            f"QPlainTextEdit {{"
            f" background-color: rgb({bg[0]}, {bg[1]}, {bg[2]});"
            f" color: rgb({fg[0]}, {fg[1]}, {fg[2]});"
            f" border: 1px solid rgb({border[0]}, {border[1]}, {border[2]});"
            f" border-radius: {radius}px;"
            f" padding: {int(pad[0])}px {int(pad[1])}px {int(pad[2])}px {int(pad[3])}px;"
            f" }}"
            f"QPlainTextEdit:focus {{"
            f" border: 1px solid rgb({focus_border[0]}, {focus_border[1]}, {focus_border[2]});"
            f" }}"
        )

    def _recipient_email(self) -> str:
        configured = str(self._dialog_config.get("recipient_email") or "").strip()
        if configured:
            return configured
        about = (
            (self.config.get("ui") or {})
            .get("dialogs", {})
            .get("about_dialog", {})
            .get("contact", {})
        )
        if isinstance(about, dict):
            return str(about.get("email") or "").strip()
        return ""

    def _app_version(self) -> str:
        return str(self.config.get("version") or "unknown")

    def _selected_category(self) -> str:
        data = self._category.currentData()
        return str(data or "").strip()

    def _selected_delivery(self) -> str:
        data = self._delivery.currentData()
        return str(data or "").strip()

    def _description_text(self) -> str:
        return self._description.toPlainText().strip()

    def _restore_delivery_selection(self) -> None:
        preferred = _DELIVERY_MAILTO
        try:
            from app.services.user_settings_service import UserSettingsService

            stored = (
                UserSettingsService.get_instance()
                .get_opening_encyclopedia_dialog()
                .get("feedback_delivery")
            )
            if isinstance(stored, str) and stored.strip():
                preferred = stored.strip()
        except Exception:
            pass
        idx = self._delivery.findData(preferred)
        self._delivery.setCurrentIndex(idx if idx >= 0 else 0)

    def _update_send_enabled(self) -> None:
        has_category = bool(self._selected_category())
        has_delivery = bool(self._selected_delivery())
        description_ok = (
            len(self._description_text()) >= self._min_description_chars
        )
        ok = has_category and has_delivery and description_ok
        self._create_btn.setEnabled(ok)
        self._update_hint(has_category=has_category, description_ok=description_ok)

    def _update_hint(self, *, has_category: bool, description_ok: bool) -> None:
        if not has_category:
            text = self._msg_category_required
        elif not description_ok:
            text = self._msg_description_too_short
        else:
            text = self._delivery_hints.get(self._selected_delivery(), "")
        self._hint.setText(text)
        self._hint.setVisible(bool(text))


    def _create_report(self) -> None:
        self._deliver(self._selected_delivery())

    def _build_report(self) -> Tuple[str, str]:
        """Return (subject, body) for the feedback report."""
        name = (self._entry.display_name or "").strip() or "(unnamed)"
        oid = (self._entry.opening_id or "").strip() or "(unknown)"
        category = self._selected_category()
        subject = f"CARA Encyclopedia feedback: {name}"
        body_lines = [
            "CARA Opening Encyclopedia Feedback",
            f"App version: {self._app_version()}",
            f"Opening ID: {oid}",
            f"Display name: {name}",
            f"Category: {category}",
            "",
            "Description:",
            self._description_text(),
            "",
        ]
        return subject, "\n".join(body_lines)

    def _apply_configured_dialog_size(self) -> None:
        """Fixed width from config; height from layout size hint (non-resizable)."""
        w = int(self.dialog_width)
        self.setFixedWidth(w)
        lay = self.layout()
        if lay is None:
            return
        h = int(lay.sizeHint().height())
        if h > 0:
            self.setFixedHeight(h)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._apply_configured_dialog_size()

    def _deliver(self, method: str) -> None:
        method = (method or "").strip()
        if (
            not method
            or not self._selected_category()
            or len(self._description_text()) < self._min_description_chars
        ):
            return
        subject, body = self._build_report()
        email = self._recipient_email()

        try:
            from app.services.user_settings_service import UserSettingsService

            UserSettingsService.get_instance().update_opening_encyclopedia_dialog(
                {"feedback_delivery": method}
            )
        except Exception:
            pass

        if method == _DELIVERY_CLIPBOARD:
            QApplication.clipboard().setText(body)
            msg = (
                "The feedback report was copied to the clipboard.\n"
                f"Paste it into an email to {email}."
                if email
                else (
                    "The feedback report was copied to the clipboard.\n"
                    "Paste it into an email to the CARA contact address."
                )
            )
            MessageDialog.show_information(
                self.config,
                "Report copied",
                msg,
                parent=self,
            )
            self.accept()
            return

        if not email:
            MessageDialog.show_warning(
                self.config,
                "Missing contact email",
                "No feedback recipient email is configured.",
                parent=self,
            )
            return

        if method == _DELIVERY_MAILTO:
            url = QUrl(f"mailto:{email}")
            url.setQuery(f"subject={quote(subject)}&body={quote(body)}")
            if not open_url(url, context="encyclopedia.feedback.mailto"):
                MessageDialog.show_warning(
                    self.config,
                    "Could not open mail app",
                    "No mail app could be opened. Try Gmail or Copy instead.",
                    parent=self,
                )
                return
            self.accept()
            return

        if method == _DELIVERY_GMAIL:
            gmail = (
                "https://mail.google.com/mail/?view=cm&fs=1"
                f"&to={quote(email)}"
                f"&su={quote(subject)}"
                f"&body={quote(body)}"
            )
            if not open_url(QUrl(gmail), context="encyclopedia.feedback.gmail"):
                MessageDialog.show_warning(
                    self.config,
                    "Could not open browser",
                    "Gmail could not be opened. Try Mail app or Copy instead.",
                    parent=self,
                )
                return
            self.accept()
            return

    @staticmethod
    def show_for_entry(
        config: Dict[str, Any],
        entry: EncyclopediaEntry,
        parent=None,
    ) -> None:
        dialog = OpeningEncyclopediaFeedbackDialog(config, entry, parent)
        dialog.exec()
