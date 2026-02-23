"""Prompt snapshot tests to detect unintended prompt changes."""

import hashlib
from pathlib import Path

import pytest

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class TestReviewerUBRPrompt:
    """Snapshot tests for the UBR reviewer prompt."""

    @pytest.fixture
    def prompt_text(self):
        """Load the UBR reviewer prompt."""
        return (PROMPTS_DIR / "reviewer_ubr.txt").read_text()

    def test_prompt_contains_json_output_format(self, prompt_text):
        """Prompt requires JSON-only output."""
        assert "MUST output ONLY valid JSON" in prompt_text

    def test_prompt_contains_position_format_rules(self, prompt_text):
        """Prompt specifies canonical position format."""
        assert 'NO "Section" prefix' in prompt_text
        assert '"3.4.1"' in prompt_text or "'3.4.1'" in prompt_text

    def test_prompt_contains_description_style_section(self, prompt_text):
        """Prompt has the description style guidance section."""
        assert "## Description Style (MANDATORY)" in prompt_text
        assert "EXACT signal and entity names" in prompt_text

    def test_prompt_contains_good_description_examples(self, prompt_text):
        """Prompt shows signal-first description examples."""
        assert "'Reject_Order': A signal is missing for not confirming orders." in prompt_text
        assert "'Confirm_Voice': The signal is missing from the MSC." in prompt_text
        assert "'Stop_Voice': The signal is missing from the MSC." in prompt_text

    def test_prompt_contains_bad_description_examples(self, prompt_text):
        """Prompt shows what NOT to write."""
        assert "BAD examples" in prompt_text
        assert "too vague" in prompt_text

    def test_prompt_contains_cross_reference_checks(self, prompt_text):
        """Prompt includes cross-reference check guidance."""
        assert "CROSS-REFERENCE CHECKS" in prompt_text
        assert "must be defined in Tables" in prompt_text

    def test_prompt_contains_extra_context_placeholder(self, prompt_text):
        """Prompt has {extra_context} placeholder for per-reviewer focus."""
        assert "{extra_context}" in prompt_text

    def test_prompt_quality_check_requires_signal_names(self, prompt_text):
        """Quality checks require specific signal names in descriptions."""
        assert "SPECIFIC signal name" in prompt_text

    def test_prompt_defect_uniqueness_required(self, prompt_text):
        """Quality checks require unique descriptions."""
        assert "No two defects have identical descriptions" in prompt_text

    def test_prompt_multi_position_guidance(self, prompt_text):
        """Prompt guides multi-position defects (table + section)."""
        assert 'list BOTH: "Table 1, 3.4.2"' in prompt_text


class TestReviewerCBRPrompt:
    """Snapshot tests for the CBR reviewer prompt."""

    @pytest.fixture
    def prompt_text(self):
        """Load the CBR reviewer prompt."""
        return (PROMPTS_DIR / "reviewer_cbr.txt").read_text()

    def test_prompt_contains_json_output_format(self, prompt_text):
        """CBR prompt requires JSON-only output."""
        assert "MUST output ONLY valid JSON" in prompt_text

    def test_prompt_contains_position_format_rules(self, prompt_text):
        """CBR prompt specifies canonical position format."""
        assert 'NO "Section" prefix' in prompt_text
        assert '"3.4.1"' in prompt_text or "'3.4.1'" in prompt_text

    def test_prompt_contains_description_style_section(self, prompt_text):
        """CBR prompt has the description style guidance section."""
        assert "## Description Style (MANDATORY)" in prompt_text
        assert "EXACT signal and entity names" in prompt_text

    def test_prompt_contains_good_description_examples(self, prompt_text):
        """CBR prompt shows signal-first description examples."""
        assert "'Reject_Order'" in prompt_text
        assert "'Confirm_Voice'" in prompt_text

    def test_prompt_contains_bad_description_examples(self, prompt_text):
        """CBR prompt shows what NOT to write."""
        assert "BAD examples" in prompt_text
        assert "too vague" in prompt_text

    def test_prompt_contains_cbr_methodology(self, prompt_text):
        """CBR prompt includes checklist iteration methodology."""
        assert "## CBR Methodology" in prompt_text
        assert "checklist item" in prompt_text.lower()

    def test_prompt_contains_extra_context_placeholder(self, prompt_text):
        """CBR prompt has {extra_context} placeholder for checklist injection."""
        assert "{extra_context}" in prompt_text

    def test_prompt_quality_check_requires_signal_names(self, prompt_text):
        """Quality checks require specific signal names in descriptions."""
        assert "SPECIFIC signal name" in prompt_text

    def test_prompt_contains_mandatory_fields(self, prompt_text):
        """CBR prompt lists all mandatory defect fields."""
        assert "position" in prompt_text
        assert "page_hint" in prompt_text
        assert "fault_type" in prompt_text
        assert "evidence" in prompt_text

    def test_prompt_no_arbitrary_defect_quota(self, prompt_text):
        """CBR prompt does NOT specify arbitrary defect targets (literature-conformant)."""
        # Per Masterarbeit Punkt 1: "Entferne nicht-literaturtreue Zielvorgaben"
        assert "Do NOT invent additional heuristics or defect quotas" in prompt_text


class TestScribeMeetingPrompt:
    """Snapshot tests for the scribe meeting prompt."""

    @pytest.fixture
    def prompt_text(self):
        """Load the scribe meeting prompt."""
        return (PROMPTS_DIR / "scribe_meeting.txt").read_text()

    def test_prompt_requires_shared_position_token(self, prompt_text):
        """Scribe prompt requires shared position token for dedup."""
        assert "SAME Position Token" in prompt_text
        assert "EXACT section token" in prompt_text

    def test_prompt_requires_high_similarity(self, prompt_text):
        """Scribe prompt requires high description similarity for dedup."""
        assert "85%" in prompt_text

    def test_prompt_preserves_defects_by_default(self, prompt_text):
        """Scribe prompt warns against over-dedup."""
        assert "When in doubt, do NOT deduplicate" in prompt_text
