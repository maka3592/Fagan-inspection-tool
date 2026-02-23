"""Factory for creating LLM providers."""

from typing import Optional

from ..core.schemas import LLMParams
from .anthropic_provider import AnthropicProvider
from .base import LLMProvider
from .openai_provider import OpenAIProvider


def get_provider(params: LLMParams, api_key: Optional[str] = None) -> LLMProvider:
    """Get LLM provider instance based on parameters.

    Args:
        params: LLM parameters including provider type
        api_key: Optional API key (otherwise uses environment variable)

    Returns:
        Configured LLM provider instance

    Raises:
        ValueError: If provider is not supported
    """
    provider_map = {
        "anthropic": AnthropicProvider,
        "openai": OpenAIProvider,
    }

    provider_class = provider_map.get(params.provider.lower())
    if not provider_class:
        raise ValueError(
            f"Unsupported provider: {params.provider}. "
            f"Supported: {', '.join(provider_map.keys())}"
        )

    kwargs = {
        "model": params.model,
        "temperature": params.temperature,
        "max_tokens": params.max_tokens,
    }

    if api_key:
        kwargs["api_key"] = api_key

    if params.top_p:
        kwargs["top_p"] = params.top_p

    # Add any extra params
    kwargs.update(params.extra)

    return provider_class(**kwargs)
