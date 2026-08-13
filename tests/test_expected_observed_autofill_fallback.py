"""Deterministic expected/observed paraphrase in the repair fallback path.

When ``record_quality_mode="repair"`` falls back (LLM error, empty
repair response, all returned defects still empty), the original
defects are kept — and now also receive an autofilled expected/observed
pair derived deterministically from their own text. No new facts are
invented: ``expected`` is a short Soll-sentence keyed to ``fault_type``,
``observed`` is the existing ``evidence.quote_or_paraphrase`` (or raw
evidence / description) verbatim.

These tests cover the three scenarios called out in the spec:

1. repair mode + unusable repair response → defects survive, with
   expected/observed filled and the audit flag set.
2. warn mode → no autofill (historical behaviour preserved).
3. defect without any text → autofill is a no-op, flags untouched.

Plus a handful of helper unit tests that exercise dict input, fault_type
variants, and the no-overwrite guarantee.
"""

from __future__ import annotations

import json as _json
from pathlib import Path

import pytest

from fagan_tool.agents.reviewer_agent import ReviewerAgent
from fagan_tool.core.schemas import (
    Defect,
    FaultType,
    ReadingTechnique,
    ReviewerOutput,
    RiskLevel,
)


# ---------------------------------------------------------------------------
# Direct helper unit tests
# ---------------------------------------------------------------------------


class TestParaphraseHelperUnit:
    def test_fills_missing_M_fault(self) -> None:
        d = Defect(
            id="u_1",
            position="3.4.1",
            page_hint="p. 5",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="'Reject_Order': A signal is missing for not confirming orders.",
            evidence="MSC 3.4.1 has no reject arrow.",
            entity="Reject_Order",
        )
        assert d.expected is None and d.observed is None
        assert "missing_expected" in d.flags
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        assert ok is True
        assert d.expected == (
            "Expected: 'Reject_Order' should be present/defined as specified."
        )
        assert d.observed == "MSC 3.4.1 has no reject arrow."
        assert "missing_expected" not in d.flags
        assert "missing_observed" not in d.flags
        assert "auto_expected_observed_from_text" in d.flags

    def test_fills_missing_W_fault(self) -> None:
        d = Defect(
            id="u_2",
            position="3.4.2",
            page_hint="p. 6",
            risk=RiskLevel.B,
            fault_type=FaultType.W,
            description="'Confirm_Voice' has wrong parameter count.",
            evidence="Table 1 lists 3 params; MSC arrow uses 2.",
            entity="Confirm_Voice",
        )
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        assert ok is True
        assert "Confirm_Voice" in d.expected
        assert "match the specification" in d.expected
        assert d.observed == "Table 1 lists 3 params; MSC arrow uses 2."

    def test_no_overwrite_when_fields_already_set(self) -> None:
        d = Defect(
            id="u_3",
            position="3.4.1",
            page_hint="p. 5",
            description="'X': missing",
            evidence="x",
            entity="X",
            expected="user-provided expected",
            observed="user-provided observed",
        )
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        # Nothing to fill — both already populated.
        assert ok is False
        assert d.expected == "user-provided expected"
        assert d.observed == "user-provided observed"
        assert "auto_expected_observed_from_text" not in d.flags

    def test_dict_with_missing_fields_autofilled(self) -> None:
        d = {
            "entity": "Cancel_Order",
            "fault_type": "M",
            "description": "'Cancel_Order': missing in MSC.",
            "evidence": "No cancel arrow at p. 7.",
            "flags": ["missing_expected", "missing_observed"],
        }
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        assert ok is True
        assert "Cancel_Order" in d["expected"]
        assert d["observed"] == "No cancel arrow at p. 7."
        assert "missing_expected" not in d["flags"]
        assert "missing_observed" not in d["flags"]
        assert "auto_expected_observed_from_text" in d["flags"]

    def test_dict_with_evidence_dict_uses_quote(self) -> None:
        d = {
            "entity": "Ack",
            "fault_type": "M",
            "description": "'Ack' missing",
            "evidence": {"quote_or_paraphrase": "MSC arrow Ack absent", "page_hint": "p. 6"},
            "flags": ["missing_observed"],
        }
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        assert ok is True
        assert d["observed"] == "MSC arrow Ack absent"

    def test_empty_defect_is_no_op(self) -> None:
        """Spec: if there is no defect text at all, do nothing and leave
        the missing_* flags intact."""
        d = {
            "entity": "",
            "description": "",
            "evidence": "",
            "flags": ["missing_expected", "missing_observed"],
        }
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        assert ok is False
        assert d.get("expected") in (None, "")
        assert d.get("observed") in (None, "")
        assert "missing_expected" in d["flags"]
        assert "missing_observed" in d["flags"]
        assert "auto_expected_observed_from_text" not in d["flags"]

    def test_no_entity_uses_generic_placeholder(self) -> None:
        d = {
            "fault_type": "M",
            "description": "Something is missing.",
            "evidence": "The relevant section is silent.",
            "flags": ["missing_expected", "missing_observed"],
        }
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        assert ok is True
        assert "the described item" in d["expected"]


# ---------------------------------------------------------------------------
# Repair-mode fallback paths: end-to-end via agent.inspect()
# ---------------------------------------------------------------------------


