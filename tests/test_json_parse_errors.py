"""Tests for JSON parse error tracking and debug file saving.

Tests verify:
1. JSON parse errors are tracked in BaseAgent.json_parse_errors
2. Debug files are saved when parsing fails and debug_dir is set
3. Error tracking can be cleared between runs
4. JSON extraction from markdown code fences works
5. Empty response handling returns valid minimal JSON
6. Trailing commas are handled
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.fagan_tool.agents.base_agent import BaseAgent


class MockProvider:
    """Mock LLM provider for testing."""
    def generate(self, messages, system=None, response_format=None):
        return "mock response"

    def get_provider_name(self):
        return "mock"


class TestJSONExtractionFromCodeFences:
    """Test extraction of JSON from markdown code fences."""

    def setup_method(self):
        """Clear errors before each test."""
        BaseAgent.clear_json_parse_errors()

    def test_extract_json_from_triple_backtick_json(self):
        """JSON in ```json ... ``` block should parse."""
        agent = BaseAgent(MockProvider(), "test")

        response = """Here is the analysis:

```json
{
  "defects": [{"position": "Section 1", "page_hint": "p. 1", "risk": "A", "fault_type": "M", "description": "test", "evidence": "none", "confidence": 0.9, "flags": []}],
  "notes": "Test note"
}
```

End of response."""

        result = agent.extract_json_from_response(response)

        assert "defects" in result
        assert len(result["defects"]) == 1
        assert result["defects"][0]["position"] == "Section 1"
        assert len(BaseAgent.json_parse_errors) == 0

    def test_extract_json_from_triple_backtick_no_lang(self):
        """JSON in ``` ... ``` block (no language hint) should parse."""
        agent = BaseAgent(MockProvider(), "test")

        response = """```
{"defects": [], "notes": "empty"}
```"""

        result = agent.extract_json_from_response(response)

        assert result == {"defects": [], "notes": "empty"}

    def test_extract_json_with_leading_prose(self):
        """JSON with leading text should parse."""
        agent = BaseAgent(MockProvider(), "test")

        response = """Based on my analysis, here are the findings:

{"defects": [{"position": "Sec 2", "page_hint": "p. 2", "risk": "B", "fault_type": "W", "description": "issue", "evidence": "text", "confidence": 0.8, "flags": []}], "notes": "found one"}"""

        result = agent.extract_json_from_response(response)

        assert len(result["defects"]) == 1
        assert result["defects"][0]["risk"] == "B"

    def test_extract_json_with_trailing_comma(self):
        """JSON with trailing comma should parse after fix."""
        agent = BaseAgent(MockProvider(), "test")

        response = '{"defects": [], "notes": "test",}'

        result = agent.extract_json_from_response(response)

        assert result == {"defects": [], "notes": "test"}


class TestEmptyResponseHandling:
    """Test handling of empty responses from LLM."""

    def setup_method(self):
        """Clear errors before each test."""
        BaseAgent.clear_json_parse_errors()

    def test_empty_string_returns_minimal_json(self):
        """Empty string should return minimal valid JSON."""
        agent = BaseAgent(MockProvider(), "test")

        result = agent.extract_json_from_response("")

        assert "defects" in result
        assert result["defects"] == []
        assert "notes" in result

    def test_whitespace_only_returns_minimal_json(self):
        """Whitespace-only response should return minimal valid JSON."""
        agent = BaseAgent(MockProvider(), "test")

        result = agent.extract_json_from_response("   \n\t  ")

        assert "defects" in result
        assert result["defects"] == []

    def test_none_response_returns_minimal_json(self):
        """None-like empty response handling."""
        agent = BaseAgent(MockProvider(), "test")

        # None is handled at provider level, but empty string goes through
        result = agent.extract_json_from_response("")

        assert isinstance(result, dict)
        assert "defects" in result


class TestJSONParseErrorTracking:
    """Test JSON parse error tracking functionality."""

    def setup_method(self):
        """Clear errors before each test."""
        BaseAgent.clear_json_parse_errors()

    def test_successful_json_extraction(self):
        """Valid JSON should parse without errors."""
        agent = BaseAgent(MockProvider(), "test")

        result = agent.extract_json_from_response('{"key": "value"}')

        assert result == {"key": "value"}
        assert len(BaseAgent.json_parse_errors) == 0

    def test_json_in_code_block_extraction(self):
        """JSON in markdown code block should parse."""
        agent = BaseAgent(MockProvider(), "test")

        response = """Here is the result:
