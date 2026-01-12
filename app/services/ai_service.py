"""Service for interacting with AI models (OpenAI and Anthropic)."""

import json
import requests
import threading
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


class AIProvider(str, Enum):
    """AI provider types."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class AIService:
    """Service for making API calls to AI providers."""
    
    # Cache for models that require max_completion_tokens instead of max_tokens
    # This is a class-level cache so it persists across all instances
    _models_requiring_max_completion_tokens: set = set()
    
    # Cache for models that don't support temperature parameter (or only support default)
    # This is a class-level cache so it persists across all instances
    _models_not_supporting_temperature: set = set()
    
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
        token_limit: Optional[int] = None
    ) -> Tuple[bool, str]:
        """Send a message to an AI provider and get response.
        
        Args:
            provider: Provider name ("openai" or "anthropic").
            model: Model ID (e.g., "gpt-4", "claude-3-5-sonnet-20241022").
            api_key: API key for the provider.
            messages: List of message dicts with "role" and "content" keys.
            system_prompt: Optional system prompt (for OpenAI, included in messages; for Anthropic, separate).
            
        Returns:
            Tuple of (success: bool, response_text: str or error_message: str).
        """
        try:
            if provider == AIProvider.OPENAI:
                return self._send_openai_message(model, api_key, messages, system_prompt, token_limit)
            elif provider == AIProvider.ANTHROPIC:
                return self._send_anthropic_message(model, api_key, messages, system_prompt)
            else:
                return False, f"Unknown provider: {provider}"
        except Exception as e:
            return False, str(e)
    
    def _send_openai_message(
        self,
        model: str,
        api_key: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        token_limit: Optional[int] = None
    ) -> Tuple[bool, str]:
        """Send message to OpenAI API.
        
        Args:
            model: Model ID.
            api_key: OpenAI API key.
            messages: List of message dicts.
            system_prompt: Optional system prompt.
            
        Returns:
            Tuple of (success: bool, response_text: str or error_message: str).
        """
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
        debug_message = ("POST " + str(self.OPENAI_CHAT_URL) + "\nHeaders: " + 
                        json.dumps(debug_headers, indent=2) + "\nPayload: " + 
                        json.dumps(debug_payload, indent=2))
        self._debug_console(debug_message, "SEND")
        
        response = requests.post(
            self.OPENAI_CHAT_URL,
            headers=headers,
            json=payload,
            timeout=60
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
            error_data = response.json() if response.content else {}
            error_message = error_data.get("error", {}).get("message", f"API error: {response.status_code}")
            
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
                debug_message_retry = ("POST (RETRY) " + str(self.OPENAI_CHAT_URL) + "\nPayload: " + 
                                      json.dumps(debug_payload_retry, indent=2))
                self._debug_console(debug_message_retry, "SEND")
                
                # Retry request
                response = requests.post(
                    self.OPENAI_CHAT_URL,
                    headers=headers,
                    json=payload_retry,
                    timeout=60
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
                    error_data_retry = response.json() if response.content else {}
                    error_message_retry = error_data_retry.get("error", {}).get("message", f"API error: {response.status_code}")
                    return False, error_message_retry
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
                debug_message_retry = ("POST (RETRY) " + str(self.OPENAI_CHAT_URL) + "\nPayload: " + 
                                      json.dumps(debug_payload_retry, indent=2))
                self._debug_console(debug_message_retry, "SEND")
                
                # Retry request
                response = requests.post(
                    self.OPENAI_CHAT_URL,
                    headers=headers,
                    json=payload_retry,
                    timeout=60
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
                    error_data_retry = response.json() if response.content else {}
                    error_message_retry = error_data_retry.get("error", {}).get("message", f"API error: {response.status_code}")
                    return False, error_message_retry
                # Otherwise, continue processing the successful retry response below (fall through to normal processing)
            
            # Provide helpful error messages for other common issues
            elif "not supported in the v1/chat/completions" in error_message or "not in v1/chat/completions" in error_message:
                if "o3-" in model:
                    return False, (
                        f"Model {model} requires the v1/responses endpoint, which is not currently supported. "
                        "Please select a different model (e.g., gpt-4, gpt-3.5-turbo, or o1 models)."
                    )
                else:
                    return False, (
                        f"Model {model} is not compatible with the chat completions endpoint. "
                        "This model may require a different API endpoint. Please select a different model."
                    )
            else:
                # Other errors - return the error message
                return False, error_message
        
        try:
            data = response.json()
            
            # Extract content from response
            # Structure: {"choices": [{"message": {"content": "..."}}]}
            choices = data.get("choices", [])
            if not choices:
                # Log the full response for debugging
                return False, f"Empty choices in API response: {data}"
            
            choice = choices[0]
            message = choice.get("message", {})
            content = message.get("content", "")
            finish_reason = choice.get("finish_reason", "")
            
            # Check if response was truncated due to token limit
            if finish_reason == "length" and not content:
                usage = data.get("usage", {})
                completion_tokens = usage.get("completion_tokens", 0)
                completion_details = usage.get("completion_tokens_details", {})
                reasoning_tokens = completion_details.get("reasoning_tokens", 0)
                
                return False, (
                    f"Response was truncated - model used all {completion_tokens} tokens for reasoning "
                    f"({reasoning_tokens} reasoning tokens) and reached the token limit before generating output. "
                    f"Try asking a simpler question or the model may need more tokens allocated."
                )
            
            if not content:
                # Log the full response for debugging
                return False, f"Empty content in API response. Finish reason: {finish_reason}. Full response: {data}"
            
            return True, content
        except Exception as e:
            return False, f"Error parsing API response: {str(e)}"
    
    def _send_anthropic_message(
        self,
        model: str,
        api_key: str,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Send message to Anthropic API.
        
        Args:
            model: Model ID.
            api_key: Anthropic API key.
            messages: List of message dicts.
            system_prompt: Optional system prompt.
            
        Returns:
            Tuple of (success: bool, response_text: str or error_message: str).
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
        
        payload = {
            "model": model,
            "max_tokens": 2000,
            "messages": anthropic_messages
        }
        
        # Add system prompt if provided
        if system_prompt:
            payload["system"] = system_prompt
        
        # Debug outbound: log request payload (hide API key)
        debug_payload = payload.copy()
        debug_headers = {k: ("***" if k == "x-api-key" else v) for k, v in headers.items()}
        debug_message = ("POST " + str(self.ANTHROPIC_MESSAGES_URL) + "\nHeaders: " + 
                        json.dumps(debug_headers, indent=2) + "\nPayload: " + 
                        json.dumps(debug_payload, indent=2))
        self._debug_console(debug_message, "SEND")
        
        response = requests.post(
            self.ANTHROPIC_MESSAGES_URL,
            headers=headers,
            json=payload,
            timeout=60
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
            return False, error_message
        
        data = response.json()
        content = data.get("content", [{}])[0].get("text", "")
        
        if not content:
            return False, "Empty response from API"
        
        return True, content
    
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
        
        # Default to OpenAI if no prefix
        return AIProvider.OPENAI, model_string

