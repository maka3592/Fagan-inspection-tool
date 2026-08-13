"""Tests for the inspection-record quality plumbing.

These cover the parts that the schema-level tests do not:

* The reviewer prompts (UBR/CBR/PBR x3) carry the new format rules so
  reviewers actually produce ``entity / expected / observed /
  evidence_location`` in their output.
* The Defect schema is the single source of truth for the deterministic
  ``evidence_location`` fallback used by ``FaganProcess`` — adding a
  defect via the same construction path the process uses must yield the
  same flags.

The matcher and metrics are not touched by this work; if anything here
relies on ``src/fagan_tool/evaluation`` we have widened the scope by
mistake.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fagan_tool.core.schemas import (
    Defect,
    FaultType,
    ReadingTechnique,
    ReviewerOutput,
    RiskLevel,
)


PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"

REVIEWER_PROMPTS = [
    "reviewer_ubr.txt",
    "reviewer_cbr.txt",
    "reviewer_pbr_user.txt",
    "reviewer_pbr_tester.txt",
    "reviewer_pbr_designer.txt",
]


# ---------------------------------------------------------------------------
# Prompt-level: every reviewer prompt has the new field rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prompt_name", REVIEWER_PROMPTS)
def test_reviewer_prompt_lists_quality_fields(prompt_name: str) -> None:
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    # All five new field names must be mentioned in the Mandatory Fields block.
    for field in ("entity", "expected", "observed", "evidence_location"):
        assert f"**{field}**" in text, f"{prompt_name} missing {field} rule"
    # And the explicit anti-hallucination sentinel.
    assert "Anti-hallucination" in text, f"{prompt_name} missing anti-hallucination rule"


@pytest.mark.parametrize("prompt_name", REVIEWER_PROMPTS)
def test_reviewer_prompt_example_includes_quality_fields(prompt_name: str) -> None:
    """The JSON example block must illustrate the new fields."""
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    for sample_key in ('"entity"', '"expected"', '"observed"', '"evidence_location"'):
        assert sample_key in text, f"{prompt_name} example missing {sample_key}"


@pytest.mark.parametrize("prompt_name", REVIEWER_PROMPTS)
def test_reviewer_prompt_still_format_compatible(prompt_name: str) -> None:
    """Sharpened prompts must keep working with `.format(extra_context=...)`."""
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    rendered = text.format(extra_context="SAMPLE FOCUS BLOCK")
    assert "SAMPLE FOCUS BLOCK" in rendered


# ---------------------------------------------------------------------------
# Schema-as-process-contract: the construction path the process uses
# ---------------------------------------------------------------------------


def test_process_style_defect_construction_yields_full_flag_set() -> None:
    """``FaganProcess`` builds ``Defect`` objects via the standard constructor
    (no custom code path) — so a reviewer JSON that omits the new fields
    still produces deterministic flags and a derived evidence_location."""
    raw_defect = {
        "id": "raw_x",
        "position": "3.4.1",
        "page_hint": "p. 7",
        "risk": "A",
        "fault_type": "M",
        "description": "'Reject_Order': missing in MSC.",
        "evidence": "MSC 3.4.1 lacks Reject_Order.",
        # entity / expected / observed / evidence_location intentionally absent
    }
    d = Defect(**raw_defect)
    assert d.evidence_location == "p. 7, 3.4.1"
    expected_flags = {"missing_entity", "missing_expected", "missing_observed"}
    assert expected_flags.issubset(set(d.flags))
    assert "missing_evidence" not in d.flags  # evidence was provided
    assert "missing_evidence_location" not in d.flags  # derived


def test_partial_quality_fields_only_flag_what_is_missing() -> None:
    d = Defect(
        id="raw_y",
        position="3.4.2",
        page_hint="p. 6",
        risk=RiskLevel.B,
        fault_type=FaultType.W,
        description="'Confirm_Voice' wrong params.",
        evidence="Param count mismatch.",
        entity="Confirm_Voice",
        # expected & observed left empty on purpose
        evidence_location="p. 6, 3.4.2, MSC",
    )
    assert "missing_entity" not in d.flags
    assert "missing_expected" in d.flags
    assert "missing_observed" in d.flags
    assert "missing_evidence" not in d.flags
    assert "missing_evidence_location" not in d.flags


# ---------------------------------------------------------------------------
# Deterministic entity backfill from description (no hallucination)
# ---------------------------------------------------------------------------


from fagan_tool.core.process import _backfill_entity_from_description


class TestEntityBackfill:
    def test_backfills_from_single_quoted_prefix(self) -> None:
        d = Defect(
            id="bf_1",
            position="3.4.1",
            page_hint="p. 5",
            description="'Reject_Order': missing in MSC",
            evidence="no reject arrow drawn",
        )
        assert d.entity is None
        assert "missing_entity" in d.flags

        changed = _backfill_entity_from_description(d)
        assert changed is True
        assert d.entity == "Reject_Order"
        assert "missing_entity" not in d.flags  # flag removed on success

    def test_backfills_from_double_quoted_prefix(self) -> None:
        d = Defect(
            id="bf_2",
            position="3.4.2",
            page_hint="p. 6",
            description='"Confirm_Voice": parameters mismatch with Table 1',
            evidence="param count differs",
        )
        changed = _backfill_entity_from_description(d)
        assert changed is True
        assert d.entity == "Confirm_Voice"

    def test_no_change_when_description_has_no_quoted_prefix(self) -> None:
        d = Defect(
            id="bf_3",
            position="3.4.1",
            page_hint="p. 5",
            description="Generic finding without leading quoted token.",
            evidence="x",
        )
        changed = _backfill_entity_from_description(d)
        assert changed is False
        assert d.entity is None
        # missing_entity stays set (no honest backfill possible).
        assert "missing_entity" in d.flags

    def test_no_change_when_entity_already_set(self) -> None:
        d = Defect(
            id="bf_4",
            position="3.4.1",
            page_hint="p. 5",
            description="'Foo': desc",
            evidence="x",
            entity="ExistingEntity",
        )
        changed = _backfill_entity_from_description(d)
        assert changed is False
        assert d.entity == "ExistingEntity"

    def test_no_change_when_description_empty(self) -> None:
        d = Defect(
            id="bf_5",
            position="3.4.1",
            page_hint="p. 5",
            description="x",  # description must be non-empty for Defect()
            evidence="x",
        )
        # Force-empty after construction to simulate the edge case.
        d.description = ""
        changed = _backfill_entity_from_description(d)
        assert changed is False
        assert d.entity is None

    def test_no_change_for_empty_quoted_token(self) -> None:
        d = Defect(
            id="bf_6",
            position="3.4.1",
            page_hint="p. 5",
            description="'': empty quoted token",
            evidence="x",
        )
        changed = _backfill_entity_from_description(d)
        assert changed is False
        assert d.entity is None


# ---------------------------------------------------------------------------
# Dict-mode + same-codepath-as-process.py regression
# ---------------------------------------------------------------------------


class TestEntityBackfillDictMode:
    """Reviewer outputs serialised to JSON come back as dicts. The helper
    must work on those without forcing a re-hydration into pydantic."""

    def test_dict_with_single_quoted_prefix_real_run_shape(self) -> None:
        """Matches the exact shape we saw in
        runs/sweep_cbr_split_soft_n10_20260530_170641/reviewer_outputs.json
        for the 'Reject_Order' defect that previously was not backfilled."""
        d = {
            "id": "reviewer_1_cbr_abc",
            "position": "3.4.1",
            "page_hint": "p. 5",
            "risk": "A",
            "fault_type": "M",
            "description": "'Reject_Order': A signal is missing for not confirming orders.",
            "evidence": {"quote_or_paraphrase": "no reject arrow", "page_hint": "p. 5"},
            "entity": None,
            "expected": None,
            "observed": None,
            "evidence_location": "p. 5, 3.4.1",
            "flags": [
                "needs_clarification",
                "missing_entity",
                "missing_expected",
                "missing_observed",
            ],
        }
        changed = _backfill_entity_from_description(d)
        assert changed is True
        assert d["entity"] == "Reject_Order"
        assert "missing_entity" not in d["flags"]
        # Sibling flags MUST stay (we only fix what we can prove).
        assert "missing_expected" in d["flags"]
        assert "missing_observed" in d["flags"]
        assert "needs_clarification" in d["flags"]

    def test_dict_with_double_quoted_prefix(self) -> None:
        d = {
            "description": '"Start_Voice": Missing signal in MSC.',
            "entity": None,
            "flags": ["missing_entity"],
        }
        changed = _backfill_entity_from_description(d)
        assert changed is True
        assert d["entity"] == "Start_Voice"
        assert "missing_entity" not in d["flags"]

    def test_dict_without_quoted_prefix_unchanged(self) -> None:
        d = {
            "description": "Generic defect without quoted prefix.",
            "entity": None,
            "flags": ["missing_entity"],
        }
        changed = _backfill_entity_from_description(d)
        assert changed is False
        assert d.get("entity") in (None, "")
        assert "missing_entity" in d["flags"]

    def test_dict_without_flags_key_does_not_crash(self) -> None:
        """Real JSON sometimes omits 'flags' entirely. The helper must
        survive that, set entity, and create an empty flags list."""
        d = {
            "description": "'Cancel_Order': missing in MSC.",
            "entity": None,
        }
        changed = _backfill_entity_from_description(d)
        assert changed is True
        assert d["entity"] == "Cancel_Order"
        assert d["flags"] == []


class TestEntityBackfillSameCodepathAsProcess:
    """Mirror the exact loop ``FaganProcess._conduct_individual_inspections``
    runs right after ``reviewer.inspect(...)``: iterate ``output.defects``
    and call the helper. This guards against future refactors that could
    accidentally bypass the helper for reviewer-side defects."""

    def _make_review_like_output(self) -> ReviewerOutput:
        """Build a ReviewerOutput whose Defect objects look like the
        sweep_cbr_split_soft_n10_20260530_170641 sample (quoted-prefix
        description, entity=None, missing_entity flag)."""
        return ReviewerOutput(
            reviewer_id="reviewer_1_cbr",
            technique=ReadingTechnique.CBR,
            defects=[
                Defect(
                    id="reviewer_1_cbr_aaa",
                    position="3.4.1",
                    page_hint="p. 5",
                    risk=RiskLevel.A,
                    fault_type=FaultType.M,
                    description="'Reject_Order': A signal is missing for not confirming orders.",
                    evidence="no reject arrow in 3.4.1 MSC",
                ),
                Defect(
                    id="reviewer_1_cbr_bbb",
                    position="3.4.2",
                    page_hint="p. 6",
                    risk=RiskLevel.B,
                    fault_type=FaultType.W,
                    description='"Confirm_Voice": Wrong parameter count vs Table 1.',
                    evidence="parameter count differs",
                ),
                Defect(
                    id="reviewer_1_cbr_ccc",
                    position="3.4.1",
                    page_hint="p. 5",
                    risk=RiskLevel.B,
                    fault_type=FaultType.M,
                    description="Generic finding without quoted prefix.",
                    evidence="x",
                ),
            ],
            notes="",
        )

    def test_loop_backfills_quoted_prefix_defects(self) -> None:
        output = self._make_review_like_output()
        # Pre-conditions match what we saw in the real run.
        assert all(d.entity is None for d in output.defects)
        assert all("missing_entity" in d.flags for d in output.defects)

        # Same loop as in process.py:_conduct_individual_inspections.
        backfilled = 0
        for d in output.defects:
            if _backfill_entity_from_description(d):
                backfilled += 1

        assert backfilled == 2  # the two quoted-prefix defects, not the generic one
        assert output.defects[0].entity == "Reject_Order"
        assert output.defects[1].entity == "Confirm_Voice"
        assert output.defects[2].entity is None
        assert "missing_entity" not in output.defects[0].flags
        assert "missing_entity" not in output.defects[1].flags
        assert "missing_entity" in output.defects[2].flags  # honest reporting

    def test_loop_is_idempotent(self) -> None:
        """Running the loop twice must not change anything on pass 2."""
        output = self._make_review_like_output()
        first = sum(1 for d in output.defects if _backfill_entity_from_description(d))
        second = sum(1 for d in output.defects if _backfill_entity_from_description(d))
        assert first == 2
        assert second == 0


# ---------------------------------------------------------------------------
# Reviewer-agent mapping must FORWARD the LLM-supplied quality fields
# ---------------------------------------------------------------------------


import json as _json

from fagan_tool.agents.reviewer_agent import ReviewerAgent


class TestReviewerAgentForwardsQualityFields:
    """Regression for the field-drop bug. The reviewer agent constructs
    ``Defect`` objects from the LLM's JSON; previously it ignored
    ``entity``, ``expected``, ``observed`` and ``evidence_location``
    (so all four ended up as ``None`` regardless of what the model
    produced). The mapping must now copy them verbatim."""

    def _make_agent_with_canned_json(self, canned: dict) -> ReviewerAgent:
        agent = ReviewerAgent.__new__(ReviewerAgent)
        agent.reviewer_id = "reviewer_test"
        agent.technique = ReadingTechnique.UBR
        agent.prompt_dir = Path("prompts")
        agent.debug_dir = None
        agent.provider = None
        # Stub everything the real code path touches so the test stays
        # hermetic (no LLM, no real prompt template).
        agent.load_prompt = lambda name: "stub {technique} {extra_context}"
        agent._format_artifacts = lambda artifacts: "stub artefact text"
        agent.call_llm = lambda *a, **kw: _json.dumps(canned)
        agent.extract_json_from_response = (
            lambda resp, context="": _json.loads(resp)
        )
        return agent

    def test_full_quality_payload_is_preserved(self) -> None:
        canned = {
            "defects": [
                {
                    "position": "3.4.1",
                    "page_hint": "p. 7",
                    "risk": "A",
                    "fault_type": "M",
                    "description": "'Reject_Order': missing in MSC.",
                    "evidence": {
                        "quote_or_paraphrase": "MSC 3.4.1 has no reject arrow.",
                        "page_hint": "p. 7",
                    },
                    "entity": "Reject_Order",
                    "expected": "MSC must contain a Reject_Order arrow.",
                    "observed": "Only Confirm arrow is drawn.",
                    "evidence_location": "p. 7, 3.4.1, MSC",
                    "confidence": 0.9,
                    "flags": [],
                }
            ],
            "notes": "x",
        }
        agent = self._make_agent_with_canned_json(canned)
        output = agent.inspect(artifacts=[], extra_context="")
        assert len(output.defects) == 1
        d = output.defects[0]
        assert d.entity == "Reject_Order"
        assert d.expected == "MSC must contain a Reject_Order arrow."
        assert d.observed == "Only Confirm arrow is drawn."
        assert d.evidence_location == "p. 7, 3.4.1, MSC"
        # No quality-missing flags should have been set by the validator.
        for flag in (
            "missing_entity",
            "missing_expected",
            "missing_observed",
            "missing_evidence",
            "missing_evidence_location",
        ):
            assert flag not in d.flags

    def test_scribe_consolidation_preserves_quality_fields(self) -> None:
        """Regression for the field-drop bug in
        ``ScribeAgent.consolidate()``. When the meeting LLM returns
        ``consolidated_defects`` carrying entity / expected / observed /
        evidence_location, those fields must survive into the resulting
        ``MeetingOutput.consolidated_defects`` — otherwise final_defects.json
        loses final-reporting context after meeting consolidation."""
        from fagan_tool.agents.scribe_agent import ScribeAgent

        consolidated = {
            "consolidated_defects": [
                {
                    "position": "3.4.1",
                    "page_hint": "p. 7",
                    "risk": "A",
                    "fault_type": "M",
                    "description": "'Reject_Order': signal is missing.",
                    "evidence": "MSC 3.4.1 has no reject arrow.",
                    "confidence": 0.9,
                    "flags": [],
                    "entity": "Reject_Order",
                    "expected": "MSC must include a Reject_Order arrow.",
                    "observed": "Only the Confirm arrow is drawn.",
                    "evidence_location": "p. 7, 3.4.1, MSC",
                }
            ],
            "duplicates_removed": 0,
            "conflicts_flagged": 0,
            "minutes": "stub",
            "exit_decision": "Accept",
        }

        agent = ScribeAgent.__new__(ScribeAgent)
        agent.prompt_dir = Path("prompts")
        agent.debug_dir = None
        agent.provider = None
        agent.load_prompt = lambda name: "stub system prompt"
        agent.call_llm = lambda u, s, response_format=None: _json.dumps(consolidated)
        agent.extract_json_from_response = (
            lambda resp, context="": _json.loads(resp)
        )

        reviewer_outputs = [
            ReviewerOutput(
                reviewer_id="reviewer_1_pbr_tester",
                technique=ReadingTechnique.PBR_TESTER,
                defects=[
                    Defect(
                        id="reviewer_1_pbr_tester_aaa",
                        position="3.4.1",
                        page_hint="p. 7",
                        risk=RiskLevel.A,
                        fault_type=FaultType.M,
                        description="'Reject_Order': signal is missing.",
                        evidence="no reject arrow in MSC",
                        entity="Reject_Order",
                        expected="MSC must include a Reject_Order arrow.",
                        observed="Only the Confirm arrow is drawn.",
                        evidence_location="p. 7, 3.4.1, MSC",
                    )
                ],
                notes="",
            )
        ]

        meeting = agent.consolidate(reviewer_outputs)
        # Find the consolidated entry for Reject_Order — it must keep all
        # four quality fields.
        match = next(
            (d for d in meeting.consolidated_defects if d.entity == "Reject_Order"),
            None,
        )
        assert match is not None, "Reject_Order consolidated defect dropped"
        assert match.entity == "Reject_Order"
        assert match.expected == "MSC must include a Reject_Order arrow."
        assert match.observed == "Only the Confirm arrow is drawn."
        assert match.evidence_location == "p. 7, 3.4.1, MSC"
        # And the validator must NOT mark these as missing.
        for flag in (
            "missing_entity",
            "missing_expected",
            "missing_observed",
            "missing_evidence_location",
        ):
            assert flag not in match.flags

    def test_scribe_consolidation_flags_missing_quality_fields(self) -> None:
        """When the meeting LLM omits the four quality fields, the
        Defect validator must still flag them as missing — proof that
        scribe.consolidate() does not silently fill defaults."""
        from fagan_tool.agents.scribe_agent import ScribeAgent

        consolidated = {
            "consolidated_defects": [
                {
                    "position": "3.4.1",
                    "page_hint": "p. 7",
                    "risk": "A",
                    "fault_type": "M",
                    "description": "Generic defect without quality fields.",
                    "evidence": "x",
                    "confidence": 0.8,
                    "flags": [],
                    # entity / expected / observed / evidence_location
                    # intentionally absent
                }
            ],
            "duplicates_removed": 0,
            "conflicts_flagged": 0,
            "minutes": "stub",
            "exit_decision": "Accept",
        }

        agent = ScribeAgent.__new__(ScribeAgent)
        agent.prompt_dir = Path("prompts")
        agent.debug_dir = None
        agent.provider = None
        agent.load_prompt = lambda name: "stub system prompt"
        agent.call_llm = lambda u, s, response_format=None: _json.dumps(consolidated)
        agent.extract_json_from_response = (
            lambda resp, context="": _json.loads(resp)
        )

        # Minimal reviewer outputs — content unimportant; the consolidated
        # LLM defect drives the assertions.
        reviewer_outputs = [
            ReviewerOutput(
                reviewer_id="reviewer_1_pbr_user",
                technique=ReadingTechnique.PBR_USER,
                defects=[
                    Defect(
                        id="reviewer_1_pbr_user_xxx",
                        position="3.4.1",
                        page_hint="p. 7",
                        risk=RiskLevel.A,
                        fault_type=FaultType.M,
                        description="Generic defect without quality fields.",
                        evidence="x",
                    )
                ],
                notes="",
            )
        ]

        meeting = agent.consolidate(reviewer_outputs)
        match = next(
            (
                d
                for d in meeting.consolidated_defects
                if d.description.startswith("Generic defect without")
            ),
            None,
        )
        assert match is not None
        assert match.entity is None
        assert match.expected is None
        assert match.observed is None
        # evidence_location is auto-derived from page_hint + position —
        # so it will NOT be flagged missing in the schema. We assert the
        # other three.
        assert "missing_entity" in match.flags
        assert "missing_expected" in match.flags
        assert "missing_observed" in match.flags

    def test_missing_quality_payload_still_yields_validator_flags(self) -> None:
        """If the LLM omits entity/expected/observed/evidence_location, the
        schema validator must mark them as missing — proving the mapping
        no longer silently swallows the fields (because if it did, the
        same flag set would appear even when the LLM supplied them)."""
        canned = {
            "defects": [
                {
                    "position": "3.4.1",
                    "page_hint": "p. 7",
                    "risk": "A",
                    "fault_type": "M",
                    "description": "Generic finding without quoted prefix.",
                    "evidence": "x",
                    "confidence": 0.8,
                    "flags": [],
                }
            ],
            "notes": "x",
        }
        agent = self._make_agent_with_canned_json(canned)
        output = agent.inspect(artifacts=[], extra_context="")
        d = output.defects[0]
        assert d.entity is None
        assert d.expected is None
        assert d.observed is None
        # evidence_location is auto-derived from page_hint + position.
        assert d.evidence_location == "p. 7, 3.4.1"
        assert "missing_entity" in d.flags
        assert "missing_expected" in d.flags
        assert "missing_observed" in d.flags


# ---------------------------------------------------------------------------
# Prompt rules for expected/observed are present in CBR and UBR
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prompt_name", ["reviewer_ubr.txt", "reviewer_cbr.txt"])
def test_reviewer_prompt_mandates_expected_observed(prompt_name: str) -> None:
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    # Both fields are listed as required in the Mandatory Fields block.
    assert "**expected**" in text
    assert "**observed**" in text
    # The do-not-log rule for expected/observed must be explicit.
    lowered = text.lower()
    assert "expected" in lowered and "observed" in lowered
    assert "do-not-log rule" in lowered or "do not log" in lowered
    # The JSON example must show both keys so the LLM has something to copy.
    assert '"expected"' in text
    assert '"observed"' in text


# ---------------------------------------------------------------------------
# Record-quality repair loop (warn vs repair, drop semantics)
# ---------------------------------------------------------------------------


class _CannedLLM:
    """Sequence-of-responses LLM stub.

    Each call to ``call_llm`` consumes the next canned JSON string and
    records its (user_message, system_prompt) for later inspection. Tests
    use this to assert how many LLM round-trips the agent actually made.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, user_message, system_prompt, response_format=None):
        self.calls.append((user_message, system_prompt))
        if not self.responses:
            raise AssertionError("LLM stub exhausted: no canned response left")
        return self.responses.pop(0)


