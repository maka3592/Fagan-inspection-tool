# Fachliche Auswertung: `costed_split_soft_n10`

## Zweck

`costed_split_soft_n10` ist der finale instrumentierte Hauptdatensatz der
Untersuchung. Er umfasst 40 Runs (20 UBR und 20 CBR) mit jeweils n = 10
Reviewer-Aufrufen. Jeder Run enthält reale Tokenusage, technische
Laufzeit und listenpreisbasierte API-Kosten (USD). Alle Ergebnisse liegen
unter `results/costed_split_soft_n10/`.

## Reproduktion

```bash
python scripts/evaluate_costed_split_soft_n10.py
```

Das Skript führt die vollständige Auswertungspipeline über die 40 Runs
aus und schreibt alle Outputs nach `results/costed_split_soft_n10/`.
Für alle Auswertungen werden derselbe Goldstandard (`artifacts/gold/`)
und dieselbe Matching- und Evaluationslogik
(`src/fagan_tool/evaluation/`) verwendet. Thresholds: **0.65** (Haupt)
und **0.60** (Sensitivität).

## Output-Struktur

```
results/costed_split_soft_n10/
├── costed_baseline_manifest.csv     # internes Manifest der Pipeline-Skripte (status=ok, scope=split, n=10)
├── evaluation_manifest.csv          # dataset/run_id/technique/run_path/usage_file/usable
├── raw_defects/                     # raw_defects_<run_id>.csv (40)
├── per_reviewer_dedupe/             # per_reviewer_dedupe_<run_id>.csv (+ defect_frequency_summary)
├── union_defects/                   # union_defects_<run_id>.csv (40)
├── incremental/                     # incremental_<run_id>.csv (40)
├── saturation/                      # saturation_points_per_run.csv + _summary.csv
├── union_gold_t065/                 # union_gold_coverage_* + union_gold_ids_* (t=0.65)
├── union_gold_t060/                 # union_gold_coverage_* + union_gold_ids_* (t=0.60)
├── gold_at_saturation/              # gold_at_saturation_t065/t060_per_run + _summary
├── fault_share/t065|t060/           # fault_share_A/B_* (+ .png)
├── manual_gold_match/               # Validierung, Review-Sheet und Human-Summary
└── costs/                           # usage_by_run.csv, usage_by_technique.csv, cost_per_gold_tp_summary.csv u. a.
```

## Wichtigste automatische Ergebnisse

Die folgende Tabelle zeigt **automatische gepoolte Zuordnungskandidaten**
des Matchers. Sie sind keine manuell bestätigten Treffer.

| Threshold | Union TP | Union Recall | UBR | CBR | automatisch gematchte Gold-IDs |
|---:|---:|---:|---:|---:|---|
| 0.65 | 5/36 | 13.89% | 5 | 4 | 8, 28, 31, 32, 38 |
| 0.60 | 9/36 | 25.00% | 9 | 6 | 6, 7, 8, 25, 27, 28, 31, 32, 38 |

Reviewer-count-Sättigung: `k*` = 10 von 10 für UBR und CBR (keine frühe
Sättigung im Bereich k ≤ 10).

## Manuelle Gold-Match-Validierung

Die manuelle semantische Validierung der automatischen Kandidaten ist
abgeschlossen. Jeder Kandidat wurde anhand der konkreten LLM-Meldung und
des zugeordneten Goldstandard-Defekts geprüft. Die finalen
Entscheidungen liegen im Review-Sheet
`results/costed_split_soft_n10/manual_gold_match/manual_gold_match_review_sheet.csv`,
die Zusammenfassung in
`results/costed_split_soft_n10/manual_gold_match/manual_gold_match_human_summary.csv`.
Nur `confirmed` zählt als bestätigter Goldstandard-Treffer. Details und
Begründungen: `docs/COSTED_MANUAL_GOLD_MATCH_VALIDATION.md`.

## Kostenanalyse (nach Gold-Coverage)

Die Usage- und Kostenbasis liegt in `costs/usage_by_run.csv` und
`costs/usage_by_technique.csv` (listenpreisbasierte USD-Kosten auf Basis
realer Tokenusage). Die Kosten-pro-Gold-Treffer-Auswertung liegt in
`costs/cost_per_gold_tp_summary.csv` und weist Kosten je automatischem
Kandidaten und je manuell bestätigtem Goldstandard-Treffer aus.
Maßgeblich für Kosten pro bestätigtem Treffer sind die final
festgelegten manuellen Bewertungsentscheidungen (t = 0.65: 3 bestätigte
Gold-IDs, t = 0.60: 5 bestätigte Gold-IDs).