```json
{"defects": []}
```
"""
        result = agent.extract_json_from_response(response)

        assert result == {"defects": []}
        assert len(BaseAgent.json_parse_errors) == 0

    def test_failed_parse_tracks_error(self):
        """Failed JSON parse should track error."""
        agent = BaseAgent(MockProvider(), "test_agent")

        with pytest.raises(ValueError, match="Could not extract valid JSON"):
            agent.extract_json_from_response("This is not JSON at all")

        assert len(BaseAgent.json_parse_errors) == 1
        error = BaseAgent.json_parse_errors[0]
        assert error["agent_role"] == "test_agent"
        assert "error_id" in error
        assert "timestamp" in error

    def test_error_tracking_with_context(self):
        """Context should be included in error info."""
        agent = BaseAgent(MockProvider(), "reviewer")

        with pytest.raises(ValueError):
            agent.extract_json_from_response("invalid", context="reviewer_1_ubr")

        error = BaseAgent.json_parse_errors[0]
        assert error["context"] == "reviewer_1_ubr"

    def test_clear_errors(self):
        """Errors should be clearable."""
        agent = BaseAgent(MockProvider(), "test")

        with pytest.raises(ValueError):
            agent.extract_json_from_response("invalid")

        assert len(BaseAgent.json_parse_errors) == 1

        BaseAgent.clear_json_parse_errors()

        assert len(BaseAgent.json_parse_errors) == 0

    def test_get_errors_returns_copy(self):
        """get_json_parse_errors should return a copy."""
        agent = BaseAgent(MockProvider(), "test")

        with pytest.raises(ValueError):
            agent.extract_json_from_response("invalid")

        errors = BaseAgent.get_json_parse_errors()
        errors.clear()  # Modify the returned list

        # Original should be unchanged
        assert len(BaseAgent.json_parse_errors) == 1


class TestDebugFileSaving:
    """Test debug file saving functionality."""

    def setup_method(self):
        """Clear errors before each test."""
        BaseAgent.clear_json_parse_errors()

    def test_debug_file_saved_on_failure(self):
        """Debug file should be saved when parse fails and debug_dir is set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = BaseAgent(MockProvider(), "reviewer", debug_dir=Path(tmpdir))

            with pytest.raises(ValueError):
                agent.extract_json_from_response("invalid json", context="test_ctx")

            # Check debug directory was created
            debug_dir = Path(tmpdir) / "debug"
            assert debug_dir.exists()

            # Check debug file exists
            debug_files = list(debug_dir.glob("raw_response_*.txt"))
            assert len(debug_files) == 1

            # Check file content
            content = debug_files[0].read_text()
            assert "invalid json" in content
            assert "reviewer" in content
            assert "test_ctx" in content

    def test_no_debug_file_without_debug_dir(self):
        """No debug file when debug_dir is not set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = BaseAgent(MockProvider(), "reviewer")  # No debug_dir

            with pytest.raises(ValueError):
                agent.extract_json_from_response("invalid json")

            # No debug directory should be created
            debug_dir = Path(tmpdir) / "debug"
            assert not debug_dir.exists()

    def test_no_debug_file_on_success(self):
        """No debug file when parsing succeeds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            agent = BaseAgent(MockProvider(), "reviewer", debug_dir=Path(tmpdir))

            result = agent.extract_json_from_response('{"valid": true}')

            assert result == {"valid": True}
            debug_dir = Path(tmpdir) / "debug"
            assert not debug_dir.exists()


class TestMultipleParseErrors:
    """Test handling of multiple parse errors."""

    def setup_method(self):
        """Clear errors before each test."""
        BaseAgent.clear_json_parse_errors()

    def test_multiple_errors_tracked(self):
        """Multiple parse errors should all be tracked."""
        agent1 = BaseAgent(MockProvider(), "reviewer")
        agent2 = BaseAgent(MockProvider(), "scribe")

        with pytest.raises(ValueError):
            agent1.extract_json_from_response("bad1", context="ctx1")

        with pytest.raises(ValueError):
            agent2.extract_json_from_response("bad2", context="ctx2")

        assert len(BaseAgent.json_parse_errors) == 2
        assert BaseAgent.json_parse_errors[0]["agent_role"] == "reviewer"
        assert BaseAgent.json_parse_errors[1]["agent_role"] == "scribe"

    def test_errors_shared_across_instances(self):
        """Error list should be shared across all agent instances."""
        agent1 = BaseAgent(MockProvider(), "agent1")
        agent2 = BaseAgent(MockProvider(), "agent2")

        with pytest.raises(ValueError):
            agent1.extract_json_from_response("invalid")

        # agent2 should see the error
        errors = agent2.get_json_parse_errors()
        assert len(errors) == 1
