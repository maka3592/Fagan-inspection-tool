"""Artifact loading and management with leakage protection."""

from pathlib import Path
from typing import Dict, List

from ..core.schemas import ArtifactMetadata
from .leakage_guard import LeakageGuard
from .pdf_extractor import PDFExtractor


class ArtifactLoader:
    """Load and manage inspection artifacts with leakage protection."""

    def __init__(self, base_path: Path = Path("artifacts/input")):
        """Initialize artifact loader.

        Args:
            base_path: Base directory for input artifacts
        """
        self.base_path = base_path

    def load_artifact(self, relative_path: str) -> Dict:
        """Load a single artifact.

        Args:
            relative_path: Path relative to base_path

        Returns:
            Dict with metadata and content

        Raises:
            ValueError: If path fails leakage check
            FileNotFoundError: If file doesn't exist
        """
        full_path = self.base_path / relative_path

        # CRITICAL: Leakage guard check
        LeakageGuard.validate_path(full_path)

        if not full_path.exists():
            raise FileNotFoundError(f"Artifact not found: {full_path}")

        # Extract content based on file type
        content = None
        page_count = None

        if full_path.suffix.lower() == ".pdf":
            extractor = PDFExtractor(full_path)
            pages = extractor.extract_pages()
            page_count = len(pages)
            content = {"type": "pdf_pages", "pages": pages}
        else:
            # Plain text file
            with open(full_path, "r", encoding="utf-8") as f:
                content = {"type": "text", "text": f.read()}

        metadata = ArtifactMetadata(
            name=full_path.name,
            path=relative_path,
            type=self._infer_type(relative_path),
            page_count=page_count,
            size_bytes=full_path.stat().st_size,
        )

        return {"metadata": metadata, "content": content}

    def load_artifacts(self, relative_paths: List[str]) -> List[Dict]:
        """Load multiple artifacts.

        Args:
            relative_paths: List of paths relative to base_path

        Returns:
            List of loaded artifacts with metadata and content

        Raises:
            ValueError: If any path fails leakage check
        """
        # Validate all paths first
        full_paths = [self.base_path / p for p in relative_paths]
        LeakageGuard.validate_paths(full_paths)

        artifacts = []
        for rel_path in relative_paths:
            try:
                artifact = self.load_artifact(rel_path)
                artifacts.append(artifact)
            except FileNotFoundError as e:
                print(f"Warning: {e}")

        return artifacts

    def _infer_type(self, path: str) -> str:
        """Infer artifact type from path.

        Args:
            path: Relative path

        Returns:
            Artifact type string
        """
        path_lower = path.lower()
        if "design" in path_lower or "stldd" in path_lower:
            return "design"
        elif "usecase" in path_lower or "use_case" in path_lower:
            return "usecase"
        elif "requirement" in path_lower or "req" in path_lower:
            return "requirements"
        elif "checklist" in path_lower or "cbr_checklist" in path_lower:
            return "checklist"
        elif "guide" in path_lower or "ubr" in path_lower or "pbr" in path_lower:
            return "guide"
        else:
            return "other"

    def get_artifact_summary(self, artifact: Dict) -> str:
        """Get human-readable summary of artifact.

        Args:
            artifact: Loaded artifact dict

        Returns:
            Summary string
        """
        meta = artifact["metadata"]
        content = artifact["content"]

        summary = f"{meta.name} ({meta.type})"
        if meta.page_count:
            summary += f" - {meta.page_count} pages"
        if content["type"] == "pdf_pages":
            total_chars = sum(len(p["text"]) for p in content["pages"])
            summary += f" - {total_chars:,} chars"

        return summary
