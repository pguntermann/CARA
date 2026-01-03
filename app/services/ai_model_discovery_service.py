"""Service for discovering available AI models from providers."""

import json
import time
from typing import Dict, List, Optional, Any
from pathlib import Path
import requests


class AIModelDiscoveryService:
    """Service for discovering available AI models from OpenAI and Anthropic."""
    
    # Cache duration: 24 hours (in seconds)
    CACHE_DURATION = 24 * 60 * 60
    
    DEFAULT_FILTERS: Dict[str, Dict[str, List[str]]] = {
        "openai": {
            "exclude_prefixes": [
                "o1-pro-",
                "text-",
                "davinci",
                "curie",
                "babbage",
                "ada",
                "whisper",
                "tts-",
                "embedding",
                "moderation",
                "gpt-realtime",
                "gpt-image",
                "codex",
            ],
            "exclude_contains": [
                "audio",
                "realtime",
                "image",
                "vision",
                "codex",
            ],
            "exclude_exact": [],
        },
        "anthropic": {
            "exclude_prefixes": [],
            "exclude_contains": [],
            "exclude_exact": [],
        },
    }
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, cache_dir: Optional[Path] = None) -> None:
        """Initialize the AI model discovery service.
        
        Args:
            config: Application configuration dictionary.
            cache_dir: Directory for caching model lists. If None, uses app root.
        """
        self.config = config or {}
        if cache_dir is None:
            app_root = Path(__file__).parent.parent.parent
            cache_dir = app_root / ".cache"
        
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self._openai_cache_path = self.cache_dir / "openai_models.json"
        self._anthropic_cache_path = self.cache_dir / "anthropic_models.json"
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
            api_key: OpenAI API key. If None, uses cached data if available.
            
        Returns:
            List of model IDs (e.g., ["gpt-4", "gpt-3.5-turbo"]).
        """
        # Try to use cached data if no API key provided
        if api_key is None:
            cached = self._load_cache(self._openai_cache_path)
            if cached:
                return cached.get("models", [])
            return []
        
        # Try to fetch from API
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
            
            # Cache the results
            self._save_cache(self._openai_cache_path, models)
            
            return models
        except Exception as e:
            # If API call fails, try to use cached data
            cached = self._load_cache(self._openai_cache_path)
            if cached:
                return cached.get("models", [])
            return []
    
    def get_anthropic_models(self, api_key: Optional[str] = None) -> List[str]:
        """Get list of available Anthropic models.
        
        Args:
            api_key: Anthropic API key. If None, uses cached data if available.
            
        Returns:
            List of model IDs (e.g., ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"]).
        """
        # Try to use cached data if no API key provided
        if api_key is None:
            cached = self._load_cache(self._anthropic_cache_path)
            if cached:
                return cached.get("models", [])
            return []
        
        # Try to fetch from API
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
            
            # Cache the results
            self._save_cache(self._anthropic_cache_path, models)
            
            return models
        except Exception as e:
            # If API call fails, try to use cached data
            cached = self._load_cache(self._anthropic_cache_path)
            if cached:
                return cached.get("models", [])
            return []
    
    def _load_cache(self, cache_path: Path) -> Optional[Dict[str, Any]]:
        """Load cached model list.
        
        Args:
            cache_path: Path to cache file.
            
        Returns:
            Cached data if valid, None otherwise.
        """
        if not cache_path.exists():
            return None
        
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Check if cache is still valid
            timestamp = data.get("timestamp", 0)
            if time.time() - timestamp > self.CACHE_DURATION:
                return None
            
            return data
        except Exception:
            return None
    
    def _save_cache(self, cache_path: Path, models: List[str]) -> None:
        """Save model list to cache.
        
        Args:
            cache_path: Path to cache file.
            models: List of model IDs.
        """
        try:
            data = {
                "timestamp": time.time(),
                "models": models
            }
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # Ignore cache write errors
    
    def clear_cache(self, provider: Optional[str] = None) -> None:
        """Clear cached model lists.
        
        Args:
            provider: Provider name ("openai" or "anthropic"). If None, clears both.
        """
        if provider is None or provider == "openai":
            if self._openai_cache_path.exists():
                try:
                    self._openai_cache_path.unlink()
                except Exception:
                    pass
        
        if provider is None or provider == "anthropic":
            if self._anthropic_cache_path.exists():
                try:
                    self._anthropic_cache_path.unlink()
                except Exception:
                    pass

    def _load_filter_config(self) -> Dict[str, Dict[str, List[str]]]:
        """Load provider-specific filter configuration from config."""
        filters: Dict[str, Dict[str, List[str]]] = {}
        ai_config = self.config.get("ai", {})
        model_filters = ai_config.get("model_filters", {})
        
        for provider, defaults in self.DEFAULT_FILTERS.items():
            provider_config = model_filters.get(provider, {})
            filters[provider] = {
                "exclude_prefixes": list(provider_config.get("exclude_prefixes", defaults.get("exclude_prefixes", []))),
                "exclude_contains": list(provider_config.get("exclude_contains", defaults.get("exclude_contains", []))),
                "exclude_exact": list(provider_config.get("exclude_exact", defaults.get("exclude_exact", []))),
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

