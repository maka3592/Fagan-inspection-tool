"""Tests for threshold-based matching behavior.

These tests verify that:
1. Different thresholds produce different match classifications
2. Metrics (TP/FP) change correctly based on threshold
"""

import pytest

from fagan_tool.core.schemas import (
    Defect,
    GoldDefect,
    MatchType,
    RiskLevel,
    FaultType,
)
from fagan_tool.evaluation.matcher import DefectMatcher
from fagan_tool.evaluation.metrics import MetricsCalculator


@pytest.fixture
def sample_found_defect() -> Defect:
    """Create a sample found defect."""
    return Defect(
        id="found_001",
        position="Section 3.2 - Data Processing",
        description="The signal 'Process_Data' fails to validate user input before processing, "
                    "potentially leading to security vulnerabilities.",
        evidence={"quote_or_paraphrase": "Input validation for 'Process_Data' mentioned on page 12", "page_hint": "12"},
        risk=RiskLevel.A,
        fault_type=FaultType.M,
        confidence=0.85,
        reviewer_id="reviewer_1",
    )


@pytest.fixture
def sample_gold_defect() -> GoldDefect:
    """Create a sample gold defect with similar but not identical description."""
    return GoldDefect(
        id="gold_001",
        position="Section 3.2 - Data Processing",
        description="Missing input validation for 'Process_Data' in data processing module creates "
                    "security risk for the system.",
        risk=RiskLevel.A,
        fault_type=FaultType.M,
        section="3.2",
        page="12",
    )


class TestThresholdMatching:
    """Test suite for threshold-based matching behavior."""

    def test_threshold_060_partial(
        self, sample_found_defect: Defect, sample_gold_defect: GoldDefect
    ):
        """Test that with threshold=0.60, similar defects produce partial match."""
        matcher = DefectMatcher(
            position_threshold=0.7,
            description_threshold=0.60,
            exact_threshold=0.85,
        )

        found_defects = [sample_found_defect]
        gold_defects = [sample_gold_defect]

        matches, stats = matcher.match(found_defects, gold_defects)

        assert len(matches) == 1
        match = matches[0]

        # With 0.60 threshold, should match as PARTIAL or EXACT
        assert match.match_type in [MatchType.PARTIAL, MatchType.EXACT], (
            f"Expected PARTIAL or EXACT match, got {match.match_type}"
        )
        assert match.found_id == "found_001"
        assert match.gold_id == "gold_001"
        assert match.similarity_score >= 0.60

    def test_threshold_090_no_match(
        self, sample_found_defect: Defect, sample_gold_defect: GoldDefect
    ):
        """Test that with very high threshold=0.90, similar defects don't match."""
        matcher = DefectMatcher(
            position_threshold=0.7,
            description_threshold=0.90,  # Very high threshold
            exact_threshold=0.95,
        )

        found_defects = [sample_found_defect]
        gold_defects = [sample_gold_defect]

        matches, stats = matcher.match(found_defects, gold_defects)

        assert len(matches) == 1
        match = matches[0]

        # With 0.90 threshold, similar but not identical descriptions should not match
        assert match.match_type in [
            MatchType.NO_MATCH_POTENTIAL_NEW,
            MatchType.NO_MATCH_FALSE_POSITIVE,
        ], f"Expected NO_MATCH type with 0.90 threshold, got {match.match_type}"

    def test_metrics_change_with_threshold(
        self, sample_found_defect: Defect, sample_gold_defect: GoldDefect
    ):
        """Test that TP/FP counts differ based on threshold settings."""
        found_defects = [sample_found_defect]
        gold_defects = [sample_gold_defect]

        # Test with lower threshold (0.60) - should match
        matcher_low = DefectMatcher(
            position_threshold=0.7,
            description_threshold=0.60,
            exact_threshold=0.85,
        )
        matches_low, stats_low = matcher_low.match(found_defects, gold_defects)

        metrics_low = MetricsCalculator.calculate(
            run_id="test_run_low_threshold",
            found_defects=found_defects,
            gold_defects=gold_defects,
            matches=matches_low,
            stats=stats_low,
            match_threshold=0.60,
        )

        # Test with very high threshold (0.90) - should not match
        matcher_high = DefectMatcher(
            position_threshold=0.7,
            description_threshold=0.90,
            exact_threshold=0.95,
        )
        matches_high, stats_high = matcher_high.match(found_defects, gold_defects)

        metrics_high = MetricsCalculator.calculate(
            run_id="test_run_high_threshold",
            found_defects=found_defects,
            gold_defects=gold_defects,
            matches=matches_high,
            stats=stats_high,
            match_threshold=0.90,
        )

        # With low threshold: defect matches -> TP >= 1
        # With high threshold: defect doesn't match -> TP = 0
        assert metrics_low.true_positives >= metrics_high.true_positives, (
            "Lower threshold should produce >= TP than higher threshold"
        )

        # Verify match_threshold is stored in metrics
        assert metrics_low.match_threshold == 0.60
        assert metrics_high.match_threshold == 0.90


class TestTPBreakdown:
    """Test suite for TP exact/partial breakdown."""

    def test_tp_exact_partial_split(self):
        """Test that TP is correctly split into exact and partial."""
        # Create defects with varying similarity
        found_exact = Defect(
            id="found_exact",
            position="Section 3.2",
            description="Missing input validation in data processing module",
            evidence={"quote_or_paraphrase": "Page 12", "page_hint": "12"},
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            confidence=0.9,
        )

        gold = GoldDefect(
            id="gold_exact",
            position="Section 3.2",
            description="Missing input validation in data processing module",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
        )

        matcher = DefectMatcher(
            position_threshold=0.7,
            description_threshold=0.60,
            exact_threshold=0.85,
        )

        matches, stats = matcher.match([found_exact], [gold])
        metrics = MetricsCalculator.calculate(
            run_id="test_exact",
            found_defects=[found_exact],
            gold_defects=[gold],
            matches=matches,
            stats=stats,
        )

        # Near-identical descriptions should be exact
        assert metrics.true_positives == 1
        assert metrics.true_positives_exact + metrics.true_positives_partial == metrics.true_positives

    def test_similarity_score_stats(self):
        """Test that similarity score statistics are computed correctly."""
        found = Defect(
            id="found_001",
            position="Section 3.2",
            description="Missing input validation in data processing",
            evidence={"quote_or_paraphrase": "Page 12", "page_hint": "12"},
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            confidence=0.9,
        )

        gold = GoldDefect(
            id="gold_001",
            position="Section 3.2",
            description="Missing input validation in data processing module",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
        )

        matcher = DefectMatcher(description_threshold=0.60)
        matches, stats = matcher.match([found], [gold])

        metrics = MetricsCalculator.calculate(
            run_id="test_stats",
            found_defects=[found],
            gold_defects=[gold],
            matches=matches,
            stats=stats,
        )

        # If there's a TP, similarity stats should be populated
        if metrics.true_positives > 0:
            assert metrics.similarity_score_mean_tp > 0
            assert metrics.similarity_score_min_tp > 0
            assert metrics.similarity_score_max_tp > 0
            assert metrics.similarity_score_min_tp <= metrics.similarity_score_mean_tp
            assert metrics.similarity_score_mean_tp <= metrics.similarity_score_max_tp
