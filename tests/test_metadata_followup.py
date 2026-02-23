"""Tests for metadata Follow-Up fields and evaluation metadata.

These tests verify that:
1. RunMetadata contains logs_complete, evidence_quality, incomplete_defects_count
2. EvaluationMetrics contains TP breakdown and similarity stats
3. All new fields are backward compatible (optional with defaults)
"""

import pytest
from datetime import datetime

from fagan_tool.core.schemas import (
    Defect,
    EvaluationMetadata,
    EvaluationMetrics,
    EvaluationThresholds,
    FaultType,
    GoldDefect,
    IncompleteDefect,
    LLMParams,
    MatchType,
    MeetingOutput,
    RiskLevel,
    RunMetadata,
    ConditionType,
)


class TestRunMetadataFollowUp:
    """Test suite for RunMetadata Follow-Up fields."""

    def test_metadata_contains_logs_complete(self):
        """Test that RunMetadata has logs_complete field."""
        metadata = RunMetadata(
            inspection_id="test_run",
            condition=ConditionType.C1_UBR,
            llm_params=LLMParams(model="gpt-4", provider="openai"),
            logs_complete=True,
        )

        assert hasattr(metadata, "logs_complete")
        assert metadata.logs_complete is True

    def test_metadata_contains_evidence_quality(self):
        """Test that RunMetadata has evidence_quality field."""
        metadata = RunMetadata(
            inspection_id="test_run",
            condition=ConditionType.C1_UBR,
            llm_params=LLMParams(model="gpt-4", provider="openai"),
            evidence_quality="high",
        )

        assert hasattr(metadata, "evidence_quality")
        assert metadata.evidence_quality == "high"

    def test_metadata_contains_incomplete_count(self):
        """Test that RunMetadata has incomplete_defects_count field."""
        metadata = RunMetadata(
            inspection_id="test_run",
            condition=ConditionType.C1_UBR,
            llm_params=LLMParams(model="gpt-4", provider="openai"),
            incomplete_defects_count=3,
        )

        assert hasattr(metadata, "incomplete_defects_count")
        assert metadata.incomplete_defects_count == 3

    def test_metadata_backward_compatible(self):
        """Test that new fields are optional (backward compatible)."""
        # Create metadata without new fields - should work
        metadata = RunMetadata(
            inspection_id="test_run",
            condition=ConditionType.C1_UBR,
            llm_params=LLMParams(model="gpt-4", provider="openai"),
        )

        # New fields should default to None
        assert metadata.logs_complete is None
        assert metadata.evidence_quality is None
        assert metadata.incomplete_defects_count is None

    def test_metadata_all_followup_fields(self):
        """Test setting all Follow-Up fields together."""
        metadata = RunMetadata(
            inspection_id="full_test",
            condition=ConditionType.C1_UBR,
            llm_params=LLMParams(model="gpt-4", provider="openai"),
            logs_complete=True,
            evidence_quality="medium",
            incomplete_defects_count=2,
        )

        assert metadata.logs_complete is True
        assert metadata.evidence_quality == "medium"
        assert metadata.incomplete_defects_count == 2


class TestEvaluationMetricsTPBreakdown:
    """Test suite for EvaluationMetrics TP breakdown fields."""

    def test_metrics_contains_tp_exact(self):
        """Test that EvaluationMetrics has true_positives_exact field."""
        metrics = EvaluationMetrics(
            run_id="test",
            total_found=10,
            total_gold=15,
            true_positives=8,
            true_positives_exact=5,
            true_positives_partial=3,
            false_positives=2,
            false_negatives=7,
            duplicates=0,
            precision=0.8,
            recall=0.53,
            f1_score=0.64,
        )

        assert hasattr(metrics, "true_positives_exact")
        assert metrics.true_positives_exact == 5

    def test_metrics_contains_tp_partial(self):
        """Test that EvaluationMetrics has true_positives_partial field."""
        metrics = EvaluationMetrics(
            run_id="test",
            total_found=10,
            total_gold=15,
            true_positives=8,
            true_positives_exact=5,
            true_positives_partial=3,
            false_positives=2,
            false_negatives=7,
            duplicates=0,
            precision=0.8,
            recall=0.53,
            f1_score=0.64,
        )

        assert hasattr(metrics, "true_positives_partial")
        assert metrics.true_positives_partial == 3

    def test_metrics_contains_similarity_stats(self):
        """Test that EvaluationMetrics has similarity score statistics."""
        metrics = EvaluationMetrics(
            run_id="test",
            total_found=10,
            total_gold=15,
            true_positives=8,
            false_positives=2,
            false_negatives=7,
            duplicates=0,
            precision=0.8,
            recall=0.53,
            f1_score=0.64,
            similarity_score_mean_tp=0.78,
            similarity_score_min_tp=0.62,
            similarity_score_max_tp=0.95,
        )

        assert hasattr(metrics, "similarity_score_mean_tp")
        assert hasattr(metrics, "similarity_score_min_tp")
        assert hasattr(metrics, "similarity_score_max_tp")
        assert metrics.similarity_score_mean_tp == 0.78
        assert metrics.similarity_score_min_tp == 0.62
        assert metrics.similarity_score_max_tp == 0.95

    def test_metrics_contains_match_threshold(self):
        """Test that EvaluationMetrics has match_threshold field."""
        metrics = EvaluationMetrics(
            run_id="test",
            total_found=10,
            total_gold=15,
            true_positives=8,
            false_positives=2,
            false_negatives=7,
            duplicates=0,
            precision=0.8,
            recall=0.53,
            f1_score=0.64,
            match_threshold=0.65,
        )

        assert hasattr(metrics, "match_threshold")
        assert metrics.match_threshold == 0.65

    def test_metrics_backward_compatible(self):
        """Test that new metrics fields are optional (backward compatible)."""
        # Create metrics without new fields - should use defaults
        metrics = EvaluationMetrics(
            run_id="test",
            total_found=10,
            total_gold=15,
            true_positives=8,
            false_positives=2,
            false_negatives=7,
            duplicates=0,
            precision=0.8,
            recall=0.53,
            f1_score=0.64,
        )

        # New fields should have default values
        assert metrics.true_positives_exact == 0
        assert metrics.true_positives_partial == 0
        assert metrics.similarity_score_mean_tp == 0.0
        assert metrics.similarity_score_min_tp == 0.0
        assert metrics.similarity_score_max_tp == 0.0
        assert metrics.match_threshold == 0.6


