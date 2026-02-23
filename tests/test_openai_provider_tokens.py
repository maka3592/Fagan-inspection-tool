"""Tests for OpenAI provider parameter handling.

Tests verify:
1. All models use max_completion_tokens (mapped from config's max_tokens)
2. Restricted models (gpt-5-mini, gpt-5-nano, gpt-5) omit sampling params
3. Non-restricted models include temperature and other sampling params
4. Warning is logged when sampling params are ignored for restricted models
"""

import logging
import pytest
from unittest.mock import MagicMock, patch

from src.fagan_tool.providers.openai_provider import (
    OpenAIProvider,
    _is_restricted_sampling_model,
    RESTRICTED_SAMPLING_MODELS,
)


class TestRestrictedModelDetection:
    """Test _is_restricted_sampling_model helper function."""

    def test_gpt5_mini_is_restricted(self):
        """gpt-5-mini should be detected as restricted."""
        assert _is_restricted_sampling_model("gpt-5-mini") is True

    def test_gpt5_nano_is_restricted(self):
        """gpt-5-nano should be detected as restricted."""
        assert _is_restricted_sampling_model("gpt-5-nano") is True

    def test_gpt5_is_restricted(self):
        """gpt-5 should be detected as restricted."""
        assert _is_restricted_sampling_model("gpt-5") is True

    def test_gpt5_mini_versioned_is_restricted(self):
        """Versioned gpt-5-mini should be detected as restricted."""
        assert _is_restricted_sampling_model("gpt-5-mini-2024-01-01") is True

    def test_gpt4o_mini_not_restricted(self):
        """gpt-4o-mini should NOT be restricted."""
        assert _is_restricted_sampling_model("gpt-4o-mini") is False

    def test_gpt4o_not_restricted(self):
        """gpt-4o should NOT be restricted."""
        assert _is_restricted_sampling_model("gpt-4o") is False

    def test_gpt4_not_restricted(self):
        """gpt-4 should NOT be restricted."""
        assert _is_restricted_sampling_model("gpt-4") is False

    def test_gpt35_not_restricted(self):
        """gpt-3.5-turbo should NOT be restricted."""
        assert _is_restricted_sampling_model("gpt-3.5-turbo") is False


class TestOpenAIProviderPayload:
    """Test that OpenAIProvider builds correct request payload."""

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_gpt5mini_payload_no_temperature(self):
        """GPT-5-mini payload should NOT contain temperature."""
        provider = OpenAIProvider(model="gpt-5-mini", temperature=0.2, max_tokens=4096)

        messages = [{"role": "user", "content": "test"}]
        kwargs = provider._build_request_kwargs(messages)

        assert "temperature" not in kwargs
        assert "top_p" not in kwargs

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_gpt5mini_payload_has_max_completion_tokens(self):
        """GPT-5-mini payload should contain max_completion_tokens."""
        provider = OpenAIProvider(model="gpt-5-mini", max_tokens=4096)

        messages = [{"role": "user", "content": "test"}]
        kwargs = provider._build_request_kwargs(messages)

        assert "max_completion_tokens" in kwargs
        assert kwargs["max_completion_tokens"] == 4096
        assert "max_tokens" not in kwargs

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_gpt4o_mini_payload_keeps_temperature(self):
        """GPT-4o-mini payload should contain temperature."""
        provider = OpenAIProvider(model="gpt-4o-mini", temperature=0.5, max_tokens=4096)

        messages = [{"role": "user", "content": "test"}]
        kwargs = provider._build_request_kwargs(messages)

        assert "temperature" in kwargs
        assert kwargs["temperature"] == 0.5

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_gpt4o_mini_payload_has_max_completion_tokens(self):
        """GPT-4o-mini payload should also use max_completion_tokens."""
        provider = OpenAIProvider(model="gpt-4o-mini", max_tokens=4096)

        messages = [{"role": "user", "content": "test"}]
        kwargs = provider._build_request_kwargs(messages)

        assert "max_completion_tokens" in kwargs
        assert kwargs["max_completion_tokens"] == 4096
        assert "max_tokens" not in kwargs

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_gpt4o_mini_payload_includes_top_p(self):
        """GPT-4o-mini should include top_p when specified."""
        provider = OpenAIProvider(model="gpt-4o-mini", top_p=0.9)

        messages = [{"role": "user", "content": "test"}]
        kwargs = provider._build_request_kwargs(messages)

        assert kwargs.get("top_p") == 0.9

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_gpt5_nano_omits_sampling_params(self):
        """GPT-5-nano should omit all sampling params."""
        provider = OpenAIProvider(
            model="gpt-5-nano",
            temperature=0.7,
            top_p=0.9,
            presence_penalty=0.5,
        )

        messages = [{"role": "user", "content": "test"}]
        kwargs = provider._build_request_kwargs(messages)

        assert "temperature" not in kwargs
        assert "top_p" not in kwargs
        assert "presence_penalty" not in kwargs


