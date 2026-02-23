"""Tests for metrics calculation."""

from fagan_tool.core.schemas import (
    Defect,
    DefectMatch,
    FaultType,
    GoldDefect,
    MatchType,
    ReadingTechnique,
    RiskLevel,
)
from fagan_tool.evaluation.metrics import MetricsCalculator


def test_false_positives_calculation():
    """Test that FP = total_found - tp - duplicates when no matches found."""
    # Create 5 found defects
    found_defects = [
        Defect(
            id=f"found_{i}",
            position=f"section_{i}",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description=f"Defect {i}",
            evidence=f"Evidence {i}",
            reviewer_id="reviewer_1",
            technique=ReadingTechnique.UBR,
        )
        for i in range(5)
    ]

    # Create 10 gold defects (all unmatched)
    gold_defects = [
        GoldDefect(
            id=f"gold_{i}",
            position=f"gold_section_{i}",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description=f"Gold defect {i}",
        )
        for i in range(10)
    ]

    # Create matches: all 5 found defects are NO_MATCH_POTENTIAL_NEW
    matches = [
        DefectMatch(
            found_id=f"found_{i}",
            gold_id=None,
            match_type=MatchType.NO_MATCH_POTENTIAL_NEW,
            similarity_score=0.0,
            notes="No match in gold standard",
        )
        for i in range(5)
    ]

    # Calculate metrics
    metrics = MetricsCalculator.calculate(
        run_id="test_run",
        found_defects=found_defects,
        gold_defects=gold_defects,
        matches=matches,
        stats={},
    )

    # Assertions
    assert metrics.total_found == 5, f"Expected 5 found, got {metrics.total_found}"
    assert metrics.total_gold == 10, f"Expected 10 gold, got {metrics.total_gold}"
    assert metrics.true_positives == 0, f"Expected 0 TP, got {metrics.true_positives}"
    assert metrics.duplicates == 0, f"Expected 0 duplicates, got {metrics.duplicates}"

    # KEY ASSERTION: FP must be 5 (all found defects are FP)
    assert metrics.false_positives == 5, (
        f"Expected 5 FP (total_found - tp - dup = 5 - 0 - 0), "
        f"got {metrics.false_positives}"
    )

    assert metrics.false_negatives == 10, f"Expected 10 FN, got {metrics.false_negatives}"
    assert metrics.precision == 0.0, f"Expected precision 0.0, got {metrics.precision}"
    assert metrics.recall == 0.0, f"Expected recall 0.0, got {metrics.recall}"


def test_false_positives_with_mixed_matches():
    """Test FP calculation with TP, duplicates, and FP."""
    # 10 found defects
    found_defects = [
        Defect(
            id=f"found_{i}",
            position=f"section_{i}",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description=f"Defect {i}",
            evidence=f"Evidence {i}",
            reviewer_id="reviewer_1",
            technique=ReadingTechnique.UBR,
        )
        for i in range(10)
    ]

    # 5 gold defects
    gold_defects = [
        GoldDefect(
            id=f"gold_{i}",
            position=f"gold_section_{i}",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description=f"Gold defect {i}",
        )
        for i in range(5)
    ]

    # Matches:
    # - 3 exact matches (TP)
    # - 2 duplicates
    # - 5 no match (FP)
    matches = [
        # 3 TP
        DefectMatch(
            found_id="found_0",
            gold_id="gold_0",
            match_type=MatchType.EXACT,
            similarity_score=1.0,
        ),
        DefectMatch(
            found_id="found_1",
            gold_id="gold_1",
            match_type=MatchType.EXACT,
            similarity_score=1.0,
        ),
        DefectMatch(
            found_id="found_2",
            gold_id="gold_2",
            match_type=MatchType.EXACT,
            similarity_score=1.0,
        ),
        # 2 duplicates
        DefectMatch(
            found_id="found_3",
            gold_id=None,
            match_type=MatchType.DUPLICATE,
            similarity_score=0.0,
        ),
        DefectMatch(
            found_id="found_4",
            gold_id=None,
            match_type=MatchType.DUPLICATE,
            similarity_score=0.0,
        ),
        # 5 FP (NO_MATCH)
        DefectMatch(
            found_id="found_5",
            gold_id=None,
            match_type=MatchType.NO_MATCH_POTENTIAL_NEW,
            similarity_score=0.0,
        ),
        DefectMatch(
            found_id="found_6",
            gold_id=None,
            match_type=MatchType.NO_MATCH_FALSE_POSITIVE,
            similarity_score=0.0,
        ),
        DefectMatch(
            found_id="found_7",
            gold_id=None,
            match_type=MatchType.NO_MATCH_POTENTIAL_NEW,
            similarity_score=0.0,
        ),
        DefectMatch(
            found_id="found_8",
            gold_id=None,
            match_type=MatchType.NO_MATCH_FALSE_POSITIVE,
            similarity_score=0.0,
        ),
        DefectMatch(
            found_id="found_9",
            gold_id=None,
            match_type=MatchType.NO_MATCH_POTENTIAL_NEW,
            similarity_score=0.0,
        ),
    ]

    metrics = MetricsCalculator.calculate(
        run_id="test_run",
        found_defects=found_defects,
        gold_defects=gold_defects,
        matches=matches,
        stats={},
    )

    # Verify: total_found = TP + duplicates + FP
    # 10 = 3 + 2 + 5
    assert metrics.total_found == 10
    assert metrics.true_positives == 3
    assert metrics.duplicates == 2
    assert metrics.false_positives == 5, (
        f"Expected FP=5 (10 - 3 - 2), got {metrics.false_positives}"
    )

    # FN = unmatched gold = 5 - 3 = 2
    assert metrics.false_negatives == 2

    # Precision = TP / (TP + FP) = 3 / 8 = 0.375
    assert abs(metrics.precision - 0.375) < 0.001

    # Recall = TP / total_gold = 3 / 5 = 0.6
    assert abs(metrics.recall - 0.6) < 0.001


