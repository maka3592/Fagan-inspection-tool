"""Load gold standard defects from Excel."""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from ..core.schemas import FaultType, GoldDefect, RiskLevel

logger = logging.getLogger(__name__)


class GoldLoader:
    """Load and parse gold standard fault list."""

    def __init__(self, gold_path: Path | str):
        """Initialize loader.

        Args:
            gold_path: Path to gold standard Excel file
        """
        # Ensure Path object for robustness
        self.gold_path = Path(gold_path)

    def load(self) -> List[GoldDefect]:
        """Load gold defects from Excel.

        Returns:
            List of gold defects

        Raises:
            FileNotFoundError: If gold file doesn't exist
            ValueError: If header row cannot be found
        """
        if not self.gold_path.exists():
            raise FileNotFoundError(f"Gold standard file not found: {self.gold_path}")

        # Read Excel without assuming headers
        try:
            df_raw = pd.read_excel(self.gold_path, header=None, engine="openpyxl")
        except Exception:
            df_raw = pd.read_excel(self.gold_path, header=None)

        # Find the header row automatically
        header_idx = self._find_header_row(df_raw)

        if header_idx is None:
            raise ValueError(
                f"Cannot find header row in {self.gold_path}. "
                "Expected a row containing keywords like 'position', 'risk', 'type', "
                "'fault', 'description', 'scenario', 'number', 'clock', or 'item'. "
                "Please ensure the Excel file has a proper header row."
            )

        # Set the header and drop meta rows
        df = df_raw.iloc[header_idx + 1:].copy()
        df.columns = df_raw.iloc[header_idx]

        # Clean up dataframe
        df = self._cleanup_dataframe(df)

        # Find column mapping using fuzzy/heuristic matching
        col_mapping = self._find_column_mapping(df.columns)

        # Validate that we found essential columns
        if not col_mapping.get("description"):
            available_cols = list(df.columns)
            raise ValueError(
                f"Cannot find 'description' column in {self.gold_path}. "
                f"Available columns: {available_cols}. "
                "Please ensure the Excel has a column for defect descriptions."
            )

        # Log the mapping for debugging
        logger.info(f"Gold loader column mapping: {col_mapping}")

        # Filter out meta/comment rows that aren't real defects
        df = self._filter_valid_defect_rows(df, col_mapping)

        defects = []
        seen_ids = set()
        fallback_count = 0

        for idx, row in df.iterrows():
            # Extract fields using mapped column names
            number_value = self._get_value(row, col_mapping.get("id"), default=None)

            # Generate defect ID from number field
            if number_value is not None:
                # Convert to string and clean
                defect_id = str(number_value).strip()
                # If it's a float like "1.0", convert to int first
                try:
                    if "." in defect_id:
                        float_val = float(defect_id)
                        if float_val.is_integer():
                            defect_id = str(int(float_val))
                except (ValueError, AttributeError):
                    pass
            else:
                # Fallback ID if number column missing or empty
                defect_id = f"gold_{idx}"
                fallback_count += 1
                logger.warning(
                    f"Row {idx}: Number field missing or empty, using fallback ID: {defect_id}"
                )

            # Check for duplicate IDs
            if defect_id in seen_ids:
                logger.error(
                    f"Row {idx}: Duplicate ID '{defect_id}' found. "
                    f"This will cause issues with matching. "
                    f"Please ensure the Number column has unique values."
                )
            seen_ids.add(defect_id)

            position = self._get_value(row, col_mapping.get("position"), default="unknown")
            risk_str = self._get_value(row, col_mapping.get("risk"), default="UNK")
            type_str = self._get_value(row, col_mapping.get("type"), default="UNK")
            description = self._get_value(row, col_mapping.get("description"), default="")
            section = self._get_value(row, col_mapping.get("section"), default=None)
            page = self._get_value(row, col_mapping.get("page"), default=None)

            # Normalize risk
            risk = self._normalize_risk(risk_str)

            # Normalize fault type
            fault_type = self._normalize_fault_type(type_str)

            defect = GoldDefect(
                id=defect_id,
                position=str(position),
                risk=risk,
                fault_type=fault_type,
                description=str(description),
                section=str(section) if section else None,
                page=str(page) if page else None,
            )
            defects.append(defect)

        # Log summary
        if fallback_count > 0:
            logger.warning(
                f"Used {fallback_count} fallback IDs due to missing Number values"
            )

        return defects

    def _find_header_row(self, df_raw: pd.DataFrame) -> int | None:
        """Find the header row by detecting key column names.

        Args:
            df_raw: Raw dataframe without headers

        Returns:
            Index of header row, or None if not found
        """
        # Keywords that should appear in header row (case-insensitive)
        keywords = [
            "position", "risk", "type", "fault", "description",
            "scenario", "number", "clock", "item"
        ]

        best_idx = None
        best_score = 0

        for idx, row in df_raw.iterrows():
            # Convert row to lowercase strings for matching
            row_strings = [
                str(cell).lower() if pd.notna(cell) else ""
                for cell in row
            ]

            # Skip rows where first cell is very long (likely explanatory text, not header)
            if row_strings and len(row_strings[0]) > 50:
                continue

            # Check individual cells for keywords (prefer columns with single keywords)
            cell_keyword_count = 0
            for cell_str in row_strings:
                # Check if this cell contains a keyword and is reasonably short (< 30 chars)
                if len(cell_str) < 30:
                    for keyword in keywords:
                        if keyword in cell_str:
                            cell_keyword_count += 1
                            break  # Count each cell only once

            # Also count keywords in full row text
            row_text = " ".join(row_strings)
            text_keyword_count = sum(1 for keyword in keywords if keyword in row_text)

            # Prefer rows where keywords appear in separate cells (better header structure)
            # Score = 2 * cell_matches + text_matches
            score = 2 * cell_keyword_count + text_keyword_count

            # Need at least 3 keywords to be considered a header
            if cell_keyword_count >= 3 and score > best_score:
                best_score = score
                best_idx = idx

        return best_idx

    def _cleanup_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove empty columns and rows from dataframe.

        Args:
            df: Dataframe to clean

        Returns:
            Cleaned dataframe
        """
        # Remove columns that are all NaN or have "Unnamed" in name
        # Use iloc to avoid ambiguity with duplicate column names
        cols_to_keep = []
        for col_idx, col in enumerate(df.columns):
            col_str = str(col)
            # Access column by position to avoid Series ambiguity
            col_values = df.iloc[:, col_idx]
            # Safe bool conversion
            has_data = bool(col_values.notna().any())
            if not col_str.startswith("Unnamed") and has_data:
                cols_to_keep.append(col)
        df = df[cols_to_keep]

        # Remove rows where both position and description are empty
        # (these are likely empty rows)
        position_cols = [c for c in df.columns if "position" in str(c).lower()]
        desc_cols = [c for c in df.columns if "description" in str(c).lower()]

        if position_cols or desc_cols:
            # Keep rows that have at least one non-empty value in position or description
            mask = pd.Series([False] * len(df), index=df.index)
            for col in position_cols + desc_cols:
                # Get column index to avoid ambiguity
                col_idx = df.columns.get_loc(col)
                if isinstance(col_idx, slice) or hasattr(col_idx, '__iter__'):
                    # Multiple columns with same name, take first
                    col_idx = 0 if isinstance(col_idx, slice) else col_idx[0]
                col_values = df.iloc[:, col_idx]
                # Safe bool operations
                is_not_na = col_values.notna()
                is_not_empty = col_values.astype(str).str.strip() != ""
                mask |= is_not_na & is_not_empty
            df = df[mask]

        return df

    def _filter_valid_defect_rows(
        self, df: pd.DataFrame, col_mapping: Dict[str, Optional[str]]
    ) -> pd.DataFrame:
        """Filter out meta/comment rows that aren't real defects.

        Args:
            df: DataFrame to filter
            col_mapping: Column name mapping

        Returns:
            Filtered DataFrame with only valid defect rows
        """
        if len(df) == 0:
            return df

        # Get mapped column names
        desc_col = col_mapping.get("description")
        id_col = col_mapping.get("id")
        pos_col = col_mapping.get("position")

        # Build filter mask
        mask = pd.Series([True] * len(df), index=df.index)

        # Rule 1: Description must exist and be at least 10 characters
        if desc_col and desc_col in df.columns:
            col_idx = df.columns.get_loc(desc_col)
            if isinstance(col_idx, slice) or hasattr(col_idx, "__iter__"):
                col_idx = 0 if isinstance(col_idx, slice) else col_idx[0]

            desc_values = df.iloc[:, col_idx]
            # Check length >= 10
            desc_is_valid = desc_values.notna() & (
                desc_values.astype(str).str.strip().str.len() >= 10
            )

            # Also filter out typical introductory phrases (case-insensitive)
            desc_lower = desc_values.astype(str).str.lower()
            is_intro = (
                desc_lower.str.startswith("the below faults")
                | desc_lower.str.contains("during development", na=False)
                | desc_lower.str.startswith("the following")
                | desc_lower.str.startswith("faults found")
            )

            mask &= desc_is_valid & ~is_intro
        else:
            # If no description column, can't validate - keep all
            pass

        # Rule 2: At least one identifier (id, position) must exist and be valid
        has_identifier = pd.Series([False] * len(df), index=df.index)

        for _, col_name in [("id", id_col), ("position", pos_col)]:
            if col_name and col_name in df.columns:
                col_idx = df.columns.get_loc(col_name)
                if isinstance(col_idx, slice) or hasattr(col_idx, "__iter__"):
                    col_idx = 0 if isinstance(col_idx, slice) else col_idx[0]

                values = df.iloc[:, col_idx]
                # Check if not empty/NaN and not "unknown"
                is_valid = values.notna() & (
                    values.astype(str).str.strip().str.len() > 0
                )
                # Also exclude "unknown" as identifier
                is_not_unknown = ~(
                    values.astype(str).str.lower().str.strip() == "unknown"
                )
                has_identifier |= is_valid & is_not_unknown

        mask &= has_identifier

        # Rule 3: Position must not be "unknown" (even if ID exists)
        # This ensures we filter rows with unknown position
        if pos_col and pos_col in df.columns:
            col_idx = df.columns.get_loc(pos_col)
            if isinstance(col_idx, slice) or hasattr(col_idx, "__iter__"):
                col_idx = 0 if isinstance(col_idx, slice) else col_idx[0]

            pos_values = df.iloc[:, col_idx]
            # Filter out "unknown" positions
            pos_is_not_unknown = ~(
                pos_values.astype(str).str.lower().str.strip() == "unknown"
            )
            mask &= pos_is_not_unknown

        # Apply filter
        filtered_df = df[mask]

        # Log filtering results
        removed_count = len(df) - len(filtered_df)
        if removed_count > 0:
            logger.info(
                f"Filtered out {removed_count} meta/comment rows. "
                f"Remaining: {len(filtered_df)} valid defect rows."
            )

        return filtered_df

    def _find_column_mapping(self, columns: pd.Index) -> Dict[str, Optional[str]]:
        """Find best matching columns for each field using fuzzy matching.

        Args:
            columns: DataFrame columns

        Returns:
            Dict mapping field name to actual column name
        """
        # Define patterns for each field (lowercase)
        # Note: Order matters - patterns are tried in order, earlier = higher priority
        patterns = {
            "id": ["id", "defect_id", "defectid", "number", "nr", "no"],
            "position": ["position", "location", "section", "abschnitt", "stelle", "item"],
            "description": [
                "description",
                "descripion",  # Handle typo in real data
                "defect",
                "problem",
                "beschreibung",
                "text",
                "details",
                "summary",
                "fault",  # Move "fault" to end to avoid matching "Type of Fault" as description
            ],
            "risk": ["risk", "severity", "klasse", "prio", "priority", "sev"],
            "type": ["type of", "fault_type", "faulttype", "type", "m/w", "mw", "class", "kind"],  # "type of" before "type"
            "section": ["section", "component", "module", "bereich"],
            "page": ["page", "pagenum", "page_number", "seite"],
        }

        # Try to import rapidfuzz for better matching
        try:
            from rapidfuzz import fuzz

            use_fuzzy = True
        except ImportError:
            use_fuzzy = False

        mapping = {}

        for field, field_patterns in patterns.items():
            best_col = None
            best_score = 0
            best_pattern_idx = len(field_patterns)  # Track pattern priority

            for col in columns:
                col_str = str(col).lower().strip()
                col_words = col_str.replace("_", " ").replace("-", " ").split()

                # Check for exact or partial matches
                for pattern_idx, pattern in enumerate(field_patterns):
                    score = 0

                    if use_fuzzy:
                        # Use fuzzy matching
                        score = fuzz.ratio(pattern, col_str)
                        # Boost score if pattern is exact word match
                        if pattern in col_words:
                            score = max(score, 95)
                        # Also check if pattern is substring
                        elif pattern in col_str:
                            score = max(score, 85)
                    else:
                        # Simple heuristic with prioritization
                        # Exact word match gets highest score
                        if pattern in col_words:
                            score = 95
                        # Substring match
                        elif pattern in col_str:
                            score = 85
                        # Reverse substring (col in pattern)
                        elif col_str in pattern:
                            score = 70
                        else:
                            score = 0

                    # Prefer earlier patterns (higher priority) if scores are similar
                    # and prefer higher scores overall
                    if score > best_score or (score == best_score and pattern_idx < best_pattern_idx):
                        best_score = score
                        best_col = col
                        best_pattern_idx = pattern_idx

            # Only accept if score is above threshold
            if best_score >= 70:
                mapping[field] = best_col
            else:
                mapping[field] = None

        return mapping

    def _get_value(self, row, col_name: Optional[str], default=None):
        """Get value from row by column name.

        Args:
            row: DataFrame row
            col_name: Column name (or None if not mapped)
            default: Default value if column not found or empty

        Returns:
            Field value or default
        """
        if col_name is None:
            return default

        if col_name in row.index and pd.notna(row[col_name]):
            value = row[col_name]
            # Check if value is not empty string
            if isinstance(value, str) and value.strip() == "":
                return default
            return value

        return default

    def _extract_field(self, row, possible_names: List[str], default=None):
        """Extract field from row using possible column names.

        Args:
            row: DataFrame row
            possible_names: List of possible column names
            default: Default value if not found

        Returns:
            Field value or default
        """
        for name in possible_names:
            if name in row.index and pd.notna(row[name]):
                return row[name]
        return default

    def _normalize_risk(self, risk_str) -> RiskLevel:
        """Normalize risk string to RiskLevel enum.

        Args:
            risk_str: Risk string from Excel

        Returns:
            RiskLevel enum
        """
        if pd.isna(risk_str):
            return RiskLevel.UNK

        risk_str = str(risk_str).upper().strip()

        # Remove common prefixes/suffixes
        risk_str = risk_str.replace("RISK", "").replace("CLASS", "").strip()

        # Check for exact single letter match first
        if risk_str == "A":
            return RiskLevel.A
        elif risk_str == "B":
            return RiskLevel.B
        elif risk_str == "C":
            return RiskLevel.C

        # Check for keywords
        if "A" in risk_str or "HIGH" in risk_str or "CRITICAL" in risk_str or "1" in risk_str:
            return RiskLevel.A
        elif "B" in risk_str or "MEDIUM" in risk_str or "MODERATE" in risk_str or "2" in risk_str:
            return RiskLevel.B
        elif "C" in risk_str or "LOW" in risk_str or "MINOR" in risk_str or "3" in risk_str:
            return RiskLevel.C
        else:
            return RiskLevel.UNK

    def _normalize_fault_type(self, type_str) -> FaultType:
        """Normalize fault type string to FaultType enum.

        Args:
            type_str: Type string from Excel

        Returns:
            FaultType enum
        """
        if pd.isna(type_str):
            return FaultType.UNK

        type_str = str(type_str).upper().strip()

        # Check for exact match first
        if type_str == "M":
            return FaultType.M
        elif type_str == "W":
            return FaultType.W
        elif type_str in ["UNK", "UNKNOWN", "?", "", "N/A", "NA"]:
            return FaultType.UNK

        # Check for keywords (full words)
        if "MISSING" in type_str or "FEHLT" in type_str or "ABSENT" in type_str:
            return FaultType.M
        elif "WRONG" in type_str or "INCORRECT" in type_str or "FALSCH" in type_str or "ERROR" in type_str:
            return FaultType.W

        # If it contains M but not W (single letter), assume M
        # But only if the string is short (to avoid matching M in random words)
        if len(type_str) <= 3:
            if "M" in type_str and "W" not in type_str:
                return FaultType.M
            elif "W" in type_str and "M" not in type_str:
                return FaultType.W

        return FaultType.UNK
