"""Anthropic (Claude) provider implementation."""

import os
from typing import Any, Dict, List, Optional

from anthropic import Anthropic

from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    """Provider for Anthropic Claude models."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-5-20250929",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        api_key: Optional[str] = None,
        **kwargs,
    ):
        """Initialize Anthropic provider.

        Args:
            model: Claude model identifier
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            api_key: API key (if not provided, reads from ANTHROPIC_API_KEY env var)
            **kwargs: Additional parameters
        """
        super().__init__(model, temperature, max_tokens, **kwargs)
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        self.client = Anthropic(api_key=api_key)

    def generate(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate completion using Claude API.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system: Optional system prompt
            response_format: Optional response format (ignored for Anthropic, but accepted
                             for API compatibility with OpenAI provider)

        Returns:
            Generated text response
        """
        # Note: response_format is ignored for Anthropic - Claude follows JSON
        # instructions in prompts without explicit API-level enforcement
        kwargs = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system

        # Add extra params if any
        if self.extra_params.get("top_p"):
            kwargs["top_p"] = self.extra_params["top_p"]

        response = self.client.messages.create(**kwargs)
        return response.content[0].text

    def get_provider_name(self) -> str:
        """Get provider name."""
        return "anthropic"