class TestOpenAIProviderWarnings:
    """Test that warnings are logged for ignored parameters."""

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_warning_on_ignored_temperature(self, caplog):
        """Warning should be logged when temperature is ignored for restricted model."""
        with caplog.at_level(logging.WARNING):
            OpenAIProvider(model="gpt-5-mini", temperature=0.2)

        assert "does not support custom sampling parameters" in caplog.text
        assert "temperature=0.2" in caplog.text

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_warning_on_ignored_top_p(self, caplog):
        """Warning should be logged when top_p is ignored for restricted model."""
        with caplog.at_level(logging.WARNING):
            OpenAIProvider(model="gpt-5-mini", top_p=0.9)

        assert "does not support custom sampling parameters" in caplog.text
        assert "top_p=0.9" in caplog.text

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_no_warning_for_default_temperature(self, caplog):
        """No warning when temperature=1.0 (default) for restricted model."""
        with caplog.at_level(logging.WARNING):
            OpenAIProvider(model="gpt-5-mini", temperature=1.0)

        assert "does not support custom sampling parameters" not in caplog.text

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_no_warning_for_non_restricted_model(self, caplog):
        """No warning for non-restricted models regardless of params."""
        with caplog.at_level(logging.WARNING):
            OpenAIProvider(model="gpt-4o-mini", temperature=0.2)

        assert "does not support custom sampling parameters" not in caplog.text


class TestOpenAIProviderGenerate:
    """Test generate method with mocked OpenAI client."""

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_generate_gpt5mini_sends_correct_params(self, mock_openai_class):
        """Generate with gpt-5-mini should use max_completion_tokens, omit temperature."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="response"))]
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAIProvider(model="gpt-5-mini", max_tokens=4096, temperature=0.2)
        result = provider.generate([{"role": "user", "content": "hello"}])

        assert result == "response"
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert "max_completion_tokens" in call_kwargs
        assert call_kwargs["max_completion_tokens"] == 4096
        assert "max_tokens" not in call_kwargs
        assert "temperature" not in call_kwargs

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_generate_gpt4o_mini_sends_correct_params(self, mock_openai_class):
        """Generate with gpt-4o-mini should use max_completion_tokens and temperature."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="response"))]
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAIProvider(model="gpt-4o-mini", max_tokens=4096, temperature=0.2)
        result = provider.generate([{"role": "user", "content": "hello"}])

        assert result == "response"
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert "max_completion_tokens" in call_kwargs
        assert call_kwargs["max_completion_tokens"] == 4096
        assert "max_tokens" not in call_kwargs
        assert call_kwargs["temperature"] == 0.2

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_generate_with_system_prompt(self, mock_openai_class):
        """System prompt should be prepended to messages."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="response"))]
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAIProvider(model="gpt-5-mini")
        provider.generate(
            [{"role": "user", "content": "hello"}],
            system="You are helpful."
        )

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        messages = call_kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[0]["content"] == "You are helpful."
        assert messages[1]["role"] == "user"

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_generate_with_response_format(self, mock_openai_class):
        """response_format should be passed to API call."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"key": "value"}'))]
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAIProvider(model="gpt-5-mini")
        provider.generate(
            [{"role": "user", "content": "Return JSON"}],
            response_format={"type": "json_object"}
        )

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert "response_format" in call_kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_payload_includes_response_format(self):
        """_build_request_kwargs should include response_format when specified."""
        provider = OpenAIProvider(model="gpt-5-mini")

        messages = [{"role": "user", "content": "test"}]
        kwargs = provider._build_request_kwargs(
            messages, response_format={"type": "json_object"}
        )

        assert "response_format" in kwargs
        assert kwargs["response_format"]["type"] == "json_object"

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_payload_without_response_format(self):
        """_build_request_kwargs should NOT include response_format when None."""
        provider = OpenAIProvider(model="gpt-5-mini")

        messages = [{"role": "user", "content": "test"}]
        kwargs = provider._build_request_kwargs(messages)

        assert "response_format" not in kwargs

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_payload_with_json_schema_format(self):
        """_build_request_kwargs should include json_schema response_format."""
        from src.fagan_tool.providers.openai_provider import REVIEWER_OUTPUT_SCHEMA

        provider = OpenAIProvider(model="gpt-5-mini")

        messages = [{"role": "user", "content": "test"}]
        response_format = {"type": "json_schema", "json_schema": REVIEWER_OUTPUT_SCHEMA}
        kwargs = provider._build_request_kwargs(messages, response_format=response_format)

        assert "response_format" in kwargs
        assert kwargs["response_format"]["type"] == "json_schema"
        assert kwargs["response_format"]["json_schema"]["name"] == "reviewer_output"
        assert kwargs["response_format"]["json_schema"]["strict"] is True


