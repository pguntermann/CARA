"""Service for interacting with AI models (OpenAI and Anthropic)."""

import json
import requests
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, Callable
from enum import Enum
from app.services.logging_service import LoggingService

# Module-level debug callbacks (set from MainWindow)
_debug_outbound_callback: Optional[Callable[[], bool]] = None
_debug_inbound_callback: Optional[Callable[[], bool]] = None

# Thread-safe debug flags (updated from MainWindow)
_debug_outbound_enabled = False
_debug_inbound_enabled = False


def set_debug_callbacks(outbound_callback: Optional[Callable[[], bool]] = None,
                       inbound_callback: Optional[Callable[[], bool]] = None) -> None:
    """Set global debug callbacks for AI communication.
    
    Args:
        outbound_callback: Callback to check if outbound debugging is enabled.
        inbound_callback: Callback to check if inbound debugging is enabled.
    """
    global _debug_outbound_callback, _debug_inbound_callback
    _debug_outbound_callback = outbound_callback
    _debug_inbound_callback = inbound_callback


def set_debug_flags(outbound_enabled: bool = False, inbound_enabled: bool = False) -> None:
    """Set thread-safe debug flags for AI communication.
    
    Args:
        outbound_enabled: True if outbound debugging is enabled.
        inbound_enabled: True if inbound debugging is enabled.
    """
    global _debug_outbound_enabled, _debug_inbound_enabled
    _debug_outbound_enabled = outbound_enabled
    _debug_inbound_enabled = inbound_enabled


# Model name substrings for which {"type": "disabled"} must be sent to suppress
# thinking.  Matches claude-sonnet-5-* and claude-opus-5-* IDs (and future
# variants).
# Fable models ("fable-5") are intentionally excluded for two reasons:
#   1. They use a different thinking API (thinking.type.adaptive + output_config.effort);
#      {"type": "disabled"} returns HTTP 400 on Fable.
#   2. Empirically (tested 2026-09-27 with claude-fable-5-1 on a real narrative
#      prompt), Fable does not self-trigger extended thinking — reasoning_tokens
#      is absent and the full narrative reply is returned without issue.
#      Returning None (no thinking override) is therefore safe for Fable.
_THINKING_DISABLE_MODELS = ("sonnet-5", "opus-5")


@dataclass(frozen=True)
class TokenUsage:
    """Token counts reported by the provider after a request."""
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    reasoning_tokens: Optional[int]   # thinking (Anthropic) or reasoning (OpenAI o-series)
    reported: bool                     # False when the provider omitted usage entirely


@dataclass(frozen=True)
class AIResult:
    """Return value from AIService.send_message."""
    success: bool
    text: str                   # response text on success; "" on failure
    error: Optional[str]        # error message on failure; None on success
    usage: Optional[TokenUsage]
    model: str
    # Anthropic-only diagnostics; None for OpenAI / custom / error paths.
    stop_reason: Optional[str] = None
    content_block_count: Optional[int] = None
    content_block_types: Optional[Tuple[str, ...]] = None


