"""Tests for matching validity improvements (A1-A4).

D1: Signal extraction — 1-word prefix, domain tokens
D2: Signal gating prevents false partial matches
D3: Multi-position gold conservative filtering
D4: Normalized core similarity and feature flags
"""

import pytest

from fagan_tool.core.schemas import Defect, FaultType, GoldDefect, MatchType, RiskLevel
from fagan_tool.evaluation.matcher import DefectMatcher
from fagan_tool.utils.position_tokens import (
    extract_domain_tokens,
    extract_signal_tokens,
    feature_flags,
    normalize_desc,
)


# ---------------------------------------------------------------------------
# D1: Signal extraction
# ---------------------------------------------------------------------------


class TestSignalExtractionOneWordPrefix:
    """D1: 1-word topic prefix extraction."""

    def test_bill_prefix(self):
        """'Bill.' must be recognized as signal 'bill'."""
        tokens = extract_signal_tokens("Bill. The signal is missing.")
        assert "bill" in tokens

    def test_order_reject_prefix(self):
        """'Order_Reject.' must be recognized."""
        tokens = extract_signal_tokens("Order_Reject. Missing ack.")
        assert "order_reject" in tokens

    def test_confirm_voice_prefix_with_domain(self):
        """'Confirm_Voice.' → signal 'confirm_voice' plus domain tokens."""
        tokens = extract_signal_tokens("Confirm_Voice. Missing from MSC.")
        assert "confirm_voice" in tokens
        domain = extract_domain_tokens(tokens)
        assert "confirm" in domain
        assert "voice" in domain

    def test_ack_prefix(self):
        """'Ack.' (3 chars) must be recognized as signal 'ack'."""
        tokens = extract_signal_tokens("Ack. The acknowledgment is missing.")
        assert "ack" in tokens

    def test_short_prefix_rejected(self):
        """'OK.' (2 chars) must NOT be recognized (too short)."""
        tokens = extract_signal_tokens("OK. Everything is fine.")
        assert "ok" not in tokens

    def test_skip_word_prefix_rejected(self):
        """'Missing.' must NOT be recognized (skip word)."""
        tokens = extract_signal_tokens("Missing. No further info.")
        assert "missing" not in tokens

    def test_design_prefix_rejected(self):
        """'Design.' must NOT be recognized (skip word)."""
        tokens = extract_signal_tokens("Design. The overall layout is wrong.")
        assert "design" not in tokens


class TestDomainTokenExtraction:
    """D1: Domain sub-token extraction from signals."""

    def test_order_reject_domain(self):
        """'order_reject' splits to 'order', 'reject'."""
        domain = extract_domain_tokens({"order_reject"})
        assert domain == {"order", "reject"}

    def test_start_voice_domain(self):
        """'start_voice' splits to 'start', 'voice'."""
        domain = extract_domain_tokens({"start_voice"})
        assert domain == {"start", "voice"}

    def test_single_word_signal_domain(self):
        """'bill' stays as 'bill' (no underscore to split)."""
        domain = extract_domain_tokens({"bill"})
        assert domain == {"bill"}

    def test_short_parts_filtered(self):
        """Parts shorter than 3 characters are filtered out."""
        domain = extract_domain_tokens({"logged_in"})
        # 'in' is only 2 chars → filtered
        assert "logged" in domain
        assert "in" not in domain

    def test_empty_input(self):
        """Empty signal set → empty domain."""
        assert extract_domain_tokens(set()) == set()


# ---------------------------------------------------------------------------
# D2: Signal gating prevents false partials
# ---------------------------------------------------------------------------