class TestStructuredOutputSchema:
    """Test that JSON schemas are properly defined."""

    def test_reviewer_schema_has_required_fields(self):
        """REVIEWER_OUTPUT_SCHEMA should have all required fields."""
        from src.fagan_tool.providers.openai_provider import REVIEWER_OUTPUT_SCHEMA

        schema = REVIEWER_OUTPUT_SCHEMA["schema"]
        assert schema["type"] == "object"
        assert "defects" in schema["properties"]
        assert "notes" in schema["properties"]
        assert "defects" in schema["required"]
        assert "notes" in schema["required"]

    def test_reviewer_schema_defect_fields(self):
        """Defect items should have all required fields."""
        from src.fagan_tool.providers.openai_provider import REVIEWER_OUTPUT_SCHEMA

        defect_schema = REVIEWER_OUTPUT_SCHEMA["schema"]["properties"]["defects"]["items"]
        required_fields = ["position", "page_hint", "risk", "fault_type",
                          "description", "evidence", "confidence", "flags"]

        for field in required_fields:
            assert field in defect_schema["properties"], f"Missing field: {field}"
            assert field in defect_schema["required"], f"Field not required: {field}"

    def test_scribe_schema_has_required_fields(self):
        """SCRIBE_OUTPUT_SCHEMA should have all required fields."""
        from src.fagan_tool.providers.openai_provider import SCRIBE_OUTPUT_SCHEMA

        schema = SCRIBE_OUTPUT_SCHEMA["schema"]
        required = ["consolidated_defects", "duplicates_removed",
                   "conflicts_flagged", "minutes", "exit_decision"]

        for field in required:
            assert field in schema["properties"], f"Missing field: {field}"
            assert field in schema["required"], f"Field not required: {field}"


