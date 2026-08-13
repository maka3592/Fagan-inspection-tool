# results/

Aktive Ergebnisse des finalen, instrumentierten Datensatzes.

## Inhalt

- **`costed_split_soft_n10/`** — finaler aktiver Ergebnisdatensatz
  (40 Runs: 20 UBR + 20 CBR, n = 10). Enthält Coverage, Kosten,
  Komplementarität, manuelle Gold-Gegenprüfung u. a.
- **`costed_pbr_split_soft_n10/`** — supplementäre PBR-Zusatzanalyse
  (20 PBR-Runs; kein Teil des Hauptvergleichs).
- Manifest- und Usage-CSVs auf dieser Ebene (`costed_*_manifest*.csv`,
  `costed_split_soft_n10_usage_*.csv`) — Plan-/Status-Manifeste und
  Usage-Aggregate der finalen Läufe.
- `README.md` — diese Datei.

Die finalen Token-/Kostenauswertungen stammen aus den per-Run-Dateien
`runs/<run_id>/llm_usage.csv` (aggregiert unter
`costed_split_soft_n10/costs/`). Ein globaler Usage-Log
(`llm_usage_log.csv`) kann bei neuen Läufen technisch erneut entstehen,
gehört aber nicht zum vorhandenen finalen Ergebnisbestand.

## Bereinigt

Die alten, nicht-instrumentierten Baseline-/Sweep-Ergebnisse auf
Root-Level von `results/` (u. a. `raw_defects_*`, `per_reviewer_dedupe_*`,
`union_defects_*`, `incremental_*`, `saturation_*`, `gold_at_saturation_*`,
`cumulative_gold_*`, `manual_gold_match*`, `baseline_manifest.csv`,
`union_gold_t065/`, `union_gold_t060/`, `fault_share_t065/`,
`fault_share_t060/`) wurden nach Validierung des instrumentierten
Datensatzes entfernt. Es gibt keine alten Root-Level-Baseline-Results mehr.

## Finale Aussagen

Für finale, kostenbezogene Schlussfolgerungen siehe
`docs/FINAL_COSTED_EXPERIMENT_RESULTS.md`.
