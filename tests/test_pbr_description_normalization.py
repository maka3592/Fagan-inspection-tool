"""Deterministic PBR description normalisation.

PBR reviewers tend to phrase findings in requirements-spec language
("not specified", "expected behavior not specified", "incomplete"),
which scores poorly against the gold standard's design-/MSC-style
vocabulary. ``_normalize_pbr_description`` in
``src/fagan_tool/core/process.py`` rewrites the existing defect text
(``observed`` > ``evidence.quote_or_paraphrase`` > ``description``)
into a more gold-near form. No new facts are invented.

Activation is opt-in via ``extra_config.pbr_description_normalize`` —
this test module also verifies that the call site in process.py
respects that flag (off by default).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fagan_tool.core.process import _normalize_pbr_description
from fagan_tool.core.schemas import (
    Defect,
    FaultType,
    ReadingTechnique,
    RiskLevel,
)


PROCESS_PATH = (
    Path(__file__).resolve().parents[1] / "src" / "fagan_tool" / "core" / "process.py"
)
PBR_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "experiments"
    / "pbr_same_n10.yaml"
)


def _make_pbr_defect(*, observed=None, evidence=None, description="x",
                     entity="Reject_Order",
                     technique=ReadingTechnique.PBR_TESTER) -> Defect:
    return Defect(
        id="t",
        position="3.4.1",
        page_hint="p. 5",
        description=description,
        evidence=evidence if evidence is not None else "stub evidence",
        observed=observed,
        entity=entity,
        risk=RiskLevel.A,
        fault_type=FaultType.M,
        technique=technique,
    )


# ---------------------------------------------------------------------------
# Helper behaviour: deterministic substitutions
# ---------------------------------------------------------------------------


class TestNormalizeAcknowledgmentPhrasing:
    def test_no_acknowledgment_is_specified(self) -> None:
        d = _make_pbr_defect(
            observed="No acknowledgment is specified for the allocate flow.",
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "missing acknowledgment" in d.description.lower()
        assert d.description.startswith("'Reject_Order':")
        assert "pbr_description_normalized" in d.flags

    def test_missing_acknowledgement_uk_spelling(self) -> None:
        d = _make_pbr_defect(
            observed="Missing acknowledgement after the order is placed.",
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        # The rule normalises both spellings to the US form.
        assert "missing acknowledgment" in d.description.lower()

    def test_missing_feedback_collapses_to_acknowledgment(self) -> None:
        d = _make_pbr_defect(observed="Missing feedback for the cancel flow.")
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "missing acknowledgment" in d.description.lower()


class TestNormalizeExpectedBehavior:
    def test_expected_behavior_not_specified(self) -> None:
        d = _make_pbr_defect(
            observed="Expected behavior for the error case is not specified.",
            entity="Reject_Order",
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "expected behavior is missing" in d.description.lower()


class TestNormalizeTimeout:
    def test_timeout_not_defined(self) -> None:
        d = _make_pbr_defect(
            observed="Timeout for Start_Voice is not defined.",
            entity="Start_Voice",
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "timeout is missing" in d.description.lower()


class TestNormalizeGenericNotSpecified:
    def test_is_not_specified_rewritten(self) -> None:
        d = _make_pbr_defect(
            observed="The Login signal is not specified in the MSC.",
            entity="Login",
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        # "is not specified" → "is missing"
        assert "is missing" in d.description.lower()
        assert "not specified" not in d.description.lower()

    def test_not_defined_rewritten(self) -> None:
        d = _make_pbr_defect(
            observed="The Confirm parameters not defined in Table 1.",
            entity="Confirm",
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "is missing" in d.description.lower()


class TestNormalizeNotDetailedDescribedDocumented:
    """Requirements-style "not detailed / described / documented" should
    standardise onto the gold vocabulary ``is missing``. The surrounding
    location adverbials ("in the design", "in the MSC", "for <name>")
    stay where the reviewer put them — we only standardise the verb."""

    def test_is_not_detailed_rewritten_to_is_missing(self) -> None:
        # The exact near-miss from the brief.
        d = _make_pbr_defect(
            observed="The handling of unallocated orders is not detailed in the design.",
            entity="Allocate_car",
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "is missing" in d.description.lower()
        # "is not detailed" must be gone (we only check the joined token
        # — the surrounding "in the design" suffix is preserved).
        assert "is not detailed" not in d.description.lower()
        assert d.description.startswith("'Allocate_car':")
        assert "pbr_description_normalized" in d.flags

    def test_is_not_described_rewritten_to_is_missing(self) -> None:
        d = _make_pbr_defect(
            observed="The error path is not described in the MSC.",
            entity="Reject_Order",
            technique=ReadingTechnique.PBR_DESIGNER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "is missing" in d.description.lower()
        assert "is not described" not in d.description.lower()

    def test_is_not_documented_rewritten_to_is_missing(self) -> None:
        d = _make_pbr_defect(
            observed="The validation flow is not documented for Login.",
            entity="Login",
            technique=ReadingTechnique.PBR_USER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "is missing" in d.description.lower()
        assert "is not documented" not in d.description.lower()


class TestNormalizeAddressCoverSpecifyDescribeState:
    """Active "does not address/cover/specify/describe/state …" and
    passive "is not addressed/covered/…" both standardise onto the
    gold-vocabulary verb "is missing". Surroundings (object clause,
    location adverbial) stay where the reviewer put them."""

    def test_does_not_address_rewritten_to_is_missing(self) -> None:
        # The exact near-miss from the brief.
        d = _make_pbr_defect(
            observed="Section 3.3.1 does not address what happens if a car cannot be allocated.",
            entity="Allocate_car",
            technique=ReadingTechnique.PBR_TESTER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "is missing" in d.description.lower()
        assert "does not address" not in d.description.lower()
        assert d.description.startswith("'Allocate_car':")
        assert "pbr_description_normalized" in d.flags

    def test_does_not_cover_rewritten_to_is_missing(self) -> None:
        d = _make_pbr_defect(
            observed="The design does not cover the cancellation path.",
            entity="Cancel_Order",
            technique=ReadingTechnique.PBR_DESIGNER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "is missing" in d.description.lower()
        assert "does not cover" not in d.description.lower()
        assert d.description.startswith("'Cancel_Order':")
        assert "pbr_description_normalized" in d.flags

    def test_is_not_addressed_rewritten_to_is_missing(self) -> None:
        d = _make_pbr_defect(
            observed="The validation step is not addressed in the design.",
            entity="Login",
            technique=ReadingTechnique.PBR_USER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "is missing" in d.description.lower()
        assert "is not addressed" not in d.description.lower()
        assert d.description.startswith("'Login':")
        assert "pbr_description_normalized" in d.flags


class TestNormalizeNotClearlyDefinedFamily:
    """Hedged "not clearly defined/specified/described/detailed/documented"
    phrasings standardise onto the gold-vocabulary verb "is missing".
    Surroundings (section ref, page hint, location adverbial) stay put."""

    def test_is_not_clearly_defined_rewritten_to_is_missing(self) -> None:
        # The exact near-miss from the brief.
        d = _make_pbr_defect(
            observed=(
                "The Order_Cancel signal is not clearly defined in section "
                "3.4.2 (p. 5)."
            ),
            entity="Order_Cancel",
            technique=ReadingTechnique.PBR_TESTER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "is missing" in d.description.lower()
        assert "not clearly defined" not in d.description.lower()
        # The location adverbial must survive — we only standardise the verb.
        assert "3.4.2" in d.description
        assert "p. 5" in d.description
        assert d.description.startswith("'Order_Cancel':")
        assert "pbr_description_normalized" in d.flags

    def test_not_clearly_specified_rewritten_to_is_missing(self) -> None:
        d = _make_pbr_defect(
            observed="The handling not clearly specified in the MSC.",
            entity="Allocate_car",
            technique=ReadingTechnique.PBR_DESIGNER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "is missing" in d.description.lower()
        assert "not clearly specified" not in d.description.lower()
        assert d.description.startswith("'Allocate_car':")
        assert "pbr_description_normalized" in d.flags

    def test_is_not_clearly_described_rewritten_to_is_missing(self) -> None:
        d = _make_pbr_defect(
            observed="The validation flow is not clearly described for Login.",
            entity="Login",
            technique=ReadingTechnique.PBR_USER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "is missing" in d.description.lower()
        assert "is not clearly described" not in d.description.lower()
        assert d.description.startswith("'Login':")
        assert "pbr_description_normalized" in d.flags


class TestNormalizeDoesNotProvideAndLocationNoise:
    """Two coordinated rewrites:

    1. "does not provide [implementation] details" → "is missing
       details" (specific) and "does not provide" → "is missing"
       (generic).
    2. Leading location noise ("Section 3.3.1, …", "In section 3.x, …",
       "p. 5, …") is stripped from the claim text because `position`
       and `evidence_location` already carry that information.
    """

    def test_section_noise_and_does_not_provide_implementation_details(self) -> None:
        # The exact near-miss from the brief.
        d = _make_pbr_defect(
            observed=(
                "Section 3.3.1 does not provide implementation details "
                "for unallocated orders."
            ),
            entity="Allocate_car",
            technique=ReadingTechnique.PBR_TESTER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        # Leading "Section 3.3.1" must be gone.
        assert "Section 3.3.1" not in d.description
        # And the verb cluster standardised.
        assert "is missing" in d.description.lower()
        assert "does not provide" not in d.description.lower()
        assert d.description.startswith("'Allocate_car':")
        assert "pbr_description_normalized" in d.flags

    def test_leading_in_section_noise_stripped(self) -> None:
        d = _make_pbr_defect(
            observed="In section 3.3.1, the validation flow is incomplete.",
            entity="Allocate_car",
            technique=ReadingTechnique.PBR_USER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "In section 3.3.1" not in d.description
        # The post-noise content is preserved.
        assert "validation flow" in d.description.lower()
        assert d.description.startswith("'Allocate_car':")

    def test_stacked_page_and_section_noise_stripped(self) -> None:
        d = _make_pbr_defect(
            observed=(
                "p. 5, Section 3.3.1 validation flow does not provide details."
            ),
            entity="Validation",
            technique=ReadingTechnique.PBR_DESIGNER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        # Both leading noises must be gone.
        assert "p. 5" not in d.description
        assert "Section 3.3.1" not in d.description
        # And "does not provide details" became "is missing details".
        assert "is missing details" in d.description.lower()
        assert d.description.startswith("'Validation':")

    def test_does_not_provide_without_details_becomes_is_missing(self) -> None:
        d = _make_pbr_defect(
            observed="The design does not provide a way to cancel orders.",
            entity="Cancel_Order",
            technique=ReadingTechnique.PBR_USER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "does not provide" not in d.description.lower()
        assert "is missing" in d.description.lower()


class TestNormalizeDoesNotDefine:
    """Active "does not define …" should standardise to "is missing".
    Same rationale as the existing "does not address/cover/…" rules —
    the verb cluster is rewritten, the object clause is preserved."""

    def test_does_not_define_rewritten_to_is_missing(self) -> None:
        # The exact near-miss from the brief (sweep gold_id=9, ~0.625).
        d = _make_pbr_defect(
            observed=(
                "The allocation process does not define what happens "
                "if no cars are available."
            ),
            entity="Allocate_car",
            technique=ReadingTechnique.PBR_TESTER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "is missing" in d.description.lower()
        assert "does not define" not in d.description.lower()
        # The object clause must survive — only the verb cluster is
        # rewritten.
        assert "what happens if no cars are available" in d.description.lower()
        assert d.description.startswith("'Allocate_car':")
        assert "pbr_description_normalized" in d.flags


class TestNormalizeLacksAndMissingTheTimeout:
    """Two more PBR verb cluster rewrites:

    1. "lacks <X>" → "is missing <X>" (the gold vocabulary uses
       "missing" as the canonical verb).
    2. "(is) missing the timeout" → "timeout is missing" (gold uses the
       subject-first phrasing).
    """

    def test_lacks_rewritten_to_is_missing(self) -> None:
        # The exact near-miss from the brief (sweep gold_id=8, ~0.633).
        d = _make_pbr_defect(
            observed="The design lacks feedback for order cancellations.",
            entity="Order_Cancel",
            technique=ReadingTechnique.PBR_TESTER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        # The verb is rewritten; the rest of the sentence is preserved.
        assert "is missing feedback" in d.description.lower()
        assert "lacks" not in d.description.lower()
        # And ensure the lacks-rule fires AFTER the acknowledgment rule
        # so "feedback" is not further collapsed into "acknowledgment".
        assert "feedback" in d.description.lower()
        assert d.description.startswith("'Order_Cancel':")
        assert "pbr_description_normalized" in d.flags

    def test_is_missing_the_timeout_pivots_to_subject_first(self) -> None:
        # The exact near-miss from the brief (sweep gold_id=38, ~0.619).
        d = _make_pbr_defect(
            observed=(
                "The MSC in 4.1 is missing the timeout for order acceptance."
            ),
            entity="Order",
            technique=ReadingTechnique.PBR_TESTER,
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "timeout is missing" in d.description.lower()
        assert "missing the timeout" not in d.description.lower()
        # Object clause must survive — only the verb cluster is rewritten.
        assert "for order acceptance" in d.description.lower()
        assert d.description.startswith("'Order':")
        assert "pbr_description_normalized" in d.flags


class TestNoopBehaviour:
    def test_no_change_when_entity_empty(self) -> None:
        d = _make_pbr_defect(
            observed="Something is not specified here.",
            entity="",  # explicit empty
        )
        # Empty entity is rejected by Defect schema if None; pass " " then strip.
        d.entity = ""
        ok = _normalize_pbr_description(d)
        assert ok is False
        # description must stay untouched.
        assert "pbr_description_normalized" not in d.flags

    def test_no_change_for_ubr_technique(self) -> None:
        d = _make_pbr_defect(
            observed="The Login signal is not specified in the MSC.",
            entity="Login",
            technique=ReadingTechnique.UBR,
        )
        before = d.description
        ok = _normalize_pbr_description(d)
        assert ok is False
        assert d.description == before
        assert "pbr_description_normalized" not in d.flags

    def test_no_change_for_cbr_technique(self) -> None:
        d = _make_pbr_defect(
            observed="The Login signal is not specified in the MSC.",
            entity="Login",
            technique=ReadingTechnique.CBR,
        )
        ok = _normalize_pbr_description(d)
        assert ok is False
        assert "pbr_description_normalized" not in d.flags

    def test_no_flag_when_already_normalised(self) -> None:
        """If the source text contains no requirements-style phrasing
        and is already in the canonical `'<entity>': <claim>` shape,
        the helper must be a no-op AND not add the audit flag."""
        d = _make_pbr_defect(
            observed="missing acknowledgment in the MSC at 3.4.1",
            entity="Reject_Order",
            description="'Reject_Order': missing acknowledgment in the MSC at 3.4.1.",
        )
        ok = _normalize_pbr_description(d)
        assert ok is False
        assert "pbr_description_normalized" not in d.flags

    def test_source_priority_observed_over_evidence(self) -> None:
        """If observed is set, evidence is ignored as the source."""
        d = _make_pbr_defect(
            observed="Timeout is not defined.",
            evidence="Some other evidence string.",
            entity="Foo",
        )
        ok = _normalize_pbr_description(d)
        assert ok is True
        # Observed-derived text won → "timeout is missing" appears.
        assert "timeout is missing" in d.description.lower()
        # Evidence string must NOT appear.
        assert "some other evidence" not in d.description.lower()

    def test_dict_shape_supported(self) -> None:
        d = {
            "technique": "PBR_USER",
            "entity": "Cancel_Order",
            "description": "'Cancel_Order': old text",
            "evidence": "x",
            "observed": "No acknowledgment is specified after cancel.",
            "flags": [],
        }
        ok = _normalize_pbr_description(d)
        assert ok is True
        assert "missing acknowledgment" in d["description"].lower()
        assert "pbr_description_normalized" in d["flags"]


# ---------------------------------------------------------------------------
# Gate: process.py only calls the helper when extra_config opts in
# ---------------------------------------------------------------------------


class TestProcessGateRespectsConfigFlag:
    """Static check on the call site so a refactor cannot quietly enable
    the rewrite globally."""

    def test_call_site_uses_extra_config_flag(self) -> None:
        text = PROCESS_PATH.read_text(encoding="utf-8")
        # The gate must reference the extra_config key.
        assert 'extra_config.get("pbr_description_normalize"' in text
        # And must wrap the actual helper invocation.
        assert "pbr_desc_normalize_enabled and _normalize_pbr_description(d)" in text

    def test_default_is_off(self) -> None:
        """Reading the call site source: the default for the flag is
        False (off), so non-PBR configs cannot accidentally normalise."""
        text = PROCESS_PATH.read_text(encoding="utf-8")
        # The default arg passed to .get is False (covers the most
        # common reading of the source).
        assert 'extra_config.get("pbr_description_normalize", False)' in text


class TestConfigOptsIn:
    """pbr_same_n10.yaml carries the flag set to true."""

    def test_pbr_config_enables_normalization(self) -> None:
        import yaml  # PyYAML is already a runtime dependency.

        with PBR_CONFIG.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        extra = data.get("extra_config", {})
        assert extra.get("pbr_description_normalize") is True
