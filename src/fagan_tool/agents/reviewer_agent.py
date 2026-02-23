"""Reviewer agent for individual inspection."""

import uuid
from pathlib import Path
from typing import Dict, List, Optional

from ..core.schemas import Defect, FaultType, ReadingTechnique, ReviewerOutput, RiskLevel
from ..providers.openai_provider import REVIEWER_OUTPUT_SCHEMA
from .base_agent import BaseAgent

# JSON response format for OpenAI API - use strict JSON Schema for reliability
JSON_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": REVIEWER_OUTPUT_SCHEMA
}


class ReviewerAgent(BaseAgent):
    """Agent that performs individual inspection using a reading technique."""

    def __init__(
        self,
        provider,
        reviewer_id: str,
        technique: ReadingTechnique,
        prompt_dir,
        debug_dir: Optional[Path] = None,
    ):
        """Initialize reviewer agent.

        Args:
            provider: LLM provider instance
            reviewer_id: Unique reviewer identifier
            technique: Reading technique to use
            prompt_dir: Directory containing prompt templates
            debug_dir: Optional directory for debug output
        """
        super().__init__(provider, "reviewer", prompt_dir, debug_dir=debug_dir)
        self.reviewer_id = reviewer_id
        self.technique = technique

    def inspect(
        self,
        artifacts: List[Dict],
        extra_context: str = "",
    ) -> ReviewerOutput:
        """Perform individual inspection.

        Args:
            artifacts: List of loaded artifacts with metadata and content
            extra_context: Additional context (e.g., checklist, use cases)

        Returns:
            ReviewerOutput with found defects
        """
        # Load technique-specific prompt
        prompt_file = self._get_prompt_file()
        template = self.load_prompt(prompt_file)

        # Prepare artifact context
        artifact_context = self._format_artifacts(artifacts)

        # Format and call
        system_prompt = template.format(
            technique=self.technique.value,
            extra_context=extra_context,
        )

        user_message = f"""
Review the following software artifacts for defects using {self.technique.value}.

{artifact_context}

Provide your findings as a JSON array of defects. Each defect must have:
- position (section/table/use case/page reference)
- page_hint (page number if applicable)
- risk (A/B/C/UNK)
- fault_type (M/W/UNK)
- description (clear description)
- evidence (quote or paraphrase with page/section reference)
- confidence (0.0-1.0)
- flags (array, e.g., ["uncertain", "needs_clarification"])

Return ONLY valid JSON, no explanations or markdown. Format:
{{
  "defects": [
    {{
      "position": "Section 3.2",
      "page_hint": "p. 15",
      "risk": "A",
      "fault_type": "M",
      "description": "'Process_Data': Missing error handling for null pointer",
      "evidence": "Section 3.2 does not specify error handling (p. 15)",
      "confidence": 0.9,
      "flags": []
    }}
  ],
  "notes": "Additional observations or comments"
}}
"""

        # Use JSON response format for structured output
        response = self.call_llm(
            user_message, system_prompt, response_format=JSON_RESPONSE_FORMAT
        )

        # Parse response
        try:
            data = self.extract_json_from_response(response, context=self.reviewer_id)

            # Check if response was marked as incomplete by provider
            is_incomplete = data.get("_incomplete", False)
            incomplete_reason = None

            # Check for truncation marker in notes
            notes = data.get("notes", "")
            if "[INCOMPLETE]" in notes or "[TRUNCATED" in response:
                is_incomplete = True
                incomplete_reason = "Response was truncated or incomplete"

            defects = []
            for d in data.get("defects", []):
                defect = Defect(
                    id=f"{self.reviewer_id}_{uuid.uuid4().hex[:8]}",
                    position=d.get("position", "unknown"),
                    page_hint=d.get("page_hint"),
                    risk=RiskLevel(d.get("risk", "UNK")),
                    fault_type=FaultType(d.get("fault_type", "UNK")),
                    description=d.get("description", ""),
                    evidence=d.get("evidence", ""),
                    confidence=float(d.get("confidence", 0.8)),
                    flags=d.get("flags", []),
                    reviewer_id=self.reviewer_id,
                    technique=self.technique,
                )
                defects.append(defect)

            return ReviewerOutput(
                reviewer_id=self.reviewer_id,
                technique=self.technique,
                defects=defects,
                notes=notes,
                is_incomplete=is_incomplete,
                incomplete_reason=incomplete_reason,
            )

        except (ValueError, KeyError) as e:
            # Return incomplete output if parsing fails - do NOT silently return 0 defects
            print(f"Warning: Failed to parse reviewer output: {e}")
            return ReviewerOutput(
                reviewer_id=self.reviewer_id,
                technique=self.technique,
                defects=[],
                notes=f"Error parsing output: {str(e)}",
                is_incomplete=True,
                incomplete_reason=f"JSON parse error: {str(e)[:100]}",
            )

    def _get_prompt_file(self) -> str:
        """Get prompt filename for technique."""
        technique_map = {
            ReadingTechnique.UBR: "reviewer_ubr.txt",
            ReadingTechnique.CBR: "reviewer_cbr.txt",
            ReadingTechnique.PBR_TESTER: "reviewer_pbr_tester.txt",
            ReadingTechnique.PBR_DESIGNER: "reviewer_pbr_designer.txt",
            ReadingTechnique.PBR_USER: "reviewer_pbr_user.txt",
        }
        return technique_map.get(self.technique, "reviewer_generic.txt")

    def _format_artifacts(self, artifacts: List[Dict]) -> str:
        """Format artifacts for prompt context.

        Args:
            artifacts: List of loaded artifacts

        Returns:
            Formatted artifact text
        """
        sections = []

        for artifact in artifacts:
            meta = artifact["metadata"]
            content = artifact["content"]

            sections.append(f"\n{'='*60}")
            sections.append(f"ARTIFACT: {meta.name} ({meta.type})")
            sections.append(f"{'='*60}\n")

            if content["type"] == "pdf_pages":
                # Format page-by-page with clear markers
                for page in content["pages"]:
                    sections.append(f"\n--- Page {page['page_num']} ---\n")
                    sections.append(page["text"])
            else:
                # Plain text
                sections.append(content["text"])

        return "\n".join(sections)
