"""Tests for ai_provider_config helpers.

Exhaustive truth table across provider configurations:
- none configured
- openai only (fully configured)
- anthropic only (fully configured)
- custom only (enabled, base_url, model)
- all three toggle flags active → falls back to OpenAI (exclusivity rule)
- none toggle flags active   → falls back to OpenAI (exclusivity rule)
- key present but model missing
- model present but key missing
- custom disabled (enabled=False)
- custom missing base_url
"""

import unittest

from app.services.ai_service import AIProvider
from app.utils.ai_provider_config import (
    get_active_provider_label,
    get_available_models,
    is_ai_configured,
    resolve_default_provider,
)


def _settings(**ai_models_overrides):
    """Build a minimal user_settings dict with the given ai_models sub-keys."""
    return {"ai_models": ai_models_overrides}


def _settings_with_summary(summary_overrides, **ai_models_overrides):
    s = _settings(**ai_models_overrides)
    s["ai_summary"] = summary_overrides
    return s


class TestIsAiConfigured(unittest.TestCase):

    def test_empty_settings_returns_false(self):
        self.assertFalse(is_ai_configured({}))

    def test_openai_fully_configured_returns_true(self):
        s = _settings(openai={"api_key": "sk-abc", "model": "gpt-4o"})
        self.assertTrue(is_ai_configured(s))

    def test_anthropic_active_fully_configured_returns_true(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": True, "use_custom_models": False},
            anthropic={"api_key": "ant-key", "model": "claude-3-5-sonnet-20241022"},
        )
        self.assertTrue(is_ai_configured(s))

    def test_custom_active_fully_configured_returns_true(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": True},
            custom={"enabled": True, "base_url": "http://localhost:11434", "model": "llama3", "api_key": ""},
        )
        self.assertTrue(is_ai_configured(s))

    def test_openai_key_only_no_model_returns_false(self):
        s = _settings(openai={"api_key": "sk-abc", "model": ""})
        self.assertFalse(is_ai_configured(s))

    def test_openai_model_only_no_key_returns_false(self):
        s = _settings(openai={"api_key": "", "model": "gpt-4o"})
        self.assertFalse(is_ai_configured(s))

    def test_custom_disabled_returns_false(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": True},
            custom={"enabled": False, "base_url": "http://localhost", "model": "llama3", "api_key": ""},
        )
        self.assertFalse(is_ai_configured(s))

    def test_custom_missing_base_url_returns_false(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": True},
            custom={"enabled": True, "base_url": "", "model": "llama3", "api_key": ""},
        )
        self.assertFalse(is_ai_configured(s))

    def test_all_toggles_true_falls_back_to_openai(self):
        # Multiple active → fallback to OpenAI; OpenAI has valid key+model
        s = _settings_with_summary(
            {"use_openai_models": True, "use_anthropic_models": True, "use_custom_models": True},
            openai={"api_key": "sk-abc", "model": "gpt-4o"},
        )
        self.assertTrue(is_ai_configured(s))

    def test_all_toggles_false_falls_back_to_openai(self):
        # The "all three False" state is only reachable via manual JSON editing —
        # the settings dialog only ever writes exactly one True (or leaves them
        # unchanged when multiple providers have credentials).  The fallback to
        # OpenAI is a defensive guard against corrupt settings state, not a path
        # normal users hit.  Credential check still applies: OpenAI must have a
        # valid api_key+model for is_ai_configured() to return True.
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": False},
            openai={"api_key": "sk-abc", "model": "gpt-4o"},
        )
        self.assertTrue(is_ai_configured(s))

    def test_all_toggles_false_no_openai_configured_returns_false(self):
        # Even with the OpenAI fallback, no api_key → False.
        # A player who has never configured any LLM will always get False here.
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": False},
            openai={"api_key": "", "model": "gpt-4o"},
        )
        self.assertFalse(is_ai_configured(s))


class TestResolveDefaultProvider(unittest.TestCase):

    def test_openai_returns_correct_tuple(self):
        s = _settings(openai={"api_key": "sk-abc", "model": "gpt-4o"})
        result = resolve_default_provider(s)
        self.assertIsNotNone(result)
        provider, model, api_key, base_url = result
        self.assertEqual(provider, AIProvider.OPENAI)
        self.assertEqual(model, "gpt-4o")
        self.assertEqual(api_key, "sk-abc")
        self.assertIsNone(base_url)

    def test_anthropic_returns_correct_tuple(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": True, "use_custom_models": False},
            anthropic={"api_key": "ant-key", "model": "claude-opus-4-7"},
        )
        result = resolve_default_provider(s)
        self.assertIsNotNone(result)
        provider, model, api_key, base_url = result
        self.assertEqual(provider, AIProvider.ANTHROPIC)
        self.assertEqual(model, "claude-opus-4-7")
        self.assertIsNone(base_url)

    def test_custom_returns_correct_tuple_with_base_url(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": True},
            custom={"enabled": True, "base_url": "http://localhost:11434", "model": "llama3", "api_key": "tok"},
        )
        result = resolve_default_provider(s)
        self.assertIsNotNone(result)
        provider, model, api_key, base_url = result
        self.assertEqual(provider, AIProvider.CUSTOM)
        self.assertEqual(base_url, "http://localhost:11434")
        self.assertEqual(api_key, "tok")

    def test_unconfigured_returns_none(self):
        self.assertIsNone(resolve_default_provider({}))

    def test_partial_openai_returns_none(self):
        s = _settings(openai={"api_key": "sk-abc"})  # no model key at all
        self.assertIsNone(resolve_default_provider(s))

    def test_fallback_exclusivity_openai_chosen(self):
        # Three toggles active → OpenAI wins; Anthropic also configured but ignored
        s = _settings_with_summary(
            {"use_openai_models": True, "use_anthropic_models": True, "use_custom_models": True},
            openai={"api_key": "sk-openai", "model": "gpt-4o"},
            anthropic={"api_key": "ant-key", "model": "claude-opus-4-7"},
        )
        result = resolve_default_provider(s)
        self.assertIsNotNone(result)
        self.assertEqual(result[0], AIProvider.OPENAI)
        self.assertEqual(result[2], "sk-openai")


