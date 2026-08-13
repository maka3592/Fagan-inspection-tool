"""OpenAI provider implementation."""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from openai import OpenAI, BadRequestError

from .base import LLMProvider
from ..utils.usage_logging import compute_costs, extract_usage

logger = logging.getLogger(__name__)


# JSON Schema for Reviewer Output - used for Structured Outputs
REVIEWER_OUTPUT_SCHEMA = {
    "name": "reviewer_output",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "defects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "position": {
                            "type": "string",
                            "description": "Section/table/use case/page reference"
                        },
                        "page_hint": {
                            "type": "string",
                            "description": "Page number if applicable"
                        },
                        "risk": {
                            "type": "string",
                            "enum": ["A", "B", "C", "UNK"],
                            "description": "Risk level: A=High, B=Medium, C=Low, UNK=Unknown"
                        },
                        "fault_type": {
                            "type": "string",
                            "enum": ["M", "W", "UNK"],
                            "description": "Fault type: M=Missing, W=Wrong, UNK=Unknown"
                        },
                        "description": {
                            "type": "string",
                            "description": "Clear description of the defect"
                        },
                        "evidence": {
                            "type": "string",
                            "description": "Quote or paraphrase with page/section reference"
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence score 0.0-1.0"
                        },
                        "flags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional flags like 'uncertain', 'needs_clarification'"
                        }
                    },
                    "required": ["position", "page_hint", "risk", "fault_type",
                                 "description", "evidence", "confidence", "flags"],
                    "additionalProperties": False
                }
            },
            "notes": {
                "type": "string",
                "description": "Additional observations or comments"
            }
        },
        "required": ["defects", "notes"],
        "additionalProperties": False
    }
}

# JSON Schema for Scribe/Meeting Output
SCRIBE_OUTPUT_SCHEMA = {
    "name": "scribe_output",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "consolidated_defects": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "position": {"type": "string"},
                        "page_hint": {"type": "string"},
                        "risk": {"type": "string", "enum": ["A", "B", "C", "UNK"]},
                        "fault_type": {"type": "string", "enum": ["M", "W", "UNK"]},
                        "description": {"type": "string"},
                        "evidence": {"type": "string"},
                        "confidence": {"type": "number"},
                        "flags": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["position", "page_hint", "risk", "fault_type",
                                 "description", "evidence", "confidence", "flags"],
                    "additionalProperties": False
                }
            },
            "duplicates_removed": {"type": "integer"},
            "conflicts_flagged": {"type": "integer"},
            "minutes": {"type": "string"},
            "exit_decision": {"type": "string"}
        },
        "required": ["consolidated_defects", "duplicates_removed",
                     "conflicts_flagged", "minutes", "exit_decision"],
        "additionalProperties": False
    }
}

# Models that do not support sampling parameters (temperature, top_p, etc.)
# These models only support default values and will error on custom values.
RESTRICTED_SAMPLING_MODELS: Set[str] = {
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5",
}


def _is_restricted_sampling_model(model: str) -> bool:
    """Check if model restricts sampling parameters.

    Restricted models (e.g., gpt-5-mini, gpt-5-nano):
    - Do NOT support custom temperature (only default=1)
    - Do NOT support top_p, logprobs, presence_penalty, frequency_penalty

    Returns:
        True if model is restricted, False otherwise.
    """
    model_lower = model.lower()
    # Check exact matches and prefix matches
    if model_lower in RESTRICTED_SAMPLING_MODELS:
        return True
    # Also match versioned variants like gpt-5-mini-2024-01-01
    for restricted in RESTRICTED_SAMPLING_MODELS:
        if model_lower.startswith(restricted):
            return True
    return False