def _make_agent(mode: str, canned_responses):
    agent = ReviewerAgent.__new__(ReviewerAgent)
    agent.reviewer_id = "reviewer_repair_test"
    agent.technique = ReadingTechnique.UBR
    agent.prompt_dir = Path("prompts")
    agent.debug_dir = None
    agent.provider = None
    agent.record_quality_mode = mode
    agent.load_prompt = lambda name: "stub {technique} {extra_context}"
    agent._format_artifacts = lambda artifacts: "stub artefact text"
    canned = _CannedLLM(canned_responses)
    agent.call_llm = canned
    agent.extract_json_from_response = lambda resp, context="": _json.loads(resp)
    return agent, canned


class TestRecordQualityRepairLoop:
    """The repair loop fills expected/observed via a single follow-up
    LLM call (when ``record_quality_mode == 'repair'``) or drops the
    defect if it still lacks the fields after the round-trip."""

    INITIAL_INCOMPLETE = {
        "defects": [
            {
                "position": "3.4.1",
                "page_hint": "p. 7",
                "risk": "A",
                "fault_type": "M",
                "description": "'Reject_Order': missing in MSC.",
                "evidence": "MSC 3.4.1 has no reject arrow.",
                "entity": "Reject_Order",
                "evidence_location": "p. 7, 3.4.1, MSC",
                # expected & observed intentionally omitted
                "confidence": 0.9,
                "flags": [],
            }
        ],
        "notes": "first pass",
    }

    def test_warn_mode_makes_no_second_call(self) -> None:
        agent, canned = _make_agent(
            mode="warn",
            canned_responses=[_json.dumps(self.INITIAL_INCOMPLETE)],
        )
        output = agent.inspect(artifacts=[], extra_context="")
        # exactly one LLM call, defect preserved with missing flags.
        assert len(canned.calls) == 1
        assert len(output.defects) == 1
        d = output.defects[0]
        assert d.expected is None
        assert d.observed is None
        assert "missing_expected" in d.flags
        assert "missing_observed" in d.flags

    def test_repair_mode_fills_expected_observed(self) -> None:
        # The second canned response answers the repair call. The model
        # echoes the id and supplies expected/observed grounded in the
        # artefacts.
        repaired = {
            "defects": [
                {
                    # id is set inside inspect() to f"{reviewer_id}_{uuid8}";
                    # we cannot know it ahead of time, so the test fills it
                    # in dynamically (see assertion code below).
                    "id": "__PLACEHOLDER__",
                    "position": "3.4.1",
                    "description": "'Reject_Order': missing in MSC.",
                    "expected": "MSC must contain a Reject_Order arrow.",
                    "observed": "Only Confirm arrow is drawn.",
                }
            ],
            "notes": "repaired",
        }

        # We will need to know the generated defect id to make the second
        # response correlate. The simplest way is to intercept the first
        # call, then patch the second canned response just-in-time.
        first = _json.dumps(self.INITIAL_INCOMPLETE)

        class _TwoStageLLM:
            def __init__(self):
                self.calls = []
                self._first = first
                self.agent_ref = None

            def __call__(self, user_message, system_prompt, response_format=None):
                self.calls.append((user_message, system_prompt))
                if len(self.calls) == 1:
                    return self._first
                # Second call → look at the user_message to recover the id.
                import re
                m = re.search(r'"id":\s*"([^"]+)"', user_message)
                assert m, "repair payload should include the defect id"
                rid = m.group(1)
                payload = _json.loads(_json.dumps(repaired))
                payload["defects"][0]["id"] = rid
                return _json.dumps(payload)

        agent = ReviewerAgent.__new__(ReviewerAgent)
        agent.reviewer_id = "reviewer_repair_test"
        agent.technique = ReadingTechnique.UBR
        agent.prompt_dir = Path("prompts")
        agent.debug_dir = None
        agent.provider = None
        agent.record_quality_mode = "repair"
        agent.load_prompt = lambda name: "stub {technique} {extra_context}"
        agent._format_artifacts = lambda artifacts: "stub artefact text"
        llm = _TwoStageLLM()
        agent.call_llm = llm
        agent.extract_json_from_response = lambda resp, context="": _json.loads(resp)

        output = agent.inspect(artifacts=[], extra_context="")
        assert len(llm.calls) == 2  # exactly one repair retry
        assert len(output.defects) == 1
        d = output.defects[0]
        assert d.expected == "MSC must contain a Reject_Order arrow."
        assert d.observed == "Only Confirm arrow is drawn."
        assert "missing_expected" not in d.flags
        assert "missing_observed" not in d.flags

    def test_repair_mode_falls_back_when_repair_still_empty(self) -> None:
        """Safety net: if the model echoes back empty expected/observed,
        we do NOT drop the defect — we fall back to warn-mode behaviour
        (original defect preserved, missing_* flags intact). This
        prevents real runs from collapsing to 0 defects when the repair
        call misbehaves."""
        repair_empty = {
            "defects": [
                {
                    # Model echoes back with empty expected/observed —
                    # fallback path keeps the original defect.
                    "id": "__PLACEHOLDER__",
                    "expected": "",
                    "observed": "   ",
                }
            ],
            "notes": "still empty",
        }
        first = _json.dumps(self.INITIAL_INCOMPLETE)

        class _TwoStageLLM:
            def __init__(self):
                self.calls = []

            def __call__(self, user_message, system_prompt, response_format=None):
                self.calls.append((user_message, system_prompt))
                if len(self.calls) == 1:
                    return first
                import re
                m = re.search(r'"id":\s*"([^"]+)"', user_message)
                payload = _json.loads(_json.dumps(repair_empty))
                payload["defects"][0]["id"] = m.group(1)
                return _json.dumps(payload)

        agent = ReviewerAgent.__new__(ReviewerAgent)
        agent.reviewer_id = "reviewer_repair_test"
        agent.technique = ReadingTechnique.UBR
        agent.prompt_dir = Path("prompts")
        agent.debug_dir = None
        agent.provider = None
        agent.record_quality_mode = "repair"
        agent.load_prompt = lambda name: "stub {technique} {extra_context}"
        agent._format_artifacts = lambda artifacts: "stub artefact text"
        llm = _TwoStageLLM()
        agent.call_llm = llm
        agent.extract_json_from_response = lambda resp, context="": _json.loads(resp)

        output = agent.inspect(artifacts=[], extra_context="")
        assert len(llm.calls) == 2
        # Fallback: original defect kept; expected/observed are now
        # deterministically paraphrased from the defect text so the
        # record is evaluable. missing_* flags are removed; the audit
        # flag "auto_expected_observed_from_text" is added.
        assert len(output.defects) == 1
        d = output.defects[0]
        assert d.entity == "Reject_Order"
        assert d.expected and "Reject_Order" in d.expected
        assert d.observed and "MSC 3.4.1" in d.observed
        assert "missing_expected" not in d.flags
        assert "missing_observed" not in d.flags
        assert "auto_expected_observed_from_text" in d.flags

    def test_repair_mode_falls_back_when_model_omits_all_defects(self) -> None:
        """If the model returns an empty defects list, we fall back to
        the original defects (with autofilled expected/observed) rather
        than emitting an empty run."""
        repair_omits = {"defects": [], "notes": "no longer reportable"}
        first = _json.dumps(self.INITIAL_INCOMPLETE)
        agent, canned = _make_agent(
            mode="repair",
            canned_responses=[first, _json.dumps(repair_omits)],
        )
        output = agent.inspect(artifacts=[], extra_context="")
        assert len(canned.calls) == 2
        assert len(output.defects) == 1
        d = output.defects[0]
        assert d.expected and "Reject_Order" in d.expected
        assert d.observed
        assert "missing_expected" not in d.flags
        assert "auto_expected_observed_from_text" in d.flags

    def test_repair_mode_falls_back_when_repair_call_errors(self) -> None:
        """If the repair LLM call raises, the agent must keep the
        original defects (no silent drop-to-zero)."""
        first = _json.dumps(self.INITIAL_INCOMPLETE)

        class _ErrorOnRepair:
            def __init__(self):
                self.calls = []

            def __call__(self, user_message, system_prompt, response_format=None):
                self.calls.append((user_message, system_prompt))
                if len(self.calls) == 1:
                    return first
                # Second call raises a parse error.
                raise ValueError("simulated repair JSON failure")

        agent = ReviewerAgent.__new__(ReviewerAgent)
        agent.reviewer_id = "reviewer_repair_test"
        agent.technique = ReadingTechnique.UBR
        agent.prompt_dir = Path("prompts")
        agent.debug_dir = None
        agent.provider = None
        agent.record_quality_mode = "repair"
        agent.load_prompt = lambda name: "stub {technique} {extra_context}"
        agent._format_artifacts = lambda artifacts: "stub artefact text"
        llm = _ErrorOnRepair()
        agent.call_llm = llm
        agent.extract_json_from_response = lambda resp, context="": _json.loads(resp)

        output = agent.inspect(artifacts=[], extra_context="")
        assert len(llm.calls) == 2
        # Fallback: keep the original defect; expected/observed are
        # autofilled from the defect text.
        assert len(output.defects) == 1
        d = output.defects[0]
        assert d.entity == "Reject_Order"
        assert d.expected and d.observed
        assert "missing_expected" not in d.flags
        assert "missing_observed" not in d.flags
        assert "auto_expected_observed_from_text" in d.flags

    def test_repair_mode_partial_keeps_repaired_drops_unrepaired(self) -> None:
        """When the model salvages SOME but not all defects, we keep the
        salvaged ones (filled expected/observed) and drop only the
        unrepaired ones. We do NOT fall back here — partial progress is
        progress."""
        # Three incomplete defects in the initial response.
        first = {
            "defects": [
                {
                    "position": "3.4.1",
                    "page_hint": "p. 5",
                    "risk": "A",
                    "fault_type": "M",
                    "description": "'Reject_Order': missing in MSC.",
                    "evidence": "no reject arrow",
                    "entity": "Reject_Order",
                    "evidence_location": "p. 5, 3.4.1",
                    "confidence": 0.9,
                    "flags": [],
                },
                {
                    "position": "3.4.2",
                    "page_hint": "p. 6",
                    "risk": "B",
                    "fault_type": "W",
                    "description": "'Confirm_Voice': wrong params.",
                    "evidence": "param mismatch with Table 1",
                    "entity": "Confirm_Voice",
                    "evidence_location": "p. 6, 3.4.2",
                    "confidence": 0.85,
                    "flags": [],
                },
                {
                    "position": "Table 1",
                    "page_hint": "p. 2",
                    "risk": "C",
                    "fault_type": "M",
                    "description": "'ZoneInfo': not listed in Table 1.",
                    "evidence": "no ZoneInfo row",
                    "entity": "ZoneInfo",
                    "evidence_location": "p. 2, Table 1",
                    "confidence": 0.8,
                    "flags": [],
                },
            ],
            "notes": "x",
        }

        class _PartialRepair:
            def __init__(self):
                self.calls = []

            def __call__(self, user_message, system_prompt, response_format=None):
                self.calls.append((user_message, system_prompt))
                if len(self.calls) == 1:
                    return _json.dumps(first)
                # Second call: extract all ids in the same order they
                # appear in the payload, then return repaired entries
                # ONLY for the first two (third gets dropped).
                import re
                ids = re.findall(r'"id":\s*"([^"]+)"', user_message)
                assert len(ids) == 3
                repaired = {
                    "defects": [
                        {
                            "id": ids[0],
                            "expected": "Reject_Order should be present in the MSC at p. 5, 3.4.1.",
                            "observed": "Reject_Order is missing from the MSC at p. 5, 3.4.1.",
                        },
                        {
                            "id": ids[1],
                            "expected": "Confirm_Voice parameters should match Table 1.",
                            "observed": "Confirm_Voice parameters do not match Table 1 at p. 6, 3.4.2.",
                        },
                        # Third id omitted entirely → drop candidate.
                    ],
                    "notes": "partial",
                }
                return _json.dumps(repaired)

        agent = ReviewerAgent.__new__(ReviewerAgent)
        agent.reviewer_id = "reviewer_repair_test"
        agent.technique = ReadingTechnique.UBR
        agent.prompt_dir = Path("prompts")
        agent.debug_dir = None
        agent.provider = None
        agent.record_quality_mode = "repair"
        agent.load_prompt = lambda name: "stub {technique} {extra_context}"
        agent._format_artifacts = lambda artifacts: "stub artefact text"
        llm = _PartialRepair()
        agent.call_llm = llm
        agent.extract_json_from_response = lambda resp, context="": _json.loads(resp)

        output = agent.inspect(artifacts=[], extra_context="")
        assert len(llm.calls) == 2
        # Two repaired defects kept, one omitted defect dropped.
        kept_ids = [d.entity for d in output.defects]
        assert kept_ids == ["Reject_Order", "Confirm_Voice"]
        for d in output.defects:
            assert d.expected
            assert d.observed
            assert "missing_expected" not in d.flags
            assert "missing_observed" not in d.flags

    def test_repair_mode_passes_through_already_complete_defects(self) -> None:
        """No extra LLM call when every defect already has expected/observed."""
        already_complete = {
            "defects": [
                {
                    "position": "3.4.1",
                    "page_hint": "p. 7",
                    "risk": "A",
                    "fault_type": "M",
                    "description": "'Reject_Order': missing in MSC.",
                    "evidence": "MSC 3.4.1 has no reject arrow.",
                    "entity": "Reject_Order",
                    "evidence_location": "p. 7, 3.4.1, MSC",
                    "expected": "MSC must contain a Reject_Order arrow.",
                    "observed": "Only Confirm arrow is drawn.",
                    "confidence": 0.9,
                    "flags": [],
                }
            ],
            "notes": "ok",
        }
        agent, canned = _make_agent(
            mode="repair",
            canned_responses=[_json.dumps(already_complete)],
        )
        output = agent.inspect(artifacts=[], extra_context="")
        # Only the original call — no repair was needed.
        assert len(canned.calls) == 1
        assert len(output.defects) == 1
        d = output.defects[0]
        assert d.expected == "MSC must contain a Reject_Order arrow."
        assert d.observed == "Only Confirm arrow is drawn."


def test_invalid_record_quality_mode_rejected() -> None:
    """ReviewerAgent.__init__ must reject unknown modes."""
    with pytest.raises(ValueError):
        ReviewerAgent(
            provider=None,
            reviewer_id="r",
            technique=ReadingTechnique.UBR,
            prompt_dir=Path("prompts"),
            record_quality_mode="bogus",
        )


# ---------------------------------------------------------------------------
# STRICT INSPECTION RECORD FORMAT block must be present in every prompt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prompt_name", REVIEWER_PROMPTS)
def test_reviewer_prompt_has_strict_record_block(prompt_name: str) -> None:
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    assert "STRICT INSPECTION RECORD FORMAT" in text
    # Explicit Do-not-log rule (DE + EN sentinels)
    assert "Do-not-log rule" in text
    assert "Defekt nicht melden wenn" in text
    # Forbidden placeholders enumerated
    assert '"unknown"' in text
    assert '"n/a"' in text
    assert '"UNK"' in text
    # Forbidden gold/fault-list reference rule
    assert "gold standard" in text
    assert "fault list" in text
