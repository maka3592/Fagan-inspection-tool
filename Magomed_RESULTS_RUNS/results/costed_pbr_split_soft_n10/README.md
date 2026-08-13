# results/costed_pbr_split_soft_n10/ — PBR Supplementary Analysis

**PBR ist Supplementary Analysis, nicht der Hauptvergleich.** Der finale
quantitative Hauptvergleich bleibt `results/costed_split_soft_n10/` (UBR vs. CBR).

## Setup

- Technik: PBR (4× TESTER / 3× USER / 3× DESIGNER)
- 20 Runs, n = 10 Reviewer pro Run
- Modell: gpt-4o-mini, temperature 0.2, max_tokens 4096
- Scope: split-soft (identisch zum UBR/CBR-Setup)
- Goldstandard: 36 Fehler (A = 13, B = 13, C = 10) — nur Evaluation, kein Reviewer-Input

## Automatische Evaluation (kanonischer Matcher)

- Thresholds: t = 0,65 und t = 0,60
- Automatische Kandidaten-IDs: t = 0,65 → `8`; t = 0,60 → `7 8 9 28 32 38`

## Manuelle Validierung

- confirmed: `8`
- doubtful: `7, 28`
- rejected: `9, 32, 38`

## Ergebnis

- **Keine neuen bestätigten PBR-only Gold-IDs gegenüber UBR/CBR**
  (ID 8 ist bereits in der bestätigten UBR/CBR-Menge enthalten).
- **PBR liefert in diesem Setup keinen belegten Zusatznutzen** für eine
  Technik-Kombination.

## Warum dieser Ordner weniger Unteranalysen enthält als `costed_split_soft_n10/`

- PBR ist **Zusatzanalyse**, nicht Hauptvergleich.
- Es wurden nur Artefakte erzeugt, die **automatische Kandidaten, Kosten und
  manuelle Validierung** belegen:
  - `raw_defects/` (20 Roh-Defekt-CSVs)
  - `union_gold_t065/`, `union_gold_t060/` (automatische Gold-Coverage je Threshold)
  - `pbr_automatic_coverage.csv`, `pbr_match_candidates.csv`
  - `costs/pbr_cost_summary.csv`
  - `pbr_final_summary.json`
  - `costed_baseline_manifest.csv` (Eval-Eingabe)
- **Keine** Saturation-/Incremental-/Fault-share-Hauptanalyse für PBR, weil PBR
  **nicht** Teil des Hauptvergleichs wurde.

## Abgrenzung

- **Keine** hybride Lesetechnik evaluiert.
- Unionen mit PBR (`UBR ∪ PBR`, `CBR ∪ PBR`, `UBR ∪ CBR ∪ PBR`) sind **post-hoc
  Ergebnis-Merges**, keine hybriden Lesetechniken.

## Quellen / weiterführend

- `docs/PBR_SUPPLEMENTARY_MANUAL_VALIDATION_SUMMARY.md`
- `docs/PBR_MANUAL_VALIDATION_PACKET.md`