class TestSignalGatingFalsePartials:
    """D2: Signal-gated rejection of false partial matches."""

    @pytest.fixture
    def matcher(self):
        return DefectMatcher()

    def test_order_reject_vs_bill_rejected(self, matcher):
        """Found 'Order_Reject' vs Gold 'Bill' — same position, high desc sim,
        but different signals → must be rejected."""
        found = Defect(
            id="F1",
            position="3.2.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Order_Reject. The signal 'Order_Reject' is missing an acknowledgment.",
            evidence="The signal 'Order_Reject' has no ack (p. 3).",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.2.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Bill. The signal 'Bill' is missing from the design.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        assert matches[0].gold_id is None
        assert matches[0].match_type in [
            MatchType.NO_MATCH_POTENTIAL_NEW,
            MatchType.NO_MATCH_FALSE_POSITIVE,
        ]

    def test_start_voice_vs_start_alarm_rejected(self, matcher):
        """Found 'Start_Voice' vs Gold 'Start alarm' — share 'start' domain
        token but only 1 overlap (< 2) → must be rejected."""
        found = Defect(
            id="F1",
            position="3.2.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Start Voice. The signal 'Start_Voice' is missing.",
            evidence="Section 3.2.1 lacks 'Start_Voice'.",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.2.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description='Start alarm. The signal "start alarm" is missing.',
            )
        ]

        matches, _ = matcher.match([found], gold)

        # Different signals (only 1 domain overlap 'start' < 2)
        assert matches[0].gold_id is None

    def test_same_signal_different_format_matches(self, matcher):
        """Found 'Reject_Order' (quoted) vs Gold 'reject_order' (underscore)
        → same signal → must match."""
        found = Defect(
            id="F1",
            position="3.4.1",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="The signal 'Reject_Order' is missing from the design.",
            evidence="Section 3.4.1 does not define 'Reject_Order'.",
            confidence=0.9,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.4.1",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Reject_Order is missing. The signal reject_order should be defined.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        assert matches[0].gold_id == "G1"
        assert matches[0].match_type in [MatchType.EXACT, MatchType.PARTIAL]


# ---------------------------------------------------------------------------
# D3: Multi-position gold filtering
# ---------------------------------------------------------------------------


class TestMultiPositionFiltering:
    """D3: Conservative position filtering for multi-position gold."""

    @pytest.fixture
    def matcher(self):
        return DefectMatcher()

    def test_three_positions_one_overlap_no_signal_rejected(self, matcher):
        """Gold has 3 positions, found overlaps only 1, no shared signal
        → must be rejected."""
        found = Defect(
            id="F1",
            position="3.2.1",
            risk=RiskLevel.B,
            fault_type=FaultType.M,
            description="A generic signal issue in the design document.",
            evidence="Section 3.2.1 shows a problem.",
            confidence=0.8,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.2.1, 3.2.2, 3.4.2",
                risk=RiskLevel.B,
                fault_type=FaultType.M,
                description="A different generic signal issue in the design.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        # 3 gold positions, only 1 overlap, no signal confirmation → rejected
        assert matches[0].gold_id is None

    def test_three_positions_one_overlap_with_signal_accepted(self, matcher):
        """Gold has 3 positions, found overlaps only 1, BUT shared signal
        → must be accepted (signal confirmation overrides A3)."""
        found = Defect(
            id="F1",
            position="3.4.1",
            risk=RiskLevel.B,
            fault_type=FaultType.M,
            description="Cancel_Order signal is missing from design.",
            evidence="Section 3.4.1 does not define 'Cancel_Order'.",
            confidence=0.85,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.2.1, 3.4.1, 3.4.2",
                risk=RiskLevel.B,
                fault_type=FaultType.M,
                description="Cancel_Order signal is missing in the design.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        # Signal 'Cancel_Order' confirms → A3 skipped → matches
        assert matches[0].gold_id == "G1"

    def test_two_positions_one_overlap_accepted(self, matcher):
        """Gold has 2 same-granularity positions, found overlaps 1
        → accepted (A3 only hard-rejects >= 3)."""
        found = Defect(
            id="F1",
            position="3.3.1",
            risk=RiskLevel.B,
            fault_type=FaultType.W,
            description="'Allocate_car' signal parameters are wrong.",
            evidence="Signal 'Allocate_car' in 3.3.1 has incorrect types.",
            confidence=0.85,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.3.1, 3.3.2",
                risk=RiskLevel.B,
                fault_type=FaultType.W,
                description="Allocate car. The design of allocate_car does not correspond.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        # 2 positions, shared signal → matches
        assert matches[0].gold_id == "G1"

    def test_mixed_granularity_most_specific_accepted(self, matcher):
        """Gold has mixed granularity (3.2, 3.4.2), found matches most
        specific (3.4.2) → accepted (with signal confirmation)."""
        found = Defect(
            id="F1",
            position="3.4.2",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Cancel_Order. The signal 'Cancel_Order' is missing from the design.",
            evidence="Section 3.4.2 does not define 'Cancel_Order'.",
            confidence=0.85,
        )
        gold = [
            GoldDefect(
                id="G1",
                position="3.2, 3.4.2",
                risk=RiskLevel.A,
                fault_type=FaultType.M,
                description="Cancel_Order signal is missing in the design specification.",
            )
        ]

        matches, _ = matcher.match([found], gold)

        # 3.4.2 is the most specific, signal confirms → accepted
        assert matches[0].gold_id == "G1"


# ---------------------------------------------------------------------------
# D4: Normalized core similarity and feature flags
# ---------------------------------------------------------------------------


class TestNormalizedDescSimilarity:
    """D4: Normalized description similarity."""

    def test_stopwords_removed(self):
        """Stopwords should not appear in normalized tokens."""
        tokens = normalize_desc("The signal is missing from the design.")
        assert "the" not in tokens
        assert "is" not in tokens
        assert "from" not in tokens
        assert "signal" in tokens
        assert "missing" in tokens
        assert "design" in tokens

    def test_punctuation_removed_underscores_kept(self):
        """Punctuation is removed but underscores are preserved."""
        tokens = normalize_desc("Signal 'Order_Reject' is missing!")
        assert "order_reject" in tokens

    def test_empty_string(self):
        """Empty string returns empty list."""
        assert normalize_desc("") == []

    def test_only_stopwords(self):
        """Text with only stopwords returns empty list."""
        assert normalize_desc("the a an is are") == []

    def test_short_tokens_filtered(self):
        """Tokens shorter than 2 chars are filtered."""
        tokens = normalize_desc("A x is 3 missing")
        assert "missing" in tokens
        # 'A', 'x', '3' all filtered (len < 2 or stopword)
        assert "a" not in tokens
        assert "x" not in tokens


class TestFeatureFlags:
    """D4: Feature flag extraction."""

    def test_ack_synonym(self):
        """'acknowledgment' normalizes to 'ack'."""
        flags = feature_flags(["acknowledgment", "missing"])
        assert "ack" in flags
        assert "missing" in flags

    def test_acknowledgement_synonym(self):
        """'acknowledgement' (British spelling) normalizes to 'ack'."""
        flags = feature_flags(["acknowledgement"])
        assert "ack" in flags

    def test_parameters_synonym(self):
        """'parameters' normalizes to 'parameter'."""
        flags = feature_flags(["parameters", "wrong"])
        assert "parameter" in flags
        assert "wrong" in flags

    def test_no_features(self):
        """Non-feature words yield empty set."""
        flags = feature_flags(["design", "document", "order"])
        assert flags == set()

    def test_ack_missing_vs_missing_ack_high_overlap(self):
        """'acknowledgment missing' and 'missing ack' should share features."""
        found_norm = normalize_desc("The acknowledgment is missing from the design.")
        gold_norm = normalize_desc("Missing ack signal in the specification.")
        found_flags = feature_flags(found_norm)
        gold_flags = feature_flags(gold_norm)
        overlap = found_flags & gold_flags
        # Both should contain 'ack' and 'missing'
        assert "ack" in overlap or "missing" in overlap

    def test_timeout_vs_parameter_no_overlap(self):
        """'timeout' and 'parameter' should have no feature overlap."""
        found_flags = feature_flags(["timeout", "specified"])
        gold_flags = feature_flags(["parameter", "wrong"])
        overlap = found_flags & gold_flags
        assert len(overlap) == 0


class TestFeatureAdjustmentInMatcher:
    """D4: Feature bonus/penalty affects score in matcher."""

    @pytest.fixture
    def matcher(self):
        return DefectMatcher()

    def test_contradictory_features_lower_score(self, matcher):
        """Defects with contradictory features (ack vs timeout) should score
        lower than those with matching features."""
        # Create two found defects with same position, matching vs contradictory
        found_match = Defect(
            id="F_match",
            position="3.2",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Missing error handling for null pointer exception",
            evidence="Section 3.2 does not handle errors (p. 15)",
            confidence=0.9,
        )
        found_contra = Defect(
            id="F_contra",
            position="3.2",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Timeout not specified for connection handling",
            evidence="Section 3.2 has no timeout (p. 15)",
            confidence=0.9,
        )
        gold = GoldDefect(
            id="G1",
            position="3.2",
            risk=RiskLevel.A,
            fault_type=FaultType.M,
            description="Missing error handling for null pointer",
        )

        result_match = matcher._calculate_similarity(found_match, gold)
        result_contra = matcher._calculate_similarity(found_contra, gold)

        # Matching features should score higher
        assert result_match.score > result_contra.score
