"""Base LLM provider interface."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        **kwargs,
    ):
        """Initialize provider.

        Args:
            model: Model identifier
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific parameters
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.extra_params = kwargs

    @abstractmethod
    def generate(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate completion from messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system: Optional system prompt
            response_format: Optional response format specification for structured output.
                             For OpenAI: {"type": "json_object"} or {"type": "json_schema", ...}

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Get provider name for logging."""
        pass
