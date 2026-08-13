"""Reviewer agent for individual inspection."""

import json
import re
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from ..core.schemas import Defect, FaultType, ReadingTechnique, ReviewerOutput, RiskLevel
from ..providers.openai_provider import REVIEWER_OUTPUT_SCHEMA
from .base_agent import BaseAgent


# Deterministic "expected from observed" rewrites.
# When auto_expected_observed_from_text fills the observed field from
# evidence/description, we try to derive a symmetric `expected` Soll
# statement by flipping the negation of `observed`. Pure text rewrite,
# no new facts — if no pattern matches, the caller falls back to the
# generic Soll-statement keyed on fault_type.
_EXPECTED_FROM_OBSERVED_RULES = [
    # More specific patterns first so a shorter one does not steal a
    # match from a longer one.
    (re.compile(r"^(.*?)\bdoes\s+not\s+include\b(.*)$", re.IGNORECASE),
     r"\1should include\2"),
    (re.compile(r"^(.*?)\bis\s+not\s+defined\b(.*)$", re.IGNORECASE),
     r"\1is defined\2"),
    (re.compile(r"^(.*?)\bis\s+missing\b(.*)$", re.IGNORECASE),
     r"\1is present/defined\2"),
    (re.compile(r"^(.*?)\blacks\b(.*)$", re.IGNORECASE),
     r"\1has\2"),
]

_EXPECTED_DERIVE_WS_RE = re.compile(r"\s{2,}")


def _derive_expected_from_observed(observed: str) -> Optional[str]:
    """Derive a Soll-statement from an Ist-statement.

    Pure text substitution: the observed clause is left intact except
    for the negation/verb token, which is flipped onto the matching
    affirmative form. Returns ``None`` if no rule matches — the caller
    must then fall back to the generic Soll-statement.
    """
    if not observed:
        return None
    text = observed.strip()
    if not text:
        return None
    for pattern, replacement in _EXPECTED_FROM_OBSERVED_RULES:
        if not pattern.search(text):
            continue
        rewritten = pattern.sub(replacement, text, count=1)
        rewritten = _EXPECTED_DERIVE_WS_RE.sub(" ", rewritten).strip()
        if not rewritten:
            continue
        if not rewritten.endswith((".", "!", "?")):
            rewritten = rewritten + "."
        return rewritten
    return None

# JSON response format for OpenAI API - use strict JSON Schema for reliability
JSON_RESPONSE_FORMAT = {
    "type": "json_schema",
    "json_schema": REVIEWER_OUTPUT_SCHEMA
}

# Allowed record-quality modes. "warn" is the historical default
# (validator just flags missing expected/observed). "repair" enables one
# extra LLM call per reviewer to fill the gaps; defects that still lack
# expected/observed after that call are dropped (quality gate).
ALLOWED_RECORD_QUALITY_MODES = {"warn", "repair"}


