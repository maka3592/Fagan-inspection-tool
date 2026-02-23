"""Tests for gold-aligned defect filtering."""

import json
from pathlib import Path

import pytest

from fagan_tool.core.schemas import Defect, FaultType, RiskLevel
from fagan_tool.utils.gold_aligned_filter import (
    DEFAULT_MAX_GOLD_ALIGNED,
    filter_gold_aligned,
    gold_aligned_summary,
    is_gold_aligned,
)


def _make_defect(
    id: str,
    position: str = "3.2.1",
    description: str = "Missing signal. The signal 'Reject_Order' is missing an ack.",
    evidence: str = "The signal 'Reject_Order' is sent without ack (p. 3).",
    confidence: float = 0.85,
    risk: RiskLevel = RiskLevel.A,
    fault_type: FaultType = FaultType.M,
) -> Defect:
    """Helper to create a Defect with gold-aligned defaults."""
    return Defect(
        id=id,
        position=position,
        description=description,
        evidence=evidence,
        confidence=confidence,
        risk=risk,
        fault_type=fault_type,
    )


# ---------------------------------------------------------------------------
# is_gold_aligned unit tests
# ---------------------------------------------------------------------------


class TestIsGoldAligned:
    """Tests for the is_gold_aligned predicate."""

    def test_fully_qualifying_defect(self):
        """Defect with valid position, signal in desc, signal in evidence, gold pattern."""
        d = _make_defect("D1")
        assert is_gold_aligned(d) is True

    def test_invalid_position_rejected(self):
        """Use-case-only position is not gold-aligned."""
        d = _make_defect("D1", position="Use Case 1.1")
        assert is_gold_aligned(d) is False

    def test_no_signal_in_description_rejected(self):
        """Description without any signal identifier fails."""
        d = _make_defect(
            "D1",
            description="Missing error handling for null pointer.",
            evidence="The signal 'Reject_Order' not handled (p. 3).",
        )
        assert is_gold_aligned(d) is False

    def test_no_signal_in_evidence_rejected(self):
        """Evidence without any signal identifier fails."""
        d = _make_defect(
            "D1",
            description="Missing signal. The signal 'Reject_Order' has no ack.",
            evidence="Acknowledgment is missing from design (p. 3).",
        )
        assert is_gold_aligned(d) is False

    def test_no_gold_pattern_rejected(self):
        """Description without gold-like pattern fails."""
        d = _make_defect(
            "D1",
            description="The signal 'Reject_Order' appears in section 3.2.1.",
            evidence="The signal 'Reject_Order' is used on page 3.",
        )
        assert is_gold_aligned(d) is False

    def test_various_gold_patterns_accepted(self):
        """Each gold-like keyword is recognized."""
        patterns = [
            "missing", "misses", "not defined", "wrong",
            "incorrect", "inconsistent", "timeout", "ack",
        ]
        for kw in patterns:
            desc = f"The signal 'Start_Voice' {kw} in design."
            d = _make_defect("D1", description=desc)
            assert is_gold_aligned(d) is True, f"Pattern '{kw}' should qualify"

    def test_evidence_dict_form_accepted(self):
        """Evidence in dict form with quote_or_paraphrase is accepted."""
        d = Defect(
            id="D1",
            position="3.4.1",
            description="Missing signal. The signal 'Cancel_Order' is missing.",
            evidence={"quote_or_paraphrase": "The signal 'Cancel_Order' is not defined (p. 5)."},
            confidence=0.9,
        )
        assert is_gold_aligned(d) is True

    def test_table_position_accepted(self):
        """Table reference is a valid position token."""
        d = _make_defect("D1", position="Table 1")
        assert is_gold_aligned(d) is True

    def test_overview_position_rejected(self):
        """'Overview' is not a valid position token."""
        d = _make_defect("D1", position="Overview")
        assert is_gold_aligned(d) is False


# ---------------------------------------------------------------------------
# filter_gold_aligned tests
# ---------------------------------------------------------------------------


class TestFilterGoldAligned:
    """Tests for the filter_gold_aligned function."""

    def test_selects_only_qualifying_defects(self):
        """Only defects passing all criteria are returned."""
        good = _make_defect("D1", confidence=0.9)
        bad_no_signal = _make_defect(
            "D2",
            description="Missing error handling.",
            evidence="See page 5.",
            confidence=0.8,
        )
        bad_position = _make_defect("D3", position="Use Case 2", confidence=0.7)

        result = filter_gold_aligned([good, bad_no_signal, bad_position])
        assert len(result) == 1
        assert result[0].id == "D1"

    def test_sorted_by_confidence_desc(self):
        """Result is sorted by confidence descending."""
        d1 = _make_defect("D1", confidence=0.7)
        d2 = _make_defect("D2", confidence=0.95)
        d3 = _make_defect("D3", confidence=0.85)

        result = filter_gold_aligned([d1, d2, d3])
        assert [d.id for d in result] == ["D2", "D3", "D1"]

    def test_cap_to_max_defects(self):
        """Output is capped to max_defects."""
        defects = [_make_defect(f"D{i}", confidence=0.9 - i * 0.01) for i in range(20)]
        result = filter_gold_aligned(defects, max_defects=5)
        assert len(result) == 5

    def test_default_cap_is_12(self):
        """Default cap is DEFAULT_MAX_GOLD_ALIGNED = 12."""
        assert DEFAULT_MAX_GOLD_ALIGNED == 12
        defects = [_make_defect(f"D{i}", confidence=0.9 - i * 0.005) for i in range(20)]
        result = filter_gold_aligned(defects)
        assert len(result) == 12

    def test_fewer_than_cap_returns_all_qualifying(self):
        """If fewer than cap qualify, return all qualifying."""
        d1 = _make_defect("D1")
        d2 = _make_defect("D2")
        result = filter_gold_aligned([d1, d2], max_defects=10)
        assert len(result) == 2

    def test_empty_input(self):
        """Empty input returns empty list."""
        assert filter_gold_aligned([]) == []


