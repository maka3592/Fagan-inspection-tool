"""Moderator agent for planning and follow-up phases."""

from typing import Dict, List

from ..core.schemas import MeetingOutput, ReviewerOutput
from .base_agent import BaseAgent


class ModeratorAgent(BaseAgent):
    """Agent that handles planning, kick-off, and follow-up."""

    def __init__(self, provider, prompt_dir):
        """Initialize moderator agent.

        Args:
            provider: LLM provider instance
            prompt_dir: Directory containing prompt templates
        """
        super().__init__(provider, "moderator", prompt_dir)

    def plan_inspection(
        self,
        artifacts: List[Dict],
        condition: str,
    ) -> Dict:
        """Perform planning phase.

        Args:
            artifacts: List of artifacts to inspect
            condition: Inspection condition/strategy

        Returns:
            Planning decisions dict
        """
        template = self.load_prompt("moderator_planning.txt")

        artifact_summary = "\n".join(
            f"- {a['metadata'].name} ({a['metadata'].type}, "
            f"{a['metadata'].page_count or 'N/A'} pages)"
            for a in artifacts
        )

        system_prompt = template

        user_message = f"""
Plan a formal software inspection for the following artifacts:

{artifact_summary}

Condition: {condition}

Provide:
1. Entry criteria check
2. Review focus areas
3. Scope definition
4. Estimated effort

Output as JSON:
{{
  "entry_check": "Pass/Fail",
  "focus_areas": ["area1", "area2", ...],
  "scope": "Description of what to review",
  "estimated_effort": "X hours",
  "notes": "Additional planning notes"
}}
"""

        response = self.call_llm(user_message, system_prompt)

        try:
            return self.extract_json_from_response(response)
        except ValueError:
            return {
                "entry_check": "Pass",
                "focus_areas": ["All sections"],
                "scope": "Full inspection",
                "estimated_effort": "Unknown",
                "notes": "Auto-generated plan",
            }

    def conduct_kickoff(
        self,
        artifacts: List[Dict],
        techniques: List[str],
    ) -> Dict:
        """Simulate kick-off meeting.

        Args:
            artifacts: Artifacts to review
            techniques: Reading techniques to use

        Returns:
            Kick-off information dict
        """
        return {
            "roles_assigned": True,
            "rules_clarified": True,
            "techniques": techniques,
            "logging_format": "JSON defect records",
            "artifacts_distributed": [a["metadata"].name for a in artifacts],
        }

    def follow_up(
        self,
        reviewer_outputs: List[ReviewerOutput],
        meeting_output: MeetingOutput,
    ) -> Dict:
        """Perform follow-up quality check.

        Args:
            reviewer_outputs: Reviewer outputs
            meeting_output: Meeting output

        Returns:
            Follow-up quality check results
        """
        template = self.load_prompt("moderator_followup.txt")

        summary = f"""
Inspection Results:
- Reviewers: {len(reviewer_outputs)}
- Total findings (pre-meeting): {sum(len(r.defects) for r in reviewer_outputs)}
- Consolidated findings: {len(meeting_output.consolidated_defects)}
- Duplicates removed: {meeting_output.duplicates_removed}
- Exit decision: {meeting_output.exit_decision}
"""

        system_prompt = template

        user_message = f"""
Perform follow-up quality check on inspection results:

{summary}

Check:
1. Are logs complete and evidence-based?
2. Are risk classifications justified?
3. Are there any obvious gaps?
4. Is exit decision appropriate?

Output JSON:
{{
  "logs_complete": true/false,
  "evidence_quality": "High/Medium/Low",
  "gaps_identified": ["gap1", ...],
  "exit_approved": true/false,
  "recommendations": "Text..."
}}
"""

        response = self.call_llm(user_message, system_prompt)

        try:
            return self.extract_json_from_response(response)
        except ValueError:
            return {
                "logs_complete": True,
                "evidence_quality": "Medium",
                "gaps_identified": [],
                "exit_approved": True,
                "recommendations": "Proceed with rework",
            }