class TestGetAvailableModels(unittest.TestCase):
    """Tests for get_available_models() — the shared plain-model-ID helper.

    Resolves #5 instance 6: extracts the provider-selection + model-list
    logic shared by ChessLogChartsController and AIChatController.
    """

    def test_openai_active_returns_models_list(self):
        s = _settings(openai={"api_key": "sk-abc", "models": ["gpt-4o", "gpt-4-turbo"]})
        self.assertEqual(get_available_models(s), ["gpt-4o", "gpt-4-turbo"])

    def test_anthropic_active_returns_models_list(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": True, "use_custom_models": False},
            anthropic={"api_key": "ant-key", "models": ["claude-opus-4-7"]},
        )
        self.assertEqual(get_available_models(s), ["claude-opus-4-7"])

    def test_custom_active_returns_models_list(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": True},
            custom={"enabled": True, "base_url": "http://localhost:11434", "models": ["llama3", "mistral"], "api_key": ""},
        )
        self.assertEqual(get_available_models(s), ["llama3", "mistral"])

    def test_no_toggles_falls_back_to_openai(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": False},
            openai={"api_key": "sk-abc", "models": ["gpt-4o"]},
        )
        self.assertEqual(get_available_models(s), ["gpt-4o"])

    def test_multiple_toggles_falls_back_to_openai(self):
        s = _settings_with_summary(
            {"use_openai_models": True, "use_anthropic_models": True, "use_custom_models": False},
            openai={"api_key": "sk-abc", "models": ["gpt-4o"]},
        )
        self.assertEqual(get_available_models(s), ["gpt-4o"])

    def test_openai_no_api_key_returns_empty(self):
        s = _settings(openai={"api_key": "", "models": ["gpt-4o"]})
        self.assertEqual(get_available_models(s), [])

    def test_openai_empty_models_returns_empty(self):
        s = _settings(openai={"api_key": "sk-abc", "models": []})
        self.assertEqual(get_available_models(s), [])

    def test_custom_disabled_returns_empty(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": True},
            custom={"enabled": False, "base_url": "http://localhost", "models": ["llama3"], "api_key": ""},
        )
        self.assertEqual(get_available_models(s), [])

    def test_custom_no_base_url_returns_empty(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": True},
            custom={"enabled": True, "base_url": "", "models": ["llama3"], "api_key": ""},
        )
        self.assertEqual(get_available_models(s), [])

    def test_empty_settings_returns_empty(self):
        self.assertEqual(get_available_models({}), [])

    def test_returns_a_copy_not_the_stored_list(self):
        s = _settings(openai={"api_key": "sk-abc", "models": ["gpt-4o"]})
        result = get_available_models(s)
        result.append("injected")
        self.assertEqual(s["ai_models"]["openai"]["models"], ["gpt-4o"])


class TestGetActiveProviderLabel(unittest.TestCase):
    """Tests for get_active_provider_label() — returns the display label for the active provider."""

    def test_openai_active_with_key_returns_openai(self):
        s = _settings(openai={"api_key": "sk-abc"})
        self.assertEqual(get_active_provider_label(s), "OpenAI")

    def test_anthropic_active_with_key_returns_anthropic(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": True, "use_custom_models": False},
            anthropic={"api_key": "ant-key"},
        )
        self.assertEqual(get_active_provider_label(s), "Anthropic")

    def test_custom_active_enabled_with_base_url_returns_custom(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": True},
            custom={"enabled": True, "base_url": "http://localhost:11434", "api_key": ""},
        )
        self.assertEqual(get_active_provider_label(s), "Custom")

    def test_openai_no_api_key_returns_none(self):
        s = _settings(openai={"api_key": ""})
        self.assertIsNone(get_active_provider_label(s))

    def test_custom_disabled_returns_none(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": True},
            custom={"enabled": False, "base_url": "http://localhost", "api_key": ""},
        )
        self.assertIsNone(get_active_provider_label(s))

    def test_empty_settings_returns_none(self):
        # Fallback to OpenAI, no api_key → None
        self.assertIsNone(get_active_provider_label({}))

    def test_label_non_none_when_models_non_empty(self):
        # Invariant: get_active_provider_label returns non-None whenever
        # get_available_models returns non-empty for the same settings.
        s = _settings(openai={"api_key": "sk-abc", "models": ["gpt-4o"]})
        models = get_available_models(s)
        label = get_active_provider_label(s)
        self.assertTrue(len(models) > 0)
        self.assertIsNotNone(label)

    def test_no_toggles_falls_back_to_openai_label(self):
        s = _settings_with_summary(
            {"use_openai_models": False, "use_anthropic_models": False, "use_custom_models": False},
            openai={"api_key": "sk-abc"},
        )
        self.assertEqual(get_active_provider_label(s), "OpenAI")


if __name__ == "__main__":
    unittest.main()