class TestEmptyResponseHandling:
    """Test handling of empty responses from OpenAI with retry logic."""

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_empty_content_retries_then_returns_incomplete(self, mock_openai_class):
        """Empty content should retry once, then return incomplete fallback JSON."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.content = None
        mock_choice.message.refusal = None
        mock_response.choices = [mock_choice]
        mock_response.usage = MagicMock()
        # Return empty on both attempts
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAIProvider(model="gpt-5-mini")
        result = provider.generate(
            [{"role": "user", "content": "Return JSON"}],
            response_format={"type": "json_object"}
        )

        # Should retry and return incomplete fallback JSON
        assert "_incomplete" in result
        assert "defects" in result
        # Should have called API twice (initial + 1 retry)
        assert mock_client.chat.completions.create.call_count == 2

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_truncated_response_retries_with_more_tokens(self, mock_openai_class, caplog):
        """Truncated response should retry with 2x tokens, then mark as incomplete."""
        import logging

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.finish_reason = "length"
        mock_choice.message.content = '{"partial": "json"}'
        mock_choice.message.refusal = None
        mock_response.choices = [mock_choice]
        # Return truncated on both attempts
        mock_client.chat.completions.create.return_value = mock_response

        with caplog.at_level(logging.WARNING):
            provider = OpenAIProvider(model="gpt-5-mini")
            result = provider.generate([{"role": "user", "content": "test"}])

        assert "truncated" in caplog.text.lower()
        # Should have retried with larger token limit
        assert mock_client.chat.completions.create.call_count == 2
        # Result should have truncation marker
        assert "[TRUNCATED" in result

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_retry_succeeds_on_second_attempt(self, mock_openai_class):
        """If retry succeeds, should return successful response."""
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # First call: empty response
        empty_response = MagicMock()
        empty_choice = MagicMock()
        empty_choice.finish_reason = "stop"
        empty_choice.message.content = None
        empty_choice.message.refusal = None
        empty_response.choices = [empty_choice]
        empty_response.usage = MagicMock()

        # Second call: successful response
        success_response = MagicMock()
        success_choice = MagicMock()
        success_choice.finish_reason = "stop"
        success_choice.message.content = '{"defects": [], "notes": "success"}'
        success_choice.message.refusal = None
        success_response.choices = [success_choice]

        mock_client.chat.completions.create.side_effect = [empty_response, success_response]

        provider = OpenAIProvider(model="gpt-4o-mini")
        result = provider.generate(
            [{"role": "user", "content": "test"}],
            response_format={"type": "json_object"}
        )

        assert result == '{"defects": [], "notes": "success"}'
        assert mock_client.chat.completions.create.call_count == 2


class TestConfigToAPIParameterMapping:
    """Test that config parameters are correctly mapped to API parameters."""

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_max_tokens_maps_to_max_completion_tokens(self):
        """Config max_tokens should be mapped to API max_completion_tokens."""
        provider = OpenAIProvider(model="gpt-4o-mini", max_tokens=2048)

        messages = [{"role": "user", "content": "test"}]
        kwargs = provider._build_request_kwargs(messages)

        # Config uses max_tokens, API should use max_completion_tokens
        assert "max_completion_tokens" in kwargs
        assert kwargs["max_completion_tokens"] == 2048
        assert "max_tokens" not in kwargs  # Should NOT appear in API call

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_max_tokens_override_for_retry(self):
        """max_tokens_override should be used for retries."""
        provider = OpenAIProvider(model="gpt-4o-mini", max_tokens=2048)

        messages = [{"role": "user", "content": "test"}]
        kwargs = provider._build_request_kwargs(messages, max_tokens_override=4096)

        assert kwargs["max_completion_tokens"] == 4096  # Override value


class TestRestrictedModelBehavior:
    """Test that restricted models don't crash when given unsupported params."""

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    @patch("src.fagan_tool.providers.openai_provider.OpenAI")
    def test_restricted_model_with_temperature_continues(self, mock_openai_class, caplog):
        """Restricted model with temperature should log warning but continue."""
        import logging

        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.finish_reason = "stop"
        mock_choice.message.content = '{"result": "success"}'
        mock_choice.message.refusal = None
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        with caplog.at_level(logging.WARNING):
            # Initialize with temperature (which gpt-5-mini doesn't support)
            provider = OpenAIProvider(model="gpt-5-mini", temperature=0.5)
            result = provider.generate([{"role": "user", "content": "test"}])

        # Should log warning about ignored temperature
        assert "does not support custom sampling parameters" in caplog.text
        assert "temperature=0.5" in caplog.text
        # But should still return response successfully
        assert result == '{"result": "success"}'

    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_restricted_model_omits_temperature_from_api_call(self):
        """Restricted model should not send temperature to API."""
        provider = OpenAIProvider(model="gpt-5-mini", temperature=0.5)

        messages = [{"role": "user", "content": "test"}]
        kwargs = provider._build_request_kwargs(messages)

        # temperature should NOT be in API call for restricted models
        assert "temperature" not in kwargs


class TestIncompleteReviewerOutput:
    """Test that incomplete outputs are properly marked."""

    def test_reviewer_output_has_incomplete_fields(self):
        """ReviewerOutput schema should have is_incomplete and incomplete_reason fields."""
        from src.fagan_tool.core.schemas import ReviewerOutput, ReadingTechnique

        output = ReviewerOutput(
            reviewer_id="test_reviewer",
            technique=ReadingTechnique.UBR,
            defects=[],
            notes="test",
            is_incomplete=True,
            incomplete_reason="Test failure",
        )

        assert output.is_incomplete is True
        assert output.incomplete_reason == "Test failure"

    def test_reviewer_output_default_not_incomplete(self):
        """ReviewerOutput should default to not incomplete."""
        from src.fagan_tool.core.schemas import ReviewerOutput, ReadingTechnique

        output = ReviewerOutput(
            reviewer_id="test_reviewer",
            technique=ReadingTechnique.UBR,
            defects=[],
            notes="test",
        )

        assert output.is_incomplete is False
        assert output.incomplete_reason is None
