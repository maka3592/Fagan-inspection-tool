"""Calculate evaluation metrics."""

from typing import Dict, List

from ..core.schemas import Defect, DefectMatch, EvaluationMetrics, GoldDefect, MatchType, RiskLevel


# Threshold for exact vs partial match classification
EXACT_THRESHOLD = 0.85


class MetricsCalculator:
    """Calculate precision, recall, and other metrics."""

    @staticmethod
    def calculate(
        run_id: str,
        found_defects: List[Defect],
        gold_defects: List[GoldDefect],
        matches: List[DefectMatch],
        stats: Dict,
        match_threshold: float = 0.6,
    ) -> EvaluationMetrics:
        """Calculate evaluation metrics.

        Args:
            run_id: Run identifier
            found_defects: List of found defects
            gold_defects: List of gold defects
            matches: List of defect matches
            stats: Match statistics
            match_threshold: The similarity threshold used for matching

        Returns:
            EvaluationMetrics object
        """
        total_found = len(found_defects)
        total_gold = len(gold_defects)

        # Collect true positive matches
        tp_matches = [
            m for m in matches
            if m.match_type in [MatchType.EXACT, MatchType.PARTIAL]
        ]
        true_positives = len(tp_matches)

        # Calculate TP exact/partial breakdown
        # exact: similarity >= 0.85
        # partial: threshold <= similarity < 0.85
        true_positives_exact = sum(
            1 for m in tp_matches
            if m.similarity_score >= EXACT_THRESHOLD
        )
        true_positives_partial = sum(
            1 for m in tp_matches
            if m.similarity_score < EXACT_THRESHOLD
        )

        # Calculate similarity score statistics for true positives only
        tp_scores = [m.similarity_score for m in tp_matches]
        if tp_scores:
            similarity_score_mean_tp = sum(tp_scores) / len(tp_scores)
            similarity_score_min_tp = min(tp_scores)
            similarity_score_max_tp = max(tp_scores)
        else:
            similarity_score_mean_tp = 0.0
            similarity_score_min_tp = 0.0
            similarity_score_max_tp = 0.0

        # Duplicates
        duplicates = sum(1 for m in matches if m.match_type == MatchType.DUPLICATE)

        # False positives: All found defects that are not TP and not duplicates
        # This includes both NO_MATCH_FALSE_POSITIVE and NO_MATCH_POTENTIAL_NEW
        # (potential new defects are still FP from evaluation perspective since not in gold standard)
        false_positives = total_found - true_positives - duplicates

        # Split false positives into in-scope and out-of-scope
        fp_in_scope = 0
        fp_out_of_scope = 0

        for match in matches:
            if match.match_type in [MatchType.NO_MATCH_FALSE_POSITIVE, MatchType.NO_MATCH_POTENTIAL_NEW]:
                # Check if notes indicate out-of-scope
                if "(out-of-scope:" in match.notes:
                    fp_out_of_scope += 1
                else:
                    fp_in_scope += 1

        # False negatives: gold defects not matched
        matched_gold_ids = {m.gold_id for m in matches if m.gold_id}
        false_negatives = total_gold - len(matched_gold_ids)

        # Calculate precision and recall
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0.0

        # Calculate in-scope precision (excludes out-of-scope FPs)
        precision_in_scope = true_positives / (true_positives + fp_in_scope) if (true_positives + fp_in_scope) > 0 else 0.0

        recall = true_positives / total_gold if total_gold > 0 else 0.0
        f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        # Calculate recall by risk level
        recall_by_risk = MetricsCalculator._calculate_recall_by_risk(
            gold_defects, matches
        )

        # Average findings per reviewer
        # Use source_reviewer_ids (provenance) when available, fall back to reviewer_id
        reviewer_ids: set = set()
        for d in found_defects:
            if d.source_reviewer_ids:
                reviewer_ids.update(d.source_reviewer_ids)
            elif d.reviewer_id:
                reviewer_ids.add(d.reviewer_id)
        avg_findings_per_reviewer = (
            total_found / len(reviewer_ids) if reviewer_ids else 0.0
        )

        return EvaluationMetrics(
            run_id=run_id,
            total_found=total_found,
            total_gold=total_gold,
            true_positives=true_positives,
            true_positives_exact=true_positives_exact,
            true_positives_partial=true_positives_partial,
            false_positives=false_positives,
            false_positives_in_scope=fp_in_scope,
            false_positives_out_of_scope=fp_out_of_scope,
            false_negatives=false_negatives,
            duplicates=duplicates,
            precision=precision,
            precision_in_scope=precision_in_scope,
            recall=recall,
            f1_score=f1_score,
            recall_by_risk=recall_by_risk,
            avg_findings_per_reviewer=avg_findings_per_reviewer,
            similarity_score_mean_tp=similarity_score_mean_tp,
            similarity_score_min_tp=similarity_score_min_tp,
            similarity_score_max_tp=similarity_score_max_tp,
            match_threshold=match_threshold,
        )

    @staticmethod
    def _calculate_recall_by_risk(
        gold_defects: List[GoldDefect],
        matches: List[DefectMatch],
    ) -> Dict[str, float]:
        """Calculate recall breakdown by risk level.

        Args:
            gold_defects: Gold defects
            matches: Matches

        Returns:
            Dict mapping risk level to recall
        """
        # Count gold defects by risk
        gold_by_risk = {}
        for risk in RiskLevel:
            gold_by_risk[risk.value] = sum(1 for g in gold_defects if g.risk == risk)

        # Count matched gold defects by risk
        matched_gold_ids = {
            m.gold_id
            for m in matches
            if m.match_type in [MatchType.EXACT, MatchType.PARTIAL]
        }

        matched_by_risk = {}
        for risk in RiskLevel:
            count = sum(
                1
                for g in gold_defects
                if g.risk == risk and g.id in matched_gold_ids
            )
            matched_by_risk[risk.value] = count

        # Calculate recall for each risk level
        recall_by_risk = {}
        for risk in RiskLevel:
            total = gold_by_risk[risk.value]
            matched = matched_by_risk[risk.value]
            recall_by_risk[risk.value] = matched / total if total > 0 else 0.0

        return recall_by_risk