class ReviewerAgent(BaseAgent):
    """Agent that performs individual inspection using a reading technique."""

    def __init__(
        self,
        provider,
        reviewer_id: str,
        technique: ReadingTechnique,
        prompt_dir,
        debug_dir: Optional[Path] = None,
        record_quality_mode: str = "warn",
    ):
        """Initialize reviewer agent.

        Args:
            provider: LLM provider instance
            reviewer_id: Unique reviewer identifier
            technique: Reading technique to use
            prompt_dir: Directory containing prompt templates
            debug_dir: Optional directory for debug output
            record_quality_mode: ``"warn"`` (default) just flags defects
                with missing ``expected``/``observed``; ``"repair"``
                triggers a single follow-up LLM call to fill those fields
                and drops defects that still lack them.
        """
        super().__init__(provider, "reviewer", prompt_dir, debug_dir=debug_dir)
        self.reviewer_id = reviewer_id
        self.technique = technique
        if record_quality_mode not in ALLOWED_RECORD_QUALITY_MODES:
            raise ValueError(
                f"Unknown record_quality_mode {record_quality_mode!r}; "
                f"expected one of {sorted(ALLOWED_RECORD_QUALITY_MODES)}"
            )
        self.record_quality_mode = record_quality_mode

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
                    # Inspection-record quality fields. The prompt requires
                    # the LLM to fill these; we forward them verbatim so
                    # downstream reporting and the defect-quality review
                    # see them. No transformation here — schema validators
                    # + the entity backfill in FaganProcess handle the rest.
                    entity=d.get("entity"),
                    expected=d.get("expected"),
                    observed=d.get("observed"),
                    evidence_location=d.get("evidence_location"),
                )
                defects.append(defect)

            # Optional record-quality repair loop. In "warn" mode this is a
            # no-op (historical behaviour). In "repair" mode we issue ONE
            # follow-up call asking the model to fill the expected/observed
            # fields it left empty; defects that still lack those fields
            # after that single retry are dropped (quality gate). Default
            # via getattr so tests / call sites that construct the agent
            # by __new__ without going through __init__ still behave like
            # warn-mode rather than crash.
            if getattr(self, "record_quality_mode", "warn") == "repair":
                defects = self._repair_quality(defects)

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

    # ------------------------------------------------------------------
    # Record-quality repair helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _defect_needs_quality_repair(defect: Defect) -> bool:
        """A defect needs repair iff expected OR observed is blank."""
        expected = (defect.expected or "").strip()
        observed = (defect.observed or "").strip()
        return not expected or not observed

    @staticmethod
    def _paraphrase_expected_observed_from_defect(defect) -> bool:
        """Deterministically fill blank ``expected``/``observed`` from the
        defect's own text (no new facts).

        Used as a last-resort step in the safety-net fallback path of
        :meth:`_repair_quality`: when the repair LLM call yields nothing
        usable, we keep the original defects (warn-equivalent) but
        re-express the existing defect text as a Soll/Ist pair so the
        record is actually evaluable.

        Rules:

        - ``expected`` is filled with a short generic Soll-sentence keyed
          to ``fault_type`` (M / W / other) and the defect's ``entity``
          (or ``"the described item"`` when entity is empty).
        - ``observed`` is filled from ``evidence.quote_or_paraphrase``
          (preferred) → raw ``evidence`` string → ``description`` —
          whichever is non-empty first. We do not paraphrase further:
          the chosen text is copied verbatim (trimmed + length-capped).
        - If both ``entity`` AND ``description`` AND ``evidence`` are
          empty, nothing is filled and the ``missing_*`` flags stay.
        - Each filled field has its corresponding ``missing_*`` flag
          removed; the audit flag ``auto_expected_observed_from_text``
          is appended once so downstream readers can tell which records
          were auto-paraphrased.

        Accepts both ``Defect`` instances and plain dicts so it can run
        against live pipeline objects or against JSON loaded from
        ``reviewer_outputs.json``.

        Returns ``True`` if at least one field was filled.
        """
        is_dict = isinstance(defect, dict)

        def _get(key, default=None):
            if is_dict:
                return defect.get(key, default)
            return getattr(defect, key, default)

        def _set(key, value):
            if is_dict:
                defect[key] = value
            else:
                setattr(defect, key, value)

        # Resolve / create the flags list once.
        if is_dict:
            flags = defect.get("flags")
            if flags is None:
                flags = []
                defect["flags"] = flags
        else:
            flags = getattr(defect, "flags", None)
            if flags is None:
                flags = []
                try:
                    setattr(defect, "flags", flags)
                except Exception:
                    pass

        entity_raw = str(_get("entity") or "").strip()
        description = str(_get("description") or "").strip()
        evidence = _get("evidence")
        ev_quote = ""
        if isinstance(evidence, dict):
            ev_quote = str(evidence.get("quote_or_paraphrase") or "").strip()
        elif isinstance(evidence, str):
            ev_quote = evidence.strip()

        # If there is literally no defect text to lean on, do not invent.
        if not entity_raw and not description and not ev_quote:
            return False

        fault_type = _get("fault_type")
        if hasattr(fault_type, "value"):
            fault_type = fault_type.value
        fault_type = str(fault_type or "").strip().upper()

        entity_display = entity_raw or "the described item"
        MAX_LEN = 240
        filled = False

        # ----- observed: decide first so `expected` can be derived from it -----
        observed_now = str(_get("observed") or "").strip()
        observed_to_use = observed_now
        if not observed_now:
            candidate = ev_quote or description
            if candidate:
                observed_to_use = candidate[:MAX_LEN]
                _set("observed", observed_to_use)
                if "missing_observed" in flags:
                    flags.remove("missing_observed")
                filled = True

        # ----- expected: prefer Soll derived from observed; fallback generic -----
        expected_now = str(_get("expected") or "").strip()
        if not expected_now:
            derived = _derive_expected_from_observed(observed_to_use)
            if derived:
                text = derived
            elif fault_type == "M":
                text = (
                    f"Expected: '{entity_display}' should be present/defined "
                    "as specified."
                )
            elif fault_type == "W":
                text = (
                    f"Expected: '{entity_display}' should match the "
                    "specification/definition."
                )
            else:
                text = (
                    f"Expected: '{entity_display}' should satisfy the "
                    "specification."
                )
            _set("expected", text[:MAX_LEN])
            if "missing_expected" in flags:
                flags.remove("missing_expected")
            filled = True

        if filled and "auto_expected_observed_from_text" not in flags:
            flags.append("auto_expected_observed_from_text")

        return filled

    def _fallback_with_autofill(
        self, defects: List[Defect], reason: str
    ) -> List[Defect]:
        """Common safety-net path: keep originals, paraphrase missing
        expected/observed from the defect text (no new facts)."""
        auto = sum(
            1
            for d in defects
            if self._paraphrase_expected_observed_from_defect(d)
        )
        print(
            f"[record_quality] {self.reviewer_id}: {reason} "
            f"Falling back to warn — keeping {len(defects)} original "
            f"defect(s); auto-paraphrased expected/observed for {auto} "
            "(no new facts invented)."
        )
        return defects

    def _build_repair_message(self, defects: List[Defect]) -> str:
        """Build the user message for the repair LLM call.

        We feed the model only the columns it needs to ground expected /
        observed against the artefacts: id, position, page_hint, entity,
        evidence_location, the short evidence excerpt, and the original
        description. We deliberately do NOT include `flags` (would bias
        the model) or `evidence` as dict (just the quote).
        """
        compact: List[Dict] = []
        for d in defects:
            ev_quote = ""
            if isinstance(d.evidence, dict):
                ev_quote = str(d.evidence.get("quote_or_paraphrase") or "").strip()
            elif isinstance(d.evidence, str):
                ev_quote = d.evidence.strip()
            compact.append({
                "id": d.id,
                "position": d.position,
                "page_hint": d.page_hint,
                "entity": d.entity,
                "evidence_location": d.evidence_location,
                "evidence": ev_quote,
                "description": d.description,
            })

        payload = json.dumps({"defects": compact}, ensure_ascii=False, indent=2)
        return (
            "The following defects you reported are missing `expected` "
            "and/or `observed`. For EACH defect, fill BOTH fields with "
            "ONE short sentence each.\n\n"
            "You may paraphrase from the fields the defect already carries "
            "(description, evidence, entity, evidence_location). This is "
            "NOT inventing new facts — it is re-expressing your own report "
            "as a Soll/Ist pair so a reviewer can evaluate it.\n\n"
            "- expected (Soll, 1 sentence): what should hold for this entity. "
            "Default formulation: \"<entity> should be <present|defined|"
            "specified|consistent|...> in <evidence_location>.\"\n"
            "- observed (Ist, 1 sentence): what the defect says actually "
            "holds. Default formulation: \"<entity> is <missing|wrong|"
            "inconsistent|...> in <evidence_location>.\"\n\n"
            "Concrete example: for a defect with\n"
            "  entity=\"Reject_Order\"\n"
            "  description=\"'Reject_Order': A signal is missing for not "
            "confirming orders.\"\n"
            "  evidence=\"MSC 3.4.1 has no reject arrow.\"\n"
            "  evidence_location=\"p. 7, 3.4.1, MSC\"\n"
            "the expected/observed pair could be\n"
            "  expected: \"Reject_Order should be present in the MSC at "
            "p. 7, 3.4.1.\"\n"
            "  observed: \"Reject_Order is missing from the MSC at "
            "p. 7, 3.4.1.\"\n\n"
            "Hard rules:\n"
            "- Do NOT introduce facts that are not already in the defect "
            "(description, evidence, entity). Paraphrasing those is fine.\n"
            "- Never reference a gold standard or fault list.\n"
            "- Only omit a defect if you genuinely cannot paraphrase even a "
            "one-sentence Soll/Ist from the defect text. Prefer to return a "
            "defensible paraphrase over omitting.\n"
            "- Preserve the `id` of each returned defect so we can match it "
            "back to the original record.\n"
            "- Return the same JSON envelope as before: "
            "{\"defects\": [...], \"notes\": \"...\"}. Each returned defect "
            "MUST carry at minimum: id, position, description, expected, "
            "observed. Copy the original position/description verbatim.\n\n"
            "Defects to repair:\n" + payload
        )

    def _repair_quality(self, defects: List[Defect]) -> List[Defect]:
        """Issue one repair call and salvage what we can.

        Three outcomes, in order of preference:

        1. Some defects come back with filled expected/observed — we
           replace those, drop the unrepaired ones, keep already-complete
           defects untouched (partial success).
        2. The repair call yields zero usable repairs (LLM error, empty
           response, or every returned defect still empty / omitted) — we
           FALL BACK to the original defect list with their
           ``missing_*`` flags intact, equivalent to ``warn`` mode. We
           never let the repair step delete every defect.
        3. Nothing was incomplete to begin with — early return.

        This keeps real runs from collapsing to zero defects when the
        model misbehaves on the repair call.
        """
        incomplete = [d for d in defects if self._defect_needs_quality_repair(d)]
        if not incomplete:
            return defects

        repair_user = self._build_repair_message(incomplete)
        repair_system = (
            "You are repairing inspection records you previously produced. "
            "Output JSON only, no markdown."
        )

        try:
            response = self.call_llm(
                repair_user,
                repair_system,
                response_format=JSON_RESPONSE_FORMAT,
            )
            data = self.extract_json_from_response(
                response, context=f"{self.reviewer_id}_repair"
            )
        except (ValueError, KeyError) as e:
            return self._fallback_with_autofill(
                defects, reason=f"repair call FAILED ({e})."
            )

        repaired_by_id: Dict[str, Dict] = {}
        for r in data.get("defects", []):
            rid = r.get("id")
            if rid:
                repaired_by_id[rid] = r

        partial: List[Defect] = []
        kept_via_repair = 0
        dropped = 0
        for d in defects:
            if not self._defect_needs_quality_repair(d):
                partial.append(d)
                continue
            r = repaired_by_id.get(d.id)
            if r is None:
                # The model chose to omit this defect — count as drop
                # candidate. Whether we actually drop depends on whether
                # any other repair succeeded (see fallback below).
                dropped += 1
                continue
            exp = str(r.get("expected") or "").strip()
            obs = str(r.get("observed") or "").strip()
            if not exp or not obs:
                dropped += 1
                continue
            d.expected = exp
            d.observed = obs
            for flag in ("missing_expected", "missing_observed"):
                if flag in d.flags:
                    d.flags.remove(flag)
            kept_via_repair += 1
            partial.append(d)

        # Safety net: if the repair pass produced ZERO usable repairs we
        # do NOT propagate the dropped state — falling back preserves
        # information instead of returning an empty run. The original
        # defects are kept but expected/observed are auto-paraphrased
        # from the defect text so the records stay evaluable.
        if kept_via_repair == 0:
            return self._fallback_with_autofill(
                defects,
                reason=(
                    f"repair produced no usable defects "
                    f"(would have dropped {dropped} of "
                    f"{len(incomplete)})."
                ),
            )

        if dropped or kept_via_repair:
            print(
                f"[record_quality] {self.reviewer_id}: repair kept "
                f"{kept_via_repair}, dropped {dropped} of "
                f"{len(incomplete)} incomplete defect(s)."
            )
        return partial

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
