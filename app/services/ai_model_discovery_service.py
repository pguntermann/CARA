"""Service for discovering available AI models from providers."""

from typing import Dict, List, Optional, Any
import requests


class AIModelDiscoveryService:
    """Service for discovering available AI models from OpenAI and Anthropic."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the AI model discovery service.
        
        Args:
            config: Application configuration dictionary.
        """
        self.config = config or {}
        self._filters = self._load_filter_config()
        
        # Load API endpoints from config
        ai_config = self.config.get("ai", {}).get("api_endpoints", {})
        openai_config = ai_config.get("openai", {})
        anthropic_config = ai_config.get("anthropic", {})
        
        # Use config values or fall back to defaults
        self.OPENAI_MODELS_URL = openai_config.get("models", "https://api.openai.com/v1/models")
        self.ANTHROPIC_MODELS_URL = anthropic_config.get("models", "https://api.anthropic.com/v1/models")
    
    def get_openai_models(self, api_key: Optional[str] = None) -> List[str]:
        """Get list of available OpenAI models.
        
        Args:
            api_key: OpenAI API key. Required for API calls.
            
        Returns:
            List of model IDs (e.g., ["gpt-4", "gpt-3.5-turbo"]).
        """
        if not api_key:
            return []
        
        # Fetch from API
        try:
            headers = {
                "Authorization": f"Bearer {api_key}"
            }
            response = requests.get(self.OPENAI_MODELS_URL, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            models = []
            
            # Extract model IDs, filtering for chat models that support v1/chat/completions
            for item in data.get("data", []):
                model_id = item.get("id", "")
                if not model_id:
                    continue
                
                if self._should_exclude_model(model_id, "openai"):
                    continue
                
                models.append(model_id)
            
            # Sort models (prefer newer models first)
            models.sort(reverse=True)
            
            return models
        except Exception:
            return []
    
    def get_anthropic_models(self, api_key: Optional[str] = None) -> List[str]:
        """Get list of available Anthropic models.
        
        Args:
            api_key: Anthropic API key. Required for API calls.
            
        Returns:
            List of model IDs (e.g., ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"]).
        """
        if not api_key:
            return []
        
        # Fetch from API
        try:
            headers = {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            }
            response = requests.get(self.ANTHROPIC_MODELS_URL, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            models = []
            
            for item in data.get("data", []):
                model_id = item.get("id", "")
                if not model_id:
                    continue
                
                if self._should_exclude_model(model_id, "anthropic"):
                    continue
                
                models.append(model_id)
            
            # Sort models (prefer newer models first)
            models.sort(reverse=True)
            
            return models
        except Exception:
            return []
    
    def _load_filter_config(self) -> Dict[str, Dict[str, List[str]]]:
        """Load provider-specific filter configuration from config.json.
        
        Returns:
            Dictionary mapping provider names to filter dictionaries.
            Each filter dictionary contains 'exclude_prefixes', 'exclude_contains', and 'exclude_exact' lists.
            Returns empty lists if filters are not configured in config.json.
        """
        filters: Dict[str, Dict[str, List[str]]] = {}
        ai_config = self.config.get("ai", {})
        model_filters = ai_config.get("model_filters", {})
        
        # Load filters for each provider from config.json
        for provider in ["openai", "anthropic"]:
            provider_config = model_filters.get(provider, {})
            filters[provider] = {
                "exclude_prefixes": list(provider_config.get("exclude_prefixes", [])),
                "exclude_contains": list(provider_config.get("exclude_contains", [])),
                "exclude_exact": list(provider_config.get("exclude_exact", [])),
            }
        
        return filters
    
    def _should_exclude_model(self, model_id: str, provider: str) -> bool:
        """Return True if the model should be filtered out for the provider."""
        provider_filters = self._filters.get(provider, {})
        prefixes = provider_filters.get("exclude_prefixes", [])
        contains = provider_filters.get("exclude_contains", [])
        exact = provider_filters.get("exclude_exact", [])
        
        if model_id in exact:
            return True
        
        for prefix in prefixes:
            if prefix and model_id.startswith(prefix):
                return True
        
        lower_model = model_id.lower()
        for keyword in contains:
            if keyword and keyword.lower() in lower_model:
                return True
        
        return False

