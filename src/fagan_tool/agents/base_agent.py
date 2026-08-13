"""Base agent class for all inspection agents."""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..providers.base import LLMProvider

logger = logging.getLogger(__name__)


class BaseAgent:
    """Base class for inspection agents."""

    # Class-level list to track JSON parse errors across agents
    json_parse_errors: List[Dict[str, Any]] = []

    def __init__(
        self,
        provider: LLMProvider,
        role: str,
        prompt_dir: Path = Path("prompts"),
        debug_dir: Optional[Path] = None,
    ):
        """Initialize agent.

        Args:
            provider: LLM provider instance
            role: Agent role identifier
            prompt_dir: Directory containing prompt templates
            debug_dir: Optional directory for debug output (raw responses on parse failure)
        """
        self.provider = provider
        self.role = role
        self.prompt_dir = prompt_dir
        self.debug_dir = debug_dir

    def load_prompt(self, filename: str) -> str:
        """Load prompt template from file.

        Args:
            filename: Prompt template filename

        Returns:
            Prompt template content
        """
        prompt_path = self.prompt_dir / filename
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()

    def format_prompt(self, template: str, **kwargs) -> str:
        """Format prompt template with variables.

        Args:
            template: Prompt template string
            **kwargs: Variables to substitute

        Returns:
            Formatted prompt
        """
        return template.format(**kwargs)

    def call_llm(
        self,
        user_message: str,
        system_prompt: Optional[str] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Call LLM with messages.

        Args:
            user_message: User message content
            system_prompt: Optional system prompt
            response_format: Optional response format for structured output.
                             Use {"type": "json_object"} for JSON mode.

        Returns:
            LLM response text
        """
        messages = [{"role": "user", "content": user_message}]
        # Agent-Rolle für das (optionale) Usage-Log setzen. No-op, wenn kein
        # UsageLogger am Provider hängt.
        set_ctx = getattr(self.provider, "set_call_context", None)
        if callable(set_ctx):
            set_ctx(agent_role=self.role)
        return self.provider.generate(
            messages, system=system_prompt, response_format=response_format
        )

    def extract_json_from_response(self, response: str, context: str = "") -> Dict:
        """Extract JSON from LLM response.

        Handles cases where JSON is wrapped in markdown code blocks,
        has leading/trailing text, or has minor formatting issues.
        On failure, saves raw response to debug file if debug_dir is set.

        Args:
            response: LLM response text
            context: Optional context string for error tracking (e.g., "reviewer_1")

        Returns:
            Parsed JSON dict

        Raises:
            ValueError: If JSON extraction fails
        """
        import re

        # Handle empty response
        if not response or not response.strip():
            logger.warning(f"Empty response received from LLM (context: {context})")
            # Return minimal valid JSON for structured output
            return {"defects": [], "notes": "Empty response from model"}

        # Step 1: Try direct parse first
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Step 2: Remove markdown code fences (```json ... ```)
        cleaned = response
        # Remove opening fence with optional language hint
        cleaned = re.sub(r'^```(?:json|JSON)?\s*\n?', '', cleaned, flags=re.MULTILINE)
        # Remove closing fence
        cleaned = re.sub(r'\n?```\s*$', '', cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

        if cleaned:
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass

        # Step 3: Extract JSON object from text with leading/trailing prose
        # Find the first { and last } to extract the JSON portion
        text = response
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            json_text = text[start : end + 1]
            try:
                return json.loads(json_text)
            except json.JSONDecodeError:
                pass

            # Step 4: Try to fix common JSON issues
            fixed = self._fix_common_json_issues(json_text)
            if fixed != json_text:
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass

        # Step 5: Look for JSON in code blocks (line-by-line fallback)
        lines = response.split("\n")
        json_lines = []
        in_code_block = False

        for line in lines:
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block or (line.strip().startswith("{") or json_lines):
                json_lines.append(line)
                if line.strip().endswith("}") and not in_code_block:
                    try:
                        return json.loads("\n".join(json_lines))
                    except json.JSONDecodeError:
                        continue

        # All parsing attempts failed - save debug info
        error_id = uuid.uuid4().hex[:8]
        error_info = {
            "error_id": error_id,
            "timestamp": datetime.now().isoformat(),
            "agent_role": self.role,
            "context": context,
            "response_preview": response[:500] if len(response) > 500 else response,
        }
        BaseAgent.json_parse_errors.append(error_info)

        # Save raw response to debug file
        if self.debug_dir:
            self._save_debug_response(response, error_id, context)

        raise ValueError(f"Could not extract valid JSON from response: {response[:200]}...")

    def _fix_common_json_issues(self, json_text: str) -> str:
        """Try to fix common JSON formatting issues.

        Args:
            json_text: Potentially malformed JSON text

        Returns:
            Fixed JSON text (may still be invalid)
        """
        import re

        fixed = json_text

        # Remove trailing commas before ] or }
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)

        # Note: We do NOT try to fix single quotes, as it's too risky
        # to accidentally corrupt string content

        return fixed

    def _save_debug_response(self, response: str, error_id: str, context: str) -> None:
        """Save raw LLM response to debug file for analysis.

        Args:
            response: Raw LLM response text
            error_id: Unique error identifier
            context: Context string (e.g., reviewer_id)
        """
        try:
            debug_dir = Path(self.debug_dir) / "debug"
            debug_dir.mkdir(parents=True, exist_ok=True)

            filename = f"raw_response_{self.role}_{context}_{error_id}.txt"
            debug_path = debug_dir / filename

            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(f"# Debug: JSON Parse Failure\n")
                f.write(f"# Error ID: {error_id}\n")
                f.write(f"# Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"# Agent: {self.role}\n")
                f.write(f"# Context: {context}\n")
                f.write(f"# Response length: {len(response)}\n")
                f.write(f"{'='*60}\n\n")
                f.write(response)

            logger.warning(f"Saved raw response to debug file: {debug_path}")
        except Exception as e:
            logger.error(f"Failed to save debug response: {e}")

    @classmethod
    def get_json_parse_errors(cls) -> List[Dict[str, Any]]:
        """Get list of JSON parse errors that occurred.

        Returns:
            List of error info dicts
        """
        return cls.json_parse_errors.copy()

    @classmethod
    def clear_json_parse_errors(cls) -> None:
        """Clear the JSON parse error list."""
        cls.json_parse_errors.clear()