# ---------------------------------------------------------------------------
# gold_aligned_summary tests
# ---------------------------------------------------------------------------


class TestGoldAlignedSummary:
    """Tests for the gold_aligned_summary function."""

    def test_summary_counts(self):
        """Summary contains correct counts."""
        all_defects = [
            _make_defect("D1"),
            _make_defect("D2", description="Generic problem.", evidence="No signal."),
            _make_defect("D3"),
        ]
        aligned = [all_defects[0], all_defects[2]]

        summary = gold_aligned_summary(all_defects, aligned)

        assert summary["total_consolidated_defects"] == 3
        assert summary["total_final_defects_all"] == 3
        assert summary["total_final_defects_gold_aligned"] == 2
        assert summary["total_novel_defects"] == 1
        assert summary["novel_defect_ids_sample"] == ["D2"]

    def test_novel_sample_capped(self):
        """Novel IDs sample is capped to novel_sample_size."""
        all_defects = [_make_defect(f"D{i}") for i in range(30)]
        aligned = all_defects[:5]

        summary = gold_aligned_summary(all_defects, aligned, novel_sample_size=3)
        assert len(summary["novel_defect_ids_sample"]) == 3


# ---------------------------------------------------------------------------
# Integration: run output file test
# ---------------------------------------------------------------------------


class TestGoldAlignedOutputFile:
    """Test that process.py would produce gold-aligned output."""

    def test_gold_aligned_json_written_by_save_run(self, tmp_path):
        """Verify _save_run produces final_defects_gold_aligned.json."""
        from fagan_tool.core.schemas import (
            ConditionType,
            InspectionConfig,
            LLMParams,
            ReadingTechnique,
        )
        from fagan_tool.core.process import FaganProcess

        config = InspectionConfig(
            inspection_id="gold_aligned_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="dry-run", provider="none"),
            dry_run=True,
        )

        process = FaganProcess(config, output_dir=tmp_path)
        run = process.run()

        # Check files exist
        run_dir = tmp_path / run.metadata.inspection_id
        assert (run_dir / "final_defects.json").exists()
        assert (run_dir / "final_defects_gold_aligned.json").exists()

        # Check meeting_output.json contains gold_aligned_summary
        with open(run_dir / "meeting_output.json") as f:
            meeting = json.load(f)
        assert "gold_aligned_summary" in meeting
        assert "total_final_defects_all" in meeting["gold_aligned_summary"]
        assert "total_final_defects_gold_aligned" in meeting["gold_aligned_summary"]
        assert "total_novel_defects" in meeting["gold_aligned_summary"]
        assert "novel_defect_ids_sample" in meeting["gold_aligned_summary"]

    def test_gold_aligned_file_is_subset_of_all(self, tmp_path):
        """Gold-aligned file contains a subset of final_defects.json IDs."""
        from fagan_tool.core.schemas import (
            ConditionType,
            InspectionConfig,
            LLMParams,
            ReadingTechnique,
        )
        from fagan_tool.core.process import FaganProcess

        config = InspectionConfig(
            inspection_id="subset_test",
            condition=ConditionType.C1_UBR,
            reading_techniques=[ReadingTechnique.UBR],
            artifacts=["design/test.pdf"],
            llm_params=LLMParams(model="dry-run", provider="none"),
            dry_run=True,
        )

        process = FaganProcess(config, output_dir=tmp_path)
        run = process.run()

        run_dir = tmp_path / run.metadata.inspection_id
        with open(run_dir / "final_defects.json") as f:
            all_ids = {d["id"] for d in json.load(f)}
        with open(run_dir / "final_defects_gold_aligned.json") as f:
            aligned_ids = {d["id"] for d in json.load(f)}

        # Gold-aligned must be a subset of all
        assert aligned_ids <= all_ids


# ---------------------------------------------------------------------------
# CLI --gold-aligned flag
# ---------------------------------------------------------------------------


class TestCLIGoldAlignedFlag:
    """Test CLI evaluation with --gold-aligned flag."""

    def test_eval_metadata_records_defects_file(self):
        """EvaluationMetadata.defects_file_used defaults to final_defects.json."""
        from fagan_tool.core.schemas import EvaluationMetadata

        meta = EvaluationMetadata(
            gold_standard_path="gold.xls",
            gold_defect_count=30,
        )
        assert meta.defects_file_used == "final_defects.json"

    def test_eval_metadata_records_gold_aligned(self):
        """EvaluationMetadata can store gold-aligned filename."""
        from fagan_tool.core.schemas import EvaluationMetadata

        meta = EvaluationMetadata(
            gold_standard_path="gold.xls",
            gold_defect_count=30,
            defects_file_used="final_defects_gold_aligned.json",
        )
        assert meta.defects_file_used == "final_defects_gold_aligned.json"