def test_perfect_score():
    """Test metrics when all defects are correctly matched."""
    # 3 found defects
    found_defects = [
        Defect(
            id=f"found_{i}",
            position=f"section_{i}",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description=f"Defect {i}",
            evidence=f"Evidence {i}",
            reviewer_id="reviewer_1",
            technique=ReadingTechnique.UBR,
        )
        for i in range(3)
    ]

    # 3 gold defects
    gold_defects = [
        GoldDefect(
            id=f"gold_{i}",
            position=f"gold_section_{i}",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description=f"Gold defect {i}",
        )
        for i in range(3)
    ]

    # All exact matches
    matches = [
        DefectMatch(
            found_id=f"found_{i}",
            gold_id=f"gold_{i}",
            match_type=MatchType.EXACT,
            similarity_score=1.0,
        )
        for i in range(3)
    ]

    metrics = MetricsCalculator.calculate(
        run_id="test_run",
        found_defects=found_defects,
        gold_defects=gold_defects,
        matches=matches,
        stats={},
    )

    assert metrics.total_found == 3
    assert metrics.total_gold == 3
    assert metrics.true_positives == 3
    assert metrics.false_positives == 0
    assert metrics.false_negatives == 0
    assert metrics.duplicates == 0
    assert metrics.precision == 1.0
    assert metrics.recall == 1.0
    assert metrics.f1_score == 1.0


def test_precision_in_scope_calculation():
    """Test that precision_in_scope correctly excludes out-of-scope FP."""
    # 8 found defects
    found_defects = [
        Defect(
            id=f"found_{i}",
            position=f"section_{i}",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description=f"Defect {i}",
            evidence=f"Evidence {i}",
            reviewer_id="reviewer_1",
            technique=ReadingTechnique.UBR,
        )
        for i in range(8)
    ]

    # 5 gold defects (all design/MSC scope)
    gold_defects = [
        GoldDefect(
            id=f"gold_{i}",
            position=f"Section {i+3}",  # Design sections
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description=f"Gold defect {i}",
        )
        for i in range(5)
    ]

    # Matches:
    # - 3 TP (matched)
    # - 2 in-scope FP (design sections, not in gold)
    # - 3 out-of-scope FP (use case sections)
    matches = [
        # 3 TP
        DefectMatch(
            found_id="found_0",
            gold_id="gold_0",
            match_type=MatchType.EXACT,
            similarity_score=1.0,
            notes="Matched",
        ),
        DefectMatch(
            found_id="found_1",
            gold_id="gold_1",
            match_type=MatchType.EXACT,
            similarity_score=1.0,
            notes="Matched",
        ),
        DefectMatch(
            found_id="found_2",
            gold_id="gold_2",
            match_type=MatchType.EXACT,
            similarity_score=1.0,
            notes="Matched",
        ),
        # 2 in-scope FP
        DefectMatch(
            found_id="found_3",
            gold_id=None,
            match_type=MatchType.NO_MATCH_POTENTIAL_NEW,
            similarity_score=0.0,
            notes="Potential new defect (high confidence, not in gold) (in-scope)",
        ),
        DefectMatch(
            found_id="found_4",
            gold_id=None,
            match_type=MatchType.NO_MATCH_POTENTIAL_NEW,
            similarity_score=0.0,
            notes="Potential new defect (high confidence, not in gold) (in-scope)",
        ),
        # 3 out-of-scope FP (use cases)
        DefectMatch(
            found_id="found_5",
            gold_id=None,
            match_type=MatchType.NO_MATCH_POTENTIAL_NEW,
            similarity_score=0.0,
            notes="Potential new defect (high confidence, not in gold) (out-of-scope: use case)",
        ),
        DefectMatch(
            found_id="found_6",
            gold_id=None,
            match_type=MatchType.NO_MATCH_FALSE_POSITIVE,
            similarity_score=0.0,
            notes="Likely false positive (low confidence, not in gold) (out-of-scope: use case)",
        ),
        DefectMatch(
            found_id="found_7",
            gold_id=None,
            match_type=MatchType.NO_MATCH_POTENTIAL_NEW,
            similarity_score=0.0,
            notes="Potential new defect (high confidence, not in gold) (out-of-scope: use case)",
        ),
    ]

    metrics = MetricsCalculator.calculate(
        run_id="test_run",
        found_defects=found_defects,
        gold_defects=gold_defects,
        matches=matches,
        stats={},
    )

    # Verify FP split
    assert metrics.false_positives_in_scope == 2, (
        f"Expected 2 in-scope FP, got {metrics.false_positives_in_scope}"
    )
    assert metrics.false_positives_out_of_scope == 3, (
        f"Expected 3 out-of-scope FP, got {metrics.false_positives_out_of_scope}"
    )
    assert metrics.false_positives == 5, (
        f"Expected total 5 FP, got {metrics.false_positives}"
    )

    # Verify precision calculations
    # Precision overall = TP / (TP + FP_total) = 3 / (3 + 5) = 3/8 = 0.375
    assert abs(metrics.precision - 0.375) < 0.001, (
        f"Expected precision 0.375, got {metrics.precision}"
    )

    # Precision in-scope = TP / (TP + FP_in_scope) = 3 / (3 + 2) = 3/5 = 0.6
    assert abs(metrics.precision_in_scope - 0.6) < 0.001, (
        f"Expected precision_in_scope 0.6, got {metrics.precision_in_scope}"
    )

    # Verify precision_in_scope > precision (excluding out-of-scope improves metric)
    assert metrics.precision_in_scope > metrics.precision