class OpenAIProvider(LLMProvider):
    """Provider for OpenAI models."""

    # Retry config for truncated/empty responses
    MAX_RETRIES = 1
    RETRY_TOKEN_MULTIPLIER = 2

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        api_key: Optional[str] = None,
        **kwargs,
    ):
        """Initialize OpenAI provider.

        Args:
            model: OpenAI model identifier (default: gpt-4o-mini for stability)
            temperature: Sampling temperature (ignored for restricted models)
            max_tokens: Maximum tokens to generate (mapped to max_completion_tokens)
            api_key: API key (if not provided, reads from OPENAI_API_KEY env var)
            **kwargs: Additional parameters (top_p, presence_penalty, etc.)
        """
        super().__init__(model, temperature, max_tokens, **kwargs)
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        self.client = OpenAI(api_key=api_key)

        # Log warning if restricted model has non-default sampling params
        self._warn_if_params_ignored()

    def _warn_if_params_ignored(self) -> None:
        """Log warning if sampling parameters will be ignored for restricted models."""
        if not _is_restricted_sampling_model(self.model):
            return

        ignored_params = []

        # Check temperature (default is typically 1.0 for these models)
        if self.temperature != 1.0:
            ignored_params.append(f"temperature={self.temperature}")

        # Check extra params that would be ignored
        sampling_params = ["top_p", "logprobs", "presence_penalty", "frequency_penalty"]
        for param in sampling_params:
            if self.extra_params.get(param) is not None:
                ignored_params.append(f"{param}={self.extra_params[param]}")

        if ignored_params:
            logger.warning(
                f"Model '{self.model}' does not support custom sampling parameters. "
                f"Ignoring: {', '.join(ignored_params)}. "
                f"Only default values are supported for this model."
            )

    def _build_request_kwargs(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
        max_tokens_override: Optional[int] = None,
    ) -> Dict:
        """Build request kwargs with correct parameters for model.

        Parameter mapping:
        - Config uses 'max_tokens' for simplicity
        - API call uses 'max_completion_tokens' (modern OpenAI API)

        Restricted models (gpt-5-mini, gpt-5-nano, gpt-5):
        - Do NOT include temperature, top_p, or other sampling params

        Other models (gpt-4o, gpt-4o-mini, etc.):
        - Include temperature and other sampling params if specified

        Args:
            messages: List of message dicts
            response_format: Optional response format for structured output
            max_tokens_override: Optional override for max_completion_tokens (for retries)
        """
        effective_max_tokens = max_tokens_override or self.max_tokens

        kwargs = {
            "model": self.model,
            "messages": messages,
            # Always use max_completion_tokens for OpenAI API
            # Config 'max_tokens' is mapped to this parameter
            "max_completion_tokens": effective_max_tokens,
        }

        if _is_restricted_sampling_model(self.model):
            # Restricted models: do NOT send any sampling parameters
            # The model only accepts default values
            pass
        else:
            # Non-restricted models: include sampling parameters
            kwargs["temperature"] = self.temperature

            # Add optional sampling params if specified
            if self.extra_params.get("top_p") is not None:
                kwargs["top_p"] = self.extra_params["top_p"]
            if self.extra_params.get("presence_penalty") is not None:
                kwargs["presence_penalty"] = self.extra_params["presence_penalty"]
            if self.extra_params.get("frequency_penalty") is not None:
                kwargs["frequency_penalty"] = self.extra_params["frequency_penalty"]

        # Add response_format if specified (for structured JSON output)
        if response_format is not None:
            kwargs["response_format"] = response_format

        return kwargs

    def generate(
        self,
        messages: List[Dict[str, str]],
        system: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate completion using OpenAI API.

        Includes automatic retry with increased token limit for truncated responses.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system: Optional system prompt
            response_format: Optional response format for structured output.
                             Use {"type": "json_object"} for JSON mode, or
                             {"type": "json_schema", "json_schema": {...}} for strict schema.

        Returns:
            Generated text response

        Raises:
            BadRequestError: If API rejects request (with helpful hint for token param issues)
            ValueError: If response is empty or refused after retries
        """
        # Prepend system message if provided
        if system:
            messages = [{"role": "system", "content": system}] + messages

        return self._generate_with_retry(messages, response_format)

    def _generate_with_retry(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
        current_max_tokens: Optional[int] = None,
    ) -> str:
        """Internal generate method with retry logic for truncated/empty responses.

        Args:
            messages: Prepared messages (system already prepended)
            response_format: Response format
            retry_count: Current retry attempt
            current_max_tokens: Override max_tokens for this attempt

        Returns:
            Generated text response
        """
        max_tokens = current_max_tokens or self.max_tokens
        kwargs = self._build_request_kwargs(messages, response_format, max_tokens_override=max_tokens)

        try:
            response = self._create_with_usage_logging(kwargs)
            choice = response.choices[0]
            finish_reason = choice.finish_reason

            # Check for refusal first
            message = choice.message
            refusal = getattr(message, 'refusal', None)
            if refusal is not None and isinstance(refusal, str) and refusal.strip():
                logger.error(f"Model refused to respond: {refusal}")
                raise ValueError(f"Model refused to respond: {refusal}")

            # Check for content filter
            if finish_reason == "content_filter":
                logger.error("Response blocked by content filter")
                raise ValueError("Response blocked by OpenAI content filter")

            content = message.content

            # Handle truncation - retry with larger token limit
            if finish_reason == "length":
                if retry_count < self.MAX_RETRIES:
                    new_max_tokens = max_tokens * self.RETRY_TOKEN_MULTIPLIER
                    logger.warning(
                        f"Response truncated (finish_reason=length). "
                        f"Retrying with max_tokens={new_max_tokens} (attempt {retry_count + 1}/{self.MAX_RETRIES})"
                    )
                    return self._generate_with_retry(
                        messages, response_format,
                        retry_count=retry_count + 1,
                        current_max_tokens=new_max_tokens
                    )
                else:
                    logger.error(
                        f"Response still truncated after {self.MAX_RETRIES} retries. "
                        f"Final max_tokens={max_tokens}. Consider increasing base max_tokens in config."
                    )
                    # Return truncated content with marker
                    if content:
                        return content + '\n[TRUNCATED - incomplete output]'
                    raise ValueError(f"Response truncated after {self.MAX_RETRIES} retries")

            # Handle empty response - retry once
            if content is None or content.strip() == "":
                if retry_count < self.MAX_RETRIES:
                    logger.warning(
                        f"Empty response from model '{self.model}'. "
                        f"Retrying (attempt {retry_count + 1}/{self.MAX_RETRIES})"
                    )
                    return self._generate_with_retry(
                        messages, response_format,
                        retry_count=retry_count + 1,
                        current_max_tokens=max_tokens
                    )
                else:
                    logger.error(
                        f"Empty response after {self.MAX_RETRIES} retries. "
                        f"finish_reason={finish_reason}, usage={response.usage}"
                    )
                    # Return marker JSON for structured output mode
                    if response_format and response_format.get("type") in ("json_object", "json_schema"):
                        return '{"defects": [], "notes": "[INCOMPLETE] Empty response from model after retries", "_incomplete": true}'
                    raise ValueError(f"Empty response from model after {self.MAX_RETRIES} retries")

            return content

        except BadRequestError as e:
            error_msg = str(e)
            if "max_tokens" in error_msg or "max_completion_tokens" in error_msg:
                raise BadRequestError(
                    message=(
                        f"{error_msg}\n"
                        f"Hint: Model '{self.model}' may require different token parameter. "
                        f"The provider maps max_tokens to max_completion_tokens automatically."
                    ),
                    response=e.response,
                    body=e.body,
                ) from e
            logger.error(f"OpenAI BadRequestError: {error_msg}")
            raise

    def _create_with_usage_logging(self, kwargs: Dict[str, Any]):
        """Führt den Chat-Completions-Call aus und loggt – falls ein
        UsageLogger angehängt ist – Token-Usage, Laufzeit und Kosten.

        Ohne angehängten Logger ist dies ein reiner Pass-through (Verhalten
        und Rückgabe identisch zum direkten API-Call). Robust: fehlende
        Usage führt nicht zum Absturz; Fehler werden geloggt und
        weitergereicht.
        """
        if self.usage_logger is None:
            return self.client.chat.completions.create(**kwargs)

        call_id = uuid.uuid4().hex[:12]
        start = datetime.now(timezone.utc)
        response = None
        error_msg = ""
        try:
            response = self.client.chat.completions.create(**kwargs)
            return response
        except Exception as exc:  # Fehler erfassen, dann weiterreichen
            error_msg = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            end = datetime.now(timezone.utc)
            duration = (end - start).total_seconds()
            input_tokens, output_tokens, total_tokens, available = (
                extract_usage(response) if response is not None else (None, None, None, False)
            )
            input_cost, output_cost, total_cost = (
                compute_costs(input_tokens, output_tokens, self.cost_config)
                if available else (None, None, None)
            )
            try:
                self.usage_logger.record({
                    "call_id": call_id,
                    "model": self.model,
                    "start_time_utc": start.isoformat(),
                    "end_time_utc": end.isoformat(),
                    "duration_seconds": round(duration, 6),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    "input_cost": input_cost,
                    "output_cost": output_cost,
                    "total_cost": total_cost,
                    "usage_available": "true" if available else "false",
                    "error": error_msg,
                })
            except Exception as log_exc:  # Logging darf den Call nie brechen
                logger.warning(f"Usage-Logging fehlgeschlagen: {log_exc}")

    def get_provider_name(self) -> str:
        """Get provider name."""
        return "openai"
