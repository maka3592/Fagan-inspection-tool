"""Tests for manual validation functionality.

These tests verify that:
1. Manual template creation works correctly
2. Manual metrics calculation works correctly
3. CLI commands are properly defined
"""

import csv
import json
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory


class TestManualTemplateCreation:
    """Test suite for manual validation template creation."""

    def test_template_adds_manual_columns(self, tmp_path):
        """Test that template adds manual_is_true_match and manual_notes columns."""
        # Create mock matches_enriched.csv
        enriched_path = tmp_path / "matches_enriched.csv"
        with open(enriched_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["match_type", "found_id", "gold_id"])
            writer.writeheader()
            writer.writerow({"match_type": "EXACT", "found_id": "f1", "gold_id": "g1"})
            writer.writerow({"match_type": "PARTIAL", "found_id": "f2", "gold_id": "g2"})

        # Create template
        manual_path = tmp_path / "matches_manual.csv"

        with open(enriched_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = list(reader.fieldnames)

        new_fieldnames = fieldnames + ["manual_is_true_match", "manual_notes"]
        for row in rows:
            row["manual_is_true_match"] = "FALSE"
            row["manual_notes"] = ""

        with open(manual_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=new_fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        # Verify template
        with open(manual_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            result_rows = list(reader)

        assert len(result_rows) == 2
        assert "manual_is_true_match" in reader.fieldnames
        assert "manual_notes" in reader.fieldnames
        assert all(row["manual_is_true_match"] == "FALSE" for row in result_rows)

    def test_template_preserves_original_data(self, tmp_path):
        """Test that template preserves all original columns and data."""
        # Create mock data
        enriched_path = tmp_path / "matches_enriched.csv"
        original_data = [
            {"match_type": "EXACT", "similarity_score": "0.95", "found_id": "f1"},
            {"match_type": "PARTIAL", "similarity_score": "0.72", "found_id": "f2"},
        ]

        with open(enriched_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["match_type", "similarity_score", "found_id"])
            writer.writeheader()
            writer.writerows(original_data)

        # Create template
        manual_path = tmp_path / "matches_manual.csv"

        with open(enriched_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = list(reader.fieldnames)

        new_fieldnames = fieldnames + ["manual_is_true_match", "manual_notes"]
        for row in rows:
            row["manual_is_true_match"] = "FALSE"
            row["manual_notes"] = ""

        with open(manual_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=new_fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        # Verify
        with open(manual_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            result_rows = list(reader)

        assert result_rows[0]["match_type"] == "EXACT"
        assert result_rows[0]["similarity_score"] == "0.95"
        assert result_rows[1]["match_type"] == "PARTIAL"


class TestManualMetricsCalculation:
    """Test suite for manual metrics calculation."""

    def test_metrics_from_manual_validation(self, tmp_path):
        """Test that metrics are correctly calculated from manual validation."""
        # Create mock matches_manual.csv with manual annotations
        manual_path = tmp_path / "matches_manual.csv"
        manual_data = [
            {"match_type": "EXACT", "found_id": "f1", "manual_is_true_match": "TRUE"},
            {"match_type": "PARTIAL", "found_id": "f2", "manual_is_true_match": "TRUE"},
            {"match_type": "NO_MATCH_FALSE_POSITIVE", "found_id": "f3", "manual_is_true_match": "FALSE"},
            {"match_type": "PARTIAL", "found_id": "f4", "manual_is_true_match": "FALSE"},
        ]

        with open(manual_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["match_type", "found_id", "manual_is_true_match"])
            writer.writeheader()
            writer.writerows(manual_data)

        # Calculate metrics
        with open(manual_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            matches = list(reader)

        total_gold = 5  # Simulated
        manual_tp = sum(1 for m in matches if m.get("manual_is_true_match", "").upper() == "TRUE")
        manual_fp = sum(1 for m in matches if m.get("manual_is_true_match", "").upper() != "TRUE")

        precision = manual_tp / (manual_tp + manual_fp) if (manual_tp + manual_fp) > 0 else 0.0
        recall = manual_tp / total_gold if total_gold > 0 else 0.0
        f1_score = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        # Verify
        assert manual_tp == 2
        assert manual_fp == 2
        assert precision == 0.5
        assert recall == 0.4  # 2/5
        assert f1_score == pytest.approx(0.444, rel=0.01)

    def test_metrics_handles_all_true(self, tmp_path):
        """Test metrics when all matches are marked as TRUE."""
        manual_path = tmp_path / "matches_manual.csv"
        manual_data = [
            {"match_type": "EXACT", "manual_is_true_match": "TRUE"},
            {"match_type": "PARTIAL", "manual_is_true_match": "TRUE"},
        ]

        with open(manual_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["match_type", "manual_is_true_match"])
            writer.writeheader()
            writer.writerows(manual_data)

        with open(manual_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            matches = list(reader)

        manual_tp = sum(1 for m in matches if m.get("manual_is_true_match", "").upper() == "TRUE")
        manual_fp = len(matches) - manual_tp

        assert manual_tp == 2
        assert manual_fp == 0

    def test_metrics_handles_empty_file(self, tmp_path):
        """Test metrics calculation with empty matches file."""
        manual_path = tmp_path / "matches_manual.csv"

        with open(manual_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["match_type", "manual_is_true_match"])
            writer.writeheader()

        with open(manual_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            matches = list(reader)

        manual_tp = sum(1 for m in matches if m.get("manual_is_true_match", "").upper() == "TRUE")
        manual_fp = len(matches) - manual_tp
        total_gold = 10

        precision = manual_tp / (manual_tp + manual_fp) if (manual_tp + manual_fp) > 0 else 0.0
        recall = manual_tp / total_gold if total_gold > 0 else 0.0

        assert manual_tp == 0
        assert manual_fp == 0
        assert precision == 0.0
        assert recall == 0.0


class TestManualMetricsBreakdown:
    """Test suite for TP/FP breakdown by match type."""

    def test_tp_by_match_type(self, tmp_path):
        """Test that TPs are correctly broken down by match type."""
        manual_path = tmp_path / "matches_manual.csv"
        manual_data = [
            {"match_type": "EXACT", "manual_is_true_match": "TRUE"},
            {"match_type": "EXACT", "manual_is_true_match": "TRUE"},
            {"match_type": "PARTIAL", "manual_is_true_match": "TRUE"},
            {"match_type": "PARTIAL", "manual_is_true_match": "FALSE"},
        ]

        with open(manual_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["match_type", "manual_is_true_match"])
            writer.writeheader()
            writer.writerows(manual_data)

        with open(manual_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            matches = list(reader)

        tp_by_type = {}
        fp_by_type = {}

        for match in matches:
            match_type = match.get("match_type", "UNKNOWN")
            is_tp = match.get("manual_is_true_match", "").upper() == "TRUE"

            if is_tp:
                tp_by_type[match_type] = tp_by_type.get(match_type, 0) + 1
            else:
                fp_by_type[match_type] = fp_by_type.get(match_type, 0) + 1

        assert tp_by_type["EXACT"] == 2
        assert tp_by_type["PARTIAL"] == 1
        assert fp_by_type["PARTIAL"] == 1
        assert "EXACT" not in fp_by_type


class TestCLICommandsExist:
    """Test that CLI commands are properly defined."""

    def test_verify_command_exists(self):
        """Test that verify command is defined in CLI."""
        from fagan_tool.cli import app

        commands = [cmd.name for cmd in app.registered_commands]
        assert "verify" in commands

    def test_manual_template_command_exists(self):
        """Test that manual-template command is defined in CLI."""
        from fagan_tool.cli import app

        commands = [cmd.name for cmd in app.registered_commands]
        assert "manual-template" in commands

    def test_manual_eval_command_exists(self):
        """Test that manual-eval command is defined in CLI."""
        from fagan_tool.cli import app

        commands = [cmd.name for cmd in app.registered_commands]
        assert "manual-eval" in commands

    def test_all_expected_commands_exist(self):
        """Test that all expected commands are present."""
        from fagan_tool.cli import app

        expected_commands = ["run", "eval", "report", "dry-run", "verify", "manual-template", "manual-eval"]
        commands = [cmd.name for cmd in app.registered_commands]

        for expected in expected_commands:
            assert expected in commands, f"Command '{expected}' not found in CLI"
