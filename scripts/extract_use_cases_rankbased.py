#!/usr/bin/env python3
"""Heuristic, offline extractor for the rank-based use case PDF.

Reads ``artifacts/input/usecases/UseCasesRank_v3.4.pdf`` and writes a JSON
worklist to ``artifacts/input/usecases/UseCasesRank_v3.4_extracted.json``.
The worklist sits next to the use-case PDF because it *is* an input
artefact (not a run result): the inspection pipeline reads it when
building the UBR context. The extractor is purely regex-based — no LLM,
no network — so it can be re-run as often as needed without API cost. If
anything looks off, a ``warnings`` array is populated; fields the
extractor is unsure about are left empty rather than fabricated.

Schema (matches ``_render_extracted_use_case_worklist`` in process.py):

    {
      "source": "<relative path>",
      "extracted_at": "<ISO timestamp>",
      "use_cases": [
        {
          "id": "1.1",
          "title": "Taxi: Submit order",
          "purpose": "...",
          "tasks": ["A customer wants a taxi.", "..."],
          "variants": ["4b. No available taxis ..."]
        },
        ...
      ],
      "warnings": ["..."]
    }
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# Make the project's src/ importable so we can reuse PDFExtractor.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from fagan_tool.utils.pdf_extractor import PDFExtractor  # noqa: E402


HEADER_RE = re.compile(r"^\s*(\d+\.\d+)\s+(.+?)\s*$", re.MULTILINE)
TASK_LINE_RE = re.compile(r"^\s*(\d+)\s*[.)]\s*(.+?)\s*$")
VARIANT_LINE_RE = re.compile(r"^\s*(\d+[a-z])\s*[.)]?\s*(.+?)\s*$")
RUNNING_HEADER_RE = re.compile(
    r"^\s*(Use Cases for the Taxi Evolution.*|Document number:.*)$",
    re.IGNORECASE,
)


def _read_pdf_text(pdf_path: Path) -> str:
    extractor = PDFExtractor(pdf_path)
    pages = extractor.extract_pages()
    parts: List[str] = []
    for p in pages:
        parts.append(p.get("text", ""))
    return "\n".join(parts)


def _strip_running_headers(text: str) -> str:
    """Drop running-header lines (per-page document title / page number)."""
    cleaned_lines: List[str] = []
    for line in text.splitlines():
        if RUNNING_HEADER_RE.match(line):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def _parse_block(block: str, warnings: List[str], uc_id: str) -> Dict[str, object]:
    """Parse the body that follows a use case header into purpose/tasks/variants."""
    sections: Dict[str, List[str]] = {"purpose": [], "tasks": [], "variants": []}
    current: Optional[str] = None
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("purpose:"):
            current = "purpose"
            rest = line.split(":", 1)[1].strip()
            if rest:
                sections["purpose"].append(rest)
            continue
        if lower.startswith("tasks:"):
            current = "tasks"
            continue
        if lower.startswith("variants:"):
            current = "variants"
            continue
        if current is None:
            # Pre-Purpose text (rare). Treat as purpose continuation only if
            # the line looks like prose rather than a numbered enumeration.
            if not TASK_LINE_RE.match(line):
                sections.setdefault("purpose", []).append(line)
            continue
        if current == "purpose":
            sections["purpose"].append(line)
        elif current == "tasks":
            m = TASK_LINE_RE.match(line)
            if m:
                sections["tasks"].append(m.group(2).strip())
            elif sections["tasks"]:
                # Continuation of the previous task line (wrapped text).
                sections["tasks"][-1] = sections["tasks"][-1].rstrip() + " " + line
            else:
                warnings.append(
                    f"use case {uc_id}: unrecognised line in Tasks: {line!r}"
                )
        elif current == "variants":
            m = VARIANT_LINE_RE.match(line)
            if m:
                sections["variants"].append(f"{m.group(1)} {m.group(2).strip()}")
            elif sections["variants"]:
                sections["variants"][-1] = (
                    sections["variants"][-1].rstrip() + " " + line
                )
            else:
                # Some variants don't start with a number/letter; keep them.
                sections["variants"].append(line)

    purpose = " ".join(sections["purpose"]).strip()
    return {
        "purpose": purpose,
        "tasks": sections["tasks"],
        "variants": sections["variants"],
    }


def extract(pdf_path: Path) -> Dict[str, object]:
    warnings: List[str] = []
    if not pdf_path.exists():
        return {
            "source": str(pdf_path),
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "use_cases": [],
            "warnings": [f"PDF not found: {pdf_path}"],
        }

    text = _read_pdf_text(pdf_path)
    text = _strip_running_headers(text)

    # Find all section headers and slice the text between consecutive headers.
    headers = list(HEADER_RE.finditer(text))
    if not headers:
        warnings.append("No use case headers (pattern '<num>.<num> <title>') matched.")

    use_cases: List[Dict[str, object]] = []
    for i, m in enumerate(headers):
        uc_id = m.group(1).strip()
        title = m.group(2).strip()
        body_start = m.end()
        body_end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        block = text[body_start:body_end]
        parsed = _parse_block(block, warnings, uc_id)
        # Drop obvious non-UC headers like a top-level section "1 Use Cases"
        # that won't expose a Purpose paragraph.
        if not parsed["purpose"] and not parsed["tasks"] and not parsed["variants"]:
            warnings.append(
                f"use case {uc_id} '{title}': empty body — skipped"
            )
            continue
        use_cases.append({
            "id": uc_id,
            "title": title,
            "purpose": parsed["purpose"],
            "tasks": parsed["tasks"],
            "variants": parsed["variants"],
        })

    if not use_cases:
        warnings.append("No use cases extracted from PDF.")

    return {
        "source": str(pdf_path),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "use_cases": use_cases,
        "warnings": warnings,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--pdf",
        default="artifacts/input/usecases/UseCasesRank_v3.4.pdf",
        help="Source PDF (default: artifacts/input/usecases/UseCasesRank_v3.4.pdf)",
    )
    p.add_argument(
        "--out",
        default="artifacts/input/usecases/UseCasesRank_v3.4_extracted.json",
        help=(
            "Output JSON path "
            "(default: artifacts/input/usecases/UseCasesRank_v3.4_extracted.json)"
        ),
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)
    pdf_path = Path(args.pdf)
    out_path = Path(args.out)

    data = extract(pdf_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    n_uc = len(data["use_cases"])
    n_warn = len(data["warnings"])
    print(f"[uc_extract] Wrote {out_path} (use_cases={n_uc}, warnings={n_warn})")
    if n_warn:
        for w in data["warnings"][:5]:
            print(f"[uc_extract]   ! {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
