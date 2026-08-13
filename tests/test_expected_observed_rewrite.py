"""Deterministic Soll-from-Ist rewrite for the autofill fallback.

When ``_paraphrase_expected_observed_from_defect`` fills the
``observed`` field from evidence/description (audit flag
``auto_expected_observed_from_text``), the previous behaviour was to
write a generic ``expected`` sentence keyed only to ``fault_type``
("Expected: '<entity>' should be present/defined as specified."). That
text was too vague for final evaluation.

The new behaviour: try to derive ``expected`` deterministically from
``observed`` by flipping the negation/verb token onto its affirmative
form. If no rule matches, the previous generic Soll-statement remains
the fallback. No new facts are invented in either path.

These tests cover the four documented rules
(``does not include`` → ``should include``, ``is missing`` →
``is present/defined``, ``is not defined`` → ``is defined``,
``lacks`` → ``has``), plus the no-match fallback and the audit-flag
preservation.
"""

from __future__ import annotations

import pytest

from fagan_tool.agents.reviewer_agent import (
    ReviewerAgent,
    _derive_expected_from_observed,
)
from fagan_tool.core.schemas import (
    Defect,
    FaultType,
    ReadingTechnique,
    RiskLevel,
)


# ---------------------------------------------------------------------------
# _derive_expected_from_observed unit tests
# ---------------------------------------------------------------------------


class TestDeriveExpectedHelper:
    def test_does_not_include_becomes_should_include(self) -> None:
        observed = "The MSC does not include a reject signal in 3.4.1."
        derived = _derive_expected_from_observed(observed)
        assert derived is not None
        assert "should include" in derived.lower()
        assert "does not include" not in derived.lower()
        # Surroundings preserved.
        assert "reject signal" in derived.lower()
        assert "3.4.1" in derived

    def test_is_missing_becomes_is_present_or_defined(self) -> None:
        observed = "Timeout is missing for order acceptance."
        derived = _derive_expected_from_observed(observed)
        assert derived is not None
        assert "is present/defined" in derived.lower()
        assert "is missing" not in derived.lower()

    def test_is_not_defined_becomes_is_defined(self) -> None:
        observed = "Reject_Order is not defined in the API."
        derived = _derive_expected_from_observed(observed)
        assert derived is not None
        assert "is defined" in derived.lower()
        assert "is not defined" not in derived.lower()

    def test_lacks_becomes_has(self) -> None:
        observed = "The design lacks feedback for cancellations."
        derived = _derive_expected_from_observed(observed)
        assert derived is not None
        assert " has " in derived.lower()
        assert "lacks" not in derived.lower()

    def test_no_match_returns_none(self) -> None:
        observed = "Some opaque sentence with no matching pattern."
        assert _derive_expected_from_observed(observed) is None

    def test_empty_input_returns_none(self) -> None:
        assert _derive_expected_from_observed("") is None
        assert _derive_expected_from_observed("   ") is None

    def test_derived_text_terminated_with_period(self) -> None:
        observed = "The MSC does not include a reject signal"  # no period
        derived = _derive_expected_from_observed(observed)
        assert derived is not None
        assert derived.endswith(".")


# ---------------------------------------------------------------------------
# Integration via _paraphrase_expected_observed_from_defect
# ---------------------------------------------------------------------------


def _make_pbr_defect(*, evidence, entity="Reject_Order",
                     fault_type=FaultType.M):
    return Defect(
        id="t",
        position="3.4.1",
        page_hint="p. 7",
        description=f"'{entity}': old description",
        evidence=evidence,
        entity=entity,
        risk=RiskLevel.A,
        fault_type=fault_type,
        technique=ReadingTechnique.PBR_TESTER,
    )


class TestParaphraseExpectedDerived:
    """End-to-end: when observed gets autofilled from evidence and the
    rewrite rules match, expected must be the derived Soll-statement
    rather than the generic fallback."""

    def test_derived_expected_when_observed_contains_does_not_include(self) -> None:
        d = _make_pbr_defect(
            evidence="The MSC does not include a reject signal in 3.4.1.",
            entity="Reject_Order",
        )
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        assert ok is True
        # observed populated from evidence.
        assert d.observed == "The MSC does not include a reject signal in 3.4.1."
        # expected derived (NOT the generic Soll-sentence).
        assert "should include" in d.expected.lower()
        assert "should be present/defined" not in d.expected
        # Audit flag still set.
        assert "auto_expected_observed_from_text" in d.flags

    def test_derived_expected_when_observed_contains_is_missing(self) -> None:
        d = _make_pbr_defect(
            evidence="Timeout is missing for order acceptance.",
            entity="Order",
        )
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        assert ok is True
        assert "is present/defined" in d.expected.lower()
        assert "auto_expected_observed_from_text" in d.flags

    def test_derived_expected_when_observed_contains_lacks(self) -> None:
        d = _make_pbr_defect(
            evidence="The design lacks feedback for cancellations.",
            entity="Order_Cancel",
        )
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        assert ok is True
        assert " has " in d.expected.lower()
        assert "auto_expected_observed_from_text" in d.flags

    def test_fallback_to_generic_when_no_pattern_matches(self) -> None:
        d = _make_pbr_defect(
            evidence="Some opaque sentence with no matching pattern.",
            entity="X",
            fault_type=FaultType.M,
        )
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        assert ok is True
        # Generic fallback for M-faults.
        assert d.expected == (
            "Expected: 'X' should be present/defined as specified."
        )
        # observed still autofilled from evidence.
        assert d.observed == "Some opaque sentence with no matching pattern."
        assert "auto_expected_observed_from_text" in d.flags

    def test_fallback_w_fault_when_no_pattern_matches(self) -> None:
        d = _make_pbr_defect(
            evidence="Table 1 parameter count does not equal MSC arrow count.",
            entity="Confirm",
            fault_type=FaultType.W,
        )
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        assert ok is True
        # No rule matches (no "does not include", "is missing", "is not
        # defined", or "lacks"). Generic W-form is the fallback.
        assert d.expected == (
            "Expected: 'Confirm' should match the specification/definition."
        )
        assert "auto_expected_observed_from_text" in d.flags

    def test_does_not_touch_observed_or_evidence_location(self) -> None:
        original_evidence = "The MSC does not include a reject signal in 3.4.1."
        d = _make_pbr_defect(
            evidence=original_evidence,
            entity="Reject_Order",
        )
        ok = ReviewerAgent._paraphrase_expected_observed_from_defect(d)
        assert ok is True
        # observed is populated from evidence — that IS the spec — but
        # we should not have mutated evidence itself.
        if isinstance(d.evidence, dict):
            assert d.evidence.get("quote_or_paraphrase") == original_evidence
        else:
            assert d.evidence == original_evidence
        # And evidence_location was deterministically composed from
        # page_hint + position by the schema validator; the rewrite must
        # not touch it.
        assert d.evidence_location == "p. 7, 3.4.1"