def test_avg_findings_per_reviewer_with_provenance():
    """Test avg_findings_per_reviewer uses source_reviewer_ids (provenance)."""
    # Simulate consolidated defects (no reviewer_id, but with source_reviewer_ids)
    found_defects = [
        Defect(
            id=f"meeting_{i}",
            position=f"3.{i+1}",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description=f"Defect {i}",
            evidence=f"Evidence {i}",
            reviewer_id=None,  # NULL after consolidation
            source_reviewer_ids=["reviewer_1", "reviewer_2"],
        )
        for i in range(6)
    ]

    gold_defects = [
        GoldDefect(
            id=f"gold_{i}",
            position=f"gold_section_{i}",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description=f"Gold defect {i}",
        )
        for i in range(10)
    ]

    matches = [
        DefectMatch(
            found_id=f"meeting_{i}",
            gold_id=None,
            match_type=MatchType.NO_MATCH_POTENTIAL_NEW,
            similarity_score=0.0,
        )
        for i in range(6)
    ]

    metrics = MetricsCalculator.calculate(
        run_id="test_run",
        found_defects=found_defects,
        gold_defects=gold_defects,
        matches=matches,
        stats={},
    )

    # 6 found defects / 2 reviewers = 3.0
    assert metrics.avg_findings_per_reviewer == 3.0, (
        f"Expected 3.0, got {metrics.avg_findings_per_reviewer}. "
        f"Bug: consolidated defects with reviewer_id=None should use source_reviewer_ids"
    )


def test_avg_findings_per_reviewer_fallback_to_reviewer_id():
    """Test avg_findings_per_reviewer falls back to reviewer_id when no provenance."""
    # Old format: reviewer_id set directly
    found_defects = [
        Defect(
            id=f"found_{i}",
            position=f"section_{i}",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description=f"Defect {i}",
            evidence=f"Evidence {i}",
            reviewer_id="reviewer_1",
            technique=ReadingTechnique.UBR,
        )
        for i in range(4)
    ]

    gold_defects = [
        GoldDefect(
            id="gold_0",
            position="gold_0",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Gold 0",
        )
    ]

    matches = [
        DefectMatch(
            found_id=f"found_{i}",
            gold_id=None,
            match_type=MatchType.NO_MATCH_POTENTIAL_NEW,
            similarity_score=0.0,
        )
        for i in range(4)
    ]

    metrics = MetricsCalculator.calculate(
        run_id="test_run",
        found_defects=found_defects,
        gold_defects=gold_defects,
        matches=matches,
        stats={},
    )

    # 4 defects / 1 reviewer = 4.0
    assert metrics.avg_findings_per_reviewer == 4.0


def test_avg_findings_per_reviewer_no_reviewer_info():
    """Test avg_findings_per_reviewer is 0.0 when no reviewer info at all."""
    found_defects = [
        Defect(
            id="found_0",
            position="3.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Defect",
            evidence="Evidence",
            reviewer_id=None,
            # No source_reviewer_ids either
        )
    ]

    gold_defects = []
    matches = [
        DefectMatch(
            found_id="found_0",
            gold_id=None,
            match_type=MatchType.NO_MATCH_POTENTIAL_NEW,
            similarity_score=0.0,
        )
    ]

    metrics = MetricsCalculator.calculate(
        run_id="test_run",
        found_defects=found_defects,
        gold_defects=gold_defects,
        matches=matches,
        stats={},
    )

    assert metrics.avg_findings_per_reviewer == 0.0
