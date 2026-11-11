"""Shared AI-provider configuration helpers.

Extracted from ``AIChatController.get_default_model`` /
``_get_provider_preferences`` so that Chess Log Charts and AI Summary
share a single definition of "is an LLM available."

All functions accept a plain ``user_settings`` dict (the value returned by
``UserSettingsService.get_settings()``) and have no side effects.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.services.ai_service import AIProvider


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _resolve_flags(user_settings: Dict[str, Any]) -> Tuple[bool, bool, bool]:
    """Return (use_openai, use_anthropic, use_custom) with exclusivity enforced.

    If zero or more than one toggle is True the fallback is OpenAI.
    """
    ai_summary = user_settings.get("ai_summary", {})
    use_openai = bool(ai_summary.get("use_openai_models", True))
    use_anthropic = bool(ai_summary.get("use_anthropic_models", False))
    use_custom = bool(ai_summary.get("use_custom_models", False))
    if sum([use_openai, use_anthropic, use_custom]) != 1:
        return True, False, False
    return use_openai, use_anthropic, use_custom


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_ai_configured(user_settings: Dict[str, Any]) -> bool:
    """Return True if at least one AI provider is fully configured and active."""
    return resolve_default_provider(user_settings) is not None


def resolve_default_provider(
    user_settings: Dict[str, Any],
) -> Optional[Tuple[AIProvider, str, str, Optional[str]]]:
    """Return ``(provider, model, api_key, base_url_override)`` for the active provider.

    Returns ``None`` if no provider is configured and active.
    ``base_url_override`` is non-None only for the ``custom`` provider.

    Mirrors the provider-preference logic from ``AIChatController``:
    - The active provider is read from ``ai_summary.use_*_models`` toggles.
    - If zero or multiple are True the fallback is OpenAI (same as the controller).
    - Custom additionally requires ``enabled=True`` and a non-empty ``base_url``.
    """
    ai_settings = user_settings.get("ai_models", {})
    use_openai, use_anthropic, use_custom = _resolve_flags(user_settings)

    if use_openai:
        s = ai_settings.get("openai", {})
        api_key = s.get("api_key") or ""
        model = s.get("model") or ""
        if api_key and model:
            return (AIProvider.OPENAI, model, api_key, None)

    if use_anthropic:
        s = ai_settings.get("anthropic", {})
        api_key = s.get("api_key") or ""
        model = s.get("model") or ""
        if api_key and model:
            return (AIProvider.ANTHROPIC, model, api_key, None)

    if use_custom:
        s = ai_settings.get("custom", {})
        base_url = (s.get("base_url") or "").strip()
        model = s.get("model") or ""
        api_key = s.get("api_key") or ""
        if s.get("enabled", False) and base_url and model:
            return (AIProvider.CUSTOM, model, api_key, base_url)

    return None


def get_available_models(user_settings: Dict[str, Any]) -> List[str]:
    """Return model IDs for the active provider as plain strings.

    Reads ``ai_models.<provider>.models`` (the full list) — distinct from
    ``resolve_default_provider`` which reads the single ``model`` field.
    Returns ``[]`` when:
    - no provider is active and configured
    - the active provider has no ``api_key`` (OpenAI / Anthropic)
    - custom: ``enabled`` is False or ``base_url`` is empty
    """
    ai_settings = user_settings.get("ai_models", {})
    use_openai, use_anthropic, use_custom = _resolve_flags(user_settings)

    if use_openai:
        s = ai_settings.get("openai", {})
        if s.get("api_key"):
            return list(s.get("models", []) or [])
    if use_anthropic:
        s = ai_settings.get("anthropic", {})
        if s.get("api_key"):
            return list(s.get("models", []) or [])
    if use_custom:
        s = ai_settings.get("custom", {})
        if s.get("enabled", False) and (s.get("base_url") or "").strip():
            return list(s.get("models", []) or [])
    return []


def get_active_provider_label(user_settings: Dict[str, Any]) -> Optional[str]:
    """Return ``"OpenAI"``, ``"Anthropic"``, or ``"Custom"`` for the active provider.

    Returns ``None`` when the active provider lacks minimum credentials
    (``api_key`` for OpenAI / Anthropic; ``enabled + base_url`` for Custom).
    When ``get_available_models()`` returns non-empty for the same settings,
    this function always returns a non-None label.
    """
    ai_settings = user_settings.get("ai_models", {})
    use_openai, use_anthropic, use_custom = _resolve_flags(user_settings)

    if use_openai:
        if ai_settings.get("openai", {}).get("api_key"):
            return "OpenAI"
    if use_anthropic:
        if ai_settings.get("anthropic", {}).get("api_key"):
            return "Anthropic"
    if use_custom:
        s = ai_settings.get("custom", {})
        if s.get("enabled", False) and (s.get("base_url") or "").strip():
            return "Custom"
    return None