class TestIncompleteDefectTracking:
    """Test suite for tracking incomplete defects."""

    def test_incomplete_defect_in_meeting_output(self):
        """Test that MeetingOutput can track incomplete defects."""
        incomplete = IncompleteDefect(
            original_data={"position": "Section 2.1", "description": "Some issue"},
            reason="Missing mandatory evidence field",
            reviewer_id="reviewer_1",
        )

        meeting = MeetingOutput(
            consolidated_defects=[],
            incomplete_defects=[incomplete],
            duplicates_removed=0,
            conflicts_flagged=0,
            minutes="Test meeting",
            exit_decision="Conditional Accept",
        )

        assert len(meeting.incomplete_defects) == 1
        assert meeting.incomplete_defects[0].reason == "Missing mandatory evidence field"

    def test_incomplete_count_tracking(self):
        """Test tracking count of incomplete defects."""
        incomplete1 = IncompleteDefect(
            original_data={"id": "inc1"},
            reason="Missing evidence",
            reviewer_id="r1",
        )
        incomplete2 = IncompleteDefect(
            original_data={"id": "inc2"},
            reason="Missing position",
            reviewer_id="r2",
        )

        meeting = MeetingOutput(
            consolidated_defects=[],
            incomplete_defects=[incomplete1, incomplete2],
            duplicates_removed=0,
            conflicts_flagged=0,
            minutes="Test",
            exit_decision="Reject",
        )

        # Count should match list length
        assert len(meeting.incomplete_defects) == 2


class TestEvaluationMetadataCompleteness:
    """Test suite for EvaluationMetadata completeness."""

    def test_evaluation_metadata_fields(self):
        """Test that EvaluationMetadata has all required fields."""
        metadata = EvaluationMetadata(
            gold_standard_path="artifacts/gold/Faults_List.xls",
            gold_defect_count=42,
            matcher_thresholds={
                "match_threshold": 0.60,
                "description_threshold": 0.60,
                "exact_threshold": 0.85,
                "position_threshold": 0.70,
            },
            evaluation_version="1.2.0",
        )

        assert metadata.gold_standard_path == "artifacts/gold/Faults_List.xls"
        assert metadata.gold_defect_count == 42
        assert "match_threshold" in metadata.matcher_thresholds
        assert metadata.matcher_thresholds["match_threshold"] == 0.60
        assert metadata.evaluation_version == "1.2.0"

    def test_evaluation_metadata_in_metrics(self):
        """Test that EvaluationMetadata can be attached to EvaluationMetrics."""
        eval_metadata = EvaluationMetadata(
            gold_standard_path="test.xls",
            gold_defect_count=30,
            matcher_thresholds={"match_threshold": 0.60},
            evaluation_version="1.2.0",
        )

        metrics = EvaluationMetrics(
            run_id="test",
            total_found=10,
            total_gold=30,
            true_positives=8,
            false_positives=2,
            false_negatives=22,
            duplicates=0,
            precision=0.8,
            recall=0.27,
            f1_score=0.40,
            evaluation_metadata=eval_metadata,
        )

        assert metrics.evaluation_metadata is not None
        assert metrics.evaluation_metadata.gold_defect_count == 30