class AIProvider(str, Enum):
    """AI provider types."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    CUSTOM = "custom"


class AIService:
    """Service for making API calls to AI providers."""

    # Cache for models that require max_completion_tokens instead of max_tokens
    # This is a class-level cache so it persists across all instances
    _models_requiring_max_completion_tokens: set = set()

    # Cache for models that don't support temperature parameter (or only support default)
    # This is a class-level cache so it persists across all instances
    _models_not_supporting_temperature: set = set()

    # Cache for Anthropic models that reject thinking.type.disabled.  Maps model_id →
    # the thinking-override dict to substitute on future calls:
    #   Opus 5.5 / Fable 5 / Mythos 5:  {"thinking": {"type": "adaptive"},
    #                                      "output_config": {"effort": "low"}}
    #   Sonnet 5.5:                       {"thinking": {"type": "between_tools"}}
    # Populated on the first 400 with a recognized "disabled not supported" message;
    # subsequent calls for that model skip straight to the replacement payload.
    _models_thinking_override: dict = {}
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the AI service.
        
        Args:
            config: Configuration dictionary. If None, uses default endpoints.
        """
        self.config = config or {}
        # Load API endpoints from config
        ai_config = self.config.get("ai", {}).get("api_endpoints", {})
        openai_config = ai_config.get("openai", {})
        anthropic_config = ai_config.get("anthropic", {})
        
        # Use config values or fall back to defaults
        self.OPENAI_CHAT_URL = openai_config.get("chat", "https://api.openai.com/v1/chat/completions")
        self.ANTHROPIC_MESSAGES_URL = anthropic_config.get("messages", "https://api.anthropic.com/v1/messages")

    @staticmethod
    def disable_thinking_for(model: str) -> Optional[Dict[str, Any]]:
        """Return {"type": "disabled"} for models that burn output budget on thinking.

        Pass the result as the thinking= kwarg to send_message.  Returns None
        (no thinking override) for all other models.
        """
        m = (model or "").lower()
        if any(name in m for name in _THINKING_DISABLE_MODELS):
            return {"type": "disabled"}
        return None

    @staticmethod
    def _extract_error_message(response: requests.Response, status_code: int) -> str:
        """Extract a human-readable error message from an API error response."""
        fallback = f"API error: {status_code}"
        try:
            body = response.json() if response.content else None
        except Exception:
            body = None
        if body is None:
            return fallback
        if isinstance(body, dict):
            # OpenAI-style: {"error": {"message": "..."}}
            err = body.get("error")
            if isinstance(err, dict) and err.get("message"):
                return f"API error: {status_code} - {err.get('message')}"
            if isinstance(err, str):
                return f"API error: {status_code} - {err}"
            # Common alternatives: detail, message
            for key in ("detail", "message", "error"):
                val = body.get(key)
                if isinstance(val, str) and val:
                    return f"API error: {status_code} - {val}"
            if isinstance(body.get("detail"), list) and body["detail"]:
                # e.g. FastAPI validation: [{"loc": [...], "msg": "..."}]
                first = body["detail"][0]
                msg = first.get("msg") if isinstance(first, dict) else str(first)
                if msg:
                    return f"API error: {status_code} - {msg}"
        if isinstance(body, str) and body.strip():
            return f"API error: {status_code} - {body[:300]}"
        return fallback

    def _debug_console(self, message: str, direction: str) -> None:
        """Log debug message to console if console debugging is enabled.
        
        Args:
            message: Debug message to log.
            direction: Direction of communication: "SEND" (outbound) or "RECV" (inbound).
        """
        try:
            # Check if console debugging is enabled for this direction
            # Use thread-safe flags first (most reliable), then try callbacks as fallback
            should_log = False
            if direction == "SEND":
                # Check thread-safe flag first
                should_log = _debug_outbound_enabled
                # If flag is False, try callbacks as fallback
                if not should_log and _debug_outbound_callback:
                    try:
                        should_log = _debug_outbound_callback()
                    except Exception:
                        pass
            elif direction == "RECV":
                # Check thread-safe flag first
                should_log = _debug_inbound_enabled
                # If flag is False, try callbacks as fallback
                if not should_log and _debug_inbound_callback:
                    try:
                        should_log = _debug_inbound_callback()
                    except Exception:
                        pass
            
            if should_log:
                # Build message (logging service handles timestamp/thread)
                formatted_message = f"[AI {direction}] {message}"
                
                logging_service = LoggingService.get_instance()
                logging_service.debug(formatted_message)
        except Exception:
            # Silently ignore debug logging errors
            pass
    
    def send_message(
        self,
        provider: str,
        model: str,
        api_key: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        token_limit: Optional[int] = None,
        base_url_override: Optional[str] = None,
        timeout_seconds: int = 60,
        thinking: Optional[Dict[str, Any]] = None,
    ) -> AIResult:
        """Send a message to an AI provider and get response.
        
        Args:
            provider: Provider name ("openai", "anthropic", or "custom").
            model: Model ID (e.g., "gpt-4", "claude-3-5-sonnet-20241022").
            api_key: API key for the provider (optional for custom endpoints).
            messages: List of message dicts with "role" and "content" keys.
            system_prompt: Optional system prompt (for OpenAI, included in messages; for Anthropic, separate).
            base_url_override: For custom provider, the base URL (e.g. http://localhost:1234/v1).
            timeout_seconds: Request timeout in seconds.
            thinking: Optional thinking config dict (e.g. {"type": "disabled"}).
            
        Returns:
            AIResult with success, text, error, usage, and model fields.
        """
        try:
            if provider == AIProvider.OPENAI:
                return self._send_openai_message(model, api_key, messages, system_prompt, token_limit, timeout_seconds=timeout_seconds)
            elif provider == AIProvider.ANTHROPIC:
                return self._send_anthropic_message(model, api_key, messages, system_prompt, token_limit=token_limit, timeout_seconds=timeout_seconds, thinking=thinking)
            elif provider == AIProvider.CUSTOM and base_url_override:
                chat_url = base_url_override.rstrip("/") + "/chat/completions"
                return self._send_openai_message(
                    model, api_key or "", messages, system_prompt, token_limit, chat_url=chat_url, timeout_seconds=timeout_seconds
                )
            else:
                return AIResult(
                    success=False, text="",
                    error=f"Unknown or misconfigured provider: {provider}",
                    usage=None, model=model,
                )
        except Exception as e:
            return AIResult(success=False, text="", error=str(e), usage=None, model=model)
    
    def _send_openai_message(
        self,
        model: str,
        api_key: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        token_limit: Optional[int] = None,
        chat_url: Optional[str] = None,
        timeout_seconds: int = 60
    ) -> AIResult:
        """Send message to OpenAI API or OpenAI-compatible endpoint.
        
        Args:
            model: Model ID.
            api_key: API key (optional for local endpoints).
            messages: List of message dicts.
            system_prompt: Optional system prompt.
            chat_url: Optional override URL (for custom provider); default is self.OPENAI_CHAT_URL.
            timeout_seconds: Request timeout in seconds.
            
        Returns:
            AIResult with success, text, error, usage, and model fields.
        """
        url = chat_url if chat_url is not None else self.OPENAI_CHAT_URL
        # Prepare messages for OpenAI
        openai_messages = []
        
        # Add system prompt if provided
        if system_prompt:
            openai_messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        # Add conversation messages
        for msg in messages:
            # OpenAI uses "assistant" instead of "ai"
            role = msg["role"]
            if role == "ai":
                role = "assistant"
            openai_messages.append({
                "role": role,
                "content": msg["content"]
            })
        
        # Make API request
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Some newer OpenAI models have different parameter requirements:
        # - Use max_completion_tokens instead of max_tokens
        # - Don't support temperature parameter
        # - For o3 models, need higher token limit to account for reasoning tokens + output tokens
        # Check if we've cached that this model requires max_completion_tokens, or if it's o3/o1
        requires_max_completion = (
            model in self._models_requiring_max_completion_tokens or
            model.startswith("o3-") or 
            model.startswith("o1-")
        )
        
        # Check if model doesn't support temperature (cached or known o3/o1 models)
        no_temperature = (
            model in self._models_not_supporting_temperature or
            model.startswith("o3-") or 
            model.startswith("o1-")
        )
        
        limit = token_limit if token_limit is not None else (4000 if model.startswith("o3-") else 2000)
        
        if requires_max_completion:
            payload = {
                "model": model,
                "messages": openai_messages,
                "max_completion_tokens": limit
            }
        else:
            # Older models use max_tokens
            payload = {
                "model": model,
                "messages": openai_messages,
                "max_tokens": limit
            }
            # Only add temperature if model supports it
            if not no_temperature:
                payload["temperature"] = 0.7
        
        # Debug outbound: log request payload (hide API key)
        debug_payload = payload.copy()
        debug_headers = {k: ("Bearer ***" if k == "Authorization" else v) for k, v in headers.items()}
        debug_message = ("POST " + str(url) + "\nHeaders: " + 
                        json.dumps(debug_headers, indent=2) + "\nPayload: " + 
                        json.dumps(debug_payload, indent=2))
        self._debug_console(debug_message, "SEND")
        _endpoint_label = "openai" if chat_url is None else "custom"
        try:
            _t0 = time.monotonic()
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
        except requests.exceptions.Timeout:
            _elapsed = time.monotonic() - _t0
            LoggingService.get_instance().error(
                f"AI request timeout: model={model}, timeout={timeout_seconds}s, "
                f"elapsed={_elapsed:.1f}s, endpoint={_endpoint_label}"
            )
            return AIResult(
                success=False, text="",
                error=f"Request timed out after {timeout_seconds}s ({url})",
                usage=None, model=model,
            )
        except requests.exceptions.ConnectionError:
            return AIResult(
                success=False, text="",
                error=f"Connection failed: could not reach {url}",
                usage=None, model=model,
            )

        # Debug inbound: log response
        try:
            response_data = response.json() if response.content else {}
            # Hide sensitive data in debug output
            debug_response = response_data.copy()
            if "choices" in debug_response:
                # Truncate content for readability
                for choice in debug_response.get("choices", []):
                    msg = choice.get("message", {})
                    if "content" in msg and len(msg["content"]) > 200:
                        msg["content"] = msg["content"][:200] + "... (truncated)"
            debug_message = ("Status: " + str(response.status_code) + "\nResponse: " + 
                            json.dumps(debug_response, indent=2))
            self._debug_console(debug_message, "RECV")
        except Exception:
            debug_message = ("Status: " + str(response.status_code) + 
                            "\nResponse: (non-JSON or error)")
            self._debug_console(debug_message, "RECV")
        
        if response.status_code != 200:
            error_message = self._extract_error_message(response, response.status_code)

            # Handle max_tokens error - retry with max_completion_tokens
            if "max_tokens" in error_message and "max_completion_tokens" in error_message.lower():
                # This model requires max_completion_tokens instead of max_tokens
                # Cache this information so we use the correct parameter from the start next time
                self._models_requiring_max_completion_tokens.add(model)
                
                # Retry the request with the correct parameter
                payload_retry = payload.copy()
                if "max_tokens" in payload_retry:
                    del payload_retry["max_tokens"]
                payload_retry["max_completion_tokens"] = limit
                
                # Also remove temperature if present - models requiring max_completion_tokens often don't support temperature
                if "temperature" in payload_retry:
                    del payload_retry["temperature"]
                    # Cache that this model doesn't support temperature
                    self._models_not_supporting_temperature.add(model)
                
                # Debug retry
                debug_payload_retry = payload_retry.copy()
                debug_message_retry = ("POST (RETRY) " + str(url) + "\nPayload: " +
                                      json.dumps(debug_payload_retry, indent=2))
                self._debug_console(debug_message_retry, "SEND")
                
                # Retry request
                try:
                    _t0_retry = time.monotonic()
                    response = requests.post(
                        url,
                        headers=headers,
                        json=payload_retry,
                        timeout=timeout_seconds
                    )
                except requests.exceptions.Timeout:
                    _elapsed = time.monotonic() - _t0_retry
                    LoggingService.get_instance().error(
                        f"AI request timeout: model={model}, timeout={timeout_seconds}s, "
                        f"elapsed={_elapsed:.1f}s, endpoint={_endpoint_label}-retry"
                    )
                    return AIResult(
                        success=False, text="",
                        error=f"Request timed out after {timeout_seconds}s ({url})",
                        usage=None, model=model,
                    )

                # Debug retry response
                try:
                    response_data_retry = response.json() if response.content else {}
                    debug_response_retry = response_data_retry.copy()
                    if "choices" in debug_response_retry:
                        for choice in debug_response_retry.get("choices", []):
                            msg = choice.get("message", {})
                            if "content" in msg and len(msg["content"]) > 200:
                                msg["content"] = msg["content"][:200] + "... (truncated)"
                    debug_message_retry = ("Status (RETRY): " + str(response.status_code) + "\nResponse: " +
                                          json.dumps(debug_response_retry, indent=2))
                    self._debug_console(debug_message_retry, "RECV")
                except Exception:
                    debug_message_retry = ("Status (RETRY): " + str(response.status_code) +
                                          "\nResponse: (non-JSON or error)")
                    self._debug_console(debug_message_retry, "RECV")

                # If retry also failed, return the error
                if response.status_code != 200:
                    return AIResult(
                        success=False, text="",
                        error=self._extract_error_message(response, response.status_code),
                        usage=None, model=model,
                    )
                # Otherwise, continue processing the successful retry response below (fall through to normal processing)

            # Handle temperature error - retry without temperature parameter
            # Check for various temperature error patterns
            # Error messages like: "Unsupported value: 'temperature' does not support 0.7..."
            # If error mentions temperature and any unsupported/error keywords, try without temperature
            # Be permissive - if temperature is mentioned in an error, try without it
            elif "temperature" in error_message.lower():
                # This model doesn't support temperature parameter (or only supports default)
                # Cache this information so we don't use temperature from the start next time
                self._models_not_supporting_temperature.add(model)
                
                # Retry the request without temperature parameter
                payload_retry = payload.copy()
                if "temperature" in payload_retry:
                    del payload_retry["temperature"]

                # Debug retry
                debug_payload_retry = payload_retry.copy()
                debug_message_retry = ("POST (RETRY) " + str(url) + "\nPayload: " +
                                      json.dumps(debug_payload_retry, indent=2))
                self._debug_console(debug_message_retry, "SEND")

                # Retry request
                try:
                    _t0_retry2 = time.monotonic()
                    response = requests.post(
                        url,
                        headers=headers,
                        json=payload_retry,
                        timeout=timeout_seconds
                    )
                except requests.exceptions.Timeout:
                    _elapsed = time.monotonic() - _t0_retry2
                    LoggingService.get_instance().error(
                        f"AI request timeout: model={model}, timeout={timeout_seconds}s, "
                        f"elapsed={_elapsed:.1f}s, endpoint={_endpoint_label}-retry"
                    )
                    return AIResult(
                        success=False, text="",
                        error=f"Request timed out after {timeout_seconds}s ({url})",
                        usage=None, model=model,
                    )

                # Debug retry response
                try:
                    response_data_retry = response.json() if response.content else {}
                    debug_response_retry = response_data_retry.copy()
                    if "choices" in debug_response_retry:
                        for choice in debug_response_retry.get("choices", []):
                            msg = choice.get("message", {})
                            if "content" in msg and len(msg["content"]) > 200:
                                msg["content"] = msg["content"][:200] + "... (truncated)"
                    debug_message_retry = ("Status (RETRY): " + str(response.status_code) + "\nResponse: " +
                                          json.dumps(debug_response_retry, indent=2))
                    self._debug_console(debug_message_retry, "RECV")
                except Exception:
                    debug_message_retry = ("Status (RETRY): " + str(response.status_code) +
                                          "\nResponse: (non-JSON or error)")
                    self._debug_console(debug_message_retry, "RECV")

                # If retry also failed, return the error
                if response.status_code != 200:
                    return AIResult(
                        success=False, text="",
                        error=self._extract_error_message(response, response.status_code),
                        usage=None, model=model,
                    )
                # Otherwise, continue processing the successful retry response below (fall through to normal processing)

            # Provide helpful error messages for other common issues
            elif "not supported in the v1/chat/completions" in error_message or "not in v1/chat/completions" in error_message:
                if "o3-" in model:
                    return AIResult(
                        success=False, text="",
                        error=(
                            f"Model {model} requires the v1/responses endpoint, which is not currently supported. "
                            "Please select a different model (e.g., gpt-4, gpt-3.5-turbo, or o1 models)."
                        ),
                        usage=None, model=model,
                    )
                else:
                    return AIResult(
                        success=False, text="",
                        error=(
                            f"Model {model} is not compatible with the chat completions endpoint. "
                            "This model may require a different API endpoint. Please select a different model."
                        ),
                        usage=None, model=model,
                    )
            else:
                # Other errors - return the error message
                return AIResult(success=False, text="", error=error_message, usage=None, model=model)
        
        try:
            data = response.json()
            if not isinstance(data, dict):
                return AIResult(
                    success=False, text="",
                    error=(
                        f"Unexpected API response format (expected JSON object, got {type(data).__name__}). "
                        "The server may have returned an error or non-standard response."
                    ),
                    usage=None, model=model,
                )

            # Extract content from response
            # Structure: {"choices": [{"message": {"content": "..."}}]}
            choices = data.get("choices", [])
            if not choices:
                return AIResult(
                    success=False, text="",
                    error=f"Empty choices in API response: {data}",
                    usage=None, model=model,
                )
            
            choice = choices[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            finish_reason = choice.get("finish_reason", "")
            
            # Extract token usage
            usage_data = data.get("usage")
            if usage_data:
                completion_details = (usage_data.get("completion_tokens_details") or {})
                usage = TokenUsage(
                    input_tokens=usage_data.get("prompt_tokens"),
                    output_tokens=usage_data.get("completion_tokens"),
                    reasoning_tokens=completion_details.get("reasoning_tokens"),
                    reported=True,
                )
            else:
                usage = TokenUsage(input_tokens=None, output_tokens=None, reasoning_tokens=None, reported=False)

            # Truncated / thinking-only empty reply (OpenAI and local OpenAI-compatible APIs)
            if finish_reason == "length" and not content:
                raw_usage = usage_data or {}
                completion_tokens = raw_usage.get("completion_tokens")
                reasoning_tokens = (raw_usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
                return AIResult(
                    success=False, text="",
                    error=self.output_token_limit_message(
                        output_tokens=completion_tokens,
                        reasoning_tokens=reasoning_tokens,
                    ),
                    usage=usage, model=model,
                )
            
            if not content:
                return AIResult(
                    success=False, text="",
                    error=f"Empty content in API response. Finish reason: {finish_reason}. Full response: {data}",
                    usage=usage, model=model,
                )
            
            return AIResult(success=True, text=content, error=None, usage=usage, model=model)
        except Exception as e:
            return AIResult(
                success=False, text="",
                error=f"Error parsing API response: {str(e)}",
                usage=None, model=model,
            )
    
    def _send_anthropic_message(
        self,
        model: str,
        api_key: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        token_limit: Optional[int] = None,
        timeout_seconds: int = 60,
        thinking: Optional[Dict[str, Any]] = None,
    ) -> AIResult:
        """Send message to Anthropic API.
        
        Args:
            model: Model ID.
            api_key: Anthropic API key.
            messages: List of message dicts.
            system_prompt: Optional system prompt.
            token_limit: Optional max output tokens (defaults to 2000).
            timeout_seconds: Request timeout in seconds.
            
        Returns:
            AIResult with success, text, error, usage, and model fields.
        """
        # Prepare messages for Anthropic
        anthropic_messages = []
        
        for msg in messages:
            # Anthropic uses "assistant" instead of "ai"
            role = msg["role"]
            if role == "ai":
                role = "assistant"
            anthropic_messages.append({
                "role": role,
                "content": msg["content"]
            })
        
        # Make API request
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        limit = token_limit if token_limit is not None else 2000
        payload = {
            "model": model,
            "max_tokens": limit,
            "messages": anthropic_messages
        }
        
        # Add system prompt if provided
        if system_prompt:
            payload["system"] = system_prompt

        if thinking is not None:
            payload["thinking"] = thinking

        # If this model already rejected thinking.type.disabled in a prior call this session,
        # substitute the cached override immediately — skip the failed first attempt.
        if thinking == {"type": "disabled"} and model in self._models_thinking_override:
            for key in ("thinking", "output_config"):
                payload.pop(key, None)
            payload.update(self._models_thinking_override[model])

        # Debug outbound: log request payload (hide API key)
        debug_payload = payload.copy()
        debug_headers = {k: ("***" if k == "x-api-key" else v) for k, v in headers.items()}
        debug_message = ("POST " + str(self.ANTHROPIC_MESSAGES_URL) + "\nHeaders: " + 
                        json.dumps(debug_headers, indent=2) + "\nPayload: " + 
                        json.dumps(debug_payload, indent=2))
        self._debug_console(debug_message, "SEND")

        try:
            _t0_anth = time.monotonic()
            response = requests.post(
                self.ANTHROPIC_MESSAGES_URL,
                headers=headers,
                json=payload,
                timeout=timeout_seconds
            )
        except requests.exceptions.Timeout:
            _elapsed = time.monotonic() - _t0_anth
            LoggingService.get_instance().error(
                f"AI request timeout: model={model}, timeout={timeout_seconds}s, "
                f"elapsed={_elapsed:.1f}s, endpoint=anthropic"
            )
            return AIResult(
                success=False, text="",
                error=f"Request timed out after {timeout_seconds}s",
                usage=None, model=model,
            )

        # Debug inbound: log response
        try:
            response_data = response.json() if response.content else {}
            # Hide sensitive data and truncate content for readability
            debug_response = response_data.copy()
            if "content" in debug_response:
                content_list = debug_response.get("content", [])
                for item in content_list:
                    if isinstance(item, dict) and "text" in item and len(item["text"]) > 200:
                        item["text"] = item["text"][:200] + "... (truncated)"
            debug_message = ("Status: " + str(response.status_code) + "\nResponse: " + 
                            json.dumps(debug_response, indent=2))
            self._debug_console(debug_message, "RECV")
        except Exception:
            debug_message = ("Status: " + str(response.status_code) + 
                            "\nResponse: (non-JSON or error)")
            self._debug_console(debug_message, "RECV")
        
        if response.status_code != 200:
            error_data = response.json() if response.content else {}
            error_message = error_data.get("error", {}).get("message", f"API error: {response.status_code}")

            # Retry once when the model rejects thinking.type.disabled with a recognized message.
            # Two distinct triggers, each narrow enough to avoid false matches:
            #   1. "thinking.type.disabled … not supported" → adaptive + effort:low
            #   2. "between_tools … instead of" → between_tools, no output_config
            #      (Sonnet 5.5 only; Anthropic docs: "'effort: high' matches the API default",
            #       which is within between_tools' allowed range, so no output_config needed)
            # Only fires when (a) we actually sent disabled and (b) this model hasn't been
            # cached yet — prevents a stale retry if pre-substitution somehow didn't apply.
            thinking_override = None
            if thinking == {"type": "disabled"} and model not in self._models_thinking_override:
                if ("thinking.type.disabled" in error_message
                        and "not supported" in error_message.lower()):
                    thinking_override = {"thinking": {"type": "adaptive"},
                                         "output_config": {"effort": "low"}}
                elif ("between_tools" in error_message
                        and "instead of" in error_message.lower()):
                    thinking_override = {"thinking": {"type": "between_tools"}}

            if thinking_override is not None:
                self._models_thinking_override[model] = thinking_override
                payload_retry = {k: v for k, v in payload.items()
                                 if k not in ("thinking", "output_config")}
                payload_retry.update(thinking_override)
                self._debug_console(
                    "POST (RETRY) " + str(self.ANTHROPIC_MESSAGES_URL) + "\nPayload: " +
                    json.dumps(payload_retry, indent=2), "SEND")
                try:
                    _t0_anth_retry = time.monotonic()
                    response = requests.post(
                        self.ANTHROPIC_MESSAGES_URL,
                        headers=headers,
                        json=payload_retry,
                        timeout=timeout_seconds,
                    )
                except requests.exceptions.Timeout:
                    _elapsed = time.monotonic() - _t0_anth_retry
                    LoggingService.get_instance().error(
                        f"AI request timeout: model={model}, timeout={timeout_seconds}s, "
                        f"elapsed={_elapsed:.1f}s, endpoint=anthropic-retry"
                    )
                    return AIResult(
                        success=False, text="",
                        error=f"Request timed out after {timeout_seconds}s",
                        usage=None, model=model,
                    )
                try:
                    response_data_retry = response.json() if response.content else {}
                    debug_response_retry = response_data_retry.copy()
                    if "content" in debug_response_retry:
                        for item in debug_response_retry.get("content", []):
                            if isinstance(item, dict) and "text" in item and len(item["text"]) > 200:
                                item["text"] = item["text"][:200] + "... (truncated)"
                    self._debug_console(
                        "Status (RETRY): " + str(response.status_code) + "\nResponse: " +
                        json.dumps(debug_response_retry, indent=2), "RECV")
                except Exception:
                    self._debug_console(
                        "Status (RETRY): " + str(response.status_code) +
                        "\nResponse: (non-JSON or error)", "RECV")
                if response.status_code != 200:
                    error_data_retry = response.json() if response.content else {}
                    error_message_retry = error_data_retry.get("error", {}).get(
                        "message", f"API error: {response.status_code}")
                    return AIResult(success=False, text="", error=error_message_retry,
                                    usage=None, model=model)
                # Retry succeeded — fall through to response parsing below.
            else:
                return AIResult(success=False, text="", error=error_message, usage=None, model=model)
        
        data = response.json()
        content_blocks = data.get("content", [])
        content = self.anthropic_message_text(data)

        stop_reason = data.get("stop_reason", "")
        block_types = tuple(
            b.get("type", "") for b in content_blocks if isinstance(b, dict)
        )

        # Extract token usage
        usage_data = data.get("usage")
        if usage_data:
            usage = TokenUsage(
                input_tokens=usage_data.get("input_tokens"),
                output_tokens=usage_data.get("output_tokens"),
                reasoning_tokens=None,  # Anthropic usage doesn't separate out thinking tokens
                reported=True,
            )
        else:
            usage = TokenUsage(input_tokens=None, output_tokens=None, reasoning_tokens=None, reported=False)

        if not content:
            if stop_reason == "max_tokens":
                return AIResult(
                    success=False, text="",
                    error=self.output_token_limit_message(
                        output_tokens=usage.output_tokens if usage else None,
                    ),
                    usage=usage, model=model,
                    stop_reason=stop_reason,
                    content_block_count=len(content_blocks),
                    content_block_types=block_types,
                )
            return AIResult(
                success=False, text="",
                error="Empty response from API",
                usage=usage, model=model,
                stop_reason=stop_reason,
                content_block_count=len(content_blocks),
                content_block_types=block_types,
            )

        if stop_reason == "max_tokens":
            content = content + (
                "\n\n[Response was cut off — the model reached the output token limit. "
                "Try increasing the Tokens limit in the narrative controls.]"
            )

        return AIResult(
            success=True, text=content, error=None, usage=usage, model=model,
            stop_reason=stop_reason,
            content_block_count=len(content_blocks),
            content_block_types=block_types,
        )
    
    @staticmethod
    def output_token_limit_message(
        output_tokens: Optional[int] = None,
        reasoning_tokens: Optional[int] = None,
    ) -> str:
        """User-facing message when the model hit max output tokens with no visible reply."""
        detail = ""
        if output_tokens is not None and reasoning_tokens is not None and reasoning_tokens > 0:
            detail = (
                f" Thinking/reasoning used {reasoning_tokens} of {output_tokens} output tokens."
            )
        elif output_tokens is not None:
            detail = f" The response used all {output_tokens} output tokens."
        return (
            "The model reached its output token limit before producing a reply"
            f" (thinking/reasoning may have used the full budget).{detail}"
            " Increase the max tokens setting, or choose a different model."
        )

    @staticmethod
    def anthropic_message_text(data: Dict[str, Any]) -> str:
        """Visible reply text, skipping thinking blocks that precede it on newer models."""
        parts = [
            block.get("text", "")
            for block in data.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(parts).strip()

    @staticmethod
    def parse_model_string(model_string: str) -> Tuple[str, str]:
        """Parse a model string with provider prefix.
        
        Args:
            model_string: Model string like "OpenAI: gpt-4" or "Anthropic: claude-3-5-sonnet".
            
        Returns:
            Tuple of (provider: str, model: str).
        """
        if ":" in model_string:
            parts = model_string.split(":", 1)
            provider_name = parts[0].strip().lower()
            model = parts[1].strip()
            
            if provider_name == "openai":
                return AIProvider.OPENAI, model
            elif provider_name == "anthropic":
                return AIProvider.ANTHROPIC, model
            elif provider_name == "custom":
                return AIProvider.CUSTOM, model
        
        # Default to OpenAI if no prefix
        return AIProvider.OPENAI, model_string