def _make_agent(mode: str, canned_responses):
    """Build a ReviewerAgent with a canned sequence of LLM responses.

    The stub avoids any real network call and lets each test assert how
    many round-trips actually happened.
    """
    agent = ReviewerAgent.__new__(ReviewerAgent)
    agent.reviewer_id = "reviewer_autofill_test"
    agent.technique = ReadingTechnique.UBR
    agent.prompt_dir = Path("prompts")
    agent.debug_dir = None
    agent.provider = None
    agent.record_quality_mode = mode
    agent.load_prompt = lambda name: "stub {technique} {extra_context}"
    agent._format_artifacts = lambda artifacts: "stub artefact text"

    counter = {"i": 0}

    def _llm(user_message, system_prompt, response_format=None):
        i = counter["i"]
        counter["i"] += 1
        if i >= len(canned_responses):
            raise AssertionError("LLM stub exhausted: no canned response left")
        resp = canned_responses[i]
        return resp(user_message) if callable(resp) else resp

    agent.call_llm = _llm
    agent.extract_json_from_response = (
        lambda resp, context="": _json.loads(resp)
    )
    return agent, counter


INITIAL_INCOMPLETE = {
    "defects": [
        {
            "position": "3.4.1",
            "page_hint": "p. 7",
            "risk": "A",
            "fault_type": "M",
            "description": "'Reject_Order': A signal is missing for not confirming orders.",
            "evidence": "MSC 3.4.1 has no reject arrow.",
            "entity": "Reject_Order",
            "evidence_location": "p. 7, 3.4.1, MSC",
            "confidence": 0.9,
            "flags": [],
        }
    ],
    "notes": "first pass",
}


class TestRepairFallbackAutofill:
    def test_fallback_paraphrases_expected_and_observed(self) -> None:
        """Scenario 1: repair returns nothing usable; fallback now also
        autofills expected/observed from the defect text."""
        repair_empty = {"defects": [], "notes": "no longer reportable"}
        agent, _counter = _make_agent(
            mode="repair",
            canned_responses=[
                _json.dumps(INITIAL_INCOMPLETE),
                _json.dumps(repair_empty),
            ],
        )
        output = agent.inspect(artifacts=[], extra_context="")
        assert len(output.defects) == 1
        d = output.defects[0]
        # expected was filled deterministically from fault_type + entity.
        assert d.expected is not None and "Reject_Order" in d.expected
        assert "should be present/defined" in d.expected
        # observed was filled from the evidence string.
        assert d.observed == "MSC 3.4.1 has no reject arrow."
        # missing_* flags cleared; audit flag added.
        assert "missing_expected" not in d.flags
        assert "missing_observed" not in d.flags
        assert "auto_expected_observed_from_text" in d.flags

    def test_warn_mode_does_not_autofill(self) -> None:
        """Scenario 2: warn mode is unchanged — no second call, no
        autofill, the missing_* flags stay exactly as the validator set
        them."""
        agent, counter = _make_agent(
            mode="warn",
            canned_responses=[_json.dumps(INITIAL_INCOMPLETE)],
        )
        output = agent.inspect(artifacts=[], extra_context="")
        # Exactly one LLM call (no repair attempted, hence no fallback).
        assert counter["i"] == 1
        assert len(output.defects) == 1
        d = output.defects[0]
        assert d.expected is None
        assert d.observed is None
        assert "missing_expected" in d.flags
        assert "missing_observed" in d.flags
        assert "auto_expected_observed_from_text" not in d.flags

    def test_repair_call_error_falls_back_with_autofill(self) -> None:
        """If the repair LLM call raises, the agent must keep the
        original defects AND autofill expected/observed (no drop, no
        empty fields)."""
        def _raise(_user_message):
            raise ValueError("simulated repair JSON failure")

        agent, _counter = _make_agent(
            mode="repair",
            canned_responses=[_json.dumps(INITIAL_INCOMPLETE), _raise],
        )
        output = agent.inspect(artifacts=[], extra_context="")
        assert len(output.defects) == 1
        d = output.defects[0]
        assert d.expected and d.observed
        assert "missing_expected" not in d.flags
        assert "auto_expected_observed_from_text" in d.flags

    def test_completely_empty_defect_survives_without_autofill(self) -> None:
        """Scenario 3 (edge): a defect with no entity/description/evidence
        text passes through the fallback unmodified — autofill must not
        crash and missing_* flags stay in place."""
        # We construct the run by writing a sparse first response. The
        # Defect schema requires `description` to be non-empty in
        # principle, but the validator allows blank → it just flags
        # missing_description. Use one-space description to model the
        # "no usable text" edge.
        sparse_initial = {
            "defects": [
                {
                    "position": "unknown",
                    "page_hint": None,
                    "risk": "C",
                    "fault_type": "UNK",
                    "description": " ",
                    "evidence": " ",
                    "confidence": 0.5,
                    "flags": [],
                }
            ],
            "notes": "sparse",
        }
        repair_empty = {"defects": [], "notes": "n/a"}
        agent, _counter = _make_agent(
            mode="repair",
            canned_responses=[
                _json.dumps(sparse_initial),
                _json.dumps(repair_empty),
            ],
        )
        output = agent.inspect(artifacts=[], extra_context="")
        assert len(output.defects) == 1
        d = output.defects[0]
        assert d.expected is None
        assert d.observed is None
        assert "missing_expected" in d.flags
        assert "missing_observed" in d.flags
        # No autofill happened, so the audit flag must NOT be present.
        assert "auto_expected_observed_from_text" not in d.flags
