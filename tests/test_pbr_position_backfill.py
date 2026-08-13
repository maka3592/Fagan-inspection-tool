"""Deterministic position re-anchor for PBR defects.

PBR reviewers occasionally write a requirements-spec reference (e.g.
``position="3.1.23"``) even though the gap they describe sits in a
design / MSC section. The matcher's position gate then drops the
candidate before description similarity is ever considered. The fix is
``_pbr_backfill_design_position_from_evidence_location`` in
``src/fagan_tool/core/process.py``: it promotes a design / MSC token
from ``evidence_location`` to ``position`` whenever the original
position looks like a requirements ref. No design position is invented.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fagan_tool.core.process import (
    _pbr_backfill_design_position_from_evidence_location,
)
from fagan_tool.core.schemas import (
    Defect,
    FaultType,
    ReadingTechnique,
    RiskLevel,
)


PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
PBR_PROMPTS = [
    "reviewer_pbr_user.txt",
    "reviewer_pbr_tester.txt",
    "reviewer_pbr_designer.txt",
]


# ---------------------------------------------------------------------------
# Backfill behaviour
# ---------------------------------------------------------------------------


class TestPbrPositionBackfill:
    def test_rewrites_pbr_req_position_using_design_ref_in_evloc(self) -> None:
        d = Defect(
            id="x",
            position="3.1.23",
            page_hint="p. 9",
            description="'Reject_Order': requirement 3.1.23 is not designed.",
            evidence="No Reject_Order arrow in MSC.",
            evidence_location="p. 9, 3.4.1",
            technique=ReadingTechnique.PBR_TESTER,
            risk=RiskLevel.A,
            fault_type=FaultType.M,
        )
        assert d.position == "3.1.23"
        assert d.original_position is None
        ok = _pbr_backfill_design_position_from_evidence_location(d)
        assert ok is True
        assert d.position == "3.4.1"
        assert d.original_position == "3.1.23"
        assert "position_backfilled_from_evidence_location" in d.flags

    def test_rewrites_to_table_when_evloc_mentions_table_1(self) -> None:
        d = Defect(
            id="t",
            position="3.2.99",
            description="x",
            evidence="x",
            evidence_location="p. 2, Table 1",
            technique=ReadingTechnique.PBR_DESIGNER,
        )
        ok = _pbr_backfill_design_position_from_evidence_location(d)
        assert ok is True
        assert d.position == "Table 1"
        assert d.original_position == "3.2.99"

    def test_noop_for_ubr_technique(self) -> None:
        d = Defect(
            id="u",
            position="3.1.23",
            description="x",
            evidence="x",
            evidence_location="p. 5, 3.4.1",
            technique=ReadingTechnique.UBR,
        )
        ok = _pbr_backfill_design_position_from_evidence_location(d)
        assert ok is False
        assert d.position == "3.1.23"

    def test_noop_for_cbr_technique(self) -> None:
        d = Defect(
            id="c",
            position="3.1.23",
            description="x",
            evidence="x",
            evidence_location="p. 5, 3.4.1",
            technique=ReadingTechnique.CBR,
        )
        ok = _pbr_backfill_design_position_from_evidence_location(d)
        assert ok is False
        assert d.position == "3.1.23"

    def test_noop_when_position_is_already_design_section(self) -> None:
        """3.4.1 does not match the requirements pattern, so the helper
        leaves it alone even if evidence_location offers a different
        design ref."""
        d = Defect(
            id="r",
            position="3.4.1",
            description="x",
            evidence="x",
            evidence_location="p. 5, 3.3.1",
            technique=ReadingTechnique.PBR_USER,
        )
        ok = _pbr_backfill_design_position_from_evidence_location(d)
        assert ok is False
        assert d.position == "3.4.1"

    def test_noop_when_evidence_location_carries_no_design_ref(self) -> None:
        d = Defect(
            id="n",
            position="3.1.23",
            description="x",
            evidence="x",
            evidence_location="p. 9",  # page-only, no 3.X.Y / 4.X / Table
            technique=ReadingTechnique.PBR_USER,
        )
        ok = _pbr_backfill_design_position_from_evidence_location(d)
        assert ok is False
        assert d.position == "3.1.23"

    def test_noop_when_evidence_location_empty(self) -> None:
        d = Defect(
            id="e",
            position="3.2.50",
            description="x",
            evidence="x",
            evidence_location=None,
            technique=ReadingTechnique.PBR_TESTER,
        )
        ok = _pbr_backfill_design_position_from_evidence_location(d)
        assert ok is False
        assert d.position == "3.2.50"

    def test_preserves_existing_original_position(self) -> None:
        """If something earlier in the pipeline set original_position,
        we must not overwrite it."""
        d = Defect(
            id="p",
            position="3.1.23",
            description="x",
            evidence="x",
            evidence_location="p. 5, 3.4.1",
            technique=ReadingTechnique.PBR_USER,
            original_position="ALREADY_RECORDED",
        )
        ok = _pbr_backfill_design_position_from_evidence_location(d)
        assert ok is True
        assert d.position == "3.4.1"
        assert d.original_position == "ALREADY_RECORDED"

    def test_dict_shape_supported(self) -> None:
        d = {
            "technique": "PBR_USER",
            "position": "3.1.23",
            "evidence_location": "p. 9, 3.4.1",
            "description": "x",
            "evidence": "x",
            "flags": [],
        }
        ok = _pbr_backfill_design_position_from_evidence_location(d)
        assert ok is True
        assert d["position"] == "3.4.1"
        assert d["original_position"] == "3.1.23"
        assert "position_backfilled_from_evidence_location" in d["flags"]

    def test_idempotent_after_rewrite(self) -> None:
        d = Defect(
            id="i",
            position="3.1.23",
            description="x",
            evidence="x",
            evidence_location="p. 5, 3.4.1",
            technique=ReadingTechnique.PBR_DESIGNER,
        )
        first = _pbr_backfill_design_position_from_evidence_location(d)
        assert first is True
        # Second pass: position is now "3.4.1" which does not match the
        # requirements pattern, so the helper is a no-op.
        second = _pbr_backfill_design_position_from_evidence_location(d)
        assert second is False
        # No duplicate flag entries.
        assert d.flags.count("position_backfilled_from_evidence_location") == 1


# ---------------------------------------------------------------------------
# PBR prompts carry the new mandatory rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("prompt_name", PBR_PROMPTS)
def test_pbr_prompt_has_position_anchor_rule(prompt_name: str) -> None:
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    assert "POSITION ANCHOR RULE" in text
    # The rule must name the design sections and the requirements-style
    # IDs it bans.
    assert "Table 1" in text
    assert "3.4.1" in text
    assert "3.1.23" in text
    # And it must say where requirement refs belong instead.
    assert "expected" in text
    assert "evidence_location" in text


@pytest.mark.parametrize("prompt_name", PBR_PROMPTS)
def test_pbr_prompt_reinforces_description_style(prompt_name: str) -> None:
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    assert "PBR-specific reinforcement" in text
    # All required claim words must be enumerated for the LLM to pick from.
    for keyword in (
        "missing",
        "incorrect",
        "mismatch",
        "parameter",
        "acknowledgment",
        "timeout",
    ):
        assert keyword in text, f"{prompt_name} missing keyword {keyword}"
    # The verbatim-quoted-entity rule.
    assert "'<ENTITY>'" in text


@pytest.mark.parametrize("prompt_name", PBR_PROMPTS)
def test_pbr_prompt_still_format_compatible(prompt_name: str) -> None:
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    rendered = text.format(extra_context="SAMPLE FOCUS BLOCK")
    assert "SAMPLE FOCUS BLOCK" in rendered


# ---------------------------------------------------------------------------
# DESIGN-CONCRETE CLAIM RULE block must be present in every PBR prompt
# ---------------------------------------------------------------------------


_DESIGN_CLAIM_PHRASINGS = [
    "signal is missing",
    "signal is incorrect",
    "does not match",
    "parameter is missing",
    "acknowledgment is missing",
    "timeout is missing",
    "not defined in the API",
    "incorrect in the MSC",
]

_FORBIDDEN_PHRASINGS = [
    "Missing specification of how",
    "Unclear requirement",
    "Not specified how",
]


@pytest.mark.parametrize("prompt_name", PBR_PROMPTS)
def test_pbr_prompt_has_design_concrete_claim_rule(prompt_name: str) -> None:
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    assert "DESIGN-CONCRETE CLAIM RULE" in text


@pytest.mark.parametrize("prompt_name", PBR_PROMPTS)
def test_pbr_prompt_lists_all_design_claim_phrasings(prompt_name: str) -> None:
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    for phrase in _DESIGN_CLAIM_PHRASINGS:
        assert phrase in text, f"{prompt_name} missing claim phrasing {phrase!r}"


@pytest.mark.parametrize("prompt_name", PBR_PROMPTS)
def test_pbr_prompt_bans_abstract_phrasings(prompt_name: str) -> None:
    """The forbidden phrasings must appear in the BAN list so the model
    recognises them as something to avoid (they appear quoted under
    FORBIDDEN phrasings / Bad examples)."""
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    for phrase in _FORBIDDEN_PHRASINGS:
        assert phrase in text, f"{prompt_name} missing forbidden phrasing {phrase!r}"
    # And the explicit "FORBIDDEN phrasings" header should anchor the
    # ban so a future edit cannot accidentally turn an example into the
    # canonical form.
    assert "FORBIDDEN phrasings" in text


@pytest.mark.parametrize("prompt_name", PBR_PROMPTS)
def test_pbr_prompt_specifies_expected_observed_alignment(prompt_name: str) -> None:
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    # The rules for expected (Soll) and observed (Ist).
    assert "REQUIRED `expected` / `observed` quality" in text
    assert "Soll" in text
    assert "Ist" in text
    # Token-alignment instruction so observed shares vocabulary with
    # description.
    assert "Reuse the same artefact tokens" in text


@pytest.mark.parametrize("prompt_name", PBR_PROMPTS)
def test_pbr_prompt_specifies_evidence_location_format(prompt_name: str) -> None:
    text = (PROMPTS_DIR / prompt_name).read_text(encoding="utf-8")
    assert "REQUIRED `evidence_location` format" in text
    # Example anchored to the canonical format.
    assert "p. 7, 3.4.1, MSC" in text or "p. 2, Table 1" in text
