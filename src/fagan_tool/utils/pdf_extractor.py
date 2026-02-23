"""PDF text extraction with page tracking."""

import re
from pathlib import Path
from typing import Dict, List

import pdfplumber


class PDFExtractor:
    """Extract text from PDF files with page-level tracking."""

    def __init__(self, pdf_path: Path):
        """Initialize extractor.

        Args:
            pdf_path: Path to PDF file
        """
        self.pdf_path = pdf_path

    def extract_pages(self) -> List[Dict[str, str | int]]:
        """Extract text with page numbers.

        Returns:
            List of dicts with 'page_num' and 'text' keys
        """
        pages = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                pages.append({"page_num": i, "text": text})
        return pages

    def extract_with_headings(self) -> List[Dict[str, str | int]]:
        """Extract text with simple heading detection.

        Returns:
            List of dicts with 'page_num', 'text', and optional 'heading' keys
        """
        pages = []
        with pdfplumber.open(self.pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                # Simple heuristic: lines with < 60 chars and no ending punctuation
                lines = text.split("\n")
                heading = None
                for line in lines[:5]:  # Check first 5 lines
                    line_clean = line.strip()
                    if (
                        line_clean
                        and len(line_clean) < 60
                        and not line_clean.endswith((".", ",", ";"))
                        and line_clean[0].isupper()
                    ):
                        heading = line_clean
                        break

                pages.append({"page_num": i, "text": text, "heading": heading})
        return pages

    def extract_sections(self) -> Dict[str, str]:
        """Extract text by detected sections.

        Returns:
            Dict mapping section names to text content
        """
        sections = {}
        current_section = "Introduction"
        current_text = []

        pages = self.extract_with_headings()
        for page_data in pages:
            text = page_data["text"]
            heading = page_data.get("heading")

            # If heading detected, start new section
            if heading and len(heading) > 3:
                # Save previous section
                if current_text:
                    sections[current_section] = "\n".join(current_text)
                current_section = heading
                current_text = [text]
            else:
                current_text.append(text)

        # Save last section
        if current_text:
            sections[current_section] = "\n".join(current_text)

        return sections

    def get_page_count(self) -> int:
        """Get total page count.

        Returns:
            Number of pages in PDF
        """
        with pdfplumber.open(self.pdf_path) as pdf:
            return len(pdf.pages)

    @staticmethod
    def chunk_text(text: str, max_chars: int = 6000) -> List[str]:
        """Split text into chunks for LLM context.

        Args:
            text: Text to chunk
            max_chars: Maximum characters per chunk

        Returns:
            List of text chunks
        """
        # Split by paragraphs first
        paragraphs = re.split(r"\n\s*\n", text)
        chunks = []
        current_chunk = []
        current_length = 0

        for para in paragraphs:
            para_len = len(para)
            if current_length + para_len > max_chars and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [para]
                current_length = para_len
            else:
                current_chunk.append(para)
                current_length += para_len

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks
