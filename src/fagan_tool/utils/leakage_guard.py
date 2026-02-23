"""Guard against gold standard leakage into agent prompts."""

from pathlib import Path
from typing import List


class LeakageGuard:
    """Prevent gold standard data from leaking into agent context."""

    FORBIDDEN_PATHS = ["artifacts/gold", "gold/", "/gold/"]
    FORBIDDEN_FILENAMES = ["Faults_List", "gold", "ground_truth", "reference"]

    @classmethod
    def validate_path(cls, path: Path | str) -> bool:
        """Check if path is safe (not from gold directory).

        Args:
            path: Path to validate

        Returns:
            True if safe, False if forbidden

        Raises:
            ValueError: If path points to gold standard data
        """
        path_str = str(path).replace("\\", "/")

        # Check for forbidden paths
        for forbidden in cls.FORBIDDEN_PATHS:
            if forbidden in path_str.lower():
                raise ValueError(
                    f"LEAKAGE GUARD: Path '{path}' contains forbidden directory '{forbidden}'. "
                    "Gold standard data must NEVER be loaded into agent context."
                )

        # Check for forbidden filenames
        for forbidden in cls.FORBIDDEN_FILENAMES:
            if forbidden.lower() in path_str.lower():
                raise ValueError(
                    f"LEAKAGE GUARD: Path '{path}' contains forbidden pattern '{forbidden}'. "
                    "Gold standard data must NEVER be loaded into agent context."
                )

        return True

    @classmethod
    def validate_paths(cls, paths: List[Path | str]) -> bool:
        """Validate multiple paths.

        Args:
            paths: List of paths to validate

        Returns:
            True if all safe

        Raises:
            ValueError: If any path is forbidden
        """
        for path in paths:
            cls.validate_path(path)
        return True

    @classmethod
    def is_gold_path(cls, path: Path | str) -> bool:
        """Check if path is in gold directory (non-raising).

        Args:
            path: Path to check

        Returns:
            True if path is in gold directory
        """
        path_str = str(path).replace("\\", "/").lower()
        return any(forbidden in path_str for forbidden in cls.FORBIDDEN_PATHS)
