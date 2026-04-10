"""AI Summary menu definition for MainWindow."""

from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenuBar


def setup_ai_summary_menu(mw, menu_bar: QMenuBar) -> None:
    ai_summary_menu = menu_bar.addMenu("AI Summary")
    mw._apply_menu_styling(ai_summary_menu)

    ai_model_settings_action = QAction("AI Model Settings...", mw)
    ai_model_settings_action.setMenuRole(QAction.MenuRole.NoRole)
    ai_model_settings_action.triggered.connect(mw._show_ai_model_settings)
    ai_summary_menu.addAction(ai_model_settings_action)

    ai_summary_menu.addSeparator()

    mw.ai_summary_use_openai_action = QAction("Use OpenAI Models", mw)
    mw.ai_summary_use_openai_action.setCheckable(True)
    mw.ai_summary_use_openai_action.triggered.connect(
        lambda: mw._on_ai_summary_provider_selected("openai")
    )
    ai_summary_menu.addAction(mw.ai_summary_use_openai_action)

    mw.ai_summary_use_anthropic_action = QAction("Use Anthropic Models", mw)
    mw.ai_summary_use_anthropic_action.setCheckable(True)
    mw.ai_summary_use_anthropic_action.triggered.connect(
        lambda: mw._on_ai_summary_provider_selected("anthropic")
    )
    ai_summary_menu.addAction(mw.ai_summary_use_anthropic_action)

    mw.ai_summary_use_custom_action = QAction("Use Custom Endpoint", mw)
    mw.ai_summary_use_custom_action.setCheckable(True)
    mw.ai_summary_use_custom_action.triggered.connect(
        lambda: mw._on_ai_summary_provider_selected("custom")
    )
    ai_summary_menu.addAction(mw.ai_summary_use_custom_action)

    ai_summary_menu.addSeparator()

    mw.ai_summary_include_analysis_action = QAction("Include Game Analysis Data in Pre-Prompt", mw)
    mw.ai_summary_include_analysis_action.setCheckable(True)
    mw.ai_summary_include_analysis_action.triggered.connect(mw._on_ai_summary_include_analysis_toggled)
    ai_summary_menu.addAction(mw.ai_summary_include_analysis_action)

    mw.ai_summary_include_metadata_action = QAction("Include PGN header tags in pre-prompt", mw)
    mw.ai_summary_include_metadata_action.setCheckable(True)
    mw.ai_summary_include_metadata_action.triggered.connect(mw._on_ai_summary_include_metadata_toggled)
    ai_summary_menu.addAction(mw.ai_summary_include_metadata_action)

